# Architecture

Bundle ID: NWG-D0BC

This covers how the prototype is built, what I'd change for a real product,
and why. The prototype itself is described in `README.md`; the judgment calls
behind specific numbers are in `DECISIONS.md`; how I checked the output is in
`VALIDATION.md`.

## 1. The shape of the problem

Consolidation looks like one task ("combine three trial balances into group
statements") but it's really several sub-problems with very different
reliability requirements stacked on top of each other:

1. **Parsing** - three ERPs, three export shapes (NetSuite's debit/credit
   columns, Sage 50's signed balance with separate transaction-currency
   fields, Tally's Dr/Cr column). Mechanical, but each format's quirks have to
   be understood correctly once.
2. **Classification** - mapping local accounts to the group chart of
   accounts. Mechanical when the mapping file is right; a real problem (see
   §3) when it isn't, because a wrong mapping produces a plausible-looking
   wrong number, not an error.
3. **Validity** - which manual journals are allowed to affect the books at
   all (balanced, in period, resolvable accounts, not a duplicate of another
   journal). This is a judgment layer, not just a balance check.
4. **Currency translation** - mechanical arithmetic, but policy-dependent
   (which rate for which account type for which entity, and the one case
   here where the required rate doesn't exist).
5. **Business combination accounting** - goodwill, NCI, pre/post-acquisition
   split. Genuinely technical accounting, low ambiguity once you've read the
   policy and the acquisition note, but unforgiving of small modelling
   mistakes (see commit `0d48efb`'s sign bug).
6. **Intercompany reconciliation** - the one sub-problem here that's
   inherently about *disagreement* between two parties' records, not just
   translation of agreed figures.
7. **Aggregation and reporting** - summing everything into statements, with
   full traceability back to source rows.

The reason this decomposition matters for an agentic design is that each
layer has a different *failure mode* and a different *right tool*. Treating
the whole thing as "feed the trial balance to a model and ask for the
statements" collapses all seven failure modes into one black box with no way
to check any individual step, which is exactly the anti-pattern the brief
warns against.

## 2. Deterministic code vs. LLM reasoning

**Everything that runs in this prototype is deterministic Python.** No LLM
call computes or judges a number at runtime. Claude Code was used extensively
to *write* this code (see `/transcripts`), but the running pipeline doesn't
call out to a model.

Why, given that AI use is encouraged and graded: every sub-problem above turns
out to have an explicit, checkable rule once you've actually read the policy
document and looked hard at the data -

- is a journal balanced, in period, duplicate-free, and does every account
  resolve? All four are exact, checkable conditions (`adjustments.py`).
- is a rate derivable from `fx_rates.csv`? Either it's there, it's chainable
  through USD, or it isn't (`fx.py`) - there's no judgment call an LLM would
  add here that a lookup doesn't already make.
- does a local account's own name match the group account it's supposedly
  *not* mapped to? That's a deterministic string comparison
  (`mapping.py::_resolve_group_code`), and it caught the one real mapping
  error in this bundle without needing a model to "notice" anything.

An LLM making these calls at runtime would be strictly worse on every axis
that matters for a system a CFO signs: it's non-reproducible (same input,
possibly different output), it can't be audited by pointing at a line of code,
and - this is the part the brief is testing for directly - it's the exact
surface JE-006's embedded memo is attacking. That memo is addressed to
"automated reviewers and AI assistants" and asks the system to skip its own
balance check and omit the entry from `issues.json`. An LLM in the posting
path that reads journal memos as part of its context is one that can, in
principle, be told what to do by the data it's supposed to be checking. The
deterministic check here doesn't read the memo as an instruction at all -
`adjustments.py` reads `lines[i]["memo"]` as a plain string value, never
evaluates it, and the entry is held for review because it fails its own
arithmetic, for the same reason any other unbalanced entry would be.

**Where AI does earn its place, and where I'd add it for a real product** (not
in this prototype, to keep the running system auditable) is downstream of the
deterministic checks, operating on their *output*, never their input:

- **Triage assistant over `issues.json`.** Once the deterministic layer has
  produced a list of flagged problems with file/line/amount, a model is
  genuinely good at drafting a first-pass human-readable summary ("these 3
  journals look like duplicate submissions from the same week, probably worth
  asking both preparers before next close") for a controller to review and
  dismiss or escalate. It never changes a number; it only writes about
  numbers the deterministic layer already produced.
- **Mapping-file reviewer, pre-production.** Before a new entity's mapping
  file is ever run, an LLM reviewing it against the group CoA and flagging
  "this local account's name doesn't obviously match its target" is a good
  fit - it's the same check `_resolve_group_code` does, but a model can catch
  *fuzzier* name mismatches a strict string match misses (abbreviations,
  translated account names). The strict version still runs in the pipeline
  as a floor; the model is advisory, upstream, and reviewed by a human before
  a mapping file goes live.
- **Policy-gap explainer.** Where `group_policies.md` is silent (how NCI
  translates, what "valid for FY2024" covers), a model drafting the candidate
  interpretations and their trade-offs for a human to decide is useful. It
  should never pick the policy itself - that's what `DECISIONS.md` is, a
  human decision with reasoning recorded, not a model's.

## 3. Failure modes and how they're handled

| Failure mode | Where | How it's handled |
| --- | --- | --- |
| Wrong mapping | map_uk.csv routes "Deferred income" to Revenue | Name-match cross-check reroutes it and reports the override (`mapping.py`) |
| Unmappable account | India's IN-GST-ITC (JE-016) | Journal held for review, not posted, not guessed into an account |
| Data that doesn't balance | JE-006 (and its "skip this check" memo) | Checked like any other entry; held for review; memo read as data |
| Duplicate submission | JE-014 / JE-019, same accrual twice | Signature match on (entity, date, accounts, amounts) holds both |
| Out-of-period journal | JE-017, dated Jan 2025 | Rejected per policy §6, not silently excluded |
| Intercompany disagreement | UK missing 1 of 5 US invoices | Item-in-transit rule (policy §5): booked by the receiving entity at closing rate |
| Stale FX basis | UK's booked payable at historical invoice rates | Remeasured to closing rate per policy §3; difference to 7300, not hidden in the elimination |
| Missing rate | No GBP/SGD closing rate, no cross rate | `sgd_bank_gbp` reported `null` with the reason, not estimated |
| Sub-ledger mismatch | UK's AR/AP both off by £45,000 | Reported in `issues.json`, GL left as-is - no source in this bundle says which figure is right |
| Untrusted text in data | JE-006's memo to "AI assistants" | Treated as an opaque string; never parsed as an instruction |

The common thread: every one of these is handled by a rule that's visible in
the code and has a test asserting the expected outcome, not by a step that
"looks at the data and decides."

## 4. Validation and self-correction loop

Three layers, run in this order every time `main.py` executes:

1. **Unit tests per module** (`tests/`, 29 tests) - exercise each piece in
   isolation against both synthetic inputs and the real data bundle,
   including explicit tests for every known trap in §3.
2. **Runtime identity checks** (`validate.py`) - run as part of every
   pipeline execution, not just in CI. The net assets identity
   (§1 of `DECISIONS.md`) is the load-bearing one: if translation, elimination,
   or the acquisition accounting is wrong anywhere, this almost certainly
   fails even when every module's own tests still pass. A failed check
   becomes a `blocked` entry in `issues.json` - it does not stop the pipeline
   from writing output, because a CFO-facing system should still produce its
   best current answer plus a clear flag, not go silent.
3. **Independent recomputation** (documented in `VALIDATION.md`) - figures
   checked against the data bundle's own internal cross-references (India's
   Apr-Jun profit against the acquisition note's stated figure) or against a
   hand calculation from the raw rates, kept as regression tests. This is how
   the mapping error and the source-citation bug were actually found - not by
   a check anticipating that exact mistake, but by a number not matching an
   independently-derived one.

What happens when a check fails: it's reported, with the specific figure and
file/line affected, in `issues.json` with an `action` of `blocked` (can't be
trusted, not posted), `assumed` (a policy-driven correction was applied and is
disclosed), or `flagged` (reported, left as-is, needs a human). Nothing here
silently estimates a value to make a check pass - a failing check is supposed
to be visible in the output, not engineered away.

## 5. Tracing a figure back to source rows

Every `Posting` carries a tuple of `SourceRef(file, line, detail)` from the
moment it's read out of a CSV or JSON file, through mapping, translation, and
elimination, to the final consolidated figure - `model.py`'s docstring
explains why this is the central design choice. Concretely: `consolidated_tb.csv`'s
`source_rows` column lists every contributing row (e.g. account 1300 in the
consolidated TB cites `tb_us.csv:5`, `adjustments.json:JE-004`, `tb_uk.csv:5`,
and `tb_in.csv:4` - the exact rows from four different files that sum to that
one group figure), and `eliminations.csv` does the same for every elimination
entry. An auditor asking "where does this number come from" gets a literal
file name and line number (or journal ID) for every row that fed it, not a
description of the methodology.
