from decimal import Decimal
from pathlib import Path

from northwind import consolidate, statements, validate

DATA = Path(__file__).parent.parent / "data"


def _run():
    return consolidate.run(DATA)


def test_net_assets_identity_holds():
    result = _run()
    assert validate.check_net_assets_identity(result) == []


def test_balance_sheet_identity_holds():
    result = _run()
    group_coa = __import__("northwind.io_loaders", fromlist=["load_group_coa"]).load_group_coa(DATA / "group_coa.csv")
    bs = statements.build_balance_sheet(result, group_coa)
    assert validate.check_balance_sheet_identity(bs) == []


def test_group_revenue_matches_independent_hand_calculation():
    """US revenue @ FY avg + UK revenue (GBP) + India post-acq revenue @ H2 average,
    computed here from the raw rates rather than through the pipeline's own code -
    if this drifts from control_figures, something in the pipeline changed the
    definition of group revenue."""
    result = _run()
    group_coa = __import__("northwind.io_loaders", fromlist=["load_group_coa"]).load_group_coa(DATA / "group_coa.csv")
    pl = statements.build_profit_and_loss(result, group_coa)

    us_rev = Decimal("18400000.00") / Decimal("1.2780")
    uk_rev = Decimal("9850000.00")
    in_rev_postacq = Decimal("437000000.00") / (Decimal("1.2840") * Decimal("83.95"))
    expected = round(us_rev + uk_rev + in_rev_postacq, 2)

    assert Decimal(str(pl["revenue"]["4100"]["amount_gbp"])) == expected


def test_deferred_income_mapping_error_is_caught():
    result = _run()
    assert any(
        "2310" in i.description and "rerouted" in i.description
        for i in result.issues if i.file == "map_uk.csv"
    )


def test_uk_subledger_mismatches_are_both_reported():
    result = _run()
    sub_issues = [i for i in result.issues if i.file == "subledger_controls.csv"]
    assert len(sub_issues) == 2


def test_known_traps_all_surface_as_issues():
    result = _run()
    descriptions = " | ".join(i.description for i in result.issues)
    assert "JE-006" in descriptions or any(i.line == "JE-006" for i in result.issues)
    assert any(i.line == "JE-017" for i in result.issues)
    assert any(i.line == "JE-016" for i in result.issues)
    assert any("IN-GST-ITC" in i.description for i in result.issues)
