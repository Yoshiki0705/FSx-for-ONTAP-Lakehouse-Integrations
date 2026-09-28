-- Manufacturing Data Platform PoC — Unity Catalog v2 (Edge-Aligned)
-- Synced from: ONTAP-Edge-to-Cloud-AI Databricks integration design
-- Sync Date: 2026-06-15
--
-- Schema: manufacturing_poc (shared between Edge and Lakehouse projects)
--   bronze — Raw Kafka events, sensor events, quality events, payload manifest, raw images
--   silver — Training features, quality trends, equipment health
--   gold   — Training dataset, quality summary, predictive maintenance
--   ml     — ML models and feature tables
--
-- Replaces the factory_alpha/factory_beta per-site separation with
-- medallion architecture (site_id as a column filter instead).
--
-- Run this in a Databricks SQL warehouse or notebook with admin privileges.
-- Prerequisites: Unity Catalog metastore attached to workspace.

-- ============================================================
-- Step 1: Create Catalog (if not exists from v1)
-- ============================================================
CREATE CATALOG IF NOT EXISTS manufacturing_poc
COMMENT 'Manufacturing Data Platform PoC — Edge-to-Cloud aligned, medallion architecture';

-- ============================================================
-- Step 2: Create Schemas (Medallion + ML)
-- ============================================================
CREATE SCHEMA IF NOT EXISTS manufacturing_poc.bronze
COMMENT 'Raw ingested data from Kafka, sensors, quality inspections, and payload manifests';

CREATE SCHEMA IF NOT EXISTS manufacturing_poc.silver
COMMENT 'Cleansed, joined, and enriched data — training features, quality trends, equipment health';

CREATE SCHEMA IF NOT EXISTS manufacturing_poc.gold
COMMENT 'Business-level aggregates — training datasets, quality summaries, predictive maintenance';

CREATE SCHEMA IF NOT EXISTS manufacturing_poc.ml
COMMENT 'ML models, feature tables, and inference results';

-- ============================================================
-- Step 3: Bronze Tables
-- ============================================================

-- Bronze: Raw Kafka events (all event types from factory.events.raw)
CREATE TABLE IF NOT EXISTS manufacturing_poc.bronze.kafka_events (
    event_id STRING NOT NULL COMMENT 'UUID v4 event identifier',
    event_type STRING NOT NULL COMMENT 'payload_arrival | sensor_event | quality_event | anomaly_event | telemetry_event',
    domain STRING DEFAULT 'manufacturing' COMMENT 'Event domain',
    event_category STRING COMMENT 'quality_inspection | environmental_monitoring | equipment_telemetry | storage_health',
    source_id STRING NOT NULL COMMENT 'Edge device ID (e.g., rpi5-001)',
    asset_type STRING COMMENT '3d_printer | storage_system | sensor_array',
    asset_id STRING COMMENT 'Specific asset ID (e.g., bambu-p2s-001)',
    site_id STRING NOT NULL COMMENT 'Site identifier (e.g., lab-tokyo)',
    line_id STRING COMMENT 'Production line ID',
    equipment_id STRING COMMENT 'Equipment ID within site',
    sensor_id STRING COMMENT 'Sensor ID within equipment',
    event_timestamp TIMESTAMP NOT NULL COMMENT 'Event time (from device)',
    ingest_time TIMESTAMP COMMENT 'Kafka publish time',
    schema_version STRING DEFAULT '2.0.0' COMMENT 'Event envelope schema version',
    payload_uri STRING COMMENT 'NFS/SMB/S3 URI to payload (or null)',
    payload_type STRING COMMENT 'image | csv | json | null',
    content_type STRING COMMENT 'MIME type (image/jpeg, application/json, etc.)',
    checksum STRING COMMENT 'sha256:<hex> (or null)',
    size_bytes BIGINT COMMENT 'Payload size in bytes',
    lineage_id STRING COMMENT 'Session or batch lineage ID',
    processing_status STRING COMMENT 'pending_analysis | completed | failed',
    metadata STRING COMMENT 'JSON — event-type specific metadata',
    is_synthetic BOOLEAN DEFAULT false COMMENT 'Governance: top-level synthetic-data flag (false when absent)',
    -- Ingestion metadata
    _kafka_topic STRING COMMENT 'Source Kafka topic',
    _kafka_partition INT COMMENT 'Source Kafka partition',
    _kafka_offset BIGINT COMMENT 'Source Kafka offset',
    _ingested_at TIMESTAMP DEFAULT current_timestamp() COMMENT 'Delta write time'
)
USING DELTA
PARTITIONED BY (event_type, date(event_timestamp))
COMMENT 'Raw Kafka events from all topics — unified event envelope v2.0.0'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true',
    'delta.deletedFileRetentionDuration' = 'interval 7 days',
    'delta.logRetentionDuration' = 'interval 30 days'
);

-- Bronze: Sensor events (extracted from raw for fast time-series queries)
CREATE TABLE IF NOT EXISTS manufacturing_poc.bronze.sensor_events (
    event_id STRING NOT NULL,
    site_id STRING NOT NULL,
    equipment_id STRING NOT NULL,
    sensor_id STRING NOT NULL,
    event_timestamp TIMESTAMP NOT NULL,
    sensor_type STRING COMMENT 'temperature | humidity | pressure | vibration | current',
    value DOUBLE NOT NULL COMMENT 'Sensor reading value',
    unit STRING COMMENT 'Measurement unit',
    source_id STRING,
    lineage_id STRING,
    _ingested_at TIMESTAMP DEFAULT current_timestamp()
)
USING DELTA
PARTITIONED BY (site_id, date(event_timestamp))
COMMENT 'Sensor readings extracted from kafka_events for time-series analysis'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true'
);

-- Bronze: Quality events (AI analysis results)
CREATE TABLE IF NOT EXISTS manufacturing_poc.bronze.quality_events (
    event_id STRING NOT NULL,
    event_type STRING NOT NULL,
    event_category STRING,
    site_id STRING NOT NULL,
    line_id STRING,
    equipment_id STRING,
    sensor_id STRING,
    event_timestamp TIMESTAMP NOT NULL,
    ingest_time TIMESTAMP,
    payload_uri STRING,
    payload_type STRING,
    content_type STRING,
    checksum STRING,
    size_bytes BIGINT,
    processing_status STRING,
    classification_result STRING COMMENT 'AI classification output',
    confidence_score DOUBLE COMMENT 'Model confidence (0.0-1.0)',
    defect_type STRING COMMENT 'Defect category if detected',
    model_id STRING COMMENT 'ML model used for inference',
    model_version STRING COMMENT 'Model version',
    metadata STRING,
    _ingested_at TIMESTAMP DEFAULT current_timestamp()
)
USING DELTA
PARTITIONED BY (site_id, date(event_timestamp))
COMMENT 'Quality inspection and AI analysis results'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true'
);

-- Bronze: Payload manifest (ONTAP ↔ Event linkage)
CREATE TABLE IF NOT EXISTS manufacturing_poc.bronze.payload_manifest (
    payload_uri STRING NOT NULL COMMENT 'Full path on ONTAP (nfs://svm/vol/path)',
    event_id STRING NOT NULL COMMENT 'Linked event ID',
    site_id STRING NOT NULL,
    equipment_id STRING,
    asset_id STRING,
    payload_type STRING,
    content_type STRING,
    checksum STRING,
    size_bytes BIGINT,
    storage_protocol STRING DEFAULT 'nfs' COMMENT 'nfs | smb | s3',
    svm_name STRING COMMENT 'ONTAP SVM name',
    volume_name STRING COMMENT 'ONTAP volume name',
    ontap_snapshot STRING COMMENT 'Snapshot name if applicable',
    registered_at TIMESTAMP NOT NULL,
    verified BOOLEAN DEFAULT false,
    verified_at TIMESTAMP,
    lineage_id STRING,
    _ingested_at TIMESTAMP DEFAULT current_timestamp()
)
USING DELTA
PARTITIONED BY (site_id, date(registered_at))
COMMENT 'Registry linking ONTAP payload files to Kafka events'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true'
);

-- Bronze: Raw images (Auto Loader from DataSync → S3)
CREATE TABLE IF NOT EXISTS manufacturing_poc.bronze.raw_images (
    file_path STRING NOT NULL COMMENT 'S3 path after DataSync',
    original_path STRING COMMENT 'Original NFS path on ONTAP',
    site_id STRING NOT NULL,
    equipment_id STRING,
    content_type STRING DEFAULT 'image/jpeg',
    size_bytes BIGINT,
    checksum STRING,
    captured_at TIMESTAMP COMMENT 'Image capture time (from filename or metadata)',
    synced_at TIMESTAMP COMMENT 'DataSync completion time',
    _ingested_at TIMESTAMP DEFAULT current_timestamp()
)
USING DELTA
PARTITIONED BY (site_id, date(captured_at))
COMMENT 'Image file metadata ingested via Auto Loader (Path C)';

-- Bronze: Feedback events (human ground-truth labels, Edge round 2)
CREATE TABLE IF NOT EXISTS manufacturing_poc.bronze.feedback_events (
    event_id STRING NOT NULL,
    target_event_id STRING NOT NULL COMMENT 'The quality/anomaly event this feedback corrects',
    site_id STRING NOT NULL,
    equipment_id STRING,
    asset_id STRING,
    event_timestamp TIMESTAMP NOT NULL,
    ingest_time TIMESTAMP,
    human_label STRING NOT NULL COMMENT 'Operator-confirmed ground truth',
    label_confidence DOUBLE COMMENT 'Labeler confidence (0.0-1.0)',
    defect_type STRING,
    labeled_by STRING COMMENT 'Operator/role identifier',
    labeled_at TIMESTAMP,
    correction_reason STRING COMMENT 'Why the AI result was corrected',
    original_ai_label STRING COMMENT 'AI prediction being corrected',
    is_synthetic BOOLEAN DEFAULT false COMMENT 'Governance: synthetic data flag',
    metadata STRING,
    _ingested_at TIMESTAMP DEFAULT current_timestamp()
)
USING DELTA
PARTITIONED BY (site_id, date(event_timestamp))
COMMENT 'Human feedback / ground-truth labels for AI accuracy measurement and training'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true'
);

-- ============================================================
-- Step 4: Silver Tables
-- ============================================================

-- Silver: Training features (from ClickHouse training_features_export)
CREATE TABLE IF NOT EXISTS manufacturing_poc.silver.training_features (
    export_id STRING NOT NULL,
    site_id STRING NOT NULL,
    equipment_id STRING NOT NULL,
    sensor_id STRING NOT NULL,
    feature_window_start TIMESTAMP NOT NULL,
    feature_window_end TIMESTAMP NOT NULL,
    avg_value DOUBLE,
    min_value DOUBLE,
    max_value DOUBLE,
    stddev_value DOUBLE,
    count_readings BIGINT,
    p50_value DOUBLE,
    p95_value DOUBLE,
    p99_value DOUBLE,
    quality_label STRING COMMENT 'good | defect | unknown',
    defect_type STRING,
    -- Human ground-truth labels (feedback loop, Edge round 2)
    human_label STRING COMMENT 'Operator-confirmed label',
    label_confidence DOUBLE COMMENT 'Labeler confidence (0.0-1.0)',
    labeled_by STRING COMMENT 'Operator/role identifier',
    labeled_at TIMESTAMP COMMENT 'Label timestamp',
    export_timestamp TIMESTAMP,
    feature_version STRING DEFAULT '1.0.0',
    window_duration_seconds INT,
    _imported_at TIMESTAMP DEFAULT current_timestamp()
)
USING DELTA
PARTITIONED BY (site_id, date(feature_window_start))
COMMENT 'Pre-computed training features imported from ClickHouse (Path B)'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true'
);

-- Silver: Quality trends (enriched quality events with rolling metrics)
CREATE TABLE IF NOT EXISTS manufacturing_poc.silver.quality_trends (
    site_id STRING NOT NULL,
    equipment_id STRING NOT NULL,
    date DATE NOT NULL,
    total_inspections BIGINT,
    pass_count BIGINT,
    fail_count BIGINT,
    pass_rate DOUBLE COMMENT 'pass_count / total_inspections',
    avg_confidence DOUBLE,
    top_defect_type STRING,
    top_defect_count BIGINT,
    _computed_at TIMESTAMP DEFAULT current_timestamp()
)
USING DELTA
PARTITIONED BY (site_id, date)
COMMENT 'Daily quality metrics per equipment — rolling trend analysis';

-- Silver: Equipment health (derived from sensor + anomaly events)
CREATE TABLE IF NOT EXISTS manufacturing_poc.silver.equipment_health (
    site_id STRING NOT NULL,
    equipment_id STRING NOT NULL,
    date DATE NOT NULL,
    total_sensor_events BIGINT,
    anomaly_count BIGINT,
    avg_anomaly_score DOUBLE,
    max_severity STRING,
    uptime_minutes DOUBLE,
    health_score DOUBLE COMMENT 'Composite score (0-100)',
    _computed_at TIMESTAMP DEFAULT current_timestamp()
)
USING DELTA
PARTITIONED BY (site_id, date)
COMMENT 'Daily equipment health derived from sensor data and anomaly events';

-- ============================================================
-- Step 5: Gold Tables
-- ============================================================

-- Gold: Training dataset (ML-ready, labeled, feature-enriched)
CREATE TABLE IF NOT EXISTS manufacturing_poc.gold.training_dataset (
    sample_id STRING NOT NULL,
    site_id STRING NOT NULL,
    equipment_id STRING NOT NULL,
    feature_window_start TIMESTAMP NOT NULL,
    feature_window_end TIMESTAMP NOT NULL,
    -- Features
    avg_value DOUBLE,
    min_value DOUBLE,
    max_value DOUBLE,
    stddev_value DOUBLE,
    count_readings BIGINT,
    p50_value DOUBLE,
    p95_value DOUBLE,
    p99_value DOUBLE,
    -- Image features (if available)
    image_path STRING,
    image_embedding ARRAY<DOUBLE> COMMENT 'Optional: pre-computed image embedding',
    -- Label
    label STRING NOT NULL COMMENT 'good | defect',
    defect_type STRING,
    -- Metadata
    dataset_version STRING DEFAULT '1.0.0',
    split STRING COMMENT 'train | validation | test',
    _created_at TIMESTAMP DEFAULT current_timestamp()
)
USING DELTA
PARTITIONED BY (split, site_id)
COMMENT 'ML-ready training dataset combining sensor features and quality labels';

-- Gold: Quality summary (executive dashboard)
CREATE TABLE IF NOT EXISTS manufacturing_poc.gold.quality_summary (
    site_id STRING NOT NULL,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    granularity STRING NOT NULL COMMENT 'daily | weekly | monthly',
    total_inspections BIGINT,
    pass_rate DOUBLE,
    defect_rate DOUBLE,
    top_defect_types ARRAY<STRING>,
    equipment_with_highest_defects STRING,
    avg_detection_confidence DOUBLE,
    _computed_at TIMESTAMP DEFAULT current_timestamp()
)
USING DELTA
PARTITIONED BY (granularity, site_id)
COMMENT 'Executive quality summary for dashboard consumption';

-- Gold: Predictive maintenance (model predictions)
CREATE TABLE IF NOT EXISTS manufacturing_poc.gold.predictive_maintenance (
    prediction_id STRING NOT NULL,
    site_id STRING NOT NULL,
    equipment_id STRING NOT NULL,
    prediction_timestamp TIMESTAMP NOT NULL,
    predicted_failure_window_start TIMESTAMP,
    predicted_failure_window_end TIMESTAMP,
    failure_probability DOUBLE COMMENT '0.0-1.0',
    recommended_action STRING,
    model_id STRING,
    model_version STRING,
    confidence_score DOUBLE,
    _created_at TIMESTAMP DEFAULT current_timestamp()
)
USING DELTA
PARTITIONED BY (site_id, date(prediction_timestamp))
COMMENT 'Predictive maintenance predictions from ML models';

-- ============================================================
-- Step 6: ML Schema
-- ============================================================

-- ML: Feature table for quality classifier
CREATE TABLE IF NOT EXISTS manufacturing_poc.ml.print_features (
    site_id STRING NOT NULL,
    equipment_id STRING NOT NULL,
    feature_timestamp TIMESTAMP NOT NULL,
    -- Sensor features (windowed)
    temp_avg DOUBLE,
    temp_max DOUBLE,
    humidity_avg DOUBLE,
    vibration_p95 DOUBLE,
    vibration_stddev DOUBLE,
    -- Derived features
    temp_humidity_ratio DOUBLE,
    sensor_reading_count BIGINT,
    anomaly_count_24h INT,
    -- Primary key for feature lookup
    lookup_key STRING GENERATED ALWAYS AS (concat(site_id, '-', equipment_id, '-', cast(feature_timestamp AS STRING)))
)
USING DELTA
COMMENT 'Feature table for quality prediction model (registered as Feature Store)'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.feature-store.enabled' = 'true'
);

-- ============================================================
-- Step 7: Cross-schema views
-- ============================================================

-- Latest payload manifest with verification status
CREATE VIEW IF NOT EXISTS manufacturing_poc.bronze.v_unverified_payloads AS
SELECT * FROM manufacturing_poc.bronze.payload_manifest
WHERE verified = false AND registered_at > current_timestamp() - INTERVAL 7 DAYS;

-- Latest equipment health
CREATE VIEW IF NOT EXISTS manufacturing_poc.gold.v_latest_equipment_health AS
SELECT * FROM manufacturing_poc.silver.equipment_health
WHERE date = current_date() - INTERVAL 1 DAY;
