"""Readers for the raw input bundle.

Each entity's ERP exported its trial balance in its own shape (NetSuite, Sage 50,
Tally Prime all do this differently), so this module's job is just getting every
row into something the rest of the pipeline can treat uniformly, while keeping
enough of the raw row around for traceability. It does not apply the UK/India
account mappings and does not apply FX - those are separate steps on purpose,
so a bad mapping or a missing rate is a distinct, reportable failure rather than
something buried inside "load the file".
"""

import csv
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .model import Posting, SourceRef


def _dec(value: str) -> Decimal:
    value = (value or "").strip()
    if value == "":
        return Decimal("0")
    return Decimal(value)


def load_entities(path: Path) -> dict:
    with open(path, newline="") as f:
        return {row["entity_id"]: row for row in csv.DictReader(f)}


def load_group_coa(path: Path) -> dict:
    with open(path, newline="") as f:
        return {row["account_code"]: row for row in csv.DictReader(f)}


def load_tb_us(path: Path) -> list[Posting]:
    """US TB is already on group account codes and uses separate debit/credit columns."""
    postings = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            net = _dec(row["debit"]) - _dec(row["credit"])
            ref = SourceRef("tb_us.csv", str(reader.line_num), row["account_name"])
            postings.append(Posting("US", row["account_code"], net, "USD", (ref,)))
    return postings


@dataclass
class UkRawRow:
    nominal_code: str
    description: str
    cost_centre: str
    txn_currency: str
    txn_amount: Decimal | None
    balance: Decimal
    ref: SourceRef


def load_tb_uk_raw(path: Path) -> list[UkRawRow]:
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ref = SourceRef("tb_uk.csv", str(reader.line_num), row["description"])
            txn_amount = _dec(row["txn_amount"]) if row["txn_amount"].strip() else None
            rows.append(
                UkRawRow(
                    nominal_code=row["nominal_code"],
                    description=row["description"],
                    cost_centre=row.get("cost_centre", ""),
                    txn_currency=row["txn_currency"],
                    txn_amount=txn_amount,
                    balance=_dec(row["balance"]),
                    ref=ref,
                )
            )
    return rows


def load_tb_in_raw(path: Path) -> list[dict]:
    """Kept as raw dicts (not Postings) because India's TB is a cumulative YTD figure
    under its own fiscal year, not a standalone FY2024 balance - acquisition.py needs
    the raw dr/cr amounts to work out the pre/post-acquisition split before anyone
    treats these as postable balances."""
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sign = 1 if row["dr_cr"] == "Dr" else -1
            rows.append(
                {
                    "ledger_code": row["ledger_code"],
                    "ledger_name": row["ledger_name"],
                    "amount": sign * _dec(row["amount"]),
                    "ref": SourceRef("tb_in.csv", str(reader.line_num), row["ledger_name"]),
                }
            )
    return rows


def load_in_pl_monthly(path: Path) -> list[dict]:
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sign = 1 if row["dr_cr"] == "Dr" else -1
            rows.append(
                {
                    "ledger_code": row["ledger_code"],
                    "month": row["month"],
                    "amount": sign * _dec(row["amount"]),
                    "ref": SourceRef("in_pl_monthly.csv", str(reader.line_num), row["month"]),
                }
            )
    return rows


def load_account_map(path: Path) -> dict:
    with open(path, newline="") as f:
        return {row["local_code"]: row["group_code"] for row in csv.DictReader(f)}


def load_fx_rates(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_prior_year_group(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_subledger_controls(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_intercompany(path: Path) -> list[dict]:
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row = dict(row)
            row["_line"] = reader.line_num
            rows.append(row)
    return rows


def load_adjustments(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)
