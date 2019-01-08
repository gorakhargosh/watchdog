# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from watchdog import watchmedo
import pytest
import yaml
import os


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

    with pytest.raises(yaml.constructor.ConstructorError):
        watchmedo.load_config(yaml_file)

    assert not os.path.exists(critical_dir)
