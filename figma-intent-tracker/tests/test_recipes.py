import json
import os

import pytest

import accounts
import recipes
from schema import IntentType, SignalType


def test_both_shipped_recipes_load_and_validate():
    all_r = recipes.load_recipes(enabled_only=False)
    names = {r["name"]: r for r in all_r}
    assert set(names) == {"base_displacement", "config2026"}
    assert names["base_displacement"]["enabled"] is True
    assert names["config2026"]["enabled"] is False  # ships disabled per its author's note


def test_only_enabled_recipes_drive_discovery():
    qs = recipes.discovery_queries()  # enabled only
    assert qs and all(r == "base_displacement" for _q, r, _s in qs)
    tools = recipes.displaced_tools()
    assert "after effects" in tools and "webflow" in tools
    assert "comfyui" not in tools  # config2026 tool, recipe disabled -> not in discovery


def test_routing_override_lookup():
    assert recipes.routing_override("GEN_PLUGINS", enabled_only=False) == "upsell"
    assert recipes.routing_override("GEN_PLUGINS") is None          # config2026 disabled
    assert recipes.routing_override("nonexistent", enabled_only=False) is None


def test_normalized_recipe_cannot_carry_gate_config():
    # the engine-facing shape exposes ONLY discovery + routing -- doc sections are stripped
    allowed = {"name", "enabled", "figma_surfaces", "routing_overrides", "signals"}
    for r in recipes.load_recipes(enabled_only=False):
        assert set(r) == allowed


def _write(dirpath, name, obj):
    with open(os.path.join(dirpath, name), "w", encoding="utf-8") as fh:
        json.dump(obj, fh)


def test_bad_recipe_fails_loud(tmp_path, monkeypatch):
    # a recipe with an unknown top-level key must raise (can't sneak in gate behavior)
    schema = json.load(open(os.path.join(recipes._DEFAULT_DIR, "schema.json")))
    _write(tmp_path, "schema.json", schema)
    _write(tmp_path, "bad.json", {
        "name": "bad", "version": "1.0", "enabled": True, "figma_surfaces": ["sites"],
        "surfaces": {"sites": {"tool_keywords": [], "queries": []}},
        "gate_threshold": 0.1,  # <-- forbidden
    })
    monkeypatch.setenv("RECIPES_DIR", str(tmp_path))
    with pytest.raises(recipes.RecipeError) as e:
        recipes.load_recipes(enabled_only=False)
    assert "unknown key 'gate_threshold'" in str(e.value)


def test_missing_body_fails_loud(tmp_path, monkeypatch):
    schema = json.load(open(os.path.join(recipes._DEFAULT_DIR, "schema.json")))
    _write(tmp_path, "schema.json", schema)
    _write(tmp_path, "nobody.json", {"name": "n", "version": "1.0", "enabled": True, "figma_surfaces": []})
    monkeypatch.setenv("RECIPES_DIR", str(tmp_path))
    with pytest.raises(recipes.RecipeError):
        recipes.load_recipes(enabled_only=False)


def test_route_applies_recipe_override(monkeypatch):
    # when a (would-be enabled) recipe declares an override for the surface, route re-aims it
    monkeypatch.setattr(accounts.recipes_mod, "routing_override", lambda s, enabled_only=True: "upsell")
    a = accounts.match_account_demo("Acme")  # existing enterprise customer
    r = accounts.route(IntentType.active_need, a, "Acme", recipe_surface="GEN_PLUGINS")
    assert r.signal_type == SignalType.upsell and "recipe override" in r.rationale
