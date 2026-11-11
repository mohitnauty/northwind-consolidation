from decimal import Decimal

from northwind.io_loaders import UkRawRow
from northwind.mapping import map_uk
from northwind.model import SourceRef

GROUP_COA = {
    "2300": {"account_name": "Deferred income", "account_type": "Liability", "statement": "BS"},
    "4100": {"account_name": "Revenue", "account_type": "Revenue", "statement": "PL"},
}
UK_MAP = {"2310": "4100", "4000": "4100"}  # map_uk.csv really does send 2310 to 4100


def test_deferred_income_is_rerouted_away_from_revenue():
    rows = [
        UkRawRow("2310", "Deferred income", "", "GBP", None, Decimal("-180000.00"),
                 SourceRef("tb_uk.csv", "11", "Deferred income")),
        UkRawRow("4000", "Sales", "", "GBP", None, Decimal("-9850000.00"),
                 SourceRef("tb_uk.csv", "15", "Sales")),
    ]
    mapped, issues = map_uk(rows, UK_MAP, GROUP_COA)

    deferred = next(m for m in mapped if m.local_code == "2310")
    assert deferred.group_code == "2300"  # rerouted, not the stated 4100
    sales = next(m for m in mapped if m.local_code == "4000")
    assert sales.group_code == "4100"  # genuine revenue is untouched

    assert any("2310" in i.description and "rerouted" in i.description for i in issues)
