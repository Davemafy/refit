"""Protected offline reproduction of upstream Requests issue #2316."""
import collections
import collections.abc
import json
from pathlib import Path
import sys

TRAINING = [['GET']]


def check(root, methods):
    for name in ('Mapping', 'MutableMapping', 'Callable', 'Iterable'):
        if not hasattr(collections, name):
            setattr(collections, name, getattr(collections.abc, name))
    root = Path(root).resolve()
    sys.path.insert(0, str(root))
    import requests
    assert Path(requests.__file__).resolve().is_relative_to(root)

    class Capture(requests.Session):
        def send(self, prepared, **kwargs):
            return prepared.method

    results = []
    for value in methods:
        method = value if isinstance(value, str) else value[0].encode("ascii")
        expected = (method.decode('ascii') if isinstance(method, bytes) else method).upper()
        actual = Capture().request(method, 'http://example.invalid/')
        results.append({'input': repr(method), 'expected': expected, 'actual': actual,
                        'passed': actual == expected})
    return results


def main():
    assert sys.argv[2:] == ['training']
    results = check(sys.argv[1], TRAINING)
    passed = all(r['passed'] for r in results)
    print(json.dumps({'completed': True, 'passed': passed, 'checks': results}))
    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()
