"""Intercompany matching and elimination for the US/UK management fee invoices.

What's in intercompany.csv: US billed UK five management fee invoices
(INV-US-2201/2224/2257/2268/2291, totalling 157,460 x 4 + 10,160 = 640,000 USD,
which matches US's own TB exactly - account 1250 receivable and 4200 income are
both 640,000 USD). UK only booked four of them. The fifth, INV-US-2291, is dated
2024-12-31 - a year-end item in transit, and policy §5 says the receiving entity
(UK, who owes the money) records it at the closing rate.

There's a second thing going on that's easy to miss: UK's existing payable for
the four invoices it did book (2150, -490,707.72 GBP) was translated invoice by
invoice at whatever rate was in effect on each invoice date. That's fine for a
P&L expense that's already been recognised, but 2150 is a monetary balance in a
currency other than UK's functional currency (GBP), so policy §3 requires it to
be retranslated to the closing rate for the group accounts, with the difference
going to UK's own P&L account 7300 - not to the elimination.

So there are two separate corrections to UK's books before anything gets
eliminated against US:
  1. Recognise the missing invoice (debit 6300, credit 2150, both at closing
     rate) - a real, previously unrecorded expense.
  2. Remeasure the payable for the four invoices UK already booked, from its
     historical booked value to the closing rate - a pure FX remeasurement,
     not a new expense.

After both corrections, UK's 2150 should equal US's 1250 exactly (both are the
same 640,000 USD at the same closing rate), so the balance-sheet elimination is
clean. The P&L elimination (4200 vs 6300) still leaves a residual, because
4200 translates at the US entity's FY-average rate while 6300 is UK's own GBP
booking at each invoice's historical rate - two different, both-correct bases
for translating the same economic event. Policy §5 sends that residual to 7300.
"""

from dataclasses import dataclass
from decimal import Decimal

from .fx import RateMiss
from .mapping import Issue
from .model import Posting, SourceRef


@dataclass
class EliminationLine:
    group_id: str
    description: str
    entity: str
    account: str
    amount: Decimal
    source: str  # human-readable source row reference


def find_item_in_transit(ic_rows: list[dict]) -> list[dict]:
    by_doc_ref: dict[str, list[dict]] = {}
    for row in ic_rows:
        by_doc_ref.setdefault(row["doc_ref"], []).append(row)
    return [rows[0] for rows in by_doc_ref.values() if len(rows) == 1]


def uk_correction_postings(ic_rows: list[dict], uk_raw_rows, fx, group_coa: dict):
    """Returns (postings, elimination_lines, issues) for the two UK-side corrections."""
    postings: list[Posting] = []
    elim_lines: list[EliminationLine] = []
    issues: list[Issue] = []

    transit = find_item_in_transit(ic_rows)
    closing_rate = fx.get_rate("USD", "closing")
    if isinstance(closing_rate, RateMiss):
        issues.append(
            Issue(
                file="intercompany.csv", line="n/a", amount=None,
                description=f"cannot value intercompany items in transit: {closing_rate.reason}",
                action="blocked",
            )
        )
    else:
        for row in transit:
            usd_amount = Decimal(row["doc_amount"])
            gbp_amount = usd_amount / closing_rate
            ref = SourceRef("intercompany.csv", str(row["_line"]), f"{row['doc_ref']} - item in transit")
            postings.append(Posting("UK", "6300", gbp_amount, "GBP", (ref,)))
            postings.append(Posting("UK", "2150", -gbp_amount, "GBP", (ref,)))
            elim_lines.append(
                EliminationLine(
                    "ic-transit", f"{row['doc_ref']}: unbooked by UK, recorded at closing rate per policy §5",
                    "UK", "2150/6300", gbp_amount, ref.label(),
                )
            )
            issues.append(
                Issue(
                    file="intercompany.csv", line=str(row["_line"]), amount=gbp_amount,
                    description=(
                        f"{row['doc_ref']} ({usd_amount} USD, {row['doc_date']}) was never booked by UK - "
                        f"item in transit, recorded at the 31 Dec closing rate per policy §5"
                    ),
                    action="assumed",
                )
            )

    # remeasure the balance UK already booked for the other four invoices
    booked_rows = [r for r in uk_raw_rows if r.nominal_code == "2150"]
    if booked_rows and not isinstance(closing_rate, RateMiss):
        booked = booked_rows[0]
        if booked.txn_amount is not None and booked.txn_currency == "USD":
            correct_gbp = booked.txn_amount / closing_rate  # txn_amount is already credit-negative
            remeasurement = correct_gbp - booked.balance
            if remeasurement != 0:
                ref = SourceRef("tb_uk.csv", booked.ref.line, "2150 remeasured to closing rate")
                postings.append(Posting("UK", "2150", remeasurement, "GBP", (ref,)))
                postings.append(Posting("UK", "7300", -remeasurement, "GBP", (ref,)))
                issues.append(
                    Issue(
                        file="tb_uk.csv", line=booked.ref.line, amount=remeasurement,
                        description=(
                            "UK's intercompany payable (2150) was booked at each invoice's historical rate "
                            f"({booked.balance} GBP for {booked.txn_amount} USD); policy §3 requires monetary "
                            "items in a non-functional currency to be remeasured at the closing rate "
                            f"({correct_gbp} GBP). Difference of {remeasurement} GBP posted to 7300."
                        ),
                        action="assumed",
                    )
                )

    return postings, elim_lines, issues


def eliminate_management_fee(us_1250: Decimal, uk_2150: Decimal, us_4200: Decimal, uk_6300: Decimal):
    """Takes the four GBP account balances (debit-positive) after translation and
    UK correction, and returns the elimination postings plus any residual to 7300.

    us_1250 (receivable, +) should now equal -uk_2150 (payable) exactly, since both
    reduce to the same 640,000 USD at the same closing rate. us_4200 (income, -) and
    uk_6300 (expense, +) won't net to zero - the residual is the FX difference
    policy §5 routes to 7300.
    """
    elim_bs = us_1250 + uk_2150  # should be ~0
    elim_pl_residual = us_4200 + uk_6300  # whatever's left over goes to 7300

    postings = [
        Posting("US", "1250", -us_1250, "GBP", ()),
        Posting("UK", "2150", -uk_2150, "GBP", ()),
        Posting("US", "4200", -us_4200, "GBP", ()),
        Posting("UK", "6300", -uk_6300, "GBP", ()),
    ]
    # the four lines above fully zero out both accounts on both sides, which only
    # balances on its own if income and expense were an exact match. They aren't
    # (different translation bases), so the shortfall/excess has to be plugged
    # back in on 7300, or this elimination would throw the consolidated TB out of
    # balance by exactly that amount.
    if elim_pl_residual != 0:
        postings.append(Posting("GROUP", "7300", elim_pl_residual, "GBP", ()))

    return postings, elim_bs, elim_pl_residual
