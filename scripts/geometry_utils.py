"""Geometry repair helpers for resilient geospatial operations."""

from __future__ import annotations

from typing import Any
import warnings

try:
    from shapely import make_valid as _make_valid
except Exception:  # pragma: no cover - shapely<2 fallback
    _make_valid = None


def repair_geometry(geom: Any):
    """Best-effort repair for malformed geometries.

    Returns ``None`` when the geometry cannot be made usable.
    """
    if geom is None:
        return None

    try:
        if geom.is_empty:
            return None
    except Exception:
        return None

    candidate = geom

    # Try make_valid first when available (more robust than buffer(0) for bad rings).
    # Some malformed geometries emit RuntimeWarning("invalid value encountered")
    # from GEOS internals; treat those as recoverable and continue to fallback.
    if _make_valid is not None:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="invalid value encountered in make_valid",
                    category=RuntimeWarning,
                )
                candidate = _make_valid(candidate)
        except Exception:
            pass

    try:
        is_valid = bool(candidate.is_valid)
    except Exception:
        is_valid = False

    if not is_valid:
        try:
            candidate = candidate.buffer(0)
        except Exception:
            return None

    # Buffer(0) can still yield invalid outputs for severely malformed inputs.
    try:
        if not bool(candidate.is_valid):
            return None
    except Exception:
        return None

    try:
        if candidate is None or candidate.is_empty:
            return None
    except Exception:
        return None

    return candidate
