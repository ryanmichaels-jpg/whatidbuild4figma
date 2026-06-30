from discover import (
    DISCOVERY_QUERIES,
    excluded_reason,
    filter_candidates,
    matched_displaced_tools,
)


def _post(content="", tools=None, bait=1, comments=0, headline=""):
    return {
        "url": content[:10], "content": content, "author_headline": headline,
        "matched_tools": tools or [], "bait_score": bait, "comment_count": comments,
    }


def test_stop_list_excludes_off_domain():
    assert excluded_reason("My Claude Code outbound cold email system") is not None
    assert excluded_reason("Real estate investing with AI") == "real estate"
    assert excluded_reason("a Figma design system workflow") is None
    assert excluded_reason("post", author_headline="601,060 followers") == "follower-count account"


def test_filter_requires_tool_and_drops_noise():
    posts = [
        _post("ditching Framer for our site", tools=["framer"], comments=34),   # keep
        _post("build an app no code, comment for guide", tools=[], comments=50),  # drop: no tool
        _post("After Effects cold outreach outbound funnel", tools=["after effects"]),  # drop: stop-list
    ]
    kept, drops = filter_candidates(posts, require_tool=True)
    assert [k["content"] for k in kept] == ["ditching Framer for our site"]
    assert drops["no_displaced_tool"] == 1
    assert any(r.startswith("stop:") for r in drops)


def test_filter_ranks_more_tool_mentions_first():
    posts = [
        _post("Webflow guide", tools=["webflow"], comments=5),
        _post("Webflow vs Framer vs Wix", tools=["webflow", "framer", "wix"], comments=2),
    ]
    kept, _ = filter_candidates(posts)
    assert kept[0]["content"] == "Webflow vs Framer vs Wix"  # more displaced tools -> ranked first


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
