# Validation record

Latest validation: 2026-11-09. Local regression tests use Python 3.12.15 on macOS ARM64,
disposable PostgreSQL 16.15, Redis 7.4.12, and the dependency locks (SQLAlchemy 2.0.57).
Hosted Supabase verification is recorded below.

| Check | Result |
| --- | --- |
| `ruff format --check .` | Passed |
| `ruff check .` | Passed |
| `mypy app` | Passed, 62 source files |
| `TEST_DATABASE_URL=... pytest -q` | 316 passed in 51.80s (latest recheck) |
| `pip check` | Passed |
| `python -m compileall -q app migrations` | Passed |
| Application factory/configuration load | Passed |
| Alembic upgrade and drift check | Passed, no new operations |
| Alembic downgrade to base and upgrade to head | Passed on the disposable database |
| Alembic offline SQL generation | Passed |
| RLS flags on all seven application tables | Enabled |
| Unprivileged PostgreSQL role with table grants | Cannot read an inserted user; owner can read it |
| Native Uvicorn and worker startup | Passed |
| HTTP liveness, readiness, OpenAPI, missing-auth response | Passed against the native API with real PostgreSQL/Redis |
| Real Redis concurrent quota reservations | Exactly 2 admitted from 10 simultaneous attempts with a quota of 2 |
| Dependency locks versus installed distributions | Both match |
| `docker compose config --quiet` | Passed |
| Docker Linux ARM64 image build | Passed, final source built with cached dependencies |
| Compose startup and migrations | Supabase schema at head; API/Redis healthy; worker running; migration exited 0; local database stopped |
| Container runtime user | UID 10001 |
| Container dependency and migration drift checks | Passed |
| Compose API smoke checks | Liveness/readiness, OpenAPI, empty question catalog, leaderboard, auth, validation, and CORS passed |

The 175 tests cover Argon2, JWT claim/expiry/signature validation, token rotation/replay
and concurrent generations, account uniqueness, request validation and redaction,
body limits including chunked uploads, CORS, rate limits, atomic quotas, database
failures and transaction rollback, public-question filtering, hidden-data privacy,
submission ownership, custom runs, execution verdicts, progress/statistics/leaderboards,
worker claims, lease recovery/fencing, persisted-token reuse, provider failures and
retry limits, language/version selection, Base64 including wrapped output, malformed
responses, deadlines, network timeouts, and response-size limits. Foundation additions
cover partial startup/cleanup/cancellation, Supabase TLS and pool configuration, corrupt
registries/caches, credential isolation, invalid tokens, redirects, cooldowns, readiness
deadlines and required-infrastructure failures. Four Compose configuration tests verify
local/hosted selection, required hosted credentials, certificate mounts, probe budgets,
and a separate migration connection using synthetic environment files.

PostgreSQL integration tests create and drop random schemas; application questions
are never seeded. Judge0 is mocked in every automated test. Separate explicit live checks
passed for Python 113, Java 91, and C++ 105, both through the adapter and through the
running API/worker. Evidence is in `audit/live_judge0.json` and `audit/api_execution.json`.
Hosted Supabase connectivity, migrations, permissions, and live API/worker execution
were subsequently verified on 2026-11-09 as recorded below.

A local `.env` was generated with a random JWT secret and mode 0600. Its values are
excluded from version control and the Docker build context. Compose contains local
development database settings; use the documented environment settings for Supabase.

The development stack is running on `http://localhost:8000`; documentation is at
`/api/v1/docs`. Stop it with `docker compose down` (named development volumes persist).
Temporary test containers were removed after verification.

The foundation audit also exercised actual Judge0/Redis/PostgreSQL outage containers:
startup/liveness remained available, readiness correctly reflected required dependencies,
dependent requests returned sanitized 503 responses, and shutdown exited 0. A separate
worker exited 0 on SIGTERM. See `AUDIT.md` for the full change list and limitations.

## Hosted Supabase connection — 2026-11-09

Configured the native `.env` for the supplied Supabase session pooler (port 5432), with
URL-encoded credentials, `DATABASE_SSL=true`, and the public Supabase CA certificate.
The certificate chain and hostname verified with TLS 1.3. SQLAlchemy/asyncpg authenticated
successfully and returned `1` from `SELECT 1` inside a read-only transaction, which was
rolled back. No schema or application data was changed.

At that connection-only checkpoint, no migration ledger existed. The setup was then
completed as described in the next section. Credentials remain only in the ignored
`.env` with mode 0600.

## Supabase setup completed — 2026-11-09

- Applied the existing `c869d03eecf9` migration to hosted Supabase; all seven application
  tables exist with RLS enabled. Native and container Alembic checks report no drift.
- Configured default Compose selection through the private `COMPOSE_FILE` setting and
  `compose.supabase.yaml`. API, worker, and migration container use Supabase with verified
  TLS and read-only CA mounts. Local Redis remains active. The unused local database
  was stopped and its named volume retained.
- A measured cold remote connection took about 3 seconds. Hosted readiness now allows
  8 seconds, with a 12-second HTTP probe and 14-second Docker probe timeout. Local-mode
  defaults remain unchanged. The native Supabase configuration uses the same 8-second budget.
- API liveness/readiness, profile authentication, refresh rotation/logout, private
  submission history, and live Python/Java/C++ execution passed against Supabase.
- Direct `anon` and `authenticated` database reads of a real temporary user row returned
  zero rows under RLS, while its owner could read it.
- All temporary verification accounts, runs, refresh tokens, and per-user Redis keys
  were removed. No question dataset was seeded.

Evidence: `audit/supabase_setup.json` and `audit/supabase_api_execution.json`.

## Running-system recheck — 2026-11-09

All checks passed again against the running Supabase-backed stack. The full automated
suite passed 175 tests in 18.00 seconds; formatting, lint, types, dependencies, imports,
and migration drift checks passed. API and worker source hashes match the workspace.

Live checks passed for health/OpenAPI, public endpoints, CORS/body restrictions,
registration/login/profile privacy, refresh rotation/replay protection, logout,
submission ownership/history, progress/statistics, seven-table RLS enforcement,
direct anonymous/authenticated read denial, and isolated real Redis quota/rate limits.
Python, Java, and C++ execution returned the expected output. Additional Python runtime
failure and Java compilation failure returned the correct terminal verdicts.

Temporary accounts, submissions, tokens, quota keys, and the disposable test database
were removed. No application source fixes or schema changes were required. Full results
are in `audit/current_verification.json`.

## Workbook catalog onboarding — 2026-11-09

The user selected a browsable sample catalog. Imported 300 workbook statements verbatim
with public LeetCode metadata; no database migration, function drivers, or test cases
were added. The first Supabase import created 300 questions; a second import reported
300 unchanged, zero created/updated.

Validation executed:

- `ruff format --check app tests`: 49 files formatted.
- `ruff check app tests`: passed.
- `mypy app`: passed, 34 source files.
- `TEST_DATABASE_URL=postgresql+asyncpg://test:test@localhost:55432/lustcode_test pytest -q`:
  **202 passed in 22.74s**, using disposable PostgreSQL schemas, fake Redis, and mocked
  external HTTP/provider dependencies.
- `pip check`: no broken requirements.
- All 300 bundled statements compared directly against workbook cells, then all 300
  stored statements and metadata compared against the bundle in Supabase.
- Docker image built and API/worker redeployed; live readiness and liveness checked.
- Live API: three pages contain exactly 300 ordered source IDs, difficulty counts match
  77/173/50, search works, fourth page is empty, and eight representative details preserve
  the exact workbook text, expose enrichment, hide private provenance, and report
  `is_judgeable=false` with no fabricated runnable samples.

New tests cover workbook validation, formula rejection, exact statement preservation,
public-only premium handling, identity/hash validation, public example/interface parsing,
mocked pagination/rate limits/provider failures, transactional idempotent/concurrent
imports, manual-edit rollback, preservation of hidden cases, API metadata privacy, and
409 submission rejection without provider execution or quota consumption.

Current catalog results are in `audit/question_ingestion.json`; earlier foundation and
execution records remain historical. This catalog is browsable, with execution support
deferred until verified drivers and private cases are supplied.

## Standard account flow — 2026-11-09

Created and retained ordinary account `lustcode_test` / `test.account@example.com` in
Supabase. Its generated password is in Git-ignored `.env.test-account` with permissions
`0600`; the database stores an Argon2 hash. No application code or schema changes.

Live checks passed for registration, correct/incorrect password login, authentication
requirements, persistent profile editing, public-profile privacy, all 300 catalog
entries, search/difficulty filters, question details/404, rejection of unjudgeable
submissions without creating a job, Python/Java/C++ runs with expected output, private
history, unchanged progress/statistics, no leaderboard credit from custom runs, refresh
rotation, and logout invalidation of refresh tokens. Three accepted custom runs are
retained in the test account's history. Verification refresh sessions were logged out;
the account remains available for a fresh password login. Existing access tokens follow
their normal expiry, as documented by the API contract.

Results are in `audit/test_account_flow.json`. Passwords and tokens are excluded from
that report. The earlier 202-test regression result remains unchanged; this check used
the live API, Supabase, Redis, worker, and public Judge0 service.

## Question judging — 2026-11-09 (v2, historical)

Judging is installed for all 283 algorithm questions in Python, Java, and C++. The
17 SQL/shell questions remain disabled by user choice. The 43 premium entries use
explicitly authorized independent LustCode contracts. All 300 workbook bodies remain
unchanged. Supabase contains 2,769 verified suite cases, including 2,195 hidden cases.
Current suite version: `authored-v2-domain-validated`. Out-of-domain boundary fixtures
were corrected before final verification; generation checks public bounds and selected
input promises, and the catalog importer requires review for constraint changes.

Executed checks:

- Full isolated PostgreSQL suite: **263 passed in 20.95s**, with mocked external
  dependencies. Coverage includes every Python driver against its complete authored
  suite, generated cases, special pointer identities, runtime failures, output privacy,
  schema validation, snapshot isolation, and rejection of unverified edits.
- All 283 generated C++ interfaces compiled with C++17; all 283 Java interfaces compiled.
- 35 native C++/Java stdin and serialization checks passed, including Unicode, control
  characters, arrays, nested containers, node structures, and a 9,000-element Java input.
- Ruff formatting/lint and mypy passed; `pip check` found no broken requirements.
- Migration `d7e901a48b22`: upgrade, drift check, downgrade, re-upgrade passed on disposable
  PostgreSQL. Hosted Compose then applied the migration; all seven tables retained RLS.
- Supabase verification compared all 300 statements and all 2,769 cases against source
  data and suite hashes. Reinstall: 283 unchanged. Catalog reimport: 300 unchanged,
  preserving judging configuration and cases. Batched idempotent install took 1.62s.
- **20 live submission scenarios passed** through the real API/worker/Judge0 pipeline:
  correct solutions in all languages; wrong answer, compilation error, runtime error,
  time limit; in-place array mutation, linked lists, graph cloning, alias rejection,
  median-stream operations, large output, Unicode codec, first-bad-version hook,
  and tree-codec round trip. Incorrect attempts awarded no solved credit; repeated
  correct submissions in different languages awarded the question once.
- These include **three live debug-output scenarios** after stdout isolation.
  Python prints, Java System.out, and C++ printf/cout were preserved as diagnostics;
  returned answers remained accepted. Hidden outputs and diagnostics stayed redacted.

Evidence: `audit/judging_verification.json`, `audit/judging_live.json`, and
`audit/judging_debug_output.json`. Source artifacts and reports were scanned against
actual configured credentials without printing their values. The test account and its
graded history are retained; verification refresh sessions were logged out.

These finite authored suites do not prove correctness on every possible input or enforce
every asymptotic complexity requirement. Public Judge0 throughput, quotas, availability,
and compilation latency remain external constraints. All Python reference suites ran
locally; Java/C++ compiled across the entire catalog, with representative programs
executed live. Normal operation uses the existing single worker; three workers were
used temporarily to complete live verification concurrently.

## Question sample runs — 2026-11-09 (v3 sample-run verification, historical)

Added `POST /questions/{question_id}/runs` for running normal solution code against
visible samples before Submit. Requests contain `language`, `source_code`, and optional
`language_id`; authentication is required. The 202 response is polled through the
existing submission detail endpoint. Sample runs use `mode=run` with the question ID.
Inputs, expected outputs, diagnostics, and verdicts are returned for visible results;
hidden input/output fields remain null in full-submission results.

All 283 enabled questions now have at least one executable sample. For the 49 questions
without usable source examples, the installer publishes one domain-validated authored
case. Version `authored-v3-visible-samples` contains 623 visible and 2,146 hidden cases
(2,769 total); every question retains at least two hidden cases. All 300 workbook
statements remain unchanged. Supabase suite hashes match the generated data. Reinstall
left 283 suites unchanged; catalog reimport left 300 records unchanged. No schema
migration was needed; revision remains `d7e901a48b22` and all seven tables retain RLS.

- **283 automated tests passed in 28.56s**, including 20 new sample-run integration
  cases using isolated PostgreSQL and mocked Judge0/Redis dependencies. Coverage includes
  every language, existing and absent progress, visible-only snapshots, immutable queued
  evaluations, ownership, hidden redaction, quotas, malformed requests, unavailable
  samples, provider failures, and passing samples followed by a failing full submission.
- Ruff format/lint, mypy (56 source files), compileall, and pip check passed.
- **11 real API/worker/Judge0 checks passed in 274.75s**: 10 sample runs covering correct
  Python/Java/C++ solutions, wrong answer, compilation error, in-place mutation, tree,
  independent contract, codec, and a sample-only solution; the eleventh check confirmed
  that the same sample-only solution fails the full hidden suite.
- Live sample runs left progress and statistics unchanged. Regression tests also verify
  no changes to attempts or leaderboard credit, including already-solved questions.
- Normal deployment uses one worker. API readiness/liveness and OpenAPI are checked,
  and running API/worker Python sources are compared with the workspace.

Evidence: `audit/sample_runs_verification.json`, `audit/sample_runs_live.json`, and the
updated `audit/current_verification.json` / `audit/judging_verification.json`. The older
20-scenario full-judging live report remains timestamped evidence for v2; it was not
rerun as part of this change. Driver code and native signatures are unchanged.

Sample Run uses installed visible cases; editable custom function fixtures are not
implemented. The separate `/runs` endpoint still supports complete stdin/stdout
programs. Passing samples does not guarantee passing the full suite. Public Judge0
availability, quotas, and latency remain external limitations; this verification does
not establish production load readiness.

## Frontend feature APIs — 2026-11-09 (current)

Implemented all eight requested feature areas. The existing question-run endpoint accepts
optional typed custom fixtures; topics/catalog filters, stored difficulty collections,
featured/random selection and filtered navigation operate on published database rows.
Drafts use account/workspace/language ownership, optimistic revisions and reset tombstones.
Preferences merge validated partial updates. Avatars use verified PNG/JPEG/WebP input,
fresh metadata-free PNG output, persistent storage, and current-owner media lookup.
Existing statistics now expose UTC activity streak and evaluated-attempt acceptance rate.
The API reports explicit graded/samples/custom/playground evaluation scope. Original
authentication, refresh rotation, full grading, and hidden privacy remain covered.

- **315 tests passed in 32.81s**, with zero failures/skips. The 32 added tests cover
  combined filters, static-route precedence, empty catalogs, real collection counts and
  private completion, existing/absent/concurrent drafts, stale resets, ownership, preference
  concurrency, registry mismatches/outages, custom function/design input validation,
  custom execution failure/isolation, image MIME/size/dimensions/animation validation,
  avatar replacement/removal and failed-commit cleanup, and streak/rate rules.
- Ruff formatting/lint, mypy (61 app files), compileall, and pip check passed. Pillow is
  pinned in runtime/development locks for verified image processing.
- Migration e42b19c06d31: disposable PostgreSQL upgrade, no-drift check, previous-head
  downgrade/re-upgrade, and full base/head round trip passed. Hosted deployment applied
  the migration; hosted Alembic drift check reports no new operations. All nine application
  tables have RLS enabled. Additive defaults preserve preceding-version inserts.
- **Eight real API/worker/Judge0 executions passed in 153.67s including API checks**:
  Python/Java/C++ custom functions, a custom design class, all three full-program Playground
  starter templates, and the existing visible-sample flow. Graded progress/statistics did
  not change. Catalog/topics/collections/random/featured/navigation, draft conflicts/reset,
  preference updates, and avatar upload/public-read/removal also passed against the live API.
  Live verification restores preferences/removes its temporary image and draft source;
  run history and a revision tombstone are retained on the ordinary test account.
- All 300 original workbook statements and all 2,769 installed cases match the generated
  source data. The 623 visible / 2,146 hidden split and 283 enabled questions are unchanged.
  Running API/worker sources match the workspace; Compose uses one worker and a persistent
  avatar volume. Frontend source hashes are unchanged.

`FRONTEND_API_HANDOFF.md` documents exact methods, request/response shapes, filters,
errors, defaults, permissions, quotas, polling, and frontend proxy integration changes.
Evidence: `audit/frontend_features_verification.json` and `audit/frontend_features_live.json`.

Custom runs have no expected-answer oracle and do not establish correctness. Input
validation enforces typed fixture representation, not every prose constraint/precondition.
Multiple API replicas require shared avatar storage; file/database backup coordination
and orphan-file cleanup remain operational concerns. The frontend proxy changes were
documented, not implemented. Public Judge0 capacity and production load readiness remain
outside this verification. Older validation sections above are timestamped evidence.
