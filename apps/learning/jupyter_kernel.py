"""Real Jupyter kernel sessions for the notebook interface.

Each (user, lesson) pair gets ONE long-lived ipykernel session, so code
cells behave like a true notebook: variables persist across cells, rich
outputs (matplotlib images, display data, tracebacks) come back, and
execution counts increment.

Kernel backends (settings.JUPYTER_KERNEL_BACKEND):
- ``local`` (default, dev): ipykernel runs as a local subprocess — full
  Python, so it is DEV-ONLY; never expose a local-backend deployment to
  untrusted users.
- ``docker``: the kernel runs inside the ``teaching-space-kernel`` image
  (network disabled via localhost-only port publishing, memory/CPU/PID
  caps, non-root, capabilities dropped). Production mode.

Idle kernels are reaped after JUPYTER_KERNEL_IDLE_TIMEOUT seconds; the
registry is capped at JUPYTER_MAX_KERNELS (LRU eviction).
"""

import json
import logging
import threading
import time

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    from jupyter_client.manager import KernelManager
    from jupyter_client.manager import start_new_kernel  # noqa: F401 (legacy path)
    HAS_JUPYTER = True
except ImportError:  # pragma: no cover - jupyter_client not installed
    KernelManager = None
    HAS_JUPYTER = False

#: Cap on text output per cell (chars).
MAX_TEXT_OUTPUT = 50_000
#: Cap on binary display data (e.g. PNG) per cell (bytes).
MAX_BINARY_OUTPUT = 5 * 1024 * 1024

_KERNEL_STARTUP = "%matplotlib inline\n"  # rich plots for matplotlib users


class _KernelSession:
    """One live kernel + its bookkeeping."""

    def __init__(self, km):
        self.km = km
        self.client = None
        self.last_active = time.time()

    def ensure_client(self):
        if self.client is None or not self.client.channels_running:
            self.client = self.km.client()
            self.client.start_channels()
        return self.client

    def shutdown(self):
        try:
            if self.client is not None:
                self.client.stop_channels()
        except Exception:
            pass
        try:
            self.km.shutdown_kernel(now=True)
        except Exception:
            pass


class DockerKernelManager(KernelManager):
    """KernelManager that launches the kernel inside a sandbox container.

    The connection file's five ZMQ ports are published on 127.0.0.1 only
    (loopback NAT), so the kernel's channels are reachable solely from the
    host — no network exposure, no host networking requirement (works on
    Docker Desktop for Windows).
    """

    def __init__(self, image='teaching-space-kernel', **kwargs):
        self.image = image
        super().__init__(**kwargs)

    def _launch_kernel(self, kernel_cmd, **kw):
        import shutil
        import tempfile
        from pathlib import Path

        if shutil.which('docker') is None:
            raise RuntimeError('JUPYTER_KERNEL_BACKEND=docker requires the docker CLI')

        # The connection file is written by the base class before this runs.
        conn = json.loads(Path(self.connection_file).read_text(encoding='utf-8'))
        ports = [
            conn['shell_port'], conn['iopub_port'], conn['stdin_port'],
            conn['hb_port'], conn['control_port'],
        ]

        # Copy the connection file into a temp dir mounted into the container
        # (ipykernel needs it; Windows paths are handled by docker -v).
        mount_dir = tempfile.mkdtemp(prefix='jupyter_conn_')
        (Path(mount_dir) / 'kernel.json').write_text(
            json.dumps(conn), encoding='utf-8')

        docker_cmd = [
            'docker', 'run', '--rm', '-i',
            '--memory', '1g',
            '--cpus', '1.0',
            '--pids-limit', '256',
            '--cap-drop', 'ALL',
            '-v', f'{mount_dir}:/kernel:ro',
        ]
        for p in ports:
            docker_cmd += ['-p', f'127.0.0.1:{p}:{p}']
        docker_cmd += [
            self.image,
            'python', '-m', 'ipykernel_launcher',
            '-f', '/kernel/kernel.json',
        ]

        return super()._launch_kernel(docker_cmd, **kw)


def _kernel_manager():
    """A KernelManager configured for the active backend."""
    backend = getattr(settings, 'JUPYTER_KERNEL_BACKEND', 'local')
    if backend == 'docker':
        image = getattr(settings, 'JUPYTER_KERNEL_IMAGE', 'teaching-space-kernel')
        return DockerKernelManager(image=image, kernel_name='python3')
    return KernelManager(kernel_name='python3')


class KernelSessionManager:
    """Registry of live kernel sessions keyed by (user_id, lesson_id)."""

    def __init__(self):
        self._sessions = {}
        self._lock = threading.Lock()

    # -- lifecycle ----------------------------------------------------------

    def _session_key(self, user_id, lesson_id):
        return f'{user_id}:{lesson_id}'

    def get_or_create(self, user_id, lesson_id):
        """Return the (existing or freshly started) kernel session."""
        if not HAS_JUPYTER:
            raise RuntimeError(
                'jupyter_client/ipykernel are not installed — '
                'pip install jupyter_client ipykernel')

        key = self._session_key(user_id, lesson_id)
        with self._lock:
            self._reap_locked(now=time.time())
            session = self._sessions.get(key)
            if session is not None and session.km.is_alive():
                session.last_active = time.time()
                return session
            if session is not None:
                session.shutdown()
                del self._sessions[key]

            km = _kernel_manager()
            km.start_kernel()
            session = _KernelSession(km)
            self._sessions[key] = session

            # Rich matplotlib outputs from the first cell on
            try:
                self._execute_raw(session, _KERNEL_STARTUP, timeout=10)
            except Exception as e:
                logger.warning('kernel startup magic failed: %s', e)
        return session

    def restart(self, user_id, lesson_id):
        """Restart the kernel (clears all variables), keeping the session slot."""
        key = self._session_key(user_id, lesson_id)
        with self._lock:
            session = self._sessions.pop(key, None)
            if session is not None:
                session.shutdown()
        return self.get_or_create(user_id, lesson_id)

    def shutdown_all(self):
        with self._lock:
            for session in self._sessions.values():
                session.shutdown()
            self._sessions.clear()

    def _reap_locked(self, now):
        """Drop idle (and, if over capacity, least-recently-used) kernels."""
        idle_timeout = float(getattr(settings, 'JUPYTER_KERNEL_IDLE_TIMEOUT', 15 * 60))
        max_kernels = int(getattr(settings, 'JUPYTER_MAX_KERNELS', 20))

        stale = [
            key for key, s in self._sessions.items()
            if now - s.last_active > idle_timeout
        ]
        for key in stale:
            self._sessions[key].shutdown()
            del self._sessions[key]

        while len(self._sessions) > max_kernels:
            lru_key = min(
                self._sessions, key=lambda k: self._sessions[k].last_active)
            self._sessions[lru_key].shutdown()
            del self._sessions[lru_key]

    # -- execution ----------------------------------------------------------

    def execute(self, user_id, lesson_id, code, timeout=None):
        """Execute code in the session; return {'outputs', 'execution_count'}.

        Outputs are rich Jupyter messages:
        {'type': 'stream'|'execute_result'|'display_data'|'error', ...}
        """
        if timeout is None:
            timeout = float(getattr(settings, 'JUPYTER_EXECUTE_TIMEOUT', 15))
        key = self._session_key(user_id, lesson_id)
        session = self.get_or_create(user_id, lesson_id)
        with self._lock:
            session.last_active = time.time()
        result = self._execute_raw(session, code, timeout)

        if result.pop('_restart_needed', False):
            # Interrupt couldn't recover the kernel (e.g. Windows has no
            # POSIX signals) — replace the session so the next cell works.
            with self._lock:
                current = self._sessions.pop(key, None)
                if current is not None:
                    current.shutdown()
            result['outputs'].append({
                'type': 'error', 'ename': 'TimeoutError',
                'evalue': f'执行超过 {timeout:.0f} 秒；中断未能恢复内核，'
                          f'已重启内核（变量已清空）',
                'traceback': [],
            })
        return result

    def _execute_raw(self, session, code, timeout):
        client = session.ensure_client()
        msg_id = client.execute(code)

        outputs = []
        execution_count = None
        deadline = time.time() + timeout
        got_idle = False

        while time.time() < deadline:
            try:
                msg = client.get_iopub_msg(timeout=1)
            except Exception:
                continue
            if msg['parent_header'].get('msg_id') != msg_id:
                continue
            msg_type = msg['header']['msg_type']
            content = msg['content']

            if msg_type == 'stream':
                outputs.append(self._cap_output({
                    'type': 'stream', 'name': content.get('name', 'stdout'),
                    'text': content.get('text', ''),
                }))
            elif msg_type in ('execute_result', 'display_data'):
                data = content.get('data', {})
                if msg_type == 'execute_result':
                    execution_count = content.get('execution_count')
                outputs.append(self._cap_output({
                    'type': msg_type,
                    'data': {k: v for k, v in data.items()
                             if k in ('text/plain', 'text/html', 'text/markdown',
                                      'image/png', 'image/jpeg')},
                    'execution_count': execution_count,
                }))
            elif msg_type == 'error':
                outputs.append({
                    'type': 'error',
                    'ename': content.get('ename', 'Error'),
                    'evalue': content.get('evalue', ''),
                    'traceback': [t for t in content.get('traceback', [])
                                  if 'ipython-input' not in t][-12:],
                })
            elif msg_type == 'status' and content.get('execution_state') == 'idle':
                got_idle = True
                break

        if not got_idle:
            # Jupyter-style soft stop: interrupt keeps the session alive so
            # students don't lose their variables on a runaway loop. Where
            # interrupts don't work (Windows), fall back to a restart.
            try:
                session.km.interrupt_kernel()
                recovered = self._drain_until_idle(client, msg_id, timeout=3)
            except Exception:
                recovered = False
            if recovered:
                outputs.append({
                    'type': 'error', 'ename': 'TimeoutError',
                    'evalue': f'执行超过 {timeout:.0f} 秒，已中断（会话状态保留）',
                    'traceback': [],
                })
            else:
                return {
                    'outputs': outputs,
                    'execution_count': execution_count,
                    '_restart_needed': True,
                }

        # The authoritative execution count lives in the shell-channel
        # execute_reply (execute_result only carries it for expressions).
        try:
            deadline = time.time() + 2
            while time.time() < deadline:
                reply = client.get_shell_msg(timeout=0.5)
                if reply['parent_header'].get('msg_id') == msg_id:
                    execution_count = reply['content'].get('execution_count')
                    break
        except Exception:
            pass

        return {'outputs': outputs, 'execution_count': execution_count}

    @staticmethod
    def _cap_output(output):
        """Truncate huge text/binary payloads before they hit the wire."""
        if output['type'] == 'stream':
            if len(output['text']) > MAX_TEXT_OUTPUT:
                output['text'] = output['text'][:MAX_TEXT_OUTPUT] + '\n…(输出已截断)'
            return output
        data = output.get('data', {})
        for key, value in list(data.items()):
            if isinstance(value, str) and len(value) > MAX_TEXT_OUTPUT:
                data[key] = value[:MAX_TEXT_OUTPUT] + '…(输出已截断)'
            elif isinstance(value, (bytes, bytearray)) and len(value) > MAX_BINARY_OUTPUT:
                data[key] = None  # drop oversized images rather than truncate
        return output

    @staticmethod
    def _drain_until_idle(client, msg_id, timeout):
        """Drain iopub until the given request reaches idle; True if it did."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = client.get_iopub_msg(timeout=1)
            except Exception:
                return False
            if msg['parent_header'].get('msg_id') == msg_id and \
                    msg['header']['msg_type'] == 'status' and \
                    msg['content'].get('execution_state') == 'idle':
                return True
        return False


#: Module-level singleton used by the views.
manager = KernelSessionManager()
