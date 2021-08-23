.. :changelog:

Changelog
---------

2.1.5
~~~~~

2021-08-23 • `full history <https://github.com/gorakhargosh/watchdog/compare/v2.1.4...v2.1.5>`__

- Fix regression introduced in 2.1.4 (reverted "Allow overriding or adding custom event handlers to event dispatch map. (`#814 <https://github.com/gorakhargosh/watchdog/pull/814>`_)"). (`#830 <https://github.com/gorakhargosh/watchdog/pull/830>`_)
- Convert regexes of type ``str`` to ``list``. (`831 <https://github.com/gorakhargosh/watchdog/pull/831>`_)
- Thanks to our beloved contributors: @unique1o1, @BoboTiG

2.1.4
~~~~~

2021-08-19 • `full history <https://github.com/gorakhargosh/watchdog/compare/v2.1.3...v2.1.4>`__

- [watchmedo] Fix usage of ``os.setsid()`` and ``os.killpg()`` Unix-only functions. (`#809 <https://github.com/gorakhargosh/watchdog/pull/809>`_)
- [mac] Fix missing ``FileModifiedEvent`` on permission or ownership changes of a file. (`#815 <https://github.com/gorakhargosh/watchdog/pull/815>`_)
- [mac] Convert absolute watch path in ``FSEeventsEmitter`` with ``os.path.realpath()``. (`#822 <https://github.com/gorakhargosh/watchdog/pull/822>`_)
- Fix a possible ``AttributeError`` in ``SkipRepeatsQueue._put()``. (`#818 <https://github.com/gorakhargosh/watchdog/pull/818>`_)
- Allow overriding or adding custom event handlers to event dispatch map. (`#814 <https://github.com/gorakhargosh/watchdog/pull/814>`_)
- Fix tests on big endian platforms. (`#828 <https://github.com/gorakhargosh/watchdog/pull/828>`_)
- Thanks to our beloved contributors: @replabrobin, @BoboTiG, @SamSchott, @AndreiB97, @NiklasRosenstein, @ikokollari, @mgorny

2.1.3
~~~~~

2021-06-26 • `full history <https://github.com/gorakhargosh/watchdog/compare/v2.1.2...v2.1.3>`__

- Publish macOS ``arm64`` and ``universal2`` wheels. (`#740 <https://github.com/gorakhargosh/watchdog/pull/740>`_)
- Thanks to our beloved contributors: @kainjow, @BoboTiG

2.1.2
~~~~~

2021-05-19 • `full history <https://github.com/gorakhargosh/watchdog/compare/v2.1.1...v2.1.2>`__

- [mac] Fix relative path handling for non-recursive watch. (`#797 <https://github.com/gorakhargosh/watchdog/pull/797>`_)
- [windows] On PyPy, events happening right after ``start()`` were missed. Add a workaround for that. (`#796 <https://github.com/gorakhargosh/watchdog/pull/796>`_)
- Thanks to our beloved contributors: @oprypin, @CCP-Aporia, @BoboTiG

2.1.1
~~~~~

2021-05-10 • `full history <https://github.com/gorakhargosh/watchdog/compare/v2.1.0...v2.1.1>`__

- [mac] Fix callback exceptions when the watcher is deleted but still receiving events (`#786 <https://github.com/gorakhargosh/watchdog/pull/786>`_)
- Thanks to our beloved contributors: @rom1win, @BoboTiG, @CCP-Aporia


2.1.0
~~~~~

2021-05-04 • `full history <https://github.com/gorakhargosh/watchdog/compare/v2.0.3...v2.1.0>`__

- [inotify] Simplify ``libc`` loading (`#776 <https://github.com/gorakhargosh/watchdog/pull/776>`_)
- [mac] Add support for non-recursive watches in ``FSEventsEmitter`` (`#779 <https://github.com/gorakhargosh/watchdog/pull/779>`_)
- [watchmedo] Add support for ``--debug-force-*`` arguments to ``tricks`` (`#781 <https://github.com/gorakhargosh/watchdog/pull/781>`_)
- Thanks to our beloved contributors: @CCP-Aporia, @aodj, @UnitedMarsupials, @BoboTiG


2.0.3
~~~~~

2021-04-22 • `full history <https://github.com/gorakhargosh/watchdog/compare/v2.0.2...v2.0.3>`__

- [mac] Use ``logger.debug()`` instead of ``logger.info()`` (`#774 <https://github.com/gorakhargosh/watchdog/pull/774>`_)
- Updated documentation links (`#777 <https://github.com/gorakhargosh/watchdog/pull/777>`_)
- Thanks to our beloved contributors: @globau, @imba-tjd, @BoboTiG


2.0.2
~~~~~

2021-02-22 • `full history <https://github.com/gorakhargosh/watchdog/compare/v2.0.1...v2.0.2>`__

- [mac] Add missing exception objects (`#766 <https://github.com/gorakhargosh/watchdog/pull/766>`_)
- Thanks to our beloved contributors: @CCP-Aporia, @BoboTiG


2.0.1
~~~~~

2021-02-17 • `full history <https://github.com/gorakhargosh/watchdog/compare/v2.0.0...v2.0.1>`__

- [mac] Fix a segmentation fault when dealing with unicode paths (`#763 <https://github.com/gorakhargosh/watchdog/pull/763>`_)
- Moved the CI from Travis-CI to GitHub Actions (`#764 <https://github.com/gorakhargosh/watchdog/pull/764>`_)
- Thanks to our beloved contributors: @SamSchott, @BoboTiG


2.0.0
~~~~~

2021-02-11 • `full history <https://github.com/gorakhargosh/watchdog/compare/v1.0.2...v2.0.0>`__

- Avoid deprecated ``PyEval_InitThreads`` on Python 3.7+ (`#746 <https://github.com/gorakhargosh/watchdog/pull/746>`_)
- [inotify] Add support for ``IN_CLOSE_WRITE`` events. A ``FileCloseEvent`` event will be fired. Note that ``IN_CLOSE_NOWRITE`` events are not handled to prevent much noise. (`#184 <https://github.com/gorakhargosh/watchdog/pull/184>`_, `#245 <https://github.com/gorakhargosh/watchdog/pull/245>`_, `#280 <https://github.com/gorakhargosh/watchdog/pull/280>`_, `#313 <https://github.com/gorakhargosh/watchdog/pull/313>`_, `#690 <https://github.com/gorakhargosh/watchdog/pull/690>`_)
- [inotify] Allow to stop the emitter multiple times (`#760 <https://github.com/gorakhargosh/watchdog/pull/760>`_)
- [mac] Support coalesced filesystem events (`#734 <https://github.com/gorakhargosh/watchdog/pull/734>`_)
- [mac] Drop support for macOS 10.12 and earlier (`#750 <https://github.com/gorakhargosh/watchdog/pull/750>`_)
- [mac] Fix an issue when renaming an item changes only the casing (`#750 <https://github.com/gorakhargosh/watchdog/pull/750>`_)
- Thanks to our beloved contributors: @bstaletic, @lukassup, @ysard, @SamSchott, @CCP-Aporia, @BoboTiG


1.0.2
~~~~~

2020-12-18 • `full history <https://github.com/gorakhargosh/watchdog/compare/v1.0.1...v1.0.2>`__

- Wheels are published for GNU/Linux, macOS and Windows (`#739 <https://github.com/gorakhargosh/watchdog/pull/739>`_)
- [mac] Fix missing ``event_id`` attribute in ``fsevents`` (`#721 <https://github.com/gorakhargosh/watchdog/pull/721>`_)
- [mac] Return byte paths if a byte path was given in ``fsevents`` (`#726` <https://github.com/gorakhargosh/watchdog/pull/726>`_)
- [mac] Add compatibility with old macOS versions (`#733` <https://github.com/gorakhargosh/watchdog/pull/733>`_)
- Uniformize event for deletion of watched dir (`#727 <https://github.com/gorakhargosh/watchdog/pull/727>`_)
- Thanks to our beloved contributors: @SamSchott, @CCP-Aporia, @di, @BoboTiG


1.0.1
~~~~~

2020-12-10 • Fix version with good metadatas.


1.0.0
~~~~~

2020-12-10 • `full history <https://github.com/gorakhargosh/watchdog/compare/v0.10.4...v1.0.0>`__

- Versioning is now following the `semver <https://semver.org/>`_
- Drop support for Python 2.7, 3.4 and 3.5
- [mac] Regression fixes for native ``fsevents`` (`#717 <https://github.com/gorakhargosh/watchdog/pull/717>`_)
- [windows] ``winapi.BUFFER_SIZE`` now defaults to ``64000`` (instead of ``2048``) (`#700 <https://github.com/gorakhargosh/watchdog/pull/700>`_)
- [windows] Introduced ``winapi.PATH_BUFFER_SIZE`` (defaults to ``2048``) to keep the old behavior with path-realted functions (`#700 <https://github.com/gorakhargosh/watchdog/pull/700>`_)
- Use ``pathlib`` from the standard library, instead of pathtools (`#556 <https://github.com/gorakhargosh/watchdog/pull/556>`_)
- Allow file paths on Unix that don't follow the file system encoding (`#703 <https://github.com/gorakhargosh/watchdog/pull/703>`_)
- Removed the long-time deprecated ``events.LoggingFileSystemEventHandler`` class, use ``LoggingEventHandler`` instead
- Thanks to our beloved contributors: @SamSchott, @bstaletic, @BoboTiG, @CCP-Aporia


0.10.4
~~~~~~

2020-11-21 • `full history <https://github.com/gorakhargosh/watchdog/compare/v0.10.3...v0.10.4>`__

- Add ``logger`` parameter for the ``LoggingEventHandler`` (`#676 <https://github.com/gorakhargosh/watchdog/pull/676>`_)
- Replace mutable default arguments with ``if None`` implementation (`#677 <https://github.com/gorakhargosh/watchdog/pull/677>`_)
- Expand tests to Python 2.7 and 3.5-3.10 for GNU/Linux, macOS and Windows
- [mac] Performance improvements for the ``fsevents`` module (`#680 <https://github.com/gorakhargosh/watchdog/pull/680>`_)
- [mac] Prevent compilation of ``watchdog_fsevents.c`` on non-macOS machines (`#687 <https://github.com/gorakhargosh/watchdog/pull/687>`_)
- [watchmedo] Handle shutdown events from ``SIGTERM`` and ``SIGINT`` more reliably (`#693 <https://github.com/gorakhargosh/watchdog/pull/693>`_)
- Thanks to our beloved contributors: @Sraw, @CCP-Aporia, @BoboTiG, @maybe-sybr


0.10.3
~~~~~~

2020-06-25 • `full history <https://github.com/gorakhargosh/watchdog/compare/v0.10.2...v0.10.3>`__

- Ensure ``ObservedWatch.path`` is a string (`#651 <https://github.com/gorakhargosh/watchdog/pull/651>`_)
- [inotify] Allow to monitor single file (`#655 <https://github.com/gorakhargosh/watchdog/pull/655>`__)
- [inotify] Prevent raising an exception when a file in a monitored folder has no permissions (`#669 <https://github.com/gorakhargosh/watchdog/pull/669>`__, `#670 <https://github.com/gorakhargosh/watchdog/pull/670>`__)
- Thanks to our beloved contributors: @brant-ruan, @rec, @andfoy, @BoboTiG


0.10.2
~~~~~~

2020-02-08 • `full history <https://github.com/gorakhargosh/watchdog/compare/v0.10.1...v0.10.2>`__

- Fixed the ``build_ext`` command on macOS Catalina (`#628 <https://github.com/gorakhargosh/watchdog/pull/628>`__)
- Fixed the installation of macOS requirements on non-macOS OSes (`#635 <https://github.com/gorakhargosh/watchdog/pull/635>`__)
- Refactored ``dispatch()`` method of ``FileSystemEventHandler``,
  ``PatternMatchingEventHandler`` and ``RegexMatchingEventHandler``
- [bsd] Improved tests support on non Windows/Linux platforms (`#633 <https://github.com/gorakhargosh/watchdog/pull/633>`__, `#639 <https://github.com/gorakhargosh/watchdog/pull/639>`__)
- [bsd] Added FreeBSD CI support (`#532 <https://github.com/gorakhargosh/watchdog/pull/532>`__)
- [bsd] Restored full support (`#638 <https://github.com/gorakhargosh/watchdog/pull/638>`__, `#641 <https://github.com/gorakhargosh/watchdog/pull/641>`__)
- Thanks to our beloved contributors: @BoboTiG, @evilham, @danilobellini


0.10.1
~~~~~~

2020-01-30 • `full history <https://github.com/gorakhargosh/watchdog/compare/v0.10.0...v0.10.1>`__

- Fixed Python 2.7 to 3.6 installation when the OS locale is set to POSIX (`#615 <https://github.com/gorakhargosh/watchdog/pull/615>`__)
- Fixed the ``build_ext`` command on macOS  (`#618 <https://github.com/gorakhargosh/watchdog/pull/618>`__, `#620 <https://github.com/gorakhargosh/watchdog/pull/620>`_)
- Moved requirements to ``setup.cfg``  (`#617 <https://github.com/gorakhargosh/watchdog/pull/617>`__)
- [mac] Removed old C code for Python 2.5 in the `fsevents` C implementation
- [snapshot] Added ``EmptyDirectorySnapshot`` (`#613 <https://github.com/gorakhargosh/watchdog/pull/613>`__)
- Thanks to our beloved contributors: @Ajordat, @tehkirill, @BoboTiG


0.10.0
~~~~~~

2020-01-26 • `full history <https://github.com/gorakhargosh/watchdog/compare/v0.9.0...v0.10.0>`__

**Breaking Changes**

- Dropped support for Python 2.6, 3.2 and 3.3
- Emitters that failed to start are now removed
- [snapshot] Removed the deprecated ``walker_callback`` argument,
  use ``stat`` instead
- [watchmedo] The utility is no more installed by default but via the extra
  ``watchdog[watchmedo]``

**Other Changes**

- Fixed several Python 3 warnings
- Identify synthesized events with ``is_synthetic`` attribute (`#369 <https://github.com/gorakhargosh/watchdog/pull/369>`__)
- Use ``os.scandir()`` to improve memory usage (`#503 <https://github.com/gorakhargosh/watchdog/pull/503>`__)
- [bsd] Fixed flavors of FreeBSD detection (`#529 <https://github.com/gorakhargosh/watchdog/pull/529>`__)
- [bsd] Skip unprocessable socket files (`#509 <https://github.com/gorakhargosh/watchdog/issue/509>`__)
- [inotify] Fixed events containing non-ASCII characters (`#516 <https://github.com/gorakhargosh/watchdog/issues/516>`__)
- [inotify] Fixed the way ``OSError`` are re-raised (`#377 <https://github.com/gorakhargosh/watchdog/issues/377>`__)
- [inotify] Fixed wrong source path after renaming a top level folder (`#515 <https://github.com/gorakhargosh/watchdog/pull/515>`__)
- [inotify] Removed  delay from non-move events (`#477 <https://github.com/gorakhargosh/watchdog/pull/477>`__)
- [mac] Fixed a bug when calling ``FSEventsEmitter.stop()`` twice (`#466 <https://github.com/gorakhargosh/watchdog/pull/466>`__)
- [mac] Support for unscheduling deleted watch (`#541 <https://github.com/gorakhargosh/watchdog/issue/541>`__)
- [mac] Fixed missing field initializers and unused parameters in
  ``watchdog_fsevents.c``
- [snapshot] Don't walk directories without read permissions (`#408 <https://github.com/gorakhargosh/watchdog/pull/408>`__)
- [snapshot] Fixed a race condition crash when a directory is swapped for a file (`#513 <https://github.com/gorakhargosh/watchdog/pull/513>`__)
- [snasphot] Fixed an ``AttributeError`` about forgotten ``path_for_inode`` attr (`#436 <https://github.com/gorakhargosh/watchdog/issues/436>`__)
- [snasphot] Added the ``ignore_device=False`` parameter to the ctor (`597 <https://github.com/gorakhargosh/watchdog/pull/597>`__)
- [watchmedo] Fixed the path separator used (`#478 <https://github.com/gorakhargosh/watchdog/pull/478>`__)
- [watchmedo] Fixed the use of ``yaml.load()`` for ``yaml.safe_load()`` (`#453 <https://github.com/gorakhargosh/watchdog/issues/453>`__)
- [watchmedo] Handle all available signals (`#549 <https://github.com/gorakhargosh/watchdog/issue/549>`__)
- [watchmedo] Added the ``--debug-force-polling`` argument (`#404 <https://github.com/gorakhargosh/watchdog/pull/404>`__)
- [windows] Fixed issues when the observed directory is deleted (`#570 <https://github.com/gorakhargosh/watchdog/issues/570>`__ and `#601 <https://github.com/gorakhargosh/watchdog/pull/601>`__)
- [windows] ``WindowsApiEmitter`` made easier to subclass (`#344 <https://github.com/gorakhargosh/watchdog/pull/344>`__)
- [windows] Use separate ctypes DLL instances
- [windows] Generate sub created events only if ``recursive=True`` (`#454 <https://github.com/gorakhargosh/watchdog/pull/454>`__)
- Thanks to our beloved contributors: @BoboTiG, @LKleinNux, @rrzaripov,
  @wildmichael, @TauPan, @segevfiner, @petrblahos, @QuantumEnergyE,
  @jeffwidman, @kapsh, @nickoala, @petrblahos, @julianolf, @tonybaloney,
  @mbakiev, @pR0Ps, javaguirre, @skurfer, @exarkun, @joshuaskelly,
  @danilobellini, @Ajordat


0.9.0
~~~~~

2018-08-28 • `full history <https://github.com/gorakhargosh/watchdog/compare/v0.8.3...v0.9.0>`__

- Deleting the observed directory now emits a ``DirDeletedEvent`` event
- [bsd] Improved the platform detection (`#378 <https://github.com/gorakhargosh/watchdog/pull/378>`__)
- [inotify] Fixed a crash when the root directory being watched by was deleted (`#374 <https://github.com/gorakhargosh/watchdog/pull/374>`__)
- [inotify] Handle systems providing uClibc
- [linux] Fixed a possible ``DirDeletedEvent`` duplication when
  deleting a directory
- [mac] Fixed unicode path handling ``fsevents2.py`` (`#298 <https://github.com/gorakhargosh/watchdog/pull/298>`__)
- [watchmedo] Added the ``--debug-force-polling`` argument (`#336 <https://github.com/gorakhargosh/watchdog/pull/336>`__)
- [windows] Fixed the ``FILE_LIST_DIRECTORY`` constant (`#376 <https://github.com/gorakhargosh/watchdog/pull/376>`__)
- Thanks to our beloved contributors: @vulpeszerda, @hpk42, @tamland, @senden9,
  @gorakhargosh, @nolsto, @mafrosis, @DonyorM, @anthrotype, @danilobellini,
  @pierregr, @ShinNoNoir, @adrpar, @gforcada, @pR0Ps, @yegorich, @dhke


0.8.3
~~~~~

2015-02-11 • `full history <https://github.com/gorakhargosh/watchdog/compare/v0.8.2...v0.8.3>`__

- Fixed the use of the root logger (`#274 <https://github.com/gorakhargosh/watchdog/issues/274>`__)
- [inotify] Refactored libc loading and improved error handling in
  ``inotify_c.py``
- [inotify] Fixed a possible unbound local error in ``inotify_c.py``
- Thanks to our beloved contributors: @mmorearty, @tamland, @tony,
  @gorakhargosh


0.8.2
~~~~~

2014-10-29 • `full history <https://github.com/gorakhargosh/watchdog/compare/v0.8.1...v0.8.2>`__

- Event emitters are no longer started on schedule if ``Observer`` is not
  already running
- [mac] Fixed usued arguments to pass clang compilation (`#265 <https://github.com/gorakhargosh/watchdog/pull/265>`__)
- [snapshot] Fixed a possible race condition crash on directory deletion (`#281 <https://github.com/gorakhargosh/watchdog/pull/281>`__)
- [windows] Fixed an error when watching the same folder again (`#270 <https://github.com/gorakhargosh/watchdog/pull/270>`__)
- Thanks to our beloved contributors: @tamland, @apetrone, @Falldog,
  @theospears


0.8.1
~~~~~

2014-07-28 • `full history <https://github.com/gorakhargosh/watchdog/compare/v0.8.0...v0.8.1>`__

- Fixed ``anon_inode`` descriptors leakage  (`#249 <https://github.com/gorakhargosh/watchdog/pull/249>`__)
- [inotify] Fixed thread stop dead lock (`#250 <https://github.com/gorakhargosh/watchdog/issues/250>`__)
- Thanks to our beloved contributors: @Witos, @adiroiban, @tamland


0.8.0
~~~~~

2014-07-02 • `full history <https://github.com/gorakhargosh/watchdog/compare/v0.7.1...v0.8.0>`__

- Fixed ``argh`` deprecation warnings (`#242 <https://github.com/gorakhargosh/watchdog/pull/242>`__)
- [snapshot] Methods returning internal stats info were replaced by
  ``mtime()``, ``inode()`` and ``path()`` methods
- [snapshot] Deprecated the ``walker_callback`` argument
- [watchmedo] Fixed ``auto-restart`` to terminate all children processes (`#225 <https://github.com/gorakhargosh/watchdog/pull/225>`__)
- [watchmedo] Added the ``--no-parallel`` argument (`#227 <https://github.com/gorakhargosh/watchdog/issues/227>`__)
- [windows] Fixed the value of ``INVALID_HANDLE_VALUE`` (`#123 <https://github.com/gorakhargosh/watchdog/issues/123>`__)
- [windows] Fixed octal usages to work with Python 3 as well (`#223 <https://github.com/gorakhargosh/watchdog/issues/223>`__)
- Thanks to our beloved contributors: @tamland, @Ormod, @berdario, @cro,
  @BernieSumption, @pypingou, @gotcha, @tommorris, @frewsxcv
