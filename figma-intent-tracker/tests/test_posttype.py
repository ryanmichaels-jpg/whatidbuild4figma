from posttype import classify_post_demo, detect_lead_magnet
from schema import PostType


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
