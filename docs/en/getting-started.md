# Quick Start Guide

🌐 [日本語](../ja/getting-started.md)

## Prerequisites

- AWS Account
- Amazon FSx for NetApp ONTAP (FSx for ONTAP) file system (deployed)
- S3 Access Point enabled on FSx for ONTAP SVM
- AWS CLI v2 configured
- Python 3.12+

## Step 1: Clone Repository

```bash
git clone https://github.com/Yoshiki0705/FSx-for-ONTAP-Lakehouse-Integrations.git
cd FSx-for-ONTAP-Lakehouse-Integrations
```

## Step 2: Deploy Base Infrastructure

> **Note:** Replace `<YOUR_REGION>` with your target AWS region (e.g., `us-east-1`, `ap-northeast-1`). The region is configurable and should match where your FSx for ONTAP file system is deployed.

### VPC + Networking

```bash
aws cloudformation deploy \
  --template-file shared/cloudformation/vpc-networking.yaml \
  --stack-name fsxn-lakehouse-vpc \
  --capabilities CAPABILITY_IAM \
  --region <YOUR_REGION>
```

### FSx for ONTAP + S3 Access Point

```bash
aws cloudformation deploy \
  --template-file shared/cloudformation/fsxn-s3ap-base.yaml \
  --stack-name fsxn-lakehouse-base \
  --parameter-overrides \
    VpcId=<vpc-id> \
    PreferredSubnetId=<subnet-1> \
    StandbySubnetId=<subnet-2> \
    FSxNSecurityGroupId=<sg-id> \
    S3BucketName=<svm-bucket-name> \
  --capabilities CAPABILITY_IAM \
  --region <YOUR_REGION>
```

## Step 3: Validate Connectivity

```bash
# Get S3 AP alias from CloudFormation output
AP_ALIAS=$(aws cloudformation describe-stacks \
  --stack-name fsxn-lakehouse-base \
  --query 'Stacks[0].Outputs[?OutputKey==`S3AccessPointAlias`].OutputValue' \
  --output text)

# Run connectivity test (uses AWS_DEFAULT_REGION env var, or specify --region)
python shared/scripts/validate-access.py --access-point-alias $AP_ALIAS --region <YOUR_REGION>
```

## Step 4: Choose Vendor Integration

| Vendor | Directory | Status |
|--------|-----------|--------|
| Athena | `integrations/athena/` | ✅ Security Verified |
| Glue | `integrations/glue/` | ✅ Functional Verified |
| Delta Lake OSS | `integrations/delta-lake-oss/` | ✅ Read Verified / ❌ Write |
| Databricks | `integrations/databricks/` | ⚠️ Blocked (UC does not support S3 Tables) |
| Snowflake | `integrations/snowflake/` | ✅ Verified (Iceberg via Glue REST + VENDED_CREDENTIALS; External Stage via S3 AP) |

See each vendor's `README.md` and `docs/en/setup-guide.md` for details.

## Next Steps

- [Architecture Overview](architecture.md)
- [Supported Regions](supported-regions.md)
- [Vendor Comparison](vendor-comparison.md)
