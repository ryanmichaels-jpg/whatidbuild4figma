import hygiene
from schema import Commenter, HygieneStatus, Decision, Lead, TitleResult, TitleStatus


def _c(profile, name, company, headline):
    return Commenter(name=name, headline=headline, company=company,
                     profile_url=profile, comment_text="x", source="demo")


def test_title_extracted_from_headline():
    assert hygiene._title_from_headline("Design Systems Lead at Acme") == "Design Systems Lead"
    assert hygiene._title_from_headline("VP of Product | Northwind") == "VP of Product"
    assert hygiene._title_from_headline("") == ""


def test_job_change_when_company_differs():
    # SFDC has Maya at Globex; scrape sees her now at Acme
    f = hygiene.check(_c("https://www.linkedin.com/in/demo-maya-chen", "Maya Chen",
                         "Acme", "Design Systems Lead at Acme"))
    assert f.status == HygieneStatus.job_change and f.is_stale


def test_title_stale_when_same_company_new_title():
    # SFDC has Devraj as Senior Product Manager at Northwind; scrape sees VP of Product
    f = hygiene.check(_c("https://www.linkedin.com/in/demo-devraj-patel", "Devraj Patel",
                         "Northwind", "VP of Product at Northwind"))
    assert f.status == HygieneStatus.title_stale and f.is_stale


def test_current_when_matches():
    f = hygiene.check(_c("https://www.linkedin.com/in/demo-lena-fischer", "Lena Fischer",
                         "Brightloom", "Product Designer at Brightloom"))
    assert f.status == HygieneStatus.current and not f.is_stale


def test_no_record_for_unknown_person():
    f = hygiene.check(_c("https://www.linkedin.com/in/nobody-xyz", "Nobody Xyz",
                         "Random Co", "Product Designer at Random Co"))
    assert f.status == HygieneStatus.no_record and not f.is_stale


def _lead(flagstatus_commenter):
    c = flagstatus_commenter
    return Lead(commenter=c, title=TitleResult(status=TitleStatus.matched),
                decision=Decision.surface, reason="x", hygiene=hygiene.check(c))


def test_digest_and_queue_only_include_stale():
    leads = [
        _lead(_c("https://www.linkedin.com/in/demo-maya-chen", "Maya Chen", "Acme", "Design Systems Lead at Acme")),
        _lead(_c("https://www.linkedin.com/in/demo-lena-fischer", "Lena Fischer", "Brightloom", "Product Designer at Brightloom")),
    ]
    stale = hygiene.stale_flags(leads)
    assert len(stale) == 1 and stale[0].commenter.name == "Maya Chen"
    digest = hygiene.build_digest(leads)
    assert digest and "1 stale" in digest and "Maya Chen" in digest and "Lena" not in digest


def test_digest_none_when_all_clean():
    leads = [_lead(_c("https://www.linkedin.com/in/demo-lena-fischer", "Lena Fischer",
                      "Brightloom", "Product Designer at Brightloom"))]
    assert hygiene.build_digest(leads) is None
