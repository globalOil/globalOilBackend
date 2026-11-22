#!/bin/sh

set -e

# Deliberately harmless deployment marker: confirms the active image reached startup.
echo "Global Oil backend deployment smoke check"

if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "Applying committed database migrations..."
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
fi

exec "$@"
