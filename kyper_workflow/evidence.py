"""Bounded direct-content checks; trusted local runner, not tamper protection."""
import os
import copy
import ast
import json
from pathlib import Path
from uuid import uuid4

HOST_CHECKS = ('text', 'model', 'browser', 'native')
ATTESTED_STATUS = ('pass', 'fail', 'blocked')


def _file_bytes(root, name):
    root = Path(root).resolve(strict=True)
    path = root / name
    if Path(name).is_absolute() or '..' in Path(name).parts or path.is_symlink():
        raise ValueError('Unsafe file')
    path = path.resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('Not an in-scope file')
    with path.open("rb") as handle:
        return handle.read(1_000_001)


def snapshot(root, names):
    result = {}
    total = 0
    for name in names:
        content = _file_bytes(root, name)
        total += len(content)
        if len(content) > 1_000_000 or total > 20_000_000 or len(result) >= 2000:
            raise ValueError('Snapshot limits exceeded')
        result[name] = content
    return result


def unchanged(root, names, original):
    """Byte comparison with early exit; identical result to a full snapshot."""
    if set(names) != set(original): return False
    total = 0
    for name in names:
        content = _file_bytes(root, name)
        total += len(content)
        if len(content) > 1_000_000 or total > 20_000_000 or len(original) > 2000:
            raise ValueError('Snapshot limits exceeded')
        if original[name] != content: return False
    return True


def _repository_names(root):
    root = Path(root)
    names = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in ('.git','__pycache__','.pytest_cache')]
        if any((Path(directory)/d).is_symlink() for d in dirs): raise ValueError('Symlink directory')
        names.extend(str((Path(directory)/f).relative_to(root)) for f in files)
        if len(names) > 2000: raise ValueError('Repository file limit exceeded')
    return names


def repository_snapshot(root):
    return snapshot(root, _repository_names(root))


class Review:
    def __init__(self, root, artifacts, revision):
        self.root, self.artifacts, self.revision = root, list(artifacts), revision
        if not self.artifacts or len(set(self.artifacts)) != len(self.artifacts):
            raise ValueError('Unique nonempty artifacts required')
        self.original = snapshot(root, self.artifacts)
        self.id = uuid4().hex
        self.results = {}
        self.invalidated = False
        self.project_snapshot = None
        self.project_requested = False

    def current(self):
        if self.invalidated: return False
        try:
            same = unchanged(self.root, self.artifacts, self.original)
            if same and self.project_snapshot is not None:
                same = unchanged(self.root, _repository_names(self.root), self.project_snapshot)
        except (ValueError, OSError):
            same = False
        if not same: self.invalidated = True
        return same

    def attest(self, check, *, status, detail, revision):
        """Record a trusted host result for checks this process cannot run.

        Only trusted application code may call this; the boolean is never taken
        from model or tool arguments. Results die with the content revision and
        are re-checked for freshness by gate().
        """
        if check not in HOST_CHECKS:
            raise ValueError('Only host checks can be attested')
        if status not in ATTESTED_STATUS or not isinstance(detail, dict) or not detail:
            raise ValueError('Attested status and evidence required')
        if type(revision) is not int or revision != self.revision:
            raise ValueError('Attestation applies to a different revision')
        if not self.current():
            raise ValueError('Content changed before attestation')
        self.results[check] = dict(detail, status=status)
        return copy.deepcopy(self.results[check])

    def syntax(self):
        if self.project_requested: return {"status":"blocked", "reason":"Cannot downgrade project test requirement"}
        if not self.current():
            return {'status': 'blocked', 'reason': 'Content changed'}
        errors = []
        unsupported = []
        for name, data in self.original.items():
            try:
                if name.endswith('.py'): ast.parse(data, filename=name)
                elif name.endswith('.json'): json.loads(data)
                else: unsupported.append({'file': name, 'reason': 'No syntax check for this file type'})
            except (SyntaxError, ValueError, UnicodeError) as exc:
                errors.append({'file': name, 'reason': type(exc).__name__})
        status = 'fail' if errors else 'blocked' if unsupported else 'pass'
        self.results['code'] = {'status': status, 'errors': errors, 'unsupported': unsupported,
                                'scope': 'Syntax only; no project execution'}
        if not self.current(): self.results['code']['status'] = 'blocked'
        return copy.deepcopy(self.results['code'])

    def gate(self, required):
        required = list(required)
        fresh = self.current()
        statuses = {name: self.results.get(name, {}).get('status', 'not_run') for name in required}
        missing = [name for name in required if statuses[name] == 'not_run' and name in HOST_CHECKS]
        return {'review_id': self.id, 'revision': self.revision, 'code_mode':'project_tests' if self.project_requested else 'syntax', 'content_current': fresh,
                'checks': statuses, 'allow_completion': bool(required) and fresh and all(s == 'pass' for s in statuses.values()),
                'unattested_checks': missing,
                'limit': 'Direct comparison at observed times; not tamper protection or semantic verification'}

    def project_tests(self, *, explicitly_trusted=False):
        """Trusted unittest runner; never use on unknown project code."""
        if explicitly_trusted is not True:
            return {'status': 'blocked', 'reason': 'Explicit trusted-code permission required'}
        import sys
        import os
        import subprocess
        from .process import run_project
        from .windows_process import OutputLimitExceeded
        if not self.current(): return {'status':'blocked', 'reason':'Content changed'}
        self.project_requested = True
        before = repository_snapshot(self.root)
        self.project_snapshot = before
        try:
            result = run_project([sys.executable, '-I', str(Path(__file__).with_name('test_runner.py'))], Path(self.root))
            try:
                counts = json.loads(result.stdout.strip().splitlines()[-1])
                valid = all(type(counts.get(k)) is int for k in ('discovered','ran','failures','errors','skipped')) and counts['discovered'] == counts['ran'] and counts['ran'] > counts['skipped'] >= 0 and counts['failures'] == counts['errors'] == 0
            except (ValueError, IndexError, AttributeError): counts, valid = {}, False
            self.results['code'] = {'status':'pass' if result.returncode == 0 and valid else 'fail',
                                    'test_counts':counts, 'exit_code':result.returncode,
                                    'stdout':result.stdout, 'stderr':result.stderr,
                                    'scope':'Trusted unittest execution, not sandbox or security certification'}
        except (OSError, subprocess.TimeoutExpired, OutputLimitExceeded) as exc:
            self.results['code'] = {'status':'blocked','reason':type(exc).__name__}
        if not self.current() or repository_snapshot(self.root) != before:self.results['code']['status']='blocked'
        return copy.deepcopy(self.results['code'])
