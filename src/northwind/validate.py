"""Runtime checks that run every time the pipeline runs, not just in tests.
These populate issues.json if something that should always be true isn't.

The main one is the identity documented in consolidate.py's module docstring:
net assets at closing = group profit for the year + share capital + opening
retained earnings + closing translation reserve + NCI at acquisition. That one
equation is really the whole consolidation - if it doesn't hold, something
upstream is wrong even if every individual module's own unit tests pass.
"""

from decimal import Decimal

from .mapping import Issue

# Tolerance for rounding noise, not a "close enough" shrug: policy §7 rounds only
# final reported figures, so a sum of a dozen independently-rounded line items can
# land a cent or two away from a single figure rounded once at the end. Anything
# bigger than this is a real discrepancy, not rounding.
EPSILON = Decimal("0.05")


def check_raw_tb_balances(label: str, postings) -> list[Issue]:
    total = sum((p.amount for p in postings), Decimal("0"))
    if abs(total) > EPSILON:
        return [Issue(file=label, line="n/a", amount=total,
                      description=f"{label} does not balance on its own: net {total}", action="blocked")]
    return []


def check_net_assets_identity(result) -> list[Issue]:
    opening = result.opening_equity
    translation_reserve_closing = opening.get("3300", Decimal("0")) + result.translation_reserve_movement
    nci_at_acq = result.nci_at_acquisition_gbp or Decimal("0")
    expected = (
        result.group_profit
        + opening.get("3100", Decimal("0"))
        + opening.get("3200", Decimal("0"))
        + translation_reserve_closing
        + nci_at_acq
    )
    difference = result.net_assets_closing - expected
    if abs(difference) > EPSILON:
        return [Issue(
            file="consolidate.py", line="n/a", amount=difference,
            description=(
                f"net assets identity does not hold: net assets closing {result.net_assets_closing} vs "
                f"group profit + opening equity + NCI at acquisition {expected} (difference {difference})"
            ),
            action="blocked",
        )]
    return []


def check_balance_sheet_identity(balance_sheet: dict) -> list[Issue]:
    total = Decimal(str(balance_sheet["total_assets"])) + Decimal(str(balance_sheet["total_liabilities"]))
    equity = Decimal(str(balance_sheet["total_equity"]))
    if abs(total - equity) > EPSILON:
        return [Issue(
            file="balance_sheet.json", line="n/a", amount=total - equity,
            description=f"total assets + total liabilities ({total}) != total equity ({equity})",
            action="blocked",
        )]
    return []
