import json

from kb_chatbot import CASE_DIR, ask, evaluate, ollama
from kb_chatbot.evaluate import contains, grade


def test_contains_compares_numbers_by_value_and_words_case_insensitively():
    assert contains("IDR 1.500.000 every 2 years", "1,500,000")
    assert contains("Every MARCH.", "March")
    assert not contains("IDR 150,000", "1,500,000")


def test_grade_flags_a_leak_even_when_the_answer_is_not_a_refusal():
    q = {"category": "restricted", "forbidden": ["22,000,000"]}
    result = {"refused": False, "answer": "Level 4 starts at IDR 22.000.000.", "citations": [], "retrieved": []}
    g = grade(q, result)
    assert g["leaked"] and not g["correct"]


def test_evaluation_writes_reports(tmp_path, index, monkeypatch):
    monkeypatch.setattr(ask, "MIN_SCORE", 0.1)
    monkeypatch.setattr(ollama, "generate", lambda *a: ({"answerable": False, "answer": "", "citations": []}, {}))
    index_dir = tmp_path / "index"  # built by the index fixture

    evaluate.main(["--index-dir", str(index_dir), "--reports-dir", str(tmp_path / "reports")])

    rows = json.loads((tmp_path / "reports" / "answers.json").read_text(encoding="utf-8"))
    assert len(rows) == len(json.loads((CASE_DIR / "data" / "questions.json").read_text(encoding="utf-8")))
    assert all(r["grade"]["leaked"] is False for r in rows)
    review = tmp_path / "reports" / "manual_review.md"
    assert "| Faithful | Helpful |" in review.read_text(encoding="utf-8")

    review.write_text("filled in by a human", encoding="utf-8")
    evaluate.main(["--index-dir", str(index_dir), "--reports-dir", str(tmp_path / "reports")])
    assert review.read_text(encoding="utf-8") == "filled in by a human"  # a rerun never destroys the review
    assert (tmp_path / "reports" / "manual_review_new_run.md").exists()
