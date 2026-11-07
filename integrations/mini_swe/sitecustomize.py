"""Python 3.11 compatibility for Requests 2.4.3's vendored dependencies.

No task source or HTTP method behavior is changed.
"""
import collections
import collections.abc
for _name in ('Mapping', 'MutableMapping', 'Callable', 'Iterable'):
    if not hasattr(collections, _name):
        setattr(collections, _name, getattr(collections.abc, _name))
