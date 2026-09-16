"""
Code execution engine for running student Python code.

Security model: student code NEVER runs inside the Django process. Two
isolation backends share one runner (apps/code_runner/sandbox_runner.py):

1. ``subprocess`` (default): a fresh ``python -I`` subprocess with a hard
   wall-clock timeout, strict builtins whitelist and AST private-attribute
   blocking. Isolated from the server process, but same OS user.
2. ``docker`` (opt-in via CODE_EXECUTION_BACKEND=docker): the same runner
   inside a container with network disabled, memory/CPU/PID limits and a
   read-only rootfs — full OS-level isolation. Requires the sandbox image
   (see docker/sandbox/Dockerfile).

Both modes enforce timeouts; optional RestrictedPython strengthens the
runner automatically when the package is installed.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from django.conf import settings

#: Hard cap on submitted code length (sanity guard for the JSON pipe).
MAX_CODE_LENGTH = 100_000
#: Sentinel marking the result JSON on the sandbox runner stdout.
_SENTINEL = '__SANDBOX_RESULT__'

_RUNNER_PATH = Path(__file__).with_name('sandbox_runner.py')


def _docker_available() -> bool:
    return shutil.which('docker') is not None


def _sandbox_image() -> str:
    return getattr(settings, 'SANDBOX_DOCKER_IMAGE', 'teaching-space-sandbox')


class CodeExecutor:
    """
    Sandboxed Python code executor (subprocess/Docker isolation + timeouts).
    """

    def __init__(self, timeout=5, max_output_length=10000, backend=None):
        """
        Args:
            timeout: Maximum execution time in seconds (default: 5)
            max_output_length: Maximum output length in characters (default: 10000)
            backend: 'subprocess' (default), 'docker', or None → settings
        """
        self.timeout = timeout
        self.max_output_length = max_output_length
        if backend is None:
            backend = getattr(settings, 'CODE_EXECUTION_BACKEND', 'subprocess')
        self.backend = backend

    # -- transport ----------------------------------------------------------

    def _spawn_subprocess(self, request: dict, timeout: float):
        kwargs = {}
        if os.name == 'nt':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        try:
            completed = subprocess.run(
                [sys.executable, '-I', str(_RUNNER_PATH)],
                input=json.dumps(request, ensure_ascii=False),
                capture_output=True, text=True, timeout=timeout, **kwargs,
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError(f'Execution timed out after {timeout} seconds')
        return completed

    def _spawn_docker(self, request: dict, timeout: float):
        """Run the same runner inside the sandbox container."""
        if not _docker_available():
            return None  # caller reports a clear "docker not available" error
        image = _sandbox_image()
        cmd = [
            'docker', 'run', '--rm', '-i',
            '--network', 'none',          # no network access
            '--memory', '128m',           # memory cap
            '--cpus', '0.5',              # half a CPU
            '--pids-limit', '64',
            '--read-only',                # read-only rootfs…
            '--tmpfs', '/tmp:rw,size=16m',  # …with a tiny writable /tmp
            '--cap-drop', 'ALL',
            image,                        # ENTRYPOINT = python /sandbox/runner.py
        ]
        try:
            completed = subprocess.run(
                cmd,
                input=json.dumps(request, ensure_ascii=False),
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise TimeoutError(f'Execution timed out after {timeout} seconds')
        return completed

    def _run_sandboxed(self, request: dict, timeout: float):
        """Dispatch to the configured backend; return the parsed result."""
        completed = None
        backend_error = None
        if self.backend == 'docker':
            completed = self._spawn_docker(request, timeout)
            if completed is None:
                backend_error = (
                    'Docker backend configured but the docker CLI was not found. '
                    'Install Docker or set CODE_EXECUTION_BACKEND=subprocess.'
                )
            elif completed.returncode != 0:
                # e.g. image not built — fall through with a clear message
                stderr = (completed.stderr or '').strip().splitlines()
                backend_error = (
                    'Docker execution failed (is the sandbox image built? '
                    'see docker/sandbox/Dockerfile): '
                    + (stderr[-1] if stderr else f'exit code {completed.returncode}')
                )
                completed = None
        else:
            completed = self._spawn_subprocess(request, timeout)

        if completed is None:
            return {
                'status': 'error',
                'error': backend_error or 'unknown sandbox failure',
                'output': '',
            }

        stdout = completed.stdout or ''
        if _SENTINEL in stdout:
            try:
                return json.loads(stdout.split(_SENTINEL, 1)[1])
            except json.JSONDecodeError:
                pass
        stderr = (completed.stderr or '').strip().splitlines()
        return {
            'status': 'error',
            'error': '执行环境异常: ' + (stderr[-1] if stderr else 'unknown sandbox failure'),
            'output': '',
        }

    # -- public API ---------------------------------------------------------

    def execute_code(self, code, mode='restricted', stdin_input=''):
        """
        Execute Python code and return results.

        Args:
            mode: 'restricted' (configured backend) or 'docker' (force docker)

        Returns:
            dict: {'output', 'status' ('success'|'error'), 'execution_time', 'error'}
        """
        if len(code) > MAX_CODE_LENGTH:
            return {
                'output': '',
                'status': 'error',
                'execution_time': 0,
                'error': f'Code too long (max {MAX_CODE_LENGTH} characters)'
            }

        backend = self.backend
        if mode == 'docker':
            backend = 'docker'
        elif mode not in ('restricted',):
            return {
                'output': '',
                'status': 'error',
                'execution_time': 0,
                'error': f'Invalid execution mode: {mode}'
            }

        saved_backend = self.backend
        self.backend = backend
        start_time = time.time()
        try:
            result = self._run_sandboxed({
                'mode': 'code',
                'code': code,
                'stdin_input': stdin_input,
                'max_output_length': self.max_output_length,
            }, timeout=self.timeout)
        except TimeoutError as e:
            result = {'status': 'error', 'error': str(e), 'output': ''}
        finally:
            self.backend = saved_backend

        result['execution_time'] = int((time.time() - start_time) * 1000)
        return result

    def execute_with_tests(self, code, test_cases, timeout=10):
        """
        Execute code and run test cases against it.

        Supports two test formats:
        1. stdin/stdout based: {'input': '...', 'expected_output': '...'}
        2. Function-based: {'input': 'func(args)', 'expected': result}

        Returns dict with keys: status, total_tests, passed_tests,
        failed_tests, test_results, execution_time, error, output, message.

        Raises TimeoutError if execution exceeds the time limit.
        """
        tests = []
        if isinstance(test_cases, dict):
            tests = test_cases.get('tests', [])
        elif isinstance(test_cases, list):
            tests = test_cases

        start_time = time.time()
        result = self._run_sandboxed({
            'mode': 'tests',
            'code': code,
            'test_cases': tests,
            'max_output_length': self.max_output_length,
        }, timeout=timeout)

        result.setdefault('total_tests', len(tests))
        result.setdefault('passed_tests', 0)
        result.setdefault('failed_tests', 0)
        result.setdefault('test_results', [])
        result['execution_time'] = int((time.time() - start_time) * 1000)
        result['message'] = f'Passed {result["passed_tests"]}/{result["total_tests"]} tests'
        return result


# Convenience function for simple execution
def execute_python_code(code, timeout=5):
    """
    Simple wrapper function to execute Python code.
    """
    executor = CodeExecutor(timeout=timeout)
    return executor.execute_code(code, mode='restricted')
