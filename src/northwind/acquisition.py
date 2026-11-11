"""India acquisition accounting: goodwill, NCI at acquisition, and splitting
India's fiscal year into the pre-acquisition stub (1 Apr - 30 Jun 2024, already
baked into "net assets at completion" and not consolidated again) and the
post-acquisition period (1 Jul - 31 Dec 2024, the part that actually enters
group P&L).

The figures below come straight from acquisition_note.md - they're a one-off
business event, not a repeating data file, so there's nothing to "load" here,
just constants with their source cited.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .model import SourceRef

ACQUISITION_DATE = date(2024, 7, 1)
OWNERSHIP_PCT = Decimal("0.80")

# acquisition_note.md: "Net assets at completion" table
EQUITY_SHARE_CAPITAL_INR = Decimal("250000000")
RESERVES_AT_1_APR_INR = Decimal("410000000")
PROFIT_1APR_TO_30JUN_INR = Decimal("18000000")
NET_ASSETS_AT_COMPLETION_INR = (
    EQUITY_SHARE_CAPITAL_INR + RESERVES_AT_1_APR_INR + PROFIT_1APR_TO_30JUN_INR
)  # 678,000,000, matches the note's own total
CONSIDERATION_INR = Decimal("690000000")

PRE_ACQUISITION_MONTHS = {"2024-04", "2024-05", "2024-06"}
POST_ACQUISITION_MONTHS = {"2024-07", "2024-08", "2024-09", "2024-10", "2024-11", "2024-12"}


@dataclass
class AcquisitionAccounting:
    goodwill_inr: Decimal
    nci_at_acquisition_inr: Decimal
    pre_acq_profit_inr: Decimal  # for cross-check against the acquisition note's 18,000,000


def goodwill_and_nci_at_acquisition() -> AcquisitionAccounting:
    nci = NET_ASSETS_AT_COMPLETION_INR * (1 - OWNERSHIP_PCT)
    goodwill = CONSIDERATION_INR - NET_ASSETS_AT_COMPLETION_INR * OWNERSHIP_PCT
    return AcquisitionAccounting(goodwill_inr=goodwill, nci_at_acquisition_inr=nci, pre_acq_profit_inr=Decimal("0"))


def split_india_monthly_pl(monthly_rows: list[dict], in_map: dict):
    """Returns (pre_acq_by_group_code, post_acq_by_group_code, sources_by_group_code).

    Amounts stay in India's own ledger-code grouping until mapped to group codes here,
    so a line with no mapping (there isn't one in the monthly P&L file, but this keeps
    the same discipline as mapping.py) would show up rather than being silently dropped.
    """
    pre: dict[str, Decimal] = {}
    post: dict[str, Decimal] = {}
    sources: dict[str, list] = {}
    unmapped = set()

    for row in monthly_rows:
        group_code = in_map.get(row["ledger_code"])
        if group_code is None:
            unmapped.add(row["ledger_code"])
            continue
        bucket = pre if row["month"] in PRE_ACQUISITION_MONTHS else (
            post if row["month"] in POST_ACQUISITION_MONTHS else None
        )
        if bucket is None:
            continue  # month outside FY2024 entirely - none exist in this file, kept defensive
        bucket[group_code] = bucket.get(group_code, Decimal("0")) + row["amount"]
        sources.setdefault(group_code, []).append(row["ref"])

    return pre, post, sources, unmapped


def pre_acquisition_profit(pre_acq_by_group_code: dict) -> Decimal:
    """Net of all pre-acquisition P&L lines, debit-positive convention, so a profit
    comes out negative here - callers that want a plain profit figure should negate it."""
    return -sum(pre_acq_by_group_code.values(), Decimal("0"))
