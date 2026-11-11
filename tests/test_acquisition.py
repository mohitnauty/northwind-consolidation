from decimal import Decimal
from pathlib import Path

from northwind.acquisition import (
    goodwill_and_nci_at_acquisition,
    pre_acquisition_profit,
    split_india_monthly_pl,
)
from northwind.io_loaders import load_account_map, load_in_pl_monthly

DATA = Path(__file__).parent.parent / "data"


def test_goodwill_and_nci_tie_to_acquisition_note():
    result = goodwill_and_nci_at_acquisition()
    # acquisition_note.md: net assets at completion 678,000,000; 80% acquired for 690,000,000
    assert result.nci_at_acquisition_inr == Decimal("135600000")
    assert result.goodwill_inr == Decimal("147600000")


def test_pre_acquisition_profit_ties_to_acquisition_note_independently():
    """acquisition_note.md states profit for 1 Apr - 30 Jun 2024 was 18,000,000.
    This recomputes that figure from in_pl_monthly.csv, which nobody hands us
    pre-summed - if these don't match, either the note or the monthly file is wrong."""
    in_map = load_account_map(DATA / "map_in.csv")
    monthly = load_in_pl_monthly(DATA / "in_pl_monthly.csv")
    pre, post, pre_sources, post_sources, unmapped = split_india_monthly_pl(monthly, in_map)
    assert not unmapped
    assert pre_acquisition_profit(pre) == Decimal("18000000")


def test_post_acquisition_months_are_h2_only():
    in_map = load_account_map(DATA / "map_in.csv")
    monthly = load_in_pl_monthly(DATA / "in_pl_monthly.csv")
    pre, post, pre_sources, post_sources, unmapped = split_india_monthly_pl(monthly, in_map)
    # revenue (group code 4100) should split 205,000,000 pre / 437,000,000 post
    assert pre["4100"] == Decimal("-205000000")  # credit-normal, debit-positive convention
    assert post["4100"] == Decimal("-437000000")


def test_sources_are_scoped_to_their_own_period():
    """A post-acquisition posting should only cite Jul-Dec rows - citing an Apr-Jun
    row as a source for a figure that excludes Apr-Jun would be wrong provenance,
    even though it wouldn't affect the number itself."""
    in_map = load_account_map(DATA / "map_in.csv")
    monthly = load_in_pl_monthly(DATA / "in_pl_monthly.csv")
    pre, post, pre_sources, post_sources, unmapped = split_india_monthly_pl(monthly, in_map)

    post_revenue_months = {s.detail for s in post_sources["4100"]}
    pre_revenue_months = {s.detail for s in pre_sources["4100"]}
    assert post_revenue_months == {"2024-07", "2024-08", "2024-09", "2024-10", "2024-11", "2024-12"}
    assert pre_revenue_months == {"2024-04", "2024-05", "2024-06"}
