"""Ties subledger_controls.csv (the independent AR/AP sub-ledger totals) back to
the mapped trial balance. This is a control check, not a correction: if the GL
and the sub-ledger disagree, that's reported as-is, the GL balance is not quietly
adjusted to match the control total (we don't know which one, if either, is
right)."""

from decimal import Decimal

from .mapping import Issue

LEDGER_TO_GROUP_ACCOUNT = {
    "Accounts receivable (trade)": "1200",
    "Accounts payable (trade)": "2100",
}


def check_subledger_controls(subledger_rows: list[dict], gl_balance_by_entity_account: dict) -> list[Issue]:
    """gl_balance_by_entity_account: {(entity, group_code): Decimal}, debit-positive,
    in the entity's own functional currency."""
    issues = []
    for row in subledger_rows:
        group_code = LEDGER_TO_GROUP_ACCOUNT.get(row["ledger"])
        if group_code is None:
            continue
        control_total = Decimal(row["control_total"])
        # AP is a credit-normal liability; control totals are given as plain positive
        # amounts, so flip sign to compare against our debit-positive GL convention.
        expected = control_total if group_code == "1200" else -control_total
        gl_balance = gl_balance_by_entity_account.get((row["entity_id"], group_code))
        if gl_balance is None:
            continue
        difference = gl_balance - expected
        if difference != 0:
            issues.append(
                Issue(
                    file="subledger_controls.csv",
                    line=f"{row['entity_id']}/{row['ledger']}",
                    amount=difference,
                    description=(
                        f"{row['entity_id']} {row['ledger']} sub-ledger control total is "
                        f"{control_total} {row['currency']}, but the mapped GL balance is "
                        f"{abs(gl_balance)} {row['currency']} - a difference of {abs(difference)}. "
                        f"Reported as-is; the GL has not been adjusted to match the sub-ledger."
                    ),
                    action="flagged",
                )
            )
    return issues
