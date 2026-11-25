#!/usr/bin/env bash
set -euo pipefail
umask 077

work="$HOME/medirover-central"
export PGPASSFILE="$work/.pgpass"
export PGOPTIONS='-c TimeZone=UTC'
target='host=10.20.30.10 port=5432 dbname=medirover_central user=medirover_sync connect_timeout=5'
export_dir=$(mktemp -d "$work/snapshot.XXXXXX")
trap 'rm -f "$export_dir/orders.csv" "$export_dir/measurements.csv"; rmdir "$export_dir"' EXIT
cd "$export_dir"

psql -Xwq -v ON_ERROR_STOP=1 -d medirover_demo <<'SQL'
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
\copy (SELECT request_id, station, status, created_at, last_error FROM public.medirover_orders) TO 'orders.csv' CSV
\copy (SELECT id, temperature_c, measured_at, humidity_percent FROM public.medirover_temperatures) TO 'measurements.csv' CSV
COMMIT;
SQL

psql -Xwq -v ON_ERROR_STOP=1 "$target" <<'SQL'
BEGIN;
CREATE TEMP TABLE incoming_orders (LIKE public.medirover_orders) ON COMMIT DROP;
CREATE TEMP TABLE incoming_measurements (LIKE public.medirover_temperatures) ON COMMIT DROP;
\copy incoming_orders (request_id, station, status, created_at, last_error) FROM 'orders.csv' CSV
\copy incoming_measurements (id, temperature_c, measured_at, humidity_percent) FROM 'measurements.csv' CSV

-- Release the previous active slot before copying a new active trip.
UPDATE public.medirover_orders AS saved SET status = incoming.status
FROM incoming_orders AS incoming
WHERE saved.request_id = incoming.request_id
  AND saved.status IN ('pending', 'running', 'delivered', 'stopped')
  AND incoming.status NOT IN ('pending', 'running', 'delivered', 'stopped');

-- An active copy that disappeared at the source no longer reserves the rover.
DELETE FROM public.medirover_orders AS saved
WHERE saved.status IN ('pending', 'running', 'delivered', 'stopped')
  AND NOT EXISTS (SELECT 1 FROM incoming_orders WHERE request_id = saved.request_id);

INSERT INTO public.medirover_orders (request_id, station, status, created_at, last_error)
SELECT request_id, station, status, created_at, last_error FROM incoming_orders
ON CONFLICT (request_id) DO UPDATE SET
    station = EXCLUDED.station, status = EXCLUDED.status,
    created_at = EXCLUDED.created_at, last_error = EXCLUDED.last_error;

INSERT INTO public.medirover_temperatures (id, temperature_c, measured_at, humidity_percent)
SELECT id, temperature_c, measured_at, humidity_percent FROM incoming_measurements
ON CONFLICT (id) DO UPDATE SET
    temperature_c = EXCLUDED.temperature_c, measured_at = EXCLUDED.measured_at,
    humidity_percent = EXCLUDED.humidity_percent;

SELECT (SELECT count(*) FROM incoming_orders) AS orders_in_snapshot,
       count(*) AS measurements_in_snapshot, max(id) AS last_measurement_id
FROM incoming_measurements;
COMMIT;
SQL

printf '[%s] MEDIROVER_CENTRAL_SYNC_OK\n' "$(date -Is)"
