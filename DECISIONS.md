# Decisions

Built with Claude Code doing the implementation from my direction - I set the
accounting approach and reviewed every module against the policy text and the
source data before accepting it, rather than asking for "a consolidation
script" and taking what came back. The "what Claude suggested" notes below are
literal: in a few places its first draft had a real bug that a test or an
independent hand calculation caught, which is exactly the kind of thing
VALIDATION.md is about. Full transcript is in `transcripts/`.

## 1. Pre-close trial balance, with translation reserve as the one exception

`consolidated_tb.csv` keeps P&L accounts open at their full-year balance and
share capital/retained earnings at their opening value, matching how every
input TB (`tb_us.csv`, `tb_uk.csv`, `tb_in.csv`) is itself presented - none of
them close P&L into retained earnings either. The one line that can't follow
that pattern is the translation reserve (3300): there's no "open" holding
account for currency translation differences the way there is for ordinary
trading profit, so it has to carry its full in-year movement even in an
otherwise pre-close TB. I checked this works by writing out the whole-TB
identity by hand before coding it: net assets at closing = group profit for
the year + share capital + opening retained earnings + closing translation
reserve + NCI at acquisition. `validate.check_net_assets_identity()` asserts
this on every run. The alternative - fully closing the TB so retained earnings
and NCI already include this year's profit - is arguably more standard for a
"trial balance" in the strictest sense, but it would make `consolidated_tb.csv`
redundant with `balance_sheet.json` instead of complementary to it, so I kept
them deliberately different: one is the working document, one is the filed
statement.

Claude's first draft of this tried to show retained earnings at its closing
value (opening + this year's profit) in the TB while also leaving P&L open -
I caught that it double-counts profit once I actually added up both sides by
hand and it didn't balance.

## 2. NCI is not retranslated at the closing rate; goodwill is

Policy §4 explicitly says goodwill is retranslated at the closing rate every
period. It says nothing about NCI. `prior_year_group.csv` does give a hint,
though: its note on account 3300 says the translation reserve is "attributable
to owners of the parent," which only makes sense if NCI doesn't participate in
translation movements at all. So NCI is built from two historical-rate pieces
that never get revisited: its value at acquisition (135,600,000 INR at the
1 July 2024 spot rate) plus its 20% share of India's post-acquisition profit
(at the H2 average rate, same as everything else that flows through P&L).
Goodwill, by contrast, genuinely is retranslated every period per policy §4.

## 3. Deterministic pipeline; no LLM in the numeric path

Every number in this repo is produced by plain Python - mapping, FX,
elimination, goodwill, all of it. Claude Code wrote and reviewed the code, but
nothing in the running pipeline calls out to a model to compute or judge a
figure. The trade-off is that anything genuinely ambiguous (the deferred
income mapping, the duplicate journals) has to be caught by an explicit,
auditable rule rather than a model's judgment call at runtime - which is
slower to build but means every output is reproducible and I can point at the
exact line of code that produced any number. `ARCHITECTURE.md` goes into where
I'd actually want an LLM in a full product (triaging `issues.json` for a human,
not computing figures).

## 4. Mapping errors are caught by a name-match rule, not trusted as given

map_uk.csv sends local code 2310 ("Deferred income") to group account 4100
(Revenue). I found this by accident, really - my hand-calculated group revenue
was exactly 180,000 off from the pipeline's, and the only UK account anywhere
near that size was 2310. Its own name is an exact match for group account
2300, which is *also* "Deferred income" (a liability) - too specific to be
coincidence. The brief says process the data as given, which I read as "don't
hand-edit the CSVs," not "apply every mapping uncritically even when it's
self-evidently wrong." So `mapping.py` checks every UK/India row: if a local
account's own name is an exact match for a *different* group account than the
one it's mapped to, it gets rerouted, and the override is reported in
`issues.json` rather than applied silently. This is a general rule, not a
hardcoded fix for 2310 specifically - it just happens that 2310 is the only
row in either mapping file that triggers it.

## 5. Null over a guess for the SGD rate; structured values for two figures

fx_rates.csv has opening and average rates for GBP/SGD but no closing rate and
no USD/SGD rate to chain through. UK's SGD bank balance needs a closing rate
per policy §3. There isn't one, so `sgd_bank_gbp` in the control figures is
`null` with a reason, not UK's own (non-policy-compliant) carrying value and
not an average-rate stand-in. Separately, the appendix says every control
figure should be "a number, or null with a reason," but two of the figures'
own descriptions ask for a breakdown - `intercompany_difference` ("split into
its causes") and `journals` ("posted, rejected and held for review"). I read
the specific instruction in each figure's description as overriding the
general formatting rule for just those two, and used small objects instead of
bare numbers for them. Every null value is `{"value": null, "reason": "..."}`
rather than a bare `null` plus a separate top-level key, so the file still has
exactly the 12 keys the brief lists.

## 6. Duplicate journals are held for review, not deduplicated

JE-014 and JE-019 book the identical 48,000 external audit fee accrual for US,
same date, same accounts, different preparer. Posting both double-counts the
accrual; posting either one is a guess about which preparer's entry is the
"real" one (or whether the fee is really 48,000 or 96,000). I added a
signature check in `adjustments.py` (same entity, date, and set of account/
amount lines) that holds both for review rather than silently picking one -
Claude's first version of the journals engine checked balance and period but
didn't check for duplicates at all; I added this after noticing the two
descriptions were nearly identical while reading through the journal list.

## 7. Intercompany: fix the two real problems before eliminating, don't force a plug

UK only booked 4 of the 5 US management-fee invoices (the 5th, year-end, is an
item in transit - policy §5 says the receiving entity books it at the closing
rate), and the 4 it did book are carried at each invoice's own historical rate
rather than retranslated to closing (policy §3, since this is a monetary item
in a non-functional currency). I could have skipped both corrections and just
plugged the whole gap to 7300 as "the intercompany difference," but that would
hide two different, explainable causes behind one number. Doing both
corrections first means the balance-sheet elimination (1250 vs 2150) nets to
exactly zero, and the only residual left for 7300 is the one policy §5 actually
describes - the gap between US income translated at the FY average rate and
UK's expense at its own booked GBP value.
