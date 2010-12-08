# -*- coding: utf-8 -*-

from __future__ import with_statement

from nose.tools import assert_raises


def assert_readonly_public_attributes(o):
    for prop in list_attributes(o, True):
        assert_raises(AttributeError, setattr, o, prop, None)


def list_attributes(o, only_public=True):
    if only_public:
        def isattribute(o, attribute):
            return not (attribute.startswith('_') or callable(getattr(o, attribute)))
    else:
        def isattribute(o, attribute):
            return not callable(getattr(o, attribute))
    return [attribute for attribute in dir(o) if isattribute(o, attribute)]
