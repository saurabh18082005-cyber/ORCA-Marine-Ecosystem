"""Tests for data_sources.py using tiny generated datasets."""

import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import xarray as xr

from agents.ocean_agent.data_sources import IRSP4OCMClient, INCOISOceansat2OCMERDDAPClient, _mock_reading


class TestMockFallback(unittest.TestCase):
    def test_mock_reading_has_expected_shape(self):
        reading = _mock_reading(value=1.0)
        reading["note"] = "test reason"
        self.assertIn("value", reading)
        self.assertIn("unit", reading)
        self.assertEqual(reading["status"], "mocked")
        self.assertEqual(reading["note"], "test reason")


class TestIRSP4OCMClient(unittest.TestCase):
    def _make_dataset(self, path: Path):
        ds = xr.Dataset(
            {
                "chlorophyll": (("time", "lat", "lon"), np.array([[[0.2, 0.4], [0.6, 0.8]]]))
            },
            coords={
                "time": np.array(["2000-01-01"], dtype="datetime64[ns]"),
                "lat": [10.0, 11.0],
                "lon": [70.0, 71.0],
            },
        )
        ds["chlorophyll"].attrs["units"] = "mg/m^3"
        ds.to_netcdf(path)

    def test_reads_nearest_chlorophyll_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "small_ocm_subset.nc"
            self._make_dataset(path)
            client = IRSP4OCMClient(str(path))
            result = client.get_chlorophyll(10.1, 70.9, "2000-01-01")
            self.assertEqual(result["status"], "ok")
            self.assertAlmostEqual(result["value"], 0.4)
            self.assertEqual(result["unit"], "mg/m^3")

    def test_inspection_returns_schema_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "small_ocm_subset.nc"
            self._make_dataset(path)
            metadata = IRSP4OCMClient(str(path)).inspect_dataset()
            self.assertIn("chlorophyll", metadata["variables"])
            self.assertIn("lat", metadata["coordinates"])

    def test_missing_file_falls_back(self):
        result = IRSP4OCMClient("/definitely/missing/file.nc").get_chlorophyll(10.0, 70.0)
        self.assertEqual(result["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()


class TestINCOISOceansat2OCMERDDAPClient(unittest.TestCase):
    def test_parses_public_erddap_response(self):
        import unittest.mock as mock

        payload = {
            "table": {
                "columnNames": ["time", "latitude", "longitude", "CHL"],
                "rows": [["2026-09-28T00:00:00Z", 10.0, 70.0, 0.8], ["2026-09-28T00:00:00Z", 10.04, 70.04, 0.5]],
            }
        }
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        with mock.patch("agents.ocean_agent.data_sources.requests.get", return_value=response) as get:
            result = INCOISOceansat2OCMERDDAPClient().get_chlorophyll(10.03, 70.03)
        self.assertEqual(result["status"], "ok")
        self.assertAlmostEqual(result["value"], 0.5)
        self.assertEqual(result["source"], "INCOIS ERDDAP:incois_oceansat2_datasets")
        self.assertIn("CHL", get.call_args.kwargs["params"])
        self.assertIn("(last)", get.call_args.kwargs["params"]["CHL"])
