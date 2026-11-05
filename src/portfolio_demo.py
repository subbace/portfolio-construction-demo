"""Small, independently written portfolio experiment using synthetic data only."""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import date, timedelta
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Sequence

import numpy as np

ASSETS = ("Asset A", "Asset B", "Asset C", "Asset D")
ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Config:
    seed: int = 20261105
    design_days: int = 378
    validation_days: int = 189
    final_days: int = 189
    grid_units: int = 10
    minimum_weight: float = 0.10
    maximum_weight: float = 0.60
    first_pair_maximum: float = 0.70
    transaction_cost_bps: float = 5.0
    initial_wealth: float = 100.0
    annualization: int = 252

    def validate(self) -> None:
        if min(self.design_days, self.validation_days, self.final_days) < 2:
            raise ValueError("Each chronological split needs at least two days.")
        if self.grid_units < 1 or not isinstance(self.grid_units, int):
            raise ValueError("grid_units must be a positive integer.")
        if not 0 <= self.minimum_weight <= self.maximum_weight <= 1:
            raise ValueError("Invalid long-only weight bounds.")
        if not 0 <= self.first_pair_maximum <= 1:
            raise ValueError("Invalid first-pair constraint.")
        if not 0 <= self.transaction_cost_bps < 10000:
            raise ValueError("Transaction cost rate must be in [0, 100%).")
        if self.initial_wealth <= 0 or self.annualization < 1:
            raise ValueError("Initial wealth and annualization must be positive.")


def business_dates(count: int) -> list:
    current = date(2020, 1, 2)
    result = []
    while len(result) < count:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return result


def synthetic_data(config: Config) -> tuple:
    """Abstract correlated simple returns, without market downloads or tickers."""
    config.validate()
    count = config.design_days + config.validation_days + config.final_days
    rng = np.random.default_rng(config.seed)
    common = rng.standard_normal((count, 1))
    specific = rng.standard_normal((count, 4))
    # Fixed constants are illustration assumptions, never estimated from splits.
    loading = np.array([0.72, 0.55, 0.15, -0.10])
    daily_vol = np.array([0.012, 0.009, 0.004, 0.006])
    daily_mean = np.array([0.00025, 0.00018, 0.00007, 0.00010])
    shocks = common * loading + specific * np.sqrt(1.0 - loading ** 2)
    returns = daily_mean + daily_vol * shocks
    return business_dates(count), returns


def screen_candidates(config: Config) -> list:
    """Enumerate a finite full-investment grid and retain rejection reasons."""
    config.validate()
    candidates = []
    for units in itertools.product(range(config.grid_units + 1), repeat=4):
        if sum(units) != config.grid_units:
            continue
        weights = np.array(units, dtype=float) / config.grid_units
        reasons = []
        if np.any(weights < config.minimum_weight - 1e-12):
            reasons.append("below_minimum")
        if np.any(weights > config.maximum_weight + 1e-12):
            reasons.append("above_maximum")
        if weights[:2].sum() > config.first_pair_maximum + 1e-12:
            reasons.append("first_pair_limit")
        candidates.append({
            "candidate_id": "W_" + "_".join(str(value) for value in units),
            "weights": weights,
            "feasible": not reasons,
            "rejection_reason": "|".join(reasons),
        })
    if not any(candidate["feasible"] for candidate in candidates):
        raise ValueError("No feasible allocation on the declared grid.")
    return candidates


def empirical_expected_shortfall(losses: Sequence[float], level: float = 0.95) -> float:
    """Average exactly (1-level) of empirical mass, fractionally at the boundary."""
    values = np.sort(np.asarray(losses, dtype=float))[::-1]
    if values.ndim != 1 or not len(values) or not np.all(np.isfinite(values)):
        raise ValueError("Expected Shortfall needs finite one-dimensional losses.")
    if not 0 < level < 1:
        raise ValueError("Expected Shortfall level must be between zero and one.")
    mass = len(values) * (1.0 - level)
    whole = int(math.floor(mass))
    fraction = mass - whole
    total = float(values[:whole].sum())
    if fraction > 0:
        total += fraction * values[whole]
    return total / mass


def metrics(wealth: Sequence[float], annualization: int = 252) -> dict:
    """wealth[0] is the initial capital, so the first loss enters drawdown."""
    values = np.asarray(wealth, dtype=float)
    if (values.ndim != 1 or len(values) < 3 or
            not np.all(np.isfinite(values)) or np.any(values <= 0)):
        raise ValueError("Metrics need initial capital and at least two positive observations.")
    daily = values[1:] / values[:-1] - 1.0
    volatility = float(np.std(daily, ddof=1) * math.sqrt(annualization))
    annual_mean = float(np.mean(daily) * annualization)
    losses = -daily
    result = {
        "observations": len(daily),
        "total_return": float(values[-1] / values[0] - 1.0),
        "cagr_252_day": float((values[-1] / values[0]) ** (annualization / len(daily)) - 1.0),
        "annualized_mean_return": annual_mean,
        "annualized_volatility": volatility,
        "sharpe_zero_risk_free": annual_mean / volatility if volatility > 0 else None,
        "maximum_drawdown": float(np.min(values / np.maximum.accumulate(values) - 1.0)),
        "daily_var95_loss": float(np.quantile(losses, 0.95, method="linear")),
        "daily_es95_loss": empirical_expected_shortfall(losses),
        "terminal_wealth": float(values[-1]),
    }
    return result


def rebalance(holdings: np.ndarray, weights: np.ndarray, rate: float) -> tuple:
    """Solve fee = rate * sum(abs(post-fee target holdings - old holdings))."""
    value = float(holdings.sum())
    lower, upper = 0.0, value * rate
    # A fully invested rebalance trades at most twice total pre-fee capital.
    upper = min(value * 2.0 * rate, value)
    for _ in range(64):
        fee = (lower + upper) / 2.0
        gross_traded = float(np.abs((value - fee) * weights - holdings).sum())
        if fee < rate * gross_traded:
            lower = fee
        else:
            upper = fee
    fee = (lower + upper) / 2.0
    target = (value - fee) * weights
    traded = float(np.abs(target - holdings).sum())
    return target, fee, traded


def portfolio_path(dates: Sequence[date], returns: np.ndarray, weights: Sequence[float],
                   config: Config) -> dict:
    """Fresh cash endowment per split; rebalance before each new calendar year."""
    array = np.asarray(returns, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if (array.ndim != 2 or array.shape != (len(dates), len(weights)) or
            len(dates) < 2 or not np.all(np.isfinite(array)) or np.any(array <= -1)):
        raise ValueError("Invalid return matrix.")
    if not np.all(np.isfinite(weights)) or np.any(weights < 0) or not np.isclose(weights.sum(), 1):
        raise ValueError("Weights must be finite, long-only and sum to one.")
    rate = config.transaction_cost_bps / 10000.0
    # Exact initial buying cost: invested + rate * invested = initial cash.
    invested = config.initial_wealth / (1.0 + rate)
    holdings = invested * weights
    wealth = [config.initial_wealth]
    fees, trades = [], []
    for position, current_date in enumerate(dates):
        fee = config.initial_wealth - invested if position == 0 else 0.0
        traded = invested if position == 0 else 0.0
        if position and current_date.year != dates[position - 1].year:
            holdings, fee, traded = rebalance(holdings, weights, rate)
        holdings = holdings * (1.0 + array[position])
        wealth.append(float(holdings.sum()))
        fees.append(fee)
        trades.append(traded)
    return {"wealth": np.array(wealth), "fees": np.array(fees), "gross_traded": np.array(trades)}


def select_on_design(dates: Sequence[date], returns: np.ndarray,
                     candidates: list, config: Config) -> tuple:
    """This boundary accepts design data only. No fallback uses later splits."""
    ranked = []
    for candidate in candidates:
        if not candidate["feasible"]:
            continue
        path = portfolio_path(dates, returns, candidate["weights"], config)
        score = metrics(path["wealth"], config.annualization)["sharpe_zero_risk_free"]
        if score is None or not math.isfinite(score):
            raise ValueError("Undefined design score; selection stops without a fallback.")
        ranked.append({**candidate, "design_sharpe": score})
    if not ranked:
        raise ValueError("No feasible design candidate.")
    ranked.sort(key=lambda row: (-row["design_sharpe"], row["candidate_id"]))
    return ranked[0], ranked


def analyze(dates: Sequence[date], returns: np.ndarray, config: Config) -> dict:
    config.validate()
    expected = config.design_days + config.validation_days + config.final_days
    if len(dates) != expected or len(returns) != expected:
        raise ValueError("Input length differs from the declared chronological split.")
    if any(left >= right for left, right in zip(dates, dates[1:])):
        raise ValueError("Dates must be strictly increasing and unique.")
    boundaries = (0, config.design_days, config.design_days + config.validation_days, expected)
    slices = {name: slice(boundaries[i], boundaries[i + 1])
              for i, name in enumerate(("design", "validation", "final"))}
    candidates = screen_candidates(config)
    design = slices["design"]
    selected, ranked = select_on_design(dates[design], returns[design], candidates, config)
    split_results = {}
    for name, span in slices.items():
        path = portfolio_path(dates[span], returns[span], selected["weights"], config)
        split_results[name] = {
            "start": dates[span][0].isoformat(), "end": dates[span][-1].isoformat(),
            "metrics": metrics(path["wealth"], config.annualization),
            "total_cost_paid": float(path["fees"].sum()),
            "gross_traded_notional": float(path["gross_traded"].sum()),
            "path": path, "dates": dates[span],
        }
    return {"selected": selected, "ranked": ranked, "candidates": candidates, "splits": split_results}


def write_csv(path: Path, fields: list, rows: list) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(output: Path, config: Config) -> dict:
    dates, returns = synthetic_data(config)
    experiment = analyze(dates, returns, config)
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "synthetic_returns.csv", ["date"] + list(ASSETS), [
        {"date": day.isoformat(), **dict(zip(ASSETS, row))} for day, row in zip(dates, returns)])
    scores = {row["candidate_id"]: row["design_sharpe"] for row in experiment["ranked"]}
    write_csv(output / "candidate_screening.csv",
              ["candidate_id"] + list(ASSETS) + ["feasible", "rejection_reason", "design_sharpe"], [
        {"candidate_id": row["candidate_id"], **dict(zip(ASSETS, row["weights"])),
         "feasible": row["feasible"], "rejection_reason": row["rejection_reason"],
         "design_sharpe": scores.get(row["candidate_id"], "")}
        for row in experiment["candidates"]])
    metric_rows, path_rows = [], []
    for name, split in experiment["splits"].items():
        metric_rows.append({"split": name, **split["metrics"], "total_cost_paid": split["total_cost_paid"]})
        path = split["path"]
        path_rows.append({"split": name, "date": "INITIAL", "wealth": config.initial_wealth,
                          "net_return": 0, "cost_paid": 0, "gross_traded": 0})
        for position, day in enumerate(split["dates"]):
            path_rows.append({"split": name, "date": day.isoformat(),
                              "wealth": path["wealth"][position + 1],
                              "net_return": path["wealth"][position + 1] / path["wealth"][position] - 1,
                              "cost_paid": path["fees"][position], "gross_traded": path["gross_traded"][position]})
    write_csv(output / "metrics.csv", list(metric_rows[0]), metric_rows)
    write_csv(output / "selected_portfolio_daily.csv", list(path_rows[0]), path_rows)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), gridspec_kw={"width_ratios": [1.7, 1]})
    colors = ("#255b67", "#c17d3c", "#6e7583")
    for (name, split), color in zip(experiment["splits"].items(), colors):
        axes[0].plot(split["path"]["wealth"], label=name.title(), color=color)
    axes[0].axhline(config.initial_wealth, color="#a0a0a0", linewidth=0.7)
    axes[0].set(xlabel="Observation within split", ylabel="Wealth (initial cash = 100)",
                title="Same frozen allocation; separate cash endowment per split")
    axes[0].legend(frameon=False)
    axes[0].grid(alpha=0.15)
    axes[1].bar(ASSETS, experiment["selected"]["weights"], color="#255b67")
    axes[1].set(ylabel="Selected weight", ylim=(0, 0.65), title="Selected on design data only")
    fig.suptitle("Portfolio construction | synthetic illustration, after declared costs", fontsize=12)
    fig.tight_layout()
    fig.savefig(output / "portfolio_overview.png", dpi=150, metadata={"Software": "portfolio-construction-demo"})
    plt.close(fig)
    summary = {
        "schema_version": 1,
        "data_role": "SYNTHETIC_ILLUSTRATION_ONLY",
        "config": asdict(config),
        "candidate_count_full_investment_grid": len(experiment["candidates"]),
        "candidate_count_feasible": len(experiment["ranked"]),
        "selected_candidate_id": experiment["selected"]["candidate_id"],
        "selected_weights": dict(zip(ASSETS, experiment["selected"]["weights"].tolist())),
        "selection_rule": "Maximum design-only net Sharpe; candidate_id lexical tie-break. Select once; no fallback.",
        "split_policy": "Chronological nonoverlapping 378/189/189; each starts from fresh cash; later splits never select weights.",
        "transaction_cost_policy": "5 basis points of actual gross buy+sell notional at initial entry and annual rebalance; solved including fees.",
        "splits": {name: {key: value for key, value in split.items() if key not in ("path", "dates")}
                   for name, split in experiment["splits"].items()},
        "limitations": ["Artificial data do not validate a market strategy or forecast returns.",
                        "Finite-grid optimum is conditional on fixed design assumptions, not a continuous global optimum.",
                        "5bps is a scenario assumption; no spread, market impact, tax, funding or empirical fee calibration.",
                        "The original internship project and its 65,807 candidates are not replicated or included.",
                        "No uncertainty interval, multiple-testing adjustment or economic superiority claim."],
        "source_sha256": {name: sha256(ROOT / name) for name in
                          ("src/portfolio_demo.py", "tests/test_portfolio_demo.py", "requirements.txt")},
        "output_sha256": {path.name: sha256(path) for path in sorted(output.iterdir())
                          if path.name in ("synthetic_returns.csv", "candidate_screening.csv", "metrics.csv",
                                           "selected_portfolio_daily.csv", "portfolio_overview.png")},
        "validation": {"status": "NOT_RECORDED_BY_THIS_INVOCATION",
                       "instruction": "Run python tools/validate.py to record actual tests and demo exit codes."},
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    summary = export(args.output, Config())
    print(json.dumps({"selected_candidate_id": summary["selected_candidate_id"],
                      "feasible_candidates": summary["candidate_count_feasible"],
                      "data_role": summary["data_role"]}, sort_keys=True))


if __name__ == "__main__":
    main()
