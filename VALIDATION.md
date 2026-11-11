# Validation

## Checks that run every time the pipeline runs

These aren't test-suite-only checks - `validate.py` runs them as part of
`main.py` and adds a `blocked` entry to `issues.json` if any of them fail, so a
real problem in the pipeline can't silently produce a clean-looking output.

- **Net assets identity.** `check_net_assets_identity()` asserts that net
  assets at closing equals group profit for the year, plus share capital, plus
  opening retained earnings, plus the closing translation reserve, plus NCI at
  acquisition. This is really the whole consolidation compressed into one
  equation - see `DECISIONS.md` #1 for why it holds, and `consolidate.py`'s
  module docstring for the derivation. If any entity's translation, any
  elimination, or the acquisition accounting were wrong, this would almost
  certainly fail even if every individual module's own unit tests still passed
  in isolation.
- **Balance sheet identity.** `check_balance_sheet_identity()` checks total
  assets plus total liabilities equals total equity in the statement actually
  being written out, independently of how those totals were built up.
- **Elimination residual check.** After the item-in-transit and remeasurement
  corrections, the intercompany receivable/payable elimination should net to
  within a cent. `consolidate.py` reports an issue if it doesn't, rather than
  assuming the correction worked.
- **Sub-ledger control tie-out.** Every entity's AR/AP sub-ledger total is
  compared to the mapped GL balance; a mismatch is reported, not corrected.

## Figures recomputed independently, not just passed through

- **India's pre-acquisition profit.** `acquisition_note.md` states profit for
  1 April - 30 June 2024 was 18,000,000 INR, as part of its net-assets-at-
  completion table. `in_pl_monthly.csv` doesn't hand that figure to anyone
  pre-summed - `test_acquisition.py::test_pre_acquisition_profit_ties_to_acquisition_note_independently`
  sums the three months from the monthly file and checks it against the note.
  It matches to the rupee. That's a genuine cross-check between two documents
  that were presumably produced by different people in the data (an M&A note
  and a monthly management P&L), not a tautology.
- **Group revenue**, hand-calculated from the raw FY2024 average, H2 average
  and closing rates in `fx_rates.csv` (US revenue at the FY average, UK as-is
  in GBP, India's post-acquisition revenue at the H2 average), matches the
  pipeline's own `profit_and_loss.json` output to the penny -
  `test_consolidate.py::test_group_revenue_matches_independent_hand_calculation`.
  This check is what originally caught the map_uk.csv mapping error (below) -
  my hand total was 180,000 off from the pipeline's first run, which is what
  sent me looking at account 2310.
- **Goodwill and NCI at acquisition** both derive from the same three figures
  in `acquisition_note.md` (share capital, reserves, H1 profit), which the
  note itself also sums to a stated total of 678,000,000 - so the note cross-
  checks its own inputs, and `test_acquisition.py::test_goodwill_and_nci_tie_to_acquisition_note`
  checks our derived goodwill (147,600,000) and NCI (135,600,000) sum back to
  that same 678,000,000 at 80/20.
- **Each entity's raw trial balance** was checked to net to zero before any
  of this project's code touched it (US: debits and credits both 43,534,373.43;
  UK's signed `balance` column sums to 0.00; India's Dr/Cr column sums to
  0.00) - this is what confirmed I'd read each entity's sign convention
  correctly before building anything on top of it.

## At least 3 things Claude got wrong, with the commit that fixed them

1. **Elimination plug had the sign backwards.** The first draft of
   `eliminate_management_fee()` posted the 7300 residual as `-elim_pl_residual`
   instead of `+elim_pl_residual`. The four "fully eliminate both accounts"
   postings and the plug need to cancel out; with the wrong sign they doubled
   up instead. `test_elimination_nets_full_postings_to_zero` failed
   immediately (the postings summed to a nonzero value instead of zero), and
   the fix is in commit `0d48efb`.
2. **Applied map_uk.csv's account mapping without any sanity check.** The
   pipeline (as of commit `9cd3726`'s successor work) would have taken local
   code 2310 ("Deferred income") at face value and routed it to group revenue,
   because that's literally what map_uk.csv says. Nothing caught this until I
   compared the pipeline's group revenue to a hand calculation and found a
   180,000 GBP gap. The fix - a general name-match check in `mapping.py`, not
   a hardcoded exception for 2310 - is in commit `c0e08cc`, along with the
   test (`test_mapping.py`, `test_consolidate.py::test_deferred_income_mapping_error_is_caught`)
   that would catch a regression.
3. **India's post-acquisition postings cited the wrong source rows.**
   `split_india_monthly_pl()` built one shared source dict for both the pre-
   and post-acquisition buckets, so a post-acquisition revenue posting ended
   up citing all 9 months of `in_pl_monthly.csv` (Apr-Dec) instead of just the
   6 that actually fed it (Jul-Dec). The number was right; the traceability
   wasn't - and traceability back to source rows is the thing this whole
   assignment is graded on. Caught by actually reading `consolidated_tb.csv`'s
   `source_rows` column after the first full pipeline run and noticing April
   showing up in a line that should only reflect the second half of the year.
   Fixed in commit `c0e08cc` by tracking pre- and post-acquisition sources in
   separate dicts; `test_acquisition.py::test_sources_are_scoped_to_their_own_period`
   checks this directly.
4. **Balance tolerance was too tight for the pre-close TB convention.**
   `validate.py`'s identity checks initially used a 0.01 tolerance. Summing a
   dozen independently-rounded line items and comparing to one figure rounded
   once at the end routinely lands a cent or two off under policy §7 ("round
   only the final figures, not intermediate steps"), which isn't a bug - it's
   rounding. Running the full pipeline produced a spurious `blocked` issue
   over a 0.02 difference; tolerance raised to 0.05 in commit `c0e08cc`.

## What I did not try to independently verify

I did not re-derive the FX rates themselves (taken as given), and I did not
attempt to reconstruct how UK's `tb_uk.csv` balance for its USD intercompany
payable (490,707.72 GBP) was originally arrived at invoice-by-invoice -
I only checked that it's internally consistent with the four invoice amounts
and FX rates in `intercompany.csv`, not that those per-invoice rates are
themselves correct. There's no independent source in this bundle to check them
against.
