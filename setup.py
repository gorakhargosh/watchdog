# coding: utf-8
#
# Copyright 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
# Copyright 2012 Google, Inc & contributors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import importlib.util
import sys
import os
import os.path
from platform import machine
from setuptools import setup, find_packages
from setuptools.extension import Extension
from setuptools.command.build_ext import build_ext

SRC_DIR = 'src'
WATCHDOG_PKG_DIR = os.path.join(SRC_DIR, 'watchdog')

# Load the module version
spec = importlib.util.spec_from_file_location(
    'version', os.path.join(WATCHDOG_PKG_DIR, 'version.py'))
version = importlib.util.module_from_spec(spec)
spec.loader.exec_module(version)

# Ignored Apple devices on which compiling watchdog_fsevents.c would fail.
# The FORCE_MACOS_MACHINE envar, when set to 1, will force the compilation.
_apple_devices = ('appletv', 'iphone', 'ipod', 'ipad', 'watch')
is_macos = sys.platform == 'darwin' and not machine().lower().startswith(_apple_devices)

ext_modules = []
if is_macos or os.getenv('FORCE_MACOS_MACHINE', '0') == '1':
    ext_modules = [
        Extension(
            name='_watchdog_fsevents',
            sources=[
                'src/watchdog_fsevents.c',
            ],
            libraries=['m'],
            define_macros=[
                ('WATCHDOG_VERSION_STRING',
                 '"' + version.VERSION_STRING + '"'),
                ('WATCHDOG_VERSION_MAJOR', version.VERSION_MAJOR),
                ('WATCHDOG_VERSION_MINOR', version.VERSION_MINOR),
                ('WATCHDOG_VERSION_BUILD', version.VERSION_BUILD),
            ],
            extra_link_args=[
                '-framework', 'CoreFoundation',
                '-framework', 'CoreServices',
            ],
            extra_compile_args=[
                '-std=c99',
                '-pedantic',
                '-Wall',
                '-Wextra',
                '-fPIC',

                # Issue #620
                '-Wno-nullability-completeness',
                # Issue #628
                '-Wno-nullability-extension',
                '-Wno-newline-eof',

                # required w/Xcode 5.1+ and above because of '-mno-fused-madd'
                '-Wno-error=unused-command-line-argument'
            ]
        ),
    ]

extras_require = {
    'watchmedo': ['PyYAML>=3.10'],
}

with open('README.rst', encoding='utf-8') as f:
    readme = f.read()

with open('changelog.rst', encoding='utf-8') as f:
    changelog = f.read()

setup(name="watchdog",
      version=version.VERSION_STRING,
      description="Filesystem events monitoring",
      long_description=readme + '\n\n' + changelog,
      long_description_content_type="text/x-rst",
      author="Yesudeep Mangalapilly",
      author_email="yesudeep@gmail.com",
      license="Apache License 2.0",
      url="https://github.com/gorakhargosh/watchdog",
      keywords=' '.join([
          'python',
          'filesystem',
          'monitoring',
          'monitor',
          'FSEvents',
          'kqueue',
          'inotify',
          'ReadDirectoryChangesW',
          'polling',
          'DirectorySnapshot',
      ]),
      classifiers=[
          'Development Status :: 3 - Alpha',
          'Environment :: Console',
          'Intended Audience :: Developers',
          'Intended Audience :: System Administrators',
          'License :: OSI Approved :: Apache Software License',
          'Natural Language :: English',
          'Operating System :: POSIX :: Linux',
          'Operating System :: MacOS :: MacOS X',
          'Operating System :: POSIX :: BSD',
          'Operating System :: Microsoft :: Windows :: Windows Vista',
          'Operating System :: Microsoft :: Windows :: Windows 7',
          'Operating System :: Microsoft :: Windows :: Windows 8',
          'Operating System :: Microsoft :: Windows :: Windows 8.1',
          'Operating System :: Microsoft :: Windows :: Windows 10',
          'Operating System :: OS Independent',
          'Programming Language :: Python',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3 :: Only',
          'Programming Language :: Python :: 3.6',
          'Programming Language :: Python :: 3.7',
          'Programming Language :: Python :: 3.8',
          'Programming Language :: Python :: 3.9',
          'Programming Language :: Python :: 3.10',
          'Programming Language :: Python :: Implementation :: PyPy',
          'Programming Language :: C',
          'Topic :: Software Development :: Libraries',
          'Topic :: System :: Monitoring',
          'Topic :: System :: Filesystems',
          'Topic :: Utilities',
      ],
      package_dir={'': SRC_DIR},
      packages=find_packages(SRC_DIR),
      include_package_data=True,
      extras_require=extras_require,
      cmdclass={
          'build_ext': build_ext,
      },
      ext_modules=ext_modules,
      entry_points={'console_scripts': [
          'watchmedo = watchdog.watchmedo:main [watchmedo]',
      ]},
      python_requires='>=3.6',
      zip_safe=False
)
