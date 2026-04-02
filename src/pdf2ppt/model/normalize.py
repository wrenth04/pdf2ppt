from __future__ import annotations

FONT_ALIASES = {
    "helvetica": "Arial",
    "arial": "Arial",
    "times": "Times New Roman",
    "timesnewromanpsmt": "Times New Roman",
    "courier": "Courier New",
    "couriernew": "Courier New",
    "symbol": "Arial",
    "zapfdingbats": "Arial",
}


def normalize_font_name(name: str) -> str:
    if "+" in name:
        return name.split("+", 1)[1]
    return name


def font_fallback(name: str) -> str:
    base = name.lower().replace(" ", "")
    for k, v in FONT_ALIASES.items():
        if k in base:
            return v
    return name
