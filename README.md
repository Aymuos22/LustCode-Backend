# LustCode backend

FastAPI API and separate Judge0 evaluation worker, using Python 3.12+, SQLAlchemy 2.0,
PostgreSQL, and Redis. The administrative importer onboards a supplied workbook as a
browsable question catalog, enriched with public LeetCode metadata.

## Run locally

```sh
test -f .env || cp .env.example .env
openssl rand -hex 32
# Set JWT_SECRET in .env to that generated value.
docker compose up --build
```

With a fresh `.env.example`, Compose starts local PostgreSQL and persistent Redis,
runs Alembic, then starts the API
and worker. Swagger is at <http://localhost:8000/api/v1/docs>. Local database credentials
in Compose are for development. The application refuses to start without a JWT secret.
The default execution endpoint is `https://ce.judge0.com`; RapidAPI is not required.
Keep an existing `.env` when restarting. If it sets `COMPOSE_FILE` to include
`compose.supabase.yaml`, the same command selects hosted Supabase instead.

For native development with PostgreSQL and Redis already running:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.lock
pip install --no-deps -e .
alembic upgrade head
uvicorn app.main:create_app --factory --reload --no-proxy-headers --no-access-log
# In another terminal with the same environment:
python -m app.worker
```

## Supabase and deployment

Set `DATABASE_URL` to the project's direct PostgreSQL connection or **session** pooler
connection (`postgresql+asyncpg://...`, normally port 5432), and set `DATABASE_SSL=true`.
Passwords in URLs must be percent encoded. `sslmode=require`, `verify-ca`, and `verify-full`
are normalized before connecting with asyncpg. All three use CA and hostname verification;
for a private CA, supply a URL-encoded `sslrootcert=/path/to/root.crt` and mount that
certificate into the container. Supabase URLs without TLS and transaction endpoints
on port 6543 are rejected at startup. This backend supports direct/session connections;
shared transaction pooling is outside the supported configuration.
`MIGRATION_DATABASE_URL` supplies a separate connection for Alembic, which uses `NullPool`.
For native Supabase development, set `READINESS_TIMEOUT_SECONDS=8` to cover the first
remote TLS/authentication handshake; hosted Compose sets this budget automatically.

Use `ENVIRONMENT=production`, HTTPS `CORS_ORIGINS`, a cryptographically random
JWT secret, and private Redis (TLS/authentication when traversing untrusted networks). Swagger and OpenAPI
are disabled in production. Terminate HTTPS at your ingress and restrict direct access
to the API. Configure ingress body and request timeouts, including a slow-upload limit.
The Docker command disables Uvicorn's automatic forwarded-header parsing. The application
accepts forwarded scheme and client identity only from `TRUSTED_PROXY_NETWORKS`.
Leave that list empty when the API is directly reachable. Client-controlled forwarded
headers must not determine rate-limit identity.

### Render deployment

The default [`render.yaml`](render.yaml) uses **only free resources**: the existing
`LustCode-Backend` web service plus private Render Key Value in Singapore. It sets
`EMBEDDED_WORKER_ENABLED=true`, so the same durable PostgreSQL lease-based evaluator
runs as an API background task. It starts with `python -m app.free_serve`, which runs
serialized migrations before opening the API port because free services do not have
pre-deploy jobs. A stopped evaluator makes readiness fail; an in-flight job interrupted
by shutdown retains its lease and can recover after restart. Default application
configuration still leaves this mode disabled for separate-worker deployments.

This is a **demo deployment**, not a production availability guarantee. Free services
sleep after 15 minutes without inbound traffic, and processing resumes after the API
wakes. Free Redis loses quotas/cache contents on restart. Avatar files disappear on
redeploy, restart, or sleep because free web services cannot attach persistent disks.
Supabase retains users, questions, drafts, submissions and evaluation leases. Move
avatars to durable object storage before relying on them across restarts. Render's
workspace free-hour/build/bandwidth limits also apply; this configuration creates no
paid resources. See [Render free-plan limitations](https://render.com/docs/free).

The optional [`render.production.yaml`](render.production.yaml) provisions a Docker API,
a separate Docker worker, and
private persistent Render Key Value in Singapore, while retaining the existing
Supabase database. API/worker each use `0.5c-512mb`, Key Value uses `256mb`, and the API
has a 1 GB avatar disk. These are paid resources: review Render's displayed monthly
estimate before creating the Blueprint. No cloud deployment is implied by this file.

1. Connect Render to `https://github.com/Aymuos22/LustCode-Backend` and create a
   Blueprint from `main` using `render.production.yaml` **only if paid compute is desired**.
2. Enter `DATABASE_URL` in Render's secret prompt. Use the Supabase **session** pooler
   on port **5432**, with the `postgresql+asyncpg://` scheme and a percent-encoded
   password. The Docker image defaults `DATABASE_SSL_ROOT_CERT` to its packaged
   public CA, so an old local certificate path in the URL is overridden even when
   creating a service manually. Render environment variables override this image
   default: remove any stale service-level override or set it to
   `/srv/lustcode/certs/supabase-root-2021.crt` on both API and worker. A different
   database CA must be explicitly supplied with `DATABASE_SSL_ROOT_CERT`.
   Rotate the database
   password previously shared in chat before using it for the public deployment;
   update local secrets and Render together. Do not put credentials in this file.
3. Render generates one fresh JWT secret in the shared environment group. Both
   processes share that secret and the API's database URL. Key Value's connection
   string comes from the private service reference; external access is disabled.
   The local `.env` and `.env.test-account` files are excluded from Git and Docker.
4. Both pre-deploy jobs run `python -m app.release`. A PostgreSQL advisory transaction
   lock serializes their Alembic upgrades. A migration failure stops deployment.
   The migration role needs schema/table ownership and two simultaneous connections
   for the lock and upgrade. The normal API/worker pools each allow 3 + 2 overflow
   connections; allow headroom for release jobs and overlapping worker rollouts.
5. The API uses Render's `PORT`, binding to `0.0.0.0`. Readiness checks PostgreSQL and
   Redis with a 4-second probe budget; liveness remains `/api/v1/health/live`. Judge0 outages do
   not block readiness. Check the worker logs as well as API health: a healthy API
   alone does not prove the queue is being processed.
6. After deployment, use the assigned HTTPS API URL to verify registration, login,
   catalog browsing, sample runs and submissions for Python/Java/C++, polling,
   avatar upload/read across an API restart, and refresh/logout. Confirm requests
   from two real clients have independent rate limits and cannot override identity
   with a forged `X-Forwarded-For` header. Then point the frontend API base URL at
   `https://<assigned-service>.onrender.com/api/v1`.

As requested, this Blueprint sets `CORS_ALLOW_ALL_ORIGINS=true`. Any frontend origin
can call the API; protected endpoints still require bearer tokens, and cross-origin
cookie credentials are disabled. To restrict origins later, set the flag to `false`
and set `CORS_ORIGINS` to a JSON array of HTTPS frontend origins in the shared group.

The Render ingress configuration uses `CF-Connecting-IP` only from configured private
ingress/Cloudflare peer ranges and ignores `X-Forwarded-For` for identity. Verify this
against the actual deployed ingress; do not replace the network list with `0.0.0.0/0`
or `::/0`. Keep the Cloudflare ranges current. A frontend server proxying requests may
share one rate-limit identity unless its ingress is configured separately.

API disk storage restricts this Blueprint to one instance and causes a deployment
interruption. Do not increase API replicas while avatars use this disk; move files
to object storage first. Existing local avatars are not automatically transferred.
Back up Supabase and avatar files and test restoration before public launch. Key Value
uses journal/snapshot persistence and `noeviction`; alert on memory pressure, as full
storage must reject writes rather than discard quota keys. Password hashing and image
normalization each run at most two operations concurrently per API process to bound
memory consumption; load-test against the intended traffic before increasing plans
or concurrency.

Automatic deployments wait for GitHub checks (`autoDeployTrigger: checksPass`); the
workflow runs lint, typing, isolated PostgreSQL tests, migration checks/roundtrips,
Blueprint schema validation, a Docker build, and production container startup with
synthetic URLs containing an unavailable native CA path. The startup probe requires
no external connections and verifies that both API and migration engines initialize,
liveness responds, TLS verification stays enabled, and the process uses UID 10001.
Initial Blueprint creation or manual
deployments still need their build/deploy results inspected. The vendored schema in
`deploy/render.schema.json` is an offline snapshot of Render's official schema,
retrieved on 2026-11-10; refresh it from `https://render.com/schema/render.yaml.json`
when changing Render features.

Enable Render alerts for failed deploys, process restarts, and resource exhaustion;
monitor stale queued/running jobs, provider errors/429s, and database connections.
The public `ce.judge0.com` service has external availability/capacity limits; a
dedicated supported Judge0 deployment is a separate production reliability decision.
This Blueprint does not create a new database, import a new catalog, or create test
accounts. It uses the existing migrated Supabase catalog. Production dashboard
settings, a restore drill, ingress checks, and live execution checks require an actual
Render deployment and are not proven by local tests.

References: [Blueprint specification](https://render.com/docs/blueprint-spec),
[health checks](https://render.com/docs/health-checks),
[persistent disks](https://render.com/docs/disks), and
[Key Value](https://render.com/docs/key-value).

Run `alembic upgrade head` once as a deployment job, then run the API and worker as
separate services. Base `compose.yaml` provides local PostgreSQL. Hosted mode adds
`compose.supabase.yaml`: set `DOCKER_DATABASE_URL` to the Supabase URL with
`sslrootcert=/srv/lustcode/certs/supabase-root-2021.crt` (URL-encoded), and set
`COMPOSE_FILE=compose.yaml:compose.supabase.yaml` in the private `.env` file. Then:

```sh
docker compose up -d --build --wait
```

Hosted mode runs the existing migrations against Supabase, mounts the public `certs/`
directory read-only in the migrator/API/worker, retains local Redis, and excludes the
local database service. `DOCKER_MIGRATION_DATABASE_URL` can supply a separate migration
connection; otherwise it uses `DOCKER_DATABASE_URL`. The native `DATABASE_URL` keeps its
host certificate path, while Docker uses the mounted container certificate path.

To explicitly switch back to the original local database configuration:

```sh
docker compose -f compose.yaml up -d --build --wait
```

Database volumes persist between modes. Never use the local credentials in a hosted
environment. A backend database owner or a dedicated privileged role must
run the application; frontend clients must never receive that database connection.

Migrations enable row-level security on all application tables without
public policies. PostgreSQL table owners bypass RLS so the API's ownership rules still
apply. This blocks direct Supabase Data API access by `anon`/`authenticated` roles, even
if default grants exist. Do not grant those roles `BYPASSRLS` or table ownership. Keep
these tables outside direct frontend access. This application owns its users and JWTs;
it does not use Supabase Auth.

Health endpoints: `/api/v1/health/live` checks the process;
`/api/v1/health/ready` checks PostgreSQL and Redis concurrently. The local budget is two
seconds; hosted Compose uses eight seconds by default to allow a cold remote TLS/login
handshake. `DOCKER_READINESS_TIMEOUT_SECONDS` configures the hosted budget (maximum 10).
The hosted container probe allows 12 seconds and has a 14-second Docker timeout.
Failures return a sanitized 503. Judge0 outages do not make the API unready.
Startup creates clients without connecting to external services, so temporary outages
do not prevent liveness. PostgreSQL/Redis remain required for readiness and admission;
rate limits and quotas continue to fail closed. API and worker share initialization,
and cleanup callbacks run even after partial startup or another cleanup failure.
Monitor worker restarts, old queued/running submissions, terminal provider
errors, provider quotas, database connections, and Redis memory. Each process has a
bounded database pool (default 5 + 5 overflow, configurable with `DATABASE_POOL_SIZE`
and `DATABASE_MAX_OVERFLOW`); size worker/API replicas against Supabase's
connection budget. Redis should use persistence and `noeviction` to retain quotas.
Connection, command, pool-wait, recycling, Redis, and health budgets are documented in
`.env.example`. Native Redis uses `localhost`; Compose uses the `redis` service hostname.
Base Compose uses the `db` PostgreSQL hostname and overrides migration URLs to local.
Hosted mode explicitly selects Supabase for all database clients; a missing hosted URL
is rejected instead of falling back to local PostgreSQL.

The shared HTTPX client has explicit connection/keepalive limits and timeouts, disables
redirects, and ignores implicit environment proxy/auth configuration. Public CE requests
strip inherited RapidAPI and unrelated authentication/cookie headers. Dedicated Judge0
authentication comes only from `JUDGE0_AUTH_TOKEN`/`JUDGE0_AUTH_HEADER`; RapidAPI header
configuration is rejected for `ce.judge0.com`. No RapidAPI credentials are needed.

## API contract

Daily engagement now has a persisted UTC Problem of the Day (`GET /questions/daily`),
a dedicated activity-streak endpoint (`GET /users/me/streak`), and LustCoins. Daily
check-in earns 1 coin; a full accepted POTD submission earns 2 once per user/date.
New grants use these rates; existing ledger entries and balances are preserved.
There are no ordinary-solve or run rewards. PostgreSQL stores an idempotent credit
ledger; free Redis restarts do not reset balances. The wallet, transaction history,
earning rules, and physical product ordering are documented in the frontend handoff.
The catalog contains only Premium Condom Pack (12 pcs), Water-Based Lubricant (100ml),
Body Massage Oil (100ml), and Soft Adjustable Blindfold, costing 500/1000/2000/4000 coins
respectively. These products have no size selection. Checkout validates an Indian shipping
address and atomically reserves stock, creates an order and deducts coins. Idempotent
retries cannot charge twice. Customers have private order history and can cancel placed
orders for a one-time refund. Fulfillment staff can process, record tracking, deliver or
cancel orders; actual shipping is manual. No courier booking is configured. Apply
`8ae36dc2f109` and update every API/worker sharing the database before enabling the UI.

The frontend feature handoff is [FRONTEND_API_HANDOFF.md](FRONTEND_API_HANDOFF.md), with
exact new methods, payloads, filters, draft conflict behavior, and proxy requirements.
The backend now provides question-specific custom inputs, server topics, stored
difficulty-based collections, featured/random selection, filtered neighbor navigation,
account-synced drafts and preferences, persistent avatars, and authoritative UTC streaks
and acceptance rates. Existing questions, authentication, judging, and history are reused.
Apply migration `e42b19c06d31` before running this version. No frontend changes are made.

The local standard test account is `test.account@example.com` (username `lustcode_test`).
Its generated password and API URL are saved in the private `.env.test-account` file,
which is ignored by Git and restricted to its owner (`0600`). Use its email/password
with `POST /api/v1/auth/login`, or through Swagger at `/api/v1/docs`. This is an ordinary
application account retained for manual testing. Its custom runs remain in private
submission history. Live flow results are in [`audit/test_account_flow.json`](audit/test_account_flow.json).

All endpoints use `/api/v1`. Single results return `{"data": ...}`. Collections return
`{"data": [...], "total": N, "page": 1, "page_size": 20}` (maximum page size 100).
Errors return `{"error": {"code": "...", "message": "...", "request_id": "..."}}`.
Validation errors add safe field details and omit submitted values. Logout returns 204.
Swagger describes fields, enums, UUIDs, authentication, and validation constraints.

| Endpoint | Purpose |
| --- | --- |
| `POST /auth/register`, `/auth/login` | Issue access and refresh tokens |
| `POST /auth/refresh` | Rotate a one-time refresh token |
| `POST /auth/logout` | Revoke a refresh-token family |
| `GET`, `PATCH /users/me` | Private profile and bio updates |
| `GET /users/me/progress`, `/users/me/statistics` | Progress and coding statistics |
| `GET /users/{username}` | Public username, bio, ID, joined date |
| `GET /questions` | Published questions, difficulty/search filters, pagination |
| `GET /questions/{uuid}` | Statement, public content, visible sample cases |
| `GET /languages` | Available Python 3, Java, C++ versions from the configured provider |
| `POST /runs` | Queue a run with custom stdin, without awarding progress |
| `POST /questions/{uuid}/runs` | Run the question solution against visible samples only, without awarding progress |
| `POST /submissions` | Queue evaluation against a question's complete test suite |
| `GET /submissions`, `/submissions/{uuid}` | Current user's history, source, and safe results |
| `GET /leaderboard` | Solved-question counts, with deterministic username tie ordering |

Protected requests require `Authorization: Bearer <access_token>`. Access tokens expire
after 15 minutes by default. Refresh tokens are opaque random secrets stored only as
SHA-256 digests, rotate atomically, and expire after 30 days (sliding on refresh).
Reusing a revoked refresh token revokes its entire family, including its replacement;
clients must serialize refresh requests. Logout revokes refresh tokens in that family;
existing access tokens remain valid until their short expiry. Public profiles never
include email, progress details, or submissions. Token endpoint responses intentionally
contain the newly issued credentials; no user/profile response contains credentials.

Execution payloads accept `language` (`python`, `java`, `cpp`), `source_code`, and an
optional provider `language_id` from `/languages`. Submissions require `question_id`;
runs accept `stdin`. If the version is omitted, the matching active language with the
highest provider ID is selected and its exact name is saved with the submission. Pin
an ID for reproducibility. Custom `/runs` use complete stdin/stdout programs; Java
defines `class Main`. Catalog `/submissions` use the supplied `starter_code` and
`evaluation_contract`: usually a `Solution` method, with separate class/design and
tree-codec contracts. Read the question detail before building the editor. Verified
drivers provide list/tree/node types, fixture-only fields, and platform hooks. C++
judged submissions compile with C++17. User-controlled compiler flags are not accepted.

All execution endpoints return 202 with a persisted submission ID. Poll
`GET /submissions/{id}` until status is terminal. `accepted` on a custom run means the
program finished successfully, without asserting correctness. Function/class evaluation
runs each private snapshot at Judge0, then compares the full JSON result in the worker.
All cases are evaluated; the first failing case in test
order determines the overall verdict, runtime is summed, and memory is the maximum.
Repeated accepted submissions award a question only once. Statistics exclude sample and
custom runs and use UTC activity dates.

### Run samples before submitting

The editor's **Run** button calls `POST /questions/{question_id}/runs` with the same
solution source and language used for Submit:

```json
{
  "language": "python",
  "source_code": "class Solution:\n    def twoSum(self, nums, target):\n        seen = {}\n        for i, n in enumerate(nums):\n            if target - n in seen:\n                return [seen[target - n], i]\n            seen[n] = i\n"
}
```

`language_id` is optional; discover current IDs through `/languages`. The question UUID
is supplied only in the URL. Authentication
is required. Poll `GET /submissions/{id}` using the returned ID. Sample runs have
`mode: "run"`, a non-null `question_id`, and only visible sample results. Each result
includes `stdin`, `expected_output`, `stdout`, verdict, and diagnostics. These are private
snapshots, so later question edits cannot change the run's expected answer.

Every enabled question has at least one executable sample, including independent
LustCode contracts. Sample runs use the normal Python/Java/C++ drivers, semantic
comparators, resource limits, pending-job limit, and daily execution quotas; only
selected visible cases consume execution quota. They do not create or update progress,
attempt counts, statistics, or solve credit. `accepted` here means the visible samples
passed; Submit still evaluates the complete visible and hidden suite.

Unsupported/invalid questions return 409; a valid suite without samples returns
`samples_unavailable` (409), before language discovery or execution quota reservation.
An optional `test_cases: [{"stdin": "[[2,8],10]"}]` runs user-provided typed fixture
inputs instead of samples. Custom inputs have no reference expected answer; accepted
means execution succeeded. Responses expose `evaluation_scope` (graded, samples,
custom, or playground), so clients can label that distinction accurately. Full custom
input and design-operation formats are documented in the frontend handoff.

The existing `/runs` endpoint continues to accept complete stdin/stdout programs for
the Playground. Hidden `stdin` and `expected_output` fields remain null in all APIs.

## Evaluation and security decisions

Routes validate and delegate; services implement auth/admission/presentation; repositories
query data; `integrations` isolates Redis and Judge0; `worker.py` evaluates outside FastAPI.
Submitted code is never executed on the API/worker host.

PostgreSQL is the durable job source. Admission commits the submission and private test
snapshots in one transaction. Redis provides atomic rate limits, daily execution quotas,
language discovery caching, and bounded worker wakeups. Workers also scan PostgreSQL,
so a lost wakeup cannot lose work. `FOR UPDATE SKIP LOCKED` claims jobs; renewable leases
and lease IDs prevent stale workers from overwriting another worker's checkpoints.
Completed test results and provider tokens survive restarts. Transient provider failures retry
with backoff up to three worker attempts, then terminate as `provider_error`.

There is no cross-system exactly-once guarantee: a crash after Judge0 accepts a POST but
before its token is persisted can cause a repeated execution after lease recovery.
HTTP POST is never automatically retried. Known tokens are reused. GET polling uses
bounded retries/deadlines; 429, invalid responses, oversized responses, and outages are
classified without returning provider internals. Polling has a total deadline, validates
canonical UUID provider tokens before HTTP, and handles both queued and processing states.
Permanent HTTP errors, missing tokens (404), and invalid tokens fail without repeated
polling/submission. HTTP 429 and 503 `Retry-After` values (seconds or HTTP dates) are
preserved with a 1–300 second bound; the worker releases the job until its cooldown.
Terminal provider errors do not resubmit code. CPU/wall/memory/file limits come only
from server policy; execution networking is disabled in the Judge0 request. Your own
Judge0 deployment must enforce sandboxing and network isolation independently.

CE does not expose a portable memory-limit status. Explicit memory-failure diagnostics
are classified as `memory_limit_exceeded`; ambiguous crashes remain `runtime_error`.
Output decoding tolerates non-UTF-8 bytes, provider responses are bounded at 1 MB, and
stored diagnostic fields are truncated to 16,384 characters.

Hidden cases are snapshotted privately. Their stdout, stderr, compiler diagnostics,
input, expected output, and provider token never leave submission APIs; only verdicts
and resource measurements are exposed. Arbitrary question JSON is never serialized:
only documented public content fields are allowlisted. Source code and results are
visible only to the submitting user. Logs omit raw exception messages and request bodies.

Defaults: 64 KiB source, 128 KiB total request body, 120 requests/IP/minute,
10 auth requests/IP/minute, 100 submissions/user/UTC day, 1,000 test executions/user/day,
5 unfinished jobs/user, and 100 cases/question. Authenticated requests also have a per-user
rate limit. Quotas count a custom run as one execution and a submission as all its cases.
Redis failures reject rate-limited operations with 503. Quota reservation precedes the
database commit, so failed persistence can conservatively consume budget; failed jobs
are not refunded. Keep Redis durable; resetting it resets quotas. Never assume the
public Judge0 service has capacity or availability; set a dedicated URL/token when needed.

## Independent question ingestion

Use a trusted administrative process connected to PostgreSQL. There are no public write
endpoints. Tables use UUIDs and timezone-aware timestamps.
The ORM supplies UUID/time defaults; a direct SQL importer must supply these explicitly.

For judgeable questions, create a question as unpublished, add its test cases, validate,
then publish in the same transaction. Browsable catalog entries may be published without
tests; their API responses set `is_judgeable=false` and submissions return 409.
`slug` is unique; `(question_id, position)` is unique. Set positive CPU
seconds, memory at least 16,384 KiB, a supported difficulty, and no more than the configured
case cap. Keep input/output sizes within your provider's limits. Effective CPU/memory
limits are capped by application settings. Use test positions to define evaluation order.
Cases are hidden by default; only explicit `hidden=false` samples appear publicly.

`questions.content` is JSONB with public keys:

- `hints`: array of strings
- `explanation`: string or null
- `constraints`: array of strings
- `starter_code`: object mapping supported language names to source strings
- `source`: official provider, question number, title, slug, URL, premium/detail status
- `supported_languages`: supported backend languages; `[]` for SQL/shell, `null` if unknown
- `examples`: factual function/design input/output pairs, separate from runnable samples
- `interface`: function signature or class constructor/methods, or SQL/shell classification

`tags` is a JSONB array of strings. Do not put secret data inside these public fields.
Hidden inputs and expected outputs belong only in `test_cases`. Other JSON keys are
ignored by public responses. Use a new question/version for materially different tests
if leaderboard consistency matters: queued work retains its original test snapshot,
and previously solved progress is intentionally not revoked by later content edits.

The supplied 1–300 workbook is bundled in
[`data/questions/leetcode_001_300.json`](data/questions/leetcode_001_300.json).
Every main statement is preserved verbatim. Current public LeetCode titles, difficulties,
tags, examples, constraints, and interface metadata supplement that text. Premium entries
use only the public catalog metadata and supplied workbook text. See
[`data/questions/README.md`](data/questions/README.md) for scope and provenance.

Prepare a bundle, review it, then apply it to the configured database:

```sh
pip install -r requirements-ingest.lock
python -m app.ingestion --workbook '/path/to/questions.xlsx' --bundle data/questions/leetcode_001_300.json
# Applying an existing bundle needs no network access to LeetCode:
python -m app.ingestion --bundle data/questions/leetcode_001_300.json --apply
```

Without `--apply`, the command prepares or validates data without writing to PostgreSQL.
Imports run in one transaction, serialize concurrent imports, use deterministic UUIDs,
and preserve existing test cases. Reapplying the same bundle creates no duplicates.
An import aborts if it would overwrite a manually edited main statement. Private workbook
provenance and body hashes are stored internally and excluded from API responses.
The separate judging installer adds independently authored suites for all 283 algorithm
questions. The 17 SQL/shell entries remain browsable with submission disabled. The
43 premium entries use user-authorized independent LustCode interfaces and tests; their
public `evaluation_contract.origin` is `lustcode`. These contracts are documented through
the API, including Unicode encoding, batched operations, and tie-breaking rules.

```sh
alembic upgrade head
# Validate suites and inspect coverage without writing:
python -m app.judging
# Install all reviewed suites atomically:
python -m app.judging --apply
```

The catalog importer preserves installed judging contracts and starter code. The suite
installer batches database reads/writes, serializes concurrent installs, preserves
unrelated questions, and refuses to overwrite manually edited tests. Main statements
remain unchanged. Statement and suite hashes prevent unverified edits from being admitted
for evaluation. Every submission snapshots its driver contract and cases, so later
catalog edits cannot change queued results.

Clients use `is_judgeable`, `judgeable_languages`, `judging_status`, `starter_code`, and
`evaluation_contract` from question responses. Ready premium questions explicitly expose
all three supported languages. Unsupported, incomplete, or changed suites return 409
before provider discovery or quota reservation. Verified interfaces correct fixture
metadata that differs from the actual callable method, such as cycle positions or
node references.

Comparators handle order-independent collections, multiple valid witnesses, float
tolerance, in-place prefixes, balanced BSTs, Gray codes, and topological orders. Special
drivers enforce deep-copy and node-identity requirements. Tests arrive through stdin;
expected answers stay outside the executed program. Full provider output is compared
before diagnostics are capped at 16 KiB. Invalid return structures are wrong answers;
exceptions from user code remain runtime errors. Hidden data stays excluded from API
responses. `accepted` means every case in the installed LustCode suite passed; the suites
are finite and independently authored.
Debug stdout is routed to diagnostics during judged method/class execution, so it does
not replace the returned answer. Custom stdin/stdout runs retain their normal output.

## Validation

```sh
ruff format --check .
ruff check .
mypy app
pytest -q -m 'not integration'
# Optional PostgreSQL integration suite, isolated into a random schema per test:
TEST_DATABASE_URL=postgresql+asyncpg://test:test@localhost:55432/lustcode_test pytest -q
alembic check
```

Integration credentials must permit creating/dropping schemas in a disposable database.
Tests never call public Judge0; HTTP behavior uses HTTPX MockTransport, and integration
evaluation uses a fake provider. Redis Lua behavior is tested with fakeredis. CI runs
PostgreSQL tests, formatting/lint/types, migration drift detection, and downgrade/upgrade.
Dependency lock files record the verified versions; regenerate and rerun checks when
upgrading. See `VALIDATION.md` for the checks actually run in this workspace.

For an explicit live check, which submits one small program in each supported language:

```sh
python -m app.diagnostics.judge0 --output audit/live_judge0.json
# Complete live submission flow using the retained standard account:
python -m app.diagnostics.judging --output audit/judging_live.json
# Native driver compilation and stdin/serialization checks:
PYTHONPATH=. python scripts/verify_judging_compilers.py
PYTHONPATH=. python scripts/verify_judging_transport.py
```

The Judge0 diagnostic checks the live registry and known output without writing
application data. The judging diagnostic creates real graded submissions under the
retained standard test account, checks verdicts/privacy/progress, and logs out its refresh
session. Both omit credentials/provider tokens and exit nonzero on failed checks.
The native checks compile trusted fixture programs locally; they require Clang and a
Docker JDK image. Submitted user programs execute only at Judge0.
See `AUDIT.md` for the foundation audit, changes, evidence, and remaining limitations.

Protocol references: [Judge0 CE API](https://ce.judge0.com/),
[SQLAlchemy asyncpg dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.asyncpg),
and [FastAPI JWT/Argon2 authentication](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/).
Supabase connection/TLS guidance follows the [official connection documentation](https://supabase.com/docs/guides/database/connecting-to-postgres).
