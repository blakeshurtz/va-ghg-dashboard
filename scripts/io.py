"""Input/output helpers for boundary and emissions datasets."""

from __future__ import annotations

from typing import Iterable

import geopandas as gpd
import pandas as pd


EPSG_4326 = "EPSG:4326"


def load_va_boundary(path: str) -> gpd.GeoDataFrame:
    """Load the Virginia boundary file as a GeoDataFrame."""
    gdf = gpd.read_file(path)
    if gdf.empty:
        raise ValueError(f"Boundary file '{path}' is empty.")
    return gdf


def load_vector_layer(path: str, layer: str | None = None) -> gpd.GeoDataFrame:
    """Load a geospatial layer from a vector file (GeoJSON/GPKG/shapefile)."""
    gdf = gpd.read_file(path, layer=layer) if layer else gpd.read_file(path)
    if gdf.empty:
        layer_msg = f" (layer='{layer}')" if layer else ""
        raise ValueError(f"Vector file '{path}'{layer_msg} is empty.")
    return gdf


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
