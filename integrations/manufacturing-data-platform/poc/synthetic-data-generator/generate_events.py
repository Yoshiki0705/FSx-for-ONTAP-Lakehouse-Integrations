#!/usr/bin/env python3
"""
Synthetic Factory Event Generator — Kafka Producer

Generates realistic manufacturing events and publishes them to Kafka topics.
Supports: sensor readings, quality inspections, equipment status.

Architecture Reference: ADR-001 (Kafka as factory event backbone)
Schema Reference: DES-004 (Message Schema)

All data is SYNTHETIC. No real factory, device, or measurement data is used.
"""

import argparse
import hashlib
import json
import logging
import os
import random
import time
import uuid
from datetime import datetime, UTC
from typing import Any

# confluent_kafka is imported lazily (only when actually producing to Kafka)
# This allows --dry-run to work without the dependency installed.

# ---------------------------------------------------------------------------
# Configuration (environment variables with defaults for local development)
# ---------------------------------------------------------------------------

KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_SECURITY_PROTOCOL = os.environ.get("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
KAFKA_SASL_MECHANISM = os.environ.get("KAFKA_SASL_MECHANISM", "")
KAFKA_SASL_USERNAME = os.environ.get("KAFKA_SASL_USERNAME", "")
KAFKA_SASL_PASSWORD = os.environ.get("KAFKA_SASL_PASSWORD", "")

# FSx for ONTAP payload base path (for generating payload_uri references)
PAYLOAD_BASE_URI = os.environ.get(
    "PAYLOAD_BASE_URI", "nfs://svm1.fsxn.local/vol_images"
)

# Topic names (matching DES-003)
TOPIC_SENSOR_DATA = os.environ.get("TOPIC_SENSOR_DATA", "factory.sensor-data")
TOPIC_QUALITY_EVENTS = os.environ.get("TOPIC_QUALITY_EVENTS", "factory.quality-events")
TOPIC_SYSTEM_ALERTS = os.environ.get("TOPIC_SYSTEM_ALERTS", "factory.system-alerts")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Synthetic Data Definitions (SYNTHETIC — not real factory data)
# ---------------------------------------------------------------------------

FACTORIES = ["factory-alpha", "factory-beta"]
LINES = {
    "factory-alpha": ["line-A1", "line-A2", "line-A3"],
    "factory-beta": ["line-B1", "line-B2"],
}
SENSOR_TYPES = ["temperature", "humidity", "pressure", "vibration"]
SENSOR_UNITS = {
    "temperature": "celsius",
    "humidity": "percent",
    "pressure": "kPa",
    "vibration": "mm/s",
}
SENSOR_RANGES = {
    "temperature": (15.0, 85.0),
    "humidity": (20.0, 95.0),
    "pressure": (90.0, 115.0),
    "vibration": (0.1, 12.0),
}
EQUIPMENT_STATES = ["running", "stopped", "maintenance", "warming_up"]
QUALITY_EVENT_TYPES = ["INSPECTION", "MEASUREMENT", "DEFECT", "PASS"]


def generate_device_ids(factory: str, line: str, count: int = 5) -> list[str]:
    """Generate synthetic device IDs for a given factory and line."""
    return [f"{factory}-{line}-sensor-{i:03d}" for i in range(1, count + 1)]


# ---------------------------------------------------------------------------
# Event Generators
# ---------------------------------------------------------------------------


def generate_sensor_event(
    factory_id: str, line_id: str, device_id: str
) -> dict[str, Any]:
    """Generate a synthetic sensor reading event."""
    sensor_type = random.choice(SENSOR_TYPES)
    low, high = SENSOR_RANGES[sensor_type]
    value = round(random.uniform(low, high), 3)

    return {
        "event_id": str(uuid.uuid4()),
        "timestamp": int(datetime.now(UTC).timestamp() * 1000),
        "factory_id": factory_id,
        "device_id": device_id,
        "line_id": line_id,
        "event_type": "SENSOR_READING",
        "sensor_type": sensor_type,
        "value": value,
        "unit": SENSOR_UNITS[sensor_type],
        "payload_reference": None,
        "content_type": None,
        "payload_size_bytes": None,
        "checksum_sha256": None,
    }


def generate_quality_event(
    factory_id: str, line_id: str, device_id: str
) -> dict[str, Any]:
    """Generate a synthetic quality inspection event with payload reference."""
    event_type = random.choice(QUALITY_EVENT_TYPES)
    pass_fail = event_type in ("PASS", "INSPECTION")
    measurement_value = (
        round(random.uniform(0.01, 100.0), 4) if event_type == "MEASUREMENT" else None
    )

    # Simulate a payload reference (image from quality camera)
    has_payload = random.random() < 0.7  # 70% of quality events have images
    payload_ref = None
    content_type = None
    payload_size = None
    checksum = None

    if has_payload:
        ts_path = datetime.now(UTC).strftime("%Y/%m/%d")
        filename = f"quality_{uuid.uuid4().hex[:12]}.jpg"
        payload_ref = f"{PAYLOAD_BASE_URI}/{factory_id}/{line_id}/{ts_path}/{filename}"
        content_type = "image/jpeg"
        payload_size = random.randint(5_000_000, 50_000_000)  # 5-50 MB
        # Synthetic checksum (not a real file hash)
        checksum = hashlib.sha256(payload_ref.encode()).hexdigest()

    return {
        "event_id": str(uuid.uuid4()),
        "timestamp": int(datetime.now(UTC).timestamp() * 1000),
        "factory_id": factory_id,
        "device_id": device_id,
        "line_id": line_id,
        "event_type": event_type,
        "measurement_value": measurement_value,
        "pass_fail": pass_fail,
        "payload_reference": payload_ref,
        "content_type": content_type,
        "payload_size_bytes": payload_size,
        "checksum_sha256": checksum,
    }


def generate_status_event(
    factory_id: str, line_id: str, device_id: str
) -> dict[str, Any]:
    """Generate a synthetic equipment status event."""
    return {
        "event_id": str(uuid.uuid4()),
        "timestamp": int(datetime.now(UTC).timestamp() * 1000),
        "factory_id": factory_id,
        "device_id": device_id,
        "line_id": line_id,
        "event_type": "EQUIPMENT_STATUS",
        "equipment_state": random.choice(EQUIPMENT_STATES),
        "payload_reference": None,
        "content_type": None,
        "payload_size_bytes": None,
        "checksum_sha256": None,
    }


# ---------------------------------------------------------------------------
# Kafka Producer Setup
# ---------------------------------------------------------------------------


def resolve_msk_region(bootstrap_servers: str) -> str:
    """Return the AWS Region for MSK IAM signing.

    AWS_REGION / AWS_DEFAULT_REGION win. Otherwise the Region is the label just before
    ``amazonaws.com`` in the first bootstrap host, for example
    ``b-1.<cluster>.<id>.c2.kafka.ap-northeast-1.amazonaws.com:9098``.
    """
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if region:
        return region
    host = bootstrap_servers.split(",")[0].split(":")[0].strip().lower()
    labels = host.split(".")
    if len(labels) >= 3 and labels[-2:] == ["amazonaws", "com"]:
        return labels[-3]
    msg = (
        "Cannot determine the AWS Region for MSK IAM auth from "
        f"KAFKA_BOOTSTRAP_SERVERS={bootstrap_servers!r}; set AWS_REGION."
    )
    raise ValueError(msg)


def create_producer_config() -> dict[str, str]:
    """Build Kafka producer configuration from environment variables."""
    config = {
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "client.id": "synthetic-factory-generator",
        "acks": "all",
        "retries": 3,
        "retry.backoff.ms": "500",
    }

    if KAFKA_SECURITY_PROTOCOL != "PLAINTEXT":
        config["security.protocol"] = KAFKA_SECURITY_PROTOCOL

    if KAFKA_SASL_MECHANISM:
        config["sasl.mechanism"] = KAFKA_SASL_MECHANISM
        if KAFKA_SASL_MECHANISM == "AWS_MSK_IAM":
            # MSK IAM auth using OAUTHBEARER with aws-msk-iam-sasl-signer.
            # Do not set sasl.oauthbearer.method=oidc: that method requires
            # sasl.oauthbearer.token.endpoint.url and fails when the client is created.
            # With the default method, librdkafka calls oauth_cb for the token.
            config["sasl.mechanism"] = "OAUTHBEARER"
            # The token provider callback handles IAM signing
            try:
                from aws_msk_iam_sasl_signer import MSKAuthTokenProvider

                region = resolve_msk_region(KAFKA_BOOTSTRAP_SERVERS)

                def oauth_cb(config_str):
                    # The signer returns (token, expiry in epoch milliseconds);
                    # oauth_cb expects the expiry in epoch seconds.
                    auth_token, expiry_ms = MSKAuthTokenProvider.generate_auth_token(
                        region
                    )
                    return auth_token, expiry_ms / 1000

                config["oauth_cb"] = oauth_cb
            except ImportError:
                logger.warning(
                    "aws-msk-iam-sasl-signer not installed. "
                    "Install with: pip install aws-msk-iam-sasl-signer-python"
                )
                raise
        else:
            config["sasl.username"] = KAFKA_SASL_USERNAME
            config["sasl.password"] = KAFKA_SASL_PASSWORD

    return config


def delivery_callback(err, msg):
    """Callback for Kafka produce delivery reports."""
    if err is not None:
        logger.error(f"Delivery failed: {err}")
    else:
        logger.debug(f"Delivered to {msg.topic()} [{msg.partition()}] @ {msg.offset()}")


def ensure_topics(config: dict[str, str], topics: list[str], num_partitions: int = 6):
    """Create Kafka topics if they don't exist (best-effort)."""
    from confluent_kafka.admin import AdminClient, NewTopic

    try:
        admin = AdminClient(config)
        new_topics = [
            NewTopic(topic, num_partitions=num_partitions, replication_factor=1)
            for topic in topics
        ]
        futures = admin.create_topics(new_topics)
        for topic, future in futures.items():
            try:
                future.result()
                logger.info(f"Created topic: {topic}")
            except Exception as e:
                # Topic may already exist
                logger.debug(f"Topic {topic} creation note: {e}")
    except Exception as e:
        logger.warning(f"Could not create topics (may already exist): {e}")


# ---------------------------------------------------------------------------
# Main Generator Loop
# ---------------------------------------------------------------------------


def run_generator(
    events_per_second: int = 100,
    duration_seconds: int = 60,
    num_devices_per_line: int = 5,
):
    """Run the synthetic event generator."""
    logger.info("Starting synthetic event generator")
    logger.info(f"  Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"  Rate: {events_per_second} events/sec")
    logger.info(f"  Duration: {duration_seconds} seconds")
    logger.info(f"  Devices per line: {num_devices_per_line}")

    # Build device inventory
    all_devices = []
    for factory in FACTORIES:
        for line in LINES[factory]:
            devices = generate_device_ids(factory, line, num_devices_per_line)
            for device in devices:
                all_devices.append((factory, line, device))

    logger.info(f"  Total devices: {len(all_devices)}")

    # Setup Kafka producer
    producer_config = create_producer_config()
    topics = [TOPIC_SENSOR_DATA, TOPIC_QUALITY_EVENTS, TOPIC_SYSTEM_ALERTS]
    ensure_topics(producer_config, topics)

    from confluent_kafka import Producer

    producer = Producer(producer_config)

    # Event generation weights
    # 70% sensor, 20% quality, 10% status
    event_weights = [0.70, 0.90, 1.00]

    interval = 1.0 / events_per_second
    total_events = 0
    start_time = time.time()

    try:
        while (time.time() - start_time) < duration_seconds:
            loop_start = time.time()

            factory, line, device = random.choice(all_devices)
            roll = random.random()

            if roll < event_weights[0]:
                event = generate_sensor_event(factory, line, device)
                topic = TOPIC_SENSOR_DATA
                key = device
            elif roll < event_weights[1]:
                event = generate_quality_event(factory, line, device)
                topic = TOPIC_QUALITY_EVENTS
                key = line
            else:
                event = generate_status_event(factory, line, device)
                topic = TOPIC_SYSTEM_ALERTS
                key = f"{factory}-{line}"

            producer.produce(
                topic=topic,
                key=key.encode("utf-8"),
                value=json.dumps(event).encode("utf-8"),
                callback=delivery_callback,
            )
            total_events += 1

            # Periodic flush and progress logging
            if total_events % 1000 == 0:
                producer.flush()
                elapsed = time.time() - start_time
                rate = total_events / elapsed
                logger.info(
                    f"  Progress: {total_events} events sent "
                    f"({rate:.1f} events/sec, {elapsed:.1f}s elapsed)"
                )

            # Rate limiting
            elapsed_this_loop = time.time() - loop_start
            sleep_time = interval - elapsed_this_loop
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        logger.info("Generator interrupted by user")
    finally:
        producer.flush()
        elapsed = time.time() - start_time
        rate = total_events / elapsed if elapsed > 0 else 0
        logger.info(
            f"Generator complete: {total_events} events in {elapsed:.1f}s "
            f"({rate:.1f} events/sec)"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Synthetic Factory Event Generator (Kafka Producer)"
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=100,
        help="Events per second (default: 100)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--devices",
        type=int,
        default=5,
        help="Number of devices per production line (default: 5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print events to stdout instead of sending to Kafka",
    )

    args = parser.parse_args()

    if args.dry_run:
        logger.info("DRY RUN mode — printing events to stdout")
        factory = FACTORIES[0]
        line = LINES[factory][0]
        device = generate_device_ids(factory, line, 1)[0]

        print("\n--- Sample Sensor Event ---")
        print(json.dumps(generate_sensor_event(factory, line, device), indent=2))
        print("\n--- Sample Quality Event (with payload) ---")
        print(json.dumps(generate_quality_event(factory, line, device), indent=2))
        print("\n--- Sample Status Event ---")
        print(json.dumps(generate_status_event(factory, line, device), indent=2))
        return

    run_generator(
        events_per_second=args.rate,
        duration_seconds=args.duration,
        num_devices_per_line=args.devices,
    )


if __name__ == "__main__":
    main()
