"""Builds the required output shapes from a ConsolidationResult.

The trial balance (consolidated_tb.csv) is pre-close: P&L accounts stay open at
their full-year consolidated balance, share capital and retained earnings stay
at their opening value, and NCI shows only its acquisition-date recognition.
Translation reserve is the one equity line that has to carry its full in-year
movement even in a pre-close TB - there's no "open" holding account for
translation differences the way there is for ordinary trading profit, they go
straight to equity as they arise. See consolidate.py's module docstring and
VALIDATION.md for the identity that proves this is internally consistent:
net assets (closing) = group profit + share capital + opening retained earnings
+ closing translation reserve + NCI at acquisition.

balance_sheet.json, by contrast, is the real post-close position: retained
earnings and NCI both include their share of this year's profit.
"""

from decimal import Decimal, ROUND_HALF_UP

TWO_DP = Decimal("0.01")


def r2(value):
    if value is None:
        return None
    return float(value.quantize(TWO_DP, rounding=ROUND_HALF_UP))


def _group_by_account(result):
    by_account: dict[str, list] = {}
    for p in result.tb_postings:
        by_account.setdefault(p.account, []).append(p)
    return by_account


def build_consolidated_tb(result, group_coa: dict) -> list[dict]:
    by_account = _group_by_account(result)
    rows = []
    for code, postings in sorted(by_account.items()):
        total = sum((p.amount for p in postings), Decimal("0"))
        rows.append({
            "account_code": code,
            "account_name": group_coa.get(code, {}).get("account_name", ""),
            "amount_gbp": r2(total),
            "source_rows": [s.label() for p in postings for s in p.sources],
        })

    opening = result.opening_equity
    translation_reserve_closing = opening.get("3300", Decimal("0")) + result.translation_reserve_movement
    rows.append({
        "account_code": "3100", "account_name": "Share capital",
        "amount_gbp": r2(-opening.get("3100", Decimal("0"))),
        "source_rows": ["prior_year_group.csv (3100) - unchanged, no share issuance evidenced this year"],
    })
    rows.append({
        "account_code": "3200", "account_name": "Retained earnings (opening - P&L for the year is still open above)",
        "amount_gbp": r2(-opening.get("3200", Decimal("0"))),
        "source_rows": ["prior_year_group.csv (3200)"],
    })
    rows.append({
        "account_code": "3300", "account_name": "Translation reserve (closing - see VALIDATION.md)",
        "amount_gbp": r2(-translation_reserve_closing),
        "source_rows": ["prior_year_group.csv (3300) + computed translation reserve movement for the year"],
    })
    rows.append({
        "account_code": "3400", "account_name": "Non-controlling interest (at acquisition only - see VALIDATION.md)",
        "amount_gbp": r2(-result.nci_at_acquisition_gbp) if result.nci_at_acquisition_gbp is not None else None,
        "source_rows": ["acquisition_note.md; fx_rates.csv (spot, 2024-07-01)"],
    })
    return sorted(rows, key=lambda r: r["account_code"])


def build_balance_sheet(result, group_coa: dict) -> dict:
    by_account = _group_by_account(result)
    assets, liabilities = {}, {}
    for code, postings in by_account.items():
        info = group_coa.get(code, {})
        if info.get("statement") != "BS":
            continue
        total = sum((p.amount for p in postings), Decimal("0"))
        bucket = assets if info["account_type"] == "Asset" else liabilities if info["account_type"] == "Liability" else None
        if bucket is not None:
            bucket[code] = {"account_name": info["account_name"], "amount_gbp": r2(total)}

    opening = result.opening_equity
    retained_earnings_closing = opening.get("3200", Decimal("0")) + result.profit_owners
    translation_reserve_closing = opening.get("3300", Decimal("0")) + result.translation_reserve_movement
    nci_closing = (result.nci_at_acquisition_gbp or Decimal("0")) + result.profit_nci

    total_assets = sum(Decimal(str(v["amount_gbp"])) for v in assets.values())
    total_liabilities = sum(Decimal(str(v["amount_gbp"])) for v in liabilities.values())
    total_equity = opening.get("3100", Decimal("0")) + retained_earnings_closing + translation_reserve_closing + nci_closing

    return {
        "as_of": "2024-12-31",
        "currency": "GBP",
        "assets": assets,
        "liabilities": liabilities,
        "equity": {
            "share_capital": r2(opening.get("3100", Decimal("0"))),
            "retained_earnings": r2(retained_earnings_closing),
            "translation_reserve": r2(translation_reserve_closing),
            "non_controlling_interest": r2(nci_closing),
        },
        "total_assets": r2(total_assets),
        "total_liabilities": r2(total_liabilities),
        # total_assets + total_liabilities (liabilities are credit-negative) should equal
        # total_equity independently - that identity is checked in validate.py, not assumed here.
        "total_equity": r2(total_equity),
    }


def build_profit_and_loss(result, group_coa: dict) -> dict:
    by_account = _group_by_account(result)
    revenue, expenses = {}, {}
    for code, postings in by_account.items():
        info = group_coa.get(code, {})
        if info.get("statement") != "PL":
            continue
        total = sum((p.amount for p in postings), Decimal("0"))
        if info["account_type"] == "Revenue":
            revenue[code] = {"account_name": info["account_name"], "amount_gbp": r2(-total)}
        elif info["account_type"] == "Expense":
            expenses[code] = {"account_name": info["account_name"], "amount_gbp": r2(total)}

    return {
        "period": "FY2024",
        "currency": "GBP",
        "revenue": revenue,
        "expenses": expenses,
        "group_profit_for_the_year": r2(result.group_profit),
        "profit_attributable_to_owners_of_the_parent": r2(result.profit_owners),
        "profit_attributable_to_non_controlling_interest": r2(result.profit_nci),
    }


def build_changes_in_equity(result) -> dict:
    opening = result.opening_equity

    def row(code):
        return r2(opening.get(code, Decimal("0")))

    return {
        "currency": "GBP",
        "opening_2023_12_31": {
            "share_capital": row("3100"),
            "retained_earnings": row("3200"),
            "translation_reserve": row("3300"),
            "non_controlling_interest": row("3400"),
        },
        "movements_fy2024": {
            "share_capital": 0.0,
            "retained_earnings": r2(result.profit_owners),
            "translation_reserve": r2(result.translation_reserve_movement),
            "non_controlling_interest": r2(
                (result.nci_at_acquisition_gbp or Decimal("0")) - opening.get("3400", Decimal("0")) + result.profit_nci
            ),
        },
        "closing_2024_12_31": {
            "share_capital": r2(opening.get("3100", Decimal("0"))),
            "retained_earnings": r2(opening.get("3200", Decimal("0")) + result.profit_owners),
            "translation_reserve": r2(opening.get("3300", Decimal("0")) + result.translation_reserve_movement),
            "non_controlling_interest": r2((result.nci_at_acquisition_gbp or Decimal("0")) + result.profit_nci),
        },
    }


def build_eliminations(result) -> list[dict]:
    return [
        {
            "group_id": e.group_id,
            "description": e.description,
            "entity": e.entity,
            "account": e.account,
            "amount_gbp": r2(e.amount_gbp),
            "source_rows": e.source,
        }
        for e in result.eliminations
    ]


def build_issues(issues: list) -> list[dict]:
    return [
        {
            "file": i.file,
            "line": i.line,
            "amount": r2(i.amount) if isinstance(i.amount, Decimal) else i.amount,
            "description": i.description,
            "action": i.action,
        }
        for i in issues
    ]
