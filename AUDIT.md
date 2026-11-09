# LustCode foundation audit — 2026-11-07

## Question display headings — 2026-11-09

Updated all 300 display headings with curated non-graphic LustCode innuendo, retaining
the original algorithm name as a prefix. Official titles remain in source.title and
workbook title provenance is unchanged. Rebuilt ingestion applies the same source-slug
keyed taglines; the cached source bundle carries the matching display titles. Existing
title search finds both original names and taglines, and every summary/detail endpoint
uses the same stored title. No frontend or schema changes are needed.

The live update changed only Question.title. Before/after snapshots prove all other
question columns and all 2,769 complete test-case records, including IDs, are unchanged.
Regression suite: 316 passed. Evidence: audit/question_title_branding.json.

## Frontend feature support — 2026-11-09

Implemented the requested frontend backend capabilities while preserving authentication,
refresh rotation, existing question contracts, judging, quotas, and hidden-result privacy.
The existing question-run route now accepts optional bounded typed custom fixtures;
custom results have no reference expected answer and explicitly identify their scope.
Topics and topic filtering share catalog predicates with random selection and filtered
neighbor navigation. Collections store explicit difficulty rules; featured selection is
the documented canonical catalog prefix. Counts/completion come from published rows and
the authenticated caller's real progress, never synthetic activity or popularity.

Drafts are account/workspace/language scoped and use revision checks, user-row locking,
and deletion tombstones to prevent stale devices from restoring reset code. Preferences
validate partial updates and registry runtimes. Avatars use configured persistent storage,
verified single-frame PNG/JPEG/WebP input, fresh metadata-free PNG output, atomic writes,
and current-owner lookup before public reads. UTC streak/rate metrics derive from graded
database activity and exclude all execution-only modes.

Migration `e42b19c06d31` adds two tables and additive metadata; both new tables have RLS.
Server defaults preserve old-version inserts during upgrade. Disposable PostgreSQL
upgrade, drift checks, downgrade/re-upgrade, and full base/head round trips pass. Hosted
Compose applied the revision successfully and all nine application tables retain RLS.
Regression suite: **315 passed**. Eight real Judge0 executions verify all three custom
function languages, design operations, three Playground starters, and existing samples.
Live catalog/draft/preferences/avatar checks pass and leave graded metrics unchanged.

Frontend files were read for integration reference and left unchanged. Exact API and
proxy changes are in `FRONTEND_API_HANDOFF.md`; machine-readable evidence is in
`audit/frontend_features_verification.json` and `audit/frontend_features_live.json`.

## Sample-run follow-up — 2026-11-09

Added authenticated `POST /questions/{question_id}/runs` for the editor's Run button.
It snapshots only visible samples using the existing trusted function/class drivers
and comparators. Sample runs retain `mode=run` and the question ID; they do not create
or update progress, attempts, solve credit, or statistics. Quotas and pending limits
remain shared with other execution modes. Visible result snapshots now expose input
and expected output; both fields remain redacted on hidden results.

49 enabled questions lacked executable samples. Version `authored-v3-visible-samples`
publishes one validated authored case for each: all 283 enabled questions now have
samples, totaling 623 visible and 2,146 hidden cases (2,769 overall). At least two
hidden cases remain per question. Statements and solution contracts are unchanged.
No schema migration is needed. Current evidence: `audit/sample_runs_verification.json`.

## Judging follow-up — 2026-11-09

Implemented and installed complete question-level grading support for the 283 algorithm
questions. The 17 SQL/shell questions remain browsable with judging disabled. Premium
questions use the user's authorized independent LustCode contracts. The implementation
preserves the original workbook bodies.

The missing pieces were method/class drivers, private suites, semantic comparators,
pointer-aware fixtures, and immutable queued evaluation contracts. Added typed stdin
transport to avoid compiling private inputs into source, full-output comparison before
diagnostic truncation, debug-output isolation, explicit C++17, hashes for verified
statements/cases, and batched idempotent suite installation. Public APIs expose effective
signatures, starter code, contract descriptions, and language readiness. Invalid or
unsupported suites fail before provider discovery and execution quotas. Hidden fields
and evaluation snapshots remain private. Fixture review found out-of-domain boundary
inputs that could reject valid solutions; these were corrected before final verification.
Suite generation now validates public bounds and selected input promises. Catalog changes
to constraints or interfaces require review before replacing installed contracts.

Validation: 263 automated tests; C++/Java compilation for all 283 drivers; 35 native
transport checks; and 20 real submission scenarios. Incorrect answers and execution
failures produced the expected verdicts, and correct solutions received solve-once
credit. See `audit/judging_verification.json` for files changed, actual results, and
remaining provider/coverage limitations. Earlier audit sections below are historical.

## Catalog follow-up — 2026-11-09

After foundation verification, the user authorized onboarding a browsable workbook
catalog. The importer now publishes 300 questions with exact workbook main statements
and factual public LeetCode enrichment. It corrects one stale title and seven stale
difficulties while retaining original workbook metadata privately. The 43 premium
entries use public catalog metadata only; 13 SQL and four shell questions explicitly
have no supported execution language in this backend.

The missing import path, public metadata contract, numerical catalog ordering, and
explicit judging availability are implemented. Imports are transactional, concurrent-safe,
idempotent, and reject overwriting manual statement edits. API serialization excludes
internal provenance; reference examples never become executable tests. No schema changes
or private test cases were added. All 300 records were checked in Supabase and the live
API was verified after rebuilding the containers. The suite passes 202 tests.
See `audit/question_ingestion.json` for changed files, actual results, and limitations.
The earlier sections below describe the foundation work at their original dates.

Foundation fixes were implemented and verified before any additional database feature
development. Database models, schema migrations, and product feature behavior were kept
in scope only for regression checks; no new database features or question data were added.

## Inspection

Reviewed every authored file present at the start: all application modules and package
markers, migrations, tests, Docker/Compose, CI, dependency manifests/locks, environment
template, ignore rules, README, and the previous validation record. The local `.env` was
inspected with secret values redacted. Installed dependencies, caches, and bytecode are
generated artifacts and were excluded from the source audit.

The application already imported successfully and its initial unit suite passed. Existing
language IDs were registry-driven rather than hardcoded in application logic. The main
gaps were lifecycle failure coverage, enforceable connection configuration, and provider
edge cases. The directory has no `.git` repository, so commit history could not be audited.

## Problems fixed

| Finding | Fix |
| --- | --- |
| A Redis cleanup failure could skip engine disposal; initialization failures before `yield` could leak resources | Shared `runtime_resources` uses `AsyncExitStack`, registering each cleanup immediately. API and worker use the same lifecycle |
| HTTPX limits and initialization policy were implicit | Explicit connection/keepalive/time budgets, no redirects, no implicit environment proxy/auth settings; HTTP client is reused and closed |
| Public CE could inherit RapidAPI/auth/cookie headers from an injected client | Public requests strip inherited credentials; public RapidAPI header configuration is rejected. Dedicated provider auth remains configurable |
| Supabase/session-only and SSL requirements existed mainly in documentation | Validate application and migration URLs; reject unsupported schemes, unsafe TLS downgrade, unencrypted Supabase URLs, and unsupported Supabase transaction port 6543 |
| Standard `sslmode`/`sslrootcert` parameters could be forwarded as unsupported asyncpg keywords | Normalize URLs into a verified `SSLContext`, support a custom CA, remove URL-only TLS options before connecting |
| Pool sizes and database connect/wait/recycle budgets were fixed or implicit | Configurable bounded application pools and connection/command/wait/recycle budgets; migrations use `NullPool` |
| Readiness could wait on sequential/unbounded infrastructure checks | Concurrent PostgreSQL/Redis probes with a two-second budget and sanitized 503; liveness remains independent; Judge0 is excluded from readiness |
| Result polling did not validate its token | Validate canonical UUID tokens before HTTP; invalid/missing creation tokens terminate without resubmitting; missing remote tokens and permanent 4xx fail immediately |
| GET errors were retried without distinguishing permanent failures; provider cooldowns were discarded | Classify retryability, preserve bounded numeric/date `Retry-After`, avoid immediate re-polling on 429/503, and defer worker claims until cooldown |
| Poll budget did not bound a slow final request | An absolute polling deadline includes HTTP requests, sleeps, and retries |
| Malformed language names could raise `AttributeError`; cache payloads were weakly validated | Strict typed registry validation, validated cache entries, fallback for corrupt cache, optional cache-independent provider diagnostics |
| Redirect responses could be treated as successful JSON | Reject every non-2xx response; disable redirects even on an injected client |
| Foundation failure paths and live language execution lacked evidence | Added mocked tests, a packaged opt-in live diagnostic, real outage/startup/shutdown checks, and three-language API-to-worker execution checks |
| Future commits could accidentally force-track an environment file | CI rejects tracked `.env` variants and verifies ignore rules. The local real JWT secret was absent from all non-secret source/config files scanned |

Only allowlisted language/result fields are returned. Hidden test output and provider
tokens remain private. HTTP provider failures map to sanitized API 503 responses; when
present, the normalized `Retry-After` header is exposed. A submission accepted from cached
language metadata may be queued during an outage and later end as `provider_error`, as
expected for asynchronous evaluation.

## Changed files

Existing files updated:

- `app/core/config.py`, `app/core/errors.py`: connection validation/settings and provider retry metadata.
- `app/db.py`: normalized verified TLS, bounded pools/timeouts, migration `NullPool`.
- `app/main.py`, `app/worker.py`: shared initialization/cleanup, bounded readiness, provider retry/cooldown handling.
- `app/integrations/judge0.py`: credential isolation, strict registry/tokens, response validation, polling deadline and retry behavior.
- `tests/test_judge0.py`, `tests/test_integration.py`: canonical token fixtures and worker retry/cooldown regressions.
- `.env.example`, `.github/workflows/ci.yml`, `README.md`, `VALIDATION.md`: settings, secret-file guard, operating instructions, evidence.

New files:

- `app/core/database_config.py`, `app/runtime.py`, `app/services/health.py`.
- `app/diagnostics/__init__.py`, `app/diagnostics/judge0.py`.
- `tests/test_foundation_config.py`, `tests/test_runtime.py`, `tests/test_readiness.py`,
  `tests/test_judge0_foundation.py`, `tests/test_live_diagnostic.py`.
- `audit/live_judge0.json`, `audit/api_execution.json`, `AUDIT.md`.

## Actual verification results

| Command/check | Result |
| --- | --- |
| `ruff format --check .` / `ruff check .` | Passed |
| `mypy app` | Passed, 29 source files |
| `TEST_DATABASE_URL=... pytest -q` | **171 passed in 13.83s**, including mocked external failures and real PostgreSQL regression tests |
| `pip check`; compile/import checks | Passed |
| Alembic upgrade/check, downgrade/upgrade, offline SQL | Passed on disposable PostgreSQL; no schema drift |
| Linux ARM64 Docker build; Compose `--wait` | Passed; API/PostgreSQL/Redis healthy, worker running, migration exited 0 |
| Container dependency check and Alembic drift check | Passed |
| Container environment | PostgreSQL/migrations use `db`, Redis uses `redis`; public Judge0 has no auth token; `.env` is absent from the image; runtime UID 10001 |
| Actual Judge0-down container | Startup succeeded; live 200; ready 200; `/languages` 503; graceful shutdown exit 0 |
| Actual Redis-down container | Startup succeeded; live 200; ready 503; rate-limited API 503; graceful shutdown exit 0 |
| Actual PostgreSQL-down container | Startup succeeded; live 200; ready 503; database API 503; graceful shutdown exit 0 |
| Separate worker SIGTERM | Exited 0 with shared resources closed |
| Ignore rules and secret scan | `.env`/`.env.production` ignored, `.env.example` allowed; configured real secrets/private keys absent from scanned non-secret files |
| CI secret-file guard | Accepted a safe temporary checkout; rejected a force-tracked synthetic `.env` |

The three live registry-selected versions were submitted to `https://ce.judge0.com`
without RapidAPI credentials. All produced `foundation:LustCode\n` and status `accepted`:

| Language | Registry ID | Version | Direct adapter | API → PostgreSQL/Redis → worker → Judge0 |
| --- | --- | --- | --- | --- |
| Python | 113 | Python 3.14.0 | Passed | Passed |
| Java | 91 | JDK 17.0.6 | Passed | Passed |
| C++ | 105 | GCC 14.1.0 | Passed | Passed |

Evidence is in [live_judge0.json](audit/live_judge0.json) and
[api_execution.json](audit/api_execution.json). No provider tokens or account credentials
are recorded. The temporary end-to-end account, its runs/refresh tokens, and per-user
Redis keys were removed. No question dataset was created.

Reproduce the explicit live check with:

```sh
python -m app.diagnostics.judge0 --output audit/live_judge0.json
```

This makes real submissions and can fail when public CE is unavailable or rate limited;
normal tests and CI remain independent of it.

## Remaining limitations

- The initial hosted Supabase verification gap was resolved on 2026-11-09: connection,
  migrations, RLS/permissions, and API/worker execution now pass. Shared transaction pooling
  remains explicitly unsupported; the verified deployment uses session pooling on port 5432.
- This workspace has no Git history, so historical committed-secret verification is
  unavailable. The current files, ignore rules, Docker context, and new CI guard were checked.
- Live CE results are a timestamped observation, not an availability/quota guarantee.
  Recovery after losing a successful POST response remains at least once: a token that
  was never received/persisted cannot prevent a duplicate execution after recovery.

The development stack remains available at `http://localhost:8000/api/v1/docs`.

## Supabase connection follow-up — 2026-11-09

The previously untested hosted connection was verified after credentials were supplied.
The session-pooler connection on port 5432 passed CA/hostname verification with TLS 1.3
and authenticated through SQLAlchemy/asyncpg. A read-only `SELECT 1` succeeded and the
transaction was rolled back. The CA certificate and its provenance are in `certs/`;
credentials are confined to the ignored native `.env` file (mode 0600).

That connection-only checkpoint made no schema changes. Setup was subsequently completed
under the user's instruction to complete initialization:

- Applied the existing migration `c869d03eecf9`; all seven application tables have RLS.
- Added `compose.supabase.yaml` and selected it by default in private local configuration.
  Containers now use Supabase and read-only CA mounts; local Redis remains active.
- Stopped the unused local PostgreSQL service while retaining its data volume.
- Allowed an eight-second hosted readiness budget after measuring a three-second cold
  connection; verified the resulting healthy Compose stack.
- Added four synthetic-environment Compose tests; the full suite now reports **175 passed**.
- Verified authentication, refresh/logout, private history, and live Python/Java/C++
  execution through the hosted database and worker, plus direct-read denial for both
  `anon` and `authenticated` roles. Removed all temporary verification data.

Current evidence is in `audit/supabase_setup.json` and `audit/supabase_api_execution.json`.
The default restart command is `docker compose up -d --build --wait`; it retains the
selected Supabase mode. Base-only local mode remains available with `-f compose.yaml`.
