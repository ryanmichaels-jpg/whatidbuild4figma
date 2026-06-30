from schema import Persona, TitleStatus
from titles import classify_title


def test_persona_mapping():
    assert classify_title("Design Systems Lead at Acme").persona == Persona.champion
    assert classify_title("VP of Product at Northwind").persona == Persona.economic_buyer
    assert classify_title("Product Designer at Brightloom").persona == Persona.user
    assert classify_title("Head of IT at Vaultline").persona == Persona.gatekeeper


def test_specific_beats_general():
    # 'director of product design' (champion) must win over 'director of product' (economic_buyer)
    assert classify_title("Director of Product Design at Lumen").persona == Persona.champion


def test_excludes_drop():
    for title in ["Computer Science Student", "Technical Recruiter", "Open to work", "Job Seeker"]:
        assert classify_title(title).status == TitleStatus.excluded


def test_intern_is_whole_word():
    assert classify_title("Marketing Intern at Foobar").status == TitleStatus.excluded
    # 'internal'/'international' must NOT trip the intern token
    assert classify_title("Internal Communications Lead").status != TitleStatus.excluded
    assert classify_title("International Sales Manager").status != TitleStatus.excluded


def test_broadened_design_roles_are_user_icp():
    assert classify_title("Webflow Developer @ Yes Chef Studio").persona == Persona.user
    assert classify_title("Digital Content Designer").persona == Persona.user
    assert classify_title("Senior Presentation Designer | Pitch Decks").persona == Persona.user
    assert classify_title("Graphic Designer at Fiverr").persona == Persona.user


def test_student_is_whole_word_with_service_exception():
    # genuine student status -> excluded
    assert classify_title("Computer Science Student at MIT").status == TitleStatus.excluded
    # 'student support'/'student success' is a service area, not a job seeker
    assert classify_title("AI Automation for Education | Student Support, Billing").status != TitleStatus.excluded
    assert classify_title("Student Success Manager").status != TitleStatus.excluded


def test_missing_title_routes_to_review_not_drop():
    assert classify_title(None).status == TitleStatus.missing
    assert classify_title("   ").status == TitleStatus.missing


def test_present_but_unrecognized_is_off_icp():
    assert classify_title("Marketing Manager at Foobar").status == TitleStatus.off_icp


def test_cpo_disambiguation():
    # full phrase still maps to economic_buyer
    assert classify_title("Chief Product Officer at Acme").persona == Persona.economic_buyer
    # Chief People Officer (HR) must NOT be an economic buyer
    assert classify_title("Chief People Officer at BigCo").status != TitleStatus.matched
    # the live false positive: HR founder is a builder (via 'founder'), not a product buyer
    assert classify_title("Founder & Fractional CPO | Vybrant HR").persona == Persona.builder
    # HR context blocks the buyer persona even if a product title appears
    assert classify_title("VP of Product | Head of People & Culture").persona != Persona.economic_buyer


def test_builder_prospect_tier():
    assert classify_title("Founder & Indie Hacker").persona == Persona.builder
    assert classify_title("Product Manager at Acme").persona == Persona.builder
    assert classify_title("No-code builder | Solopreneur").persona == Persona.builder
    # a design title still wins over builder (design rules are checked first)
    assert classify_title("Founder & Product Designer").persona == Persona.user
