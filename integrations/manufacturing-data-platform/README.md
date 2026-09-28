# Manufacturing Data Platform PoC

🌐 **English** | [日本語](README-ja.md)

---

> Architecture validation for a manufacturing data platform that integrates edge/factory data
> with Databricks Unity Catalog — without relying on S3 Access Points.

## Architecture

```
Edge/Factory ──→ Kafka (MSK) ──→ ClickHouse (real-time dashboards)
                      │                         
                      └──────→ Databricks (governed Delta tables on S3)
                                    
Payloads (images/video/docs) ──→ ONTAP (on-prem origin)
                                    ↓ FlexCache
                                 FSx for ONTAP (AWS cache, no full copy)
```

**Key Design Principles:**
- No S3 Access Points dependency for Databricks/Unity Catalog
- No data duplication — FlexCache provides on-demand caching
- Single source of truth for payloads (on-premises ONTAP)
- Real-time + governed analytics as complementary layers

## Quick Start (Phase A — AWS)

> **Current Status (2026-06-15):** MSK Provisioned is ACTIVE. ClickHouse Cloud ClickPipes shows
> the Multi-VPC endpoint as "Incompatible" — awaiting ClickHouse Support resolution (ClickHouse support case pending).
> On-premises Instaclustr setup is in parallel (VM host ready, awaiting VM images from Instaclustr SE).

```bash
# 1. Deploy infrastructure (existing VPC + FSx for ONTAP reused)
cd poc/infrastructure
./deploy.sh deploy          # S3 + MSK into existing VPC
./deploy.sh volumes         # Create volumes on existing FSx for ONTAP

# 2. Verify synthetic data generator
cd ../synthetic-data-generator
pip install -r requirements.txt
python generate_events.py --dry-run

# 3. Run tests
pytest tests/ -v
```

## Documentation

| Document | Purpose |
|----------|---------|
| [Project Overview](docs/en/00_project_overview.md) | Architecture summary and scope |
| [Requirements](docs/en/01_requirements.md) | Functional and non-functional requirements |
| [Research Findings](docs/en/02_research_findings.md) | Technical validation with sources |
| [Architecture Design](docs/en/03_architecture_design.md) | Detailed design (DES-001 to DES-010) |
| [Risks](docs/en/04_risks_and_considerations.md) | Risk register (RSK-001 to RSK-017) |
| [PoC Plan](docs/en/05_poc_plan.md) | Implementation plan with acceptance criteria |
| [Decision Matrix](docs/en/06_decision_matrix.md) | Component selection rationale |
| [ADRs](docs/adr/README.md) | 14 Architecture Decision Records |
| [SLOs](docs/en/10_slo_operational_readiness.md) | Service Level Objectives and runbooks |
| [Performance Targets](docs/en/11_performance_targets_business_metrics.md) | Latency, throughput, business metrics |
| [Security](docs/en/12_security_hardening.md) | Encryption, secrets, audit, deny policies |
| [Engagement Template](docs/en/13_customer_engagement_template.md) | Partner/SI reusable template |
| [Edge ↔ Lakehouse Sync](docs/en/14_edge_lakehouse_sync.md) | Cross-project design synchronization |

## Architecture Decision Records (ADRs)

| ADR | Decision |
|-----|----------|
| [001](docs/adr/ADR-001.md) | Kafka as factory event backbone |
| [002](docs/adr/ADR-002.md) | ClickHouse for real-time analytics |
| [003](docs/adr/ADR-003.md) | FSx for ONTAP as payload storage |
| [004](docs/adr/ADR-004.md) | No S3 Access Points dependency |
| [005](docs/adr/ADR-005.md) | Metadata/payload separation |
| [006](docs/adr/ADR-006.md) | ClickHouse Cloud for Phase A |
| [007](docs/adr/ADR-007.md) | Phased deployment + FlexCache |
| [008](docs/adr/ADR-008.md) | Edge buffering (3-tier) |
| [009](docs/adr/ADR-009.md) | Kafka → ClickHouse connector |
| [010](docs/adr/ADR-010.md) | Deduplication strategy |
| [011](docs/adr/ADR-011.md) | Unity Catalog permissions |
| [012](docs/adr/ADR-012.md) | Schema evolution |
| [013](docs/adr/ADR-013.md) | FSx for ONTAP sizing |
| [014](docs/adr/ADR-014.md) | MSK Serverless → Provisioned migration |
| [015](docs/adr/ADR-015.md) | Kafka deployment strategy — MSK vs Instaclustr |

## Project Structure

```
integrations/manufacturing-data-platform/
├── docs/
│   ├── en/              — English documentation (00-13)
│   ├── ja/              — Japanese documentation (synchronized)
│   ├── adr/             — Architecture Decision Records (ADR-001 to ADR-014)
│   ├── references.md    — All research sources (100+ entries)
│   ├── glossary_ja_en.md — Bilingual technical glossary
│   └── support-inquiries/ — Vendor support cases
├── poc/
│   ├── config/          — Unified Phase A/B configuration
│   ├── infrastructure/  — CloudFormation + deployment scripts
│   ├── clickhouse/      — ClickHouse setup SQL (v1 + v2 Edge-aligned + feedback_events)
│   ├── databricks/      — UC catalog + DLT + feature import + Gold dataset + success metrics
│   ├── on-premises/     — Phase B on-prem procedures
│   ├── edge-device/     — Raspberry Pi setup
│   ├── shared-test-data/ — Shared test events (synced with Edge project)
│   └── synthetic-data-generator/ — Test data + 28 unit tests
└── README.md            — This file
```

## Phase A vs Phase B

| | Phase A (Current) | Phase B (Target) |
|-|-------------------|-----------------|
| Kafka | AWS MSK Provisioned | Instaclustr on-prem |
| ClickHouse | ClickHouse Cloud | Instaclustr on-prem |
| ONTAP | FSx for ONTAP (AWS) | On-prem ONTAP (origin) + FlexCache (AWS) |
| Databricks | AWS | AWS (unchanged) |
| Edge | Synthetic generator | Raspberry Pi (ONTAP-Edge-to-Cloud-AI) |

## Related Projects

- [ONTAP-Edge-to-Cloud-AI](https://github.com/Yoshiki0705/ONTAP-Edge-to-Cloud-AI) — Edge device (Raspberry Pi) integration

## Confidentiality

All data is synthetic. No real customer names, factory names, or device data.
