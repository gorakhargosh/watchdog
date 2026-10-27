"""Monitor a directory by comparing periodic directory snapshots."""

import sys
import time

from watchdog.utils.dirsnapshot import DirectorySnapshot, DirectorySnapshotDiff


path = sys.argv[1]

previous_snapshot = DirectorySnapshot(path, recursive=True)

try:
    while True:
        time.sleep(1)

        current_snapshot = DirectorySnapshot(path, recursive=True)
        diff = DirectorySnapshotDiff(previous_snapshot, current_snapshot)

        for file_path in diff.files_created:
            print(f"Created: {file_path}")

        for file_path in diff.files_deleted:
            print(f"Deleted: {file_path}")

        for file_path in diff.files_modified:
            print(f"Modified: {file_path}")

        for old_path, new_path in diff.files_moved:
            print(f"Moved: {old_path} -> {new_path}")

        previous_snapshot = current_snapshot

finally:
    print("Stopped directory snapshot monitoring.")
