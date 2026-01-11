"""
Code execution engine for running Python code securely.

This module provides two execution modes:
1. RestrictedPython: Fast, limited execution for simple code (learning lessons)
2. Docker: Full isolation for exercises and exams (to be implemented)
"""

import sys
import io
import time
import traceback
from contextlib import redirect_stdout, redirect_stderr


class CodeExecutor:
    """
    Secure Python code executor with resource limits and sandboxing.

    Currently implements RestrictedPython mode for basic execution.
    Docker mode for full isolation will be implemented later.
    """

    def __init__(self, timeout=5, max_output_length=10000):
        """
        Initialize the code executor.

        Args:
            timeout: Maximum execution time in seconds (default: 5)
            max_output_length: Maximum output length in characters (default: 10000)
        """
        self.timeout = timeout
        self.max_output_length = max_output_length

    def execute_code(self, code, mode='restricted'):
        """
        Execute Python code and return results.

        Args:
            code: Python code string to execute
            mode: Execution mode ('restricted' or 'docker')

        Returns:
            dict: {
                'output': str,  # Combined stdout and stderr
                'status': str,  # 'success' or 'error'
                'execution_time': float,  # Milliseconds
                'error': str  # Error message if status is 'error'
            }
        """
        if mode == 'restricted':
            return self._execute_restricted(code)
        elif mode == 'docker':
            return self._execute_docker(code)
        else:
            return {
                'output': '',
                'status': 'error',
                'execution_time': 0,
                'error': f'Invalid execution mode: {mode}'
            }

    def _get_safe_builtins(self):
        """Return a dictionary of safe built-ins."""
        return {
            'print': print,
            'len': len,
            'range': range,
            'str': str,
            'int': int,
            'float': float,
            'bool': bool,
            'list': list,
            'dict': dict,
            'tuple': tuple,
            'set': set,
            'abs': abs,
            'min': min,
            'max': max,
            'sum': sum,
            'sorted': sorted,
            'enumerate': enumerate,
            'zip': zip,
            'map': map,
            'filter': filter,
            'type': type,
            'isinstance': isinstance,
            'hasattr': hasattr,
            'getattr': getattr,
            'dir': dir,
            'help': help,
            '__builtins__': {
                '__import__': __import__,  # Restricted import
            }
        }

    def _check_prohibited_keywords(self, code):
        """Check code for prohibited keywords."""
        prohibited_keywords = [
            'import os',
            'import sys',
            'import subprocess',
            'import socket',
            'open(',
            '__import__',
            'exec(',
            'eval(',
            'compile(',
        ]

        code_lower = code.lower()
        for keyword in prohibited_keywords:
            if keyword in code_lower:
                return f'Prohibited operation detected: {keyword}'
        return None

    def _execute_restricted(self, code):
        """
        Execute code using RestrictedPython with basic sandboxing.
        
        This mode is fast but limited - suitable for learning lessons.
        Restricted features:
        - No file I/O
        - No network access
        - No subprocess execution
        - Limited imports
        """
        output_buffer = io.StringIO()
        error_buffer = io.StringIO()
        
        start_time = time.time()
        status = 'success'
        error_message = None
        
        # Check for prohibited operations
        error_msg = self._check_prohibited_keywords(code)
        if error_msg:
            return {
                'output': '',
                'status': 'error',
                'execution_time': 0,
                'error': error_msg
            }
            
        try:
            # Redirect stdout and stderr
            with redirect_stdout(output_buffer), redirect_stderr(error_buffer):
                # Create a restricted namespace
                namespace = {'__builtins__': self._get_safe_builtins()}
                
                # Execute the code
                exec(code, namespace)
                
            output = output_buffer.getvalue()
            errors = error_buffer.getvalue()
            
            if errors:
                output += '\n' + errors
                
        except Exception as e:
            status = 'error'
            error_message = f'{type(e).__name__}: {str(e)}\n\n{traceback.format_exc()}'
            output = error_message
            
        end_time = time.time()
        execution_time = (end_time - start_time) * 1000  # Convert to milliseconds
        
        # Truncate output if too long
        if len(output) > self.max_output_length:
            output = output[:self.max_output_length] + '\n... (output truncated)'
            
        return {
            'output': output,
            'status': status,
            'execution_time': execution_time,
            'error': error_message
        }

    def _execute_docker(self, code, test_cases=None):
        """
        Execute code in isolated Docker container (to be implemented).

        This mode provides full isolation and is suitable for exercises and exams.

        Args:
            code: Python code to execute
            test_cases: Optional list of test cases to run

        Returns:
            dict: Execution results
        """
        # TODO: Implement Docker-based execution
        return {
            'output': '',
            'status': 'error',
            'execution_time': 0,
            'error': 'Docker execution mode not yet implemented. Coming soon!'
        }

    def execute_with_tests(self, code, test_cases, timeout=10):
        """
        Execute code and run test cases against it.

        Args:
            code: Python code to execute
            test_cases: List of test case dictionaries with 'input' and 'expected'
            timeout: Maximum execution time in seconds

        Returns:
            dict: {
                'status': str,  # 'passed', 'failed', or 'error'
                'total_tests': int,
                'passed_tests': int,
                'failed_tests': int,
                'test_results': list,  # Individual test results
                'execution_time': float,
                'error': str,
                'output': str
            }
        """
        output_buffer = io.StringIO()
        error_buffer = io.StringIO()
        start_time = time.time()
        
        # Initialize results
        results = {
            'status': 'error',
            'total_tests': 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'test_results': [],
            'execution_time': 0,
            'error': None,
            'output': ''
        }

        # Handle test_cases format (list or dict with 'tests' key)
        tests = []
        if isinstance(test_cases, dict):
            tests = test_cases.get('tests', [])
        elif isinstance(test_cases, list):
            tests = test_cases
        
        results['total_tests'] = len(tests)
        
        # Check for prohibited operations
        error_msg = self._check_prohibited_keywords(code)
        if error_msg:
            results['error'] = error_msg
            return results

        try:
            # Redirect stdout and stderr
            with redirect_stdout(output_buffer), redirect_stderr(error_buffer):
                # Create a restricted namespace
                namespace = {'__builtins__': self._get_safe_builtins()}
                
                # Execute the user code first (to define functions)
                exec(code, namespace)
                
                # Run tests
                for test in tests:
                    test_input = test.get('input')
                    expected = test.get('expected')
                    if expected is None:
                        expected = test.get('expected_output') # Handle both keys
                        
                    test_result = {
                        'input': test_input,
                        'expected': expected,
                        'actual': None,
                        'passed': False,
                        'error': None,
                        'description': test.get('description', '')
                    }
                    
                    try:
                        # Evaluate the test input expression in the same namespace
                        actual = eval(test_input, namespace)
                        test_result['actual'] = actual
                        
                        # Compare results
                        if actual == expected:
                            test_result['passed'] = True
                            results['passed_tests'] += 1
                        else:
                            test_result['passed'] = False
                            results['failed_tests'] += 1
                            
                    except Exception as e:
                        test_result['passed'] = False
                        test_result['error'] = str(e)
                        results['failed_tests'] += 1
                    
                    results['test_results'].append(test_result)
                    
            # Determine final status
            if results['failed_tests'] == 0 and results['passed_tests'] == results['total_tests']:
                results['status'] = 'passed'
            elif results['failed_tests'] > 0:
                results['status'] = 'failed'
            else:
                results['status'] = 'error' # Should not happen if total > 0
                
            output = output_buffer.getvalue()
            errors = error_buffer.getvalue()
            
            if errors:
                output += '\n' + errors
            
            results['output'] = output

        except Exception as e:
            results['status'] = 'error'
            results['error'] = f'{type(e).__name__}: {str(e)}\n\n{traceback.format_exc()}'
            
        end_time = time.time()
        results['execution_time'] = (end_time - start_time) * 1000
        
        return results


# Convenience function for simple execution
def execute_python_code(code, timeout=5):
    """
    Simple wrapper function to execute Python code.

    Args:
        code: Python code string
        timeout: Maximum execution time in seconds

    Returns:
        dict: Execution results
    """
    executor = CodeExecutor(timeout=timeout)
    return executor.execute_code(code, mode='restricted')
