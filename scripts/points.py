"""Point rendering utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import matplotlib.image as mpimg
from matplotlib.offsetbox import AnnotationBbox, OffsetImage


_DEFAULT_ICON_BY_SUBPARTS = {
    "C": "factory_C.jpg",
    "C,HH": "CHH_furnace.jpg",
    "C,Q": "CQ_tanks.jpg",
    "C,W": "CW_clarifier.jpg",
    "C,S": "CS_steel.jpg",
    "C,I": "manufacturing.jpg",
    "C,II": "manufacturing.jpg",
    "AA,C": "paper.jpg",
    "DD": "gas.jpg",
    "C,N": "chemical.jpg",
    "TT": "gas.jpg",
    "FF": "coal.jpg",
    "D": "power.jpg",
    "C,D": "power.jpg",
    "C,G,PP": "chemical.jpg",
    "C,H": "cement.jpg",
    "C,TT": "generation.jpg",
    "AA,C,TT": "paper.jpg",
}


def _normalize_subparts(subparts: str) -> str:
    codes = sorted({part.strip().upper() for part in str(subparts or "").split(",") if part.strip()})
    return ",".join(codes)


def _load_icon_mappings(cfg: dict[str, Any]) -> tuple[str, dict[str, str]]:
    icon_cfg = cfg.get("icons", {})
    default_icon = str(icon_cfg.get("default", "manufacturing.jpg"))

    raw_mapping = icon_cfg.get("by_subparts", _DEFAULT_ICON_BY_SUBPARTS)
    mapping: dict[str, str] = {}
    if isinstance(raw_mapping, dict):
        for subparts, icon_name in raw_mapping.items():
            mapping[_normalize_subparts(str(subparts))] = str(icon_name)

    if not mapping:
        mapping = {key: value for key, value in _DEFAULT_ICON_BY_SUBPARTS.items()}

    return default_icon, mapping


def _load_icon(path: Path):
    return mpimg.imread(path)


def _primary_subpart(subparts: str) -> str:
    parts = [part.strip().upper() for part in str(subparts or "").split(",") if part.strip()]
    return parts[0] if parts else "UNK"


def draw_points_with_facility_icons(
    map_ax,
    points_gdf: gpd.GeoDataFrame,
    cfg: dict[str, Any],
) -> None:
    """Draw facilities with icons by subpart mapping, with subpart text fallback."""
    style = cfg["style"]
    if points_gdf.empty:
        return

    icon_dir = Path(cfg.get("paths", {}).get("icons_dir", "icons"))
    default_icon, icon_by_subparts = _load_icon_mappings(cfg)
    apply_icons_to_all = bool(cfg.get("icons", {}).get("apply_to_all_facilities", True))
    icon_zoom = float(style.get("top20_icon_zoom", 0.09))
    non_top20_label_size = float(style.get("non_top20_label_size", 5))
    non_top20_label_color = style.get("non_top20_label_color", "#dbe8f5")

    points = points_gdf.copy()
    if "subparts" not in points.columns:
        points["subparts"] = ""
    if "_is_top20" not in points.columns:
        points["_is_top20"] = False

    icon_cache: dict[str, Any] = {}
    for _, row in points.iterrows():
        should_try_icon = apply_icons_to_all or bool(row.get("_is_top20", False))
        if not should_try_icon:
            map_ax.text(
                row.geometry.x,
                row.geometry.y,
                _primary_subpart(row["subparts"]),
                color=non_top20_label_color,
                fontsize=non_top20_label_size,
                ha="center",
                va="center",
                zorder=6,
            )
            continue

        subparts = row["subparts"]
        normalized_subparts = _normalize_subparts(subparts)
        icon_name = icon_by_subparts.get(normalized_subparts, default_icon)
        icon_path = icon_dir / icon_name
        if not icon_path.exists():
            map_ax.text(
                row.geometry.x,
                row.geometry.y,
                _primary_subpart(row["subparts"]),
                color=non_top20_label_color,
                fontsize=non_top20_label_size,
                ha="center",
                va="center",
                zorder=6,
            )
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
