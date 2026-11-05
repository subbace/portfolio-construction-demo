# Validation record

This file records an actual local run; it is not a claim about a clean installation.

Status: **PASS**

Tests reported: 11. Warnings observed: True. The existing environment emitted matplotlib/pyparsing deprecation warnings; all tests and the CLI exited zero.

Environment: Python 3.9.1, NumPy 2.0.2, matplotlib 3.9.4; Windows.

Elapsed wall time of each subprocess, including import/startup; not CPU or a benchmark.

| Command | Exit code | Wall seconds |
|---|---:|---:|
| `python -m unittest discover -s tests -v` | 0 | 5.366075 |
| `python src/portfolio_demo.py --output outputs` | 0 | 2.432485 |

Commands ran from the repository root using the same Python executable as the validation runner.

Actual stdout/stderr, including any observed failures, are retained in `outputs/validation_run.json` and `outputs/summary.json`.

No market download, credentials, paid API, model training or internship data was used.

Numerical tolerances: manual accounting/fee cases absolute 1e-12; first-loss drawdown 1e-14. Exact input reproducibility is checked within this pinned environment.

Reproduction on another platform: compare return/risk metrics with absolute tolerance 1e-10; PNG byte hashes and subprocess timing need not match.

Local filesystem prefixes in the retained diagnostic logs are replaced by `[repository]` and `[python-environment]`; warning content is retained. The first successful scientific test/demo run was reused after documentation and log-sanitization changes.


## Clean independent environment validation

A fresh local Git clone was verified byte-for-byte and the README commands were executed in a new isolated **CPython 3.12.14 / Windows / CPU** environment. Installation, checks and examples all exited **0**. The exact commands, versions, installed distributions and wall times are in [validation/CLEAN_ENVIRONMENT.json](validation/CLEAN_ENVIRONMENT.json). Other operating systems are not tested. Timing is engineering evidence, not an economic or algorithmic speed claim.

Recorded passing counts: unit_tests_passed = 11. These counts describe tests, not project completion or investment effectiveness.

The initial packaging check found Git line-ending conversion before any tests ran. Its clone was preserved and the source bytes were restored through a separate checkout with explicit `.gitattributes`; no source guard or test was removed.
