# Synthetic Data Generator

🌐 **English** | [日本語](README-ja.md)

---

## Overview

Generates synthetic manufacturing events and payloads for the manufacturing data platform PoC. All data is **SYNTHETIC** — no real factory, device, or measurement data is used.

### Components

| Script | Purpose | Output |
|--------|---------|--------|
| `generate_events.py` | Kafka producer — publishes structured events | Kafka messages |
| `generate_payloads.py` | Generates and uploads synthetic files (images, PDFs) | Files on FSx for ONTAP |

## Prerequisites

- Python 3.12+
- Access to a Kafka cluster (Amazon MSK or local)
- Access to FSx for ONTAP (NFS mount or ONTAP S3 endpoint)

## Installation

```bash
cd integrations/manufacturing-data-platform/poc/synthetic-data-generator
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Event Generator Usage

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka bootstrap servers |
| `KAFKA_SECURITY_PROTOCOL` | `PLAINTEXT` | `PLAINTEXT`, `SASL_SSL`, `SSL` |
| `KAFKA_SASL_MECHANISM` | (empty) | `SCRAM-SHA-256`, `SCRAM-SHA-512`, `AWS_MSK_IAM` |
| `KAFKA_SASL_USERNAME` | (empty) | SASL username |
| `KAFKA_SASL_PASSWORD` | (empty) | SASL password |
| `AWS_REGION` | (derived from the bootstrap host) | Region used to sign MSK IAM tokens (`AWS_MSK_IAM`). Takes precedence over the host name; `AWS_DEFAULT_REGION` is the fallback |
| `PAYLOAD_BASE_URI` | `nfs://svm1.fsxn.local/vol_images` | Base URI for payload references |

### Commands

```bash
# Dry run — print sample events to stdout
python generate_events.py --dry-run

# Generate 100 events/sec for 60 seconds
python generate_events.py --rate 100 --duration 60

# Generate with more devices
python generate_events.py --rate 500 --duration 120 --devices 10

# Use with Amazon MSK (IAM auth)
export KAFKA_BOOTSTRAP_SERVERS="b-1.msk-cluster.xxxxx.kafka.ap-northeast-1.amazonaws.com:9098"
export KAFKA_SECURITY_PROTOCOL="SASL_SSL"
export KAFKA_SASL_MECHANISM="AWS_MSK_IAM"
python generate_events.py --rate 100 --duration 300
```

### Event Types

| Type | Topic | Description | Payload |
|------|-------|-------------|---------|
| SENSOR_READING | `factory.sensor-data` | Temperature, humidity, pressure, vibration | None |
| INSPECTION/MEASUREMENT/DEFECT/PASS | `factory.quality-events` | Quality inspection results | 70% have image reference |
| EQUIPMENT_STATUS | `factory.system-alerts` | Running, stopped, maintenance | None |

### Message Schema

```json
{
  "event_id": "uuid",
  "timestamp": 1717776000000,
  "factory_id": "factory-alpha",
  "device_id": "factory-alpha-line-A1-sensor-001",
  "line_id": "line-A1",
  "event_type": "SENSOR_READING",
  "sensor_type": "temperature",
  "value": 42.5,
  "unit": "celsius",
  "payload_reference": null,
  "content_type": null,
  "payload_size_bytes": null,
  "checksum_sha256": null
}
```

## Payload Generator Usage

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STORAGE_MODE` | `nfs` | `nfs` or `s3` |
| `NFS_MOUNT_PATH` | `/mnt/fsxn/vol_images` | Local NFS mount point |
| `ONTAP_S3_ENDPOINT` | `https://svm1-s3.fsxn.local` | ONTAP S3 endpoint URL |
| `ONTAP_S3_BUCKET` | `factory-payloads` | ONTAP S3 bucket name |
| `ONTAP_S3_ACCESS_KEY` | (empty) | ONTAP S3 access key |
| `ONTAP_S3_SECRET_KEY` | (empty) | ONTAP S3 secret key |

### Commands

```bash
# Dry run — generate one sample image locally
python generate_payloads.py --dry-run

# Generate 10 payloads via NFS mount
export STORAGE_MODE=nfs
export NFS_MOUNT_PATH=/mnt/fsxn/vol_images
python generate_payloads.py --count 10

# Generate 50 payloads via ONTAP S3
export STORAGE_MODE=s3
export ONTAP_S3_ENDPOINT="https://<svm-management-ip>:443"
export ONTAP_S3_ACCESS_KEY="<access-key>"
export ONTAP_S3_SECRET_KEY="<secret-key>"
python generate_payloads.py --count 50 --manifest payloads.json
```

### Output Manifest

The payload generator produces a JSON manifest file listing all uploaded files:

```json
[
  {
    "uri": "nfs://svm1.fsxn.local/vol_images/factory-alpha/line-A1/2026/06/07/quality_abc123.jpg",
    "size_bytes": 15728640,
    "checksum_sha256": "a1b2c3d4...",
    "content_type": "image/jpeg"
  }
]
```

## Architecture References

- [ADR-001](../../docs/adr/ADR-001.md) — Kafka as factory event backbone
- [ADR-003](../../docs/adr/ADR-003.md) — FSx for ONTAP as payload storage
- [ADR-005](../../docs/adr/ADR-005.md) — Metadata/payload separation
- [DES-003](../../docs/en/03_architecture_design.md#des-003-kafka-topic-design) — Kafka topic design
- [DES-004](../../docs/en/03_architecture_design.md#des-004-message-schema-avrojson-schema) — Message schema

## Confidentiality Note

All generated data is **synthetic**. Factory names (`factory-alpha`, `factory-beta`), line names, device IDs, and measurement values are randomly generated and do not represent any real manufacturing environment.
