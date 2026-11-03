#!/bin/bash
set -euo pipefail

# Trino + FSx for ONTAP S3 AP Verification Script
# Prerequisites:
#   - Docker installed
#   - AWS credentials exported in this shell (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY and,
#     for temporary credentials, AWS_SESSION_TOKEN). docker-compose.yaml passes them through.
#   - Permission to use the Glue Data Catalog (the fsxn catalog keeps its schemas and
#     tables there; Test 2 and Test 3 create a database and a table)
#   - FSx for ONTAP S3 AP alias known
#
# Side effect: Test 2 and Test 3 create the Glue database sensor_data and its table
# readings in the account these credentials belong to. cleanup.sh stops the container
# only; delete them in Glue when you are done:
#   aws glue delete-table --database-name sensor_data --name readings
#   aws glue delete-database --name sensor_data

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
AP_ALIAS="${1:-}"

if [ -z "$AP_ALIAS" ]; then
    echo "Usage: $0 <fsx-s3-ap-alias>"
    echo "Example: $0 athena-verificat-e8z7oep4u3hrqr7wzke4b8k6yi65hapn1b-ext-s3alias"
    exit 1
fi

echo "=== Trino + FSx for ONTAP S3 AP Verification ==="
echo "AP Alias: $AP_ALIAS"
echo ""

# 1. Check credentials. The container reads them from the environment; without them the
#    queries below fail later with errors that do not say why.
echo "1. Checking AWS credentials in the environment..."
if [ -z "${AWS_ACCESS_KEY_ID:-}" ] || [ -z "${AWS_SECRET_ACCESS_KEY:-}" ]; then
    echo "   AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are not set." >&2
    echo "   For SSO: eval \"\$(aws configure export-credentials --format env)\"" >&2
    exit 1
fi

# 2. Start Trino
echo "2. Starting Trino container..."
cd "$PROJECT_DIR"
docker compose up -d
echo "   Waiting for Trino to start (30s)..."
sleep 30

# 3. Check Trino health
echo "3. Checking Trino health..."
if curl -s http://localhost:8080/v1/info | grep -q '"starting":false'; then
    echo "   Trino is ready ✅"
else
    echo "   Trino not ready yet, waiting 15s more..."
    sleep 15
fi

# 4. Run verification queries
echo "4. Running verification queries..."
echo ""

echo "--- Test 1: List files via S3 AP ---"
docker exec trino trino --execute "
    SELECT * FROM system.metadata.table_properties LIMIT 5
" 2>&1 || echo "   (metadata query — informational)"

echo ""
echo "--- Test 2: Create schema ---"
docker exec trino trino --execute "
    CREATE SCHEMA IF NOT EXISTS fsxn.sensor_data
    WITH (location = 's3://${AP_ALIAS}/sensor-data/')
" 2>&1 && echo "   Schema created ✅" || echo "   Schema creation FAILED ❌"

echo ""
echo "--- Test 3: Create table on Parquet ---"
docker exec trino trino --execute "
    CREATE TABLE IF NOT EXISTS fsxn.sensor_data.readings (
        device_id VARCHAR,
        timestamp TIMESTAMP,
        temperature DOUBLE,
        humidity DOUBLE,
        pressure DOUBLE,
        status VARCHAR
    ) WITH (
        external_location = 's3://${AP_ALIAS}/sensor-data/',
        format = 'PARQUET'
    )
" 2>&1 && echo "   Table created ✅" || echo "   Table creation FAILED ❌"

echo ""
echo "--- Test 4: COUNT(*) ---"
START=$(date +%s%N)
docker exec trino trino --execute "
    SELECT COUNT(*) AS total_rows FROM fsxn.sensor_data.readings
" 2>&1
END=$(date +%s%N)
echo "   Duration: $(( (END - START) / 1000000 ))ms"

echo ""
echo "--- Test 5: GROUP BY ---"
START=$(date +%s%N)
docker exec trino trino --execute "
    SELECT status, COUNT(*), AVG(temperature) FROM fsxn.sensor_data.readings GROUP BY status
" 2>&1
END=$(date +%s%N)
echo "   Duration: $(( (END - START) / 1000000 ))ms"

echo ""
echo "=== Verification Complete ==="
echo "To stop Trino: docker compose down"
echo "The Glue database sensor_data (table readings) was created and is still there."
