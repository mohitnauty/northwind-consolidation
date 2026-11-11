"""Single entry point: `python -m northwind.main [--initials XX]`.

Runs the whole pipeline and writes every required file to /output. Nothing in
here computes a number - this module just wires the pieces together and
serialises the result.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from . import consolidate, control_figures as control_figures_module, statements, validate
from .fx import FxTable
from .io_loaders import load_fx_rates, load_group_coa

REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--initials", default="mk", help="your initials, for control_figures_<initials>.json")
    parser.add_argument("--data-dir", default=str(REPO_ROOT / "data"))
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "output"))
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    group_coa = load_group_coa(data_dir / "group_coa.csv")
    fx = FxTable(load_fx_rates(data_dir / "fx_rates.csv"))

    result = consolidate.run(data_dir)
    issues = list(result.issues)

    balance_sheet = statements.build_balance_sheet(result, group_coa)
    profit_and_loss = statements.build_profit_and_loss(result, group_coa)
    changes_in_equity = statements.build_changes_in_equity(result)
    consolidated_tb = statements.build_consolidated_tb(result, group_coa)
    eliminations = statements.build_eliminations(result)
    control_figures = control_figures_module.build_control_figures(result, balance_sheet, profit_and_loss, fx)

    issues += validate.check_net_assets_identity(result)
    issues += validate.check_balance_sheet_identity(balance_sheet)
    issue_dicts = statements.build_issues(issues)

    _write_csv(output_dir / "consolidated_tb.csv", consolidated_tb,
               ["account_code", "account_name", "amount_gbp", "source_rows"])
    _write_csv(output_dir / "eliminations.csv", eliminations,
               ["group_id", "description", "entity", "account", "amount_gbp", "source_rows"])
    _write_json(output_dir / "balance_sheet.json", balance_sheet)
    _write_json(output_dir / "profit_and_loss.json", profit_and_loss)
    _write_json(output_dir / "changes_in_equity.json", changes_in_equity)
    _write_json(output_dir / "issues.json", issue_dicts)
    _write_json(output_dir / f"control_figures_{args.initials}.json", control_figures)

    print(f"wrote 7 files to {output_dir}")
    print(f"issues: {len(issue_dicts)} (see issues.json)")
    blocked = [i for i in issue_dicts if i["action"] == "blocked"]
    if blocked:
        print(f"{len(blocked)} blocked issue(s) - review before treating this as a clean run", file=sys.stderr)


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            row = dict(row)
            if isinstance(row.get("source_rows"), list):
                row["source_rows"] = " | ".join(row["source_rows"])
            writer.writerow(row)


def _write_json(path: Path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
        f.write("\n")


if __name__ == "__main__":
    main()
