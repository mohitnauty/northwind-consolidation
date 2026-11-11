from decimal import Decimal
from pathlib import Path

from northwind.fx import FxTable
from northwind.intercompany import eliminate_management_fee, find_item_in_transit, uk_correction_postings
from northwind.io_loaders import load_group_coa, load_intercompany, load_tb_uk_raw

DATA = Path(__file__).parent.parent / "data"

FX_ROWS = [
    {"base_currency": "GBP", "quote_currency": "USD", "rate_type": "closing", "rate": "1.2530"},
]


def test_item_in_transit_is_the_fifth_invoice():
    ic_rows = load_intercompany(DATA / "intercompany.csv")
    transit = find_item_in_transit(ic_rows)
    assert len(transit) == 1
    assert transit[0]["doc_ref"] == "INV-US-2291"


def test_uk_corrections_balance_to_zero_on_their_own():
    ic_rows = load_intercompany(DATA / "intercompany.csv")
    uk_raw = load_tb_uk_raw(DATA / "tb_uk.csv")
    group_coa = load_group_coa(DATA / "group_coa.csv")
    fx = FxTable(FX_ROWS)

    postings, elim_lines, issues = uk_correction_postings(ic_rows, uk_raw, fx, group_coa)
    assert sum(p.amount for p in postings) == Decimal("0")
    assert len(elim_lines) == 1  # just the transit item; the remeasurement isn't an elimination
    assert not any(i.action == "blocked" for i in issues)


def test_corrected_uk_payable_matches_us_receivable_in_usd_terms():
    ic_rows = load_intercompany(DATA / "intercompany.csv")
    uk_raw = load_tb_uk_raw(DATA / "tb_uk.csv")
    group_coa = load_group_coa(DATA / "group_coa.csv")
    fx = FxTable(FX_ROWS)
    closing = fx.get_rate("USD", "closing")

    postings, _, _ = uk_correction_postings(ic_rows, uk_raw, fx, group_coa)
    booked_2150 = next(r for r in uk_raw if r.nominal_code == "2150").balance
    corrected_2150 = booked_2150 + sum(p.amount for p in postings if p.account == "2150")
    # two separate divisions (629,840 then 10,160) vs one division of the 640,000 total
    # differ in the far decimal places at full Decimal precision - round to 2dp, which is
    # the precision that actually ends up in any reported figure (policy §7).
    expected = -(Decimal("640000.00") / closing)
    assert round(corrected_2150, 2) == round(expected, 2)


def test_elimination_nets_full_postings_to_zero():
    # us_1250/-uk_2150 match exactly (both 640,000 USD at the same closing rate);
    # us_4200/uk_6300 don't, so the 7300 plug should absorb exactly the difference.
    postings, elim_bs, elim_pl_residual = eliminate_management_fee(
        us_1250=Decimal("510774.94"),
        uk_2150=Decimal("-510774.94"),
        us_4200=Decimal("-500782.47"),
        uk_6300=Decimal("498817.06"),
    )
    assert elim_bs == Decimal("0")
    assert sum(p.amount for p in postings) == Decimal("0")
