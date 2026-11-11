from decimal import Decimal

from northwind.fx import FxTable, RateMiss

ROWS = [
    {"base_currency": "GBP", "quote_currency": "USD", "rate_type": "closing", "rate": "1.2530"},
    {"base_currency": "GBP", "quote_currency": "USD", "rate_type": "h2_average", "rate": "1.2840"},
    {"base_currency": "USD", "quote_currency": "INR", "rate_type": "closing", "rate": "85.62"},
    {"base_currency": "USD", "quote_currency": "INR", "rate_type": "h2_average", "rate": "83.95"},
    {"base_currency": "GBP", "quote_currency": "SGD", "rate_type": "average", "rate": "1.7120"},
]


def test_direct_gbp_rate():
    fx = FxTable(ROWS)
    assert fx.get_rate("USD", "closing") == Decimal("1.2530")


def test_cross_rate_is_product_of_same_rate_type():
    fx = FxTable(ROWS)
    rate = fx.get_rate("INR", "closing")
    assert rate == Decimal("1.2530") * Decimal("85.62")


def test_missing_rate_type_is_explicit_miss_not_a_fallback():
    # SGD only has an "average" row here (matching the real fx_rates.csv, which has
    # no SGD closing/spot row and no USD/SGD row to chain through).
    fx = FxTable(ROWS)
    result = fx.get_rate("SGD", "closing")
    assert isinstance(result, RateMiss)
    assert "SGD" in result.reason


def test_gbp_to_gbp_is_identity():
    fx = FxTable(ROWS)
    assert fx.get_rate("GBP", "closing") == Decimal("1")


def test_to_gbp_divides_by_rate():
    fx = FxTable(ROWS)
    converted = fx.to_gbp(Decimal("125300"), "USD", "closing")
    assert converted == Decimal("100000")
