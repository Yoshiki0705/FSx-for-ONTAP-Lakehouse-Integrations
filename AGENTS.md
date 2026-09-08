# AGENTS.md

> Data Lake and Lakehouse platform integrations with Amazon FSx for NetApp ONTAP via S3 Access Points

## Project Overview

This repository provides integration patterns for connecting Amazon FSx for NetApp ONTAP to AWS analytics services (Athena, Glue, EMR, SageMaker, DuckDB, Snowflake, Databricks) via S3 Access Points. It contains 28+ CloudFormation templates, verification scripts, and bilingual documentation (JA/EN).

## Build & Test Commands

```bash
# Install dependencies
npm install

# Run tests
npm test

# Validate all CFn parameter files
for f in cfn-params/*.json shared/params/*.json; do python3 -c "import json; json.load(open('$f'))"; done

# Run preflight check before deploying
./scripts/preflight-check.sh --integration athena
```

## Coding Conventions

- Python 3.12 for Lambda functions (arm64 preferred)
- TypeScript for CDK/infrastructure code
- Structured JSON logging
- Property-based tests with Hypothesis
- CloudFormation parameter files: `[{"ParameterKey":"X","ParameterValue":"Y"}]` format
- Example IPs: RFC 5737 range (`198.51.100.x`) — never use real IPs

## Supply-Chain Security

Enforced by pre-commit hooks (`.githooks/pre-commit`) and CI workflows:

| Workflow | File | Purpose |
|----------|------|---------|
| zizmor | `.github/workflows/zizmor.yml` | GitHub Actions security linting |
| gitleaks | `.github/workflows/gitleaks.yml` | Secret detection (custom rules in `.gitleaks.toml`) |
| OpenSSF Scorecard | `.github/workflows/scorecard.yml` | Security health scoring |
| Renovate | `renovate.json` | Automated dependency updates |

**Actions pinning**: All third-party Actions pinned to SHA hashes. Verify: `zizmor .github/workflows/`

**gitleaks allowlist**: `cfn-params/` and `shared/params/` are globally allowlisted (example data only).

## Agent Output Standards

> Full rules in global Kiro steering. Summary enforced by `.github/workflows/agent-output-audit.yml`.

- **Naming**: "FSx for ONTAP" (never FSx for ONTAP/bare FSx). "FSx for ONTAP S3 AP" for access points.
- **Neutrality**: No vendor-versus framing. Present trade-offs symmetrically.
- **Safety**: No PII, account IDs, internal IPs, persona names in public output.
- **Bilingual**: JA/EN parity (same section structure/count).
- **JA/EN numeric parity**: unit-bearing quantities (byte sizes, their `/s` rate forms,
  percentages) must agree between an EN document and its JA twin. **Section-count parity does not
  imply this** — the same table said "PutObject 5 GB ceiling" in EN and "50 GB 上限" in JA while
  section counts matched. Usually the mismatch is a signal about the original, not the translation.
  - `python3 scripts/check-doc-number-parity.py --selftest && python3 scripts/check-doc-number-parity.py`
  - Scope is every tracked EN/JA pair (`/en/` ↔ `/ja/` swap **and** the `-ja.md` suffix).
  - One-language-only quantity: `<!-- allow:number-parity -->` on the line. Whole-document
    divergence: `KNOWN_DIVERGENT_PAIRS`. **Both are shrink-only** — the checker fails on a
    suppression that no longer suppresses anything, so the list can only get shorter.
  - `--report-unit-collisions` lists same-number/different-prefix pairs (`128 MB` vs `128 MiB`).
    Reporting only: where a comparison depends on the prefix, state bytes.
- **Japanese section headings** (`##`–`######`) are noun phrases (体言止め). Rule body — including
  the suffix list for keeping an assertion under nominalization (`〜の存在` / `〜の不成立` /
  `〜の理由` …) and the three narrative sentence types that stay as they are — lives in the global
  `global-writing-style.md` steering; it is not restated here, so that only one copy can go stale.
  Repo-side enforcement, both of which run `--selftest` before the real check because a gate that
  cannot fail is indistinguishable from no gate:
  - `python3 scripts/check-heading-style.py --selftest && python3 scripts/check-heading-style.py`
  - `.githooks/pre-commit` step 6 (when `.md` files are staged) and the
    `.github/workflows/docs-quality.yml` heading-style step.
  - A heading that is deliberately narrative (a timeline entry, advice whose tone is the content,
    a stated intention) carries `<!-- allow:heading-style -->` on the heading line, with the reason
    written in the prose around it. H1 is out of scope: it is the document title.
- **Detector word boundaries: never `\b`, and the reason is engine-dependent.** In a
  Japanese-primary tree, `\b` silences a detector on the Japanese side while it keeps matching
  English, so the run reports clean. `\bFSxN\b` matches neither `FSxNを使う` nor `構成でFSxN`.
  **Both ends break independently.**

  | Engine | Used by | `\b` semantics | Affected |
  |---|---|---|:---:|
  | Python `re` | `scripts/*.py`, `shared/scripts/*.py` | Unicode-aware (CJK is a word char) | **Yes** |
  | GNU grep `-E` | `.github/workflows/*` | Locale-aware; CJK is a word constituent in UTF-8 | **Yes** |
  | Go RE2 | `gitleaks` / `.gitleaks.toml` | ASCII-only | No |

  Replacements: Python `(?<![A-Za-z0-9])` / `(?![A-Za-z0-9])`; ERE (no lookaround)
  `(^|[^A-Za-z0-9_])x([^A-Za-z0-9_]|$)`. **Keep `_` in the class** to match `\b`'s ASCII semantics —
  dropping it flags `FSxN_OnPre`, a configured SVM name, as a prose violation. Test each boundary
  with a **Japanese-adjacent case and an ASCII-with-space case as a pair**, plus a negative case:
  widening a match is invisible to positive cases.
- **`scripts/check-detector-mutations.py` proves the selftests can fail.** It breaks each detector
  deliberately and requires that detector's `--selftest` to fail; a surviving mutation means the
  guard is untested. Run unconditionally in `.githooks/pre-commit` and `docs-quality.yml` (0.26s).
  Rationale and the specific traps live in the script's own comments, not here.
- **Pre-commit**: `gitleaks detect --config .gitleaks.toml --no-git --source .`

## Project-Specific Technical Knowledge

### SSM Domain Join — Correct Pattern (verified failure)

When joining Windows EC2 to AD via CloudFormation:

```yaml
# ✅ CORRECT: Separate AWS::SSM::Association with AWS-managed document
DomainJoinAssociation:
  Type: AWS::SSM::Association
  Properties:
    Name: AWS-JoinDirectoryServiceDomain  # AWS-managed, not custom
    Targets:
      - Key: InstanceIds
        Values:
          - !Ref WindowsInstance
    Parameters:
      directoryId:
        - !Ref ManagedAD
      directoryName:
        - !Ref AdDomainName
      dnsIpAddresses:
        - !Select [0, !GetAtt ManagedAD.DnsIpAddresses]
        - !Select [1, !GetAtt ManagedAD.DnsIpAddresses]

# ❌ BROKEN: EC2 SsmAssociations property + custom SSM Document with aws:domainJoin
# Fails with: "Document schema version 2.2 is not supported by association
#              that is created with instance id"
```

Required IAM policies for domain-joined instances:
- `arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore`
- `arn:aws:iam::aws:policy/AmazonSSMDirectoryServiceAccess`

### S3 Access Point Networking — Critical Gotcha

**S3 Gateway Endpoint may block FSx for ONTAP S3 AP traffic** for internet-origin APs.

- FSx for ONTAP S3 AP aliases resolve to `s3-r-w.<region>.amazonaws.com`
- This hostname may NOT be in the S3 prefix list used by Gateway endpoints
- Impact: VPC-attached Lambda/EC2 → S3 Gateway EP → timeout for internet-origin APs

Solutions:
1. Place Lambda outside VPC (simplest for internet-origin APs)
2. Use NAT Gateway for S3 AP traffic
3. Use VPC-scoped S3 AP + S3 Interface Endpoint (production recommended)

Full details: `docs/en/fsx-ontap-s3ap-networking.md`

### ONTAP Version Detection

The FSx console and `describe-file-systems` API do NOT expose ONTAP version. Use ONTAP REST API:

```bash
# ONTAP REST API query (authenticate via Secrets Manager — do not inline passwords)
# GET https://<MGMT-IP>/api/cluster?fields=version
# Auth: Basic fsxadmin:<password-from-secrets-manager>
# See: shared/scripts/demo-ad-join-svm.sh for full authentication pattern
```

Minimum versions: S3 AP basic (9.14.1), S3 AP enhanced (9.15.1), FPolicy (9.8+).

### SVM and S3 AP Structural Conflict

FSx for ONTAP S3 Access Points CANNOT coexist with a native ONTAP S3 object-store server on the same SVM. Creating an S3 AP on an SVM that has `vserver object-store-server` configured will fail with:

> "Amazon FSx is unable to create an S3 access point because of an existing ONTAP object storage server on SVM..."

This is a structural conflict (not a timing issue). Use a different SVM or delete the native S3 server first.

### S3 AP WINDOWS User Type — AD Requirement

S3 APs with `FileSystemIdentity.Type=WINDOWS` require the SVM to be AD-joined (CIFS server configured). Template: `shared/templates/demo-ad-environment.yaml`. Script: `shared/scripts/demo-ad-join-svm.sh`.

### AgentCore MCP Gateway — Data Access via S3 AP (verified 2026-07)

When exposing lakehouse data operations (query, catalog browse) as MCP tools via AgentCore Gateway:

- **Region**: AgentCore Gateway は **ap-northeast-1 で利用可能**（us-east-1 前提は Workshop の簡便性のため）
- **同一リージョン必須**: Gateway と Lambda ターゲットは同一リージョンに配置。クロスリージョン Lambda 呼び出しは不可
- **Lambda event format**: ツール名は `event.toolName` ではなく `context.client_context.custom['bedrockAgentCoreToolName']` で取得。event はフラットなパラメータ辞書
- **E2E 検証済み構成**: Internet-origin S3 AP + VPC-external Lambda + AgentCore Gateway (ap-northeast-1) で list/read/search が動作確認済み

## Template Inventory (28 templates)

| Category | Path Prefix | Count | Purpose |
|----------|-------------|:-----:|---------|
| Shared infra | `shared/cloudformation/` | 8 | VPC, FSx for ONTAP base, IAM, FPolicy pipeline, sample data |
| Shared AD | `shared/templates/` | 1 | AD environment (3 patterns) |
| Athena/Glue/DuckDB/Delta | `integrations/*/template.yaml` | 5 | Analytics engine integrations |
| Databricks | `integrations/databricks/` | 3 | Network, S3 AP, VPC peering |
| Snowflake | `integrations/snowflake/` | 2 | IAM role + Snowpipe poller |
| OpenSharing | `integrations/opensharing-server/` | 1 | Credential vending server |
| Iceberg Catalog | `integrations/iceberg-metadata-catalog/` | 4 | S3 Tables, sync, demos |
| Manufacturing PoC | `integrations/manufacturing-data-platform/` | 4 | VPC, S3, FSx for ONTAP, MSK |
| PoC Quick-Start | `poc-templates/` | 2 | DuckDB Lambda, DataSync |

Deployment guide: `docs/en/deployment-guide.md` (EN) / `docs/ja/deployment-guide.md` (JA)

## Browser Automation and Credentials

A browser accessibility snapshot includes the **values** of input fields. When a password
manager autofills a sign-in form, the password is in that tree — and the tree is both
returned to the caller and written to disk as a snapshot file. This happened on
2026-08-12 with an AWS console password, and earlier with a Databricks personal access
token.

**Rules**

1. **Never snapshot a page that has a password field.** Do not call snapshot/find/verbose
   accessibility dumps on a sign-in page. If you need to know whether the form is ready,
   check for the submit button by selector, not by dumping the tree.
2. **Fill credentials without reading them back.** Use a code-execution browser tool to
   set the value and submit. Never return the value from the evaluated function.
3. **Never return a freshly created secret.** When a UI generates a token, relay it
   straight to its destination inside the same evaluated function — for example POST it to
   a short-lived `127.0.0.1` listener that writes the config file — and return only a
   length and a prefix. See the token-creation pattern used for the 2026-08 Databricks
   verification.
4. **A leaked value is not fixed by masking alone.** Masking removes disk persistence, not
   the conversation record. Rotate the credential.

**Enforcement**

| Layer | Mechanism | Portable? |
|-------|-----------|:---:|
| Disk persistence, immediate | `.kiro/hooks/redact-browser-snapshots.json` (PostToolUse on `browser_`/`devtool_`) runs the redactor after every browser tool call | ❌ `.kiro/` is gitignored — this exists per machine and has to be recreated after a clone |
| Disk persistence, at commit time | `.githooks/pre-commit` step 5 runs `--check` and warns loudly. Warn-only, because snapshot directories are gitignored and nothing there can reach the repository | ✅ tracked; needs `git config core.hooksPath .githooks` |
| Audit on demand | `python3 shared/scripts/redact_browser_snapshots.py --check` — exit 1 if any unredacted credential shape remains | ✅ |
| Conversation record | Rules 1–3 above | ❌ no tooling can retract what was already returned |

Snapshot directories (`.playwright-mcp/`, `/tmp/.playwright-mcp/`) are gitignored and hold
zero tracked files, so a leaked value cannot reach the repository through a commit. The
exposure is local disk plus the conversation record — which is why rule 4 is rotation, not
masking.

The redactor covers Databricks PATs, AWS access key IDs, STS session tokens, bearer
tokens, and password-field values. It is idempotent and leaves ordinary prose alone.
