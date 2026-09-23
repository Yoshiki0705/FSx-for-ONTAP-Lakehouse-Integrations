🌐 **English** | [日本語](../ja/databricks-verification-environment-cost.md)

# Standing Up a Databricks Workspace to Verify FSx for ONTAP Integration: Cost and Decision Axes

> **Status**: Prices retrieved 2026-08-12 from primary sources — Databricks' own pricing data file and the AWS Price List API. Rates change; re-check before quoting.
> **Evidence tier**: **Public** (published rates) / **Verified** (observed in this account) / **Project-context** (our decision) / **Hypothesis**.
> **Why this page exists**: two of our verification cases could not be answered on the workspace we had, and working out *why* turned out to be more useful than the price list. The blocker was not the plan tier or the price. It was the workspace's storage mode and its region.

---

## Executive Summary

- **The plan tier is usually not the blocker.** A workspace on a credit-funded Premium plan could create Unity Catalog storage credentials perfectly well (**Verified**). What it could not do was launch classic compute, because it was created as a **"Serverless only"** workspace.
- **Two attributes decide whether a workspace can verify FSx for ONTAP integration at all**: its **region** (must match the FSx file system) and its **storage and compute mode** (must be "use your existing cloud account" if you need an instance profile).
- **The dominant cost is not compute.** It is the **NAT Gateway** inside the Databricks-managed VPC, at **$0.062/hour in ap-northeast-1 — about $45/month — billed whether or not any cluster runs.**
- **Databricks credits do not pay for AWS infrastructure.** Credits cover DBUs. EC2, NAT Gateway and S3 bill to the AWS account separately. A "$400 of free credit" balance does not make the exercise free.
- **Tokyo is at parity with Oregon for classic compute and ~43% more expensive for SQL Serverless** ($1.00 vs $0.70 per DBU, Premium).
- **Teardown is the real risk, and it is not a single stack delete.** With the automatic setup path, Databricks creates the IAM roles, S3 bucket and VPC **directly**, not as a CloudFormation stack. Deleting the workspace does not remove them.

---

## 1. What actually determines whether a workspace can do the job

**Evidence tier: Verified** in this account, 2026-08-12.

Before comparing prices, check three things. Getting these wrong means paying for a workspace that cannot answer the question.

| Attribute | Requirement | Why |
|---|---|---|
| **Region** | Must match the FSx for ONTAP file system | An S3 Access Point can only exist in the region of its volume. Co-locating compute avoids cross-region latency and egress, and matches the [region design guidance](./region-design-guide.md) |
| **Storage and compute mode** | **"Use your existing cloud account"** if you need classic compute | A "Serverless only" workspace cannot launch classic clusters, so it cannot use an instance profile. Without an instance profile the only route to an Access Point is a Unity Catalog external location — which is exactly what [BLK-001](./blocker-tracker.md#blk-001-uc-credential-vending-does-not-authorise-s3-ap-reads) blocks |
| Plan tier | Premium is sufficient | Enterprise costs more per DBU and adds compliance features not needed for this. Notably, a credit-funded Premium workspace **could** create UC storage credentials |

> **The trap worth naming**: it is easy to read "trial" or "free credits" as "feature-limited" and conclude that a paid plan is the fix. In our case the plan was already Premium and storage credentials worked. The limitation was the **storage mode chosen at workspace creation**, which is not something you can change later — you create another workspace.

---

## 2. Published rates

### Databricks DBU rates

**Evidence tier: Public** — from the pricing data file that `databricks.com/product/pricing` renders, retrieved 2026-08-12.

| SKU | AP (Tokyo) Premium | AP (Tokyo) Enterprise | US West (Oregon) Premium |
|---|---|---|---|
| Jobs Compute / Photon | **$0.15** | $0.20 | $0.15 |
| All-Purpose / Photon | **$0.55** | $0.65 | $0.55 |
| SQL Classic | $0.22 | $0.22 | — |
| SQL Pro | $0.78 | $0.78 | — |
| SQL Serverless | **$1.00** | $1.00 | **$0.70** |
| Jobs Serverless | $0.39 | — | — |

Classic compute is priced the same in Tokyo as in Oregon. **SQL Serverless is about 43% more expensive in Tokyo.** If a workload is serverless-SQL-heavy, region choice has a real price consequence; for classic compute it does not.

> **Jobs Compute is roughly a quarter the price of All-Purpose** ($0.15 vs $0.55). For a scripted verification that does not need an interactive notebook, running it as a job is the cheaper shape. Use All-Purpose when interactive debugging is worth the difference.

### AWS rates, ap-northeast-1

**Evidence tier: Public** — AWS Price List API, effective 2026-08-01.

| Resource | Rate |
|---|---|
| m5d.large (2 vCPU, 8 GiB) | $0.146 / hour |
| m5d.xlarge (4 vCPU, 16 GiB) | $0.292 / hour |
| r5d.large (2 vCPU, 16 GiB) | $0.174 / hour |
| **NAT Gateway** | **$0.062 / hour** + $0.062 / GB processed |

---

## 3. The cost that dominates

```
NAT Gateway:  $0.062/h x 24 x 30  =  ~$44.6 / month, idle
Verification: single node m5d.large, All-Purpose, 6 hours  =  ~$4.2
```

The infrastructure that exists to support the compute costs an order of magnitude more than the compute, because it bills continuously while the compute bills only when running.

Two consequences:

1. **Duration matters far more than instance size.** Choosing a larger node changes cents. Leaving the workspace up for a month changes tens of dollars.
2. **Credits do not protect you.** Databricks credits are consumed by DBUs. The NAT Gateway is an AWS charge. A workspace sitting idle on "free" Databricks credits still accrues AWS charges.

> **Cost note**: verify whether the managed VPC provisions one NAT Gateway or one per availability zone before accepting the estimate. A per-AZ layout multiplies this line. Inspect the VPC after creation rather than assuming.

---

## 4. Decision matrix

**Evidence tier: Project-context** — our decision for this repository's open cases.

| Option | AWS cost | Databricks cost | Can it verify an Access Point read? |
|---|---|---|---|
| **A. Serverless workspace, co-located region** | $0 | SQL Serverless at $1.00/DBU | ❌ No. Serverless-only means no instance profile, so the only path is a UC external location, which BLK-001 blocks |
| **B. "Use your existing cloud account", co-located region** | NAT Gateway ~$1.5/day + EC2 while running | Jobs $0.15 or All-Purpose $0.55 per DBU | ✅ **Yes — the only option that can** |
| **C. Reuse an existing workspace in another region** | $0 | same as its mode allows | ❌ No, if it is serverless-only. Cross-region also adds egress and latency |

Option A is still worth a few dollars for one narrow purpose: re-confirming BLK-001 on a **current** workspace and capturing today's error message. That is evidence, just not the evidence we need.

**Choose B, and treat teardown as part of the task rather than a follow-up.**

---

## 5. Teardown is not a stack delete

**Evidence tier: Verified** — observed in the workspace creation flow, 2026-08-12.

With the automatic setup path, the review step lists exactly what will be created:

| Purpose | Resource |
|---|---|
| Cloud storage | IAM role `databricks-storage-role-<workspace-id>` |
| Cloud storage | S3 bucket `databricks-storage-<workspace-id>` |
| Cloud storage | Access policy `databricks-uc-storage-policy-<workspace-id>` |
| Cloud credentials | IAM role `databricks-compute-role-<workspace-id>` |
| Cloud credentials | **VPC `databricks-compute-vpc-<workspace-id>`** — contains the NAT Gateway |
| Cloud credentials | Access policy `databricks-compute-policy-<workspace-id>` |

These are created **directly through delegated IAM permissions, not as a CloudFormation stack**. There is no stack to delete, so teardown means removing each resource — and the VPC is the one that costs money.

**Deleting the Databricks workspace does not delete any of them.** That asymmetry is how an idle NAT Gateway survives for months.

Verify teardown rather than trusting it:

```bash
# must return 0
aws ec2 describe-nat-gateways --region <region> \
  --filter Name=state,Values=available --query 'length(NatGateways)' --output text

# the VPC and bucket, by naming convention
aws ec2 describe-vpcs --region <region> \
  --filters 'Name=tag:Name,Values=databricks-compute-vpc-*' --output json
aws s3api list-buckets --output json   # look for databricks-storage-<workspace-id>
```

> **Record the baseline before creating anything.** We counted zero available NAT Gateways in the target region first, so that any NAT Gateway found afterwards is unambiguously ours. Without that baseline, teardown verification cannot distinguish our resources from pre-existing ones.

Leftover IAM roles from earlier workspaces cost nothing but accumulate. We found roles from a workspace created six weeks earlier still present. Worth a periodic sweep by naming convention.

---

## 6. Interactive steps you cannot automate

**Evidence tier: Verified.**

The automatic setup path ends with **"Log in to AWS and create workspace"**, which opens an AWS Console sign-in and an IAM access-request review. That sign-in requires an **MFA code**.

AWS CLI credentials are not sufficient — this is a console flow, not an API call. Plan for a human at this step, and note that everything before it (naming, region, storage mode, reviewing the resource list) can be prepared in advance.

If you want a fully scriptable path instead, create the credential configuration, storage configuration and network configuration yourself and register them through the account API, then create the workspace referencing them. That trades an interactive MFA prompt for writing and owning the IAM and VPC definitions.

---

## 7. Actuals from the standard-S3 unstructured-data AI PoC

**Evidence tier: Verified / Public** (measured 2026-09-23; unit prices re-confirm before quoting).

Running the [standard-S3 unstructured-data AI PoC](./databricks-standard-s3-unstructured-poc.md) surfaced cost facts that the price tables above do not capture:

- **Pay-per-token Foundation Models are US-region only.** A Tokyo (ap-northeast-1) workspace has no default Serving endpoints, so `ai_query` / `ai_parse_document` cannot be called there as-is. The PoC ran on a us-west-2 workspace. If AI Functions are the goal, region selection is a functionality gate, not just a price difference.
- **Serverless SQL Warehouse (Small, 10-minute auto-stop)** covered the AI Functions, OCR and Vision at metered, small cost.
- **Vector Search is an always-on endpoint charge with a 24-hour tail.** Per Databricks documentation, the endpoint is billed after an index is created, and billing stops only 24 hours after the last index is deleted. Tearing the endpoint down does not stop the charge immediately. Budget for the tail.
- **The embedding model `databricks-gte-large-en` is high-latency pay-per-token**, which contributes to slow first-index sync. In the PoC the index stayed in `PROVISIONING_ENDPOINT` for ~16 minutes without reaching ONLINE (environment-dependent; reported repeatedly in the community).
- **Teardown checklist for this PoC shape**: Vector Search index → endpoint (verify with `list_endpoints`), then the standard S3 bucket, the IAM role for the storage credential, the UC External Location + auto-generated storage credential, and the catalog/schema/volume/tables. None of these is large, but the Vector Search 24-hour tail is the one to watch.

---

## References

- [Databricks pricing](https://www.databricks.com/product/pricing) · [AWS pricing by Databricks](https://www.databricks.com/product/aws-pricing)
- [Serverless workspaces](https://docs.databricks.com/admin/workspace/serverless-workspaces)
- [AWS NAT Gateway pricing](https://aws.amazon.com/vpc/pricing/) · [Amazon EC2 pricing](https://aws.amazon.com/ec2/pricing/on-demand/)
- This repo: [blocker tracker](./blocker-tracker.md) (BLK-001) · [region design guide](./region-design-guide.md) · [FILE type evaluation](./databricks-file-type-evaluation.md) · [Databricks integration](../../integrations/databricks/README.md)
