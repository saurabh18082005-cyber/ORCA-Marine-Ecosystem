"""
Data source client for the Ocean/Chlorophyll Agent.

Primary source: IRS-P4 OCM (Oceansat-1 Ocean Colour Monitor) chlorophyll data.
The task explicitly asks us to avoid downloading huge unnecessary portions of
the dataset, so this module does NOT automatically download a global archive.
Instead it opens a local NetCDF/HDF dataset path supplied through:

    OCEAN_AGENT_DATASET_PATH=/path/to/subset.nc

Development workflow:
  1. Obtain a small geographical/time subset of the approved dataset.
  2. Save it locally (or mount it in the project data directory).
  3. Point OCEAN_AGENT_DATASET_PATH to that file.
  4. The client detects common coordinate/variable names and retrieves the
     nearest valid chlorophyll grid cell.

The exact variable names in the team's chosen IRS-P4 OCM file must be checked
against that file's metadata. Common aliases are supported, but no scientific
conversion or threshold is invented here.

Every request fails soft. If a dataset is unavailable or a query cannot be
resolved, a clearly flagged mocked reading can be returned for UI/demo pipeline
continuity. Set OCEAN_AGENT_ALLOW_MOCK=false to surface real errors instead.
"""

from __future__ import annotations

import logging
import os
import random
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("ocean_agent.data_sources")

ALLOW_MOCK_FALLBACK = os.environ.get("OCEAN_AGENT_ALLOW_MOCK", "false").lower() != "false"
DEFAULT_DATASET_PATH = os.environ.get("OCEAN_AGENT_DATASET_PATH")
INCOIS_ERDDAP_BASE_URL = os.environ.get(
    "INCOIS_ERDDAP_BASE_URL", "https://erddap.incois.gov.in/erddap"
).rstrip("/")
INCOIS_OCM_DATASET_ID = os.environ.get(
    "INCOIS_OCM_DATASET_ID", "incois_oceansat2_datasets"
)

# Aliases allow the first version to work with common scientific file naming
# conventions while remaining explicit about what was actually found.
CHLOROPHYLL_VARIABLE_ALIASES = [
    "chlorophyll", "chlor_a", "chl_a", "chl", "chla", "chlorophyll_a",
]
LATITUDE_ALIASES = ["lat", "latitude", "Latitude"]
LONGITUDE_ALIASES = ["lon", "longitude", "Longitude"]
TIME_ALIASES = ["time", "Time", "date", "datetime"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _find_name(candidates, available) -> Optional[str]:
    available_set = set(available)
    for name in candidates:
        if name in available_set:
            return name
    return None


class IRSP4OCMClient:
    """Thin reader for a local, small IRS-P4 OCM chlorophyll subset."""

    def __init__(self, dataset_path: Optional[str] = None):
        self.dataset_path = dataset_path or DEFAULT_DATASET_PATH

    def inspect_dataset(self) -> Dict[str, Any]:
        """Return basic metadata without loading the whole dataset into memory."""
        ds = self._open_dataset()
        try:
            return {
                "variables": list(ds.data_vars),
                "coordinates": list(ds.coords),
                "dimensions": {name: int(size) for name, size in ds.sizes.items()},
                "source_path": str(self.dataset_path),
            }
        finally:
            ds.close()

    def get_chlorophyll(self, lat: float, lon: float, date: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve the nearest available chlorophyll observation."""
        try:
            ds = self._open_dataset()
            try:
                variable_name, lat_name, lon_name, time_name = self._resolve_schema(ds)
                selection = ds[variable_name].sel(
                    {lat_name: lat, lon_name: lon}, method="nearest"
                )

                if date and time_name and time_name in selection.dims:
                    selection = selection.sel({time_name: date}, method="nearest")
                elif time_name and time_name in selection.dims:
                    # Latest available time when caller does not specify one.
                    selection = selection.isel({time_name: -1})

                value = float(selection.values)
                if not self._is_valid_value(value):
                    raise ValueError("Selected chlorophyll value is missing, NaN, or invalid.")

                unit = selection.attrs.get("units") or ds[variable_name].attrs.get("units") or "mg/m^3"
                observed_at = self._selected_time(selection, time_name)
                grid_lat = self._selected_coordinate(selection, lat_name)
                grid_lon = self._selected_coordinate(selection, lon_name)

                return {
                    "value": value,
                    "unit": str(unit),
                    "source": f"IRS-P4-OCM:{Path(str(self.dataset_path)).name}",
                    "observed_at": observed_at,
                    "status": "ok",
                    "grid_lat": grid_lat,
                    "grid_lon": grid_lon,
                }
            finally:
                ds.close()
        except Exception as exc:  # intentionally broad: missing file/schema/query all fail soft
            logger.warning("IRS-P4 OCM chlorophyll fetch failed: %s", exc)
            return _unavailable_reading(reason=f"IRS-P4 OCM request failed: {exc}")

    def _open_dataset(self):
        if not self.dataset_path:
            raise FileNotFoundError(
                "No dataset path configured. Set OCEAN_AGENT_DATASET_PATH to a small IRS-P4 OCM subset."
            )
        path = Path(self.dataset_path)
        if not path.exists():
            raise FileNotFoundError(f"Dataset not found: {path}")

        import xarray as xr
        # xarray opens lazily; values are loaded only for the selected point.
        return xr.open_dataset(path)

    def _resolve_schema(self, ds):
        variable_name = _find_name(CHLOROPHYLL_VARIABLE_ALIASES, ds.data_vars)
        lat_name = _find_name(LATITUDE_ALIASES, ds.coords) or _find_name(LATITUDE_ALIASES, ds.variables)
        lon_name = _find_name(LONGITUDE_ALIASES, ds.coords) or _find_name(LONGITUDE_ALIASES, ds.variables)
        time_name = _find_name(TIME_ALIASES, ds.coords) or _find_name(TIME_ALIASES, ds.variables)

        missing = []
        if not variable_name:
            missing.append("chlorophyll variable")
        if not lat_name:
            missing.append("latitude coordinate")
        if not lon_name:
            missing.append("longitude coordinate")
        if missing:
            raise ValueError(
                "Dataset schema not recognized; missing " + ", ".join(missing) +
                f". Available variables: {list(ds.variables)}"
            )
        return variable_name, lat_name, lon_name, time_name

    @staticmethod
    def _is_valid_value(value: float) -> bool:
        return value == value and value >= 0  # rejects NaN and negative concentrations

    @staticmethod
    def _selected_coordinate(selection, name: str) -> Optional[float]:
        try:
            return float(selection.coords[name].values)
        except Exception:
            return None

    @staticmethod
    def _selected_time(selection, name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        try:
            value = selection.coords[name].values
            return str(value)
        except Exception:
            return None


class INCOISOceansat2OCMERDDAPClient:
    """Read the public INCOIS Oceansat-2 OCM dataset through ERDDAP.

    This is a public machine-readable INCOIS dataset and does not require an
    API key. Only a tiny spatial subset for the latest available time is
    requested, so ORCA never downloads the full archive.
    """

    def __init__(self, base_url: Optional[str] = None, dataset_id: Optional[str] = None, timeout: float = 15.0):
        self.base_url = (base_url or INCOIS_ERDDAP_BASE_URL).rstrip("/")
        self.dataset_id = dataset_id or INCOIS_OCM_DATASET_ID
        self.timeout = timeout

    def get_chlorophyll(self, lat: float, lon: float, date: Optional[str] = None) -> Dict[str, Any]:
        # Request a small 3x3-ish neighborhood around the query point. ERDDAP
        # supports (last) for the latest grid time; no fixed historical date is
        # embedded in the request.
        delta = 0.08
        time_selector = f"[({date})]" if date else "[(last)]"
        query = (
            f"CHL{time_selector}[({lat-delta}):({lat+delta})][({lon-delta}):({lon+delta})]"
        )
        url = f"{self.base_url}/griddap/{self.dataset_id}.json"
        try:
            response = requests.get(url, params={"CHL": query[len("CHL"): ]}, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            table = payload.get("table", {})
            columns = table.get("columnNames", [])
            rows = table.get("rows", [])
            if not rows:
                raise ValueError("INCOIS ERDDAP returned no chlorophyll rows for the requested location.")

            # Expected columns are time, latitude, longitude, CHL. Be tolerant
            # of column ordering while remaining explicit about the source.
            index = {str(name).lower(): i for i, name in enumerate(columns)}
            lat_i = index.get("latitude")
            lon_i = index.get("longitude")
            chl_i = index.get("chl")
            time_i = index.get("time")
            if lat_i is None or lon_i is None or chl_i is None:
                raise ValueError(f"Unexpected INCOIS ERDDAP response columns: {columns}")

            def distance(row):
                return ((float(row[lat_i]) - lat) ** 2 + (float(row[lon_i]) - lon) ** 2) ** 0.5

            row = min(rows, key=distance)
            value = float(row[chl_i])
            if not self._is_valid(value):
                raise ValueError("INCOIS returned a missing or invalid chlorophyll value.")

            observed_at = str(row[time_i]) if time_i is not None else None
            return {
                "value": value,
                "unit": "mg/m^3",
                "source": f"INCOIS ERDDAP:{self.dataset_id}",
                "observed_at": observed_at,
                "status": "ok",
                "grid_lat": float(row[lat_i]),
                "grid_lon": float(row[lon_i]),
            }
        except Exception as exc:
            logger.warning("INCOIS Oceansat-2 OCM ERDDAP fetch failed: %s", exc)
            return _unavailable_reading(reason=f"INCOIS ERDDAP request failed: {exc}")

    @staticmethod
    def _is_valid(value: float) -> bool:
        return value == value and value >= 0 and value < 1e20


class OpenMeteoMarineClient:
    """Client for Open-Meteo Marine API."""

    def __init__(self):
        self.base_url = "https://marine-api.open-meteo.com/v1/marine"

    def get_marine_data(self, lat: float, lon: float) -> Dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "wave_height,wave_direction,ocean_current_velocity,ocean_current_direction",
            "timezone": "auto"
        }
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.warning("Open-Meteo marine fetch failed: %s", e)
            return {"error": str(e)}


def _unavailable_reading(reason: str) -> Dict[str, Any]:
    if ALLOW_MOCK_FALLBACK:
        return {
            "value": round(random.uniform(0.1, 2.0), 3),
            "unit": "mg/m^3",
            "source": "mock-fallback",
            "observed_at": _utc_now_iso(),
            "status": "mocked",
            "note": reason,
            "grid_lat": None,
            "grid_lon": None,
        }
    return {
        "value": None,
        "unit": "mg/m^3",
        "source": "unknown",
        "observed_at": None,
        "status": "unavailable",
        "note": reason,
        "grid_lat": None,
        "grid_lon": None,
    }



# Backwards-compatible test/demo helper used by the repository test suite.
def _mock_reading(lat: float = 0.0, lon: float = 0.0, value: float = 1.0) -> Dict[str, Any]:
    return {
        "value": float(value),
        "unit": "mg/m^3",
        "source": "mock-test",
        "observed_at": _utc_now_iso(),
        "status": "mocked",
        "grid_lat": lat,
        "grid_lon": lon,
    }
