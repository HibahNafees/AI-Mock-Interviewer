#!/bin/sh
# Bring the schema up to date, then run the given command (gunicorn by default).
set -e
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  flask db upgrade
fi
exec "$@"
