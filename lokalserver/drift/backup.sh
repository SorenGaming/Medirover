#!/usr/bin/env bash
set -euo pipefail
umask 077

work="$HOME/medirover-backup"
dump=$(mktemp "$work/medirover_demo.XXXXXX.dump")
trap 'rm -f "$dump"' EXIT

printf '[%s] Starting medirover_demo backup\n' "$(date -Is)"
pg_dump -w --format=custom --no-owner --no-privileges --dbname=medirover_demo --file="$dump"
pg_restore --list "$dump" >/dev/null
checksum=$(sha256sum "$dump" | cut -d ' ' -f 1)
length=$(stat -c %s "$dump")
reply=$(
    { printf '%s %s\n' "$checksum" "$length"; cat "$dump"; } |
        ssh -T -o BatchMode=yes -o ConnectTimeout=10 \
            -o StrictHostKeyChecking=yes -o HostKeyAlgorithms=ssh-ed25519 \
            -o IdentitiesOnly=yes -o UserKnownHostsFile="$HOME/.ssh/known_hosts.medirover-backup" \
            -i "$HOME/.ssh/medirover-windows-backup" isaks@10.20.30.10
)
printf '%s\n' "$reply"
grep -q "^MEDIROVER_BACKUP_OK $checksum medirover_demo-" <<< "$reply"
completed_at=$(date -Is)
printf '[%s] Backup verified on Windows B\n' "$completed_at"
bash "$HOME/Medirover/lokalserver/drift/publish-backup-status.sh" "$completed_at"
