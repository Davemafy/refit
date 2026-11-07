"""Host-side launcher. Hidden fixtures are sent only to one-shot evaluators."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess

from scripts.container_agent import command, run
from scripts.docker_cleanup import remove_and_verify

HERE = Path(__file__).resolve().parent


def evaluate_patch(image, request):
    cases = json.loads((HERE / 'evaluation_cases.json').read_text())
    partition = request['partition']
    patch = request['patch']
    if partition not in cases or not isinstance(patch, str) or len(patch.encode()) > 512 * 1024:
        raise ValueError('Invalid mini-SWE evaluation request')
    methods = cases[partition]
    name = 'refit-mini-eval-' + secrets.token_hex(10)
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin')}
    invocation = command(image, name)
    invocation[-1:] = ['--entrypoint', 'python', image, '-I', '-S',
                      '/opt/refit/integrations/mini_swe/evaluate.py']
    try:
        process = subprocess.run(invocation, input=json.dumps({'patch': patch, 'methods': methods}) + '\n',
                                 text=True, capture_output=True, timeout=50, env=env)
        process.check_returncode()
        result = json.loads(process.stdout)
        expected = [
            (repr(method) if isinstance(method, str) else repr(method[0].encode('ascii')),
             (method if isinstance(method, str) else method[0]).upper())
            for method in methods
        ]
        checks = result['checks']
        if result['returncode'] or [(c['input'], c['expected']) for c in checks] != expected:
            raise ValueError('Mini-SWE evaluator did not complete the expected checks')
        passed = all(c['actual'] == answer for c, (_, answer) in zip(checks, expected))
    finally:
        cleanup = remove_and_verify('docker', name, env=env)
        if not cleanup['verified']:
            raise RuntimeError('Mini-SWE evaluator cleanup was not verified')
    return {'partition': partition, 'patch_sha256': hashlib.sha256(patch.encode()).hexdigest(),
            'passed': passed, 'checks': checks, 'cleanup': cleanup}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--reference-patch', type=Path)
    args = parser.parse_args()
    if args.execute and args.reference_patch:
        parser.error('A live run must never receive the reference patch')
    config = json.loads((HERE / 'manifest.json').read_text())
    if args.reference_patch:
        # The reference solution stays host-side, even during preflight.
        image = subprocess.check_output(['docker', 'image', 'inspect', '--format={{.Id}}', args.image],
                                        text=True).strip()
        args.image = image
        reference = args.reference_patch.read_text()
        receipts = [evaluate_patch(image, {'partition': partition, 'patch': diff})
                    for partition in ('training', 'validation', 'holdout') for diff in ('', reference)]
        if [receipt['passed'] for receipt in receipts] != [False, True] * 3:
            raise RuntimeError('Upstream issue did not reproduce with the expected red/green checks')
    else:
        receipts = []
    run(config, args.image, args.output, args.execute, patch_evaluator=evaluate_patch)
    if receipts:
        (args.output / 'reference-evaluations.json').write_text(json.dumps(receipts, indent=2))


if __name__ == '__main__':
    main()
