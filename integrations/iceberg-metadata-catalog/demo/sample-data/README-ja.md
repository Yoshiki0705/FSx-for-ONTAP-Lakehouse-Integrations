# 業界別サンプルデータ

🌐 日本語 | [English](README.md)

## 概要

業界別デモ用のサンプルデータリファレンスと生成スクリプト。各業界のデータセットは、メタデータカタログの価値をその業界の非構造化データで実証する。

## 業界別データセット

### 製造業

| データタイプ | ソース | ライセンス | サイズ | デモ用途 |
|------------|--------|----------|------|---------|
| CAD ファイル (STEP/STL) | [GrabCAD Community](https://grabcad.com/library) | CC-BY / Free | 可変 | 設計図面の類似検索 |
| エンジニアリング図面 (PDF) | [NASA Technical Reports](https://ntrs.nasa.gov/) | Public Domain | 1-50MB | ドキュメント分類 |
| 製品画像 | [MVTec Anomaly Detection](https://www.mvtec.com/company/research/datasets/mvtec-ad) | CC-BY-NC-SA 4.0 | 4.9GB | 品質検査 AI |
| IoT センサーデータ | [NASA Turbofan Engine](https://data.nasa.gov/Aerospace/CMAPSS-Jet-Engine-Simulated-Data/ff5v-kuh6) | Public Domain | 26MB | 予知保全 |

### 金融

| データタイプ | ソース | ライセンス | サイズ | デモ用途 |
|------------|--------|----------|------|---------|
| 請求書画像 | [SROIE Dataset](https://rrc.cvc.uab.es/?ch=13) | Research | 36MB | 請求書分類 + OCR |
| ドキュメント画像 | [RVL-CDIP](https://huggingface.co/datasets/rvl_cdip) | Research | 38GB | ドキュメントタイプ分類 |
| 財務報告書 (PDF) | [SEC EDGAR](https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany) | Public Domain | 可変 | コンプライアンス検索 |
| 契約書サンプル | [CUAD Dataset](https://www.atticusprojectai.org/cuad) | CC-BY-4.0 | 80MB | 契約条項抽出 |

### 医療

| データタイプ | ソース | ライセンス | サイズ | デモ用途 |
|------------|--------|----------|------|---------|
| 医療画像 (DICOM) | [NIH Chest X-rays](https://nihcc.app.box.com/v/ChestXray-NIHCC) | CC0 1.0 | 42GB | DICOM 匿名化デモ |
| 医療画像 (DICOM) | [TCIA Collections](https://www.cancerimagingarchive.net/) | Various (CC-BY) | 可変 | 医療画像分類 |
| 臨床ドキュメント | [MIMIC-III Clinical Notes](https://physionet.org/content/mimiciii/) | PhysioNet License | 6GB | 医療テキスト PII 検出 |
| 病理画像 | [Camelyon16](https://camelyon16.grand-challenge.org/) | CC0 1.0 | 700GB | 全スライド画像分析 |

### メディア

| データタイプ | ソース | ライセンス | サイズ | デモ用途 |
|------------|--------|----------|------|---------|
| 画像（多様） | [Open Images V7](https://storage.googleapis.com/openimages/web/index.html) | CC-BY-4.0 | 561GB | 画像分類 + タグ付け |
| 動画クリップ | [Kinetics-700](https://www.deepmind.com/open-source/kinetics) | CC-BY-4.0 | 大規模 | 動画シーン分類 |
| 音声録音 | [Common Voice](https://commonvoice.mozilla.org/) | CC0 | 90GB+ | 音声文字起こし |
| ストック写真 | [Unsplash Dataset](https://unsplash.com/data) | Unsplash License | 25GB | 写真類似検索 |

### 公共セクター

| データタイプ | ソース | ライセンス | サイズ | デモ用途 |
|------------|--------|----------|------|---------|
| 衛星画像 | [Sentinel-2 on AWS](https://registry.opendata.aws/sentinel-2/) | Copernicus | PB規模 | 地理空間分類 |
| 政府文書 | [US Government Publishing Office](https://www.govinfo.gov/) | Public Domain | 可変 | ドキュメント検索 + PII |
| 国勢調査データ | [US Census Bureau](https://data.census.gov/) | Public Domain | 可変 | 人口統計分析 |
| 気象データ | [NOAA NEXRAD on AWS](https://registry.opendata.aws/noaa-nexrad/) | Public Domain | 270TB | センサーデータパターン |

### エネルギー/ユーティリティ

| データタイプ | ソース | ライセンス | サイズ | デモ用途 |
|------------|--------|----------|------|---------|
| 風力タービンデータ | [Engie Open Data](https://opendata-renewables.engie.com/) | Open License | 可変 | 予知保全 |
| 電力グリッドログ | [Pecan Street Dataport](https://www.pecanstreet.org/dataport/) | Research | 可変 | 異常検知 |
| 地震データ | [SEG Open Data](https://wiki.seg.org/wiki/Open_data) | Various | 可変 | 地下構造分析 |
| ソーラーパネル画像 | [DeepSolar](https://web.stanford.edu/group/deepsolar/) | Research | 130万画像 | アセット検査 |

## プラットフォーム別サンプルデータ

### Databricks

| データセット | ソース | 用途 |
|-----------|--------|------|
| Databricks サンプルデータ | 組み込み (`/databricks-datasets/`) | クイックスタート |
| Delta Sharing サンプル | [delta.io/sharing](https://delta.io/sharing/) | 組織横断共有デモ |
| MLflow 実験データ | 組み込み | ML ライフサイクルデモ |
| Unity Catalog サンプル | 組み込み (`samples` カタログ) | ガバナンスデモ |

### Snowflake

| データセット | ソース | 用途 |
|-----------|--------|------|
| Snowflake サンプルデータ | 組み込み (`SNOWFLAKE_SAMPLE_DATA`) | クイックスタート |
| Snowflake Marketplace | [marketplace.snowflake.com](https://app.snowflake.com/marketplace) | 業界データ |
| Cortex AI サンプル | 組み込み | AI 機能デモ |
| Weather Source | Marketplace (無料) | 時系列デモ |

### AWS

| データセット | ソース | 用途 |
|-----------|--------|------|
| Registry of Open Data | [registry.opendata.aws](https://registry.opendata.aws/) | 全業界 |
| AWS Data Exchange | [aws.amazon.com/data-exchange](https://aws.amazon.com/data-exchange/) | 商用データ |
| SageMaker サンプルノートブック | 組み込み | ML デモ |
| Bedrock Knowledge Base サンプル | ドキュメント | RAG デモ |

## クイックセットアップ: デモデータ生成

```bash
# 業界別サンプルファイル生成
python generate-sample-data.py \
  --industry manufacturing \
  --output-dir /tmp/demo-data \
  --file-count 50

# FSx for ONTAP S3 AP にアップロード
aws s3 sync /tmp/demo-data/ s3://<AP_ALIAS>/demo-data/ --region ap-northeast-1
```

## ライセンスに関する注意

- 参照データセットは全てオープンまたは研究ライセンス
- 利用者向けデモで使用する前にライセンス条件を確認すること
- 利用者環境での PoC: 利用者自身のデータを使用（最も説得力がある）
- 社内デモ: CC0/Public Domain データセットのみ使用
