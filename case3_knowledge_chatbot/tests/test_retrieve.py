from kb_chatbot import CASE_DIR
from kb_chatbot.ingest import read_doc, split_sections
from kb_chatbot.retrieve import search


def test_documents_split_into_sections_with_roles():
    meta, body = read_doc(CASE_DIR / "data" / "docs" / "salary-bands.md")
    chunks = split_sections(meta, body)

    assert [c["chunk_id"] for c in chunks] == [
        "salary-bands#monthly-salary-bands", "salary-bands#annual-salary-review", "salary-bands#confidentiality"]
    assert all(c["allowed_roles"] == ["hr"] for c in chunks)
    assert chunks[0]["text"].startswith("Salary Bands (Confidential) - Monthly salary bands")


def test_search_ranks_the_matching_section_first(index):
    results = search("How many days of annual leave do I get per year?", "employee", index)
    assert results[0][0]["chunk_id"] == "leave-policy#annual-leave"
    assert results[0][1] >= results[1][1]
