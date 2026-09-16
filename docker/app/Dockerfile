# Application image for the teaching platform.
# Build from the repo root:  docker build -f docker/app/Dockerfile -t teaching-space-app .

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

# System deps: none beyond CA certs (psycopg2-binary wheel handles Postgres)
COPY requirements.txt .
RUN pip install --no-cache-dir \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        -r requirements.txt \
    && pip install --no-cache-dir \
        -i https://pypi.tuna.tsinghua.edu.cn/simple \
        gunicorn==21.2.0

COPY . .

RUN useradd --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/media /app/logs /app/staticfiles \
    && chown -R app:app /app

USER app

EXPOSE 8000

# Collect static at image build; migrate/createsuperuser run at deploy time
RUN python manage.py collectstatic --noinput || true

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
