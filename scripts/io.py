"""Input/output helpers for boundary and emissions datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import pandas as pd

from scripts.geometry_utils import repair_geometry


EPSG_4326 = "EPSG:4326"


def _is_geojson_sequence(path: Path) -> bool:
    """Return True when a .geojson file is newline-delimited GeoJSON features."""
    if path.suffix.lower() not in {".geojson", ".json"}:
        return False

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            return stripped.startswith('{"type": "Feature"') or stripped.startswith('{"type":"Feature"')
    return False


def _load_geojson_sequence(path: Path) -> gpd.GeoDataFrame:
    """Load newline-delimited GeoJSON feature files as a GeoDataFrame."""
    features: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            record = json.loads(stripped)
            record_type = record.get("type")
            if record_type == "Feature":
                features.append(record)
            elif record_type == "FeatureCollection":
                features.extend(record.get("features", []))

    if not features:
        raise ValueError(f"GeoJSON sequence file '{path}' contains no features.")

    return gpd.GeoDataFrame.from_features(features, crs=EPSG_4326)


def _sanitize_geometries(gdf: gpd.GeoDataFrame, *, label: str) -> gpd.GeoDataFrame:
    """Drop empty geometries and best-effort repair invalid shapes.

    Some source datasets contain malformed rings that trigger GEOS failures
    during clipping/union operations. This helper performs a conservative
    clean-up pass so downstream rendering can proceed.
    """
    cleaned = gdf[gdf.geometry.notna()].copy()
    if cleaned.empty:
        raise ValueError(f"{label} has no geometries.")

    repaired_geometries = [repair_geometry(geom) for geom in cleaned.geometry]

    cleaned["geometry"] = repaired_geometries
    cleaned = cleaned[cleaned.geometry.notna() & ~cleaned.geometry.is_empty].copy()
    if cleaned.empty:
        raise ValueError(f"{label} has no usable geometries after repair.")

    return cleaned


def load_va_boundary(path: str) -> gpd.GeoDataFrame:
    """Load the Virginia boundary file as a GeoDataFrame."""
    gdf = gpd.read_file(path)
    if gdf.empty:
        raise ValueError(f"Boundary file '{path}' is empty.")
    return _sanitize_geometries(gdf, label=f"Boundary file '{path}'")


def load_vector_layer(path: str, layer: str | None = None) -> gpd.GeoDataFrame:
    """Load a geospatial layer from a vector file (GeoJSON/GPKG/shapefile)."""
    vector_path = Path(path)
    if _is_geojson_sequence(vector_path):
        gdf = _load_geojson_sequence(vector_path)
    else:
        gdf = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    if gdf.empty:
        layer_msg = f" (layer='{layer}')" if layer else ""
        raise ValueError(f"Vector file '{path}'{layer_msg} is empty.")
    layer_msg = f" (layer='{layer}')" if layer else ""
    return _sanitize_geometries(gdf, label=f"Vector file '{path}'{layer_msg}")


def load_vector_collection(path: str, layer: str | None = None) -> gpd.GeoDataFrame:
    """Load one vector layer or combine all vector files found under a directory."""
    input_path = Path(path)
    if input_path.is_file():
        return load_vector_layer(str(input_path), layer=layer)

    if not input_path.is_dir():
        raise FileNotFoundError(f"Vector input path does not exist: {input_path}")

    vector_paths = sorted(
        p
        for p in input_path.rglob("*")
        if p.is_file() and p.suffix.lower() in {".geojson", ".json", ".gpkg", ".shp"}
    )
    if not vector_paths:
        raise ValueError(f"No supported vector files found under directory: {input_path}")

    gdfs = [load_vector_layer(str(vector_path), layer=layer) for vector_path in vector_paths]
    base_crs = gdfs[0].crs
    merged = []
    for gdf in gdfs:
        if base_crs is not None and gdf.crs != base_crs:
            merged.append(gdf.to_crs(base_crs))
        else:
            merged.append(gdf)

    combined = gpd.GeoDataFrame(
        pd.concat(merged, ignore_index=True),
        geometry="geometry",
        crs=base_crs,
    )
    if combined.empty:
        raise ValueError(f"Vector input '{input_path}' resolved to zero features.")
    return combined


def load_emissions_csv(path: str) -> pd.DataFrame:
    """Load emissions CSV data into a DataFrame."""
    try:
        return pd.read_csv(path)
    except pd.errors.ParserError as exc:
        raise ValueError(
            f"Failed to parse CSV '{path}': inconsistent commas/quoting are likely; "
            "check quoted fields in rows that contain commas."
        ) from exc


def validate_required_columns(df: pd.DataFrame, required: Iterable[str]) -> None:
    """Ensure required columns are present in a DataFrame."""
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def emissions_to_gdf(
    df: pd.DataFrame,
    lat_col: str,
    lon_col: str,
    crs: str = EPSG_4326,
) -> gpd.GeoDataFrame:
    """Convert emissions tabular records to a point GeoDataFrame."""
    validate_required_columns(df, [lat_col, lon_col])

    clean_df = df.copy()
    clean_df[lat_col] = pd.to_numeric(clean_df[lat_col], errors="coerce")
    clean_df[lon_col] = pd.to_numeric(clean_df[lon_col], errors="coerce")
    clean_df = clean_df.dropna(subset=[lat_col, lon_col])

    return gpd.GeoDataFrame(
        clean_df,
        geometry=gpd.points_from_xy(clean_df[lon_col], clean_df[lat_col]),
        crs=crs,
    )


def ensure_crs(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    """Return a GeoDataFrame in the target CRS."""
    if gdf.crs is None:
        raise ValueError("GeoDataFrame has no CRS; cannot reproject.")
    if str(gdf.crs) == target_crs:
        return gdf
    return gdf.to_crs(target_crs)
