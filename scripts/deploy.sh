#!/usr/bin/env bash
# Idempotent production deploy script (6.3). Run on the server:
#   bash scripts/deploy.sh
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[1/4] Pulling latest code..."
git pull --ff-only

echo "[2/4] Migrating database..."
python manage.py migrate --settings=config.settings.production

echo "[3/4] Collecting static files..."
python manage.py collectstatic --noinput --settings=config.settings.production

echo "[4/4] Restarting workers..."
# systemd unit names — adjust to your deployment
sudo systemctl restart teaching-space-gunicorn || true
sudo systemctl restart teaching-space-celery || true

echo "Deploy complete."
