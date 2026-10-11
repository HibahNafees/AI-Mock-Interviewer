#!/bin/sh
# Daily MySQL dump from the compose stack; keeps the newest 14.
# cron: 0 3 * * * /home/ubuntu/InterVox/deploy/backup.sh
set -e
cd "$(dirname "$0")/.."
mkdir -p "$HOME/backups"
docker compose exec -T db sh -c 'mysqldump --single-transaction -u mock -p"$MYSQL_PASSWORD" mock_interviewer' \
  | gzip > "$HOME/backups/db-$(date +%F).sql.gz"
ls -1t "$HOME"/backups/db-*.sql.gz | tail -n +15 | xargs -r rm --
