import csv
from dataclasses import replace
from datetime import date
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import portfolio_demo as demo


class PortfolioDemoTests(unittest.TestCase):
    def test_seed_reproduces_dates_and_values_exactly(self):
        first_dates, first = demo.synthetic_data(demo.Config())
        second_dates, second = demo.synthetic_data(demo.Config())
        self.assertEqual(first_dates, second_dates)
        np.testing.assert_array_equal(first, second)
        self.assertEqual(first.shape, (756, 4))
        self.assertTrue(all(left < right for left, right in zip(first_dates, first_dates[1:])))

    def test_full_investment_grid_and_constraints(self):
        rows = demo.screen_candidates(demo.Config())
        # Integer compositions of ten units into four parts: C(13,3) = 286.
        self.assertEqual(len(rows), 286)
        self.assertEqual(len({row["candidate_id"] for row in rows}), 286)
        for row in rows:
            self.assertAlmostEqual(float(row["weights"].sum()), 1.0)
        self.assertTrue(any(not row["feasible"] for row in rows))
        feasible = [row["weights"] for row in rows if row["feasible"]]
        self.assertTrue(feasible)
        for weights in feasible:
            self.assertGreaterEqual(float(weights.min()), 0.10 - 1e-12)
            self.assertLessEqual(float(weights.max()), 0.60 + 1e-12)
            self.assertLessEqual(float(weights[:2].sum()), 0.70 + 1e-12)

    def test_infeasible_constraints_fail_without_relaxation(self):
        config = replace(demo.Config(), maximum_weight=0.20)
        with self.assertRaisesRegex(ValueError, "No feasible"):
            demo.screen_candidates(config)

    def test_drawdown_includes_first_day_loss_from_initial_cash(self):
        result = demo.metrics([100.0, 80.0, 88.0])
        self.assertAlmostEqual(result["maximum_drawdown"], -0.20, places=14)
        self.assertAlmostEqual(result["total_return"], -0.12, places=14)
        self.assertAlmostEqual(result["daily_es95_loss"], 0.20, places=14)

    def test_fractional_expected_shortfall_manual_examples(self):
        self.assertAlmostEqual(demo.empirical_expected_shortfall([0.4, 0.2, 0.1], 0.5), 1.0 / 3.0)
        self.assertAlmostEqual(demo.empirical_expected_shortfall([0.1, 0.2, -0.1, -0.2], 0.5), 0.15)
        with self.assertRaises(ValueError):
            demo.empirical_expected_shortfall([0.1, float("nan")])

    def test_annual_rebalance_matches_hand_calculation(self):
        dates = [date(2020, 12, 31), date(2021, 1, 4), date(2021, 1, 5)]
        returns = np.array([[1.0, 0.0], [0.0, 0.0], [0.2, 0.0]])
        result = demo.portfolio_path(dates, returns, [0.5, 0.5],
                                     replace(demo.Config(), transaction_cost_bps=0))
        np.testing.assert_allclose(result["wealth"], [100, 150, 150, 165], rtol=0, atol=1e-12)

    def test_actual_traded_notional_fee_and_initial_entry(self):
        holdings, fee, gross = demo.rebalance(np.array([100.0, 50.0]), np.array([0.5, 0.5]), 0.01)
        np.testing.assert_allclose(holdings, [74.75, 74.75], rtol=0, atol=1e-12)
        self.assertAlmostEqual(fee, 0.5, places=12)
        self.assertAlmostEqual(gross, 50.0, places=12)
        config = replace(demo.Config(), transaction_cost_bps=10.0)
        result = demo.portfolio_path([date(2020, 1, 2), date(2020, 1, 3)],
                                     np.zeros((2, 4)), [0.25] * 4, config)
        self.assertAlmostEqual(result["wealth"][-1], 100.0 / 1.001, places=12)
        self.assertAlmostEqual(result["fees"][0], 0.001 * result["gross_traded"][0], places=12)
        self.assertEqual(result["fees"][1], 0.0)

    def test_future_tampering_cannot_change_selection_or_design_scores(self):
        config = demo.Config()
        dates, returns = demo.synthetic_data(config)
        original = demo.analyze(dates, returns, config)
        changed = returns.copy()
        # An intentionally disastrous future must be reported, never trigger a replacement.
        changed[config.design_days:] = -0.20
        altered = demo.analyze(dates, changed, config)
        self.assertEqual(original["selected"]["candidate_id"], altered["selected"]["candidate_id"])
        self.assertEqual([row["design_sharpe"] for row in original["ranked"]],
                         [row["design_sharpe"] for row in altered["ranked"]])
        self.assertLess(altered["splits"]["final"]["metrics"]["total_return"], -0.99)

    def test_selection_called_once_with_design_rows_only(self):
        config = demo.Config()
        dates, returns = demo.synthetic_data(config)
        with mock.patch.object(demo, "select_on_design", wraps=demo.select_on_design) as selector:
            result = demo.analyze(dates, returns, config)
        selector.assert_called_once()
        selected_dates, selected_returns = selector.call_args.args[:2]
        self.assertEqual(len(selected_dates), config.design_days)
        self.assertEqual(selected_returns.shape, (config.design_days, 4))
        self.assertLess(result["splits"]["design"]["end"], result["splits"]["validation"]["start"])
        self.assertLess(result["splits"]["validation"]["end"], result["splits"]["final"]["start"])

    def test_invalid_dates_and_returns_are_rejected(self):
        dates, returns = demo.synthetic_data(demo.Config())
        dates[1] = dates[0]
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            demo.analyze(dates, returns, demo.Config())
        with self.assertRaisesRegex(ValueError, "Invalid return"):
            demo.portfolio_path([date(2020, 1, 2), date(2020, 1, 3)],
                                 np.array([[-1.0, 0], [0, 0]]), [0.5, 0.5], demo.Config())

    def test_smoke_exports_parseable_artifacts_and_matching_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            result = demo.export(output, demo.Config())
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["selected_candidate_id"], result["selected_candidate_id"])
            self.assertEqual(summary["candidate_count_full_investment_grid"], 286)
            self.assertEqual(summary["data_role"], "SYNTHETIC_ILLUSTRATION_ONLY")
            for name, expected in summary["output_sha256"].items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), expected)
            with (output / "metrics.csv").open(encoding="utf-8", newline="") as handle:
                self.assertEqual([row["split"] for row in csv.DictReader(handle)],
                                 ["design", "validation", "final"])
            self.assertEqual((output / "portfolio_overview.png").read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
