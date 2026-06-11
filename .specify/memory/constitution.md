<!--
Sync Impact Report
==================
Version change: 1.2.1 → 1.3.0
Bump rationale: Terraform remote-state locking moved from DynamoDB to native S3 locking
(`use_lockfile`, Terraform >= 1.11); DynamoDB-based locking is deprecated and removed from the
project. Materially changed guidance in Principle V → MINOR.

Modified principles:
  - V. Infrastructure as Code, Plan-Only in CI (S3 native locking replaces DynamoDB)

--- History ---
Version change: 1.2.0 → 1.2.1
Bump rationale: Clarified the SSH deploy key as the project key pair in `.ssh/`
(`project_key` / `project_key.pub`) and added `.ssh/` to the required `.gitignore` exclusions in
Principle IV (wording/clarification, no semantic change) → PATCH.

Modified principles:
  - IV. Secrets Never Touch Source Control (clarified deploy key source, added .ssh/ to .gitignore)

--- History ---
Version change: 1.1.0 → 1.2.0
Bump rationale: Added a DNS-scoping safeguard (Terraform manages site A-records only; mail/MX and
other records untouched) to Principle V, and added the 6 concrete managed domains to
Infrastructure & Networking Standards (new guidance; no principle removed) → MINOR.

Modified principles:
  - V. Infrastructure as Code, Plan-Only in CI (added mail/MX-record protection rule)
Modified sections:
  - Infrastructure & Networking Standards (added the list of 6 managed domains)

--- History ---
Version change: 1.0.0 → 1.1.0
Bump rationale: Image registry changed from Docker Hub to Amazon ECR Public across Principle VI,
Principle VII, and the CI/CD Workflow (materially changed guidance; no principle removed) → MINOR.

Modified principles:
  - VI. Reproducible, Pinned Containers (registry is now Amazon ECR Public, Docker Hub forbidden)
  - VII. Automated Validation Gates (Docker digest check now against ECR Public)
Modified sections:
  - CI/CD Workflow (app-repo push and EC2 pull now use ECR Public; secrets list updated:
    DOCKERHUB_USERNAME/DOCKERHUB_TOKEN removed, ECR_PUBLIC_ALIAS added)

--- History ---
Version change: (template) → 1.0.0
Bump rationale: Initial ratification of the project constitution (first concrete version).

Modified principles: N/A (initial adoption)
Added principles:
  - I. Repository Responsibility Separation
  - II. Single Source of Deployment Truth
  - III. Domain-Isolated Single-Server Routing
  - IV. Secrets Never Touch Source Control
  - V. Infrastructure as Code, Plan-Only in CI
  - VI. Reproducible, Pinned Containers
  - VII. Automated Validation Gates (NON-NEGOTIABLE)
Added sections:
  - Infrastructure & Networking Standards
  - CI/CD Workflow
  - Definition of Done — Phase 1
  - Governance

Templates requiring updates:
  - .specify/templates/plan-template.md ✅ aligned (Constitution Check resolves gates dynamically)
  - .specify/templates/spec-template.md ✅ aligned (no hardcoded principle references)
  - .specify/templates/tasks-template.md ✅ aligned (no hardcoded principle references)
  - .specify/templates/checklist-template.md ✅ aligned (no hardcoded principle references)

Follow-up TODOs: None.
-->

# AWS Infrastructure Constitution

This constitution governs an infrastructure-as-code project (not an application project). The
primary deliverable is a reproducible, automated system that provisions and maintains one AWS
EC2 free-tier instance running 6 Docker containers, each serving a minimal static site on its own
domain over HTTPS, routed by Traefik, with DNS in Cloudflare, all driven by GitHub Actions CI/CD
across a 7-repository architecture (`infra-repo` + `app-repo-1..6`).

## Core Principles

### I. Repository Responsibility Separation

Build authority and deployment authority MUST remain strictly separated.

- `app-repo-1` through `app-repo-6` are **build authority only**: each owns exactly one domain and
  one container, and contains only its `Dockerfile`, `index.html`, and a build workflow.
- App-repos MUST NOT contain deployment logic, Terraform configuration, SSH keys, or EC2
  credentials. They build, push the image, and notify — they MUST NOT deploy.
- `infra-repo` is **deployment authority only**: it owns all deployment, provisioning, and routing
  logic. Application HTML/content MUST NOT live in `infra-repo`.

Rationale: Blast-radius isolation. A compromised or broken app-repo cannot alter infrastructure,
and infra changes cannot silently change application content.

### II. Single Source of Deployment Truth

`infra-repo` is the single source of truth for all deployment logic and state.

- All of `docker-compose.yml`, Terraform configs, and Traefik static/dynamic config live in
  `infra-repo` and nowhere else.
- App-repos trigger deployment exclusively via `repository_dispatch` events whose payload MUST
  include `service_name`, `image_tag`, and `domain`.
- Deployment to EC2 MUST originate from the `infra-repo` workflow — never from an app-repo.

Rationale: One authoritative place to reason about, audit, and roll back the running system.

### III. Domain-Isolated Single-Server Routing

All 6 domains resolve to the same EC2 public IP, and Traefik is the sole entry point.

- Traefik is the only process bound to host ports 80 and 443; HTTP MUST redirect to HTTPS at the
  Traefik level, not inside containers.
- Each app container runs `nginx:alpine` serving a single `index.html`, exposes NO host ports, and
  is reachable only through Traefik over the shared Docker network.
- Routing is declared via Docker labels: `Host(...)`, entrypoint `websecure`, TLS certresolver
  `letsencrypt`. TLS termination and ACME (HTTP challenge) renewal are handled by Traefik.
- Cloudflare proxy MUST be OFF (DNS-only, grey cloud) for these domains so the Let's Encrypt HTTP
  challenge reaches the server directly. ACME storage (`acme.json`) MUST be mode `600`.
- The Traefik dashboard MUST be disabled in production or bound to localhost only.

Rationale: A single hardened ingress with per-domain isolation keeps the free-tier footprint
minimal while preserving clean separation between sites.

### IV. Secrets Never Touch Source Control

No secret, token, private key, credential, or live IP is ever committed to any repository.

- All sensitive values are stored as GitHub Actions secrets and referenced only as
  `${{ secrets.NAME }}`. Secrets MUST NOT be echoed or logged.
- `.gitignore` MUST exclude at minimum: `.env`, `.ssh/`, `*.pem`, `*.key`, `acme.json`,
  `terraform.tfvars`, and `.terraform/`.
- EC2 access from CI uses a dedicated deploy key, never a personal key. This is the project key
  pair stored in `.ssh/` (`project_key` / `project_key.pub`); the public key is installed in the
  EC2 `authorized_keys`, and the private key material is provided to CI only via the
  `EC2_SSH_PRIVATE_KEY` GitHub secret (never committed).
- Terraform variables carrying secrets MUST be declared `sensitive = true`; no hardcoded tokens or
  IPs in `.tf` files.

Rationale: Credential leakage is the highest-severity, least-reversible failure mode for this
system; prevention is mandatory and non-negotiable.

### V. Infrastructure as Code, Plan-Only in CI

All infrastructure is declared in Terraform and validated before it is changed.

- Terraform manages: the EC2 instance, security group, key pair, and Cloudflare DNS A records for
  all 6 domains (`type = A`, `proxied = false`, `TTL = 60`).
- Remote state lives in the S3 bucket (`AWS_BUCKET_NAME`) under a `terraform.tfstate` key, with
  native S3 state locking (`use_lockfile`, Terraform >= 1.11). DynamoDB-based locking is deprecated
  and is not used.
- CI runs `terraform plan` ONLY. `terraform apply` is manual or gated behind a protected workflow
  requiring explicit approval.
- A successful CI plan MUST show zero drift; any non-zero plan is treated as a failure to
  investigate, not an expected outcome.
- Terraform's Cloudflare management is **scoped to site A-records only**. It MUST NOT create,
  modify, or delete `MX`, `TXT` (SPF/DKIM/DMARC), mail-related `CNAME`/`SRV`, or any other
  pre-existing record. Mail and all non-site records remain under manual control in Cloudflare.
  Terraform MUST NOT take ownership of an entire zone; any `plan` that shows destroy/modify of a
  non-site record MUST be treated as a failure and blocked before apply.

Rationale: Plan-only CI prevents accidental destructive changes while still continuously verifying
that real infrastructure matches declared intent; scoping DNS to site records protects email and
other services that share the same domains.

### VI. Reproducible, Pinned Containers

The deployed system MUST be reproducible from declared artifacts.

- Container images MUST be stored in **Amazon ECR Public** and referenced as
  `public.ecr.aws/<registry-alias>/<service-name>:<tag>`. Docker Hub MUST NOT be used as the image
  registry for this project.
- `docker-compose.yml` MUST pin images to a specific immutable tag (commit SHA) in addition to any
  `latest` tag, so any deployed state can be reconstructed exactly.
- Every change to `docker-compose.yml` MUST pass `docker compose config` validation before commit.
- Traefik config changes MUST be validated (`traefik healthcheck --configfile traefik.yml` when
  available, otherwise explicit manual review) before commit.

Rationale: "Works on the server right now" is not reproducibility; pinned, validated artifacts are.

### VII. Automated Validation Gates (NON-NEGOTIABLE)

Every deployment is gated by an automated validation suite that MUST pass.

- On `repository_dispatch` (and on direct push to `main` of `infra-repo`), the deploy workflow
  MUST: run `terraform plan` (exit 0), pull and bring up the changed service over SSH, wait, then
  run the full validation suite.
- Validation suite covers all 6 domains:
  - **DNS**: `dig +short <domain>` returns the EC2 IP.
  - **HTTPS**: `curl -sSf https://<domain>` returns HTTP 200 with a valid Let's Encrypt cert.
  - **Docker**: each running service's image digest matches the intended Amazon ECR Public digest.
- If any check fails, the workflow MUST post a failure summary to workflow annotations and exit 1.
  A failing gate MUST NOT be bypassed or marked green manually.

Rationale: The system's correctness is defined by observable health, not by "the deploy command
ran"; gates make that health a hard requirement on every change.

## Infrastructure & Networking Standards

- **Managed domains** (one per app-repo, all DNS-only / grey cloud in Cloudflare):
  1. `buyraq.com`
  2. `codehelp.pp.ua`
  3. `cosmeticpro.pp.ua`
  4. `ddnsteltonicka.pp.ua`
  5. `solovkadmytro.pp.ua`
  6. `solovkaskincare.pp.ua`
- **Instance**: `t2.micro` (free-tier eligible), AMI Ubuntu 22.04 LTS, region `us-east-1`.
- **Security group inbound**: 22 (SSH, restricted to GitHub Actions IP ranges or a bastion), 80
  (HTTP), 443 (HTTPS). No other inbound ports.
- **Provisioning**: Docker and Docker Compose installed at provision time via Terraform
  `user_data` (or Ansible).
- **Addressing**: An Elastic IP is strongly recommended to avoid public-IP changes on stop/start;
  if used, DNS records reference it.
- **Traefik static config** (`traefik.yml`): entrypoints `web:80` and `websecure:443`, Docker
  provider, ACME resolver pointing at Let's Encrypt production. **Dynamic config**: Docker labels
  on each app container.

## CI/CD Workflow

**App-repo workflow** (on push/merge to `main`):

1. `docker build -t public.ecr.aws/<registry-alias>/<service-name>:<tag> .`
2. Authenticate to Amazon ECR Public (region `us-east-1`):
   `aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws`
   (uses `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`).
3. Push to ECR Public: `docker push public.ecr.aws/<registry-alias>/<service-name>:<tag>`.
4. Fire `repository_dispatch` to `infra-repo` (requires `INFRA_REPO_DISPATCH_TOKEN`, a PAT with
   `repo` scope) with payload `{ service_name, image_tag, domain }`.

**Infra-repo deploy workflow** (on `repository_dispatch` and on direct push to `main`):

1. Checkout `infra-repo`.
2. `terraform plan` — MUST exit 0 with no unexpected changes.
3. SSH into EC2 and pull from Amazon ECR Public:
   `docker compose pull <service_name> && docker compose up -d <service_name>`. ECR Public images
   pull anonymously; if authenticated pulls are needed (rate limits), the EC2 host authenticates
   the same way as step 2 of the app-repo workflow.
4. Wait ~15 seconds, then run the full validation suite (Principle VII).
5. On any failure: annotate and exit 1.

**Required GitHub secrets** (in `infra-repo` and app-repos as applicable):
`CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_EMAIL`, `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `AWS_BUCKET_NAME`, `AWS_MEDIA_URL`, `ECR_PUBLIC_ALIAS`
(ECR Public registry alias, e.g. `public.ecr.aws/<alias>`), `EC2_SSH_PRIVATE_KEY`, `EC2_HOST`,
`INFRA_REPO_DISPATCH_TOKEN`.

ECR Public push/login uses the existing AWS credentials (`AWS_ACCESS_KEY_ID` /
`AWS_SECRET_ACCESS_KEY`); no separate Docker Hub credentials are required.

Terraform variables are passed via environment (`TF_VAR_cloudflare_api_token`, `TF_VAR_aws_region`,
etc.).

## Definition of Done — Phase 1

Phase 1 is complete when ALL of the following hold:

1. The EC2 instance is running and reachable.
2. All 6 domains resolve to the EC2 IP in Cloudflare DNS.
3. All 6 containers are running and serve their `index.html` over HTTPS with a valid Let's Encrypt
   certificate.
4. HTTP requests to any of the 6 domains redirect to HTTPS.
5. Every push to `main` in any app-repo triggers the `infra-repo` deploy workflow and passes all 6
   validation checks.
6. `terraform plan` in CI shows zero drift.
7. All secrets are stored in GitHub, not in any file in any repository.

## Governance

- This constitution supersedes other deployment practices and conventions for this project. Where a
  workflow, script, or template conflicts with it, the constitution wins and the conflicting
  artifact MUST be corrected.
- **Amendments** require: a written change description, justification, and a version bump per the
  policy below. Security-affecting amendments (Principles IV–VII) require explicit reviewer
  approval before merge.
- **Versioning policy** (semantic):
  - MAJOR: backward-incompatible governance/principle removal or redefinition.
  - MINOR: a new principle/section or materially expanded guidance.
  - PATCH: clarifications, wording, or non-semantic refinements.
- **Compliance**: every PR/review against `infra-repo` and the app-repos MUST verify compliance
  with the relevant principles. The automated validation gates (Principle VII) are the runtime
  enforcement of this constitution; a red gate blocks merge/deploy.

**Version**: 1.3.0 | **Ratified**: 2026-06-05 | **Last Amended**: 2026-06-05
