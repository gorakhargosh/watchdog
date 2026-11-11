from __future__ import annotations

import contextlib
import errno
import logging
import os
import shutil
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

import watchdog.observers.polling as polling_mod
from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirMovedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)
from watchdog.observers.api import (
    BaseObserver,
    EventEmitter,
    ObservedWatch,
    SnapshotStatus,
    _WatchSyncState,
)
from watchdog.observers.polling import PollingEmitter, PollingObserver
from watchdog.utils.dirsnapshot import DirectorySnapshot
from watchdog.utils.sync import (
    SynchronizationComplete,
    diff_snapshot_events,
    stream_directory_events,
)

if TYPE_CHECKING:
    from typing import Any


class _IdleEmitter(EventEmitter):
    def queue_events(self, timeout: float) -> None:
        self.stopped_event.wait(timeout)


class _RecordingHandler(FileSystemEventHandler):
    def __init__(self, *, basename: bool = True, expected_count: int = 1) -> None:
        super().__init__()
        self.events: list[tuple[str, str, bool]] = []
        self.raw_events: list[FileSystemEvent] = []
        self.received = threading.Event()
        self._basename = basename
        self._expected_count = expected_count

    def on_any_event(self, event: FileSystemEvent) -> None:
        self.raw_events.append(event)
        path = os.fsdecode(event.src_path)
        label = os.path.basename(path) if self._basename else os.path.normpath(path)
        self.events.append((event.event_type, label, event.is_synthetic))
        if len(self.events) >= self._expected_count:
            self.received.set()


def _stage(obs: BaseObserver, watch: ObservedWatch, ev: FileSystemEvent) -> None:
    obs.event_queue.put((ev, watch))
    obs.dispatch_events(obs.event_queue)


def _drain_events(obs: BaseObserver) -> None:
    while not obs.event_queue.empty():
        obs.dispatch_events(obs.event_queue)


def test_synchronization_complete() -> None:
    w1 = ObservedWatch("/tmp/dir1", recursive=True)
    w2 = ObservedWatch("/tmp/dir1", recursive=True)
    w3 = ObservedWatch("/tmp/dir2", recursive=True)
    token1, token2 = object(), object()

    s1, s2, s3 = SynchronizationComplete(w1), SynchronizationComplete(w2), SynchronizationComplete(w3)

    assert s1 == s2
    assert s1 != s3
    assert hash(s1) == hash(s2)
    assert repr(s1) == f"<SynchronizationComplete: watch={w1!r}>"
    assert s1 != object()

    # Session token equality and isolation
    t1 = SynchronizationComplete(w1, session_token=token1)
    t1_same = SynchronizationComplete(w1, session_token=token1)
    t2 = SynchronizationComplete(w1, session_token=token2)
    assert t1 == t1_same
    assert t1 != t2
    assert hash(t1) == hash(t1_same)
    assert hash(t1) != hash(t2)

    # ObservedWatch sync flags normalize ordered_startup when emit_existing=False
    w_ignored = ObservedWatch("/tmp/dir1", recursive=False, emit_existing=False, ordered_startup=True)
    w_plain = ObservedWatch("/tmp/dir1", recursive=False)
    w_emit = ObservedWatch("/tmp/dir1", recursive=False, emit_existing=True)
    w_ordered = ObservedWatch("/tmp/dir1", recursive=False, emit_existing=True, ordered_startup=True)
    assert not w_ignored.ordered_startup
    assert w_ignored == w_plain
    assert len({w_plain, w_emit, w_ordered}) == 3
    assert "emit_existing=True" in repr(w_emit)
    assert "ordered_startup=True" in repr(w_ordered)


@pytest.mark.parametrize("sort_by_birthtime", [False, True])
def test_stream_events(sort_by_birthtime: bool) -> None:  # noqa: FBT001
    temp_dir = tempfile.mkdtemp(prefix="watchdog_stream_")
    try:
        assert list(stream_directory_events(temp_dir, sort_by_birthtime=sort_by_birthtime)) == []
        assert list(stream_directory_events("/nonexistent/path", sort_by_birthtime=sort_by_birthtime)) == []

        f1 = os.path.join(temp_dir, "a.txt")
        sub = os.path.join(temp_dir, "sub")
        f2 = os.path.join(sub, "b.txt")
        os.makedirs(sub)
        Path(f1).touch()
        Path(f2).touch()

        # Single file
        single = list(stream_directory_events(f1, sort_by_birthtime=sort_by_birthtime))
        assert len(single) == 1
        assert single[0].src_path == f1
        assert single[0].is_synthetic

        # Recursive directory
        events = list(stream_directory_events(temp_dir, recursive=True, sort_by_birthtime=sort_by_birthtime))
        assert all(ev.is_synthetic for ev in events)
        paths = [ev.src_path for ev in events]
        assert paths.index(sub) < paths.index(f2)  # Topological: dir before file
    finally:
        shutil.rmtree(temp_dir)


def test_snapshot_diff() -> None:
    temp_dir = tempfile.mkdtemp(prefix="watchdog_diff_")
    try:
        f_mod, f_del, f_mov1 = (os.path.join(temp_dir, n) for n in ("m.txt", "d.txt", "mv1.txt"))
        Path(f_mod).write_text("v1")
        os.utime(f_mod, (1_000_000, 1_000_000))
        Path(f_del).touch()
        Path(f_mov1).touch()
        snap1 = DirectorySnapshot(temp_dir)

        f_cre, f_mov2 = (os.path.join(temp_dir, n) for n in ("c.txt", "mv2.txt"))
        Path(f_cre).touch()
        Path(f_mod).write_text("v2_modified")
        os.utime(f_mod, (1_000_002, 1_000_002))
        os.remove(f_del)
        os.rename(f_mov1, f_mov2)
        snap2 = DirectorySnapshot(temp_dir)

        events = list(diff_snapshot_events(snap1, snap2))
        assert len(events) >= 4
        assert all(ev.is_synthetic for ev in events)
        types = {type(ev) for ev in events}
        assert {FileCreatedEvent, FileModifiedEvent, FileDeletedEvent, FileMovedEvent} <= types
    finally:
        shutil.rmtree(temp_dir)


@pytest.mark.parametrize("emit_existing", [False, True])
def test_observer_sync(tmp_path: Path, emit_existing: bool) -> None:  # noqa: FBT001
    (tmp_path / "f1.txt").touch()
    handler = _RecordingHandler()
    obs = BaseObserver(_IdleEmitter, timeout=0.01)
    obs.schedule(handler, tmp_path, recursive=False, emit_existing=emit_existing)
    obs.start()
    try:
        if emit_existing:
            assert handler.received.wait(timeout=2.0)
        else:
            handler.received.wait(timeout=0.05)
        expected = [("created", "f1.txt", True)] if emit_existing else []
        assert handler.events == expected
    finally:
        obs.stop()
        obs.join()


@pytest.mark.parametrize("empty_directory", [False, True])
def test_polling_sync(empty_directory: bool) -> None:  # noqa: FBT001
    temp_dir = tempfile.mkdtemp(prefix="watchdog_poll_")
    try:
        if not empty_directory:
            Path(os.path.join(temp_dir, "exist.txt")).touch()
        created: list[str] = []
        exist_event = threading.Event()
        new_event = threading.Event()

        class Handler(FileSystemEventHandler):
            def on_created(self, event: FileSystemEvent) -> None:
                name = os.path.basename(os.fsdecode(event.src_path))
                created.append(name)
                if name == "exist.txt":
                    exist_event.set()
                elif name == "new.txt":
                    new_event.set()

        obs = PollingObserver(timeout=0.05)
        obs.schedule(Handler(), temp_dir, recursive=False, emit_existing=True)
        obs.start()
        try:
            emitter = next(iter(obs.emitters))
            assert emitter.wait_for_snapshot(snapshot_timeout=1.0) is SnapshotStatus.SUCCESS

            if not empty_directory:
                assert exist_event.wait(timeout=2.0)
                assert "exist.txt" in created

            # Live creation after startup
            Path(os.path.join(temp_dir, "new.txt")).touch()
            assert new_event.wait(timeout=2.0)
            expected = ["new.txt"] if empty_directory else ["exist.txt", "new.txt"]
            assert created == expected
        finally:
            obs.stop()
            obs.join()
    finally:
        shutil.rmtree(temp_dir)


def test_ordered_sync(tmp_path: Path) -> None:
    for name in ("f1.txt", "f2.txt", "stale.txt"):
        (tmp_path / name).touch()
    events: list[tuple[str, str, bool]] = []
    done_event, unscheduled_safely = threading.Event(), threading.Event()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event: FileSystemEvent) -> None:
            events.append((event.event_type.upper(), os.path.basename(os.fsdecode(event.src_path)), event.is_synthetic))
            if event.event_type == "deleted":
                obs.unschedule(watch)
                unscheduled_safely.set()
            if len(events) >= 3:
                done_event.set()

    obs = BaseObserver(_IdleEmitter, timeout=0.01)
    watch = obs.schedule(Handler(), tmp_path, recursive=False, emit_existing=True, ordered_startup=True)
    current_token, stale_token = object(), object()
    obs._sync_state[watch] = _WatchSyncState(ordered_startup=True, session_token=current_token)  # noqa: SLF001

    stale_ev: Any = FileCreatedEvent(str(tmp_path / "stale.txt"), is_synthetic=True)
    stale_ev.session_token = stale_token
    obs.event_queue.put((stale_ev, watch))
    obs.event_queue.put((FileModifiedEvent(str(tmp_path / "f1.txt")), watch))
    obs.event_queue.put((FileDeletedEvent(str(tmp_path / "f2.txt")), watch))
    for name in ("f1.txt", "f2.txt"):
        ev: Any = FileCreatedEvent(str(tmp_path / name), is_synthetic=True)
        ev.session_token = current_token
        obs.event_queue.put((ev, watch))
    obs.event_queue.put((SynchronizationComplete(watch, session_token=current_token), watch))

    obs.start()
    try:
        assert done_event.wait(timeout=2.0)
        assert unscheduled_safely.is_set()
        assert events == [("CREATED", "f1.txt", True), ("MODIFIED", "f1.txt", False), ("DELETED", "f2.txt", False)]
    finally:
        obs.stop()
        obs.join()


def test_recreated_file_delivered(tmp_path: Path) -> None:
    (f := tmp_path / "item.txt").touch()
    handler = _RecordingHandler(expected_count=3)
    obs = BaseObserver(_IdleEmitter, timeout=0.01)
    # Schedule with emit_existing=False to prevent background sync worker from enqueuing duplicate events
    watch = obs.schedule(handler, tmp_path, recursive=False, emit_existing=False)
    obs._sync_state[watch] = _WatchSyncState()  # noqa: SLF001

    obs.event_queue.put((FileCreatedEvent(str(f), is_synthetic=True), watch))
    obs.event_queue.put((FileDeletedEvent(str(f)), watch))
    obs.event_queue.put((FileCreatedEvent(str(f)), watch))
    obs.event_queue.put((SynchronizationComplete(watch), watch))

    obs.start()
    try:
        assert handler.received.wait(timeout=2.0)
        assert handler.events == [
            ("created", "item.txt", True),
            ("deleted", "item.txt", False),
            ("created", "item.txt", False),
        ]
    finally:
        obs.stop()
        obs.join()


def test_stream_events_follow_symlink(tmp_path: Path) -> None:
    main_dir, ext_dir = tmp_path / "main", tmp_path / "ext"
    main_dir.mkdir()
    ext_dir.mkdir()
    (ext_dir / "ext.txt").touch()
    link_dir = main_dir / "link_to_ext"
    try:
        os.symlink(ext_dir, link_dir, target_is_directory=True)
        os.symlink(main_dir, ext_dir / "cycle", target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"Symlinks unavailable: {exc}")

    no_follow = {
        os.path.normpath(os.fsdecode(e.src_path)) for e in stream_directory_events(str(main_dir), recursive=True)
    }
    assert os.path.normpath(str(link_dir)) in no_follow
    assert os.path.normpath(str(link_dir / "ext.txt")) not in no_follow

    follow = {
        os.path.normpath(os.fsdecode(e.src_path))
        for e in stream_directory_events(str(main_dir), recursive=True, follow_symlink=True)
    }
    expected = {
        os.path.normpath(str(link_dir)),
        os.path.normpath(str(link_dir / "ext.txt")),
        os.path.normpath(str(link_dir / "cycle")),
    }
    assert expected <= follow


def test_stream_events_non_recursive_and_mtime_fallback(tmp_path: Path) -> None:
    """recursive=False stays shallow and sort_by_birthtime falls back to mtime ordering."""
    (sub := tmp_path / "sub").mkdir()
    (top := tmp_path / "top.txt").write_text("top")
    (nested := sub / "nested.txt").write_text("nested")

    non_rec = {e.src_path for e in stream_directory_events(str(tmp_path), recursive=False)}
    assert {str(top), str(sub)} <= non_rec
    assert str(nested) not in non_rec

    (z_old := tmp_path / "z_old.txt").write_text("old")
    (a_new := tmp_path / "a_new.txt").write_text("new")
    os.utime(z_old, (500, 500))
    os.utime(a_new, (3000, 3000))
    with patch("watchdog.utils.sync.get_path_birthtime_ns", return_value=None):
        names = [
            os.path.basename(os.fsdecode(ev.src_path))
            for ev in stream_directory_events(str(tmp_path), recursive=False, sort_by_birthtime=True)
            if isinstance(ev, FileCreatedEvent)
        ]
    assert names.index("z_old.txt") < names.index("a_new.txt")


@pytest.mark.parametrize("sort_by_birthtime", [False, True])
def test_stream_events_cancellation(tmp_path: Path, sort_by_birthtime: bool) -> None:  # noqa: FBT001
    """Signaling cancel_event or stop_event aborts traversal cooperatively."""
    for name in ("a.txt", "b.txt", "c.txt"):
        (tmp_path / name).write_text(name)

    cancel_event = threading.Event()
    gen = stream_directory_events(
        str(tmp_path),
        recursive=False,
        sort_by_birthtime=sort_by_birthtime,
        cancel_event=cancel_event,
    )
    assert next(gen).is_synthetic
    cancel_event.set()
    assert list(gen) == []

    stop_event = threading.Event()
    stop_event.set()
    assert not list(stream_directory_events(str(tmp_path), sort_by_birthtime=sort_by_birthtime, stop_event=stop_event))


def test_emit_existing_single_file_and_event_filter(tmp_path: Path) -> None:
    """Single-file emit_existing and event_filter restrict synthetic startup events accurately."""
    (target := tmp_path / "target.txt").write_text("target")
    (tmp_path / "sibling.txt").write_text("sibling")
    (sub := tmp_path / "sub").mkdir()
    (sub / "leaf.txt").write_text("leaf")

    obs_single = BaseObserver(_IdleEmitter, timeout=0.01)
    h_single = _RecordingHandler()
    obs_single.schedule(h_single, target, recursive=False, emit_existing=True)
    obs_single.start()
    try:
        assert h_single.received.wait(timeout=2.0)
        obs_single.event_queue.join()
        assert h_single.events == [("created", "target.txt", True)]
    finally:
        obs_single.stop()
        obs_single.join(timeout=2.0)

    obs_filtered = BaseObserver(_IdleEmitter, timeout=0.01)
    h_filtered = _RecordingHandler(expected_count=3)
    obs_filtered.schedule(h_filtered, tmp_path, recursive=True, event_filter=[FileCreatedEvent], emit_existing=True)
    obs_filtered.start()
    try:
        assert h_filtered.received.wait(timeout=2.0)
        obs_filtered.event_queue.join()
        assert h_filtered.raw_events
        assert all(isinstance(ev, FileCreatedEvent) for ev in h_filtered.raw_events)
        assert not any(isinstance(ev, DirCreatedEvent) for ev in h_filtered.raw_events)
        assert {name for _, name, _ in h_filtered.events} == {"target.txt", "sibling.txt", "leaf.txt"}
    finally:
        obs_filtered.stop()
        obs_filtered.join(timeout=2.0)


def test_ordered_startup_reconciliation_end_to_end(tmp_path: Path) -> None:
    """Ordered startup reconciles A->B moves, overwritten moves, and ping-pong chains cleanly."""

    def setup(name: str) -> tuple[Path, BaseObserver, _RecordingHandler, Any]:
        root = tmp_path / name
        root.mkdir()
        obs = BaseObserver(_IdleEmitter, timeout=0.01)
        handler = _RecordingHandler()
        watch = obs.schedule(handler, root, recursive=False, emit_existing=True, ordered_startup=True)
        return root, obs, handler, watch

    def flush_synthetic(obs: BaseObserver, watch: Any, path: Path) -> None:
        token = obs._sync_state[watch].session_token  # noqa: SLF001
        ev: Any = FileCreatedEvent(str(path), is_synthetic=True)
        ev.session_token = token
        obs.event_queue.put((ev, watch))
        obs.event_queue.put((SynchronizationComplete(watch, session_token=token), watch))
        _drain_events(obs)

    # 1. Real _sync_worker() discovery after live A->B move drops obsolete Created(A) and Moved(A, B)
    root1, obs1, h1, w1 = setup("move")
    (f_a := root1 / "A.txt").write_text("a")
    f_b = root1 / "B.txt"
    _stage(obs1, w1, FileCreatedEvent(str(f_a), is_synthetic=False))
    os.rename(f_a, f_b)
    _stage(obs1, w1, FileMovedEvent(str(f_a), str(f_b), is_synthetic=False))
    st1 = obs1._sync_state[w1]  # noqa: SLF001
    obs1._sync_worker(w1, st1, st1.session_token, obs1._emitter_for_watch[w1])  # noqa: SLF001
    _drain_events(obs1)
    assert h1.events == [("created", "B.txt", True)]

    # 2. Overwritten move destination (A->B then C->B) drops both obsolete moves
    root2, obs2, h2, w2 = setup("overwrite")
    (c2_a := root2 / "A.txt").write_text("a")
    (c2_c := root2 / "C.txt").write_text("c")
    c2_b = root2 / "B.txt"
    os.rename(c2_a, c2_b)
    _stage(obs2, w2, FileMovedEvent(str(c2_a), str(c2_b), is_synthetic=False))
    os.replace(c2_c, c2_b)
    _stage(obs2, w2, FileMovedEvent(str(c2_c), str(c2_b), is_synthetic=False))
    flush_synthetic(obs2, w2, c2_b)
    assert h2.events == [("created", "B.txt", True)]

    # 3. Ping-pong chain A -> B -> A drops intermediate moves before startup discovery
    root3, obs3, h3, w3 = setup("pingpong")
    (p_a := root3 / "A.txt").write_text("a")
    p_b = root3 / "B.txt"
    os.rename(p_a, p_b)
    _stage(obs3, w3, FileMovedEvent(str(p_a), str(p_b), is_synthetic=False))
    os.rename(p_b, p_a)
    _stage(obs3, w3, FileMovedEvent(str(p_b), str(p_a), is_synthetic=False))
    flush_synthetic(obs3, w3, p_a)
    assert h3.events == [("created", "A.txt", True)]


@pytest.mark.parametrize("mode", ["recreate", "move_overwrite", "move_out_recreate", "move_out_move_in"])
def test_pre_scan_delete_races(tmp_path: Path, mode: str) -> None:
    """Live removal (Deleted or Moved-out) before recreate or Moved-in keeps startup catch-up consistent."""
    (file_a := tmp_path / "A.txt").write_text("old_a")
    obs = BaseObserver(_IdleEmitter, timeout=0.01)
    handler = _RecordingHandler()
    watch = obs.schedule(handler, tmp_path, recursive=False, emit_existing=True, ordered_startup=True)
    token = obs._sync_state[watch].session_token  # noqa: SLF001

    synth_paths = [file_a]
    if mode in ("recreate", "move_overwrite"):
        file_a.unlink()
        _stage(obs, watch, FileDeletedEvent(str(file_a), is_synthetic=False))
    else:
        file_c = tmp_path / "C.txt"
        os.rename(file_a, file_c)
        _stage(obs, watch, FileMovedEvent(str(file_a), str(file_c), is_synthetic=False))
        synth_paths.append(file_c)

    if mode == "recreate":
        file_a.write_text("v2")
        _stage(obs, watch, FileCreatedEvent(str(file_a), is_synthetic=False))
        expected = [("created", "A.txt", True), ("deleted", "A.txt", False), ("created", "A.txt", False)]
    elif mode == "move_overwrite":
        (file_b := tmp_path / "B.txt").write_text("from_b")
        os.rename(file_b, file_a)
        _stage(obs, watch, FileMovedEvent(str(file_b), str(file_a), is_synthetic=False))
        expected = [("created", "A.txt", True)]
    elif mode == "move_out_recreate":
        file_a.write_text("v2")
        _stage(obs, watch, FileCreatedEvent(str(file_a), is_synthetic=False))
        expected = [("created", "A.txt", True), ("moved", "A.txt", False), ("created", "A.txt", False)]
    else:
        (file_b := tmp_path / "B.txt").write_text("from_b")
        os.rename(file_b, file_a)
        _stage(obs, watch, FileMovedEvent(str(file_b), str(file_a), is_synthetic=False))
        expected = [("created", "A.txt", True), ("moved", "A.txt", False), ("moved", "B.txt", False)]

    for path in synth_paths:
        ev_synth: Any = FileCreatedEvent(str(path), is_synthetic=True)
        ev_synth.session_token = token
        obs.event_queue.put((ev_synth, watch))
    obs.event_queue.put((SynchronizationComplete(watch, session_token=token), watch))
    _drain_events(obs)

    assert file_a.exists()
    assert handler.events == expected


@pytest.mark.parametrize("vanish_mode", ["during_wait", "before_wait"])
def test_polling_vanished_dir_fails(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    vanish_mode: str,
) -> None:
    """Vanished root dir during or before wait_for_snapshot must report FAILED, tear down sync, and deliver delete."""
    (watch_dir := tmp_path / "watched").mkdir()
    (watch_dir / "f1.txt").write_text("hello")
    obs = PollingObserver(timeout=0.01)
    handler = _RecordingHandler(basename=False)
    watch = obs.schedule(handler, watch_dir, recursive=False, emit_existing=True, ordered_startup=True)
    sync_state = obs._sync_state[watch]  # noqa: SLF001
    emitter = obs._emitter_for_watch[watch]  # noqa: SLF001
    emitter.on_thread_start()

    holder: dict[str, Any] = {}
    waiter_entered, emitter_stopped = threading.Event(), threading.Event()
    orig_wait, orig_take = emitter.wait_for_snapshot, emitter._take_snapshot  # noqa: SLF001

    def wrapped_wait(*args: Any, **kwargs: Any) -> SnapshotStatus:
        waiter_entered.set()
        if vanish_mode == "before_wait":
            assert emitter_stopped.wait(timeout=2.0)
        holder["status"] = orig_wait(*args, **kwargs)
        return holder["status"]

    emitter.wait_for_snapshot = wrapped_wait
    if vanish_mode == "during_wait":

        def vanish_on_poll() -> DirectorySnapshot:
            with emitter._snapshot_cond:  # noqa: SLF001
                assert emitter._snapshot_waiting_seqs.get(1, 0) > 0  # noqa: SLF001
            shutil.rmtree(watch_dir)
            return orig_take()

        emitter._take_snapshot = vanish_on_poll  # noqa: SLF001

    def run_poll() -> None:
        assert waiter_entered.wait(timeout=2.0)
        if vanish_mode == "during_wait":
            assert emitter._wake_event.wait(timeout=2.0)  # noqa: SLF001
        else:
            shutil.rmtree(watch_dir)
        emitter.queue_events(0.0)
        emitter_stopped.set()

    poll_thread = threading.Thread(target=run_poll)
    with caplog.at_level(logging.CRITICAL, logger="watchdog.observers.api"):
        poll_thread.start()
        try:
            obs._sync_worker(watch, sync_state, sync_state.session_token, emitter)  # noqa: SLF001
        finally:
            poll_thread.join(timeout=2.0)

    assert not poll_thread.is_alive()
    assert holder.get("status") is SnapshotStatus.FAILED
    _drain_events(obs)
    assert watch not in obs._sync_state  # noqa: SLF001
    assert ("deleted", os.path.normpath(str(watch_dir)), False) in handler.events


@pytest.mark.parametrize("use_cancel_event", [True, False])
def test_polling_cancel_returns_cancelled(tmp_path: Path, use_cancel_event: bool) -> None:  # noqa: FBT001
    """Explicit cancel_event or clean emitter stop must return SnapshotStatus.CANCELLED."""
    (tmp_path / "f1.txt").write_text("hello")
    obs = PollingObserver(timeout=0.01)
    watch = obs.schedule(FileSystemEventHandler(), tmp_path, recursive=False, emit_existing=True)
    emitter = obs._emitter_for_watch[watch]  # noqa: SLF001
    assert emitter.wait_for_snapshot(snapshot_timeout=0.01) is SnapshotStatus.TIMEOUT
    emitter.on_thread_start()
    cancel_ev = threading.Event() if use_cancel_event else None

    def trigger_stop() -> None:
        assert emitter._wake_event.wait(timeout=2.0)  # noqa: SLF001
        if cancel_ev is not None:
            cancel_ev.set()
        emitter.stop()

    stopper = threading.Thread(target=trigger_stop)
    stopper.start()
    try:
        assert emitter.wait_for_snapshot(cancel_event=cancel_ev) is SnapshotStatus.CANCELLED
    finally:
        stopper.join(timeout=2.0)


def test_slow_polling_snapshot(tmp_path: Path) -> None:
    """Healthy polling snapshot taking >2.0s must not fail startup sync with TIMEOUT."""
    (tmp_path / "pre1.txt").write_text("1")
    (tmp_path / "pre2.txt").write_text("2")

    clock = {"now": 100.0}
    wait_mode_known, wait_has_no_deadline = threading.Event(), threading.Event()
    clock_advanced, waiter_polled_after_jump = threading.Event(), threading.Event()

    class _SnapshotCondProxy:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        def __enter__(self) -> Any:
            return self._inner.__enter__()

        def __exit__(self, *args: object) -> Any:
            return self._inner.__exit__(*args)

        def _finish_wait(self, res: Any) -> Any:
            if clock_advanced.is_set() and not waiter_polled_after_jump.is_set():
                waiter_polled_after_jump.set()
            return res

        def wait(self, timeout: float | None = None) -> Any:
            if timeout is None:
                wait_has_no_deadline.set()
            wait_mode_known.set()
            return self._finish_wait(self._inner.wait(timeout=timeout))

        def wait_for(self, predicate: Any, timeout: float | None = None) -> Any:
            if timeout is None:
                wait_has_no_deadline.set()
            wait_mode_known.set()
            return self._finish_wait(self._inner.wait_for(predicate, timeout=timeout))

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

    with patch.object(polling_mod, "time", SimpleNamespace(monotonic=lambda: clock["now"])):
        obs = PollingObserver(timeout=0.01)
        handler = _RecordingHandler()
        watch = obs.schedule(handler, tmp_path, recursive=False, emit_existing=True, ordered_startup=True)
        sync_state = obs._sync_state[watch]  # noqa: SLF001
        emitter = obs._emitter_for_watch[watch]  # noqa: SLF001
        emitter.on_thread_start()
        emitter._snapshot_cond = _SnapshotCondProxy(emitter._snapshot_cond)  # noqa: SLF001

        holder: dict[str, Any] = {}
        orig_wait, orig_take = emitter.wait_for_snapshot, emitter._take_snapshot  # noqa: SLF001

        def tracked_wait(*args: Any, **kwargs: Any) -> SnapshotStatus:
            holder["wait_status"] = orig_wait(*args, **kwargs)
            return holder["wait_status"]

        def slow_take() -> DirectorySnapshot:
            assert wait_mode_known.wait(timeout=2.0)
            clock["now"] = 102.5
            clock_advanced.set()
            if not wait_has_no_deadline.is_set():
                assert waiter_polled_after_jump.wait(timeout=2.0)
            return orig_take()

        def run_poll() -> None:
            assert emitter._wake_event.wait(timeout=2.0)  # noqa: SLF001
            emitter.queue_events(0.0)

        emitter.wait_for_snapshot = tracked_wait
        emitter._take_snapshot = slow_take  # noqa: SLF001
        poll_thread = threading.Thread(target=run_poll)
        poll_thread.start()
        try:
            obs._sync_worker(watch, sync_state, sync_state.session_token, emitter)  # noqa: SLF001
        finally:
            poll_thread.join(timeout=2.0)

        assert not poll_thread.is_alive()
        assert holder.get("wait_status") is SnapshotStatus.SUCCESS
        _drain_events(obs)
        assert sorted(handler.events) == [("created", "pre1.txt", True), ("created", "pre2.txt", True)]


def test_async_startup_dedup(tmp_path: Path) -> None:
    """Async emitter wait_for_snapshot() must not finish sync while pending live creations are buffered."""
    (target_file := tmp_path / "A.txt").write_text("hello")
    entered_queue = threading.Event()
    release_buffer = threading.Event()
    buffer_queued = threading.Event()
    entered_wait = threading.Event()
    exited_wait = threading.Event()

    class _BufferedAsyncEmitter(EventEmitter):
        def __init__(self, event_queue: Any, watch: ObservedWatch, *, timeout: float = 0.05, **kwargs: Any) -> None:
            super().__init__(event_queue, watch, timeout=timeout, **kwargs)
            self._flushed = False

        def queue_events(self, timeout: float) -> None:
            if not self._flushed:
                self._flushed = True
                entered_queue.set()
                if release_buffer.wait(timeout=2.0):
                    self.queue_event(FileCreatedEvent(str(target_file)))
                    buffer_queued.set()
                return
            self.stopped_event.wait(timeout)

    obs = BaseObserver(_BufferedAsyncEmitter, timeout=0.05)
    handler = _RecordingHandler()
    watch = obs.schedule(handler, tmp_path, recursive=False, emit_existing=True, ordered_startup=True)
    sync_state = obs._sync_state[watch]  # noqa: SLF001
    emitter = obs._emitter_for_watch[watch]  # noqa: SLF001

    orig_wait = emitter.wait_for_snapshot

    def tracked_wait(*args: Any, **kwargs: Any) -> SnapshotStatus:
        entered_wait.set()
        try:
            return orig_wait(*args, **kwargs)
        finally:
            exited_wait.set()

    emitter.wait_for_snapshot = tracked_wait
    emitter.start()
    sync_thread = threading.Thread(
        target=obs._sync_worker,  # noqa: SLF001
        args=(watch, sync_state, sync_state.session_token, emitter),
    )
    try:
        assert entered_queue.wait(timeout=2.0)
        sync_thread.start()
        assert entered_wait.wait(timeout=2.0)
        # Buggy no-op wait_for_snapshot() returns immediately before queue_events() drains;
        # a genuine barrier waits until release_buffer lets the pending creation flush.
        exited_wait.wait(timeout=0.05)
        release_buffer.set()
        assert buffer_queued.wait(timeout=2.0)
        sync_thread.join(timeout=2.0)
        assert not sync_thread.is_alive()
    finally:
        release_buffer.set()
        emitter.stop()
        emitter.join(timeout=2.0)
        sync_thread.join(timeout=2.0)

    _drain_events(obs)
    assert handler.events == [("created", "A.txt", True)]


def test_failure_flush_on_dispatcher(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Failed startup wait must flush staged events via dispatcher thread, never concurrently from _sync_worker."""
    (watch_dir := tmp_path / "watched").mkdir()
    staged_file = watch_dir / "staged.txt"
    live_file = watch_dir / "live_after_fail.txt"

    active_lock = threading.Lock()
    active_callbacks = 0
    overlap_detected = False
    handler_tids: list[int] = []
    staged_entered = threading.Event()
    release_staged = threading.Event()
    live_entered = threading.Event()
    live_finished = threading.Event()

    class _SerializeProbeHandler(FileSystemEventHandler):
        def __init__(self) -> None:
            super().__init__()
            self.events: list[tuple[str, str, bool]] = []

        def on_any_event(self, event: FileSystemEvent) -> None:
            nonlocal active_callbacks, overlap_detected
            tid = threading.get_ident()
            name = os.path.basename(os.fsdecode(event.src_path))
            with active_lock:
                active_callbacks += 1
                if active_callbacks > 1:
                    overlap_detected = True
                handler_tids.append(tid)
            try:
                if name == "staged.txt":
                    staged_entered.set()
                    assert release_staged.wait(timeout=2.0)
                elif name == "live_after_fail.txt":
                    live_entered.set()
                self.events.append((event.event_type, name, event.is_synthetic))
            finally:
                with active_lock:
                    active_callbacks -= 1
                if name == "live_after_fail.txt":
                    live_finished.set()

    obs = BaseObserver(_IdleEmitter, timeout=0.05)
    handler = _SerializeProbeHandler()
    watch = obs.schedule(handler, watch_dir, recursive=False, emit_existing=True, ordered_startup=True)
    sync_state = obs._sync_state[watch]  # noqa: SLF001
    emitter = obs._emitter_for_watch[watch]  # noqa: SLF001

    _stage(obs, watch, FileModifiedEvent(str(staged_file), is_synthetic=False))
    emitter.wait_for_snapshot = lambda *, cancel_event=None: SnapshotStatus.FAILED

    disp_tid_box: dict[str, int] = {}
    disp_ready = threading.Event()
    stop_disp = threading.Event()

    def run_dispatcher() -> None:
        disp_tid_box["tid"] = threading.get_ident()
        disp_ready.set()
        while not stop_disp.is_set():
            obs.dispatch_events(obs.event_queue)

    disp_thread = threading.Thread(target=run_dispatcher, name="TestDispatcher")
    sync_thread = threading.Thread(
        target=obs._sync_worker,  # noqa: SLF001
        args=(watch, sync_state, sync_state.session_token, emitter),
        name="TestSyncWorker",
    )
    with caplog.at_level(logging.CRITICAL, logger="watchdog.observers.api"):
        disp_thread.start()
        try:
            assert disp_ready.wait(timeout=2.0)
            sync_thread.start()
            assert staged_entered.wait(timeout=2.0)

            obs.event_queue.put((FileCreatedEvent(str(live_file), is_synthetic=False), watch))
            # Buggy path completes sync early so dispatcher runs live event concurrently with _sync_worker.
            live_entered.wait(timeout=0.05)
            release_staged.set()
            assert live_finished.wait(timeout=2.0)
            sync_thread.join(timeout=2.0)
        finally:
            release_staged.set()
            stop_disp.set()
            obs.event_queue.put_nowait(obs.stop_event)
            sync_thread.join(timeout=2.0)
            disp_thread.join(timeout=2.0)

    disp_tid = disp_tid_box["tid"]
    assert not overlap_detected
    assert handler_tids == [disp_tid, disp_tid]
    assert handler.events == [("modified", "staged.txt", False), ("created", "live_after_fail.txt", False)]


@pytest.mark.parametrize("ordered_startup", [False, True])
def test_subtree_move_reconcile(
    tmp_path: Path,
    ordered_startup: bool,  # noqa: FBT001
) -> None:
    """Moving an already-scanned directory before destination scan must not emit duplicate descendant creations."""
    (watch_dir := tmp_path / "watched").mkdir()
    dir_a = watch_dir / "A"
    dir_a_sub = dir_a / "sub"
    file_in_sub = dir_a_sub / "file.txt"
    dir_b = watch_dir / "B"
    dest_a = dir_b / "A"
    dest_sub = dest_a / "sub"
    dest_file = dest_sub / "file.txt"

    dir_a_sub.mkdir(parents=True)
    file_in_sub.write_text("hello")
    dir_b.mkdir()

    obs = BaseObserver(_IdleEmitter)
    recorded: list[tuple[str, str, bool]] = []

    class _RelHandler(FileSystemEventHandler):
        def on_any_event(self, event: FileSystemEvent) -> None:
            rel_src = os.path.relpath(os.fsdecode(event.src_path), watch_dir).replace(os.sep, "/")
            dest = getattr(event, "dest_path", "")
            if dest:
                rel_dest = os.path.relpath(os.fsdecode(dest), watch_dir).replace(os.sep, "/")
                label = f"{rel_src} -> {rel_dest}"
            else:
                label = rel_src
            recorded.append((event.event_type, label, event.is_synthetic))

    watch = obs.schedule(_RelHandler(), watch_dir, recursive=True, emit_existing=True, ordered_startup=ordered_startup)
    token = obs._sync_state[watch].session_token  # noqa: SLF001

    def put_synth(ev: FileSystemEvent) -> None:
        ev.session_token = token
        obs.event_queue.put((ev, watch))

    # 1. Startup scanner discovers A and its descendants before the directory move.
    for ev in (
        DirCreatedEvent(str(dir_a), is_synthetic=True),
        DirCreatedEvent(str(dir_a_sub), is_synthetic=True),
        FileCreatedEvent(str(file_in_sub), is_synthetic=True),
        DirCreatedEvent(str(dir_b), is_synthetic=True),
    ):
        put_synth(ev)
    _drain_events(obs)

    # 2. Live OS move relocates A -> B/A before scanner walks B/A.
    os.rename(dir_a, dest_a)
    _stage(obs, watch, DirMovedEvent(str(dir_a), str(dest_a), is_synthetic=False))

    # 3. Startup scanner subsequently walks destination subtree B/A.
    for ev in (
        DirCreatedEvent(str(dest_a), is_synthetic=True),
        DirCreatedEvent(str(dest_sub), is_synthetic=True),
        FileCreatedEvent(str(dest_file), is_synthetic=True),
    ):
        put_synth(ev)
    obs.event_queue.put((SynchronizationComplete(watch, session_token=token), watch))
    _drain_events(obs)

    assert recorded == [
        ("created", "A", True),
        ("created", "A/sub", True),
        ("created", "A/sub/file.txt", True),
        ("created", "B", True),
        ("moved", "A -> B/A", False),
    ]


def test_polling_transient_error_recovery(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Transient OSError while PollingEmitter remains healthy must retry startup wait instead of aborting."""
    (watch_dir := tmp_path / "watched").mkdir()
    (watch_dir / "pre.txt").write_text("v1")
    obs = PollingObserver(timeout=0.01)
    handler = _RecordingHandler()
    watch = obs.schedule(handler, watch_dir, recursive=False, emit_existing=True, ordered_startup=True)
    sync_state = obs._sync_state[watch]  # noqa: SLF001
    emitter = obs._emitter_for_watch[watch]  # noqa: SLF001
    emitter.on_thread_start()
    (watch_dir / "race.txt").write_text("v2")

    calls = 0
    orig_take = emitter._take_snapshot  # noqa: SLF001
    orig_wait = emitter.wait_for_snapshot
    holder: dict[str, Any] = {}
    wait_entered = threading.Event()
    sync_done = threading.Event()

    def flaky_take() -> DirectorySnapshot:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(errno.EIO, "transient I/O error")
        return orig_take()

    def tracked_wait(*args: Any, **kwargs: Any) -> SnapshotStatus:
        wait_entered.set()
        holder["status"] = orig_wait(*args, **kwargs)
        return holder["status"]

    emitter._take_snapshot = flaky_take  # noqa: SLF001
    emitter.wait_for_snapshot = tracked_wait

    def run_sync() -> None:
        try:
            obs._sync_worker(watch, sync_state, sync_state.session_token, emitter)  # noqa: SLF001
        finally:
            sync_done.set()

    def run_polls() -> None:
        assert wait_entered.wait(timeout=2.0)
        assert emitter._wake_event.wait(timeout=2.0)  # noqa: SLF001
        emitter.queue_events(0.0)
        if not sync_done.wait(timeout=0.05):
            emitter.queue_events(0.0)

    sync_thread = threading.Thread(target=run_sync)
    poll_thread = threading.Thread(target=run_polls)
    with caplog.at_level(logging.WARNING, logger="watchdog.observers.polling"):
        sync_thread.start()
        poll_thread.start()
        try:
            sync_thread.join(timeout=2.0)
            poll_thread.join(timeout=2.0)
        finally:
            sync_thread.join(timeout=2.0)
            poll_thread.join(timeout=2.0)

    assert not sync_thread.is_alive()
    assert not poll_thread.is_alive()
    assert emitter.should_keep_running()
    assert holder.get("status") is SnapshotStatus.SUCCESS
    assert "will retry" in caplog.text
    assert calls >= 2
    _drain_events(obs)
    # Directory modification on child creation is filesystem/OS-dependent (e.g. absent on Windows NTFS).
    events = [e for e in handler.events if not (e[0] == "modified" and e[1] == "watched")]
    assert sorted(events) == [
        ("created", "pre.txt", True),
        ("created", "race.txt", True),
    ]


def _wait_for_startup_sync(obs: BaseObserver) -> None:
    with obs._lock:  # noqa: SLF001
        sync_threads = list(obs._sync_threads)  # noqa: SLF001
    for t in sync_threads:
        t.join(timeout=3.0)
        assert not t.is_alive()
    obs.event_queue.join()


def test_polling_transient_error_timeout(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    watch_dir = tmp_path / "watched"
    watch_dir.mkdir()
    obs = BaseObserver(_IdleEmitter)
    watch = ObservedWatch(str(watch_dir), recursive=True, emit_existing=True, ordered_startup=True)
    fail_polls = threading.Event()
    real_stat = os.stat

    def transient_stat(path: str) -> os.stat_result:
        if fail_polls.is_set():
            raise OSError(errno.EIO, "Transient I/O error", path)
        return real_stat(path)

    class _RetryingPollEmitter(PollingEmitter):
        def on_thread_start(self) -> None:
            super().on_thread_start()
            fail_polls.set()

    emitter = _RetryingPollEmitter(obs.event_queue, watch, timeout=0.01, stat=transient_stat)
    with caplog.at_level(logging.WARNING, logger="watchdog.observers.polling"):
        emitter.start()
        try:
            status = emitter.wait_for_snapshot(snapshot_timeout=2.0, retry_timeout=0.05)
            assert status is SnapshotStatus.TIMEOUT
            assert "Transient I/O error" in caplog.text
            assert emitter.should_keep_running()
        finally:
            emitter.stop()
            emitter.join(timeout=2.0)


@pytest.mark.parametrize(
    "case",
    ["delete_recreate", "dir_move", "dir_file_delete", "overwrite", "missing", "zero_ino"],
)
def test_ledger_post_sync(tmp_path: Path, case: str) -> None:
    """Post-sync ledger handles delete/recreate, dir moves, Windows dir deletes, and fail-open checks."""
    watch_dir = tmp_path / "watched"
    if case in ("dir_move", "dir_file_delete"):
        src_dir = watch_dir / "src_dir"
        nested = src_dir / "sub"
        nested.mkdir(parents=True)
        target_path = nested / "f.txt"
    else:
        watch_dir.mkdir()
        src_dir = watch_dir
        target_path = watch_dir / "a.txt"
    target_path.write_text("v1")
    dst_dir = watch_dir / "dst_dir"

    handler = _RecordingHandler()
    obs = BaseObserver(_IdleEmitter)
    obs.start()
    try:
        watch = obs.schedule(handler, str(watch_dir), recursive=True, emit_existing=True, ordered_startup=True)
        _wait_for_startup_sync(obs)

        if case == "delete_recreate":
            obs.event_queue.put((FileDeletedEvent(str(target_path), is_synthetic=False), watch))
            obs.event_queue.join()
            target_path.write_text("v2")
            obs.event_queue.put((FileCreatedEvent(str(target_path), is_synthetic=False), watch))
            obs.event_queue.join()
            assert ("created", "a.txt", False) in handler.events
        elif case == "dir_move":
            os.rename(src_dir, dst_dir)
            obs.event_queue.put((DirMovedEvent(str(src_dir), str(dst_dir), is_synthetic=False), watch))
            obs.event_queue.put((FileCreatedEvent(str(dst_dir / "sub" / "f.txt"), is_synthetic=False), watch))
            obs.event_queue.join()
            assert ("moved", "src_dir", False) in handler.events
            assert ("created", "f.txt", False) not in handler.events
        elif case == "dir_file_delete":
            # Windows can emit FileDeletedEvent for a deleted directory while children still stat on disk.
            obs.event_queue.put((FileDeletedEvent(str(src_dir), is_synthetic=False), watch))
            obs.event_queue.join()
            obs.event_queue.put((FileCreatedEvent(str(target_path), is_synthetic=False), watch))
            obs.event_queue.join()
            assert ("deleted", "src_dir", False) in handler.events
            assert ("created", "f.txt", False) in handler.events
            assert not obs._sync_state[watch].children_by_parent  # noqa: SLF001
        elif case == "overwrite":
            tmp_replacement = tmp_path / "replacement.tmp"
            tmp_replacement.write_text("v2")
            os.replace(tmp_replacement, target_path)
            obs.event_queue.put((FileCreatedEvent(str(target_path), is_synthetic=False), watch))
            obs.event_queue.join()
            assert ("created", "a.txt", False) in handler.events
        elif case == "missing":
            target_path.unlink()
            obs.event_queue.put((FileCreatedEvent(str(target_path), is_synthetic=False), watch))
            obs.event_queue.join()
            assert ("created", "a.txt", False) in handler.events
        elif case == "zero_ino":
            real_stat, real_lstat = os.stat, os.lstat

            def zero_ino(fn: Any) -> Any:
                def wrapper(path: Any, *args: Any, **kwargs: Any) -> Any:
                    if os.fspath(path) == str(target_path):
                        return SimpleNamespace(st_dev=1, st_ino=0)
                    return fn(path, *args, **kwargs)

                return wrapper

            with (
                patch.object(os, "stat", side_effect=zero_ino(real_stat)),
                patch.object(os, "lstat", side_effect=zero_ino(real_lstat)),
            ):
                obs.event_queue.put((FileCreatedEvent(str(target_path), is_synthetic=False), watch))
                obs.event_queue.join()
            assert ("created", "a.txt", False) in handler.events
    finally:
        obs.stop()
        obs.join(timeout=3.0)


def test_ledger_index_pruning(tmp_path: Path) -> None:
    """Removing leaf then parent via remove_startup_entity must leave no empty parent sets."""
    root = os.path.normcase(os.path.abspath(str(tmp_path)))
    sub_dir = os.path.join(root, "dir")
    child_file = os.path.join(sub_dir, "file.txt")
    state = _WatchSyncState(root_norm=root)
    state.record_startup_entity(sub_dir, ((1, 10), 100))
    state.record_startup_entity(child_file, ((1, 11), 101))
    assert state.children_by_parent == {root: {sub_dir}, sub_dir: {child_file}}

    state.remove_startup_entity(child_file)
    assert state.children_by_parent == {root: {sub_dir}}

    state.remove_startup_entity(sub_dir)
    assert not state.startup_entities
    assert not state.children_by_parent


def test_stream_directory_events_zero_inode(tmp_path: Path) -> None:
    """stream_directory_events must recursively traverse nested dirs and break symlink cycles when st_ino == 0."""
    sub2 = tmp_path / "sub1" / "sub2"
    sub2.mkdir(parents=True)
    leaf = sub2 / "leaf.txt"
    leaf.write_text("data")
    loop = tmp_path / "sub1" / "loop"
    with contextlib.suppress(OSError):
        loop.symlink_to(tmp_path / "sub1", target_is_directory=True)

    real_stat = os.stat

    def zero_ino_stat(p: str) -> os.stat_result:
        st = real_stat(p)
        return os.stat_result(
            (
                st.st_mode,
                0,
                st.st_dev,
                st.st_nlink,
                st.st_uid,
                st.st_gid,
                st.st_size,
                st.st_atime,
                st.st_mtime,
                st.st_ctime,
            )
        )

    from watchdog.utils.sync import stream_directory_events

    events = list(stream_directory_events(str(tmp_path), recursive=True, stat_func=zero_ino_stat, follow_symlink=True))
    paths = {os.fsdecode(ev.src_path) for ev in events}
    assert str(sub2) in paths
    assert str(leaf) in paths


@pytest.mark.parametrize("use_bytes", [False, True])
@pytest.mark.parametrize("cycle", [False, True])
def test_partially_scanned_dir_move(tmp_path: Path, *, use_bytes: bool, cycle: bool) -> None:
    """Interleaved directory move during partial scan reconciles cleanly under ordered startup."""
    dir_a = tmp_path / "A"
    sub_a = dir_a / "sub"
    sub_a.mkdir(parents=True)
    file_a = sub_a / "file.txt"
    file_a.write_text("hello")
    dir_b = tmp_path / "B"
    dir_b.mkdir()
    dest_a = dir_b / "A"

    def to_p(p: Path | str) -> bytes | str:
        s = str(p)
        return os.fsencode(s) if use_bytes else s

    handler = _RecordingHandler()
    obs = BaseObserver(_IdleEmitter, timeout=0.01)
    watch = obs.schedule(handler, to_p(tmp_path), recursive=True, emit_existing=True, ordered_startup=True)
    token = obs._sync_state[watch].session_token  # noqa: SLF001

    def put_s(ev: FileSystemEvent) -> None:
        ev.session_token = token
        obs.event_queue.put((ev, watch))

    # Scanner visits A/ only
    put_s(DirCreatedEvent(to_p(dir_a), is_synthetic=True))
    _drain_events(obs)

    # Live move A -> B/A
    os.rename(dir_a, dest_a)
    obs.event_queue.put((DirMovedEvent(to_p(dir_a), to_p(dest_a), is_synthetic=False), watch))
    if cycle:
        # Move back: B/A -> A
        os.rename(dest_a, dir_a)
        obs.event_queue.put((DirMovedEvent(to_p(dest_a), to_p(dir_a), is_synthetic=False), watch))
    _drain_events(obs)

    # Scanner discovers children
    active_a = dir_a if cycle else dest_a
    dest_sub = active_a / "sub"
    dest_file = dest_sub / "file.txt"
    put_s(DirCreatedEvent(to_p(active_a), is_synthetic=True))
    put_s(DirCreatedEvent(to_p(dest_sub), is_synthetic=True))
    put_s(FileCreatedEvent(to_p(dest_file), is_synthetic=True))
    obs.event_queue.put((SynchronizationComplete(watch, session_token=token), watch))
    _drain_events(obs)

    if use_bytes:
        for ev in handler.raw_events:
            assert isinstance(ev.src_path, bytes)
            assert b"b'" not in ev.src_path

    def _rel(p: Any) -> str:
        return os.path.normcase(os.path.relpath(os.fsdecode(p), str(tmp_path)).replace(os.sep, "/"))

    rel_events = [
        (
            ev.event_type,
            _rel(ev.src_path) + (f" -> {_rel(ev.dest_path)}" if getattr(ev, "dest_path", None) else ""),
            ev.is_synthetic,
        )
        for ev in handler.raw_events
    ]
    if cycle:
        created = {p for t, p, syn in rel_events if t == "created" and syn}
        assert {os.path.normcase(x) for x in ("A", "A/sub", "A/sub/file.txt")} <= created
    else:
        assert rel_events == [
            ("created", os.path.normcase("A"), True),
            ("created", os.path.normcase("A/sub"), True),
            ("created", os.path.normcase("A/sub/file.txt"), True),
            ("moved", f"{os.path.normcase('A')} -> {os.path.normcase('B/A')}", False),
        ]


def test_dir_delete_recreate(tmp_path: Path) -> None:
    """Directory recreation invalidates dead incarnations while allowing live and moved descendants."""
    dir_a, dir_b = tmp_path / "A", tmp_path / "B"
    dir_a.mkdir()
    dir_b.mkdir()
    dest_a = dir_b / "A"
    f_same = dir_a / "same.txt"
    f_same.write_text("old")

    handler = _RecordingHandler()
    obs = BaseObserver(_IdleEmitter, timeout=0.01)
    watch = obs.schedule(handler, str(tmp_path), recursive=True, emit_existing=True, ordered_startup=True)
    token = obs._sync_state[watch].session_token  # noqa: SLF001

    def put_event(ev: FileSystemEvent, *, session: bool = False) -> None:
        if session:
            ev.session_token = token
        obs.event_queue.put((ev, watch))

    # Incarnation 1: scan discovery -> live delete -> recreate -> move to B/A
    put_event(FileCreatedEvent(str(f_same), is_synthetic=True), session=True)
    f_same.unlink()
    dir_a.rmdir()
    put_event(DirDeletedEvent(str(dir_a)))

    dir_a.mkdir()
    (dir_a / "same.txt").write_text("new")
    put_event(DirCreatedEvent(str(dir_a)))

    os.rename(dir_a, dest_a)
    put_event(DirMovedEvent(str(dir_a), str(dest_a)))
    (dest_a / "moved.txt").write_text("moved")

    for f in (dest_a / "same.txt", dest_a / "moved.txt"):
        put_event(FileCreatedEvent(str(f), is_synthetic=True), session=True)

    put_event(SynchronizationComplete(watch, session_token=token))
    _drain_events(obs)

    created = {
        os.path.relpath(os.fsdecode(ev.src_path), str(tmp_path)).replace(os.sep, "/")
        for ev in handler.raw_events
        if ev.event_type == "created"
    }
    assert any("same.txt" in p for p in created)
    assert any("moved.txt" in p for p in created)


def test_chained_dir_moves(tmp_path: Path) -> None:
    """Deleting parent directory preserves historical aliases for moved-out subtrees."""
    x, a, b, sub_b, c = [str(tmp_path / d) for d in ("X", "A", "B", "B/sub", "C")]
    st = _WatchSyncState(ordered_startup=True, root_norm=str(tmp_path))
    st.record_dir_move(x, a, is_staged=True)
    st.record_dir_move(a, b, is_staged=True)
    st.record_dir_move(sub_b, c, is_staged=True)
    st.record_dir_delete(b)

    for src_dir in (x, a):
        live, handler_p, suppress = st.resolve_startup_path(os.path.join(src_dir, "sub", "f.txt"))
        assert live == os.path.join(c, "f.txt")
        assert handler_p == os.path.join(x, "sub", "f.txt")
        assert suppress is False


def test_symlink_watch_identity(tmp_path: Path) -> None:
    """Distinct symlinks to same directory retain independent watch identity and separate emitters."""
    real, a, b = tmp_path / "real", tmp_path / "a", tmp_path / "b"
    real.mkdir()
    try:
        os.symlink(real, a)
        os.symlink(real, b)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not supported in this environment")

    obs = BaseObserver(_IdleEmitter, timeout=0.01)
    w_a = obs.schedule(_RecordingHandler(), str(a), recursive=True, follow_symlink=True)
    w_b = obs.schedule(_RecordingHandler(), str(b), recursive=True, follow_symlink=True)

    assert w_a != w_b
    assert obs._emitter_for_watch[w_a] is not obs._emitter_for_watch[w_b]  # noqa: SLF001
    assert w_a == ObservedWatch(str(a) + os.sep + ".", recursive=True, follow_symlink=True)


@pytest.mark.parametrize("post_sync", [False, True])
def test_replacement_parent_cleanup(tmp_path: Path, *, post_sync: bool) -> None:
    """Replacement cleanly unlinks parent index during active sync and post-sync."""
    root = str(tmp_path)
    state = _WatchSyncState(ordered_startup=True, root_norm=root)
    file_p = str(tmp_path / "item.txt")

    state.record_startup_entity(file_p, ((10, 100), 1_000))
    state.mark_seen(file_p)
    assert file_p in state.children_by_parent.get(root, set())

    obs = object.__new__(BaseObserver)
    ev = FileCreatedEvent(file_p)
    if post_sync:
        state.finish(clear_ledger=False)
        assert obs._reconcile_post_sync_event(ev, state, file_p, current_file_id=(10, 200), current_btime=2_000)
    else:
        obs._should_dispatch_live_event(
            ev, state, file_p, current_file_id=(10, 200), current_btime=2_000, follow_symlink=False
        )

    assert file_p not in state.children_by_parent.get(root, set())
