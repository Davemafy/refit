"""Protected offline reproduction of upstream Requests issue #2316."""
import collections
import collections.abc
import json
from pathlib import Path
import sys

METHODS = {'training': [b'GET'], 'validation': [b'POST', b'PATCH'],
           'holdout': [b'head', b'OPTIONS', 'GET', 'post']}


def main():
    for name in ('Mapping', 'MutableMapping', 'Callable', 'Iterable'):
        if not hasattr(collections, name):
            setattr(collections, name, getattr(collections.abc, name))
    root = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(root))
    import requests
    assert Path(requests.__file__).resolve().is_relative_to(root)

    class Capture(requests.Session):
        def send(self, prepared, **kwargs):
            return prepared.method

    results = []
    for method in METHODS[sys.argv[2]]:
        expected = (method.decode('ascii') if isinstance(method, bytes) else method).upper()
        actual = Capture().request(method, 'http://example.invalid/')
        results.append({'input': repr(method), 'expected': expected, 'actual': actual,
                        'passed': actual == expected})
    passed = all(r['passed'] for r in results)
    print(json.dumps({'completed': True, 'passed': passed, 'checks': results}))
    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()
