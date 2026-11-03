-- Write-back test: CTAS to FSx for ONTAP via S3 AP
--
-- Result on Trino 481 (checked 2026-11-03): with rows in fsxn.sensor_data.readings the
-- CTAS FAILS with HIVE_WRITER_CLOSE_ERROR. With an empty source it reports "0 rows" and
-- succeeds, because no object is written; that is not a write test.
-- Cause: Trino sets x-amz-storage-class on every PutObject and CreateMultipartUpload
-- (s3.storage-class defaults to STANDARD; none of its 11 values is FSX_ONTAP or "none"),
-- and an FSx for ONTAP S3 Access Point answers InvalidStorageClass to all 11. The same
-- PutObject with no storage class, or with FSX_ONTAP, succeeds. No catalog property
-- works around it. Reading is unaffected. Details: ../README.md, section "Writing".

-- Create output schema
CREATE SCHEMA IF NOT EXISTS fsxn.analytics_output
WITH (location = 's3://<FSX_S3_AP_ALIAS>/trino-output/');

-- CTAS: Write aggregated results back to FSx for ONTAP
CREATE TABLE fsxn.analytics_output.hourly_summary
WITH (format = 'PARQUET')
AS
SELECT
    date_trunc('hour', timestamp) AS hour,
    status,
    COUNT(*) AS reading_count,
    AVG(temperature) AS avg_temperature,
    AVG(humidity) AS avg_humidity,
    AVG(pressure) AS avg_pressure
FROM fsxn.sensor_data.readings
GROUP BY date_trunc('hour', timestamp), status;

-- Verify write-back
SELECT * FROM fsxn.analytics_output.hourly_summary LIMIT 10;
