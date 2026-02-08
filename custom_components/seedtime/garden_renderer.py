"""Pure-Python SVG renderer for Seedtime garden plans."""

from __future__ import annotations

import html
import logging
import math
from typing import Any

_LOGGER = logging.getLogger(__name__)


def _shape_to_path(shape: dict[str, Any]) -> str:
    """Convert a Seedtime Shape object to an SVG path 'd' attribute.

    Shape → SVG path:
      M segment[0].start.x segment[0].start.y
      For each segment:
        if 2 bezierControlPoints → C (cubic bezier)
        if 1 bezierControlPoint  → Q (quadratic bezier)
        if 0 control points      → L (line)
      Z (close)
    """
    segments = shape.get("segments", [])
    if not segments:
        return ""

    try:
        parts: list[str] = []
        first = segments[0]["start"]
        parts.append(f"M {first['x']:.2f} {first['y']:.2f}")

        for i, seg in enumerate(segments):
            cps = seg.get("bezierControlPoints") or []
            # End point is the start of the next segment, or close to first
            if i + 1 < len(segments):
                end = segments[i + 1]["start"]
            else:
                end = segments[0]["start"]

            if len(cps) >= 2:
                # Cubic bezier
                parts.append(
                    f"C {cps[0]['x']:.2f} {cps[0]['y']:.2f}, "
                    f"{cps[1]['x']:.2f} {cps[1]['y']:.2f}, "
                    f"{end['x']:.2f} {end['y']:.2f}"
                )
            elif len(cps) == 1:
                # Quadratic bezier
                parts.append(
                    f"Q {cps[0]['x']:.2f} {cps[0]['y']:.2f}, "
                    f"{end['x']:.2f} {end['y']:.2f}"
                )
            else:
                # Straight line
                parts.append(f"L {end['x']:.2f} {end['y']:.2f}")

        parts.append("Z")
        return " ".join(parts)
    except (KeyError, TypeError, IndexError) as exc:
        _LOGGER.debug("Malformed shape segment data, skipping: %s", exc)
        return ""


def _shape_centroid(shape: dict[str, Any]) -> tuple[float, float]:
    """Compute the centroid of a shape from its segment start points."""
    segments = shape.get("segments", [])
    if not segments:
        return (0.0, 0.0)
    try:
        xs = [s["start"]["x"] for s in segments]
        ys = [s["start"]["y"] for s in segments]
    except (KeyError, TypeError):
        return (0.0, 0.0)
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _esc(text: str) -> str:
    """Escape text for safe SVG embedding."""
    return html.escape(str(text), quote=True)


# MDI icon paths (24x24 viewBox)
_MDI_TREE = (
    "M11,21V16.74C10.53,16.91 10.03,17 9.5,17C7.01,17 5,14.99 5,12.5"
    "C5,11.23 5.5,10.09 6.36,9.27C6.13,8.73 6,8.13 6,7.5C6,5.01 8.01,3 "
    "10.5,3C12.06,3 13.44,3.8 14.25,5C14.33,5 14.41,5 14.5,5C16.99,5 "
    "19,7.01 19,9.5C19,10.8 18.45,11.97 17.57,12.79C17.84,13.33 18,13.9 "
    "18,14.5C18,16.99 15.99,19 13.5,19C13.03,19 12.57,18.92 12.13,18.77"
    "V21H11Z"
)
_MDI_HOME = "M10,20V14H14V20H19V12H22L12,3L2,12H5V20H10Z"


def _landmark_badge_svg(
    icon_name: str | None, cx: float, cy: float, radius: float = 60
) -> str:
    """Generate a circular badge with MDI icon for landmarks, like HA map markers."""
    icon_path: str | None = None
    badge_color = "#555"

    if icon_name == "house":
        badge_color = "#44739e"
        icon_path = _MDI_HOME
    elif icon_name == "tree":
        badge_color = "#4a7c3f"
        icon_path = _MDI_TREE

    if not icon_path:
        return ""

    # Scale MDI 24x24 icon to fit ~60% of badge diameter
    scale = (radius * 1.2) / 24
    tx = cx - 12 * scale
    ty = cy - 12 * scale

    return (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{radius:.1f}" '
        f'fill="{badge_color}" stroke="#fff" stroke-width="4"/>'
        f'<path d="{icon_path}" fill="#fff" '
        f'transform="translate({tx:.1f},{ty:.1f}) scale({scale:.3f})"/>'
    )


def _build_render_order(
    landmarks: list[dict[str, Any]],
    locations: list[dict[str, Any]],
    groups: list[dict[str, Any]],
) -> list[tuple[str, dict[str, Any]]]:
    """Build a correctly ordered list of landmarks and locations for SVG rendering.

    Text elements are excluded — they are rendered separately on top of everything.

    Items within groups are rendered as a unit at the group's index position,
    maintaining their API return order within the group.
    """
    # Map group IDs to group index
    group_index_map: dict[str, int] = {}
    for grp in groups:
        if not grp.get("hidden"):
            group_index_map[grp["id"]] = grp.get("index") if grp.get("index") is not None else 0

    # Categorize all items
    grouped_items: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    ungrouped: list[tuple[int, str, dict[str, Any]]] = []

    for lm in landmarks:
        if lm.get("hidden"):
            continue
        group_id = lm.get("groupId")
        if group_id and group_id in group_index_map:
            grouped_items.setdefault(group_id, []).append(("landmark", lm))
        else:
            idx = lm.get("index") if lm.get("index") is not None else 0
            ungrouped.append((idx, "landmark", lm))

    for loc in locations:
        if loc.get("hidden"):
            continue
        group_id = loc.get("groupId")
        if group_id and group_id in group_index_map:
            grouped_items.setdefault(group_id, []).append(("location", loc))
        else:
            idx = loc.get("index") if loc.get("index") is not None else 0
            ungrouped.append((idx, "location", loc))

    # Build render units: each is (sort_index, items_list)
    render_units: list[tuple[int, list[tuple[str, dict[str, Any]]]]] = []

    # Each group becomes one render unit at the group's index
    for group_id, items in grouped_items.items():
        group_idx = group_index_map[group_id]
        render_units.append((group_idx, items))

    # Each ungrouped item is its own render unit
    for idx, item_type, item in ungrouped:
        render_units.append((idx, [(item_type, item)]))

    # Sort by index descending (higher index = rendered first = background)
    # In Seedtime, lower index values are closer to the viewer (foreground).
    # In SVG, later elements render on top. So higher-indexed items must
    # be rendered first (back) and lower-indexed items last (front).
    render_units.sort(key=lambda x: x[0], reverse=True)

    # Flatten to a single ordered list
    result: list[tuple[str, dict[str, Any]]] = []
    for _idx, items in render_units:
        result.extend(items)

    return result


def render_garden_svg(garden_data: dict[str, Any]) -> str:
    """Render a complete garden plan as an SVG string.

    All non-draft formations are included with date data attributes so the
    frontend card can filter by date client-side via the timeline slider.

    Args:
        garden_data: The 'garden' dict from coordinator data, containing
                     gardenPlan with plantingLocations, landmarks, groups.

    Returns:
        SVG markup string.
    """
    plan = garden_data.get("gardenPlan")
    if not plan:
        return _empty_svg("No garden plan data")

    width = plan.get("width") or 800
    height = plan.get("height") or 600

    locations = (plan.get("plantingLocations") or {}).get("nodes", [])
    landmarks = (plan.get("landmarks") or {}).get("nodes", [])
    groups = (plan.get("groups") or {}).get("nodes", [])
    texts = (plan.get("texts") or {}).get("nodes", [])

    # Build correctly ordered render list (landmarks + locations only)
    render_list = _build_render_order(landmarks, locations, groups)

    # Build SVG
    svg_parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" '
        f'style="background:#f5f0e8">',
        "<defs>"
        '<style type="text/css">'
        ".crop-initial { font-family: sans-serif; font-weight: 600; "
        "fill: #fff; text-anchor: middle; dominant-baseline: central; "
        "pointer-events: none; }"
        ".tooltip-target { cursor: pointer; }"
        ".text-label { font-family: sans-serif; fill: #333; "
        "dominant-baseline: hanging; pointer-events: none; }"
        "</style>"
        "</defs>",
    ]

    # Render landmarks and locations in z-order
    for item_type, item in render_list:
        if item_type == "landmark":
            svg_parts.append(_render_landmark(item))
        elif item_type == "location":
            svg_parts.append(_render_planting_location(item))

    # Render text elements LAST so they always appear on top
    for txt in texts:
        if not txt.get("hidden"):
            svg_parts.append(_render_text(txt))

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def _render_landmark(lm: dict[str, Any]) -> str:
    """Render a landmark as SVG path + optional badge icon."""
    shape = lm.get("shape", {})
    d = _shape_to_path(shape)
    if not d:
        return ""

    fill = lm.get("fillColor", "#cccccc")
    stroke = lm.get("strokeColor", "#999999")
    stroke_w = lm.get("strokeWidth", 1)
    name = _esc(lm.get("name", ""))

    # No rotation transform — Seedtime stores coordinates in final rotated frame
    # Landmarks have semitransparent fills with thick opaque strokes
    fill_opacity = 0.55
    # Clamp stroke width: minimum 3 for visibility, maximum 60 to prevent
    # oversized SVG strokes (e.g., Seedtime sets 1000 on some background layers
    # which extends the shape by 500 units on each side in SVG)
    effective_stroke_w = max(3, min(stroke_w, 60))

    icon_name = lm.get("iconName")
    raw_name = lm.get("name", "")

    # Landmarks with icons and a name get tooltip support
    if icon_name and raw_name:
        g_attrs = (
            f'class="landmark tooltip-target" data-name="{name}" '
            f'data-crop="{name}" data-color="{_esc(fill)}"'
        )
    else:
        g_attrs = f'class="landmark" data-name="{name}"'

    # House icons are small markers — skip the fill path entirely.
    # Tree icons keep their canopy circle (fill + stroke) with badge on top.
    skip_fill = (icon_name == "house")

    parts = [f'<g {g_attrs}>']
    if not skip_fill:
        parts.append(
            f'  <path d="{d}" fill="{_esc(fill)}" fill-opacity="{fill_opacity}" '
            f'stroke="{_esc(stroke)}" stroke-width="{effective_stroke_w}"/>'
        )

    if icon_name:
        cx, cy = _shape_centroid(shape)
        segs = shape.get("segments", [])
        if segs:
            xs = [s["start"]["x"] for s in segs]
            ys = [s["start"]["y"] for s in segs]
            extent = min(max(xs) - min(xs), max(ys) - min(ys))
            badge_r = max(30, min(80, extent * 0.15))
        else:
            badge_r = 60
        parts.append(_landmark_badge_svg(icon_name, cx, cy, badge_r))

    parts.append("</g>")
    return "\n".join(parts)


def _render_text(txt: dict[str, Any]) -> str:
    """Render a text element."""
    shape = txt.get("shape", {})
    segments = shape.get("segments", [])
    if not segments:
        return ""

    # Position text at the first segment start point
    x = segments[0]["start"]["x"]
    y = segments[0]["start"]["y"]
    text = _esc(txt.get("text", ""))
    font_size = txt.get("fontSize", 14)

    return (
        f'<text x="{x:.1f}" y="{y:.1f}" class="text-label" '
        f'font-size="{font_size}" font-weight="bold">{text}</text>'
    )


def _render_planting_location(loc: dict[str, Any]) -> str:
    """Render a planting location with all its non-draft formations.

    Every formation is included in the SVG with date data attributes;
    the frontend card handles visibility filtering via the timeline slider.
    """
    shape = loc.get("shape", {})
    d = _shape_to_path(shape)
    if not d:
        return ""

    fill = loc.get("fillColor", "#d4e6b5")
    name = _esc(loc.get("name", ""))

    all_formations = (loc.get("plantingFormations") or {}).get("nodes", [])
    formations = [
        f for f in all_formations
        if not f.get("draft") and f.get("gardenCrop")
    ]

    parts = [
        f'<g class="planting-location" data-name="{name}">',
        f'  <path d="{d}" fill="{_esc(fill)}" stroke="#8faa6e" '
        f'stroke-width="1"/>',
    ]

    for formation in formations:
        parts.append(_render_formation(formation))

    parts.append("</g>")
    return "\n".join(parts)


def _crop_initial(gc: dict[str, Any]) -> str:
    """Get a single-letter initial for a crop, matching Seedtime's display."""
    # Prefer cropName ("Brussels Sprouts") over title ("Brussels Sprouts - 1 - Red Rubine")
    name = gc.get("cropName") or gc.get("title") or ""
    return name[0].upper() if name else ""


def _plant_positions_from_rows(
    rows: list[dict[str, Any]], plant_spacing: float
) -> list[tuple[float, float]]:
    """Compute individual plant positions from cluster row data.

    Each row has a start and end point. Plants are evenly spaced along
    the row at `plant_spacing` intervals.
    """
    positions: list[tuple[float, float]] = []
    for row in rows:
        try:
            sx = row["start"]["x"]
            sy = row["start"]["y"]
            ex = row["end"]["x"]
            ey = row["end"]["y"]
        except (KeyError, TypeError):
            continue
        dx, dy = ex - sx, ey - sy
        row_len = math.sqrt(dx * dx + dy * dy)

        if row_len < 1 or plant_spacing < 1:
            # Single plant at the start of the row
            positions.append((sx, sy))
            continue

        ux, uy = dx / row_len, dy / row_len
        n_plants = int(row_len / plant_spacing) + 1
        for i in range(n_plants):
            px = sx + i * plant_spacing * ux
            py = sy + i * plant_spacing * uy
            positions.append((px, py))

    return positions


def _render_formation(formation: dict[str, Any]) -> str:
    """Render a planting formation with individual plant circles.

    Each plant is drawn as two concentric circles:
      - Outer (translucent): represents the spacing/growing area
      - Inner (opaque): represents the plant itself
    """
    shape = formation.get("shape", {})
    d = _shape_to_path(shape)
    if not d:
        return ""

    gc = formation.get("gardenCrop", {})
    color = gc.get("color", "#6b8e23")
    title = gc.get("title", "Unknown")
    seeding = gc.get("seedingDate", "")
    harvest = gc.get("harvestingDate", "")
    initial = _crop_initial(gc)
    plant_spacing = formation.get("plantSpacing") or 80

    plant_count = sum(
        c.get("plantCount", 0) for c in formation.get("clusters", [])
    )

    # Date range for timeline slider filtering
    ground_start = gc.get("groundOccupationStart", "")
    ground_end = gc.get("groundOccupationEnd", "")

    # Build data attributes for interactive tooltips + timeline filtering
    data_attrs = (
        f'data-crop="{_esc(title)}"'
        f' data-seeding="{_esc(seeding)}"'
        f' data-harvest="{_esc(harvest)}"'
        f' data-plants="{plant_count}"'
        f' data-ground-start="{_esc(ground_start)}"'
        f' data-ground-end="{_esc(ground_end)}"'
    )
    if color:
        data_attrs += f' data-color="{_esc(color)}"'

    # Outer radius = half the plant spacing (the spacing boundary)
    outer_r = plant_spacing / 2.0
    # Inner radius = ~35% of spacing (the plant body)
    inner_r = plant_spacing * 0.35

    parts = [
        f'  <g class="tooltip-target" {data_attrs}>',
        # Formation outline as invisible hit area for tooltip
        f'    <path d="{d}" fill="{_esc(color)}" fill-opacity="0" stroke="none"/>',
    ]

    # Render individual plant circles from cluster row data
    for cluster in formation.get("clusters", []):
        rows = cluster.get("rows") or []
        if rows:
            positions = _plant_positions_from_rows(rows, plant_spacing)
            # Draw outer (spacing) circles first, then inner (plant) circles on top
            for px, py in positions:
                parts.append(
                    f'    <circle cx="{px:.1f}" cy="{py:.1f}" r="{outer_r:.1f}" '
                    f'fill="{_esc(color)}" fill-opacity="0.3" stroke="none"/>'
                )
            for px, py in positions:
                parts.append(
                    f'    <circle cx="{px:.1f}" cy="{py:.1f}" r="{inner_r:.1f}" '
                    f'fill="{_esc(color)}" stroke="none"/>'
                )
        else:
            # Fallback: no row data, render cluster shape as solid fill
            cluster_shape = cluster.get("shape", {})
            cd = _shape_to_path(cluster_shape)
            if cd:
                parts.append(
                    f'    <path d="{cd}" fill="{_esc(color)}" stroke="none"/>'
                )

    # Show crop initial centered on the formation
    if initial:
        fcx, fcy = _shape_centroid(shape)
        segs = shape.get("segments", [])
        if segs:
            xs = [s["start"]["x"] for s in segs]
            ys = [s["start"]["y"] for s in segs]
            extent = min(max(xs) - min(xs), max(ys) - min(ys))
            font_size = max(24, min(80, extent * 0.35))
        else:
            font_size = 40
        parts.append(
            f'    <text x="{fcx:.1f}" y="{fcy:.1f}" '
            f'class="crop-initial" font-size="{font_size:.0f}">'
            f'{_esc(initial)}</text>'
        )

    parts.append("  </g>")
    return "\n".join(parts)


def _empty_svg(message: str) -> str:
    """Return a placeholder SVG with a message."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200" '
        'width="400" height="200">'
        '<rect width="400" height="200" fill="#f5f0e8"/>'
        f'<text x="200" y="100" text-anchor="middle" '
        f'font-family="sans-serif" font-size="14" fill="#999">'
        f"{html.escape(message)}</text>"
        "</svg>"
    )
