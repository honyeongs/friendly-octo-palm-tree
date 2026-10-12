"""Re-run ten portfolio cases and optionally every regression/browser check."""
import argparse
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from tools.portfolio_cases import PROJECT
from tools.validation_support import make_report, markdown_report, run_checks, run_suite


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("portfolio", "all"), default="portfolio")
    parser.add_argument("--browser", action="store_true")
    parser.add_argument("--allow-postgres", action="store_true", help="Explicitly allow the configured dedicated test DB")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/local-validation.json")
    args = parser.parse_args()
    os.chdir(ROOT)
    if not args.allow_postgres:
        os.environ.pop("NETSEC_TEST_POSTGRES", None)
    started = datetime.now(timezone.utc).isoformat()
    loader = unittest.TestLoader()
    cases = PROJECT["cases"]
    if len(cases) != 10 or len({entry[1] for entry in cases}) != 10:
        raise ValueError("Exactly ten distinct portfolio test IDs are required")
    portfolio = run_suite(loader.loadTestsFromNames([entry[1] for entry in cases]))
    expected = {identifier: (f"P{index:02}", title) for index, (title, identifier) in enumerate(cases, 1)}
    for item in portfolio["tests"]:
        case_id, title = expected.get(item["test_id"], ("LOAD_ERROR", "Test could not be loaded"))
        item.update(case_id=case_id, title=title)
    regression = run_suite(unittest.TestLoader().discover(str(ROOT / "tests"), top_level_dir=str(ROOT))) if args.suite == "all" else None
    checks = run_checks(ROOT, PROJECT["checks"]) if args.browser else []
    data = make_report(ROOT, PROJECT, portfolio, regression, checks, started)
    import json
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents silently replacing evidence or overwriting any input.
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=True, indent=2, allow_nan=False)
        handle.write("\n")
    with args.output.with_suffix(".md").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(markdown_report(data))
    for name in ("portfolio", "regression"):
        if data[name]:
            print(name + ": " + json.dumps(data[name]["summary"], sort_keys=True))
    for check in checks:
        print(check["check_id"] + ": " + check["status"])
    suites = [portfolio] + ([regression] if regression else [])
    failed = any(suite["summary"][key] for suite in suites for key in ("failed", "error", "unexpected_success", "fixture_errors"))
    incomplete = portfolio["summary"]["total"] != 10 or portfolio["summary"]["passed"] != 10
    return int(failed or incomplete or any(check["status"] != "passed" for check in checks))


if __name__ == "__main__":
    raise SystemExit(main())

