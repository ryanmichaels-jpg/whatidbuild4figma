from richness import score_richness


def test_thin_hand_raise():
    score, label = score_richness("Interested!")
    assert score == 0 and label == "thin"
    assert score_richness("Website")[1] == "thin"


def test_rich_comment_names_tool_and_pain():
    # names a competitor (Gamma) + states a limitation + substantive length
    score, label = score_richness(
        "after playing around with Gamma, it's still quite limited -- the API can't "
        "generate fully sales-ready proposals yet, which is a real problem for us"
    )
    assert score >= 2 and label == "rich"


def test_moderate_when_only_one_signal():
    # a question but short and no tool named
    score, label = score_richness("is this better than what we have?")
    assert label in ("moderate", "rich")
