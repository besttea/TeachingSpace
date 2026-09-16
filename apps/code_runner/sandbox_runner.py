"""
Sandbox runner — executes student code in an isolated Python process.

This file is the SINGLE source of truth for sandboxed execution and runs in
two contexts:

1. Subprocess mode: ``python -I sandbox_runner.py`` (spawned by CodeExecutor)
2. Docker mode: copied into the sandbox image (docker/sandbox/Dockerfile)

Protocol: the parent writes a JSON request to stdin, the runner executes it
and writes ``__SANDBOX_RESULT__<json>`` to stdout. Student stdout/stderr are
captured inside the JSON, never written to the process stdout.

Stdlib only — the Docker image does not carry site-packages.
"""

import ast
import io
import json
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout

SENTINEL = '__SANDBOX_RESULT__'
ALLOWED_IMPORTS = {
    'math', 'random', 'json', 're', 'collections', 'itertools',
    'functools', 'heapq', 'statistics', 'string', 'datetime', 'decimal',
    'fractions', 'copy', 'bisect', 'enum', 'typing', 'calendar',
}

_orig_import = __import__


def _safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split('.')[0]
    if root not in ALLOWED_IMPORTS:
        raise ImportError("import of %r is not allowed in this sandbox" % name)
    return _orig_import(name, globals, locals, fromlist, level)


SAFE_BUILTINS = {
    'print': print, 'input': input,
    'len': len, 'range': range, 'iter': iter, 'next': next, 'reversed': reversed,
    'enumerate': enumerate, 'zip': zip, 'map': map, 'filter': filter,
    'str': str, 'int': int, 'float': float, 'bool': bool, 'complex': complex,
    'list': list, 'dict': dict, 'tuple': tuple, 'set': set, 'frozenset': frozenset,
    'abs': abs, 'min': min, 'max': max, 'sum': sum, 'round': round, 'pow': pow,
    'divmod': divmod, 'sorted': sorted, 'all': all, 'any': any,
    'chr': chr, 'ord': ord, 'repr': repr, 'format': format,
    'isinstance': isinstance, 'issubclass': issubclass,
    '__build_class__': __build_class__,
    'Exception': Exception, 'ValueError': ValueError, 'TypeError': TypeError,
    'KeyError': KeyError, 'IndexError': IndexError, 'StopIteration': StopIteration,
    '__import__': _safe_import,
    '__name__': '__main__',
}

# Optional RestrictedPython hardening (used when the package is installed).
try:
    from RestrictedPython import compile_restricted
    from RestrictedPython.Guards import guarded_getattr, guarded_getitem, guarded_getiter
    HAVE_RESTRICTED = True
except ImportError:
    HAVE_RESTRICTED = False


def _check_no_private_attrs(tree):
    """Reject attribute access to names starting with '_'.

    Blocks the classic ``().__class__.__mro__[1].__subclasses__()`` gadget
    chains without RestrictedPython. Student code rarely needs private
    attributes; the error message explains the rule.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith('_'):
            raise SyntaxError(
                "access to private attribute %r is not allowed in this sandbox" % node.attr)


def _compile(source):
    if HAVE_RESTRICTED:
        try:
            code, errors, _warnings, _used = compile_restricted(
                source, filename='<student-code>',
                policy={'allowed_imports': sorted(ALLOWED_IMPORTS)},
            )
        except TypeError:  # older RestrictedPython signatures
            code, errors, _warnings, _used = compile_restricted(
                source, filename='<student-code>')
        if errors:
            raise SyntaxError('; '.join(errors))
        return code
    tree = ast.parse(source, '<student-code>')
    _check_no_private_attrs(tree)
    return compile(tree, '<student-code>', 'exec')


def _execute_source(source, stdin_lines=None):
    """Execute source with captured stdout/stderr. Returns (ns, out, err)."""
    out, err = io.StringIO(), io.StringIO()
    ns = {'__builtins__': dict(SAFE_BUILTINS)}
    if HAVE_RESTRICTED:
        ns['_getattr_'] = guarded_getattr
        ns['_getitem_'] = guarded_getitem
        ns['_getiter_'] = guarded_getiter
        ns['_write_'] = lambda x: x
    if stdin_lines is not None:
        iterator = iter(stdin_lines)

        def mock_input(prompt=''):
            if prompt:
                out.write(str(prompt))
            try:
                return next(iterator)
            except StopIteration:
                raise EOFError('EOF when reading a line')

        ns['__builtins__']['input'] = mock_input

    code_obj = _compile(source)
    with redirect_stdout(out), redirect_stderr(err):
        exec(code_obj, ns)
    return ns, out.getvalue(), err.getvalue()


def _error_text(exc):
    """Exception message + last traceback line, without server file paths."""
    tb = traceback.format_exc().strip().splitlines()
    relevant = [tb[-1]] if tb else []
    return '%s: %s\n%s' % (type(exc).__name__, exc, '\n'.join(relevant))


def _run_simple(req):
    result = {'output': '', 'status': 'success', 'error': None}
    stdin_input = req.get('stdin_input', '')
    try:
        lines = stdin_input.splitlines() if stdin_input else None
        _ns, out, err = _execute_source(req['code'], stdin_lines=lines)
        result['output'] = out + ('\n' + err if err else '')
        if err:
            result['status'] = 'error'
            result['error'] = err.strip()
    except Exception as e:
        result['status'] = 'error'
        result['error'] = _error_text(e)
    return result


def _run_tests(req):
    tests = req['test_cases'] or []
    code = req['code']
    result = {
        'status': 'error', 'total_tests': len(tests),
        'passed_tests': 0, 'failed_tests': 0, 'test_results': [],
        'error': None, 'output': '', 'message': '',
    }
    if not tests:
        result['error'] = 'No test cases provided'
        return result

    first = tests[0]
    is_function_test = 'expected_output' not in first and 'expected' in first

    if is_function_test:
        try:
            ns, out, err = _execute_source(code)
            for test in tests:
                test_result = {
                    'input': test.get('input'), 'expected': test.get('expected'),
                    'actual': None, 'passed': False, 'error': None,
                    'description': test.get('description', ''),
                    'is_hidden': test.get('is_hidden', False),
                }
                try:
                    actual = eval(test.get('input'), ns)
                    test_result['actual'] = actual
                    if actual == test.get('expected'):
                        test_result['passed'] = True
                        result['passed_tests'] += 1
                    else:
                        result['failed_tests'] += 1
                except Exception as e:
                    test_result['error'] = str(e)
                    result['failed_tests'] += 1
                result['test_results'].append(test_result)
            result['output'] = out + ('\n' + err if err else '')
        except Exception as e:
            result['error'] = _error_text(e)
    else:
        for i, test in enumerate(tests):
            input_data = test.get('input', '')
            expected_output = str(test.get('expected_output', '')).strip()
            case = {
                'case_index': i, 'input': input_data,
                'expected': expected_output, 'actual': '', 'passed': False,
                'error': None, 'is_hidden': test.get('is_hidden', False),
                'description': test.get('description', ''),
            }
            try:
                lines = input_data.splitlines() if input_data else None
                _ns, out, err = _execute_source(code, stdin_lines=lines)
                case['actual'] = out.strip()
                if err.strip():
                    case['passed'] = False
                    case['error'] = err.strip()
                    result['failed_tests'] += 1
                elif case['actual'] == expected_output:
                    case['passed'] = True
                    result['passed_tests'] += 1
                else:
                    result['failed_tests'] += 1
                result['output'] += out
            except Exception as e:
                case['error'] = _error_text(e)
                result['failed_tests'] += 1
            result['test_results'].append(case)

    if result['error'] is None and result['failed_tests'] == 0 and result['passed_tests'] == result['total_tests']:
        result['status'] = 'passed'
    elif result['passed_tests'] > 0:
        result['status'] = 'failed'
    return result


def main():
    req = json.loads(sys.stdin.read())
    mode = req.get('mode', 'tests')
    max_output = int(req.get('max_output_length', 10000))
    if mode == 'code':
        result = _run_simple(req)
    else:
        result = _run_tests(req)
    for key in ('output',):
        if len(result.get(key) or '') > max_output:
            result[key] = result[key][:max_output] + '\n... (output truncated)'
    result['execution_time'] = 0
    sys.stdout.write(SENTINEL + json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
