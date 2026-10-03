**English** | [日本語](../ja/databricks-verification-runbook.md)

# Runbook: Unity Catalog on an FSx for ONTAP S3 Access Point

Reproduce the 2026-08-12 verification in your own account, in about 45 minutes of
wall-clock time and under 2 USD, and tear it down the same day.

## What you will find, and what you will not

Be clear on the expected outcome before you start, because "it failed" is the
result and it is not a mistake on your part:

| Step | Expected result |
|---|---|
| Register a storage credential, an external location and an external volume on an Access Point alias | ✅ Succeeds, with Unity Catalog's own validation enabled |
| Read through them (`read_files`, `list_files`, `to_file`, `dbutils.fs.ls`) | Denied with 403 |
| The same read against a native S3 bucket | ✅ Succeeds, object tags populated |

The read is denied because AWS authorises an Access Point request against the
**access point ARN**, while the down-scoped session policy Unity Catalog attaches
when it vends credentials is written in **bucket-style** ARNs. A session policy
intersects with the role policy, so the access point ARN grant in your role never
comes into play. There is no workaround on your side.

If your run shows the Access Point read **succeeding**, that is news: the platform
has changed. Record which Databricks release you were on and open an issue.

> **Why the control matters.** This repository recorded, from May to August 2026,
> that "Unity Catalog External Location does not support S3 Access Points". That
> wording was wrong, and it survived three months because the original attempt had
> no native-S3 control running the same test. A bare failure cannot be told apart
> from a mistake in your own IAM setup. Every step below keeps the control.

## Prerequisites

| Requirement | How to check |
|---|---|
| An FSx for ONTAP file system with an S3 Access Point | `aws fsx describe-s3-access-point-attachments --region <region> --query 'S3AccessPointAttachments[].{name:Name,alias:S3AccessPoint.Alias,state:Lifecycle}' --output table` |
| A Databricks workspace **in the same AWS account and region** as the file system | See "Which workspace" below |
| Permission to create an IAM role and an S3 bucket | `AdministratorAccess` is more than enough; `iam:CreateRole` plus S3 create is the minimum |
| AWS CLI, Python 3.9+, `databricks-sdk` | `aws --version`, `python3 -V`, `python3 -c "import databricks.sdk"` |
| A SQL warehouse in the workspace | The probe starts a stopped one for you |

Install the SDK into a virtual environment rather than system Python, which is
what PEP 668 will make you do anyway:

```bash
python3 -m venv .venv
.venv/bin/pip install databricks-sdk
```

Create a Databricks CLI profile. The token needs the `unity-catalog`, `files` and
`sql` scopes. Two later steps need more, and it is cheaper to know now than to
regenerate: `--vend-check` needs `all-apis`, and revoking the token by API needs
`authentication`.

```ini
# ~/.databrickscfg   (chmod 600)
[fsxn-verify]
host  = https://<your-workspace-host>
token = <personal access token>
```

## Which workspace

The workspace has to sit in the same account and region as the file system,
because a Unity Catalog storage credential reaches into that account.

| Option | Works for this test? | Cost |
|---|---|---|
| 14-day trial workspace | No. Serverless-only, so no storage credential into your account | Free |
| Non-trial, "Use your existing cloud account", same region | ✅ This is the one | See the cost table |
| Existing workspace in another region | ⚠️ Cross-region adds a variable you do not want in a verification | Whatever it already costs |

"Use your existing cloud account" creates a VPC with a NAT Gateway inside your
account. It also asks for a temporary IAM delegation; read that policy rather than
approving it blind, especially in a shared account. Full cost and decision notes:
[Databricks verification environment and cost](./databricks-verification-environment-cost.md).

## Step 1 — record a baseline

Do this **before** creating anything. Without it, "the teardown looks clean" is
not a verifiable claim, and in a shared account most of what you see belongs to
other people.

```bash
python3 shared/scripts/audit_databricks_workspace_footprint.py \
  --region <region> --save /tmp/fsxn-baseline.json
```

## Step 2 — deploy the IAM role and the control bucket

```bash
cp cfn-params/databricks-uc-storage-credential.example.json \
   cfn-params/databricks-uc-storage-credential.json
# edit the copy: your Databricks account UUID, Access Point name and alias
```

Your filled-in copy is gitignored, so it will not be committed by accident.

```bash
aws cloudformation deploy \
  --region <region> \
  --stack-name fsxn-databricks-uc-credential \
  --template-file integrations/databricks/uc-storage-credential-role.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides file://cfn-params/databricks-uc-storage-credential.json

aws cloudformation describe-stacks --region <region> \
  --stack-name fsxn-databricks-uc-credential \
  --query 'Stacks[0].Outputs' --output table
```

Two parameters decide whether this works, and both produce a 403 that reads like
"Access Points are not supported":

- **`DatabricksAccountId` is the account UUID.** Not the metastore ID, not the
  workspace ID. It is what the storage credential presents as `sts:ExternalId`.
- **The IAM policy needs the access point ARN.** The template grants both the
  access point ARN and the alias-as-bucket ARN, so this only bites if you write
  the policy yourself.

Note the asymmetry the outputs restate: the external location **URL** must use
the alias form (`s3://<alias>/`), because the ARN-style URL is rejected with
`url does not specify a valid bucket name`, while the IAM **policy** wants the ARN
form.

## Step 3 — run the comparison

The stack's `NextStep` output is the command, with the ARNs already filled in:

```bash
.venv/bin/python shared/scripts/probe_uc_external_location.py \
  --profile fsxn-verify \
  --role-arn <from stack output> \
  --ap-alias <your alias>-ext-s3alias \
  --ap-name <your access point name> \
  --control-bucket <from stack output> \
  --region <region>
```

`--control-bucket` is required on purpose. Add `--vend-check` for the decisive
test described in step 4, and `--teardown-after` to clean up the Unity Catalog
objects in the same run.

## Step 4 — read the verdict

The script prints one of three conclusions. They are not pass/fail:

| Verdict | Meaning | What to do |
|---|---|---|
| **Inconclusive** — the control could not be read | Your harness is wrong, not the platform | Check the external ID printed by the script against the role's trust policy, and that the role grants the control bucket |
| **Registration works, read denied** | The 2026-08-12 result | Nothing to fix on your side. This is [BLK-001](./blocker-tracker.md#blk-001-uc-credential-vending-does-not-authorise-s3-ap-reads) |
| **Registration and read both work** | The platform changed | Note the Databricks release and open an issue against this repository |
| **Registration itself fails** | Almost always the access point ARN missing from the IAM policy | Compare your policy against the template |

`--vend-check` settles the question without involving Databricks compute at all.
It asks Unity Catalog for the credentials it would use, then exercises them from
your machine. Same role, same session, same network; the only variable is which
path the credential was scoped to. If the control succeeds and the Access Point is
denied, the session policy is the cause and nothing in your IAM or networking can
change it.

It needs two things that are off by default, and reports which one is missing
rather than failing opaquely:

```sql
-- metastore admin
ALTER METASTORE SET external_access_enabled = true;
GRANT EXTERNAL USE SCHEMA   ON SCHEMA <catalog>.<schema> TO `you@example.com`;
GRANT EXTERNAL USE LOCATION ON EXTERNAL LOCATION <name>  TO `you@example.com`;
```

These are real governance controls. Turn them back off afterwards if the metastore
is shared.

## Step 5 — tear down, in this order

Order matters. Two steps fail if you go straight at them.

```bash
# 1. Unity Catalog objects created by the probe
.venv/bin/python shared/scripts/probe_uc_external_location.py \
  --profile fsxn-verify --teardown-only \
  --control-bucket <bucket> --ap-alias <alias>

# 2. the probe's objects on the Access Point are removed by the step above;
#    the bucket and role belong to the stack
aws s3 rm s3://<control-bucket> --recursive --region <region>
aws cloudformation delete-stack --region <region> \
  --stack-name fsxn-databricks-uc-credential
aws cloudformation wait stack-delete-complete --region <region> \
  --stack-name fsxn-databricks-uc-credential

# 3. verify against the baseline from step 1
python3 shared/scripts/audit_databricks_workspace_footprint.py \
  --region <region> --compare /tmp/fsxn-baseline.json
```

If you also created a workspace for this, delete it in the Databricks account
console **and then** remove the AWS resources it left behind. Deleting the
workspace removes none of them, because they are created directly rather than as
a CloudFormation stack:

| Order | Resource | Gotcha |
|---:|---|---|
| 1 | NAT Gateway | Must be `deleted`, not `deleting`, before the subnets go |
| 2 | Elastic IP | Release it, or it keeps charging |
| 3 | S3 gateway endpoint | — |
| 4 | Internet gateway | Detach before delete |
| 5 | Subnets | — |
| 6 | Security groups | Revoke ingress **and** egress rules first, or deletion fails on dependencies |
| 7 | Route tables | The main route table cannot be deleted separately; it goes with the VPC |
| 8 | VPC | Fails with `DependencyViolation` until 1–7 are done |
| 9 | Workspace S3 bucket | Empty it first |
| 10 | The two `databricks-*-role-*` IAM roles | Delete inline policies first |

Then re-run the audit and expect zero differences from your baseline.

## Cost

Measured for a same-day run in ap-northeast-1, 2026-08-12. Prices retrieved that
day; re-check before quoting them.

| Item | Cost |
|---|---|
| NAT Gateway (workspace VPC) | 0.062 USD/hour + 0.062 USD/GB — about 45 USD/month if forgotten |
| Classic single-node cluster, `m5d.large` | 0.146 USD/hour instance + DBU |
| Serverless SQL warehouse, Small | 1.00 USD/DBU-hour in this region |
| S3 control bucket | Negligible; objects expire after 7 days |
| IAM role, external locations | Free |

The NAT Gateway is the one that matters. Everything else in this runbook stops
costing money when you stop using it; a NAT Gateway does not.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `403 Forbidden` from the storage provider when creating the credential | The external ID is not the Databricks account UUID |
| `AccessDeniedException` on the external location, control works | The IAM policy lacks the access point ARN form |
| `url does not specify a valid bucket name` | You used the ARN-style URL; use the alias form |
| `/…/_delta_log: … statusCode: 403` on read | The session policy issue. Expected — this is the finding |
| `LIST_FILES_AUTHORIZATION_ERROR.ON_PATH` even with `READ VOLUME` granted | Same cause. The privilege is not what is missing |
| `Cannot get file metadata under managed storage` | Unrelated to Access Points: a `FILE MANAGED` FileSpace is pointing at the volume that holds the source files. Use a dedicated volume |
| `External Data Access … is disabled` | `--vend-check` needs `external_access_enabled` on the metastore |
| `Provided access token does not have required scopes: all-apis` | `--vend-check` needs a token with `all-apis` |
| `Invalid principal` when hand-writing the trust policy | You named the role as its own principal before it existed. The template uses account root plus an `aws:PrincipalArn` condition instead |
| Bucket name error during stack creation | The role name is too long; the control bucket is derived from it |

## What this runbook does not cover

- VPC-origin Access Points, and Access Points with `WINDOWS` identity. One
  INTERNET-origin, UNIX-root Access Point was exercised.
- Whether `_object_metadata` would read object tags through an Access Point if the
  session policy were widened. The read is refused before reaching that code.
- Throughput or latency of any of these paths.
- The FILE type itself beyond registration. For that see
  [Databricks FILE type evaluation](./databricks-file-type-evaluation.md).

## Related

- [Databricks FILE type evaluation](./databricks-file-type-evaluation.md) — the analysis this runbook came from
- [Databricks verification environment and cost](./databricks-verification-environment-cost.md) — trial vs non-trial, and what a run costs
- [Blocker tracker BLK-001](./blocker-tracker.md#blk-001-uc-credential-vending-does-not-authorise-s3-ap-reads) — the corrected blocker
- [Compatibility matrix](./compatibility-matrix.md) — where this sits among the other engines
- Evidence: [2026-08-12 run](../../verification-pack/databricks/file-type/evidence/2026-08-12/evidence-record-tokyo.yaml)
