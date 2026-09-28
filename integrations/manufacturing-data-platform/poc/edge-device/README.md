# Edge Device Setup — Raspberry Pi Gateway

🌐 **English** | [日本語](README-ja.md)

---

> Edge gateway for manufacturing data platform.
> Implements ADR-008 (3-tier buffering: MQTT → SQLite → Kafka idempotent producer).
>
> This device connects to the separate edge project:
> https://github.com/Yoshiki0705/ONTAP-Edge-to-Cloud-AI

---

## Hardware Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Board | Raspberry Pi 4B (4GB) | Raspberry Pi 5 (8GB) |
| Storage | 32 GB SD card | 128 GB USB SSD |
| Network | Ethernet (factory LAN) | Ethernet + WiFi (backup) |
| Power | USB-C 5V/3A | UPS-backed supply |

---

## Software Stack

```
┌─────────────────────────────────────────────────────────┐
│  Raspberry Pi OS (64-bit, Lite)                         │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Mosquitto MQTT Broker (local)                   │   │
│  │  - QoS 2 persistence                            │   │
│  │  - Receives sensor/PLC data on port 1883        │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Edge Gateway Service (Python systemd)           │   │
│  │  - MQTT subscriber                              │   │
│  │  - SQLite store-and-forward queue               │   │
│  │  - Kafka idempotent producer                    │   │
│  │  - Payload upload worker (NFS)                  │   │
│  │  - Health/heartbeat reporter                    │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  NFS mount: /mnt/ontap/vol_images               │   │
│  │  (on-prem ONTAP via factory LAN)                │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Installation

### 1. OS Setup

```bash
# Flash Raspberry Pi OS Lite (64-bit) to SD/SSD
# Enable SSH, set hostname, configure network

# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y \
  python3 python3-pip python3-venv \
  mosquitto mosquitto-clients \
  nfs-common \
  sqlite3 \
  jq
```

### 2. Mosquitto MQTT Broker

```bash
# Configure Mosquitto for local persistence
sudo tee /etc/mosquitto/conf.d/factory.conf << 'EOF'
listener 1883
allow_anonymous true
persistence true
persistence_location /var/lib/mosquitto/
max_queued_messages 100000
max_inflight_messages 1000
EOF

sudo systemctl enable mosquitto
sudo systemctl restart mosquitto
```

### 3. NFS Mount (to on-prem ONTAP)

```bash
# Create mount point
sudo mkdir -p /mnt/ontap/vol_images

# Add to fstab (replace with actual NFS LIF IP)
echo "<ONPREM_NFS_LIF>:/vol_images /mnt/ontap/vol_images nfs defaults,soft,timeo=150,retrans=3 0 0" \
  | sudo tee -a /etc/fstab

# Mount
sudo mount -a

# Verify
df -h /mnt/ontap/vol_images
```

### 4. Edge Gateway Service

```bash
# Create application directory
sudo mkdir -p /opt/edge-gateway
sudo mkdir -p /var/lib/edge-gateway

# Create virtual environment
python3 -m venv /opt/edge-gateway/.venv
source /opt/edge-gateway/.venv/bin/activate

# Install dependencies
pip install \
  confluent-kafka==2.6.1 \
  paho-mqtt==2.1.0 \
  Pillow==11.1.0

# Copy edge gateway code (from this repo or ONTAP-Edge-to-Cloud-AI)
# cp edge_gateway.py /opt/edge-gateway/
# cp config.yaml /opt/edge-gateway/
```

### 5. Configuration

```yaml
# /opt/edge-gateway/config.yaml
edge:
  device_id: "factory-alpha-gateway-001"
  factory_id: "factory-alpha"

mqtt:
  host: localhost
  port: 1883
  topics:
    - "sensors/#"
    - "quality/#"
    - "status/#"

store_and_forward:
  db_path: /var/lib/edge-gateway/queue.db
  max_size_bytes: 10737418240  # 10 GB

kafka:
  bootstrap_servers: "<INSTACLUSTR_BOOTSTRAP_SERVERS>"
  security_protocol: SASL_SSL
  sasl_mechanism: SCRAM-SHA-512
  sasl_username: "<KAFKA_USERNAME>"
  sasl_password: "<KAFKA_PASSWORD>"
  enable_idempotence: true
  acks: all
  retries: 2147483647
  delivery_timeout_ms: 3600000
  compression_type: lz4
  batch_size: 65536
  linger_ms: 100

payload:
  upload_dir: /mnt/ontap/vol_images
  max_retries: 10
  retry_backoff_initial_ms: 1000
  retry_backoff_max_ms: 60000
  dead_letter_dir: /var/lib/edge-gateway/dead-letter

monitoring:
  heartbeat_topic: "factory.system-alerts"
  heartbeat_interval_seconds: 60
  metrics_port: 9090  # Prometheus scrape endpoint (optional)
```

### 6. Systemd Service

```bash
sudo tee /etc/systemd/system/edge-gateway.service << 'EOF'
[Unit]
Description=Manufacturing Edge Gateway
After=network-online.target mosquitto.service
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/opt/edge-gateway
ExecStart=/opt/edge-gateway/.venv/bin/python edge_gateway.py --config /opt/edge-gateway/config.yaml
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Resource limits
MemoryMax=512M
CPUQuota=80%

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable edge-gateway
sudo systemctl start edge-gateway
```

### 7. Verification

```bash
# Check service status
sudo systemctl status edge-gateway

# Check logs
journalctl -u edge-gateway -f

# Check MQTT
mosquitto_sub -h localhost -t "sensors/#" -v &

# Check store-and-forward queue
sqlite3 /var/lib/edge-gateway/queue.db "SELECT count(*) FROM events WHERE status='pending';"

# Check Kafka delivery
# (from a machine with kafka-console-consumer):
kafka-console-consumer.sh --bootstrap-server <KAFKA_BOOTSTRAP> \
  --topic factory.sensor-data --from-beginning --max-messages 5
```

---

## Integration with ONTAP-Edge-to-Cloud-AI

The [ONTAP-Edge-to-Cloud-AI](https://github.com/Yoshiki0705/ONTAP-Edge-to-Cloud-AI) project provides:
- Sensor simulation on Raspberry Pi GPIO
- Camera integration for quality inspection
- MQTT publisher for sensor data

This project provides:
- MQTT → Kafka bridge (store-and-forward)
- Payload upload to ONTAP (NFS)
- Configuration for Instaclustr Kafka

### Integration Point

```
ONTAP-Edge-to-Cloud-AI         this project
(sensor/camera → MQTT)   →   (MQTT → SQLite → Kafka + NFS upload)
```

The API contract between the two projects:
- MQTT topic: `sensors/<device_id>/<sensor_type>`
- MQTT payload: JSON matching the schema in `config/environment.yaml`
- Payload files: written to `/tmp/payloads/` by edge-to-cloud-ai, uploaded by this project's gateway

---

## Failure Modes and Recovery

| Failure | Behavior | Recovery |
|---------|----------|---------|
| Kafka unreachable | Events queue in SQLite (up to 10 GB) | Auto-drain when connectivity returns |
| NFS mount lost | Payload uploads fail → dead-letter | Reconnect NFS; retry dead-letter files |
| Raspberry Pi reboot | systemd restarts gateway; SQLite queue persists | Automatic |
| SD card corruption | Service fails to start | Replace SD; queue data lost (accept) |
| Factory power outage | All services stop | Auto-start on power restore; some in-flight data may be lost |

---

## Confidentiality Note

All device IDs, factory names, and configuration values in this document are **synthetic placeholders**. Replace with actual values during deployment. Never commit real credentials to version control.
