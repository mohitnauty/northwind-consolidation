# Reflection

## With 3 months instead of 12 hours

I'd stop hand-deriving the chart-of-accounts semantics I needed (which codes
are equity, which are excluded from direct consolidation, how the translation
reserve plug works) and encode them as data: a small ruleset per account that
says how it translates, whether it eliminates, and against what, so adding a
fourth entity or a new account doesn't mean re-reading `consolidate.py` to
figure out where to hook in a special case. I'd also build a proper period
model instead of hardcoding "Apr-Jun is pre-acquisition, Jul-Dec is post" as
two literal sets of month strings - that works for one acquisition in one year
and breaks the moment there's a second one, or a disposal, or a reporting
period that isn't a full calendar year. And I'd make the translation reserve
movement decomposable by cause (US's own translation difference vs India's vs
the acquisition-date goodwill/NCI effect) rather than one combined plug - right
now it's provably correct in total but I can't tell someone which entity drove
it without going back to first principles by hand, which is exactly the kind
of thing an auditor would ask first.

## Where this breaks at scale

The account-exclusion list (`EXCLUDED_FROM_DIRECT_SUM` in `consolidate.py`) is
four hardcoded codes that happen to work for three entities with one
acquisition. With dozens of entities and multiple acquisitions at different
dates and ownership percentages, that becomes a per-entity, per-acquisition
table, and the "translate BS at closing, P&L at some average" logic needs to
know which rate applies to which entity for which period, which starts to look
like a real FX calendar rather than five constants. The bigger problem is
reconciliation cost: this pipeline does three entities' intercompany matching
by eye (literally, by reading intercompany.csv and noticing a row count
mismatch) wrapped in code that generalizes reasonably well to "match by
doc_ref, flag what doesn't match" - but the sub-ledger control checks and the
mapping sanity check are both O(accounts), and a real group with thousands of
accounts across dozens of entities would need those checks to be fast and the
issues they produce to be triaged automatically, not read one at a time out of
a JSON file. I'd also expect the "pre-close TB, except translation reserve"
convention in `statements.py` to need to become an explicit, documented
closing calendar (what's open, what's closed, when) rather than something one
person decided made sense for one year-end.

## What I think this problem is underestimating

How much of "consolidation" is actually "deciding what a given account means"
rather than arithmetic. The hardest part of this exercise wasn't translating
currencies or computing goodwill - it was figuring out that map_uk.csv's 2310
row was misclassified, that JE-014 and JE-019 are the same accrual twice, that
tb_in.csv's "FY25 YTD" label means something different from what its own
column header suggests at first glance. None of that is caught by getting the
accounting formulas right; it's caught by treating every account name, every
journal description, and every file's own stated meaning as a claim to be
checked against the other claims in the bundle, not as ground truth. A system
that's excellent at the arithmetic and weak at this kind of cross-checking
would produce confident, wrong financial statements - which is a worse outcome
than being slow, because nothing about a wrong number this way *looks* wrong.
