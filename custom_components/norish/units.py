"""Short unit names for Norish unit ids.

Taken from Norish's default unit configuration
(packages/config/src/units.default.json), plus a few common metric units
missing there. Unknown units are shown unchanged.
"""

from __future__ import annotations

from typing import Final

# unit id -> (English, German) short form
SHORT_UNITS: Final[dict[str, tuple[str, str]]] = {
    "centiliter": ("cl", "cl"),
    "deciliter": ("dl", "dl"),
    "gram": ("g", "g"),
    "teaspoon": ("tsp", "TL"),
    "tablespoon": ("tbsp", "EL"),
    "knife_tip": ("knife tip", "Msp."),
    "pinch": ("pinch", "Prise"),
    "piece": ("piece", "Stk."),
    "clove": ("clove", "Zehe"),
    "leaf": ("leaf", "Blatt"),
    "sprig": ("sprig", "Zweig"),
    "bunch": ("bunch", "Bund"),
    "stalk": ("stalk", "Stängel"),
    "pack": ("pack", "Pck."),
    "can": ("can", "Dose"),
    "jar": ("jar", "Gl."),
    "bottle": ("bottle", "Fl."),
    "bag": ("bag", "Btl."),
    "box": ("box", "Schachtel"),
    "handful": ("handful", "Handvoll"),
    "splash": ("splash", "Schuss"),
    "cup": ("cup", "Tasse"),
    "glass": ("glass", "Glas"),
    "slice": ("slice", "Scheibe"),
    "strip": ("strip", "Streifen"),
    "sheet": ("sheet", "Platte"),
    "serving": ("serving", "Portion"),
    "round_slice": ("round", "Rädchen"),
    "ring": ("ring", "Ring"),
    "ball": ("ball", "Kugel"),
    "dash": ("dash", "Spritzer"),
    "drizzle": ("drizzle", "Spritzerchen"),
    "scoop": ("scoop", "Kelle"),
    "stick": ("stick", "Stange"),
    "tub": ("tub", "Becher"),
    "capful": ("capful", "Verschluss"),
    "pouch": ("pouch", "Beutel"),
    "sleeve": ("sleeve", "Tube"),
    "roll": ("roll", "Rolle"),
    "ear": ("ear", "Kolben"),
    "wedge": ("wedge", "Spalte"),
    "chunk": ("chunk", "Brocken"),
    "cube": ("cube", "Würfel"),
    "fillet": ("fillet", "Filet"),
    "heaping_tablespoon": ("heaping tbsp", "geh. EL"),
    "scant_tablespoon": ("scant tbsp", "gestr. EL"),
    "generous_pinch": ("generous pinch", "großzügige Prise"),
    "large_splash": ("large splash", "großer Schuss"),
    "dozen": ("dozen", "Dutzend"),
    "small_splash": ("small splash", "kleiner Schuss"),
    "bulb": ("bulb", "Knolle"),
    "head": ("head", "Kopf"),
    "to_taste": ("to taste", "n. B."),
    "pound": ("lb", "Pfd."),
    "bar": ("bar", "Riegel"),
    "bowl": ("bowl", "Schale"),
    "heaping_teaspoon": ("heaping tsp", "geh. TL"),
    "scant_teaspoon": ("scant tsp", "gestr. TL"),
    "pot": ("pot", "Topf"),
    "drop": ("drop", "Tr."),
    "ounce": ("oz", "Unze"),
    "milliliter": ("ml", "ml"),
    "liter": ("l", "l"),
    "centimeter": ("cm", "cm"),
    "to_serve": ("to serve", "zum Servieren"),
    "for_garnish": ("for garnish", "zum Garnieren"),
    "optional": ("optional", "optional"),
    "kilogram": ("kg", "kg"),
    "milligram": ("mg", "mg"),
}


def short_unit(unit: str, language: str) -> str:
    """Return the short form of a Norish unit id for the given language."""
    forms = SHORT_UNITS.get(unit.strip().lower())
    if forms is None:
        return unit
    return forms[1] if language.lower().startswith("de") else forms[0]
