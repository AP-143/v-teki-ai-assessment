"""Answer guard tests. The language model is replaced by a fake, so these run without Ollama."""
import pytest

from kb_chatbot import ask, ollama
from kb_chatbot.ask import REFUSAL, answer

QUESTION = "How many days of annual leave do I get per year?"


@pytest.fixture(autouse=True)
def low_bar(monkeypatch):
    monkeypatch.setattr(ask, "MIN_SCORE", 0.1)  # fake bag-of-words scores are lower than real embeddings


def fake_model(monkeypatch, reply, prompts=None):
    def generate(prompt, schema):
        if prompts is not None:
            prompts.append(prompt)
        return reply, {"prompt_tokens": 500, "output_tokens": 40}
    monkeypatch.setattr(ollama, "generate", generate)


def test_grounded_answer_keeps_citations(monkeypatch, index):
    fake_model(monkeypatch, {"answerable": True, "answer": "14 days per year.", "citations": ["leave-policy#annual-leave"]})
    result = answer(QUESTION, "employee", index)
    assert not result["refused"]
    assert result["citations"] == ["leave-policy#annual-leave"]


def test_question_below_the_score_bar_is_refused_without_calling_the_model(monkeypatch, index):
    monkeypatch.setattr(ask, "MIN_SCORE", 0.99)
    monkeypatch.setattr(ollama, "generate", lambda *a: pytest.fail("model must not be called"))
    result = answer("Where can I park my car?", "employee", index)
    assert result["refused"] and result["reason"] == "NO_RELEVANT_SECTION"
    assert result["answer"] == REFUSAL


def test_model_saying_not_in_excerpts_becomes_a_refusal(monkeypatch, index):
    fake_model(monkeypatch, {"answerable": False, "answer": "", "citations": []})
    result = answer(QUESTION, "employee", index)
    assert result["refused"] and result["reason"] == "NOT_IN_EXCERPTS"


@pytest.mark.parametrize("citations", [[], ["salary-bands#monthly-salary-bands"], ["made-up#section"]])
def test_answer_citing_anything_not_retrieved_is_refused(monkeypatch, index, citations):
    fake_model(monkeypatch, {"answerable": True, "answer": "14 days.", "citations": citations})
    result = answer(QUESTION, "employee", index)
    assert result["refused"] and result["reason"] == "INVALID_CITATION"
    assert result["answer"] == REFUSAL


def test_model_failure_becomes_a_refusal(monkeypatch, index):
    fake_model(monkeypatch, None)
    assert answer(QUESTION, "employee", index)["reason"] == "MODEL_ERROR"


def test_prompt_contains_only_retrieved_excerpts(monkeypatch, index):
    prompts = []
    fake_model(monkeypatch, {"answerable": False, "answer": "", "citations": []}, prompts)
    answer(QUESTION, "employee", index)
    assert prompts[0].count("<excerpt id=") == 3
    assert QUESTION in prompts[0]
