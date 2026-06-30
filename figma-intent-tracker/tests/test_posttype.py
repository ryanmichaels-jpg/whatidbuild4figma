from posttype import _finalize, classify_post_demo, detect_lead_magnet
from schema import FigmaSurface, PostType


def test_detect_lead_magnet_structure():
    assert detect_lead_magnet("Comment 'guide' and I'll DM you the playbook")
    assert detect_lead_magnet("Type WEBSITE below and I'll send you the guide")
    assert not detect_lead_magnet("Figma Motion vs After Effects -- what do you think?")


def test_demo_posts_typed_and_qualified():
    lm = classify_post_demo({"url": "https://www.linkedin.com/posts/demo-post-migration-guide"})
    assert lm.post_type == PostType.lead_magnet and lm.qualifies

    tq = classify_post_demo({"url": "https://www.linkedin.com/posts/demo-post-pricing-change"})
    assert tq.post_type == PostType.tool_question and tq.qualifies


def test_offtopic_post_does_not_qualify():
    ot = classify_post_demo({"url": "https://www.linkedin.com/posts/demo-post-offtopic"})
    assert ot.post_type == PostType.off_topic
    assert not ot.qualifies


def test_qualifies_requires_both_structure_and_figma_overlap():
    # right structure but Figma can't displace the use case (e.g. interior decor) -> drop
    no_overlap = _finalize(PostType.lead_magnet, FigmaSurface.none, "interior room redesign", [], "r", "demo")
    assert not no_overlap.qualifies
    # right structure AND a Figma surface -> qualify
    overlap = _finalize(PostType.lead_magnet, FigmaSurface.sites, "build a website", [], "r", "demo")
    assert overlap.qualifies
    # Figma overlap but wrong structure (a showcase) -> drop
    showcase = _finalize(PostType.showcase, FigmaSurface.motion, "animate a logo", [], "r", "demo")
    assert not showcase.qualifies
