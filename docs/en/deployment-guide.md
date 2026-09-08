# Deployment Guide — FSx for ONTAP Lakehouse Integrations

> Unified deployment reference for all 28 CloudFormation templates in this repository.
> Assumes an **existing FSx for ONTAP environment** (file system, SVM, and volumes already provisioned).
>
> Don't have FSx for ONTAP yet? See [Getting Started](./getting-started.md) to provision one (~45 min).

---

## Which Integration Should I Deploy?

```
Start here:
│
├─ "I want to query files with SQL, no ETL"
│   └─ Path 1: Athena (~5 min, $0 idle)
│
├─ "I need ETL: raw → cleaned → aggregated"
│   └─ Path 2: Glue ETL (~8 min, pay-per-run)
│
├─ "I need sub-second analytics on small-medium data"
│   └─ Path 3: DuckDB Lambda (~8 min, $0 idle)
│
├─ "I use Snowflake and want to read FSx for ONTAP data"
│   └─ Path 4: Snowflake (~10 min, $0 idle)
│
├─ "I need real-time file change detection → pipeline"
│   └─ Path 5: FPolicy (~15 min, ~$15/month)
│
└─ "I use Databricks and want Unity Catalog integration"
    └─ Path 6: Databricks (~15 min, ~$35/month)
        ⚠️ Known limitation: see Verified Deployment Paths
```

---

## Quick Reference

| What you need | Where to look |
|---|---|
| Deploy a single integration fast | [Verified Deployment Paths](#verified-deployment-paths) |
| Understand template dependencies | [Stack Inventory](#stack-inventory) |
| Check VPC endpoint requirements | [VPC Endpoint Conflict Matrix](#vpc-endpoint-conflict-matrix) |
| Validate environment before deploy | [Preflight Check](#preflight-check) |
| Estimate costs | [Cost Reference](#cost-reference) |
| Roll back a failed deployment | [Rollback Procedures](#rollback-procedures) |
| Test WINDOWS user type S3 APs | [AD Environment Setup](#ad-environment-for-windows-user-type) |

---

## Prerequisites

### Required

- AWS CLI v2.15+ configured with appropriate IAM permissions
- Existing Amazon FSx for NetApp ONTAP file system (ONTAP 9.14.1+ for S3 AP support)
- At least one SVM with S3 protocol enabled (`vserver object-store-server create`)
- The SVM must **NOT** have a native ONTAP S3 object-store server on the same SVM where you plan to use FSx for ONTAP S3 Access Points (structural conflict — see [Troubleshooting](#common-deployment-failures))
- At least one volume with a junction path
- S3 Access Point already created via `aws fsx create-and-attach-s3-access-point`

> **How to check ONTAP version**: The FSx console and `describe-file-systems` API do not expose the ONTAP version directly. Use the ONTAP REST API: `GET https://<mgmt-ip>/api/cluster?fields=version` with fsxadmin credentials.

### ONTAP Version Requirements

| Feature | Minimum ONTAP Version | Notes |
|---|---|---|
| S3 Access Points (basic) | 9.14.1 | Read + Write (no conditional writes) |
| S3 Access Points (enhanced) | 9.15.1 | Improved throughput, multi-part upload |
| FPolicy external engine | 9.8+ | Required for event-driven pipelines |
| FlexClone | 9.1+ | Used for safe ingestion patterns |

### IAM Permissions for Deployer

The IAM principal running `aws cloudformation create-stack` needs:

```
cloudformation:CreateStack, cloudformation:DescribeStacks, cloudformation:DescribeStackEvents,
  cloudformation:GetTemplate, cloudformation:ListStackResources, cloudformation:DeleteStack,
  cloudformation:UpdateStack
iam:CreateRole, iam:PutRolePolicy, iam:AttachRolePolicy, iam:PassRole, iam:DeleteRole,
  iam:DeleteRolePolicy, iam:DetachRolePolicy
s3:CreateAccessPoint, s3:PutAccessPointPolicy
ec2:CreateVpcEndpoint, ec2:CreateSecurityGroup, ec2:AuthorizeSecurityGroupIngress
lambda:CreateFunction, lambda:CreateLayerVersion
glue:CreateDatabase, glue:CreateCrawler, glue:CreateJob
fsx:DescribeFileSystems, fsx:DescribeVolumes, fsx:DescribeStorageVirtualMachines
logs:CreateLogGroup
events:PutRule, events:PutTargets
sns:CreateTopic
sqs:CreateQueue
ecs:CreateCluster, ecs:CreateService (FPolicy only)
```

> **Security note**: Scope these permissions to specific resource ARNs in production. The list above is the minimum action set; `cloudformation:*` is overly broad and not recommended.

---

## Stack Inventory

### Category A: Shared Infrastructure (deploy first if greenfield)

| # | Template | Description | Deploy Time | Idempotent |
|---|---|---|---|---|
| A1 | `shared/cloudformation/vpc-networking.yaml` | VPC, subnets, S3 Gateway + Interface EP, Security Groups | ~3 min | No |
| A2 | `shared/cloudformation/fsxn-s3ap-base.yaml` | FSx for ONTAP FS + SVM + Volumes + S3 AP (full greenfield) | ~45 min | No |
| A3 | `shared/cloudformation/iam-policies.yaml` | Common IAM policies (read-only, read-write, platform, ETL, consumer roles) | ~1 min | Yes |
| A4 | `shared/cloudformation/sample-data-generator.yaml` | Lambda to generate Parquet/CSV/JSON sample data via S3 AP | ~2 min | Yes |

> **Note**: For overlay deployments (existing FSx for ONTAP), skip A1–A2 and provide your existing VPC/subnet/SG/FS IDs as parameters.

### Category B: Analytics Integrations (independent, pick what you need)

| # | Template | Description | Deploy Time | VPC Required |
|---|---|---|---|---|
| B1 | `integrations/athena/template.yaml` | Glue Crawler + Athena Workgroup + IAM | ~2 min | No |
| B2 | `integrations/glue/template.yaml` | Glue ETL (Crawler + Bronze→Silver→Gold Jobs + EventBridge) | ~3 min | No |
| B3 | `integrations/duckdb/template.yaml` | DuckDB Lambda (VPC-attached, arm64) + Layer + S3 bucket | ~3 min | Yes |
| B4 | `integrations/delta-lake-oss/template.yaml` | Delta Lake OSS IAM Role + Instance Profile for EMR | ~1 min | No |
| B5 | `integrations/opensharing-server/template.yaml` | OpenSharing Volumes API (Lambda + Function URL + credential vending) | ~2 min | No |

### Category C: Databricks Integration (deploy in order)

| # | Template | Description | Deploy Time | Depends On |
|---|---|---|---|---|
| C1 | `integrations/databricks/customer-vpc-network.yaml` | Databricks subnets, NAT GW, route tables, cluster SG | ~5 min | Existing VPC |
| C2 | `integrations/databricks/template.yaml` | S3 AP (VPC-scoped) + cross-account IAM Role + S3 Interface EP | ~3 min | C1 |
| C3 | `integrations/databricks/vpc-peering.yaml` | VPC Peering between Databricks and FSx for ONTAP VPCs | ~2 min | C1 |

### Category D: Snowflake Integration

| # | Template | Description | Deploy Time | Depends On |
|---|---|---|---|---|
| D1 | `integrations/snowflake/template.yaml` | IAM Role (two-phase trust) + optional SNS for Snowpipe | ~1 min | S3 AP exists |
| D2 | `integrations/snowflake/snowpipe-lambda/template.yaml` | Snowpipe polling Lambda + EventBridge schedule | ~2 min | D1 |

### Category E: FPolicy Event-Driven Pipeline (deploy in order)

| # | Template | Description | Deploy Time | Depends On |
|---|---|---|---|---|
| E1 | `shared/cloudformation/fpolicy-routing.yaml` | SNS Topic + Snowpipe subscription + EventBridge routing | ~1 min | — |
| E2 | `shared/cloudformation/fpolicy-ingestion.yaml` | SQS Queue + DLQ + SQS VPC Endpoint + Lambda Bridge | ~3 min | E1 |
| E3 | `shared/cloudformation/fpolicy-server-fargate.yaml` | ECS Fargate FPolicy TCP server | ~5 min | E2 |
| E4 | `shared/cloudformation/fpolicy-ip-updater.yaml` | Lambda to auto-update ONTAP external-engine IP on task restart | ~2 min | E3 |

### Category F: Iceberg Metadata Catalog

| # | Template | Description | Deploy Time | Depends On |
|---|---|---|---|---|
| F1 | `integrations/iceberg-metadata-catalog/cloudformation/s3-tables-setup.yaml` | S3 Tables bucket + Athena Workgroup + Lake Formation | ~3 min | — |
| F2 | `integrations/iceberg-metadata-catalog/cloudformation/metadata-sync-pipeline.yaml` | SQS + Lambda sync handler for FPolicy events | ~2 min | F1 |
| F3 | `integrations/iceberg-metadata-catalog/demo/cloudformation/demo-stack.yaml` | All-in-one demo (S3 Tables + OpenSearch Serverless + Athena) | ~5 min | — |
| F4 | `integrations/iceberg-metadata-catalog/use-cases/_shared/cloudformation/industry-demo-stack.yaml` | Per-industry demo (20 industries, S3 Tables + optional OpenSearch) | ~3 min | — |

### Category G: Manufacturing Data Platform PoC (deploy in order)

| # | Template | Description | Deploy Time | Depends On |
|---|---|---|---|---|
| G1 | `integrations/manufacturing-data-platform/poc/infrastructure/01-vpc-network.yaml` | Dedicated VPC + subnets + SGs + S3/STS VPC Endpoints | ~3 min | — |
| G2 | `integrations/manufacturing-data-platform/poc/infrastructure/02-s3-buckets.yaml` | KMS keys + S3 buckets (Delta Lake, checkpoints, audit) | ~2 min | G1 |
| G3 | `integrations/manufacturing-data-platform/poc/infrastructure/03-fsx-ontap.yaml` | FSx for ONTAP Single-AZ + SVM + 4 volumes | ~45 min | G1 |
| G4 | `integrations/manufacturing-data-platform/poc/infrastructure/msk-serverless.yaml` | MSK Serverless cluster + IAM policy | ~10 min | G1 |

### Category H: PoC Quick-Start Templates

| # | Template | Description | Deploy Time | Depends On |
|---|---|---|---|---|
| H1 | `poc-templates/06-duckdb-lambda/template.yaml` | Minimal DuckDB Lambda PoC (no VPC) | ~2 min | S3 AP exists |
| H2 | `poc-templates/04-databricks-integration/datasync-task.yaml` | DataSync NFS→S3 task for Databricks UC workaround | ~3 min | FSx SVM + S3 bucket |

---

## VPC Endpoint Conflict Matrix

FSx for ONTAP S3 Access Points have specific networking requirements. This matrix shows which VPC endpoints each integration needs.

### Endpoint Types

| Endpoint | Type | Cost | Purpose |
|---|---|---|---|
| S3 Gateway | Gateway | **Free** | Routes S3 traffic from route tables to S3 service |
| S3 Interface | Interface (PrivateLink) | ~$0.01/hr/AZ + data | Private DNS for VPC-scoped S3 APs |
| SQS Interface | Interface (PrivateLink) | ~$0.01/hr/AZ + data | Fargate → SQS communication in private subnets |
| STS Interface | Interface (PrivateLink) | ~$0.01/hr/AZ + data | MSK IAM auth, cross-account AssumeRole |

### Compatibility Matrix

| Integration | S3 Gateway EP | S3 Interface EP | SQS Interface EP | STS Interface EP | Notes |
|---|:---:|:---:|:---:|:---:|---|
| Athena | — | — | — | — | AWS-managed, no customer VPC involvement |
| Glue ETL (non-VPC) | — | — | — | — | AWS-managed execution |
| Glue ETL (VPC-attached) | ⚠️ | Optional | — | — | Gateway EP may block S3 AP traffic; use NAT GW |
| DuckDB Lambda (VPC) | ⚠️ | Recommended | — | — | VPC-scoped AP needs Interface EP or NAT GW |
| Delta Lake / EMR | ✅ | Optional | — | — | Standard S3 traffic works via Gateway EP |
| Databricks (Customer VPC) | ✅ | ✅ Required | — | — | VPC-scoped AP requires Interface EP |
| Snowflake | — | — | — | — | SaaS platform; internet-origin AP required |
| FPolicy Pipeline | ✅ | — | ✅ Required | — | Fargate needs SQS EP for private subnets |
| Manufacturing PoC | ✅ | — | — | ✅ Required | MSK Serverless IAM auth needs STS EP |
| OpenSharing Server | — | — | — | — | Lambda (non-VPC), internet-origin AP |

### Critical Warning: S3 Gateway Endpoint and FSx for ONTAP S3 AP

> **S3 Gateway Endpoint may intercept but fail to correctly route FSx for ONTAP S3 AP traffic** for internet-origin Access Points. FSx for ONTAP S3 AP aliases resolve to `s3-r-w.<region>.amazonaws.com`, which may not be in the S3 prefix list used by Gateway endpoints.

**Impact**: VPC-attached Lambda or EC2 accessing an internet-origin FSx for ONTAP S3 AP through a route table with S3 Gateway EP → **timeout**.

**Solutions** (choose one):
1. Place Lambda outside VPC (no VPC attachment) — simplest for internet-origin APs
2. Use NAT Gateway for FSx for ONTAP S3 AP traffic
3. Use VPC-scoped S3 AP + S3 Interface Endpoint (recommended for production)

See [FSx for ONTAP S3 AP Networking](./fsx-ontap-s3ap-networking.md) for full details.

---

## Verified Deployment Paths

### Path 1: Athena Quick-Start (fastest, read-only analytics)

**Time**: ~5 minutes | **Cost**: ~$0/month (pay per query) | **VPC**: Not required

**Prerequisite**: S3 Access Point in AVAILABLE state (internet-origin).

```bash
# 1. Preflight
./scripts/preflight-check.sh --integration athena

# 2. Validate template syntax
aws cloudformation validate-template --template-body file://integrations/athena/template.yaml

# 3. Deploy
aws cloudformation create-stack \
  --stack-name fsxn-athena-dev \
  --template-body file://integrations/athena/template.yaml \
  --parameters file://cfn-params/athena.example.json \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
# Note: --capabilities CAPABILITY_NAMED_IAM is required because templates create
# IAM roles with custom names. file:// paths are relative to your current directory.

# 4. Wait for completion (~2 minutes)
aws cloudformation wait stack-create-complete --stack-name fsxn-athena-dev
# If stuck > 5 minutes: aws cloudformation describe-stack-events --stack-name fsxn-athena-dev

# 5. Run Glue Crawler to discover schema
aws glue start-crawler --name fsxn-athena-crawler-dev
# Wait ~1 minute, then verify:
aws glue get-crawler --name fsxn-athena-crawler-dev --query 'Crawler.LastCrawl.Status'

# 6. Verify: Run a test query in Athena
# Go to Athena Console → select workgroup "fsxn-verification" → run:
#   SELECT * FROM fsxn_athena_db.<discovered_table> LIMIT 10;
```

**Tear-down**:
```bash
aws cloudformation delete-stack --stack-name fsxn-athena-dev
```

### Path 2: Glue ETL Medallion Pipeline (bronze→silver→gold)

**Time**: ~8 minutes | **Cost**: ~$0.44/DPU-hour (Glue) | **VPC**: Optional

```bash
# 1. Upload ETL scripts to S3
aws s3 cp integrations/glue/scripts/ s3://YOUR-SCRIPT-BUCKET/glue-scripts/ --recursive

# 2. Deploy
aws cloudformation create-stack \
  --stack-name fsxn-glue-dev \
  --template-body file://integrations/glue/template.yaml \
  --parameters file://cfn-params/glue.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# 3. Run pipeline: Crawler → Bronze→Silver → Silver→Gold
aws glue start-crawler --name fsxn-glue-crawler-dev
```

### Path 3: DuckDB Serverless Analytics (sub-second queries)

**Time**: ~8 minutes | **Cost**: ~$0/month (pay per invocation) | **VPC**: Required

```bash
# 1. Build and upload DuckDB layer
cd integrations/duckdb && ./build-layer.sh

# 2. Deploy
aws cloudformation create-stack \
  --stack-name fsxn-duckdb-dev \
  --template-body file://integrations/duckdb/template.yaml \
  --parameters file://cfn-params/duckdb.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# 3. Test query
aws lambda invoke --function-name fsxn-duckdb-query-dev \
  --payload '{"query":"SELECT COUNT(*) FROM read_parquet('"'"'s3://YOUR-AP-ALIAS/data.parquet'"'"')"}' \
  response.json
```

### Path 4: Snowflake External Stage (two-phase trust)

**Time**: ~10 minutes | **Cost**: ~$0/month (IAM role only) | **VPC**: Not required

```bash
# Phase 1: Deploy with placeholder trust
aws cloudformation create-stack \
  --stack-name fsxn-snowflake-dev \
  --template-body file://integrations/snowflake/template.yaml \
  --parameters file://cfn-params/snowflake-phase1.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# Phase 2: In Snowflake, create Storage Integration and run DESCRIBE
# Then update stack with actual Snowflake account info
aws cloudformation update-stack \
  --stack-name fsxn-snowflake-dev \
  --template-body file://integrations/snowflake/template.yaml \
  --parameters file://cfn-params/snowflake-phase2.example.json \
  --capabilities CAPABILITY_NAMED_IAM
```

### Path 5: FPolicy Event-Driven Pipeline (file change → Snowpipe)

**Time**: ~15 minutes | **Cost**: ~$15/month (Fargate + SQS + Lambda) | **VPC**: Required

```bash
# Deploy in order: E1 → E2 → E3 → E4
for stack in fpolicy-routing fpolicy-ingestion fpolicy-server fpolicy-ip-updater; do
  aws cloudformation create-stack \
    --stack-name "fsxn-${stack}" \
    --template-body "file://shared/cloudformation/${stack}.yaml" \
    --parameters "file://cfn-params/${stack}.example.json" \
    --capabilities CAPABILITY_NAMED_IAM
  aws cloudformation wait stack-create-complete --stack-name "fsxn-${stack}"
done
```

### Path 6: Databricks Unity Catalog (VPC-scoped AP)

**Time**: ~15 minutes | **Cost**: ~$35/month (NAT GW + Interface EP) | **VPC**: Required

> **Known limitation**: Unity Catalog session policy does not currently recognize FSx for ONTAP S3 AP ARN format. The AWS-side infrastructure deploys correctly, but queries from Databricks clusters will fail with an access denied error at the UC layer. A support case is filed. For a working alternative, use the DataSync path (`poc-templates/04-databricks-integration/datasync-task.yaml`) or see [Blocker Tracker](./blocker-tracker.md). The OpenSharing pattern (Pattern E) is under analysis as a potential bypass.

```bash
# Step 1: Network infrastructure
aws cloudformation create-stack \
  --stack-name databricks-network \
  --template-body file://integrations/databricks/customer-vpc-network.yaml \
  --parameters file://cfn-params/databricks-network.example.json \
  --capabilities CAPABILITY_NAMED_IAM

aws cloudformation wait stack-create-complete --stack-name databricks-network

# Step 2: S3 AP + IAM Role
aws cloudformation create-stack \
  --stack-name databricks-s3ap \
  --template-body file://integrations/databricks/template.yaml \
  --parameters file://cfn-params/databricks.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# Step 3: Verify cross-account trust
aws sts assume-role \
  --role-arn "$(aws cloudformation describe-stacks --stack-name databricks-s3ap --query 'Stacks[0].Outputs[?OutputKey==`DatabricksRoleArn`].OutputValue' --output text)" \
  --role-session-name test \
  --external-id YOUR-EXTERNAL-ID \
  2>&1 | head -5
# If you see credentials JSON → trust is working. If AccessDenied → check ExternalId.
```

**Tear-down** (reverse order):
```bash
aws cloudformation delete-stack --stack-name databricks-s3ap
aws cloudformation wait stack-delete-complete --stack-name databricks-s3ap
aws cloudformation delete-stack --stack-name databricks-network
```

---

## Deployment Command Reference

### `create-stack` vs `deploy`

| Command | `file://` support | Capabilities | Use when |
|---|:---:|---|---|
| `aws cloudformation create-stack` | ✅ Yes | `--capabilities CAPABILITY_NAMED_IAM` | First-time deployment, JSON params from file |
| `aws cloudformation deploy` | ❌ No (S3 or inline only) | `--capabilities CAPABILITY_NAMED_IAM` | CI/CD pipelines, SAM transforms |

**Important**: `aws cloudformation deploy` does NOT support `file://` for template bodies. Use `create-stack` for local deployments with parameter files.

```bash
# ✅ Correct: create-stack with file://
aws cloudformation create-stack \
  --stack-name my-stack \
  --template-body file://path/to/template.yaml \
  --parameters file://cfn-params/my-params.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# ✅ Correct: deploy with S3 URL (for CI/CD)
aws cloudformation deploy \
  --stack-name my-stack \
  --template-file path/to/template.yaml \
  --parameter-overrides Key1=Value1 Key2=Value2 \
  --capabilities CAPABILITY_NAMED_IAM

# ❌ Wrong: deploy does NOT support --parameters file://
```

### Parameter File Format

All `cfn-params/*.example.json` files use the standard AWS CLI format:

```json
[
  {"ParameterKey": "VpcId", "ParameterValue": "vpc-0123456789abcdef0"},
  {"ParameterKey": "SubnetIds", "ParameterValue": "subnet-aaa,subnet-bbb"}
]
```

### Naming Conventions for Multi-Team Environments

When multiple teams deploy to the same account, use the `EnvironmentName` parameter to namespace resources:

| Team | EnvironmentName | Stack Name | Result |
|---|---|---|---|
| Data Engineering | `de-prod` | `de-prod-athena` | Roles: `de-prod-athena-*` |
| ML Platform | `ml-dev` | `ml-dev-duckdb` | Roles: `ml-dev-duckdb-*` |
| Analytics | `analytics-staging` | `analytics-staging-glue` | Roles: `analytics-staging-*` |

Add cost-allocation tags via `--tags Key=Team,Value=data-engineering Key=CostCenter,Value=CC-1234` on `create-stack`.

---

## Cost Reference

### Per-Integration Estimated Monthly Cost (ap-northeast-1)

| Integration | Idle Cost | Active Cost | Primary Cost Driver |
|---|---|---|---|
| Athena (B1) | $0 | Pay-per-query ($5/TB scanned) | Query volume |
| Glue ETL (B2) | $0 | $0.44/DPU-hour | ETL job duration × workers |
| DuckDB Lambda (B3) | $0 | $0.0000166667/GB-sec | Invocations × memory × duration |
| Delta Lake / EMR (B4) | $0 | EMR cluster cost | Instance hours |
| OpenSharing Server (B5) | $0 | $0.20/1M requests | Function URL invocations |
| Databricks (C1-C3) | ~$35 | +Databricks compute | NAT GW ($32) + Interface EP ($7/AZ) |
| Snowflake (D1-D2) | $0 | Snowflake compute | Warehouse credits |
| FPolicy Pipeline (E1-E4) | ~$15 | +$0.40/1M SQS msgs | Fargate ($10) + SQS EP ($7) |
| Iceberg Catalog (F1-F2) | $0 | $0.004/1K requests (S3 Tables) | Table requests |
| Manufacturing PoC (G1-G4) | ~$250 | +MSK/compute | FSx for ONTAP ($180) + MSK ($45) + NAT ($32) |

### VPC Endpoint Costs

| Endpoint | Hourly Cost (per AZ) | Monthly (2 AZ) | Data Processing |
|---|---|---|---|
| S3 Gateway | **$0** | **$0** | **$0** |
| S3 Interface | $0.014 | ~$20 | $0.01/GB |
| SQS Interface | $0.014 | ~$20 | $0.01/GB |
| STS Interface | $0.014 | ~$20 | $0.01/GB |

---

## Preflight Check

Run before any deployment:

```bash
./scripts/preflight-check.sh --integration <name>
```

Available integration names: `athena`, `glue`, `duckdb`, `databricks`, `snowflake`, `fpolicy`, `manufacturing`, `iceberg-catalog`, `all`

The script validates:
- AWS CLI version and credentials
- Target region availability
- Existing FSx for ONTAP file system status
- SVM S3 protocol configuration
- S3 Access Point existence and lifecycle state
- VPC endpoint conflicts (for VPC-based integrations)
- IAM permission adequacy
- ONTAP version compatibility

---

## Rollback Procedures

### Automatic Rollback (default)

CloudFormation automatically rolls back on CREATE_FAILED. To disable (for debugging):

```bash
aws cloudformation create-stack \
  --stack-name my-stack \
  --template-body file://template.yaml \
  --parameters file://params.json \
  --capabilities CAPABILITY_NAMED_IAM \
  --disable-rollback
```

### Manual Rollback

```bash
# Delete a failed or unwanted stack
aws cloudformation delete-stack --stack-name my-stack

# For stacks with retained resources (S3 buckets with data):
aws cloudformation delete-stack --stack-name my-stack \
  --retain-resources BucketLogicalId
```

### Rollback Order (multi-stack deployments)

Delete in **reverse** deployment order:

```bash
# FPolicy pipeline: E4 → E3 → E2 → E1
for stack in fpolicy-ip-updater fpolicy-server fpolicy-ingestion fpolicy-routing; do
  aws cloudformation delete-stack --stack-name "fsxn-${stack}"
  aws cloudformation wait stack-delete-complete --stack-name "fsxn-${stack}"
done
```

### Known Rollback Issues

| Scenario | Symptom | Resolution |
|---|---|---|
| S3 bucket not empty | DELETE_FAILED | Empty bucket first: `aws s3 rm s3://bucket --recursive` |
| IAM role in use | DELETE_FAILED | Remove role from services first, then retry |
| VPC EP in use by ENI | DELETE_FAILED | Delete dependent resources (Lambda VPC config) first |
| Log group with retention | Retained (not deleted) | Manual cleanup: `aws logs delete-log-group` |

---

## Day 2 Operations

### Updating a Stack

```bash
aws cloudformation update-stack \
  --stack-name fsxn-athena-dev \
  --template-body file://integrations/athena/template.yaml \
  --parameters file://cfn-params/athena.example.json \
  --capabilities CAPABILITY_NAMED_IAM
```

### Monitoring Stack Events

```bash
# Real-time event monitoring
aws cloudformation describe-stack-events \
  --stack-name my-stack \
  --query 'StackEvents[?ResourceStatus!=`CREATE_COMPLETE`].[Timestamp,LogicalResourceId,ResourceStatus,ResourceStatusReason]' \
  --output table
```

### CloudWatch Alarms (recommended)

After deploying Lambda-based integrations, set up:

```bash
# Lambda error rate alarm
aws cloudwatch put-metric-alarm \
  --alarm-name "fsxn-duckdb-errors" \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --dimensions Name=FunctionName,Value=fsxn-duckdb-query-dev \
  --statistic Sum --period 300 --threshold 5 \
  --comparison-operator GreaterThanThreshold \
  --evaluation-periods 1
```

### Periodic Maintenance

| Task | Frequency | Command |
|---|---|---|
| Check S3 AP lifecycle | Weekly | `aws fsx describe-s3-access-point-attachments` |
| Rotate Secrets Manager credentials | 90 days | `aws secretsmanager rotate-secret` |
| Review CloudWatch Logs retention | Monthly | Check `/aws/lambda/*` log groups |
| Verify Glue Crawler schema drift | After data changes | `aws glue start-crawler` |
| Check Fargate task health (FPolicy) | Daily | `aws ecs describe-services` |

### Getting ONTAP audit logs into a SIEM

The alarms above cover the AWS side: Lambda errors, Glue job failures, stack drift. They do
not cover what happened inside the file system. **Operations through an access point are
recorded in the ONTAP native audit log, and that log does not reach CloudWatch on its own** —
nor does it record the requesting IAM principal, which lives in CloudTrail data events for the
access point instead. The two together are what an audit trail needs.

Shipping that log to Datadog, Splunk, New Relic, Grafana or Elastic without running an EC2
collector is a solved problem in a sibling repository:
[FSx-for-ONTAP-Observability-integrations](https://github.com/Yoshiki0705/FSx-for-ONTAP-Observability-integrations).
It is not duplicated here. See also
[which repository answers your question](./repository-map.md).

---

## Troubleshooting

### Common Deployment Failures

| Error | Cause | Fix |
|---|---|---|
| `CAPABILITY_NAMED_IAM required` | Template creates named IAM resources | Add `--capabilities CAPABILITY_NAMED_IAM` |
| `S3 bucket already exists` | Global bucket name collision | Change `BucketName` parameter or use account-specific naming |
| `VPC endpoint already exists` | Only one Gateway EP per VPC per service | Skip or use existing EP ID |
| `Role already exists` | Named role from previous deployment | Delete old stack or change `EnvironmentName` |
| `Access Point creation failed` | SVM has ONTAP S3 server on same SVM | Use different SVM or remove native S3 server |
| `Timeout creating FSx resources` | FSx creation takes 30-45 min | Increase CLI timeout or use `wait` command |

### Validating S3 Access Point Connectivity

```bash
# 1. Check AP status
aws fsx describe-s3-access-point-attachments \
  --query 'S3AccessPointAttachments[].{Name:Name,Status:Lifecycle,Alias:S3AccessPoint.Alias}'

# 2. Test access (from appropriate network location)
aws s3 ls "s3://YOUR-AP-ALIAS/" --region ap-northeast-1

# 3. If timeout, check DNS resolution
nslookup YOUR-AP-ALIAS.s3.ap-northeast-1.amazonaws.com
```

---

## AD Environment for WINDOWS User Type

FSx for ONTAP S3 Access Points support three `FileSystemIdentity` types:

| Type | AD Required | Use Case |
|---|:---:|---|
| `UNIX` | No | NFS workloads, simplest setup |
| `WINDOWS` | **Yes** | NTFS-secured data, AD-authenticated access |
| `NONE` | No | Root access (testing only, not recommended) |

To test WINDOWS-type S3 APs, the SVM must be joined to an Active Directory domain (CIFS server configured).

### Quick Deploy

```bash
# 1. Deploy AD environment (choose pattern: ManagedAD, SimpleAD, or SelfManagedEC2)
aws cloudformation create-stack \
  --stack-name demo-ad-env \
  --template-body file://shared/templates/demo-ad-environment.yaml \
  --parameters file://shared/params/demo-ad-environment.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# 2. Wait for AD to become Active (~15-30 min)
aws cloudformation wait stack-create-complete --stack-name demo-ad-env

# 3. Get DNS IPs from stack outputs
DNS_IPS=$(aws cloudformation describe-stacks --stack-name demo-ad-env \
  --query 'Stacks[0].Outputs[?OutputKey==`DnsIpAddresses`].OutputValue' --output text)

# 4. Join SVM to domain
./shared/scripts/demo-ad-join-svm.sh \
  --fsxn-mgmt-ip YOUR-MGMT-IP \
  --svm-name YOUR-SVM-NAME \
  --domain lakehouse.example.com \
  --dns-ips "$DNS_IPS" \
  --secret-arn $(aws cloudformation describe-stacks --stack-name demo-ad-env \
    --query 'Stacks[0].Outputs[?OutputKey==`CredentialsSecretArn`].OutputValue' --output text)

# 5. Create WINDOWS-type S3 AP
aws fsx create-and-attach-s3-access-point \
  --name windows-test-ap --type ONTAP \
  --ontap-configuration '{"VolumeId":"YOUR-VOL-ID","FileSystemIdentity":{"Type":"WINDOWS","WindowsUser":{"Name":"LAKEHOUSE\\lakehouse-reader"}}}'
```

### Pattern Comparison

| Pattern | Deploy Time | Monthly Cost | Best For |
|---|---|---|---|
| AWS Managed Microsoft AD | ~20 min | ~$100 (Standard) | Production, multi-AZ HA |
| Simple AD | ~15 min | ~$50 (Small) | Dev/test, cost-sensitive |
| Self-Managed EC2 | ~10 min + config | ~$30 (t3.medium) | Existing domain, custom config |

### Tear-down

```bash
# Important: Unjoin SVM from domain BEFORE deleting AD
# (via ONTAP: vserver cifs delete -vserver <svm>)
aws cloudformation delete-stack --stack-name demo-ad-env
```

---

## Related Documents

- [FSx for ONTAP S3 AP Networking](./fsx-ontap-s3ap-networking.md) — VPC endpoint details, DNS resolution, timeout troubleshooting
- [Compatibility Matrix](./compatibility-matrix.md) — Platform verification status
- [Getting Started](./getting-started.md) — First-time setup walkthrough
- [Architecture](./architecture.md) — System design patterns
- [PoC Execution Guide](../implementation-guide/poc-execution-guide.md) — Step-by-step PoC checklist
