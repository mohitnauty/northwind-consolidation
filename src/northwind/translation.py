"""Translates a list of local-currency postings to GBP at one rate type.

Nothing here decides *which* rate type to use for a given account - that's a
policy decision made by the caller (consolidate.py), because it depends on
whether the account is a balance-sheet or P&L account, and for India, on
whether the activity is pre- or post-acquisition. This module just does the
division and carries provenance through, and reports a RateMiss as an issue
rather than converting at some other rate or dropping the posting.
"""

from .fx import RateMiss
from .mapping import Issue
from .model import Posting


def translate_postings(postings: list[Posting], fx, rate_type: str) -> tuple[list[Posting], list[Issue]]:
    translated = []
    issues = []
    for p in postings:
        converted = fx.to_gbp(p.amount, p.currency, rate_type)
        if isinstance(converted, RateMiss):
            issues.append(
                Issue(
                    file=p.sources[0].file if p.sources else "unknown",
                    line=p.sources[0].line if p.sources else "unknown",
                    amount=p.amount,
                    description=(
                        f"{p.entity} account {p.account}: cannot translate {p.amount} {p.currency} "
                        f"to GBP at '{rate_type}' rate - {converted.reason}"
                    ),
                    action="blocked",
                )
            )
            continue
        translated.append(Posting(p.entity, p.account, converted, "GBP", p.sources))
    return translated, issues
