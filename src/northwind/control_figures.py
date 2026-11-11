"""Builds the 12 appendix figures, using exactly the keys the brief specifies.

Ten keys are a plain number, or {"value": null, "reason": "..."} when the
figure genuinely can't be computed from the inputs - that shape keeps every
null self-explanatory without adding extra top-level keys the brief doesn't
list. Two keys - intercompany_difference and journals - are small breakdown
objects instead of a bare number, because their own descriptions in the brief
ask for a split ("split into its causes", "posted, rejected and held for
review"); that interpretation is recorded in DECISIONS.md.
"""

from decimal import Decimal

from .fx import RateMiss
from .statements import r2


def _num_or_null(value, reason: str):
    if value is None:
        return {"value": None, "reason": reason}
    return r2(value)


def build_control_figures(result, balance_sheet: dict, profit_and_loss: dict, fx) -> dict:
    sgd_rate = fx.get_rate("SGD", "closing")
    sgd_reason = None
    if isinstance(sgd_rate, RateMiss):
        sgd_reason = (
            "UK holds a 40,000 SGD bank balance (tb_uk.csv, nominal code 1210) that policy §3 requires "
            "to be remeasured at the 31 Dec closing rate. fx_rates.csv has no GBP/SGD closing rate and "
            "no USD/SGD rate to chain through, so the policy-correct figure cannot be computed. "
            "UK's own books carry it at 23,010.00 GBP, translated at an undocumented historical rate - "
            "that figure is not policy-compliant and is not reported here as if it were."
        )
    sgd_bank_gbp = {"value": None, "reason": sgd_reason} if sgd_reason else None

    causes = result.intercompany_causes
    intercompany_difference = {
        "item_in_transit_gbp": r2(causes["item_in_transit_gbp"]),
        "fx_remeasurement_on_booked_balance_gbp": r2(causes["fx_remeasurement_on_booked_balance_gbp"]),
        "pl_translation_basis_residual_gbp": r2(causes["pl_translation_basis_residual_gbp"]),
        "note": (
            "US's receivable/income and UK's payable/expense disagreed before consolidation for two reasons: "
            "a 10,160 USD invoice UK never booked (item in transit, policy §5), and UK's payable being carried "
            "at historical invoice-date rates instead of the closing rate (policy §3). Both are corrected before "
            "elimination; the remaining pl_translation_basis_residual_gbp is the unavoidable difference between "
            "translating US's income at the FY average rate and UK's expense at its own booked GBP value, which "
            "policy §5 routes to account 7300."
        ),
    }

    nci_reason = "goodwill/NCI could not be translated - see issues.json" if result.nci_at_acquisition_gbp is None else None

    return {
        "group_revenue": r2(sum(Decimal(str(v["amount_gbp"])) for v in profit_and_loss["revenue"].values())),
        "group_profit": r2(result.group_profit),
        "profit_owners": r2(result.profit_owners),
        "profit_nci": r2(result.profit_nci),
        "nci_closing": _num_or_null(
            None if result.nci_at_acquisition_gbp is None else Decimal(str(balance_sheet["equity"]["non_controlling_interest"])),
            nci_reason,
        ),
        "goodwill_closing": _num_or_null(result.goodwill_closing_gbp, nci_reason),
        "translation_reserve_movement": r2(result.translation_reserve_movement),
        "total_assets": balance_sheet["total_assets"],
        "total_equity": balance_sheet["total_equity"],
        "intercompany_difference": intercompany_difference,
        "sgd_bank_gbp": sgd_bank_gbp,
        "journals": dict(result.journal_counts),
    }
