"""Run a reviewed external adapter in gVisor; broker bounded Vultr calls only.

No imported repository or adapter is ever imported into this host process.
"""
import argparse
import hashlib
import gzip
import json
import os
from pathlib import Path
import secrets
import selectors
import subprocess
import tempfile
import time

from .docker_cleanup import remove_and_verify
from .refit_vultr_probe import VultrInference, load_key
from .release_identity import capture_revision

MAX_FRAME = 32 * 1024 * 1024


def command(image, name):
    return ['docker', 'run', '-i', '--name', name, '--runtime', 'runsc',
            '--network', 'none', '--read-only', '--user', '65534:65534',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
            '--pids-limit', '128', '--memory', '4g', '--memory-swap', '4g',
            '--cpus', '2', '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=128m',
            '--log-driver', 'none', image]


def frame(proc, buffer, deadline):
    with selectors.DefaultSelector() as selector:
        selector.register(proc.stdout, selectors.EVENT_READ)
        while b'\n' not in buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise TimeoutError('external worker response deadline exceeded')
            try:
                chunk = os.read(proc.stdout.fileno(), min(65536, MAX_FRAME + 1 - len(buffer)))
            except BlockingIOError:
                continue
            if not chunk:
                raise RuntimeError('external worker exited before a complete result')
            buffer.extend(chunk)
            if len(buffer) > MAX_FRAME:
                raise ValueError('external worker frame exceeds budget')
    line, _, rest = buffer.partition(b'\n')
    buffer[:] = rest
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError('worker frame must be an object')
    return value


def send(proc, value, deadline):
    data = json.dumps(value, separators=(',', ':'), ensure_ascii=False).encode() + b'\n'
    if len(data) > MAX_FRAME:
        raise ValueError('host response exceeds frame budget')
    sent = 0
    with selectors.DefaultSelector() as selector:
        selector.register(proc.stdin, selectors.EVENT_WRITE)
        while sent < len(data):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise TimeoutError('worker input deadline exceeded')
            try:
                sent += os.write(proc.stdin.fileno(), data[sent:])
            except BlockingIOError:
                continue


def validate_config(config):
    if config.get('format') != 'refit.container-agent.v1':
        raise ValueError('unsupported external agent manifest')
    if type(config.get('max_requests')) is not int or not 1 <= config['max_requests'] <= 400:
        raise ValueError('request budget must be 1..400')
    if config['source'] == config['target']:
        raise ValueError('model replacement must change model')
    if not isinstance(config.get('revision'), str) or len(config['revision']) != 40:
        raise ValueError('manifest requires a pinned repository revision')


def validate_completion(value, models):
    if value.get('model') not in models:
        raise ValueError('worker requested an unapproved model')
    messages = value.get('messages')
    if not isinstance(messages, list) or not 1 <= len(messages) <= 500:
        raise ValueError('invalid completion messages')
    if len(json.dumps(value).encode()) > 2 * 1024 * 1024:
        raise ValueError('completion request exceeds budget')
    tools = value.get('tools')
    if tools is not None and (not isinstance(tools, list) or len(tools) > 128):
        raise ValueError('invalid completion tool schemas')


def validate_result(result, description, config):
    if result['status'] not in ('verified_adaptation', 'compatible_on_sample'):
        raise ValueError('migration did not pass shared engine gates')
    if result['export']['model'] != config['target'] or result['export']['revision'] != config['revision']:
        raise ValueError('export target identity mismatch')
    check = result['original_runner_verification']
    expected_names = {row['case_name'] for row in description['metadata']['splits']['holdout']}
    if (check.get('passed') is not True or not check.get('uses_exported_configuration') or
            {c['case'] for c in check['cases']} != expected_names or
            len(check['cases']) != len(expected_names) or not all(c['passed'] for c in check['cases'])):
        raise ValueError('export lacks complete independent native-runner verification')
    expected = {row['case_name']: row for rows in description['metadata']['splits'].values() for row in rows}
    cases = [c for phase in result['report']['evaluations'].values() for c in phase['cases']]
    cases.extend(check['cases'])
    for case in cases:
        row = expected[case['case']]
        if (case['initial_db_hash'] != row['initial_db_hash'] or
                (case['passed'] and case['final_db_hash'] != row['expected_db_hash'])):
            raise ValueError('native state fingerprint mismatch')


def run(config, image, output, execute=False, recorded=None):
    validate_config(config)
    if execute and recorded is not None:
        raise ValueError('Recorded transport recovery cannot make new inference calls')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    root = Path(__file__).resolve().parents[1]
    helper = (root / config['application_helper']).resolve()
    if not helper.is_relative_to(root / 'integrations') or helper.suffix != '.py':
        raise ValueError('Application helper must be reviewed integration source')
    helper_source = helper.read_text()
    client = VultrInference(load_key(Path('/etc/refit/inference.env')),
                            max_requests=config['max_requests']) if execute else None
    prior = None
    if recorded is not None:
        prior = json.loads(gzip.decompress(recorded.read_bytes()))
        if prior['config'] != config or any(c['status'] != 'completed' for c in prior['completions']):
            raise ValueError('Recorded run does not match this manifest')
    docker_env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin')}
    image_info = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image],
                                                    text=True, env=docker_env))[0]
    name = 'refit-external-' + secrets.token_hex(10)
    record = {'format': 'refit.external-agent-run.v1', 'config': config,
              'engine_revision': capture_revision(Path(__file__).resolve().parents[1]),
              'image_id': image_info['Id'], 'container_name': name,
              'execute': execute, 'completions': [], 'events': [], 'native_cases': [],
              'mode': 'recorded_transport_recovery' if prior else ('live' if execute else 'inspect'),
              'recorded_source_sha256': hashlib.sha256(recorded.read_bytes()).hexdigest() if prior else None}
    proc = None
    result = None
    buffer = bytearray()
    deadline = time.monotonic() + 1800

    def save():
        temp = output / '.run.json.tmp'
        temp.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        temp.replace(output / 'run.json')

    try:
        with (output / 'worker.log').open('wb') as log:
            proc = subprocess.Popen(command(image_info['Id'], name), stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=log, bufsize=0,
                                    env=docker_env)
            os.set_blocking(proc.stdin.fileno(), False)
            os.set_blocking(proc.stdout.fileno(), False)
            send(proc, {**config, 'inspect_only': not (execute or prior)}, min(deadline, time.monotonic() + 15))
            while result is None:
                value = frame(proc, buffer, min(deadline, time.monotonic() + 120))
                kind = value.get('type')
                if kind == 'completion':
                    if client is None and prior is None:
                        raise ValueError('inspection must not request inference')
                    validate_completion(value, {config['source'], config['target'], config['user_model']})
                    receipt = {'sequence': len(record['completions']) + 1, 'model': value['model'],
                               'request_sha256': hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest(),
                               'status': 'requested'}
                    record['completions'].append(receipt)
                    record['last_request'] = value
                    save()
                    if prior is not None:
                        index = len(record['completions']) - 1
                        if index >= len(prior['completions']) or receipt['request_sha256'] != prior['completions'][index]['request_sha256']:
                            raise ValueError('Recorded provider request differs; no inference fallback')
                        receipt['status'] = 'replayed'
                        receipt['response'] = prior['completions'][index]['response']
                        send(proc, {'type': 'completion_result', 'message': receipt['response']},
                             min(deadline, time.monotonic() + 15))
                        save()
                        continue
                    try:
                        response = client.complete(value['model'], value['messages'], value.get('tools'), max_tokens=2500)
                        receipt['status'] = 'completed'
                        receipt['response'] = response
                        send(proc, {'type': 'completion_result', 'message': response},
                             min(deadline, time.monotonic() + 15))
                    except Exception as error:
                        receipt['status'] = 'failed'
                        receipt['error_type'] = type(error).__name__
                        send(proc, {'type': 'completion_result', 'error': type(error).__name__},
                             min(deadline, time.monotonic() + 15))
                        # One failed provider call ends the run. No billable retries.
                        raise
                    save()
                elif kind == 'description':
                    record['description'] = value
                    if value['metadata']['upstream_revision'] != config['revision']:
                        raise ValueError('upstream checkout identity mismatch')
                    save()
                elif kind == 'progress':
                    record['events'].append(value)
                    save()
                    print(json.dumps(value), flush=True)
                elif kind == 'case_result':
                    record['native_cases'].append(value['case'])
                    save()
                elif kind == 'result':
                    result = value
                else:
                    raise ValueError('unknown external worker frame')
            proc.wait(timeout=15)
            if proc.returncode != 0:
                raise RuntimeError('external worker failed')
    except Exception as error:
        record['error_type'] = type(error).__name__
        record['error_message'] = str(error)[:250]
    finally:
        if proc is not None:
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=10)
            proc.stdin.close()
            proc.stdout.close()
            record['docker_cli_exit_code'] = proc.returncode
        try:
            info = json.loads(subprocess.check_output(['docker', 'inspect', name], text=True,
                                                     env=docker_env, timeout=10))[0]
            record['container_state'] = info['State']
            record['actual_runtime'] = info['HostConfig']['Runtime']
        except (subprocess.SubprocessError, OSError, ValueError, KeyError):
            record['container_state'] = None
        cleanup = remove_and_verify('docker', name, env={'PATH': os.environ.get('PATH', '/usr/bin:/bin')})
        record['cleanup'] = cleanup
        record['model_requests'] = client.requests if client else 0
        record['result'] = result
        record['logical_requests'] = len(record['completions'])
        verified = bool((execute or prior) and result and result.get('verified') is True and
                        result.get('model_requests') == record['logical_requests'] and
                        record.get('actual_runtime') == 'runsc' and
                        cleanup['verified'] and not record.get('error_type'))
        if verified:
            try:
                validate_result(result, record['description'], config)
            except (KeyError, TypeError, ValueError) as error:
                verified = False
                record['error_type'] = type(error).__name__
                record['error_message'] = str(error)[:250]
        record['verified'] = verified
        if not verified and result:
            result['export'] = None
        save()
        if verified:
            (output / 'agent-config.json').write_text(json.dumps(result['export'], indent=2))
            # Plain source to copy into the developer checkout, never imported here.
            (output / 'apply_config.py').write_text(helper_source)
    print(json.dumps({'verified': verified, 'status': result.get('status') if result else 'execution_error',
                      'model_requests': record['model_requests'], 'cleanup_verified': cleanup['verified'],
                      'output': str(output)}), flush=True)
    if (execute or prior) and not verified:
        raise RuntimeError('migration not verified; evidence retained, export withheld')
    if not cleanup['verified'] or record.get('error_type'):
        raise RuntimeError('external execution failed; evidence retained')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--recorded', type=Path, help='Exact-request replay of saved real responses; never bills')
    args = parser.parse_args()
    previous = os.umask(0o077)
    try:
        run(json.loads(args.manifest.read_text()), args.image, args.output, args.execute, args.recorded)
    finally:
        os.umask(previous)


if __name__ == '__main__':
    main()
