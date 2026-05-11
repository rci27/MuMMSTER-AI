"""
Mummster — shared field name normalization.

Apply normalize_field() to any category name, header, or column label before
writing to parsed_scores. Ensures consistent keys across all era parsers and
the vision extractor regardless of how the source sheet labeled a column.
"""

from __future__ import annotations

# Maps lowercase-stripped variants → canonical name.
# Includes identity mappings (lowercase → proper case) so already-canonical
# input is returned correctly without special-casing the caller.
FIELD_NORMALIZATION: dict[str, str] = {
    # ── Marching order field ──────────────────────────────────────────────
    "position":         "marching_order",
    "order":            "marching_order",
    "march order":      "marching_order",
    "marching order":   "marching_order",
    "marching_order":   "marching_order",

    # ── Music categories ──────────────────────────────────────────────────
    "music playing":         "Music Playing",
    "music arrangement":     "General Effect Music",
    "arrangement":           "General Effect Music",
    "ge music":              "General Effect Music",
    "general effect music":  "General Effect Music",

    # ── Visual categories ─────────────────────────────────────────────────
    "production":            "Visual Performance",
    "visual performance":    "Visual Performance",
    "ge visual":             "General Effect Visual",
    "general effect visual": "General Effect Visual",

    # ── Other scored categories ───────────────────────────────────────────
    "music":        "Music",
    "presentation": "Presentation",
    "costume":      "Costume",
    # Maps standalone "Performance" category label to Visual Performance.
    # Does NOT affect subcategory names (e.g. VP subcategory "Performance" in _ERA3_SUBCATS)
    # because subcategory values never go through this lookup.
    "performance":  "Visual Performance",

    # ── Total score variants ──────────────────────────────────────────────
    "total":       "Total Score",
    "grand total": "Total Score",
    "total score": "Total Score",
}


def normalize_field(name: str) -> str:
    """
    Return the canonical name for a category, column header, or field label.
    Case-insensitive match after stripping whitespace.
    Returns the stripped input unchanged if no mapping exists.
    """
    stripped = name.strip()
    return FIELD_NORMALIZATION.get(stripped.lower(), stripped)


def normalize_band_name(name: str) -> str:
    """Return the band name with leading/trailing whitespace stripped."""
    return name.strip()
