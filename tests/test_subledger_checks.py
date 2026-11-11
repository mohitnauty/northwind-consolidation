from decimal import Decimal

from northwind.subledger_checks import check_subledger_controls

SUBLEDGER_ROWS = [
    {"entity_id": "US", "ledger": "Accounts receivable (trade)", "currency": "USD", "control_total": "3120000.00"},
    {"entity_id": "UK", "ledger": "Accounts receivable (trade)", "currency": "GBP", "control_total": "1940000.00"},
    {"entity_id": "UK", "ledger": "Accounts payable (trade)", "currency": "GBP", "control_total": "1165000.00"},
]


def test_matching_control_total_raises_no_issue():
    gl = {("US", "1200"): Decimal("3120000.00")}
    issues = check_subledger_controls([SUBLEDGER_ROWS[0]], gl)
    assert issues == []


def test_uk_ar_and_ap_mismatches_are_both_flagged():
    gl = {
        ("UK", "1200"): Decimal("1985000.00"),
        ("UK", "2100"): Decimal("-1210000.00"),
    }
    issues = check_subledger_controls(SUBLEDGER_ROWS[1:], gl)
    assert len(issues) == 2
    assert all(abs(i.amount) == Decimal("45000.00") for i in issues)
