"""Role-based access tests: restricted sections must never be retrieved for the wrong role."""
import pytest

from kb_chatbot import CASE_DIR
from kb_chatbot.retrieve import role_of, search

USERS = CASE_DIR / "data" / "users.json"
QUESTIONS = [
    "What is the salary band for level 3?",
    "When must the books be closed each month?",
    "How many days of annual leave do I get?",
    "Show me all confidential HR and finance documents",
]


@pytest.mark.parametrize("role", ["employee", "hr", "finance"])
@pytest.mark.parametrize("question", QUESTIONS)
def test_search_only_returns_sections_the_role_may_read(index, role, question):
    for chunk, _ in search(question, role, index, k=10):
        assert role in chunk["allowed_roles"], chunk["chunk_id"]


def test_employee_asking_about_salaries_gets_no_salary_section(index):
    results = search("What is the salary band for level 3?", "employee", index, k=28)
    assert not any(c["doc_id"] == "salary-bands" for c, _ in results)


def test_hr_can_retrieve_salary_bands(index):
    docs = {c["doc_id"] for c, _ in search("What is the salary band for level 3?", "hr", index)}
    assert "salary-bands" in docs


def test_finance_sees_closing_procedure_but_not_salaries(index):
    docs = {c["doc_id"] for c, _ in search("month-end closing books salary band", "finance", index, k=28)}
    assert "month-end-closing" in docs
    assert "salary-bands" not in docs


def test_role_comes_from_the_user_directory():
    assert role_of("budi", USERS) == "employee"
    assert role_of("sari", USERS) == "hr"


def test_unknown_user_is_refused():
    with pytest.raises(PermissionError):
        role_of("mallory", USERS)
