**English** | [日本語](../ja/quickstart-business-guide.md)

# How to Use Your File Server Data for Analytics and AI

> For account managers, sales, business leaders, and anyone who needs the "what" and "why" without the implementation details.
>
> **Note**: This guide assumes your file server runs on **Amazon FSx for NetApp ONTAP** (FSx for ONTAP) — AWS's managed enterprise file storage that supports Windows shares, Linux mounts, and S3 access simultaneously.

---

## The One-Sentence Answer

**Yes, you can analyze your file server data (shared drives) using analytics platforms like Databricks, Athena, or Snowflake — and the system creates a small "card catalog" of your files rather than moving the files themselves.**

---

## The Library Analogy

Think of it this way:

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   Your file server (shared drives)     =  The library shelves   │
│   Files (PDFs, images, CSVs, etc.)     =  The actual books      │
│   The analytics extract                =  The card catalog      │
│   Analytics platforms                  =  The search system     │
│   (Athena, Snowflake, Databricks,                               │
│    EMR, OpenSearch, etc.)                                       │
│                                                                 │
│   You DON'T move the books.                                     │
│   You CREATE a card catalog that tells you what's on each       │
│   shelf, and the search system lets anyone find what they need. │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

- The **books stay on the shelves** (your files stay on the file server)
- A small **card catalog** is created (structured data: titles, authors, categories — extracted from the files)
- **Analytics platforms** (Athena, Snowflake, Databricks, etc.) let people query the catalog
- When someone needs the actual book, they go to the shelf (on-demand file access)

---

## Why Can't You Just "Connect" Directly?

Short answer: **Most analytics platforms don't speak the file server's language natively.**

Your file server uses NFS and SMB (the technology behind shared network drives — what Windows Explorer and Linux use to access files). Analytics platforms expect data in cloud storage formats. It's like trying to plug a Japanese appliance into a US outlet — you need an adapter.

**Good news**: Some platforms (Athena, Snowflake, EMR) can already read directly from the file server via a built-in connector (S3 Access Points) — no adapter needed for read-only analytics. For platforms that need managed tables (like Databricks Unity Catalog), a small pipeline extracts and writes the structured data.

The "adapter" pipeline:
1. **Reads** relevant data from your file server (no files are moved)
2. **Extracts** the useful information (measurements, metadata, classifications)
3. **Writes** that small extract to analytics-compatible storage

---

## The Three Ways to Get Your Data There

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  Your File Server                                                   │
│  (thousands of files,                                               │
│   images, PDFs, CSVs)                                               │
│         │                                                           │
│         │ 1. Read relevant files                                    │
│         ▼                                                           │
│  ┌─────────────────┐                                                │
│  │  Processing     │  An automated pipeline picks out the           │
│  │  Pipeline       │  useful information from your files.           │
│  └────────┬────────┘                                                │
│           │                                                         │
│     ┌─────┼──────────────────────┐                                  │
│     │     │                      │                                  │
│     ▼     ▼                      ▼                                  │
│  ┌──────┐ ┌────────────────┐ ┌───────────────────┐                  │
│  │Tables│ │Search Index    │ │Analytics Platform │                  │
│  │(AWS) │ │(for AI-powered │ │(Athena/Snowflake/ │                  │
│  │      │ │ search)        │ │ Databricks/EMR)   │                  │
│  └──────┘ └────────────────┘ └───────────────────┘                  │
│                                                                     │
│                                                                     │
│  2. Only the "card catalog" is stored here — NOT your files.        │
│     Typically less than 1% of the original file volume.             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

| Way | Best for | Speed | Cost |
|-----|----------|-------|------|
| **A. Smart Extract** (recommended) | Getting structured insights from mixed files | Hours to set up | Very low (~$5/month for 100K files) |
| **B. Selective Sync** | When you only need specific file types (e.g., CSVs) | 1 day to set up | Low (only synced files cost storage) |
| **C. Full Sync** | When ML needs all files (e.g., training on images) | 1 day to set up | Higher (duplicates all files) |

---

## Which Way Is Right for You?

```
Start here:
     │
     ▼
Do you need to analyze the FILE CONTENTS
(text, numbers inside CSVs/PDFs)?
     │
     ├── YES → Do you need ALL files or just specific types?
     │              │
     │              ├── Specific types (CSVs, Parquet) → Way B (Selective Sync)
     │              └── All files (images for ML) → Way C (Full Sync)
     │
     └── NO, just file METADATA (what's there, who owns it,
         when it changed, AI classification) → Way A (Smart Extract)
```

**Most organizations start with Way A** because they want to find and categorize their files, not copy them all.

---

## What It Costs and How Long It Takes

### Typical timeline

| Phase | What happens | Duration |
|-------|-------------|----------|
| Setup | Connect your file server to the pipeline | 1–2 days |
| Processing | Pipeline reads files and creates the catalog | 2–3 days |
| Live | People can search and analyze | Ongoing |

**Total: 5–7 business days from start to "people can search."**

### Typical monthly cost (Way A, 100,000 files)

| What you're paying for | Monthly cost |
|----------------------|:------------:|
| AI that reads and classifies your files | ~$65 |
| The search database | ~$42 |
| Compute (the pipeline itself) | ~$7 |
| **Total** | **~$114/month** |
| When nobody's using it (idle) | ~$5/month |

Your files stay on your file server — no additional storage cost for them.

---

## What "Zero-Copy" Actually Means

This phrase causes the most confusion. Here's the plain truth:

| What is "zero-copy" | What still gets created |
|--------------------|-----------------------|
| Your **files don't move** — images, PDFs, videos stay on the file server | A small **analytics extract** is created (~1 MB for every 6 GB of source files) |
| No **duplicate storage** of your raw data | Structured tables with metadata (file names, categories, measurements) |
| No ongoing **sync of full files** | The pipeline runs continuously on new/changed files |

**Analogy**: When Google indexes a website, the website stays where it is. Google creates an index (a fraction of the original size) that makes it searchable. Same principle.

---

## Common Questions from Business Stakeholders

**Q: Is this secure?**
Yes. Files never leave your AWS account. The pipeline reads files inside your private network and writes the extract to your own AWS storage. Access is controlled by the same security rules as your existing systems.

**Q: What happens to my existing workflows?**
Nothing changes. People using Windows file shares or Linux mounts continue exactly as before. The analytics pipeline is additive — it reads files without modifying them.

**Q: Which analytics platform should I use?**
It depends on what you need:
| Platform | Characteristics and fit |
|---|---|
| Amazon Athena | Serverless SQL, no infrastructure, pay per query. Works immediately with zero-copy reads from the file server. The simplest starting point |
| Snowflake | If you already use it. Supports External Tables on the file server + AI features (Cortex). Zero-copy reads verified ([evidence](../../verification-pack/snowflake/evidence/2026-05-24/evidence-record.yaml), ap-northeast-1) |
| Databricks | Advanced ML/AI, Unity Catalog governance. Requires a small data extract (indirect path) due to a current platform constraint with file server access points |
| Amazon EMR | Spark-based ETL, read + write verified ([evidence](../../verification-pack/emr-spark/evidence/2026-05-23/evidence-record.yaml), ap-northeast-1). Suits large-scale data transformation |
| DuckDB (Lambda) | Lightest option. Serverless, ~$0.00001/query. Suits ad-hoc exploration |

Multiple platforms can access the same file server data simultaneously — they are not mutually exclusive.

**Q: Can I try this without committing?**
Yes. A proof-of-concept with 100–1,000 sample files takes about 1 week and costs less than $50. No changes to your production file server.

---

## Next Steps

| Your role | Start here |
|-----------|-----------|
| Business leader / executive | You've read enough. Ask your technical team to review the [PoC Execution Guide](../implementation-guide/poc-execution-guide.md) |
| Account manager / sales | Share this page + the [Cost Estimation](../adoption-guide/cost-estimation.md) with the evaluating team |
| Technical lead | Continue to the [UC Connection Guide](./fsx-ontap-to-databricks-unity-catalog-guide.md) for full architecture details |
| SI / implementation partner | See the [PoC Execution Guide](../implementation-guide/poc-execution-guide.md) for the step-by-step checklist |

---

*Last updated: 2026-06*
