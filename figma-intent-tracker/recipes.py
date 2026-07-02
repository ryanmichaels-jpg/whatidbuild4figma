"""RECIPES: discovery signals as pluggable config, not code.

A recipe is a JSON file in recipes/ that declares WHAT to search for (the tools a Figma
surface displaces, the queries) and, optionally, HOW to route leads it surfaces. The
discovery + post-type stages iterate over every ENABLED recipe, so a GTM team ships a new
signal by opening a recipe PR -- no engineering deploy (see docs/ADDING_A_SIGNAL.md).

GATE-SAFETY (the whole point of the pattern): a recipe can ONLY touch discovery + routing.
It is validated against recipes/schema.json with additionalProperties:false, and the
NORMALIZED form handed to the engine carries only {name, enabled, figma_surfaces,
routing_overrides, signals}. There is no field, and no code path, by which a recipe can
alter the trust gates (ICP filter, verbatim gate, verify, richness). Those are inherited by
every recipe and cannot be bypassed by config.

Validation runs at load (startup) and fails LOUD with the offending file + reason -- a bad
recipe never silently skips.
"""
from __future__ import annotations

import json
import os
import re

_DEFAULT_DIR = os.path.join(os.path.dirname(__file__), "recipes")
_SCHEMA_FILE = "schema.json"

_TYPE = {"string": str, "boolean": bool, "array": list, "object": dict, "number": (int, float)}


class RecipeError(ValueError):
    """A recipe failed validation. Message names the file and the reason."""


def _dir() -> str:
    return os.environ.get("RECIPES_DIR", _DEFAULT_DIR)


def _schema() -> dict:
    with open(os.path.join(_dir(), _SCHEMA_FILE), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _validate(recipe: dict, fname: str, schema: dict) -> None:
    props = schema.get("properties", {})
    for k in schema.get("required", []):
        if k not in recipe:
            raise RecipeError(f"{fname}: missing required key '{k}'")
    if schema.get("additionalProperties", True) is False:
        for k in recipe:
            if k not in props:
                raise RecipeError(
                    f"{fname}: unknown key '{k}' -- recipes may only declare discovery/routing "
                    f"config, never gate behavior (allowed: {sorted(props)})"
                )
    for k, v in recipe.items():
        t = props.get(k, {}).get("type")
        if t and not isinstance(v, _TYPE[t]):
            raise RecipeError(f"{fname}: key '{k}' must be {t}, got {type(v).__name__}")
    bodies = [b for b in schema.get("one_of_body", []) if b in recipe]
    if len(bodies) != 1:
        raise RecipeError(f"{fname}: must have EXACTLY one body of {schema.get('one_of_body')}, found {bodies}")


def _clean_tool(name: str) -> str:
    """Lowercase a displaced-tool name and drop parentheticals ('After Effects (UI motion)')."""
    return re.sub(r"\s*\(.*?\)\s*", " ", name).strip().lower()


def _normalize(recipe: dict) -> dict:
    """Reduce a validated recipe to ONLY what the engine may see: discovery + routing.

    Documentation sections (_meta, lead_magnet_playbook, pipeline_changes) are intentionally
    dropped here so they can never reach engine code -- the gate-safety boundary in practice.
    """
    signals = []
    if "surfaces" in recipe:  # base-map shape
        for surface, body in recipe["surfaces"].items():
            signals.append({
                "recipe": recipe["name"], "surface": surface,
                "tool_keywords": [t.lower() for t in body.get("tool_keywords", [])],
                "queries": list(body.get("queries", [])),
                "stop_list": [],
            })
    else:  # features-list shape (config-2026)
        for feat in recipe["features"]:
            signals.append({
                "recipe": recipe["name"], "surface": feat["figma_surface"],
                "tool_keywords": [_clean_tool(t) for t in feat.get("displaced_tools", [])],
                "queries": list(feat.get("or_queries", [])),
                "stop_list": [s.lower() for s in feat.get("stop_list", [])],
            })
    return {
        "name": recipe["name"],
        "enabled": bool(recipe["enabled"]),
        "figma_surfaces": list(recipe["figma_surfaces"]),
        "routing_overrides": dict(recipe.get("routing_overrides", {})),
        "signals": signals,
    }


def load_recipes(enabled_only: bool = True) -> list[dict]:
    """Load, validate, and normalize every recipe in the recipes dir. Fails loud on a bad one."""
    d = _dir()
    schema = _schema()
    out = []
    for fname in sorted(os.listdir(d)):
        if not fname.endswith(".json") or fname == _SCHEMA_FILE:
            continue
        path = os.path.join(d, fname)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except json.JSONDecodeError as e:
            raise RecipeError(f"{fname}: invalid JSON ({e})")
        _validate(raw, fname, schema)
        norm = _normalize(raw)
        if norm["enabled"] or not enabled_only:
            out.append(norm)
    return out


# --- Engine-facing helpers (enabled recipes only) --------------------------------

def discovery_queries(enabled_only: bool = True) -> list[tuple]:
    """[(query, recipe_name, surface)] across enabled recipes."""
    return [(q, r["name"], s["surface"]) for r in load_recipes(enabled_only) for s in r["signals"] for q in s["queries"]]


def displaced_tools(enabled_only: bool = True) -> dict:
    """{tool_keyword: (recipe_name, surface)} across enabled recipes. First writer wins."""
    out: dict[str, tuple] = {}
    for r in load_recipes(enabled_only):
        for s in r["signals"]:
            for tool in s["tool_keywords"]:
                out.setdefault(tool, (r["name"], s["surface"]))
    return out


def routing_override(surface_label: str | None, enabled_only: bool = True) -> str | None:
    """Return a recipe-declared routing override (SignalType value) for a surface, or None."""
    if not surface_label:
        return None
    for r in load_recipes(enabled_only):
        ov = r["routing_overrides"].get(surface_label)
        if ov:
            return ov
    return None
