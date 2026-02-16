"""Point rendering utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.image as mpimg
import pandas as pd
from matplotlib.offsetbox import AnnotationBbox, OffsetImage


_ICON_BY_SECTOR = {
    "power": "power.jpg",
    "coal": "coal.jpg",
    "paper": "paper.jpg",
    "cement": "cement.jpg",
    "chemical": "chemical.jpg",
    "manufacturing": "manufacturing.jpg",
    "generation": "generation.jpg",
}


def _normalize_name(name: Any) -> str:
    if name is None:
        return ""
    return str(name).strip().upper()


def _pick_icon_key(subparts: str) -> str:
    codes = {part.strip().upper() for part in str(subparts or "").split(",") if part.strip()}
    if "FF" in codes:
        return "coal"
    if "AA" in codes:
        return "paper"
    if "H" in codes:
        return "cement"
    if {"G", "PP"} & codes:
        return "chemical"
    if "D" in codes:
        return "power"
    if "TT" in codes:
        return "generation"
    return "manufacturing"


def _load_icon(path: Path):
    return mpimg.imread(path)


def draw_points_with_top20_icons(
    map_ax,
    points_gdf: gpd.GeoDataFrame,
    top20_df: pd.DataFrame,
    cfg: dict[str, Any],
) -> None:
    """Draw all points as dots, then overlay top-20 facilities with icons."""
    style = cfg["style"]
    points_gdf.plot(
        ax=map_ax,
        markersize=float(style["points_size"]),
        color=style.get("points_color", "#ff8c42"),
        alpha=float(style["points_alpha"]),
        linewidth=0,
        zorder=2,
    )

    if top20_df.empty or points_gdf.empty:
        return

    icon_dir = Path(cfg.get("paths", {}).get("icons_dir", "icons"))
    icon_zoom = float(style.get("top20_icon_zoom", 0.2))

    top20 = top20_df.copy()
    if "facility_name" not in top20.columns:
        return

    top20["_facility_norm"] = top20["facility_name"].map(_normalize_name)
    if "subparts" not in top20.columns:
        top20["subparts"] = ""
    top20 = top20.drop_duplicates(subset=["_facility_norm"])

    points = points_gdf.copy()
    if "facility_name" not in points.columns:
        return

    points["_facility_norm"] = points["facility_name"].map(_normalize_name)
    points = points[points["_facility_norm"].isin(set(top20["_facility_norm"]))]

    if points.empty:
        return

    points = points.drop_duplicates(subset=["_facility_norm"])
    top20_by_name = top20.set_index("_facility_norm")

    icon_cache: dict[str, Any] = {}

    for _, row in points.iterrows():
        facility_norm = row["_facility_norm"]
        if facility_norm not in top20_by_name.index:
            continue

        subparts = top20_by_name.loc[facility_norm, "subparts"]
        icon_key = _pick_icon_key(subparts)
        icon_name = _ICON_BY_SECTOR.get(icon_key, "manufacturing.jpg")
        icon_path = icon_dir / icon_name
        if not icon_path.exists():
            continue

        if icon_name not in icon_cache:
            icon_cache[icon_name] = _load_icon(icon_path)

        image = OffsetImage(icon_cache[icon_name], zoom=icon_zoom)
        marker = AnnotationBbox(
            image,
            (row.geometry.x, row.geometry.y),
            frameon=False,
            box_alignment=(0.5, 0.5),
            zorder=6,
        )
        map_ax.add_artist(marker)
