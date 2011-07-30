# -*- coding: utf-8 -*-

from __future__ import with_statement

def list_attributes(o, only_public=True):
    if only_public:
        def isattribute(o, attribute):
            return not (attribute.startswith('_') or callable(getattr(o, attribute)))
    else:
        def isattribute(o, attribute):
            return not callable(getattr(o, attribute))
    return [attribute for attribute in dir(o) if isattribute(o, attribute)]
