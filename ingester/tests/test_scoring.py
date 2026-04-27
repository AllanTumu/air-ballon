"""Smoke tests for the scoring module — run with `python -m unittest`.

Kept dependency-free so it works in CI without extras.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir))

from scoring import score_hour  # noqa: E402


class ScoringTests(unittest.TestCase):
    def test_calm_morning_is_go(self):
        r = score_hour(dict(
            wind_speed_10m_kmh=4, wind_gusts_10m_kmh=8, wind_speed_80m_kmh=5,
            wind_dir_10m_deg=140, wind_dir_80m_deg=145,
            visibility_m=40000, precipitation_mm=0, cape_jkg=0,
            lifted_index=4, cloud_cover_low_pct=0, boundary_layer_m=200,
        ))
        self.assertEqual(r.verdict, "GO")
        self.assertGreater(r.score, 90)

    def test_high_wind_is_no_go(self):
        r = score_hour(dict(
            wind_speed_10m_kmh=22, wind_gusts_10m_kmh=35,
            wind_speed_80m_kmh=28, wind_dir_10m_deg=180, wind_dir_80m_deg=200,
            visibility_m=30000, precipitation_mm=0, cape_jkg=0,
            lifted_index=3, cloud_cover_low_pct=10, boundary_layer_m=400,
        ))
        self.assertEqual(r.verdict, "NO_GO")

    def test_fog_is_no_go(self):
        r = score_hour(dict(
            wind_speed_10m_kmh=2, wind_gusts_10m_kmh=4, wind_speed_80m_kmh=3,
            wind_dir_10m_deg=10, wind_dir_80m_deg=20,
            visibility_m=1500, precipitation_mm=0, cape_jkg=0,
            lifted_index=5, cloud_cover_low_pct=95, boundary_layer_m=20,
        ))
        self.assertEqual(r.verdict, "NO_GO")

    def test_storm_is_no_go(self):
        r = score_hour(dict(
            wind_speed_10m_kmh=8, wind_gusts_10m_kmh=14, wind_speed_80m_kmh=10,
            wind_dir_10m_deg=200, wind_dir_80m_deg=210,
            visibility_m=8000, precipitation_mm=2.0, cape_jkg=900,
            lifted_index=-3, cloud_cover_low_pct=80, boundary_layer_m=300,
        ))
        self.assertEqual(r.verdict, "NO_GO")

    def test_marginal_wind(self):
        r = score_hour(dict(
            wind_speed_10m_kmh=14, wind_gusts_10m_kmh=20, wind_speed_80m_kmh=16,
            wind_dir_10m_deg=140, wind_dir_80m_deg=150,
            visibility_m=20000, precipitation_mm=0, cape_jkg=50,
            lifted_index=2, cloud_cover_low_pct=20, boundary_layer_m=300,
        ))
        self.assertIn(r.verdict, {"MARGINAL", "GO"})  # depending on exact thresholds
        self.assertLess(r.score, 80)

    def test_missing_fields_dont_crash(self):
        r = score_hour({})
        self.assertIsNotNone(r.verdict)
        self.assertEqual(r.score, 100.0)


if __name__ == "__main__":
    unittest.main()
