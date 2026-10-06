#!/bin/sh
# Startscript voor Docker/Render: database bijwerken, basisgegevens (eenmalig), beheerder, webserver.
set -e
python manage.py migrate --noinput
python manage.py seed_portal --if-empty
python manage.py ensure_admin
exec gunicorn config.wsgi --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --timeout 120
