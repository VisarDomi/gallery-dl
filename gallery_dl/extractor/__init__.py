# -*- coding: utf-8 -*-

# Copyright 2015-2025 Mike Fährmann
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation.

import sys
from ..text import re_compile

modules = [
    "hitomi",
    "nozomi",
    "noop",
    "generic",
]


def find(url):
    """Find a suitable extractor for the given URL"""
    for cls in _list_classes():
        if match := cls.pattern.match(url):
            return cls(match)
    return None


def add(cls):
    """Add 'cls' to the list of available extractors"""
    if isinstance(cls.pattern, str):
        cls.pattern = re_compile(cls.pattern)
    _cache.append(cls)
    return cls


def add_module(module):
    """Add all extractors in 'module' to the list of available extractors"""
    if classes := _get_classes(module):
        if isinstance(classes[0].pattern, str):
            for cls in classes:
                cls.pattern = re_compile(cls.pattern)
        _cache.extend(classes)
    return classes


def extractors():
    """Yield all available extractor classes"""
    return sorted(
        _list_classes(),
        key=lambda x: x.__name__
    )


# --------------------------------------------------------------------
# internals


def _list_classes():
    """Yield available extractor classes"""
    yield from _cache

    for module in _module_iter:
        yield from add_module(module)

    globals()["_list_classes"] = lambda : _cache


def _modules_internal():
    globals_ = globals()
    for module_name in modules:
        yield __import__(module_name, globals_, None, None, 1)


def _modules_path(path, files):
    sys.path.insert(0, path)
    try:
        return [
            __import__(name[:-3])
            for name in files
            if name.endswith(".py")
        ]
    finally:
        del sys.path[0]


def _get_classes(module):
    """Return a list of all extractor classes in a module"""
    return [
        cls for cls in module.__dict__.values() if (
            hasattr(cls, "pattern") and cls.__module__ == module.__name__
        )
    ]


_cache = []
_module_iter = _modules_internal()
