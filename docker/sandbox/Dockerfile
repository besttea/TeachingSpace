# Sandbox image for executing student Python code (full OS-level isolation).
#
# Build from the repo root:
#   docker build -f docker/sandbox/Dockerfile -t teaching-space-sandbox .
#
# Run mode: the Django executor passes a JSON request via stdin; the runner
# (apps/code_runner/sandbox_runner.py — the SAME file used by subprocess
# mode) executes it and writes __SANDBOX_RESULT__<json> to stdout.

FROM python:3.13-slim

# Non-root user (defense in depth; docker run also drops all capabilities)
RUN useradd --create-home --shell /usr/sbin/nologin sandbox

WORKDIR /sandbox

# The single source of truth for sandboxed execution — keep it in sync with
# the subprocess mode automatically (both read this file).
COPY apps/code_runner/sandbox_runner.py /sandbox/runner.py

# Optional hardening: RestrictedPython (uncomment to enable compile-time
# restrictions inside the sandbox; the runner auto-detects the package).
# RUN pip install --no-cache-dir RestrictedPython==7.0

RUN chown -R sandbox:sandbox /sandbox

USER sandbox

ENTRYPOINT ["python", "/sandbox/runner.py"]
