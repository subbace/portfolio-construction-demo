"""Run only the small demo and its tests; retain actual outcomes and timings."""
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def public_log(value):
    """Retain diagnostics while removing local repository/interpreter prefixes."""
    for path, label in ((ROOT, "[repository]"), (Path(sys.prefix), "[python-environment]")):
        value = value.replace(str(path), label).replace(path.as_posix(), label)
    return value


def main():
    steps = []
    commands = [
        ["-m", "unittest", "discover", "-s", "tests", "-v"],
        ["src/portfolio_demo.py", "--output", "outputs"],
    ]
    for arguments in commands:
        started = time.perf_counter()
        result = subprocess.run([sys.executable] + arguments, cwd=str(ROOT),
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        elapsed = time.perf_counter() - started
        step = {"command": "python " + " ".join(arguments), "exit_code": result.returncode,
                "elapsed_seconds": elapsed,
                "stdout": public_log(result.stdout),
                "stderr": public_log(result.stderr)}
        steps.append(step)
        print("{} -> exit {} ({:.3f}s)".format(step["command"], result.returncode, elapsed))
        if result.returncode:
            break
    count_match = re.search(r"Ran (\d+) tests?", steps[0]["stderr"]) if steps else None
    record = {
        "status": "PASS" if len(steps) == 2 and all(step["exit_code"] == 0 for step in steps) else "FAIL",
        "environment": {"python": platform.python_version(),
                        "numpy": importlib.metadata.version("numpy"),
                        "matplotlib": importlib.metadata.version("matplotlib"),
                        "platform": platform.system()},
        "timing_scope": "Elapsed wall time of each subprocess, including import/startup; not CPU or a benchmark.",
        "tests_reported": int(count_match.group(1)) if count_match else None,
        "warnings_observed": any("warning" in step["stderr"].lower() for step in steps),
        "steps": steps,
    }
    output = ROOT / "outputs"
    output.mkdir(exist_ok=True)
    (output / "validation_run.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    summary_path = output / "summary.json"
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["validation"] = record
        summary_path.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = ["# Validation record", "", "This file records an actual local run; it is not a claim about a clean installation.", "",
             "Status: **{}**".format(record["status"]), "",
             "Tests reported: {}. Warnings observed: {}. Consult the retained diagnostic log.".format(record["tests_reported"], record["warnings_observed"]), "",
             "Environment: Python {python}, NumPy {numpy}, matplotlib {matplotlib}; {platform}.".format(**record["environment"]), "",
             record["timing_scope"], "", "| Command | Exit code | Wall seconds |", "|---|---:|---:|"]
    for step in steps:
        lines.append("| `{}` | {} | {:.6f} |".format(step["command"], step["exit_code"], step["elapsed_seconds"]))
    lines.extend(["", "Commands ran from the repository root using the same Python executable as the validation runner.", "",
                  "Actual stdout/stderr, including any observed failures, are retained in `outputs/validation_run.json` and `outputs/summary.json`.", "",
                  "Local filesystem prefixes are replaced by `[repository]` and `[python-environment]`; diagnostic content is retained.", "",
                  "No market download, credentials, paid API, model training or internship data was used.", "",
                  "Numerical tolerances: manual accounting/fee cases absolute 1e-12; first-loss drawdown 1e-14. Exact input reproducibility is checked within this pinned environment.", "",
                  "Reproduction on another platform: compare return/risk metrics with absolute tolerance 1e-10; PNG byte hashes and subprocess timing need not match.", ""])
    (ROOT / "VALIDATION.md").write_text("\n".join(lines), encoding="utf-8")
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
