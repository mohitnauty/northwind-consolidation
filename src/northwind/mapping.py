"""Applies map_uk.csv / map_in.csv and reports anything that doesn't map.

US doesn't go through this module at all - its TB already uses group account codes
(there's no map_us.csv in the bundle, and tb_us.csv's account_code column matches
group_coa.csv directly), so io_loaders.load_tb_us() output goes straight to
translation.py.
"""

from dataclasses import dataclass
from decimal import Decimal

from .model import SourceRef


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
