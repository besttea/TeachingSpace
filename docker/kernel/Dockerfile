# Jupyter kernel image for the learning class — REAL notebook semantics.
#
# Each (user, lesson) session gets a kernel from this image, launched by
# Django via jupyter_client (see apps/learning/jupyter_kernel.py). The
# manager publishes the kernel's five ZMQ ports on 127.0.0.1 only and runs
# with resource caps, so kernels are loopback-reachable but network-free.
#
# Build from the repo root:
#   docker build -f docker/kernel/Dockerfile -t teaching-space-kernel .
#
# NOTE: China networks may need a pip mirror (defaults to Tsinghua TUNA).

FROM python:3.13-slim

RUN useradd --create-home --shell /usr/sbin/nologin sandbox

# Scientific stack for teaching (keep it small: numpy + matplotlib + pandas)
RUN pip install --no-cache-dir \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        ipykernel==6.29.5 numpy==2.2.0 matplotlib==3.10.0 pandas==2.2.3

USER sandbox

ENTRYPOINT ["python", "-m", "ipykernel_launcher"]
