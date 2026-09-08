🌐 **English** | [日本語](../ja/delta-sharing-volume-guide.md)

# OpenSharing & Volume Sharing Integration Guide

> **Status**: Architecture Reference — Pattern A/B ready for PoC, Pattern C blocked (awaiting Databricks UC feature development)
>
> **Context**: This guide documents how to expose FSx for ONTAP data to Databricks Unity Catalog governance using OpenSharing (formerly Delta Sharing), given that direct UC External Location integration with FSx S3 Access Points is [not currently supported](../../README.md#where-the-denial-originates).

## Executive Summary

OpenSharing is a **sharing protocol**, not a transformation engine. It does not convert arbitrary NAS files (images, videos, PDFs) into queryable tables on the fly. Instead, it exposes **prepared tabular datasets** to recipients across organizations, clouds, and platforms.

For FSx for ONTAP integration with Databricks, OpenSharing provides a practical sharing layer when:
- Databricks acts as a **recipient** rather than the direct storage owner
- Data is first transformed into Delta or Parquet tables
- Unity Catalog Volumes are used for governed non-tabular file access

### Key Principles

1. **OpenSharing = sharing protocol** (not a transformation engine)
2. **FSx for ONTAP S3 Access Points provide object access** — OpenSharing requires table semantics
3. **For unstructured data**: The shareable asset is the derived structured representation (metadata, extracted text, captions, embeddings)
4. **For true zero-copy raw file access**: Unity Catalog must support FSx for ONTAP S3 AP as first-class storage locations (feature gap — [reported to Databricks engineering](../../README.md#where-the-denial-originates))

### Quick Start: What Should I Do Today?

| Your situation | Recommended action | Pattern |
|---|---|---|
| **Databricks customer needing governed analytics on NAS data** | DataSync → S3 → UC External Location → Delta Tables | DataSync path (validated) |
| **Need to share file metadata with Databricks users** | Lambda + ListObjectsV2 → Delta Table → OpenSharing | Pattern A |
| **Need AI/RAG on NAS documents in Databricks** | Textract/Bedrock → Delta Table → OpenSharing | Pattern B |
| **Need to browse raw files (images/videos/PDFs) in Databricks** | DataSync → S3 → UC External Volume → Volume Sharing | Pattern C (with S3 sync) |
| **Want zero-copy direct access (no S3 bucket)** | Not available today — awaiting Databricks UC feature development | Pattern C (blocked) |
2. **FSx for ONTAP S3 Access Points provide object access** — OpenSharing requires table semantics
3. **For unstructured data**: The shareable asset is the derived structured representation (metadata, extracted text, captions, embeddings)
4. **For true zero-copy raw file access**: Unity Catalog must support FSx for ONTAP S3 AP as first-class storage locations (feature gap — [reported to Databricks engineering](../../README.md#where-the-denial-originates))

---

## Three Integration Patterns

### Pattern A: Metadata Table Sharing (Recommended First PoC)

Share a **file catalog** — not the raw files themselves — through OpenSharing.

```
FSx for ONTAP
  ↓ S3 Access Point (ListObjectsV2)
AWS Lambda / Glue / Step Functions
  ↓ file inventory extraction
Parquet or Delta metadata table (on S3)
  ↓
OpenSharing (UC Share or OSS Server)
  ↓
Databricks recipient
```

**Shared table schema example:**

| Column | Type | Description |
|--------|------|-------------|
| `file_id` | STRING | Unique identifier |
| `path` | STRING | S3 AP path |
| `s3_ap_key` | STRING | Object key within access point |
| `size_bytes` | BIGINT | File size |
| `last_modified` | TIMESTAMP | Last modification time |
| `etag` | STRING | S3 ETag |
| `file_extension` | STRING | e.g., `.pdf`, `.jpg`, `.parquet` |
| `mime_type` | STRING | MIME type |
| `classification` | STRING | Data classification label |
| `scan_timestamp` | TIMESTAMP | When inventory was taken |

**AWS services used:**
- FSx for ONTAP S3 Access Points — file access via S3 API
- AWS Lambda — small-scale PoC (ListObjectsV2 → metadata extraction)
- AWS Step Functions — batch processing with retry logic
- AWS Glue — ETL to Parquet/Delta, catalog management
- Amazon S3 — metadata table storage (recommended over FSx for ONTAP S3 AP for OpenSharing compatibility)

**PoC success criteria:** Databricks can query a OpenSharing table that represents FSx for ONTAP file metadata.

**ONTAP value in this pattern**: Snapshots enable instant point-in-time file inventory recovery. If a metadata scan produces incorrect results, revert to a previous Snapshot and re-scan — no data loss, no re-upload.

**Production readiness checklist (Pattern A):**
- [ ] Data freshness SLA defined (e.g., metadata table updated every N minutes/hours)
- [ ] Failure handling: Lambda DLQ, Step Functions retry with exponential backoff
- [ ] Monitoring: CloudWatch metrics for Lambda errors, invocation count, duration
- [ ] Cost model: Lambda invocations × file count × schedule frequency
- [ ] Schema evolution: How are new file types or metadata fields handled?
- [ ] Access control: Who can query the shared metadata table? (OpenSharing recipient permissions)
- [ ] Operational runbook: What to do when metadata table is stale or Lambda fails

---

### Pattern B: AI-Enriched Table Sharing (RAG / Search / Analytics)

Process unstructured data with AI services, then share the **derived structured output** through OpenSharing.

```
FSx for ONTAP (raw files: PDFs, images, audio, video)
  ↓ S3 Access Point (GetObject)
AWS AI Services (Textract, Rekognition, Transcribe, Bedrock)
  ↓ extracted text / captions / transcripts / embeddings
Parquet or Delta tables (on S3)
  ↓
OpenSharing
  ↓
Databricks recipient (Mosaic AI, Vector Search, MLflow)
```

**Shared table schemas by data type:**

#### Documents (PDF/DOCX) — RAG Pipeline

| Column | Type | Description |
|--------|------|-------------|
| `document_id` | STRING | Unique document ID |
| `source_path` | STRING | FSx for ONTAP S3 AP path |
| `page_number` | INT | Page within document |
| `chunk_id` | STRING | Text chunk identifier |
| `text` | STRING | Extracted text content |
| `summary` | STRING | AI-generated summary |
| `embedding` | ARRAY<FLOAT> | Vector embedding |
| `classification` | STRING | Document classification |
| `created_at` | TIMESTAMP | Processing timestamp |

#### Images — Visual Search

| Column | Type | Description |
|--------|------|-------------|
| `image_id` | STRING | Unique image ID |
| `source_path` | STRING | FSx for ONTAP S3 AP path |
| `mime_type` | STRING | image/jpeg, image/png, etc. |
| `width` | INT | Image width (px) |
| `height` | INT | Image height (px) |
| `detected_labels` | ARRAY<STRING> | Object detection results |
| `caption` | STRING | AI-generated description |
| `embedding` | ARRAY<FLOAT> | Visual embedding |
| `created_at` | TIMESTAMP | Processing timestamp |

#### Video/Audio — Transcription & Analysis

| Column | Type | Description |
|--------|------|-------------|
| `video_id` | STRING | Unique video/audio ID |
| `source_path` | STRING | FSx for ONTAP S3 AP path |
| `start_time_sec` | FLOAT | Segment start time |
| `end_time_sec` | FLOAT | Segment end time |
| `transcript` | STRING | Transcribed text |
| `detected_objects` | ARRAY<STRING> | Objects in frame |
| `scene_summary` | STRING | AI scene description |
| `embedding` | ARRAY<FLOAT> | Segment embedding |
| `created_at` | TIMESTAMP | Processing timestamp |

**AWS AI services by data type:**

| Data Type | Primary Service | Secondary | Output |
|-----------|----------------|-----------|--------|
| PDF/Documents | Amazon Textract | Amazon Bedrock (summarize, embed) | Text, tables, forms, summaries |
| Images | Amazon Rekognition | Bedrock multimodal (caption) | Labels, objects, faces, captions |
| Audio | Amazon Transcribe | Bedrock (summarize) | Transcripts, speaker IDs |
| Video | Rekognition Video | Transcribe + Bedrock | Labels, scenes, transcripts |

**PoC success criteria:** Databricks can query AI-enriched metadata (extracted text, labels, summaries, embeddings) through OpenSharing.

**ONTAP value in this pattern**: FlexClone enables instant zero-copy dataset provisioning for AI processing — clone a volume for Textract/Rekognition processing without impacting production NFS/SMB workloads. Storage Efficiency (dedup + compression) reduces the cost of maintaining both source files and AI-derived tables.

**Production readiness checklist (Pattern B):**
- [ ] AI processing pipeline SLA: End-to-end latency from file creation to searchable embedding
- [ ] Quality gates: Embedding quality validation, OCR accuracy thresholds, hallucination detection
- [ ] Cost model: Textract/Rekognition/Transcribe per-page/per-minute pricing × volume × frequency
- [ ] Failure handling: Partial processing (some files fail OCR), retry logic, poison message handling
- [ ] Data lineage: Track which source file produced which embedding/summary (for audit and reprocessing)
- [ ] Incremental processing: Only process new/modified files (avoid full reprocessing on each run)
- [ ] Monitoring: Processing success rate, embedding drift detection, pipeline lag metrics
- [ ] Security: Ensure AI services do not retain customer data; validate data residency for regulated content

---

### Pattern C: Raw File Sharing via UC Volumes (Requires Databricks Enhancement)

The ideal zero-copy architecture — but currently blocked by UC session policy limitations.

**Desired architecture:**
```
FSx for ONTAP
  ↓ S3 Access Point
Databricks UC External Location (direct)
  ↓
UC External Volume
  ↓
OpenSharing (Volume Sharing)
  ↓
Databricks recipient (read_files, ai_query, ai_parse_document)
```

**Current reality (requires S3 copy):**
```
FSx for ONTAP
  ↓ DataSync
Amazon S3 bucket (standard)
  ↓
Databricks UC External Location
  ↓
UC External Volume
  ↓
OpenSharing (Volume Sharing)
  ↓
Databricks recipient
```

**Production design for DataSync → S3 → UC path:**

This is the **fully supported, production-ready path** for Databricks + FSx for ONTAP today. It provides full Unity Catalog governance, Delta Lake ACID, Mosaic AI, and Feature Store capabilities.

| Component | Design Decision | Rationale |
|-----------|----------------|-----------|
| Sync mechanism | AWS DataSync (validated) | Scheduled sync from FSx for ONTAP NFS to S3 bucket. Supports incremental transfer. |
| S3 bucket design | `s3://fsxn-lakehouse-<env>/raw/`, `/bronze/`, `/silver/`, `/gold/` | Medallion architecture for progressive refinement |
| UC Catalog structure | `fsxn_lakehouse.raw.*`, `fsxn_lakehouse.curated.*` | Separate raw ingestion from governed consumption |
| Delta Table design | Managed Tables (UC controls lifecycle) | Enables OPTIMIZE, VACUUM, Time Travel, Z-ORDER |
| Ingestion | Auto Loader (Directory Listing mode on S3 bucket) | Incremental, exactly-once, schema evolution |
| Governance | UC Tags + Row Access Policies + Column Masks | Full enterprise governance on synced data |
| AI/ML | Mosaic AI, Feature Store, MLflow on Delta Tables | Full platform capabilities available |
| Cost | FSx storage + S3 storage + Databricks compute | Accept duplication cost for full platform value |

**End-to-end data freshness model:**

| Sync Pattern | DataSync Schedule | Auto Loader Detection | UC Table Available | Total Lag |
|---|---|---|---|---|
| DataSync (5 min schedule) + Auto Loader (5 min poll) | 5 min | 5 min | <1 min | **~10 min max** |
| DataSync (1 min schedule) + Auto Loader (1 min poll) | 1 min | 1 min | <1 min | **~2-3 min max** |
| FPolicy → Lambda → S3 + Auto Loader (File Notification) | Real-time | Seconds (SQS) | <1 min | **~30 sec** |
| DataSync (hourly schedule) + Auto Loader (5 min poll) | 60 min | 5 min | <1 min | **~65 min max** |

> **For manufacturing use cases**: "How long until factory floor images appear in Databricks?" — With DataSync 5-min schedule + Auto Loader 5-min polling, the answer is "within 10 minutes." For near-real-time requirements (<1 min), use FPolicy → Lambda → S3 path.

**Representative cost estimate (DataSync → S3 → UC path):**

| Component | 1 TB dataset | 10 TB dataset | Notes |
|-----------|---|---|---|
| DataSync transfer | ~$0.04/GB (first copy), incremental after | ~$0.40/GB first, incremental | Pay-per-GB transferred; incremental syncs transfer only changes |
| S3 Standard storage | ~$23/month | ~$230/month | Stores synced copy of FSx for ONTAP data |
| Auto Loader (Jobs compute) | ~$5-10/month | ~$15-30/month | Few minutes/day of job cluster |
| Delta Table overhead | ~$2-5/month | ~$10-20/month | Metadata, transaction logs, versions |
| **Total additional cost** | **~$30-40/month** | **~$260-280/month** | Beyond existing FSx for ONTAP cost |

> This is the cost of "full Databricks platform capabilities" (ACID, Time Travel, Mosaic AI, governance). Compare with zero-copy paths (Athena, Snowflake External Table) which add $0 storage cost but lack these capabilities.

> **Key insight for Databricks customers**: The DataSync → S3 → UC path is not a workaround — it is the **production architecture this repository recommends**, on the measurements below. It provides capabilities that zero-copy paths cannot: ACID transactions, Time Travel, MERGE, OPTIMIZE, full Mosaic AI, and enterprise governance. The trade-off is data duplication and sync latency.

> **ONTAP value in this pattern**: FabricPool automatically tiers cold data on FSx for ONTAP to S3 (transparent to NFS/SMB users), reducing storage costs. Snapshots provide point-in-time consistency for DataSync transfers — sync from a Snapshot to ensure a consistent view of the data.

> **Note on SnapMirror S3**: NetApp ONTAP documentation describes SnapMirror S3 (ONTAP S3 bucket → AWS S3 replication) as available from ONTAP 9.10.1+. However, **this feature is disabled on FSx for ONTAP** (verified May 2026, ONTAP 9.17.1P6). The `snapmirror object-store` CLI commands and `/api/cloud/targets` REST API are blocked as a managed service restriction. AWS DataSync remains the only validated sync path. Feature request submitted to AWS.

**What works today (with S3 copy):**

```sql
-- Provider side: Create External Volume on S3 (synced from FSx for ONTAP)
CREATE EXTERNAL VOLUME media_files
  LOCATION 's3://fsxn-synced-bucket/unstructured-data/'
  COMMENT 'Images, videos, PDFs synced from FSx for ONTAP';

-- Add Volume to Share
CREATE SHARE IF NOT EXISTS unstructured_data_share
  COMMENT 'Document and media files for partners';

ALTER SHARE unstructured_data_share
  ADD VOLUME catalog.schema.media_files;

-- Grant to recipient
GRANT SELECT ON SHARE unstructured_data_share
  TO RECIPIENT <partner_org>;
```

```sql
-- Recipient side: Access shared files
CREATE CATALOG IF NOT EXISTS shared_media
  FROM SHARE <provider_name>.unstructured_data_share;

-- Query file metadata
SELECT * EXCEPT (content), _metadata
FROM read_files(
  '/Volumes/shared_media/schema/media_files/',
  format => 'binaryFile'
) LIMIT 10;

-- AI analysis on shared images
SELECT path,
  ai_query('databricks-llama-4-maverick',
    'Describe this image:', files => content)
FROM read_files(
  '/Volumes/shared_media/schema/media_files/',
  format => 'binaryFile',
  fileNamePattern => '*.{jpg,png}')
WHERE _metadata.file_size < 5000000;

-- Parse shared PDFs
SELECT path,
  ai_parse_document(content, map('version', '2.0'))
FROM read_files(
  '/Volumes/shared_media/schema/media_files/',
  format => 'binaryFile',
  fileNamePattern => '*.pdf');
```

**Feature requests to Databricks (reported May 2026):**

1. Support S3 Access Point ARNs as first-class storage locations in UC External Locations
2. Update UC session policy generation for FSx for ONTAP S3 AP ARN patterns
3. Allow UC Volumes to use FSx for ONTAP S3 AP as backend storage
4. Generalize UC storage abstractions beyond standard S3 buckets
5. Clarify whether Databricks-to-Databricks Volume Sharing can work with non-bucket S3 AP backends

**PoC success criteria:** Databricks confirms required UC enhancements or provides an alternative supported design for zero-copy FSx for ONTAP access.

---

## Pattern Comparison

| Dimension | Pattern A | Pattern B | Pattern C |
|-----------|-----------|-----------|-----------|
| **Shared asset** | File metadata table | AI-processed tables | Raw files (via UC Volume) |
| **Data on FSx for ONTAP** | Remains (not shared directly) | Remains (derivatives shared) | Remains (accessed directly) |
| **S3 copy required** | Metadata only (~KB) | Derived tables (~MB-GB) | Full file sync (~GB-TB) |
| **PoC complexity** | Low | Medium | Blocked (requires Databricks UC feature development) |
| **Governance** | OpenSharing + UC | OpenSharing + UC | UC Volume ACL |
| **AI/ML readiness** | Catalog only | Full (embeddings, RAG) | Full (read_files + ai_query) |
| **Real-time freshness** | Polling-based | Pipeline-dependent | Near real-time (if supported) |
| **Snowflake co-access** | ✅ Same curated Iceberg on S3 | ✅ Shared via open format | ❌ UC Volume is Databricks-only |
| **Best for** | File discovery, audit | RAG, search, analytics | Direct file processing |

> **Open Table Format as shared data layer**: Patterns A and B produce Delta/Parquet tables on S3. These same tables can be registered as Snowflake External Iceberg Tables or AWS Glue Data Catalog tables — enabling multi-engine access to the same curated dataset without additional copies. This is the "common data surface" that avoids vendor lock-in while preserving each platform's governance and AI capabilities.

---

## Unstructured Data: How Raw Files Appear in Unity Catalog

### The Key Question: Can images, videos, and PDFs be used "as-is"?

**Yes — through UC Volumes.** Unity Catalog Volumes store files in their original format. Files are NOT converted to Parquet or Delta. A JPEG remains a JPEG, a PDF remains a PDF.

Reference: [What are Unity Catalog volumes?](https://docs.databricks.com/aws/en/volumes/managed-vs-external) — "Volumes govern non-tabular data of any format, including structured, semi-structured, or unstructured."

### Supported Unstructured File Formats in UC Volumes

| Category | File Formats | AI Processing Available | Use Case |
|----------|---|---|---|
| **Images** | JPEG, PNG, GIF, BMP, TIFF, WebP, SVG, HEIC, RAW (CR2, NEF, ARW) | `ai_query()` (vision), `ai_parse_document()` | Image classification, quality inspection, OCR |
| **Documents** | PDF, DOCX, DOC, XLSX, XLS, PPTX, PPT, ODT, ODS, ODP, RTF, TXT, MD | `ai_parse_document()`, `ai_query()` | Text extraction, summarization, RAG |
| **Video** | MP4, MOV, AVI, MKV, WebM, FLV, WMV, MPEG, 3GP | Custom UDF (frame extraction) | Video analytics, scene detection |
| **Audio** | WAV, MP3, FLAC, AAC, OGG, WMA, M4A, AIFF | Custom UDF (transcription) | Speech-to-text, speaker diarization |
| **CAD/Engineering** | DWG, DXF, STEP, STL, IGES, OBJ, FBX, GLTF | Custom UDF | Manufacturing, 3D analysis |
| **Medical/Scientific** | DICOM, NIfTI, HDF5, FITS, NetCDF | Custom UDF | Medical imaging, scientific data |
| **Geospatial** | GeoTIFF, Shapefile (.shp), GeoJSON, KML, GPX, LAS/LAZ (LiDAR) | Custom UDF | Mapping, terrain analysis |
| **Archives** | ZIP, TAR, GZ, 7Z, RAR, BZIP2 | Extract → process contents | Batch processing |
| **Logs/Config** | JSON, YAML, XML, CSV, TSV, LOG, INI, TOML | `read_files()` directly | Log analysis, config management |
| **Code/Scripts** | PY, JS, TS, Java, C, CPP, SQL, SH, Notebook (.ipynb) | `ai_query()` for code analysis | Code review, documentation |
| **Email** | EML, MSG, MBOX, PST | Custom UDF | E-discovery, compliance |
| **Fonts/Design** | TTF, OTF, WOFF, PSD, AI, INDD, SKETCH, FIG | Custom UDF | Asset management |

### Three Ways Unstructured Data Appears in Databricks

#### Method 1: UC Volume (files remain in original format)

```
Unity Catalog
  └── Catalog: enterprise_data
       └── Schema: raw_media
            └── Volume: fsxn_files (External Volume on S3)
                 ├── images/
                 │    ├── product_photo_001.jpg     ← Original JPEG (2.3 MB)
                 │    ├── xray_scan_042.dicom       ← Original DICOM (15 MB)
                 │    └── floor_plan.dwg            ← Original CAD (8 MB)
                 ├── videos/
                 │    ├── security_cam_2026-05-26.mp4  ← Original MP4 (1.2 GB)
                 │    └── training_session.webm     ← Original WebM (450 MB)
                 ├── documents/
                 │    ├── contract_v3.pdf           ← Original PDF (340 KB)
                 │    ├── financial_report.xlsx     ← Original Excel (2.1 MB)
                 │    └── meeting_notes.docx        ← Original Word (89 KB)
                 ├── audio/
                 │    ├── customer_call_001.wav     ← Original WAV (45 MB)
                 │    └── podcast_ep12.mp3          ← Original MP3 (62 MB)
                 └── scientific/
                      ├── brain_mri.nii.gz          ← Original NIfTI (120 MB)
                      └── sensor_data.hdf5          ← Original HDF5 (3.4 GB)
```

**What UC sees**: File paths, sizes, modification times. Files are governed by Volume-level permissions.

**What users can do**:
```sql
-- List all files
SELECT * FROM DIRECTORY('/Volumes/enterprise_data/raw_media/fsxn_files/');

-- Read file content as binary
SELECT path, content FROM read_files(
  '/Volumes/enterprise_data/raw_media/fsxn_files/documents/',
  format => 'binaryFile'
);

-- AI analysis on images (vision model)
SELECT path,
  ai_query('databricks-llama-4-maverick',
    'Describe this image in detail:', files => content) AS description
FROM read_files(
  '/Volumes/enterprise_data/raw_media/fsxn_files/images/',
  format => 'binaryFile',
  fileNamePattern => '*.{jpg,jpeg,png}')
WHERE _metadata.file_size < 10000000;

-- Parse PDF documents
SELECT path,
  ai_parse_document(content, map('version', '2.0')) AS parsed
FROM read_files(
  '/Volumes/enterprise_data/raw_media/fsxn_files/documents/',
  format => 'binaryFile',
  fileNamePattern => '*.pdf');
```

Reference: [Work with unstructured data in volumes](https://docs.databricks.com/aws/en/volumes/unstructured-data-tutorial)

#### Method 2: Delta Table with binaryFile (file content embedded in Parquet)

```sql
CREATE TABLE image_embeddings AS
SELECT
  path,
  _metadata.file_name,
  _metadata.file_size,
  _metadata.file_modification_time,
  content  -- Original file bytes stored as BINARY column in Parquet
FROM read_files(
  '/Volumes/enterprise_data/raw_media/fsxn_files/images/',
  format => 'binaryFile'
);
```

**What happens to the original file**:
- The file's binary content is **copied into a Parquet file** as a BINARY column
- The original file still exists in the Volume (not deleted)
- The Delta Table contains a **copy** of the bytes, not a reference
- File is no longer in its original format inside the table — it's a byte array in Parquet

**When to use**: When you need ACID, Time Travel, or OpenSharing on the file content itself.

#### Method 3: Metadata-only table (file stays in original location)

```sql
CREATE TABLE file_catalog AS
SELECT
  path,
  _metadata.file_name AS file_name,
  _metadata.file_size AS size_bytes,
  _metadata.file_modification_time AS last_modified,
  SPLIT_PART(_metadata.file_name, '.', -1) AS extension
FROM read_files(
  '/Volumes/enterprise_data/raw_media/fsxn_files/',
  format => 'binaryFile'
);
```

**What happens to the original file**: Nothing — it stays exactly where it is. The table only contains metadata (path, size, timestamp). To access the actual file content, you use the `path` column to read from the Volume.

### Comparison: What Happens to the Original File?

| Method | Original file format preserved? | Where does the file live? | UC governance level | OpenSharing compatible? |
|--------|:---:|---|---|---|
| **UC Volume** | ✅ Yes (JPEG stays JPEG) | Volume storage (S3 bucket) | Volume-level (READ/WRITE VOLUME) | ✅ Volume Sharing |
| **Delta Table (binaryFile)** | ❌ No (bytes in Parquet) | Delta Table (Parquet files) | Table-level (SELECT, column masks) | ✅ Table Sharing |
| **Metadata-only table** | ✅ Yes (file untouched) | Original location (Volume/Stage) | Table-level (metadata) + Volume-level (file access) | ⚠️ Metadata only shared |

### FSx for ONTAP S3 AP: Current Status for Each Method

| Method | FSx for ONTAP S3 AP directly? | With S3 sync? | Notes |
|--------|:---:|:---:|---|
| UC Volume (External) | ❌ Blocked | ✅ Works | Requires DataSync → S3 → External Volume |
| UC Volume (Managed) | N/A | ✅ Works | Copy files to Managed Volume |
| Delta Table (binaryFile) | ❌ Blocked | ✅ Works | Read from synced Volume, write to Delta Table |
| Metadata-only table | ✅ Possible (Pattern A) | ✅ Works | ListObjectsV2 on FSx for ONTAP S3 AP → metadata table |

### Key Takeaway

**UC Volumes are the "zero-transformation" path for unstructured data** — files remain in their original format, governed by UC, and accessible via SQL (`read_files`), Python (`dbutils.fs`), and AI functions (`ai_query`, `ai_parse_document`).

The blocker for FSx for ONTAP is not the file format — it's that **UC cannot register FSx for ONTAP S3 AP as a storage location**. Once that is resolved (Databricks feature development), files on FSx for ONTAP could be accessed directly through UC Volumes without any format conversion.

### Rendering & Viewing Unstructured Files in Databricks

**Can users actually view images, play videos, listen to audio, and read PDFs within Databricks?**

#### UC Volume path (original files — recommended for governed file browsing)

Files in UC Volumes are accessed by path and can be rendered directly in notebooks:

```python
# === Images (JPEG, PNG, TIFF, DICOM, etc.) ===
from IPython.display import display, Image

# Display a single image from Volume
display(Image(filename="/Volumes/catalog/schema/media/images/inspection_001.jpg"))

# Display multiple images as a gallery
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

fig, axes = plt.subplots(1, 3, figsize=(15, 5))
for i, img_path in enumerate([
    "/Volumes/catalog/schema/media/images/assembly_line_cam01.jpg",
    "/Volumes/catalog/schema/media/images/quality_check_042.png",
    "/Volumes/catalog/schema/media/images/weld_inspection.tiff"
]):
    axes[i].imshow(mpimg.imread(img_path))
    axes[i].set_title(img_path.split("/")[-1])
plt.show()
```

```python
# === PDFs and Documents ===
from IPython.display import display, IFrame, HTML

# Render PDF inline (via presigned URL or direct path)
display(IFrame(src="/Volumes/catalog/schema/media/documents/safety_manual.pdf",
               width=800, height=600))

# Extract text from PDF using AI
df = spark.sql("""
  SELECT path,
    ai_parse_document(content, map('version', '2.0')) AS parsed_text
  FROM read_files(
    '/Volumes/catalog/schema/media/documents/',
    format => 'binaryFile',
    fileNamePattern => '*.pdf')
""")
display(df)
```

```python
# === Audio (WAV, MP3, FLAC, etc.) ===
from IPython.display import display, Audio

# Play audio file directly from Volume
display(Audio(filename="/Volumes/catalog/schema/media/audio/customer_call_001.wav"))
display(Audio(filename="/Volumes/catalog/schema/media/audio/machine_vibration.mp3"))
```

```python
# === Video (MP4, WebM, MOV, etc.) ===
from IPython.display import display, Video

# Play video from Volume
display(Video(filename="/Volumes/catalog/schema/media/videos/assembly_process.mp4",
              embed=True, width=640))

# For large videos, use HTML5 video tag with Volume path
from IPython.display import HTML
display(HTML('''
  <video width="640" controls>
    <source src="/Volumes/catalog/schema/media/videos/robot_arm_cycle.webm"
            type="video/webm">
  </video>
'''))
```

```python
# === 3D/CAD files (STL, OBJ, GLTF) ===
import trimesh

# Load and visualize 3D model
mesh = trimesh.load("/Volumes/catalog/schema/media/cad/part_assembly.stl")
mesh.show()  # Opens 3D viewer in notebook
```

```python
# === Medical imaging (DICOM) ===
import pydicom
import matplotlib.pyplot as plt

# Load and display DICOM image
ds = pydicom.dcmread("/Volumes/catalog/schema/media/medical/chest_xray.dcm")
plt.imshow(ds.pixel_array, cmap='gray')
plt.title(f"Patient: {ds.PatientName}, Study: {ds.StudyDescription}")
plt.show()
```

Reference: [Work with files in Unity Catalog volumes](https://docs.databricks.com/aws/en/volumes/volume-files) — "You can use standard Python, Scala, or R libraries to read and write files in volumes."

Reference: [Work with unstructured data in volumes](https://docs.databricks.com/aws/en/volumes/unstructured-data-tutorial) — Complete tutorial for images, PDFs, and AI processing.

#### Delta Table path (binaryFile — bytes stored in Parquet)

When files are stored as BINARY columns in a Delta Table, they can still be rendered but require an extra decode step:

```python
# Read image bytes from Delta Table
df = spark.read.table("shared_catalog.schema.image_table")
row = df.filter("file_name = 'inspection_001.jpg'").first()

# Decode and display
from IPython.display import display, Image
display(Image(data=row.content))  # 'content' is the BINARY column

# Display audio from Delta Table
from IPython.display import Audio
audio_row = df.filter("file_name = 'machine_sound.wav'").first()
display(Audio(data=audio_row.content, rate=44100))
```

```python
# Databricks display() renders BINARY columns as thumbnails automatically
display(spark.read.table("shared_catalog.schema.image_table")
        .select("path", "content", "file_name"))
# → Databricks UI shows image thumbnails in the content column
```

Reference: [Databricks display() function](https://docs.databricks.com/aws/en/notebooks/notebooks-manage#display-function) — Databricks notebooks can render binary image data inline.

#### Comparison: User Experience for Governed File Browsing

| Aspect | UC Volume (original files) | Delta Table (binaryFile) |
|--------|---|---|
| **Image viewing** | ✅ Direct path → `Image(filename=...)` | ✅ Decode bytes → `Image(data=...)` |
| **Video playback** | ✅ `Video(filename=...)` or HTML5 `<video>` | ⚠️ Must write bytes to temp file first |
| **Audio playback** | ✅ `Audio(filename=...)` | ⚠️ `Audio(data=bytes, rate=...)` |
| **PDF rendering** | ✅ `IFrame(src=path)` | ⚠️ Must write bytes to temp file |
| **3D/CAD viewing** | ✅ `trimesh.load(path)` | ⚠️ Must write bytes to temp file |
| **DICOM medical** | ✅ `pydicom.dcmread(path)` | ⚠️ Must deserialize from bytes |
| **Thumbnail gallery** | ✅ Catalog Explorer file browser | ⚠️ Custom notebook code |
| **File download** | ✅ Direct download from Volume | ⚠️ Extract bytes → save → download |
| **Sharing recipient UX** | File explorer (browse folders) | Table view (rows and columns) |
| **Non-technical user friendly** | ✅ Familiar file/folder navigation | ❌ Requires SQL/Python knowledge |

**Conclusion for governed file browsing**: UC Volume + Volume Sharing provides a **file-system-like browsing experience** where non-technical users (factory workers, managers, auditors) can navigate folders and view files directly. Delta Table (binaryFile) requires notebook code to render each file — suitable for data engineers but not for browsable, governed file access.

---

## Provider vs Recipient: Role Clarification

| Role | Databricks as Provider | Databricks as Recipient |
|------|---|---|
| **Data location** | Data must be in UC (S3 bucket) | Data can be anywhere (FSx for ONTAP → processing → share) |
| **Governance** | UC governs access | Provider governs; UC applies local policies |
| **Architecture** | FSx for ONTAP → S3 → UC → Share | FSx for ONTAP → Lambda/Glue → Delta table → OSS OpenSharing Server → Databricks |
| **Complexity** | Simpler (UC handles everything) | More flexible (customer-managed sharing server) |
| **Recommended for** | Databricks-centric organizations | Multi-platform environments |

**Key insight**: When Databricks is the **recipient**, a customer-managed [OSS OpenSharing server](https://github.com/delta-io/delta-sharing) can expose FSx for ONTAP-backed datasets without requiring data to be in UC first.

---

## Governance Layers

| Layer | Scope | Enforcement Point |
|-------|-------|-------------------|
| FSx file permissions | NFS/SMB ACLs, UNIX users | FSx for ONTAP |
| S3 AP policy | IAM-based, per-access-point | AWS IAM |
| FPolicy | File operation audit/block | ONTAP |
| OpenSharing | Share-level, recipient-level | Sharing server or UC |
| Unity Catalog | Table/Volume/Column/Row level | Databricks |

For production deployments, define which layer is the **primary governance point** based on organizational requirements.

---

## Data Freshness Considerations

| Freshness Requirement | Recommended Pattern | Mechanism |
|---|---|---|
| Daily | Pattern A or B | Scheduled Glue/Lambda job |
| Hourly | Pattern A or B | Step Functions with CloudWatch Events |
| Near real-time (minutes) | Pattern A + FPolicy | FPolicy → Lambda → incremental update |
| Real-time (seconds) | Pattern C (future) | Direct FSx for ONTAP S3 AP access (requires UC support) |

---

## Recommended PoC Roadmap

```
Phase 1: Pattern A — File Metadata Sharing
├── Lambda function: ListObjectsV2 on FSx for ONTAP S3 AP → Parquet table
├── OpenSharing: Expose metadata table to Databricks
├── Databricks: Query file catalog, filter by type/date/size
└── Success: Databricks sees governed FSx for ONTAP file inventory

Phase 2: Pattern B — AI-Enriched Sharing
├── Textract: Extract text from PDFs on FSx for ONTAP
├── Bedrock: Generate embeddings and summaries
├── Delta table: Store chunks + embeddings
├── OpenSharing: Expose to Databricks
└── Success: Databricks Vector Search on FSx for ONTAP-derived content

Phase 3: Pattern C — Blocked (Databricks Feature Development Required)
├── Feature gap reported to Databricks UC engineering (May 2026)
├── Track UC engineering response and timeline
├── If supported: Direct FSx for ONTAP S3 AP → UC Volume → Volume Sharing
└── Until then: Pattern A/B + S3 sync for raw files (only production-ready path)
```

---

## FAQ: Why Can't We Just "Create a Delta Table on EC2" Without ETL?

A common misconception is that OpenSharing is purely a metadata problem — that you can simply point a Delta Table at FSx for ONTAP files and share them without any ETL or data movement. This section explains why that is not the case, with references to Databricks documentation.

### Misconception: "OpenSharing is just metadata, so create a Delta Table on EC2 and share it"

**The assumption**: FSx for ONTAP stores files → an EC2 instance creates a Delta Table pointing to those files → OpenSharing exposes the table → Databricks reads it. No ETL, no copy.

**Why this doesn't work with FSx for ONTAP S3 Access Points:**

#### 1. Delta Table ≠ a pointer to arbitrary files

A Delta Table is not just metadata pointing to existing files. It is a **specific storage format** consisting of:
- Parquet data files (the actual data)
- A `_delta_log/` directory containing JSON commit files (transaction log)

The transaction log records every change to the table and is what provides ACID guarantees. Creating a Delta Table requires **writing** both the Parquet files and the commit log to the storage location.

Reference: [What are ACID guarantees on Databricks?](https://docs.databricks.com/aws/lakehouse/acid) — "Databricks uses Delta Lake by default for all reads and writes and builds upon the ACID guarantees provided by the open source Delta Lake protocol."

#### 2. Delta Lake commit protocol requires conditional writes

Delta Lake's commit protocol on S3 requires either:
- **put-if-absent** (conditional write) semantics, OR
- A **DynamoDB-based commit coordinator** (for multi-cluster writes)

FSx for ONTAP S3 Access Points **do not support conditional writes** (`If-None-Match` header returns "not supported"). This means:
- You cannot safely write Delta commit logs to FSx for ONTAP S3 AP
- Concurrent writers would corrupt the transaction log
- Even a single writer cannot guarantee atomic commits

Reference: [Multi-cluster writes to Delta Lake on S3](https://delta.io/blog/2022-05-18-multi-cluster-writes-to-delta-lake-storage-in-s3/) — "S3 currently lacks 'put-If-Absent' consistency guarantees. Thus, to guarantee ACID transactions on S3, one would need to have concurrent writes originating from the same Apache Spark driver."

Reference: [Delta Lake storage configuration](http://docs.delta.io/latest/delta-storage.html) — "Delta Lake uses the scheme of the path to dynamically identify the storage system and use the corresponding LogStore implementation that provides the transactional guarantees."

#### 3. Delta Lake on S3 requires specific IAM permissions for `_delta_log`

Even on standard S3, Delta Lake requires specific permissions beyond basic read/write:
- `s3:PutObject` for data files AND commit log files
- `s3:GetObject` for reading the latest commit version
- `s3:ListBucket` for discovering commit log entries
- `s3:DeleteObject` for vacuum operations

On FSx for ONTAP S3 AP, the UC session policy blocks `PutObject` and subdirectory `ListBucket` — making Delta Table creation impossible under UC governance.

Reference: [Access denied when writing Delta Lake tables to S3](https://kb.databricks.com/en_US/delta/s3-permissions-delta) — "Delta Lake requires creation of a _delta_log directory. The write operation also needs to check the latest version of the commit logs."

#### 4. OpenSharing requires the table to be registered in Unity Catalog

OpenSharing (Databricks-to-Databricks protocol) shares tables that are **registered in Unity Catalog**. A table registered in UC must reside in either:
- A **UC Managed Storage** location (Databricks-managed S3 bucket), OR
- A **UC External Location** (customer S3 bucket registered with Storage Credential)

FSx for ONTAP S3 AP cannot be read through a UC External Location: registration succeeds and the read is what fails, because the down-scoped session policy Unity Catalog issues carries a bucket-form ARN (measured here 2026-08-12). Therefore, even if you could create a Delta Table on FSx for ONTAP S3 AP, you could not register it in UC for sharing.

Reference: [Create and manage shares for OpenSharing](https://docs.databricks.com/en/delta-sharing/create-share.html) — Shares can contain tables from "only one Unity Catalog metastore."

Reference: [What is the OpenSharing Databricks-to-Databricks protocol?](https://docs.databricks.com/aws/en/delta-sharing/share-data-databricks) — Requires UC-enabled workspace and UC-registered assets.

#### 5. OSS OpenSharing Server still needs a valid Delta Table

Even using the [OSS OpenSharing server](https://github.com/delta-io/delta-sharing) (bypassing UC), the server must point to a valid Delta Table with a consistent `_delta_log`. The same storage requirements apply — you need a storage backend that supports the Delta commit protocol.

### What "creating a Delta Table on EC2" actually means

If you run a Spark job on EC2 that reads files from FSx for ONTAP S3 AP and writes a Delta Table, you are performing ETL:

```
FSx for ONTAP S3 AP (source files: CSV, Parquet, JSON, images)
  ↓ GetObject (read)
EC2 / EMR / Glue (Spark job)
  ↓ spark.read → transform → spark.write.format("delta")
S3 bucket (Delta Table: Parquet files + _delta_log/)
  ↓ Register in UC
OpenSharing
```

This is **not** "just metadata" — it is:
1. **Reading** source files from FSx for ONTAP S3 AP (GetObject)
2. **Transforming** them into Parquet format with Delta schema
3. **Writing** Parquet data files + commit log to a different storage location (S3 bucket)
4. **Registering** the table in Unity Catalog

This is ETL by definition. The "E" (Extract) is reading from FSx for ONTAP. The "T" (Transform) is converting to Delta format. The "L" (Load) is writing to S3.

### Summary: Why S3 bucket is required

| Step | Why FSx for ONTAP S3 AP alone is insufficient |
|------|---|
| Write Delta commit log | Conditional writes not supported on FSx for ONTAP S3 AP |
| Register in UC | Registration succeeds; reads through it are denied by the vended session policy (BLK-001, scope corrected 2026-08-12) |
| Multi-cluster safety | No DynamoDB LogStore equivalent for FSx for ONTAP S3 AP |
| OpenSharing | Requires UC-registered table or valid Delta Table on supported storage |

### The only true "Zero Copy" path

The only scenario where no data copy occurs is **Pattern C** (UC Volume Sharing) — but this requires Databricks to support FSx for ONTAP S3 AP as a first-class UC storage location. Volume Sharing shares file references, not table data, so no Delta commit log is needed.

**Current status**: Blocked — awaiting Databricks UC feature development (reported May 2026, no timeline).

### Alternative: OSS OpenSharing Server with direct Parquet reference (experimental, unverified)

The [OSS OpenSharing server](https://github.com/delta-io/delta-sharing) supports sharing Parquet files without a full Delta commit log. If FSx for ONTAP S3 AP already contains well-structured Parquet files with known schemas, it may be possible to configure the OSS server to expose them as shared tables.

**How it could work:**
1. Parquet files exist on FSx for ONTAP (written by ETL jobs, NFS clients, or other engines)
2. OSS OpenSharing server is configured with a `delta-sharing-server.yaml` pointing to the S3 AP paths
3. Recipients query the shared "table" through the OpenSharing protocol

**Constraints and risks:**
- No ACID guarantees (no commit log = no transaction isolation)
- No schema evolution tracking (schema must be managed externally)
- No Time Travel or versioning
- Concurrent writes to the same Parquet files could produce inconsistent reads
- The OSS server must be able to generate presigned URLs for the S3 AP paths (requires IAM role with S3 AP access)
- This is NOT a Databricks-supported path — it bypasses Unity Catalog entirely

**When to consider**: Only when the requirement is "expose existing Parquet files on FSx for ONTAP to external consumers without any data movement" AND governance/ACID requirements are minimal. For production workloads requiring governance, use the DataSync → S3 → UC path instead.

> **Verification status**: This approach has NOT been validated against FSx for ONTAP S3 Access Points. It is documented as a theoretical alternative pending Pattern A PoC validation. Key unknowns: whether the OSS server can generate valid presigned URLs for FSx for ONTAP S3 AP paths, and whether ListObjectsV2 latency impacts the sharing protocol's file discovery.

---

## Next Steps

1. **Start Pattern A PoC**: Deploy a Lambda function that calls ListObjectsV2 on your FSx for ONTAP S3 AP, writes metadata to a Delta Table on S3, and exposes it via OpenSharing
2. **For immediate Databricks access**: Set up DataSync → S3 → UC External Location for full governance ([README Configuration Guide](../../README.md#quick-start))
3. **Track Databricks feature gap**: Monitor UC engineering response for native FSx for ONTAP S3 AP support (reported May 2026, no timeline)

---

## References

- [Work with unstructured data in volumes](https://docs.databricks.com/aws/en/volumes/unstructured-data-tutorial) — Complete tutorial including Volume Sharing
- [What are Unity Catalog volumes?](https://docs.databricks.com/aws/en/volumes/managed-vs-external) — Managed vs External volumes
- [Volume Sharing with OpenSharing (Video)](https://www.databricks.com/resources/demos/videos/data-sharing/volume-sharing-delta-sharing) — Demo video
- [Create and manage shares](https://docs.databricks.com/en/delta-sharing/create-share.html) — Adding Volumes to Shares
- [OpenSharing OSS](https://github.com/delta-io/delta-sharing) — Open-source OpenSharing server
- [FSx for ONTAP S3 Access Points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-access-points.html) — AWS documentation

---

## Related Documents

- [Databricks README](../../README.md) — Full integration status and architecture
- [Analytics & AI Demo Guide](ai-demo-guide.md) — AI/ML capabilities and current status
- [Blocker Tracker](../../../../docs/en/blocker-tracker.md) — BLK-001 records the Unity Catalog / S3 Access Point limitation, its confirmation date and the available workarounds
