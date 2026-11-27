#!/usr/bin/env bash
set -euo pipefail
umask 077

# Opdater kun tidspunktet, efter at modtageren har bekræftet SHA-256.
static_dir="$(cd -- "$(dirname -- "$0")/../static" && pwd)"
completed_at=$(date --iso-8601=seconds --date="$1")
status_file=$(mktemp "$static_dir/.backup-status.XXXXXX")
trap 'rm -f "$status_file"' EXIT
printf '{"last_success_at":"%s"}\n' "$completed_at" > "$status_file"
chmod 0644 "$status_file"
mv -f "$status_file" "$static_dir/backup-status.json"
