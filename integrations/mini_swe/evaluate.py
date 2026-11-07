"""Run an objective check in a disposable container separate from generation."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    request = json.loads(sys.stdin.readline())
    with tempfile.TemporaryDirectory(prefix='mini-evaluation-') as temp:
        root = Path(temp) / 'task'
        shutil.copytree('/opt/task-base', root)
        if request['patch']:
            subprocess.run(['git', '-C', str(root), 'apply', '-'], input=request['patch'],
                           text=True, check=True, capture_output=True, timeout=10)
        # The trusted evaluator owns the transport. Imported task code runs in
        # a subprocess, with its stdout/stderr separated from the result pipe.
        process = subprocess.run(
            [sys.executable, '-I', '-S', __file__, str(root)],
            input=json.dumps(request['methods']), text=True, capture_output=True, timeout=30)
        checks = json.loads(process.stdout) if process.returncode == 0 else []
        print(json.dumps({'checks': checks, 'returncode': process.returncode}), flush=True)


if __name__ == '__main__':
    if len(sys.argv) == 2:
        sys.path.insert(0, str(Path(__file__).parent))
        from verify import check
        print(json.dumps(check(sys.argv[1], json.load(sys.stdin))))
    else:
        main()
