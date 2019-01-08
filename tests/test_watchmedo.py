# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from watchdog import watchmedo
import unittest
import tempfile
import yaml
import os


class TestWatchmedo(unittest.TestCase):
    def setUp(self):
        """Initial setup"""
        tmp_dir = tempfile.gettempdir()
        self.critical_dir = os.path.join(tmp_dir, 'critical')
        self.valid_yaml_file = os.path.join(tmp_dir, 'config_file.yaml')
        self.invalid_yaml_file = os.path.join(tmp_dir, 'tricks_file.yaml')
        if not os.path.exists(self.valid_yaml_file):
            f = open(self.valid_yaml_file, 'w')
            f.write('one: value\ntwo:\n- value1\n- value2\n')
            f.close()
        if not os.path.exists(self.invalid_yaml_file):
            f = open(self.invalid_yaml_file, 'w')
            content = (
                'one: value\n'
                'run: !!python/object/apply:os.system ["mkdir {}"]\n'
            ).format(self.critical_dir)
            f.write(content)
            f.close()

    def test_load_config(self):
        """Verifies the load of a valid yaml file"""
        config = watchmedo.load_config(self.valid_yaml_file)
        self.assertTrue(type(config) is dict)
        self.assertTrue('one' in config)
        self.assertTrue('two' in config)
        self.assertTrue(type(config['two']) is list)
        self.assertEqual(config['one'], 'value')
        self.assertEqual(config['two'], ['value1', 'value2'])

    def test_load_config_invalid(self):
        """Verifies if safe load avoid the execution
        of untrusted code inside yaml files"""
        self.assertRaises(
            yaml.constructor.ConstructorError,
            watchmedo.load_config,
            self.invalid_yaml_file
        )
        self.assertFalse(os.path.exists(self.critical_dir))

    def tearDown(self):
        """Perform a clean up before finishing the tests"""
        if os.path.exists(self.critical_dir):
            if os.path.isdir(self.critical_dir):
                os.rmdir(self.critical_dir)
            else:
                os.remove(self.critical_dir)
