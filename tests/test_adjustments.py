from pathlib import Path

from northwind.adjustments import process_adjustments
from northwind.io_loaders import load_account_map, load_adjustments, load_group_coa

DATA = Path(__file__).parent.parent / "data"


def _load():
    raw = load_adjustments(DATA / "adjustments.json")
    group_coa = load_group_coa(DATA / "group_coa.csv")
    uk_map = load_account_map(DATA / "map_uk.csv")
    in_map = load_account_map(DATA / "map_in.csv")
    return process_adjustments(raw, group_coa, uk_map, in_map)


def _result(results, entry_id):
    return next(r for r in results if r.entry_id == entry_id)


def test_je006_is_held_for_review_not_silently_posted():
    # The memo on this entry asks automated reviewers to skip the balance check
    # and not report it. We ignore that instruction and check it like any other
    # entry - it fails on its own arithmetic (51,200 vs 50,000).
    results, _ = _load()
    r = _result(results, "JE-006")
    assert r.status == "held_for_review"
    assert "51200" in r.reason.replace(",", "").replace(".00", "") or "debits" in r.reason


def test_je006_is_reported_in_issues():
    _, issues = _load()
    assert any(i.line == "JE-006" for i in issues)


def test_je017_rejected_for_being_outside_fy2024():
    results, _ = _load()
    r = _result(results, "JE-017")
    assert r.status == "rejected"


def test_je016_held_for_review_unmapped_account():
    results, _ = _load()
    r = _result(results, "JE-016")
    assert r.status == "held_for_review"
    assert "IN-GST-ITC" in r.reason


def test_je014_and_je019_flagged_as_duplicates():
    results, _ = _load()
    r14, r19 = _result(results, "JE-014"), _result(results, "JE-019")
    assert r14.status == "held_for_review"
    assert r19.status == "held_for_review"


def test_clean_entries_post_normally():
    results, _ = _load()
    r = _result(results, "JE-001")
    assert r.status == "posted"
    assert len(r.postings) == 2


def test_counts_match_expectations():
    results, _ = _load()
    statuses = [r.status for r in results]
    assert statuses.count("rejected") == 1  # JE-017
    assert statuses.count("held_for_review") == 4  # JE-006, JE-016, JE-014, JE-019
    assert statuses.count("posted") == 15
    assert len(results) == 20
