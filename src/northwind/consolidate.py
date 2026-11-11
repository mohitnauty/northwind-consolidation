"""Runs the whole consolidation and returns everything the output files need.

The chart-of-accounts codes 1600, 1610, 3100 and 3200 are deliberately excluded
from every entity's postings before anything gets summed. 1600/1610 are the
parent's investments in its subsidiaries - not a group asset, they're eliminated
against the subsidiary's own net assets. 3100/3200 are every entity's own local
share capital and retained earnings - not group equity, because prior_year_group.csv
already gives the group's opening equity directly, built up over however many
years this group has been consolidating. Re-summing each entity's local equity on
top of that would double-count years of UK's accumulated post-acquisition profit
that are already sitting inside the group's opening retained earnings.

That's also why there's no elimination entry in eliminations.csv for UK's own
investment/equity: it's not a FY2024 event, it's a standing structural exclusion
that was presumably already accounted for however group accounts were produced
in prior years, and nothing in this data bundle lets us reconstruct what that
elimination looked like eight years ago. India's acquisition, by contrast,
happened this year and is fully documented, so it gets a real elimination entry
with real source rows.

The trial balance this module builds is a pre-close one, same convention as
every input TB: P&L accounts stay open at their full consolidated-for-the-year
balance, and 3100/3200/3300 show their OPENING value unchanged. NCI (3400) is
the one new line this year - it's shown at its acquisition-date recognition
only (not including its share of this year's profit, for the same reason: that
profit is still sitting, undivided, in India's open P&L lines). statements.py
is what turns this into an actual post-close balance sheet.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from . import acquisition, io_loaders, intercompany, subledger_checks, translation
from .adjustments import process_adjustments
from .fx import FxTable, RateMiss
from .mapping import Issue, map_india, map_uk
from .model import Posting, SourceRef

EXCLUDED_FROM_DIRECT_SUM = {"1600", "1610", "3100", "3200"}

US_PL_RATE = "average"       # FY2024 average, per policy §2
INDIA_POSTACQ_PL_RATE = "h2_average"
INDIA_BS_RATE = "closing"
US_BS_RATE = "closing"
ACQUISITION_RATE = "spot"    # 1 Jul 2024, matches the acquisition completion date exactly


@dataclass
class EliminationRow:
    group_id: str
    description: str
    entity: str
    account: str
    amount_gbp: Decimal
    source: str


@dataclass
class ConsolidationResult:
    tb_postings: list  # final pre-close GBP postings, one per (entity, account) with provenance
    eliminations: list  # EliminationRow
    issues: list  # Issue
    group_profit: Decimal
    profit_owners: Decimal
    profit_nci: Decimal
    goodwill_closing_gbp: Decimal
    nci_at_acquisition_gbp: Decimal
    opening_equity: dict
    translation_reserve_movement: Decimal
    net_assets_closing: Decimal
    journal_counts: dict
    intercompany_causes: dict


def _posting_sources_label(rows: list) -> str:
    """Accepts a mix of Posting (has `.sources`, a tuple of SourceRef) and
    MappedRow (has `.ref`, a single SourceRef) - both show up here depending on
    which stage of the pipeline a value was pulled from for citation purposes."""
    refs = []
    for row in rows:
        if hasattr(row, "sources"):
            refs.extend(row.sources)
        elif hasattr(row, "ref"):
            refs.append(row.ref)
    return "; ".join(r.label() for r in refs)


def run(data_dir: Path) -> ConsolidationResult:
    issues: list[Issue] = []

    entities = io_loaders.load_entities(data_dir / "entities.csv")
    group_coa = io_loaders.load_group_coa(data_dir / "group_coa.csv")
    uk_map = io_loaders.load_account_map(data_dir / "map_uk.csv")
    in_map = io_loaders.load_account_map(data_dir / "map_in.csv")
    fx_rows = io_loaders.load_fx_rates(data_dir / "fx_rates.csv")
    fx = FxTable(fx_rows)
    prior_year = io_loaders.load_prior_year_group(data_dir / "prior_year_group.csv")
    subledger_rows = io_loaders.load_subledger_controls(data_dir / "subledger_controls.csv")
    ic_rows = io_loaders.load_intercompany(data_dir / "intercompany.csv")
    adjustments_raw = io_loaders.load_adjustments(data_dir / "adjustments.json")

    opening = {row["group_account"]: Decimal(row["amount_gbp"]) for row in prior_year}

    # ---- adjustments: validate once, shared across entities ----
    journal_results, journal_issues = process_adjustments(adjustments_raw, group_coa, uk_map, in_map)
    issues.extend(journal_issues)
    journal_counts = {
        "posted": sum(1 for r in journal_results if r.status == "posted"),
        "rejected": sum(1 for r in journal_results if r.status == "rejected"),
        "held_for_review": sum(1 for r in journal_results if r.status == "held_for_review"),
    }
    posted_by_entity = {"US": [], "UK": [], "IN": []}
    for r in journal_results:
        if r.status == "posted":
            posted_by_entity[r.entity].extend(r.postings)

    # ---- US: already group-coded, BS @ closing, P&L @ FY average ----
    us_raw = io_loaders.load_tb_us(data_dir / "tb_us.csv")
    us_all = us_raw + posted_by_entity["US"]
    us_investment_postings = [p for p in us_all if p.account in ("1600", "1610")]
    us_direct = [p for p in us_all if p.account not in EXCLUDED_FROM_DIRECT_SUM]
    us_bs = [p for p in us_direct if group_coa[p.account]["statement"] == "BS"]
    us_pl = [p for p in us_direct if group_coa[p.account]["statement"] == "PL"]
    us_bs_gbp, iss = translation.translate_postings(us_bs, fx, US_BS_RATE)
    issues += iss
    us_pl_gbp, iss = translation.translate_postings(us_pl, fx, US_PL_RATE)
    issues += iss

    # ---- UK: already GBP, no entity-level translation, but needs its own corrections ----
    uk_raw_rows = io_loaders.load_tb_uk_raw(data_dir / "tb_uk.csv")
    uk_mapped, map_issues = map_uk(uk_raw_rows, uk_map, group_coa)
    issues += map_issues
    uk_direct_postings = [
        Posting("UK", m.group_code, m.amount, "GBP", (m.ref,))
        for m in uk_mapped if m.group_code not in EXCLUDED_FROM_DIRECT_SUM
    ]
    uk_correction_postings, uk_elim_lines, uk_corr_issues = intercompany.uk_correction_postings(
        ic_rows, uk_raw_rows, fx, group_coa
    )
    issues += uk_corr_issues
    uk_all_postings = uk_direct_postings + posted_by_entity["UK"] + uk_correction_postings

    # ---- India: BS @ closing (ex equity), P&L post-acquisition only @ H2 average ----
    in_tb_rows = io_loaders.load_tb_in_raw(data_dir / "tb_in.csv")
    in_mapped, in_map_issues = map_india(in_tb_rows, in_map, group_coa)
    issues += in_map_issues
    in_equity_postings = [m for m in in_mapped if m.group_code in ("3100", "3200")]
    in_bs_direct = [
        Posting("IN", m.group_code, m.amount, "INR", (m.ref,))
        for m in in_mapped
        if group_coa[m.group_code]["statement"] == "BS" and m.group_code not in EXCLUDED_FROM_DIRECT_SUM
    ]
    in_bs_adjustments = [p for p in posted_by_entity["IN"] if group_coa[p.account]["statement"] == "BS"]
    in_bs_gbp, iss = translation.translate_postings(in_bs_direct + in_bs_adjustments, fx, INDIA_BS_RATE)
    issues += iss

    monthly = io_loaders.load_in_pl_monthly(data_dir / "in_pl_monthly.csv")
    pre_acq, post_acq, pre_sources, post_sources, unmapped_monthly = acquisition.split_india_monthly_pl(monthly, in_map)
    for code in unmapped_monthly:
        issues.append(
            Issue(file="in_pl_monthly.csv", line="n/a", amount=None,
                  description=f"India monthly P&L ledger code {code} has no group mapping", action="blocked")
        )
    in_pl_adjustments = [p for p in posted_by_entity["IN"] if group_coa[p.account]["statement"] == "PL"]
    for p in in_pl_adjustments:
        post_acq[p.account] = post_acq.get(p.account, Decimal("0")) + p.amount
        post_sources.setdefault(p.account, []).extend(p.sources)

    post_acq_postings = [
        Posting("IN", code, amount, "INR", tuple(post_sources.get(code, [])))
        for code, amount in post_acq.items()
    ]
    in_pl_gbp, iss = translation.translate_postings(post_acq_postings, fx, INDIA_POSTACQ_PL_RATE)
    issues += iss

    # ---- acquisition accounting ----
    acq = acquisition.goodwill_and_nci_at_acquisition()
    recomputed_pre_acq_profit = acquisition.pre_acquisition_profit(pre_acq)
    if recomputed_pre_acq_profit != acquisition.PROFIT_1APR_TO_30JUN_INR:
        issues.append(
            Issue(file="in_pl_monthly.csv", line="n/a", amount=recomputed_pre_acq_profit,
                  description=(
                      f"India's Apr-Jun profit recomputed from monthly data is {recomputed_pre_acq_profit}, "
                      f"which does not match acquisition_note.md's stated 18,000,000"
                  ),
                  action="flagged")
        )

    goodwill_closing = fx.to_gbp(acq.goodwill_inr, "INR", "closing")
    nci_at_acq_gbp = fx.to_gbp(acq.nci_at_acquisition_inr, "INR", ACQUISITION_RATE)
    for rate_result, label in ((goodwill_closing, "goodwill"), (nci_at_acq_gbp, "NCI at acquisition")):
        if isinstance(rate_result, RateMiss):
            issues.append(Issue(file="acquisition_note.md", line="n/a", amount=None,
                                 description=f"cannot translate {label}: {rate_result.reason}", action="blocked"))

    post_acq_profit_inr = -sum(post_acq.values(), Decimal("0"))
    profit_nci_inr = post_acq_profit_inr * Decimal("0.20")
    profit_nci_gbp = fx.to_gbp(profit_nci_inr, "INR", INDIA_POSTACQ_PL_RATE)

    goodwill_closing_gbp = None if isinstance(goodwill_closing, RateMiss) else goodwill_closing
    goodwill_posting = Posting(
        "IN", "1700", goodwill_closing_gbp or Decimal("0"),
        "GBP", (SourceRef("acquisition_note.md", "n/a", "goodwill on India acquisition"),),
    )

    # ---- intercompany elimination (post-translation GBP balances) ----
    def _sum(postings, entity, account):
        return sum((p.amount for p in postings if p.entity == entity and p.account == account), Decimal("0"))

    us_1250 = _sum(us_bs_gbp, "US", "1250")
    uk_2150 = _sum(uk_all_postings, "UK", "2150")
    us_4200 = _sum(us_pl_gbp, "US", "4200")
    uk_6300 = _sum(uk_all_postings, "UK", "6300")
    ic_elim_postings, elim_bs_check, elim_pl_residual = intercompany.eliminate_management_fee(
        us_1250, uk_2150, us_4200, uk_6300
    )
    if abs(elim_bs_check) > Decimal("0.000001"):  # Decimal division leaves tiny non-zero dust at 28 sig figs
        issues.append(
            Issue(file="intercompany.csv", line="n/a", amount=elim_bs_check,
                  description=(
                      f"intercompany receivable/payable did not eliminate to zero after corrections "
                      f"(residual {elim_bs_check} GBP) - check the closing-rate remeasurement"
                  ),
                  action="flagged")
        )

    # ---- subledger control checks (on local-currency, pre-translation balances) ----
    gl_by_entity_account = {}
    for p in us_direct:
        if p.account in ("1200", "2100"):
            gl_by_entity_account[("US", p.account)] = gl_by_entity_account.get(("US", p.account), Decimal("0")) + p.amount
    for m in uk_mapped:
        if m.group_code in ("1200", "2100"):
            key = ("UK", m.group_code)
            gl_by_entity_account[key] = gl_by_entity_account.get(key, Decimal("0")) + m.amount
    for m in in_mapped:
        if m.group_code in ("1200", "2100"):
            key = ("IN", m.group_code)
            gl_by_entity_account[key] = gl_by_entity_account.get(key, Decimal("0")) + m.amount
    issues += subledger_checks.check_subledger_controls(subledger_rows, gl_by_entity_account)

    # ---- assemble the pre-close consolidated TB ----
    all_postings = us_bs_gbp + us_pl_gbp + uk_all_postings + in_bs_gbp + in_pl_gbp + [goodwill_posting] + ic_elim_postings
    by_account: dict[str, list] = {}
    for p in all_postings:
        by_account.setdefault(p.account, []).append(p)

    net_assets_closing = sum(
        (sum(p.amount for p in ps) for code, ps in by_account.items()
         if group_coa.get(code, {}).get("account_type") in ("Asset", "Liability")),
        Decimal("0"),
    )

    # ---- group profit for the year, and the owners/NCI split ----
    us_profit = -sum((p.amount for p in us_pl_gbp), Decimal("0"))
    uk_pl_postings = [p for p in uk_all_postings if group_coa.get(p.account, {}).get("statement") == "PL"]
    uk_profit = -sum((p.amount for p in uk_pl_postings), Decimal("0"))
    in_postacq_profit_gbp = -sum((p.amount for p in in_pl_gbp), Decimal("0"))
    # the elimination residual on 7300 reduces (or increases) group profit too - it's a P&L account
    fx_elim_residual_gbp = -sum((p.amount for p in ic_elim_postings if p.account == "7300"), Decimal("0"))

    group_profit = us_profit + uk_profit + in_postacq_profit_gbp + fx_elim_residual_gbp
    profit_nci = profit_nci_gbp if not isinstance(profit_nci_gbp, RateMiss) else Decimal("0")
    profit_owners = group_profit - profit_nci

    # ---- translation reserve: the single balancing plug ----
    share_capital_closing = opening.get("3100", Decimal("0"))
    retained_earnings_closing = opening.get("3200", Decimal("0")) + profit_owners
    nci_closing = (nci_at_acq_gbp if not isinstance(nci_at_acq_gbp, RateMiss) else Decimal("0")) + profit_nci
    translation_reserve_closing = net_assets_closing - share_capital_closing - retained_earnings_closing - nci_closing
    translation_reserve_movement = translation_reserve_closing - opening.get("3300", Decimal("0"))

    # ---- India acquisition elimination entry (the one that's a real FY2024 event) ----
    in_sc_ref = _posting_sources_label([m for m in in_equity_postings if m.group_code == "3100"])
    in_re_ref = _posting_sources_label([m for m in in_equity_postings if m.group_code == "3200"])
    pre_acq_sources = "; ".join(
        s.label() for code in pre_acq for s in pre_sources.get(code, [])
    )
    us_inv_ref = _posting_sources_label(us_investment_postings)
    eliminations = []
    for el in uk_elim_lines:
        eliminations.append(
            EliminationRow(el.group_id, el.description, el.entity, el.account, el.amount, el.source)
        )
    eliminations.append(EliminationRow(
        "ic-mgmt-fee-bs", "Eliminate intercompany management fee receivable/payable (1250 vs 2150)",
        "US/UK", "1250/2150", us_1250, "tb_us.csv (1250); tb_uk.csv (2150); intercompany.csv",
    ))
    eliminations.append(EliminationRow(
        "ic-mgmt-fee-pl", "Eliminate intercompany management fee income/expense (4200 vs 6300); "
                          "residual FX difference to 7300 per policy §5",
        "US/UK", "4200/6300", us_4200, "tb_us.csv (4200); tb_uk.csv (6300)",
    ))
    eliminations.append(EliminationRow(
        "acq-india", "Eliminate India's pre-acquisition net assets against goodwill, NCI at acquisition, "
                     "and the parent's investment (acquisition_note.md)",
        "IN/US", "3100/3200/1610", acquisition.NET_ASSETS_AT_COMPLETION_INR,
        f"{in_sc_ref}; {in_re_ref}; {pre_acq_sources}; {us_inv_ref}",
    ))

    return ConsolidationResult(
        tb_postings=all_postings,
        eliminations=eliminations,
        issues=issues,
        group_profit=group_profit,
        profit_owners=profit_owners,
        profit_nci=profit_nci,
        goodwill_closing_gbp=goodwill_closing_gbp,
        nci_at_acquisition_gbp=nci_at_acq_gbp if not isinstance(nci_at_acq_gbp, RateMiss) else None,
        opening_equity=opening,
        translation_reserve_movement=translation_reserve_movement,
        net_assets_closing=net_assets_closing,
        journal_counts=journal_counts,
        intercompany_causes={
            "item_in_transit_gbp": sum((p.amount for p in uk_correction_postings if p.account == "6300"), Decimal("0")),
            "fx_remeasurement_on_booked_balance_gbp": sum(
                (p.amount for p in uk_correction_postings if p.account == "7300"), Decimal("0")
            ),
            "pl_translation_basis_residual_gbp": elim_pl_residual,
        },
    )
