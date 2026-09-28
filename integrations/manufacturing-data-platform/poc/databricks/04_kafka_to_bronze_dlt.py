# Databricks notebook source
# Manufacturing Data Platform PoC — Kafka → Bronze (DLT Pipeline)
#
# Integration Path A: Spark Structured Streaming via DLT
# Source: factory.events.raw (Kafka)
# Target: manufacturing_poc.bronze.kafka_events
#
# Synced from: ONTAP-Edge-to-Cloud-AI Databricks integration design
# Sync Date: 2026-06-15
#
# This Delta Live Tables pipeline provides:
#   - Declarative streaming from Kafka to Bronze
#   - Data quality expectations (schema validation)
#   - Auto-scaling and checkpoint management
#   - Schema evolution support
#
# Deploy as a DLT pipeline in Databricks Workflows.
# Required pipeline settings:
#   - Target: manufacturing_poc.bronze
#   - Catalog: manufacturing_poc (Unity Catalog mode)
#
# DAIS 2026 note: Real-Time Mode (RTM) for Spark Declarative Pipelines is now in
# Public Preview — end-to-end latency as low as 5ms (continuous processing, not
# microbatch). Evaluate RTM alongside the Lakehouse//RT comparison in Phase B.
# Current pipeline uses standard microbatch DLT for Phase A stability.
#   - Configuration:
#       kafka.bootstrap.servers = <MSK bootstrap>
#       kafka.security.protocol = SASL_SSL
#       kafka.sasl.mechanism = AWS_MSK_IAM

# COMMAND ----------

import dlt
from pyspark.sql.functions import (
    col,
    current_timestamp,
    from_json,
    to_timestamp,
    get_json_object,
    expr,
)
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    LongType,
    BooleanType,
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

KAFKA_BOOTSTRAP_SERVERS = spark.conf.get(
    "kafka.bootstrap.servers", "PLACEHOLDER:9098"
)

# Unified Event Envelope v2.0.0 schema
event_envelope_schema = StructType([
    StructField("event_id", StringType(), False),
    StructField("event_type", StringType(), False),
    StructField("domain", StringType(), True),
    StructField("event_category", StringType(), True),
    StructField("source_id", StringType(), False),
    StructField("asset_type", StringType(), True),
    StructField("asset_id", StringType(), True),
    StructField("site_id", StringType(), False),
    StructField("line_id", StringType(), True),
    StructField("equipment_id", StringType(), True),
    StructField("sensor_id", StringType(), True),
    StructField("timestamp", StringType(), False),
    StructField("ingest_time", StringType(), True),
    StructField("schema_version", StringType(), True),
    StructField("payload_uri", StringType(), True),
    StructField("payload_type", StringType(), True),
    StructField("content_type", StringType(), True),
    StructField("checksum", StringType(), True),
    StructField("size_bytes", LongType(), True),
    StructField("lineage_id", StringType(), True),
    StructField("processing_status", StringType(), True),
    StructField("metadata", StringType(), True),
    # Governance: top-level synthetic-data flag (aligned with ClickHouse
    # JSONExtractBool(raw, '_synthetic') and the unified event envelope)
    StructField("_synthetic", BooleanType(), True),
])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Bronze Layer: Raw Kafka Events

# COMMAND ----------

@dlt.table(
    name="kafka_events",
    comment="Raw Kafka events from factory.events.raw — unified event envelope v2.0.0",
    table_properties={
        "quality": "bronze",
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.autoOptimize.autoCompact": "true",
    },
    partition_cols=["event_type", "_event_date"],
)
@dlt.expect_or_drop("valid_event_id", "event_id IS NOT NULL AND length(event_id) = 36")
@dlt.expect_or_drop("valid_event_type", "event_type IS NOT NULL AND event_type != ''")
@dlt.expect_or_drop("valid_site_id", "site_id IS NOT NULL AND site_id != ''")
@dlt.expect_or_drop("valid_timestamp", "event_timestamp IS NOT NULL")
@dlt.expect("has_schema_version", "schema_version IS NOT NULL")
def kafka_events():
    """Ingest all events from factory.events.raw Kafka topic."""
    raw_stream = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
        .option("subscribe", "factory.events.raw")
        .option("kafka.security.protocol", "SASL_SSL")
        .option("kafka.sasl.mechanism", "AWS_MSK_IAM")
        .option(
            "kafka.sasl.jaas.config",
            "software.amazon.msk.auth.iam.IAMLoginModule required;",
        )
        .option(
            "kafka.sasl.client.callback.handler.class",
            "software.amazon.msk.auth.iam.IAMClientCallbackHandler",
        )
        .option("startingOffsets", "earliest")
        .option("maxOffsetsPerTrigger", "200000")
        .load()
    )

    parsed = (
        raw_stream
        .select(
            from_json(col("value").cast("string"), event_envelope_schema).alias("data"),
            col("topic").alias("_kafka_topic"),
            col("partition").alias("_kafka_partition"),
            col("offset").alias("_kafka_offset"),
        )
        .select("data.*", "_kafka_topic", "_kafka_partition", "_kafka_offset")
        .withColumn("event_timestamp", to_timestamp(col("timestamp")))
        .withColumn("ingest_time", to_timestamp(col("ingest_time")))
        .withColumn("_ingested_at", current_timestamp())
        .withColumn("_event_date", expr("date(event_timestamp)"))
        # Carry the top-level synthetic flag as a stable column (defaults to
        # false when absent, matching ClickHouse semantics)
        .withColumn("is_synthetic", expr("coalesce(_synthetic, false)"))
        .drop("timestamp", "_synthetic")
    )

    return parsed


# COMMAND ----------

# MAGIC %md
# MAGIC ## Bronze Layer: Sensor Events (extracted from raw)

# COMMAND ----------

@dlt.table(
    name="sensor_events",
    comment="Sensor readings extracted from kafka_events for time-series analysis",
    table_properties={
        "quality": "bronze",
        "delta.autoOptimize.optimizeWrite": "true",
    },
    partition_cols=["site_id", "_event_date"],
)
@dlt.expect_or_drop("valid_sensor_value", "value IS NOT NULL")
@dlt.expect_or_drop("valid_sensor_id", "sensor_id IS NOT NULL AND sensor_id != ''")
def sensor_events():
    """Extract sensor readings from kafka_events where event_type = 'sensor_event'."""
    return (
        dlt.read_stream("kafka_events")
        .filter(col("event_type") == "sensor_event")
        .select(
            col("event_id"),
            col("site_id"),
            col("equipment_id"),
            col("sensor_id"),
            col("event_timestamp"),
            get_json_object(col("metadata"), "$.sensor_type").alias("sensor_type"),
            get_json_object(col("metadata"), "$.value").cast("double").alias("value"),
            get_json_object(col("metadata"), "$.unit").alias("unit"),
            col("source_id"),
            col("lineage_id"),
            current_timestamp().alias("_ingested_at"),
            expr("date(event_timestamp)").alias("_event_date"),
        )
    )


# COMMAND ----------

# MAGIC %md
# MAGIC ## Bronze Layer: Quality Events

# COMMAND ----------

@dlt.table(
    name="quality_events",
    comment="Quality inspection and AI analysis results",
    table_properties={
        "quality": "bronze",
        "delta.autoOptimize.optimizeWrite": "true",
    },
    partition_cols=["site_id", "_event_date"],
)
@dlt.expect("has_processing_status", "processing_status IS NOT NULL")
def quality_events():
    """Extract quality events from kafka_events."""
    return (
        dlt.read_stream("kafka_events")
        .filter(col("event_type") == "quality_event")
        .select(
            col("event_id"),
            col("event_type"),
            col("event_category"),
            col("site_id"),
            col("line_id"),
            col("equipment_id"),
            col("sensor_id"),
            col("event_timestamp"),
            col("ingest_time"),
            col("payload_uri"),
            col("payload_type"),
            col("content_type"),
            col("checksum"),
            col("size_bytes"),
            col("processing_status"),
            get_json_object(col("metadata"), "$.classification_result").alias("classification_result"),
            get_json_object(col("metadata"), "$.confidence_score").cast("double").alias("confidence_score"),
            get_json_object(col("metadata"), "$.defect_type").alias("defect_type"),
            get_json_object(col("metadata"), "$.model_id").alias("model_id"),
            get_json_object(col("metadata"), "$.model_version").alias("model_version"),
            col("metadata"),
            current_timestamp().alias("_ingested_at"),
            expr("date(event_timestamp)").alias("_event_date"),
        )
    )


# COMMAND ----------

# MAGIC %md
# MAGIC ## Bronze Layer: Payload Manifest

# COMMAND ----------

@dlt.table(
    name="payload_manifest",
    comment="Registry linking ONTAP payload files to Kafka events",
    table_properties={
        "quality": "bronze",
        "delta.autoOptimize.optimizeWrite": "true",
    },
    partition_cols=["site_id", "_event_date"],
)
@dlt.expect_or_drop("has_payload_uri", "payload_uri IS NOT NULL AND payload_uri != ''")
def payload_manifest():
    """Extract payload arrival events to build ONTAP ↔ event linkage."""
    return (
        dlt.read_stream("kafka_events")
        .filter(
            (col("event_type") == "payload_arrival")
            & (col("payload_uri").isNotNull())
            & (col("payload_uri") != "")
        )
        .select(
            col("payload_uri"),
            col("event_id"),
            col("site_id"),
            col("equipment_id"),
            col("asset_id"),
            col("payload_type"),
            col("content_type"),
            col("checksum"),
            col("size_bytes"),
            expr("'nfs'").alias("storage_protocol"),
            col("lineage_id"),
            col("event_timestamp").alias("registered_at"),
            expr("false").alias("verified"),
            expr("CAST(NULL AS TIMESTAMP)").alias("verified_at"),
            current_timestamp().alias("_ingested_at"),
            expr("date(event_timestamp)").alias("_event_date"),
        )
    )


# COMMAND ----------

# MAGIC %md
# MAGIC ## Bronze Layer: Feedback Events (human ground-truth labels)

# COMMAND ----------

@dlt.table(
    name="feedback_events",
    comment="Human feedback / ground-truth labels for AI accuracy and training",
    table_properties={
        "quality": "bronze",
        "delta.autoOptimize.optimizeWrite": "true",
    },
    partition_cols=["site_id", "_event_date"],
)
@dlt.expect_or_drop("has_target_event", "target_event_id IS NOT NULL AND target_event_id != ''")
@dlt.expect_or_drop("has_human_label", "human_label IS NOT NULL AND human_label != ''")
def feedback_events():
    """Extract feedback events (event_type = 'feedback_event') from kafka_events.

    Feedback originates from: operator → feedback_recorder Lambda
    → Kafka (feedback_event) → this DLT route → bronze.feedback_events.
    """
    return (
        dlt.read_stream("kafka_events")
        .filter(col("event_type") == "feedback_event")
        .select(
            col("event_id"),
            get_json_object(col("metadata"), "$.target_event_id").alias("target_event_id"),
            col("site_id"),
            col("equipment_id"),
            col("asset_id"),
            col("event_timestamp"),
            col("ingest_time"),
            get_json_object(col("metadata"), "$.human_label").alias("human_label"),
            get_json_object(col("metadata"), "$.label_confidence").cast("double").alias("label_confidence"),
            get_json_object(col("metadata"), "$.defect_type").alias("defect_type"),
            get_json_object(col("metadata"), "$.labeled_by").alias("labeled_by"),
            to_timestamp(get_json_object(col("metadata"), "$.labeled_at")).alias("labeled_at"),
            get_json_object(col("metadata"), "$.correction_reason").alias("correction_reason"),
            get_json_object(col("metadata"), "$.original_ai_label").alias("original_ai_label"),
            # Governance: synthetic flag carried from the top-level envelope
            # (aligned with ClickHouse top-level JSONExtractBool(raw, '_synthetic'))
            col("is_synthetic"),
            col("metadata"),
            current_timestamp().alias("_ingested_at"),
            expr("date(event_timestamp)").alias("_event_date"),
        )
    )
