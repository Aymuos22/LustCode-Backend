# LustCode frontend API handoff

Backend prefix: `/api/v1`. Development base: `http://127.0.0.1:8000/api/v1`.
Interactive documentation: `/api/v1/docs`; OpenAPI: `/api/v1/openapi.json` in development.
The frontend reference was inspected; no frontend files were changed.

Question `title` values include the official algorithm name followed by non-graphic
LustCode wordplay. Render `title` for the heading; `source.title` remains the original
official name for source attribution. This applies consistently to catalog/detail,
collections, featured, and random responses. IDs/slugs and execution contracts remain
stable, and the existing search finds both names and taglines.

Single responses use `{"data": ...}`. Pages use
`{"data": [...], "total": 0, "page": 1, "page_size": 20}`. Errors use
`{"error":{"code":"...","message":"...","request_id":"..."}}`, with validation
`details` where applicable. Examples below illustrate contracts rather than live metrics.

Protected endpoints require the existing Bearer access-token authentication. Keep the
frontend's server-side session handling and refresh rotation. Serialize refreshes; replay
of an old refresh token revokes its family. Never expose refresh tokens to client code.
Public endpoints can be called without authentication. Collections accept optional
authentication: valid credentials add the caller's completion data, invalid credentials
return 401. Never substitute another user's ID in a request body.

## Question Run: samples and custom inputs

`POST /questions/{question_id}/runs` is authenticated and returns **202**.
It accepts the same solution method/class source as Submit. Runtime IDs are optional
and must come from `/languages`; no compiler flags or resource limits are client-settable.

Run all installed visible samples (existing behavior):

```json
{"language":"python","source_code":"class Solution:\n    def twoSum(self, nums, target):\n        return [0, 1]\n"}
```

Run user-edited cases:

```json
{
  "language":"python",
  "source_code":"class Solution:\n    def twoSum(self, nums, target):\n        return [0, 1]\n",
  "test_cases":[{"stdin":"[[2,8],10]"},{"stdin":"[[3,4],7]"}]
}
```

Omit `test_cases` (or use null) to run visible samples. A supplied list must contain
1–10 cases. Each `stdin` is a JSON-encoded array of positional fixture arguments, at
most 16,384 UTF-8 bytes. The entire JSON request is limited to 131,072 bytes; source
is limited to 65,536 UTF-8 bytes. Empty lists, unknown case fields, expected answers,
hidden flags, and invalid typed/arity inputs return 422. Custom inputs validate against
the installed fixture contract, not every English-language problem constraint or design
method precondition; violations of those preconditions can produce runtime errors.

Use `question.evaluation_contract.fixture_signature` for function fixture arguments,
and `evaluation_contract.design` for class operations. `signature` and the effective
`interface` still describe the method the user implements. Pointer/hook problems can
require fixture-only arguments such as a cycle index. Start from `samples[].stdin`
when presenting an editable case. Design input has two parallel arrays, for example:

```json
{"test_cases":[{"stdin":"[[\"MinStack\",\"push\",\"getMin\"],[[],[5],[]]]"}]}
```

The design constructor must be first; operation names, parameter types, and arities
are validated. The fragment above is added to the normal language/source body.

Example queued response:

```json
{
  "data":{
    "id":"00000000-0000-0000-0000-000000000001",
    "question_id":"00000000-0000-0000-0000-000000000002",
    "language":"python",
    "language_version":"Python (provider-selected version)",
    "mode":"run",
    "evaluation_scope":"custom",
    "status":"queued",
    "total_tests":2,
    "passed_tests":0,
    "execution_time":null,
    "memory_used_kb":null,
    "created_at":"2026-11-09T12:00:00Z",
    "completed_at":null
  }
}
```

Poll authenticated `GET /submissions/{id}`. Only `queued` and `running` are nonterminal.
Poll with bounded backoff; stop on terminal status or unmount. Do not retry execution
POSTs automatically. A client polling timeout does not cancel or fail a persisted run.
Submission details retain the existing source/results fields and add `evaluation_scope`:

| Scope | Meaning of accepted | Progress/statistics credit |
| --- | --- | --- |
| `samples` | All selected visible samples passed the server comparator | None |
| `custom` | User code executed successfully; there is no correctness oracle | None |
| `playground` | Full stdin/stdout program executed successfully | None |
| `graded` | The complete visible/hidden problem suite passed | Normal solve-once credit |

For a custom case, `expected_output` is always null, including if the input happens
to match a hidden test. No reference solver or hidden expected answer is returned.
`passed_tests` for output-only custom/Playground runs counts successful executions.
Label these results “Executed successfully”, not “Correct solution”.

Each result contains `position`, `hidden`, `status`, `execution_time` (seconds),
`memory_kb`, `stdin`, `expected_output`, `stdout`, `stderr`, and `compile_output`.
Visible/custom inputs and available outputs are returned. All hidden inputs, expected
answers, stdout, stderr, and compilation diagnostics remain null. Diagnostics are
bounded; use server verdicts rather than comparing displayed strings in the browser.

`POST /submissions` is unchanged, with the additional response scope `graded`.
`POST /runs` remains the full-program Playground endpoint with optional stdin and scope
`playground`. Question solution code does not need a main program for question runs.
History `GET /submissions?question_id=...` includes question sample/custom runs; use
`evaluation_scope` to label entries. Existing progress `last_submission_id` continues
to refer to graded attempts, not sample/custom runs.

Error cases: 401 unauthenticated; 404 missing/unpublished question or foreign run;
409 unsupported/invalid/unconfigured suite or `samples_unavailable`; 422 invalid input
or unavailable/mismatched runtime; 429 pending/daily limits; 503 discovery or infrastructure
failure before admission. Provider failure after admission is reported in the pollable
run. SQL/shell remain browse-only. Passing samples never guarantees hidden-test success.

## Topics and catalog filtering

Public `GET /topics` returns actual distinct-question counts over published questions:

```json
{"data":[{"slug":"hash-table","name":"Hash Table","question_count":1}]}
```

Topics are sorted by slug; display names are title-cased slug words. Duplicate tags
on one question count once. Unpublished questions do not contribute.

Public `GET /questions` adds optional `topic=<slug>` to existing `difficulty`, `search`,
`page`, and `page_size` parameters. Filters combine with AND and counts are computed
before pagination. Topic is one exact, case-sensitive slug, up to 80 characters;
unknown valid slugs return an empty page. Difficulty is `easy|medium|hard`, search is
at most 100 characters. Existing title search behavior is retained. Pages start at 1,
page_size defaults to 20 and has maximum 100. Catalog order remains source problem
number ascending (missing numbers last), then created_at, then UUID.

Example: `GET /questions?topic=array&difficulty=easy&search=Sum&page=1&page_size=20`.

## Collections and featured questions

Public/optionally authenticated `GET /collections?page=1&page_size=20` returns a page
of collection records. Initial database-backed selection rules are:

| Slug | Name | Membership rule |
| --- | --- | --- |
| `foreplay` | Foreplay | Published easy questions |
| `main-event` | The main event | Published medium questions |
| `hardcore` | Hardcore | Published hard questions |

Collection fields: `id` (UUID), `slug`, `name`, `description`, `position`, `difficulty`,
`selection_rule` (`difficulty`), `question_count`, `solved_count`, and
`completion_percentage`. Ordering is stored position followed by UUID. Guest completion
fields are null, not fabricated zeroes. For authenticated callers they are actual solved
counts and a percentage from 0–100 (0 for an empty collection). Only published members
contribute, including to completion counts.

`GET /collections/{collection_id}?page=1&page_size=20&topic=array&search=Sum` returns:

```json
{
  "data":{
    "collection":{
      "id":"00000000-0000-0000-0000-000000000003",
      "slug":"foreplay","name":"Foreplay",
      "description":"Published easy problems in catalog order.",
      "position":0,"difficulty":"easy","selection_rule":"difficulty",
      "question_count":0,"solved_count":null,"completion_percentage":null
    },
    "questions":{"data":[],"total":0,"page":1,"page_size":20}
  }
}
```

Use returned UUIDs for collection detail URLs. Topic/search affect the question page;
collection totals/completion still describe the full collection. The collection's
difficulty is fixed by its rule. Missing collection returns 404.

Public `GET /questions/featured?limit=6` (limit 1–20) returns
`{"data":{"selection_rule":"first_in_catalog","questions":[]}}` with real
QuestionSummary records when available. The explicit initial rule selects the first N
published questions in canonical catalog order. It does not claim popularity or activity.

## Random selection and previous/next navigation

Public `GET /questions/random?topic=array&difficulty=easy&search=Sum` returns one
QuestionSummary in the standard data envelope. It samples uniformly from matching
published rows; there is no automatic judgeable-only filter. Empty match: 404 with
`no_matching_questions`. Static random/featured routes precede UUID matching.

Public `GET /questions/{question_id}/navigation` accepts the same topic, difficulty,
and search filters and returns:

```json
{"data":{"question_id":"00000000-0000-0000-0000-000000000002","previous_id":null,"next_id":null,"position":1,"total":1}}
```

Position is one-based in the complete filtered catalog. First/last boundaries are null;
navigation does not wrap. Missing/unpublished question: 404. Published question outside
the selected filters: 404 `question_not_in_catalog`. Preserve filters in frontend URLs
when following either neighbor; pagination does not restrict the navigation universe.

## Account-synced drafts

Authenticated routes:

| Method | Path | Request |
| --- | --- | --- |
| GET | `/users/me/drafts/{workspace}/{language}` | None |
| PUT | `/users/me/drafts/{workspace}/{language}` | DraftWrite JSON |
| DELETE | `/users/me/drafts/{workspace}/{language}?revision=N` | No body |

Workspace is `playground` or a published question UUID. Language is python/java/cpp.
Drafts are isolated by account, workspace, and language. Another account sees its own
empty draft, never another user's source. Unknown workspace returns 422; missing or
unpublished question returns 404. Unsupported execution does not make saved text executable.

PUT example:

```json
{"revision":0,"source_code":"print('hello')","stdin":"hello\n"}
```

`stdin` is optional and supported only for Playground drafts (including an explicit
empty string); sending it for a question draft returns 422. Source may be empty and
has a 65,536-byte UTF-8 limit; stdin has a 16,384-byte limit. Both reject NUL and invalid
Unicode. Revision is a required integer from 0–2147483646, excluding booleans.

Response example:

```json
{"data":{"workspace":"playground","question_id":null,"language":"python","source_code":"print('hello')","stdin":"hello\n","revision":1,"updated_at":"2026-11-09T12:00:00Z","exists":true}}
```

An untouched workspace returns exists=false, revision=0, and null source/stdin/timestamp.
Every write/delete increments revision. Send the last-read revision. Simultaneous writes
have one winner; stale writes return 409 with the current revision:

```json
{"error":{"code":"draft_conflict","message":"Draft changed on another device; read it before saving","request_id":"request-id","current_revision":2}}
```

Refetch and offer an explicit merge/overwrite decision; never silently retry with the new
revision. DELETE returns 200 with exists=false and the incremented revision, clearing
source/stdin. It retains a small revision tombstone so an old device cannot resurrect
a reset draft. The next save uses that returned revision, not zero. Even resetting an
untouched draft creates a tombstone. No draft operation affects progress or statistics.

## Preferences and runtime metadata

Authenticated `GET /users/me/preferences` returns defaults merged through validation:

```json
{"data":{"font_size":14,"editor_mode":"standard","preferred_language":"python","preferred_runtime_id":null,"pane_split":50.0}}
```

`PATCH /users/me/preferences` accepts any subset of those fields. Font size is an
integer 10–32; editor_mode is standard/vim/emacs; preferred_language is python/java/cpp;
pane_split is the left pane percentage, 20–80. Only preferred_runtime_id accepts null.
Concurrent partial updates preserve unrelated fields. Changing language clears an old
runtime unless a new runtime ID is supplied. Non-null runtime IDs must be available for
that language in the actual registry; invalid/mismatched IDs return 422. Setting a
runtime may return 503 if discovery is unavailable. Ordinary editor preference changes
and reads do not require provider connectivity. Existing stale runtime preferences are
returned as saved; clients should reconcile them with current `/languages` metadata.

Public `GET /languages` retains `id`, `language`, and `name` and adds `display_name`,
`capabilities`, and `playground_starter_code`. Capabilities are `playground`,
`question_samples`, `question_custom_inputs`, and `graded_submissions` for the three
implemented languages. Runtime names/IDs come from Judge0; capabilities describe backend
features, not a promise that user code compiles on every historical compiler version.
Templates are complete stdin/stdout programs; Java declares Main. Continue using the
question's own starter_code for the problem editor. Empty/failed registry discovery
retains existing sanitized provider errors and retry behavior.

## Avatars

`avatar_url` is added to `/users/me`, `/users/{username}`, and leaderboard entries. It
is null without an avatar, otherwise an API-relative `/api/v1/avatars/{key}` path. Public
profiles and leaderboard entries still omit email and other private account fields.

Authenticated `PUT /users/me/avatar` takes the **raw image bytes**, not JSON, a URL,
base64, or multipart. Set Content-Type to image/png, image/jpeg, or image/webp. The
default upload limit is 262,144 bytes (including chunked uploads); it can be configured
with AVATAR_MAX_BYTES. Content is decoded/verified, must match its declared type, and
must be a single frame of at most 4,000,000 pixels. It is resized to fit 256x256 and
re-encoded to a fresh PNG with metadata removed. SVG, animation, malformed images,
and MIME mismatches are rejected (415 unsupported type; 422 invalid content; 413 size).

Success returns 200 with the standard private MeView. Replacing an image invalidates
its old URL. Authenticated `DELETE /users/me/avatar` takes no body and returns 200 with
MeView and avatar_url=null. It affects only the caller's image. Public
`GET /avatars/{key}` returns image/png bytes, not a JSON envelope. Unknown, removed,
superseded, inactive-user, and invalid-path keys return 404. Upload/storage failures
return sanitized infrastructure errors; a failed database commit preserves the old image.

Storage: AVATAR_STORAGE_DIR defaults to var/avatars. Native development creates the
directory on first upload. Docker Compose mounts the persistent named avatar_data volume
at /srv/lustcode/var/avatars; the image initializes ownership for UID 10001. Do not use
an ephemeral container directory or remove the volume during deployment. Multiple API
replicas require the same persistent shared filesystem/path. Back up files together with
database avatar metadata. Best-effort old-file cleanup can leave unreachable orphan files
after failures/crashes; no orphan file can be fetched through the public route unless it
is the current key of an active user. Runtime uploads are Git/Docker ignored.

## Authoritative statistics

### Streak, daily problem, and LustCoins

All paths below are relative to `/api/v1`. The reward store now supports coin-funded
physical orders to Indian addresses, with manual staff fulfillment.

| Endpoint | Authentication | Purpose |
| --- | --- | --- |
| `GET /users/me/streak` | Required | Current/longest activity streak and calendar |
| `GET /questions/daily` | Optional | Shared UTC Problem of the Day and completion state |
| `GET /coins/rules` | Public | Authoritative earning amounts and redemption capability |
| `GET /users/me/coins` | Required | Durable balance and today's check-in state |
| `GET /users/me/coins/transactions?page=1&page_size=20` | Required | Owned credit ledger |
| `POST /users/me/coins/check-in` | Required | Claim today's five coins once |
| `GET /coins/rewards` | Public | Four orderable physical products and size options |
| `POST /coins/redeem` | Required | Place an order and spend coins atomically |
| `GET /users/me/orders` | Required | Own order history; address-free summaries |
| `GET /users/me/orders/{id}` | Required | Own receipt, address and shipment status |
| `POST /users/me/orders/{id}/cancel` | Required | Cancel a placed order and refund coins |

The streak endpoint returns `current_streak`, `longest_streak`, `active_today`,
`last_activity_date`, `daily_activity`, `next_reset_at`, `timezone: "UTC"`, and
`basis: "graded_submission_activity"`. Existing statistics also add `longest_streak`.
As with the existing streak, any graded submission is activity; runs and coin check-ins
do not extend it. Yesterday's activity retains the current streak until today's UTC
deadline. Longest streak uses all historical graded activity, not just the 365-day calendar.

`GET /questions/daily` returns `date`, `starts_at`, `expires_at`, `timezone: "UTC"`,
`question` (the existing `QuestionSummary`), `reward_coins: 20`, `completed`, and
`reward_claimed`. Fetch the existing `/questions/{id}` endpoint to open the editor.
Guests receive `null` for completion/reward state; bearer-authenticated users receive
booleans. Each UTC date is persisted once and shared across users, processes and
restarts. Only published questions with valid executable suites are eligible. Catalog
changes do not rotate today's problem. An empty eligible catalog returns 404
`daily_problem_unavailable`; a subsequently disabled assigned problem returns 409.
Keep `/questions/featured` for its existing first-in-catalog recommendations; it is
not a daily challenge.

Coin rules are LustCode's own initial policy:

- One explicit daily check-in earns 5 coins.
- A full accepted submission for the day's selected problem earns 20 coins once,
  across all languages and retries, even if the user solved that question previously.
- Ordinary solves, sample runs, custom inputs and playground executions earn 0.
- No signup bonus, historical backfill or streak multiplier is enabled.

The wallet response includes `currency: "LustCoins"`, `balance`, `total_earned`,
`total_spent`, `total_refunded`, `check_in_claimed_today`, `next_reset_at`, `rules`, and
`redemption_enabled: true`. `total_spent` is gross redemption spend; refunds do not
inflate `total_earned`. Balance equals earned minus spent plus refunded. The ledger
contains positive rewards/refunds and negative redemption entries. Everything is stored
in PostgreSQL, so free Redis restarts do not erase balances. Never grant or decrement coins in the
frontend. Display the server values and refetch the wallet after a terminal submission
or a successful check-in.

Check-in accepts no body or `{}`. It returns HTTP 200 with `awarded`, `credited_amount`,
`transaction` and `wallet`. Repeated or simultaneous requests return the same owned
transaction and `credited_amount: 0`, without adding another credit. Extra fields such
as `amount`, `date` or `user_id` are rejected 422. The transaction page contains
`id`, signed `amount`, `reason` (`daily_check_in`, `daily_problem`, `redemption`, or
`redemption_refund`), `reward_date`, `question_id`, `submission_id`, `order_id`, and
`created_at`. It never exposes another user's history.

POTD eligibility is captured on server-side graded admission, using the submission's
UTC creation date. A submission queued before midnight can finish after midnight and
still earn its original day's reward. Successful grading and coin credit commit in one
transaction. No frontend claim endpoint is needed for POTD. Refresh its completion
state and the wallet after Submit; polling a sample Run must not award coins.

### Physical product ordering

| Product ID | Product | Coins | Size |
| --- | --- | --- | --- |
| `premium-condom-pack` | Premium Condom Pack (12 pcs) | 500 | None |
| `water-based-lubricant` | Water-Based Lubricant (100ml) | 1,000 | None |
| `body-massage-oil` | Body Massage Oil (100ml) | 2,000 | None |
| `soft-adjustable-blindfold` | Soft Adjustable Blindfold | 4,000 | None |

Read prices and availability from `GET /coins/rewards`. The catalog has
`redemption_enabled: true`, `fulfillment_mode: "manual"`, `shipping_countries: ["IN"]`,
and `shipping_cost_coins: 0`. Products have `coin_cost`, `available_sizes`,
`stock_quantity`, `status` (`available`, `out_of_stock`, `unavailable`),
`is_placeholder: false`, and `redeemable`. A null stock quantity means manual/on-demand
fulfillment, not a claimed physical inventory count. Staff can pause a product or set
an actual stock quantity. One redemption orders one item; no cash checkout is involved.

Show an address form and confirm the server's price before ordering. Send a stable UUID
`Idempotency-Key` header for each checkout intent. Retain that same key when retrying
after a timeout or double click; generate a new key only for a new order.

```http
POST /api/v1/coins/redeem
Authorization: Bearer <access_token>
Content-Type: application/json
Idempotency-Key: <crypto.randomUUID() retained for this checkout>
```

```json
{
  "reward_id": "premium-condom-pack",
  "shipping_address": {
    "full_name": "Test Recipient",
    "phone": "9000000000",
    "address_line1": "123 Test Street",
    "address_line2": null,
    "city": "Bengaluru",
    "state": "Karnataka",
    "postal_code": "560001",
    "country_code": "IN"
  }
}
```

Only Indian addresses are accepted. PIN codes have six digits; Indian mobile numbers
normalize to `+91` format. This validates format, not the existence of an address;
fulfillment staff must confirm dispatch details. All four products have no size options;
omit `size` or send null. Non-null sizes are rejected. Do not send price, quantity, balance, status or
owner fields: the server controls them. Extra fields are rejected 422.

The first order returns 201 with `data: {order, wallet, replayed:false, coins_spent,
coins_refunded:0}`. An identical retry returns 200 with the same order, `replayed:true`
and `coins_spent:0`. Reusing a key with a different address/product/size returns 409
`idempotency_conflict`. Insufficient balance returns 409 `insufficient_coins`; unavailable
and out-of-stock products return 409; unknown products return 404. Missing or malformed
idempotency keys return 422. The order, stock reservation and ledger debit commit together.

Orders start as `placed`, awaiting **manual dispatch**. Customer history uses the same
page/page_size envelope as submissions and omits addresses. An owned order detail returns
its immutable product/price/size/address snapshot, status, timestamps, courier and tracking
number. Refresh the wallet and order history after checkout. Addresses must not be stored
in analytics, request logs or public profile components.

Customers can cancel only a `placed` order. Cancellation returns an order receipt and
refunds its original coin cost atomically; repeats never refund twice. Retrying the old
checkout key after cancellation returns that cancelled order, without charging again.
Once processing starts, customer cancellation returns 409 `order_not_cancellable`.
Refunds appear as positive `redemption_refund` transactions linked to the original order.

### Manual fulfillment

Private `GET /users/me` adds `is_staff`. Staff authority is checked against the database
on every request; no client request or token role claim can grant it.

| Endpoint | Staff operation |
| --- | --- |
| `GET /admin/orders?status=placed` | Paginated queue; optional status filter |
| `GET /admin/orders/{id}` | Read shipping details |
| `PATCH /admin/orders/{id}` | Update status and shipment tracking |
| `PATCH /admin/rewards/{id}` | Set `active` and/or `stock_quantity` |

Allowed status transitions are `placed → processing → shipped → delivered`, or staff
cancellation from `placed`/`processing` with a one-time coin refund. Marking shipped
requires `courier` and `tracking_number`. Terminal orders cannot move backwards or be
refunded through cancellation. There is no courier booking or automatic shipping/email
integration. Staff must physically fulfill the products and supply real tracking details.

An operator with private backend database access can grant/revoke a named existing
account using `python -m app.fulfillment_admin --username admin` (add `--revoke` to revoke).
No account receives staff privileges by signup or by default. Customer credentials cannot
read another customer's order or address; fulfillment routes return 403 to non-staff.

Apply migration `8ae36dc2f109` before serving this version. Only the four products above
are listed. The previous merchandise is retired and cannot be ordered; historical orders
keep their original product and price snapshots. Existing balances and ledger entries are
preserved. Downgrading the catalog migration is refused if new-product orders exist;
otherwise it removes the new products and leaves retired merchandise disabled for an
operator to review before re-enabling.
Update every API and worker sharing the database together.

Authenticated `/users/me/statistics` retains all previous fields and adds:

```json
{"current_streak":0,"acceptance_rate":0.0,"evaluated_submissions":0,"timezone":"UTC"}
```

These fields are part of the existing data object. Acceptance is a percentage from
0–100 rounded to two decimals: accepted graded submissions divided by completed judged
attempts (accepted, wrong answer, compilation error, runtime error, time limit, memory
limit). Pending/running and provider errors are excluded from that denominator. With
no evaluated submissions the rate is 0. Existing submissions/by_verdict counts retain
all graded statuses. Custom, sample, and Playground runs contribute to none of these.

Activity uses the graded attempt's created_at UTC calendar date, including unsuccessful
and pending graded attempts. Current streak counts consecutive active UTC dates ending
today, or yesterday if today has no activity; otherwise zero. It can exceed 365 days.
daily_activity contains the last 365 UTC calendar dates with activity (missing dates
mean zero). All-time history determines the streak. This is an attempt/activity streak,
not an accepted-solution streak. Keep solve-once progress and leaderboard behavior.

## Limits and polling failures

New JSON routes share existing body limits and Redis rate limiting (default 120
requests/minute per client IP; authenticated routes also use the user limit). Avatar
PUT alone uses its configured image byte limit. Poll requests count toward rate limits;
use backoff and avoid polling inactive panels continuously. Execution admission shares
the pending cap (5 by default), daily run/submission allowance (100), and daily test
execution allowance (1000). Samples consume only visible-case executions; custom runs
consume only supplied cases. Drafts/preferences/avatar operations do not consume
execution quota. Respect Retry-After on 429/503. Provider outages do not fail liveness;
database/Redis readiness remains required. No new client-side credential is needed.

## Frontend proxy changes required (frontend left unchanged)

The reference proxy is src/lib/server/proxy.ts; its current catch-all route supports
only GET/POST/PATCH and the proxy assumes every mutation/response is JSON. Integration
needs all of the following, not merely a path regex addition:

1. Allow GET topics, collections, collections/{UUID}, questions/featured,
   questions/random, and questions/{UUID}/navigation. Keep static question routes ahead
   of UUID matching. Forward page/page_size, difficulty/search, and new topic/limit.
2. Allow POST questions/{UUID}/runs, classify it as **protected**, and forward POST/body
   with the authenticated session. The current public branch otherwise changes it to GET.
   Forward test_cases unchanged. Do not auto-retry execution POSTs after network errors.
3. Allow GET/PUT/DELETE users/me/drafts/{playground-or-UUID}/{python|java|cpp} and forward
   the revision query on DELETE. Export PUT/DELETE in the frontend catch-all route handler
   as well as its proxy allowlist. Treat DELETE's empty body as valid.
4. Allow authenticated GET/PATCH users/me/preferences.
5. Allow authenticated PUT/DELETE users/me/avatar. Permit bounded raw PNG/JPEG/WebP bytes,
   preserve Content-Type, use the avatar byte limit, and skip JSON parsing for binary uploads
   and bodyless DELETEs. Retain origin/CSRF checks, including for PUT/DELETE.
6. Allow public GET avatars/{32-lowercase-hex}.png and relay bounded binary image/png
   responses with the correct Content-Type; do not call response.json() on image bytes.
   Map the backend's API-relative avatar_url into the same-origin frontend proxy path
   (backend /api/v1/avatars/... becomes frontend /api/avatars/...), or configure a deliberate
   public media origin. Do not concatenate untrusted arbitrary upstream URLs.
7. Collections are public with optional private completion: when a valid frontend session
   exists, forward authenticated GETs and apply the normal serialized refresh flow; without
   a session, request anonymously. Do not force all public requests into authenticated mode.
8. Keep strict allowed methods/paths/query keys and the configured upstream origin.
   Preserve sanitized errors, Retry-After, request IDs, and the existing session/refresh
   protections. Parse error.current_revision for draft conflict UI. Update TypeScript
   models for new preference, draft, collection, avatar, statistics, runtime, fixture-signature,
   and evaluation_scope fields. Never forward signing secrets or database credentials.

## Migration and operational notes

Apply Alembic revision e42b19c06d31 after d7e901a48b22. It creates question_collections
and workspace_drafts, seeds only the three explicit selection rules, and adds users'
preferences/avatar metadata plus the custom-input marker on submissions. New tables
have RLS enabled; backend authorization still scopes every private operation. Defaults
preserve inserts from the preceding backend version during an additive upgrade. Existing
users receive default preferences and no avatar; historical runs retain their old meaning.
Downgrading this revision removes the new drafts, collection rules, preferences, and
avatar associations; it does not delete stored image files. Back up before a real rollback.

Existing questions, source bodies, cases, immutable evaluation snapshots, refresh-token
rotation, runtime IDs, and graded worker behavior are reused. Private LeetCode cases
are neither fetched nor exposed. Production load, backups/restoration, public Judge0
capacity, and multi-replica storage provisioning remain operational work.
