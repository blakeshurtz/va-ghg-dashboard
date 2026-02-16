"""Point rendering utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.image as mpimg
from matplotlib.offsetbox import AnnotationBbox, OffsetImage


_ICON_BY_SECTOR = {
    "power": "coal.jpg",
    "coal": "coal.jpg",
    "paper": "paper.jpg",
    "cement": "cement.jpg",
    "chemical": "chemical.jpg",
    "manufacturing": "manufacturing.jpg",
    "generation": "generation.jpg",
}


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


def draw_points_with_facility_icons(
    map_ax,
    points_gdf: gpd.GeoDataFrame,
    cfg: dict[str, Any],
) -> None:
    """Draw all facilities with icons; keep unmatched facilities as yellow points."""
    style = cfg["style"]
    if points_gdf.empty:
        return

    icon_dir = Path(cfg.get("paths", {}).get("icons_dir", "icons"))
    icon_zoom = float(style.get("top20_icon_zoom", 0.2))
    default_point_color = style.get("default_points_color", "#ffd84d")
    default_point_size = float(style.get("points_size", 8))
    default_point_alpha = float(style.get("points_alpha", 0.8))

    points = points_gdf.copy()
    if "subparts" not in points.columns:
        points["subparts"] = ""

    icon_cache: dict[str, Any] = {}
    fallback_x: list[float] = []
    fallback_y: list[float] = []

    for _, row in points.iterrows():
        subparts = row["subparts"]
        icon_key = _pick_icon_key(subparts)
        icon_name = _ICON_BY_SECTOR.get(icon_key, "manufacturing.jpg")
        icon_path = icon_dir / icon_name
        if not icon_path.exists():
            fallback_x.append(row.geometry.x)
            fallback_y.append(row.geometry.y)
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

    if fallback_x:
        map_ax.scatter(
            fallback_x,
            fallback_y,
            s=default_point_size,
            c=default_point_color,
            alpha=default_point_alpha,
            linewidths=0,
            zorder=4,
        )
