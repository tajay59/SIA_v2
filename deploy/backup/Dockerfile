# Backup runner: mongodump/mongorestore (from the mongo image) + restic (static binary). INFRASTRUCTURE §7.
FROM restic/restic:0.17.3 AS restic
FROM mongo:8.0.30
COPY --from=restic /usr/bin/restic /usr/local/bin/restic
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /home/backup /restic && chown 999 /home/backup /restic   # /restic: local repository (tests)
ENV HOME=/home/backup
COPY --chmod=755 backup.sh restore.sh /usr/local/bin/
ENTRYPOINT []
# Default: wait for BACKUP_AT each day, run backup.sh. `docker compose run backup backup.sh` runs one now.
CMD ["bash", "-c", "while true; do now=$(date +%s); next=$(date -d \"today ${BACKUP_AT:-02:00}\" +%s); [ $next -le $now ] && next=$(date -d \"tomorrow ${BACKUP_AT:-02:00}\" +%s); sleep $((next-now)); backup.sh || echo 'backup FAILED'; done"]
