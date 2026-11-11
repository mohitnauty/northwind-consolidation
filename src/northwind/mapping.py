"""Applies map_uk.csv / map_in.csv and reports anything that doesn't map.

US doesn't go through this module at all - its TB already uses group account codes
(there's no map_us.csv in the bundle, and tb_us.csv's account_code column matches
group_coa.csv directly), so io_loaders.load_tb_us() output goes straight to
translation.py.

One mapping is wrong: map_uk.csv sends local code 2310 ("Deferred income") to
group account 4100 (Revenue). 2310's own name is an exact match for group
account 2300, which is *also* called "Deferred income" - a liability, not
revenue - and it's the only group account with that name. That's too specific
to be a coincidence, and letting it stand would overstate group revenue by
180,000 GBP and understate the deferred income liability by the same amount.
_resolve_group_code() catches this generically (any local account whose own
name is an exact match for a *different* group account than the one it's
mapped to) rather than hardcoding this one case, and reroutes it, with the
override reported in issues.json rather than applied silently.
"""

from dataclasses import dataclass
from decimal import Decimal

from .model import SourceRef


def _name_matched_group_code(local_name: str, group_coa: dict):
    normalized = local_name.strip().lower()
    for code, info in group_coa.items():
        if info["account_name"].strip().lower() == normalized:
            return code
    return None


def _resolve_group_code(local_name: str, stated_code: str, group_coa: dict):
    """Returns (group_code, override_issue_description_or_None)."""
    name_match = _name_matched_group_code(local_name, group_coa)
    if name_match is not None and name_match != stated_code:
        return name_match, (
            f"'{local_name}' is mapped to group account {stated_code} "
            f"({group_coa.get(stated_code, {}).get('account_name', '?')}), but its own name is an exact "
            f"match for group account {name_match} ({group_coa[name_match]['account_name']}) - rerouted "
            f"to {name_match} as a mapping error rather than applied as stated"
        )
    return stated_code, None


@dataclass
class Issue:
    file: str
    line: str
    amount: Decimal | None
    description: str
    action: str  # "blocked" | "assumed" | "flagged"


@dataclass
class MappedRow:
    entity: str
    group_code: str
    local_code: str
    amount: Decimal  # debit-positive, in the row's stated currency
    currency: str
    ref: SourceRef
    extra: dict  # entity-specific leftovers (e.g. UK's txn_currency/txn_amount)


def map_uk(raw_rows, uk_map: dict, group_coa: dict) -> tuple[list[MappedRow], list[Issue]]:
    mapped, issues = [], []
    for row in raw_rows:
        group_code = uk_map.get(row.nominal_code)
        if group_code is None or group_code not in group_coa:
            issues.append(
                Issue(
                    file="tb_uk.csv",
                    line=row.ref.line,
                    amount=row.balance,
                    description=(
                        f"UK nominal code {row.nominal_code} ({row.description}) has no "
                        f"group account mapping in map_uk.csv"
                    ),
                    action="blocked",
                )
            )
            continue
        group_code, override_reason = _resolve_group_code(row.description, group_code, group_coa)
        if override_reason:
            issues.append(
                Issue(file="map_uk.csv", line=row.ref.line, amount=row.balance,
                      description=f"UK nominal code {row.nominal_code}: {override_reason}", action="assumed")
            )
        mapped.append(
            MappedRow(
                entity="UK",
                group_code=group_code,
                local_code=row.nominal_code,
                amount=row.balance,
                currency="GBP",
                ref=row.ref,
                extra={"txn_currency": row.txn_currency, "txn_amount": row.txn_amount},
            )
        )
    return mapped, issues


def map_india(raw_rows, in_map: dict, group_coa: dict) -> tuple[list[MappedRow], list[Issue]]:
    mapped, issues = [], []
    for row in raw_rows:
        group_code = in_map.get(row["ledger_code"])
        if group_code is None or group_code not in group_coa:
            issues.append(
                Issue(
                    file="tb_in.csv",
                    line=row["ref"].line,
                    amount=row["amount"],
                    description=(
                        f"India ledger code {row['ledger_code']} ({row['ledger_name']}) has no "
                        f"group account mapping in map_in.csv"
                    ),
                    action="blocked",
                )
            )
            continue
        group_code, override_reason = _resolve_group_code(row["ledger_name"], group_code, group_coa)
        if override_reason:
            issues.append(
                Issue(file="map_in.csv", line=row["ref"].line, amount=row["amount"],
                      description=f"India ledger code {row['ledger_code']}: {override_reason}", action="assumed")
            )
        mapped.append(
            MappedRow(
                entity="IN",
                group_code=group_code,
                local_code=row["ledger_code"],
                amount=row["amount"],
                currency="INR",
                ref=row["ref"],
                extra={},
            )
        )
    return mapped, issues
