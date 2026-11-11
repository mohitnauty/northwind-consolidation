"""Exchange rate lookups, in a single convention: every rate is stated as
"units of X per 1 GBP", so converting a foreign-currency amount to GBP is always
amount / rate(X, rate_type). fx_rates.csv doesn't actually give GBP/INR directly -
policy §2 says to get it by chaining GBP/USD and USD/INR of the same rate type,
so that's what _rate() does when there's no direct GBP row for a currency.

The one rate this deliberately can't produce is a GBP/SGD closing rate: the file
only has "opening" and "average" rows for SGD, and there's no USD/SGD rate at all
to chain through. get_rate() returns None rather than falling back to some other
rate type as a stand-in - policy §7 is about rounding, not about which rate to use,
and the assignment is explicit that an honest null beats a guess.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RateMiss:
    reason: str


class FxTable:
    def __init__(self, rows: list[dict]):
        # direct[(quote_ccy, rate_type)] = Decimal, keyed only for rows based on GBP or USD
        self._gbp_direct: dict[tuple[str, str], Decimal] = {}
        self._usd_direct: dict[tuple[str, str], Decimal] = {}
        for row in rows:
            rate = Decimal(row["rate"])
            key = (row["quote_currency"], row["rate_type"])
            if row["base_currency"] == "GBP":
                self._gbp_direct[key] = rate
            elif row["base_currency"] == "USD":
                self._usd_direct[key] = rate

    def get_rate(self, currency: str, rate_type: str):
        """Returns units of `currency` per 1 GBP, or a RateMiss explaining why not."""
        if currency == "GBP":
            return Decimal("1")

        direct = self._gbp_direct.get((currency, rate_type))
        if direct is not None:
            return direct

        gbp_usd = self._gbp_direct.get(("USD", rate_type))
        usd_x = self._usd_direct.get((currency, rate_type))
        if gbp_usd is not None and usd_x is not None:
            return gbp_usd * usd_x

        return RateMiss(
            f"no GBP/{currency} {rate_type} rate, and no GBP->USD->{currency} cross rate "
            f"available for '{rate_type}' in fx_rates.csv"
        )

    def to_gbp(self, amount: Decimal, currency: str, rate_type: str):
        rate = self.get_rate(currency, rate_type)
        if isinstance(rate, RateMiss):
            return rate
        return amount / rate
