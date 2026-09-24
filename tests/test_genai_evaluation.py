import pytest
from studio_genai import RAGEvaluation, evaluate_rag_example, summarize_rag_evaluation


def test_rag_evaluation_is_deterministic_and_serializable():
    result = evaluate_rag_example(
        "example-1",
        expected_chunks=("a", "b"),
        retrieved_chunks=("b", "c"),
        expected_answer="42",
        actual_answer=" 42 ",
    )
    assert result.retrieval_precision == 0.5
    assert result.retrieval_recall == 0.5
    assert result.answer_exact_match == 1.0
    assert result.to_payload()["metrics"]["retrieval_recall"] == 0.5


@pytest.mark.parametrize("kwargs", [{"example_id": "bad\nvalue"}, {"expected_chunks": ("a", "a")}])
def test_rag_evaluation_rejects_unsafe_or_ambiguous_input(kwargs):
    base = {
        "example_id": "x",
        "expected_chunks": ("a",),
        "retrieved_chunks": ("a",),
        "expected_answer": "a",
        "actual_answer": "a",
    }
    base.update(kwargs)
    with pytest.raises(ValueError, match="identifier|chunk"):
        evaluate_rag_example(**base)


def test_rag_evaluation_report_sorts_and_averages_bounded_evidence() -> None:
    first = evaluate_rag_example(
        "b", expected_chunks=("x",), retrieved_chunks=("x",), expected_answer="a", actual_answer="b"
    )
    second = evaluate_rag_example(
        "a", expected_chunks=("x",), retrieved_chunks=(), expected_answer="a", actual_answer="a"
    )
    report = summarize_rag_evaluation((first, second))
    assert [item.example_id for item in report.examples] == ["a", "b"]
    assert report.retrieval_precision == 0.5
    assert report.retrieval_recall == 0.5
    assert report.answer_exact_match == 0.5
    assert report.to_payload()["example_count"] == 2
    assert report.evidence_digest() == report.evidence_digest()
    assert len(report.evidence_digest()) == 64


def test_rag_evaluation_rejects_non_finite_or_out_of_range_metrics() -> None:
    with pytest.raises(ValueError, match="finite metric"):
        RAGEvaluation("invalid", (), (), "a", "a", 1.1, 0.0, 1.0)
