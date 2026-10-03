# -*- coding: utf-8 -*-
"""Host-independent colour-override logic (US-10): no Revit imports."""


def _clamp(v):
    return max(0, min(255, int(v)))


def to_rgb(color_like):
    """(r, g, b) ints in 0..255 from any object with .R/.G/.B."""
    return (_clamp(color_like.R), _clamp(color_like.G), _clamp(color_like.B))


def override_plan(rgb, solid_fill_id):
    """Ordered (OverrideGraphicSettings setter name, value) pairs.

    Values are the rgb tuple, the solid fill id, or True; the Revit layer
    turns tuples into DB.Color.
    """
    rgb = tuple(rgb)
    return [
        ("SetSurfaceForegroundPatternId", solid_fill_id),
        ("SetSurfaceForegroundPatternColor", rgb),
        ("SetSurfaceForegroundPatternVisible", True),
        ("SetCutForegroundPatternId", solid_fill_id),
        ("SetCutForegroundPatternColor", rgb),
        ("SetCutForegroundPatternVisible", True),
        ("SetProjectionLineColor", rgb),
        ("SetCutLineColor", rgb),
    ]


def action_enabled(colour_ticked, colour_chosen, m):
    """(apply_enabled, reset_enabled) for the colour buttons."""
    return (bool(colour_ticked) and bool(colour_chosen) and m > 0, m > 0)


def find_solid_fill_id(fill_patterns):
    """Id of the first Drafting solid-fill pattern element, else None."""
    for fpe in fill_patterns:
        pattern = fpe.GetFillPattern()
        if pattern.IsSolidFill and str(pattern.Target) == "Drafting":
            return fpe.Id
    return None


def format_rgb(rgb):
    return "%d,%d,%d" % tuple(rgb)


def parse_rgb(text):
    """(r, g, b) from "r,g,b"; None on any bad input."""
    try:
        parts = [int(p) for p in str(text).split(",")]
    except (ValueError, TypeError):
        return None
    if len(parts) != 3:
        return None
    return tuple(_clamp(p) for p in parts)


def format_ints(values):
    return ",".join(str(int(v)) for v in values)


def parse_ints(text):
    """List of ints from a comma-separated string; None on bad or empty input."""
    try:
        values = [int(p) for p in str(text).split(",")]
    except (ValueError, TypeError):
        return None
    return values or None
