# coding: utf-8

import pytest

# Skip if import PyYAML failed. PyYAML missing possible because
# watchdog installed without watchmedo. See Installation section
# in README.rst
yaml = pytest.importorskip('yaml')  # noqa

import os  # noqa

from watchdog import watchmedo  # noqa
from yaml.constructor import ConstructorError  # noqa
from yaml.scanner import ScannerError  # noqa


def test_load_config_valid(tmpdir):
    """Verifies the load of a valid yaml file"""

    yaml_file = os.path.join(tmpdir, 'config_file.yaml')
    with open(yaml_file, 'w') as f:
        f.write('one: value\ntwo:\n- value1\n- value2\n')

    config = watchmedo.load_config(yaml_file)
    assert isinstance(config, dict)
    assert 'one' in config
    assert 'two' in config
    assert isinstance(config['two'], list)
    assert config['one'] == 'value'
    assert config['two'] == ['value1', 'value2']


def test_load_config_invalid(tmpdir):
    """Verifies if safe load avoid the execution
    of untrusted code inside yaml files"""

    critical_dir = os.path.join(tmpdir, 'critical')
    yaml_file = os.path.join(tmpdir, 'tricks_file.yaml')
    with open(yaml_file, 'w') as f:
        content = (
            'one: value\n'
            'run: !!python/object/apply:os.system ["mkdir {}"]\n'
        ).format(critical_dir)
        f.write(content)

    # PyYAML get_single_data() raises different exceptions for Linux and Windows
    with pytest.raises((ConstructorError, ScannerError)):
        watchmedo.load_config(yaml_file)

    assert not os.path.exists(critical_dir)


def make_dummy_script(tmpdir, n=10):
    script = os.path.join(tmpdir, 'auto-test-%d.py' % n)
    with open(script, 'w') as f:
        f.write('import time\nfor i in range(%d):\n\tprint("+++++ %%d" %% i, flush=True)\n\ttime.sleep(1)\n' % n)
    return script


def test_kill_auto_restart(tmpdir, capfd):
    from watchdog.tricks import AutoRestartTrick
    import sys
    import time
    script = make_dummy_script(tmpdir)
    a = AutoRestartTrick([sys.executable, script])
    a.start()
    time.sleep(5)
    a.stop()
    cap = capfd.readouterr()
    assert '+++++ 0' in cap.out
    assert '+++++ 9' not in cap.out     # we killed the subprocess before the end
    # in windows we seem to lose the subprocess stderr
    # assert 'KeyboardInterrupt' in cap.err
