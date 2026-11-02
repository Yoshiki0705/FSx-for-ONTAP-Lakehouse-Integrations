# 合成データジェネレーター

🌐 [English](README.md) | **日本語**

---

## 概要

製造データプラットフォーム PoC 用の合成製造イベントとペイロードを生成する。全データは**合成データ**であり、実際の工場、デバイス、測定データは使用しない。

### コンポーネント

| スクリプト | 目的 | 出力 |
|----------|------|------|
| `generate_events.py` | Kafka プロデューサー — 構造化イベントを発行 | Kafka メッセージ |
| `generate_payloads.py` | 合成ファイル（画像、PDF）を生成・アップロード | FSx for ONTAP 上のファイル |

## 前提条件

- Python 3.12+
- Kafka クラスターへのアクセス（Amazon MSK またはローカル）
- FSx for ONTAP へのアクセス（NFS マウントまたは ONTAP S3 エンドポイント）

## インストール

```bash
cd integrations/manufacturing-data-platform/poc/synthetic-data-generator
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## イベントジェネレーター使用方法

### 環境変数

| 変数 | デフォルト | 説明 |
|------|---------|------|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka ブートストラップサーバー |
| `KAFKA_SECURITY_PROTOCOL` | `PLAINTEXT` | `PLAINTEXT`, `SASL_SSL`, `SSL` |
| `KAFKA_SASL_MECHANISM` | (空) | `SCRAM-SHA-256`, `SCRAM-SHA-512`, `AWS_MSK_IAM` |
| `KAFKA_SASL_USERNAME` | (空) | SASL ユーザー名 |
| `KAFKA_SASL_PASSWORD` | (空) | SASL パスワード |
| `AWS_REGION` | (bootstrap ホスト名から導出) | MSK IAM トークンの署名に使うリージョン（`AWS_MSK_IAM`）。ホスト名より優先される。`AWS_DEFAULT_REGION` が次の候補 |
| `PAYLOAD_BASE_URI` | `nfs://svm1.fsxn.local/vol_images` | ペイロード参照のベース URI |

### コマンド

```bash
# ドライラン — サンプルイベントを stdout に表示
python generate_events.py --dry-run

# 100 イベント/秒で 60 秒間生成
python generate_events.py --rate 100 --duration 60

# より多くのデバイスで生成
python generate_events.py --rate 500 --duration 120 --devices 10

# Amazon MSK で使用（IAM 認証）
export KAFKA_BOOTSTRAP_SERVERS="b-1.msk-cluster.xxxxx.kafka.ap-northeast-1.amazonaws.com:9098"
export KAFKA_SECURITY_PROTOCOL="SASL_SSL"
export KAFKA_SASL_MECHANISM="AWS_MSK_IAM"
python generate_events.py --rate 100 --duration 300
```

### イベントタイプ

| タイプ | トピック | 説明 | ペイロード |
|--------|---------|------|---------|
| SENSOR_READING | `factory.sensor-data` | 温度、湿度、圧力、振動 | なし |
| INSPECTION/MEASUREMENT/DEFECT/PASS | `factory.quality-events` | 品質検査結果 | 70% が画像参照あり |
| EQUIPMENT_STATUS | `factory.system-alerts` | 稼働中、停止、メンテナンス | なし |

### メッセージスキーマ

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

## ペイロードジェネレーター使用方法

### 環境変数

| 変数 | デフォルト | 説明 |
|------|---------|------|
| `STORAGE_MODE` | `nfs` | `nfs` または `s3` |
| `NFS_MOUNT_PATH` | `/mnt/fsxn/vol_images` | ローカル NFS マウントポイント |
| `ONTAP_S3_ENDPOINT` | `https://svm1-s3.fsxn.local` | ONTAP S3 エンドポイント URL |
| `ONTAP_S3_BUCKET` | `factory-payloads` | ONTAP S3 バケット名 |
| `ONTAP_S3_ACCESS_KEY` | (空) | ONTAP S3 アクセスキー |
| `ONTAP_S3_SECRET_KEY` | (空) | ONTAP S3 シークレットキー |

### コマンド

```bash
# ドライラン — サンプル画像を1枚ローカル生成
python generate_payloads.py --dry-run

# NFS マウント経由で 10 ペイロード生成
export STORAGE_MODE=nfs
export NFS_MOUNT_PATH=/mnt/fsxn/vol_images
python generate_payloads.py --count 10

# ONTAP S3 経由で 50 ペイロード生成
export STORAGE_MODE=s3
export ONTAP_S3_ENDPOINT="https://<svm-management-ip>:443"
export ONTAP_S3_ACCESS_KEY="<access-key>"
export ONTAP_S3_SECRET_KEY="<secret-key>"
python generate_payloads.py --count 50 --manifest payloads.json
```

## アーキテクチャ参照

- [ADR-001](../../docs/adr/ADR-001.md) — Kafka を工場イベントバックボーンとして使用
- [ADR-003](../../docs/adr/ADR-003.md) — FSx for ONTAP をペイロードストレージとして使用
- [ADR-005](../../docs/adr/ADR-005.md) — メタデータ/ペイロード分離
- [DES-003](../../docs/ja/03_architecture_design.md) — Kafka トピック設計
- [DES-004](../../docs/ja/03_architecture_design.md) — メッセージスキーマ

## 機密性に関する注記

生成される全データは**合成データ**です。工場名（`factory-alpha`、`factory-beta`）、ライン名、デバイス ID、測定値はランダム生成であり、実際の製造環境を表すものではありません。
