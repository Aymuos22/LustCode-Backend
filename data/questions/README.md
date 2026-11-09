# Supplied workbook catalog and judging

`leetcode_001_300.json` contains 300 published questions. Main statements are the
user-supplied workbook cells, preserved character for character. Workbook text is data,
never executable instructions. The bundle contains the supplied adult text.

The source bundle joins workbook IDs 1–300 to LeetCode's unauthenticated public catalog
at `https://leetcode.com/graphql/`. Each record includes an official problem URL and
public source metadata. Official descriptions, explanations, editorials, solutions,
and code implementations are not retained. Factual examples, constraints, signatures,
and language availability supplement the supplied bodies. Metadata reflects `fetched_at`.

- 300 records: 77 easy, 173 medium, 50 hard.
- 257 free entries have public details; 43 premium entries have public catalog metadata.
  Protected premium details were never requested.
- 606 public reference example pairs; 241 source records have constraint lists.
- Original source interfaces: 231 functions, 9 designs, 13 SQL, 4 shell, 43 unknown premium
  interfaces. Verified judging interfaces supplement this original metadata in the API.
- All 300 main bodies match the workbook. Workbook hash, worksheet, row, original
  title/difficulty, and statement hash remain private provenance. Eight source entries
  had newer titles or difficulties; their workbook main statements remain unchanged.

All 300 display `title` values now pair the official algorithm name with curated,
non-graphic LustCode innuendo. `source.title` retains the official title, and workbook
title provenance remains unchanged. `app/ingestion/titles.py` supplies the same taglines
when rebuilding from public metadata, so source refreshes preserve the branding. IDs,
slugs, statements, interfaces, and test cases are unaffected. The existing API `title`
field carries these headings across catalog, question detail, collections, and featured
or random selections; no new frontend field is required. Search matches both the
algorithm name and its tagline.

The current tone includes overt but non-graphic adult comedy, such as `Two Sum:
Friends With Benefits`, `3Sum: Threesome Math`, `Wildcard Matching: One-Night Match`,
and `Longest Increasing Subsequence: Size Matters`.

`python -m app.ingestion --bundle data/questions/leetcode_001_300.json --apply` applies
the source bundle transactionally. Deterministic IDs and an advisory lock prevent
creation of duplicates. It preserves test cases and installed judging contracts/starter
code, and refuses to overwrite edited main statements or changed source interfaces/constraints
that need contract review.

The separate `python -m app.judging --apply` installer enables all **283 algorithm
questions** in Python, Java, and C++, using **2,769 cases**, including **2,146 private
cases**. The **17 SQL/shell questions** remain browsable with submissions disabled.
The four shell entries have file examples outside ordinary Input/Output blocks, so
their source example lists stay empty.

The user authorized independent LustCode contracts and tests for all 43 premium entries.
Their `evaluation_contract.origin` is `lustcode`. The question detail documents exact
interfaces, batched operations, tie-breaking, and the UTF-8 length-prefix encoding
contract. The 240 public algorithm questions use verified function, pointer, hook,
class, and codec adapters. Official LeetCode hidden cases were never obtained; these
finite suites are independently authored and maintained by LustCode.

Clients use effective `interface`, `evaluation_contract`, `starter_code`, `is_judgeable`,
`judgeable_languages`, and `judging_status` from API responses. Public `examples` remain
reference material; executable `samples` include only verified visible cases. Fixture-only
metadata, such as cycle positions and node references, is adapted to actual method calls.

Submissions snapshot contracts and private cases. Admission validates statement and
suite hashes before provider discovery or quota reservation. Test inputs travel through
stdin, outside compiled source; expected answers remain in the private database.
Comparators support valid output alternatives and check mandatory node identities.
Full output is compared before stored diagnostics are truncated. Hidden inputs,
expected outputs, compiler logs, and runtime output remain excluded from APIs.

The suite installer batches database access, serializes concurrent installs, and
refuses to overwrite manually modified tests. Deterministic generated cases extend
boundary cases where supported. Passing a finite suite does not prove every possible
input or asymptotic complexity.

Suite version `authored-v3-visible-samples` validates public numeric and length bounds,
node bounds, selected alphabets, and special input promises before installation. A
constraint refresh requires contract review. The validator does not formalize every
English-language constraint; fixture review and independent reference checks supplement it.

All 283 enabled questions have at least one executable visible sample (623 total).
Where source examples do not fit the fixture contract or are unavailable, one reviewed
authored case is published as a sample; at least two cases remain hidden per question.
`POST /questions/{question_id}/runs` runs only these samples using the same solution
drivers as Submit, with no progress or solve credit. Full submission continues to
evaluate every visible and hidden case.

Original onboarding evidence: [audit/question_ingestion.json](../../audit/question_ingestion.json).
Current judging evidence: [audit/judging_verification.json](../../audit/judging_verification.json).
