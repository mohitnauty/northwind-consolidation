"""Shared data shapes for the consolidation pipeline.

Everything downstream of the loaders is built out of Posting objects. The point of
carrying `sources` on every posting, all the way through mapping, FX translation,
and elimination, is traceability: by the time we write consolidated_tb.csv we can
just flatten each account's postings back into their source file/line references
instead of trying to reconstruct where a number came from after the fact.

Sign convention: `amount` is always debit-positive, credit-negative, regardless of
the account's normal balance. That's what lets us check "does this sum to zero"
at every stage without having to know each account's type first.
"""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class SourceRef:
    file: str
    line: str  # CSV line number as a string, or a journal/invoice id - whatever locates the row
    detail: str = ""  # short human-readable context, e.g. the raw account code or description

    def label(self) -> str:
        suffix = f" ({self.detail})" if self.detail else ""
        return f"{self.file}:{self.line}{suffix}"


@dataclass
class Posting:
    entity: str
    account: str  # group chart-of-accounts code
    amount: Decimal  # debit-positive, in `currency`
    currency: str
    sources: tuple = field(default_factory=tuple)

    def with_amount(self, amount: Decimal) -> "Posting":
        return Posting(self.entity, self.account, amount, self.currency, self.sources)
