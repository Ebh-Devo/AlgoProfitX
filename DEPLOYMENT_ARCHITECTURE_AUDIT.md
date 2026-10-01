# AlgoProfitX Deployment Architecture Audit

**Audit date:** 2026-10-01  
**Scope:** Read-only inspection of `AlgoProfitX` and the public snapshot of `algoprofitx-catalyst-connectivity-poc`.  
**Primary AlgoProfitX snapshot:** local branch `dev`; remote configured as `https://github.com/Ebhadmin/AlgoProfitX.git`.  
**POC snapshot:** `c6e025501fc75f82bb31d80e01270480b8a052cc` (`ci: deploy configuration diagnostics`, 2026-09-04).

No deployment, Catalyst operation, secret change, environment-variable change, repository change, or application/configuration change was performed.

## A. Current Architecture

### Evidence-based architecture

```text
feature/*, fix/*, refactor/*, chore/*
             |
             v
       pull request -> dev -> release PR -> main
             |          |
             |          +--> CI (.github/workflows/ci.yml)
             |
             +--> Catalyst artifact build/verification
                  (.github/workflows/build-catalyst.yml)
                         |
                         +--> Docker archives, linux/amd64
                         |    algoprofitx-api:<GitHub SHA>
                         |    algoprofitx-web:<GitHub SHA>
                         |
                         +--> manual workflow dispatch
                              .github/workflows/deploy-catalyst-development.yml
                              |
                              v
                       Catalyst project 36851000000392052
                       org 60069781151, DC in
                              |
                    +---------+----------+
                    |                    |
                    v                    v
             AppSail algoprofitx-api  AppSail algoprofitx-web
                    |                    |
                    +------ Catalyst Development target ------+

Separate path, not in the API/web release chain:

algoprofitx-catalyst-connectivity-poc
             |
             +--> manual build workflow -> connectivity-poc:<POC SHA>
             |    Docker archive + one-day artifact
             |
             +--> manual deploy workflow -> AppSail connectivity-poc
                  Catalyst project 36851000000392052 / Development
                  /health and /db-check probe against runtime-supplied PostgreSQL
```

### What is and is not deployed today

- The primary repository has CI, Docker packaging, Catalyst Development deployment workflows, and an API runtime verification workflow.
- The primary repository has no production deployment workflow. `docs/production-runtime.md` explicitly says production deployment does not yet exist and that the packaging is provider-neutral.
- The primary repository's Catalyst deployment workflows target Development. No checked-in workflow targets a Catalyst Production environment or a production AppSail.
- The POC deploys only a separate `connectivity-poc` AppSail in Catalyst Development. It is not the `algoprofitx-api` or `algoprofitx-web` image.
- The user-supplied current production AppSail names (`algoprofitx-web`, `algoprofitx-api`) and `connectivity-poc` were not queried or changed during this audit. Repository evidence does not establish their current live versions or deployment history.
- The checked-out worktree contains an untracked `.release/application` copy of many primary files. It was inspected for context but is not treated as authoritative tracked source and was not modified.

### Workflow and script inventory

| File | Purpose | Trigger | Environment/target | Inputs/secrets | Artifact/deployment mechanism |
|---|---|---|---|---|---|
| `.github/workflows/ci.yml` | Backend migrations/tests/health smoke; frontend typecheck/tests/build; backend image build and liveness smoke | Every push and PR | GitHub-hosted Linux; CI-only PostgreSQL and secrets | Hard-coded CI-only database URL and `SECRET_KEY`; no Catalyst secret | Disposable test image `algoprofitx-backend:ci`; no upload/deploy |
| `.github/workflows/build-catalyst.yml` | Build and verify API/web Catalyst Docker archives | Manual, push to `main`, PR | `linux/amd64`; frontend API URL is `https://api.algoprofitx.com/api/v1` | `github.sha`, repository/server URL as backend build args; no secret | `/tmp/algoprofitx-api.tar`, `/tmp/algoprofitx-web.tar`, `/tmp/SHA256SUMS`; uploaded as `catalyst-release-<SHA>` for non-PR runs, one-day retention |
| `.github/workflows/deploy-catalyst-development.yml` | Deploy a reviewed immutable API and web release to Catalyst Development | Manual dispatch | Catalyst project `36851000000392052`, org `60069781151`, DC `in`, target `Development`; AppSails `algoprofitx-api` and `algoprofitx-web` | Fixed release run/artifact IDs and expected archive SHA-256 values; GitHub environment `catalyst-development`; `secrets.CATALYST_TOKEN` | Downloads GitHub artifact, verifies checksums, installs `zcatalyst-cli@1.27.2`, runs `catalyst deploy appsail` with `docker-archive://`; no rollback step |
| `.github/workflows/deploy-catalyst-api.yml` | Verified API-only Development redeploy | Manual dispatch with `source_sha` and `runtime_run_id` | Catalyst project/org/DC are fixed in the command; existing `algoprofitx-api` Development AppSail | `github.token`; `secrets.CATALYST_TOKEN`; exact source SHA and successful `verify-catalyst-api.yml` run required | Downloads `algoprofitx-api-<SHA>`, checks archive and `api-runtime.json`, installs CLI `1.27.2`, deploys API archive only; no rollback step |
| `.github/workflows/verify-catalyst-api.yml` | Build real API image, reproduce configuration failure, then verify liveness/readiness/runtime stability | Push only to branch `codex/catalyst-api-liveness`, or manual | GitHub-hosted Linux; local Docker container | `GITHUB_SHA`; generated test secret only inside the job; no Catalyst token | API archive, checksum, and `api-runtime.json`; uploaded for three days; no Catalyst deployment |
| `scripts/verify-api-runtime.py` | Runtime smoke helper used by API verification | Called by `verify-catalyst-api.yml` | Local Docker; no external environment | Reads `GITHUB_SHA`; generates ephemeral smoke secret | Writes API archive/checksum and runtime metadata containing source and deployment repository fields |
| `scripts/migrate.ps1` | Local Alembic migration helper | Manual/local | Developer PostgreSQL | Local environment file/PowerShell inputs | Database migration only; no Catalyst/deployment action |
| `scripts/run-api.ps1` | Local API startup helper | Manual/local | Developer machine | Local `backend/.env` | Local process only |
| `scripts/test.ps1` | Local backend/frontend test orchestration | Manual/local | Developer machine | Local environment | Test results only; no deployment |
| `scripts/validate-cloudflare-staging.py` | Validate a proposed Cloudflare Pages staging contract | Manual/local | Contract validation; no live mutation | Contract values in source | Validation output only |
| `scripts/validate-digitalocean-staging.py` | Validate proposed DigitalOcean staging contract | Manual/local | Contract validation; no live mutation | Contract values in source | Validation output only |
| `deploy/cloudflare/pages-staging.md` | Operator-reviewed Pages contract | None; documentation | Planned staging only | No live token/account/ID | No deployment |
| `deploy/digitalocean/staging.yaml` and `docs/deployment-digitalocean-staging.md` | Provider-neutral/planned staging specification and runbook | None; documentation | Planned Cloudflare/DigitalOcean staging, not Catalyst production | Runtime secrets described but not embedded | No deployment; `deploy_on_push: false` in the proposed DigitalOcean spec |

### Catalyst and Docker details

- Catalyst CLI is installed at a pinned `1.27.2` in the primary API/web deployment workflows. The POC pins `1.27.1`.
- Primary API and web archives are Docker `save`-style archives produced by Buildx with `linux/amd64` and consumed through Catalyst's `docker-archive://` source.
- Primary image tags are `algoprofitx-api:<github.sha>` and `algoprofitx-web:<github.sha>`. No registry push is performed.
- Backend image labels include `org.opencontainers.image.source` and `org.opencontainers.image.revision`; frontend has no equivalent Git SHA label.
- Backend and frontend runtime containers use UID/GID `10001:10001` and have Docker health checks. The API exposes `/health/live` and `/health/ready`; the web health check requests `/`.
- No checked-in production rollback command or automated smoke test against a live production endpoint was found. The staging runbook describes rollback concepts for future DigitalOcean/Pages infrastructure, not a live current deployment.

## B. Dependency Matrix

| Dependency source | Consumer | Production critical? | Migration required? | Evidence and assessment |
|---|---|---:|---:|---|
| `AlgoProfitX` API/web source | Primary Catalyst Development workflows | No current production evidence; critical to Development | No repository move; consolidate/standardize later | `build-catalyst.yml` and `deploy-catalyst-development.yml` build and deploy directly from primary source |
| POC repository | Catalyst `connectivity-poc` Development AppSail | No for API/web production; operationally relevant to the separate connectivity probe | Yes, if the probe is still required | POC `build.yml` and `deploy-catalyst-poc.yml` build/deploy its own image and use a separate AppSail |
| POC commit metadata | Primary API runtime artifact metadata | Potentially critical to release traceability, not runtime execution | Yes | `scripts/verify-api-runtime.py` writes `DEPLOYMENT_REPO=Ebh-Devo/algoprofitx-catalyst-connectivity-poc` and a fixed `DEPLOYMENT_SHA`; this describes provenance but does not fetch or execute POC code |
| POC repository GitHub artifact | POC Catalyst Development deployment | No for primary API/web; critical for `connectivity-poc` | Yes, if POC is retired | POC deploy workflow downloads a fixed run `33869556076` and artifact `connectivity-poc-linux-amd64-cb99...` from a differently spelled owner/repository reference |
| Catalyst project/org/DC IDs | Both repositories' Catalyst workflows | Yes for any corresponding Development deployment | Move to one controlled configuration surface | Both use project `36851000000392052`, org `60069781151`, DC `in` |
| `CATALYST_TOKEN` GitHub secret | Primary and POC Catalyst deploy workflows | Yes for their respective manual deployments | Centralize/standardize ownership and environment scope | Both reference `secrets.CATALYST_TOKEN`; no secret values were accessed |
| CLI version | Primary and POC deploy workflows | Yes for command compatibility | Standardize | Primary uses `1.27.2`; POC uses `1.27.1` |
| Fixed GitHub run IDs/checksums | Reviewed release deployment workflow | Yes for repeatability of that manual release | Replace with an explicit release input/attestation mechanism | `deploy-catalyst-development.yml` embeds release run, artifact, and archive checksums |
| Docker registry/image | Both repositories | No registry dependency found | None | Both use local Docker archives; no registry push or pull appears in the workflows |
| AppSail names | Catalyst target | Yes | Preserve and explicitly inventory before migration | Primary: `algoprofitx-api`, `algoprofitx-web`; POC: `connectivity-poc` |

### Cross-repository references found

1. **Primary repository, `scripts/verify-api-runtime.py`:** runtime metadata names `Ebh-Devo/algoprofitx-catalyst-connectivity-poc` and fixed POC commit `c6e025501fc75f82bb31d80e01270480b8a052cc`. This is an artifact metadata dependency only in the checked-in code; the script does not clone, download, import, or execute the POC.
2. **POC repository, `.github/workflows/deploy-catalyst-poc.yml`:** downloads an artifact from `Ebh-Digtal/algoprofitx-catalyst-connectivity-poc`, run `33869556076`, with a fixed artifact SHA/name, then deploys AppSail `connectivity-poc`.
3. **Repository identity mismatch:** the user supplied `Ebh-Devo` for the POC and `Ebh-Devo/AlgoProfitX` for the primary repository, while the checked-out primary remote is `Ebhadmin/AlgoProfitX`, the primary workflows use `Ebhadmin/AlgoProfitX`, and the POC workflow uses `Ebh-Digtal/...`. These must be resolved before relying on automated artifact downloads or provenance checks.
4. **No primary workflow reference to the POC repository was found** in the build, CI, Catalyst Development deployment, or API verification workflows. The only primary tracked reference is the metadata field described above.
5. **No POC reference in application runtime behavior was found.** The POC is not imported by the API/web source, is not a Docker build context for either primary image, and is not called by primary CI.

## C. Current Development Deployment

### AlgoProfitX API/web Development

The repository evidence supports this exact manual sequence:

1. A developer works on a feature/fix branch, opens a PR into `dev`, and promotes a reviewed milestone through a PR into `main`, according to `docs/DEVELOPMENT_WORKFLOW.md`.
2. CI runs on pushes and PRs. `build-catalyst.yml` also builds API/web archives on PRs, `main` pushes, and manual dispatch, but PR archives are verified and not uploaded.
3. The build uses the commit SHA as the Docker tag and backend OCI revision label. It produces one-day GitHub artifacts only for non-PR events.
4. An operator manually dispatches `deploy-catalyst-development.yml`, which downloads a fixed reviewed artifact and verifies both archive checksums.
5. The workflow installs Catalyst CLI `1.27.2`, validates the fixed project/org/DC/Development target, reads `CATALYST_TOKEN` from the `catalyst-development` environment, and deploys two archives using `catalyst deploy appsail`.
6. The evidence does not show an automated post-deployment HTTP smoke test, deployment ID capture, or rollback in that workflow.

The API-only `deploy-catalyst-api.yml` is a separate manual path: an operator supplies an exact source SHA and successful verification run ID; the workflow verifies the run's SHA/path/conclusion, verifies the archive metadata/checksum, then redeploys only the Development API AppSail.

### POC Development

1. An operator manually dispatches POC `build.yml`; it does not run on push or PR.
2. The workflow checks that the checkout is the expected POC repository, builds `connectivity-poc:<POC SHA>` from only `Dockerfile`, `app.py`, and `requirements.txt`, verifies non-root/platform/secret exclusion, runs `/health` and sanitized `/db-check` tests, and uploads a one-day Docker archive/checksum artifact.
3. An operator manually dispatches POC `deploy-catalyst-poc.yml`; it downloads one fixed artifact from the hard-coded external repository/run, verifies its checksum and image metadata, installs Catalyst CLI `1.27.1`, and deploys one `connectivity-poc` AppSail in Development using `CATALYST_TOKEN`.
4. The POC is a connectivity diagnostic surface. It accepts runtime PostgreSQL host/port/database/user/password and CA material; it does not contain AlgoProfitX product routes, frontend code, migrations, or production release logic.

## D. Current Production Deployment

No current production deployment process is defined in the inspected primary repository.

- `docs/production-runtime.md` states: "No production deployment exists yet." It defines provider-neutral packaging and runtime contracts but explicitly does not publish images, create cloud resources, configure DNS, or run migrations automatically.
- No tracked primary workflow has a production trigger, Catalyst `Production` target, production AppSail command, production smoke test, rollback command, or production deployment ID capture.
- The Catalyst workflows guard `CATALYST_TARGET_ENVIRONMENT=Development` or are clearly named/implemented as Development deployment workflows.
- The POC workflow comments and commands explicitly exclude source build, registry, database configuration, and production deployment.
- The supplied production AppSail names and project context may reflect live infrastructure outside this repository, but this audit did not query live Catalyst state and cannot map that state to a checked-in workflow or artifact.

Therefore the current production path is **not reconstructable from repository evidence**. Any real production process is external/manual or in another system not inspected here.

## E. Git SHA Traceability

### What works

For the primary API verification path, the chain is partially implemented:

```text
GITHUB_SHA
  -> Docker tag algoprofitx-api:<SHA>
  -> OCI label org.opencontainers.image.revision=<SHA>
  -> archive checksum
  -> api-runtime.json APP_SOURCE_SHA=<SHA>
  -> manual Development API workflow verifies source SHA and runtime-gate run
```

The evidence is in `backend/Dockerfile`, `scripts/verify-api-runtime.py`, `verify-catalyst-api.yml`, and `deploy-catalyst-api.yml`.

### Gaps

The audit cannot answer "which exact Git commit is running in production?" from this repository.

1. There is no checked-in production deployment workflow or production deployment record.
2. The normal combined API/web Development workflow uses fixed release run IDs and archive checksums but does not emit or capture a Catalyst deployment ID or query Catalyst deployment metadata.
3. The frontend image receives no Git SHA build argument/OCI revision label; its SHA is present in the tag and artifact name only.
4. The API runtime metadata includes a `DEPLOYMENT_REPO` and fixed `DEPLOYMENT_SHA` referring to the POC, which can be mistaken for the application source/deployment commit. It is not a Catalyst deployment ID and does not prove that the POC participated in the API deployment.
5. Artifact retention is one day for the combined release and three days for the API verification artifact, so durable historical release evidence is not defined.
6. No runtime version endpoint exposes source SHA, image digest, or release identity. The API version is statically `0.1.0`; `/health/live` and `/health/ready` expose only status.
7. No immutable registry digest or Catalyst AppSail deployment export is recorded in the repository.
8. The repository-owner spelling mismatch (`Ebhadmin`, `Ebh-Devo`, `Ebh-Digtal`) undermines automated provenance retrieval until resolved.

**Conclusion:** exact SHA traceability exists for a verified API build artifact and a manual Development API gate, but not for a live production AppSail. The complete `Git SHA -> artifact -> Catalyst deployment -> production AppSail` chain is missing.

## F. Recommended Target Architecture

```text
feature/*
   |
   v
PR -> dev
   |
   +--> CI: backend tests, frontend tests, Docker builds, security checks
   |
   v
release PR -> main
   |
   v
single AlgoProfitX release workflow
   |
   +--> immutable API/web artifacts, SHA + digest + checksums + signed/attested metadata
   |
   +--> gated Catalyst Development deployment
   |       |
   |       +--> live health/connectivity/product smoke tests
   |       +--> capture Catalyst deployment IDs and environment
   |
   +--> approved production promotion of the exact same artifact
           |
           +--> Catalyst Production AppSails algoprofitx-api / algoprofitx-web
           +--> production smoke tests and deployment record
           +--> documented rollback to prior known-good artifact
```

Recommended single-repository layout:

```text
AlgoProfitX/
|-- backend/
|-- frontend/
|-- tests/
|-- deployment/                 # Catalyst specs/contracts and promotion metadata
|-- scripts/
|-- Dockerfiles
`-- .github/workflows/
   |-- ci.yml
   |-- build-release.yml
   |-- deploy-development.yml
   |-- deploy-production.yml
   `-- production-smoke.yml
```

Design requirements for the target:

- Build once and promote the same immutable API/web archives from Development to Production.
- Use one canonical repository/owner identity and one canonical Catalyst CLI version.
- Store project/org/DC/AppSail/environment identifiers in one reviewed deployment configuration surface, with target guards.
- Keep secrets only in GitHub environment secret stores or Catalyst runtime configuration; never in images, build args, artifacts, or logs.
- Emit durable release metadata: source SHA, repository, image digest, archive checksum, Catalyst deployment ID, target environment, migration head, and smoke-test evidence.
- Add explicit production approval, concurrency protection, pre-deployment migration policy, live smoke tests, and rollback to the previous immutable artifact.
- Decide separately whether the POC's DB/TLS connectivity probe becomes a maintained test/diagnostic component under `AlgoProfitX` or is retired after equivalent coverage is established.

## G. Migration Plan

| Step | Repository/files | Expected change | Testing required | Production risk | Rollback |
|---|---|---|---|---|---|
| 1. Inventory live state | Both repos; Catalyst console/API records; GitHub Actions environments | Record current AppSails, environments, deployment IDs, active image/archive identities, domains, and secret ownership without changing them | Read-only reconciliation; export evidence | None | Delete local audit notes only; no platform change |
| 2. Resolve identity mismatches | Both repos: workflow repository fields, source metadata, documentation | Choose the canonical GitHub owner/repository names and update references only after authorization | Validate artifact download against a known non-production run; grep for old identities | Low, but incorrect identity can block deployments | Restore previous reference values via reviewed commit |
| 3. Decide POC capability ownership | POC `app.py`, Dockerfile, workflows; primary `scripts/verify-api-runtime.py` | Define whether DB/TLS probe is moved into AlgoProfitX tests/diagnostics or remains a separately governed service temporarily | Re-run POC tests and equivalent primary-repo tests; compare probe behavior and failure sanitization | Low if no live target changes | Keep POC active until parity is demonstrated |
| 4. Add canonical deployment metadata | Primary `.github/workflows`, deployment contract, release metadata schema | Record source SHA, image digest, archive checksum, target, CLI version, deployment ID, and smoke evidence | Unit/schema tests; artifact inspection; dry-run or non-production validation | Low | Revert workflow/schema commit; no target change |
| 5. Build/promote immutable release | Primary build and deploy workflows | Replace fixed historical IDs with explicit release inputs/attestations and promote the same archives | PR CI, image tests, checksum verification, Development deployment and smoke tests | Medium in Development; none in Production until approval | Redeploy the prior Development artifact |
| 6. Add controlled Production workflow | Primary production workflow and environment configuration | Add manual approval, Production target guard, concurrency, migration gate, API/web deployment, deployment record, smoke test, and rollback input | Staging/non-production rehearsal; exact-artifact promotion test; failure injection where possible | High; requires separate authorization and backup/PITR validation | Promote prior known-good artifact; follow database recovery plan for incompatible migrations |
| 7. Run a parallel release observation period | Both repos and Catalyst Development/Production records | Compare primary-repo probe/release evidence to POC outputs while leaving POC available | Multiple successful release cycles, health checks, connectivity checks, and provenance reconciliation | Medium | Continue using POC path until criteria pass |
| 8. Remove active POC references | Primary metadata/workflows and POC workflows | Remove POC commit metadata dependency and disable its deployment only after retirement criteria pass | Full repository grep, CI, Development/Production smoke, artifact provenance audit | Medium if hidden consumers exist | Restore POC deployment and references from prior commit |
| 9. Archive POC | POC repository settings, after all criteria below | Archive only; do not delete history or live Catalyst AppSail without a separate approved decision | Final read-only dependency scan and owner sign-off | Low after criteria; operational probe loss remains the main risk | Unarchive repository if a missed dependency is found |

## H. POC Retirement Criteria

Do not archive `algoprofitx-catalyst-connectivity-poc` until every condition is evidenced:

- The required connectivity capability has a named owner and an equivalent implementation, test, or approved replacement inside `AlgoProfitX`.
- No checked-in workflow, script, artifact metadata, documentation, external scheduler, GitHub environment, or deployment run references the POC repository, its commit, its workflow run IDs, or its artifact names.
- No build context, Docker image, Catalyst AppSail specification, runtime service, smoke test, or operator runbook requires the POC.
- The canonical GitHub repository owner/name is resolved and all artifact download/provenance checks pass using that identity.
- `algoprofitx-api` and `algoprofitx-web` can be built, deployed, health-checked, and rolled back from `AlgoProfitX` alone in Development.
- The intended production AppSails can be promoted from an immutable artifact built by `AlgoProfitX`, with the source SHA, image digest/checksum, Catalyst deployment ID, target environment, and smoke evidence durably recorded.
- Production and Development secrets are owned by the canonical repository/environment or documented Catalyst runtime store; no secret depends on POC workflow permissions.
- At least two successful release cycles have completed without POC artifacts, POC workflow runs, or POC runtime endpoints.
- The separate `connectivity-poc` Catalyst AppSail has an explicit disposition: retained independently, replaced, or decommissioned under a separate authorized operational task. Archiving the repository must not silently delete or alter the AppSail.
- Owners approve the archive after a final read-only search of GitHub Actions, scheduled jobs, external deployment systems, Catalyst configuration, and documentation.

## Final Status

```text
AUDIT COMPLETE

Repositories inspected:
- AlgoProfitX
- algoprofitx-catalyst-connectivity-poc

Production modified: NO
Catalyst modified: NO
Secrets modified: NO

Critical dependencies found:
- Primary Development deployment and POC Development deployment share Catalyst project/org/DC identifiers.
- Both deployment paths depend on a GitHub Actions CATALYST_TOKEN secret.
- The primary API runtime metadata records the POC repository and a fixed POC commit as deployment metadata, although primary deployment does not execute or download POC code.
- The POC deployment workflow depends on a fixed external repository owner/name, run ID, artifact name, and checksum.
- Repository identity strings are inconsistent: Ebhadmin, Ebh-Devo, and Ebh-Digtal appear in the inspected evidence.

Migration blockers:
- No repository-backed production deployment workflow or production deployment record was found.
- Live Catalyst state, active production deployment IDs, and current production artifact identities were not queried during this read-only audit.
- The exact runtime role of the separate connectivity AppSail must be accepted, migrated, or explicitly retained before POC retirement.
- Durable SHA-to-Catalyst-to-production traceability and rollback evidence are not currently defined.

Recommended next task:
- Perform a read-only live-state reconciliation of Catalyst/GitHub environments and resolve the repository identity mismatch, then approve a design for moving or retaining the connectivity probe before implementing any deployment changes.
```