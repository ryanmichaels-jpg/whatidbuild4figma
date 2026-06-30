from discover import DISCOVERY_QUERIES, matched_displaced_tools


def test_displaced_tool_matching_is_whole_word():
    # 'anima' (the handoff tool) must NOT fire on 'animation'/'animated'
    assert matched_displaced_tools("recent motion graphics animation work") == []
    assert "anima" in matched_displaced_tools("we tried Anima for design handoff")
    # 'rive' must not fire on 'arrive'
    assert matched_displaced_tools("we arrive tomorrow") == []
    assert "rive" in matched_displaced_tools("built the prototype in Rive")


def test_matches_named_competitors():
    tools = matched_displaced_tools("My best decision was ditching Framer and Webflow for our site")
    assert "framer" in tools and "webflow" in tools
    assert "after effects" in matched_displaced_tools("trying to get off After Effects for UI animation")


def test_discovery_queries_loaded_from_map():
    assert len(DISCOVERY_QUERIES) > 10
    assert any("After Effects" in q for q in DISCOVERY_QUERIES)
