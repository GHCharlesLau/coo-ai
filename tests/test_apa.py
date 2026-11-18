from coo.citations.apa import assemble_proposal, in_text, reference
from coo.schemas.evidence import EvidenceItem, EvidenceLog


def _item() -> EvidenceItem:
    return EvidenceItem(
        id="ev1",
        claim="APEC is a regional forum.",
        author="APEC",
        year="2024",
        title="About APEC",
        container="APEC",
        source_url="https://www.apec.org/about-us",
        is_assumption=False,
    )


def test_in_text_and_reference_format():
    item = _item()
    assert in_text(item) == "(APEC, 2024)"
    assert reference(item) == "APEC. (2024). About APEC. APEC. https://www.apec.org/about-us"


def test_assemble_expands_markers_and_overwrites_references():
    item = _item()
    log = EvidenceLog(campaign_id="cmp-20260101-abcd1234", items=[item])
    text = """# Campaign Proposal

## 9. Next Steps
Approve. <!-- cite:ev1 -->

## References
stale line https://example.com/wrong
"""
    assembled = assemble_proposal(text, log)
    assert "(APEC, 2024)" in assembled
    assert "<!-- cite:ev1 -->" not in assembled
    assert "https://www.apec.org/about-us" in assembled
    assert "https://example.com/wrong" not in assembled
    assert assembled.count("## References") == 1
