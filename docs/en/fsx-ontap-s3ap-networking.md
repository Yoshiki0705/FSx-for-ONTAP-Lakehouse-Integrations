# FSx for ONTAP S3 Access Points Networking Considerations

## Overview

Amazon FSx for NetApp ONTAP S3 Access Points have specific networking requirements that differ from regular S3 bucket access. This document consolidates findings from multiple verification rounds.

## Key Findings

### 1. S3 Gateway Endpoint and FSx for ONTAP S3 Access Points

Known issue (documented in [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)): a VPC-internal Lambda times out when it reaches an internet-origin AP through the S3 Gateway EP. Place the Lambda outside the VPC, or route it through a NAT Gateway.

Explanation: When a VPC-attached Lambda or EC2 instance accesses an internet-origin FSx for ONTAP S3 Access Point, the S3 Gateway VPC Endpoint may intercept the traffic but fail to route it correctly to the backend. This is because FSx for ONTAP S3 Access Points aliases resolve to `s3-r-w.<region>.amazonaws.com`, which may not be handled the same way as standard S3 bucket traffic by the Gateway endpoint.

Workarounds:

1. Place Lambda outside the VPC (no VPC attachment). Simplest for internet-origin APs
2. Use NAT Gateway for outbound S3 Access Points traffic
3. Remove the S3 Gateway endpoint from the specific route table (not recommended for production; breaks regular S3 access optimization)

### 2. Internet-Origin vs VPC-Origin

| AP Type | Access from VPC Lambda | Access from non-VPC Lambda | Access from EC2 (public subnet) |
|---------|----------------------|---------------------------|-------------------------------|
| Internet-origin | May timeout via Gateway EP | Works | Works (via IGW) |
| VPC-origin | Works (via Interface EP) | Blocked by design | Works (same VPC) |

### 3. AWS Service Access Patterns

| Service | Network Path | FSx for ONTAP S3 Access Points Compatibility |
|---------|-------------|------------------------|
| Athena | AWS-managed (no customer VPC) | Internet-origin required |
| Glue ETL | AWS-managed or VPC-attached | Internet-origin (non-VPC) or NAT Gateway (VPC) |
| EMR Serverless | AWS-managed | Internet-origin required |
| Lambda (no VPC) | Internet | Internet-origin works directly |
| Lambda (VPC-attached) | VPC routing | Requires NAT Gateway or no S3 Gateway EP |
| Redshift Spectrum | AWS-managed | Internet-origin required |
| Databricks | Customer-managed VPC | Session policy blocks (separate issue) |

### 4. DNS Resolution

FSx for ONTAP S3 Access Points aliases resolve differently from regular S3 buckets.

```text
Regular S3 bucket:
  my-bucket.s3.ap-northeast-1.amazonaws.com → S3 service IPs (in prefix list)

FSx for ONTAP S3 Access Points alias:
  my-ap-alias-ext-s3alias.s3.ap-northeast-1.amazonaws.com → s3-r-w.ap-northeast-1.amazonaws.com
```

The `s3-r-w` hostname is the FSx for ONTAP S3 Access Points backend. Its IP addresses may or may not be included in the S3 prefix list (`pl-61a54008` for ap-northeast-1) used by S3 Gateway endpoints.

### 5. Troubleshooting Checklist

When FSx for ONTAP S3 Access Points access times out, check the following.

1. Verify DNS resolution: `nslookup <alias>.s3.<region>.amazonaws.com`
2. Verify TCP connectivity: `curl -s -o /dev/null -w '%{http_code}' --max-time 5 https://<alias>.s3.<region>.amazonaws.com/`
3. Test regular S3: `aws s3 ls s3://<regular-bucket>/`. If this works, the issue is S3 Access Points specific
4. Check the S3 Gateway endpoint: is the route table associated with a Gateway endpoint? If yes, try removing it temporarily
5. Check AP lifecycle: `aws fsx describe-s3-access-point-attachments` should report AVAILABLE
6. Check volume status: `aws fsx describe-volumes --volume-ids <vol-id>` should report CREATED/AVAILABLE
7. Check SVM S3 protocol: ensure the SVM has S3 protocol enabled and the volume is mounted

### 6. Recommended Architecture for VPC-Internal Access

```text
┌─────────────────────────────────────────────────────────────────┐
│  VPC                                                             │
│                                                                  │
│  ┌──────────────────┐     ┌──────────────────┐                  │
│  │ Private Subnet    │     │ Public Subnet     │                  │
│  │ (Lambda/EC2)      │────▶│ NAT Gateway       │────▶ IGW ──▶ FSx for ONTAP S3 Access Points
│  │                   │     │                   │                  │
│  └──────────────────┘     └──────────────────┘                  │
│         │                                                        │
│         │ S3 Gateway EP (for regular S3 bucket access)           │
│         └──────────────────────────────────────▶ S3 Service      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

For VPC-internal workloads that need both regular S3 and FSx for ONTAP S3 Access Points, keep the S3 Gateway endpoint for regular S3 bucket access (free, low latency) and route FSx for ONTAP S3 Access Points traffic through a NAT Gateway (or place compute outside the VPC).

---

## 7. SVM DNS/AD Configuration and S3 Access Points Availability

### S3 Access Points ReadTimeout Caused by Unreachable DNS Servers

If an SVM has DNS servers configured (for Active Directory domain membership) and those DNS servers become unreachable, all S3 Access Points on that SVM time out. This happens even when:

- The S3 Access Points volumes use UNIX security style
- Customer-configured FPolicy is disabled
- NFS export policies allow all access
- The S3 Access Points lifecycle state is AVAILABLE

This is because the S3 Access Points request processing path traverses the SVM's name-service stack. When CIFS/AD is configured, ONTAP attempts user-mapping resolution (UNIX and Windows), which requires DNS communication with domain controllers.

### Root Cause Mechanism

```text
S3 API Request
  → FSx for ONTAP S3 Access Points backend
    → SVM file system access
      → ONTAP name-service stack (ns-switch: files, dns)
        → CIFS server present → user-mapping requires DC lookup
          → DNS query to configured servers (e.g., 10.0.x.x)
            → DNS servers unreachable → timeout (30+ seconds)
              → S3 API client receives ReadTimeout
```

### Authentication Mode Behavior Matrix

| SVM Configuration | DNS Dependency for S3 Access Points | Behavior if DNS Down |
|---|---|---|
| NFS-only (no CIFS, no DNS) | None | Works normally |
| CIFS Workgroup mode (no AD) | None | Works normally |
| CIFS + AD domain join + DNS configured + DNS reachable | Yes (but transparent) | Works normally |
| CIFS + AD domain join + DNS configured + DNS unreachable | Yes (blocks) | ReadTimeout |
| FPolicy configured (any state) + no CIFS/DNS | None | Works normally |

Key insight: the DNS dependency is triggered by the presence of a CIFS server joined to an AD domain, not by FPolicy, export policies, or volume security style.

### Diagnostic Commands

```bash
# 1. Check DNS configuration on the SVM
vserver services dns show -vserver <SVM_NAME>

# 2. Check DNS server reachability (CRITICAL)
vserver services dns check -vserver <SVM_NAME>
# If status shows "down" or "Operation timed out" → this is likely the cause

# 3. Check CIFS/AD membership
vserver cifs show -vserver <SVM_NAME>

# 4. Check ns-switch configuration
vserver services name-service ns-switch show -vserver <SVM_NAME>
# Look for "dns" in the hosts database sources
```

### Resolution Options

Option A: Remove DNS and CIFS (if AD/SMB not needed)

```bash
# Force-delete CIFS (AD server may be gone, use force flag)
set adv -c off
vserver cifs delete -vserver <SVM_NAME> -admin-username x -admin-password x -force-account-delete true

# Delete DNS configuration
vserver services dns delete -vserver <SVM_NAME>

# Remove DNS from ns-switch
vserver services name-service ns-switch modify -vserver <SVM_NAME> -database hosts -sources files
```

Option B: Point DNS to a reachable server (if AD/SMB needed)

```bash
# Update DNS to VPC-provided DNS (AmazonProvidedDNS)
# For VPC CIDR 10.0.0.0/16, the resolver is at 10.0.0.2
vserver services dns modify -vserver <SVM_NAME> -name-servers 10.0.0.2 -domains <domain>
```

Note: Option B restores DNS resolution but CIFS/AD authentication fails unless the domain controller is also reachable.

Option C: Restore the AD domain controller. Recreate the AD server at the same IP addresses. This is the heaviest option and only necessary if CIFS/SMB access with AD authentication is required.

### Verified Behavior (2026-05-24)

| Test | SVM | DNS Config | CIFS/AD | S3 Access Points Result |
|------|-----|-----------|---------|-------------|
| Before fix | ad-joined-svm | `<DNS-IP-1>, <DNS-IP-2>` (both DOWN) | AD domain join | ReadTimeout |
| Before fix | verification-svm | None | None | Instant success |
| After fix (Option A) | ad-joined-svm | Removed | Removed | Instant success |

### Prevention

- Do not leave orphaned DNS/AD configurations. If an AD domain controller is decommissioned, remove the CIFS server and DNS settings from the SVM.
- Monitor DNS health. Periodically run `vserver services dns check` to verify DNS servers are reachable.
- Separate concerns. If S3 Access Points access is the primary use case, consider using a dedicated SVM without CIFS/AD dependencies. This eliminates the DNS dependency entirely.
- Document AD server lifecycle. Track which SVMs depend on which AD servers, so decommissioning an AD server triggers SVM configuration cleanup.

---

## References

- [FSx for ONTAP S3 Access Points documentation](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)
- [Configuring network access for S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/configuring-network-access-for-s3-access-points.html)
- [S3 Gateway endpoints](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-s3.html)
- [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns — s3ap-authorization-model.md](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/blob/main/docs/s3ap-authorization-model.md)
