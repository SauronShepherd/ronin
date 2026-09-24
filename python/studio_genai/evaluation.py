"""Deterministic, provider-neutral RAG evaluation contracts."""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from studio_core.canonical_json import encode as encode_canonical_json


@dataclass(frozen=True, slots=True)
class RAGEvaluation:
    example_id: str
    expected_chunks: tuple[str, ...]
    retrieved_chunks: tuple[str, ...]
    expected_answer: str
    actual_answer: str
    retrieval_precision: float
    retrieval_recall: float
    answer_exact_match: float

    def __post_init__(self) -> None:
        if not self.example_id or self.example_id != self.example_id.strip():
            raise ValueError("RAG evaluation example_id must be non-empty and trimmed")
        if len(self.example_id) > 256 or any(c in self.example_id for c in "\r\n\x00"):
            raise ValueError("RAG evaluation example_id must be a bounded identifier")
        if len(set(self.expected_chunks)) != len(self.expected_chunks) or len(
            set(self.retrieved_chunks)
        ) != len(self.retrieved_chunks):
            raise ValueError("RAG chunk identifiers must be unique")
        for name, value in (
            ("retrieval_precision", self.retrieval_precision),
            ("retrieval_recall", self.retrieval_recall),
            ("answer_exact_match", self.answer_exact_match),
        ):
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError(f"RAG {name} must be a finite metric between 0 and 1")

    def to_payload(self) -> dict[str, object]:
        return {
            "example_id": self.example_id,
            "expected_chunks": list(self.expected_chunks),
            "retrieved_chunks": list(self.retrieved_chunks),
            "expected_answer": self.expected_answer,
            "actual_answer": self.actual_answer,
            "metrics": {
                "retrieval_precision": self.retrieval_precision,
                "retrieval_recall": self.retrieval_recall,
                "answer_exact_match": self.answer_exact_match,
            },
        }


@dataclass(frozen=True, slots=True)
class RAGEvaluationReport:
    """Deterministic aggregate over a bounded RAG evaluation dataset."""

    examples: tuple[RAGEvaluation, ...]
    retrieval_precision: float
    retrieval_recall: float
    answer_exact_match: float

    def to_payload(self) -> dict[str, object]:
        return {
            "example_count": len(self.examples),
            "metrics": {
                "retrieval_precision": self.retrieval_precision,
                "retrieval_recall": self.retrieval_recall,
                "answer_exact_match": self.answer_exact_match,
            },
            "examples": [item.to_payload() for item in self.examples],
        }

    def evidence_digest(self) -> str:
        """Return the stable digest of the complete serialized evaluation evidence."""

        encoded = encode_canonical_json(self.to_payload())
        return hashlib.sha256(encoded).hexdigest()


def summarize_rag_evaluation(
    evaluations: tuple[RAGEvaluation, ...], *, max_examples: int = 10_000
) -> RAGEvaluationReport:
    """Aggregate bounded example evidence without invoking a judge provider."""
    if not evaluations or len(evaluations) > max_examples:
        raise ValueError("RAG evaluation dataset must contain between 1 and max_examples entries")
    ordered = tuple(sorted(evaluations, key=lambda item: item.example_id))
    if len({item.example_id for item in ordered}) != len(ordered):
        raise ValueError("RAG evaluation example identifiers must be unique")
    count = len(ordered)
    return RAGEvaluationReport(
        ordered,
        sum(item.retrieval_precision for item in ordered) / count,
        sum(item.retrieval_recall for item in ordered) / count,
        sum(item.answer_exact_match for item in ordered) / count,
    )


def evaluate_rag_payload(payload: object, *, max_examples: int = 1000) -> RAGEvaluationReport:
    """Evaluate the bounded JSON dataset accepted by the public GenAI route."""

    if not isinstance(payload, dict) or set(payload) != {"examples"}:
        raise ValueError("RAG evaluation payload must contain only examples")
    raw_examples = payload["examples"]
    if not isinstance(raw_examples, list) or not raw_examples or len(raw_examples) > max_examples:
        raise ValueError("RAG evaluation examples are outside the allowed bounds")
    evaluations: list[RAGEvaluation] = []
    required = {
        "example_id", "expected_chunks", "retrieved_chunks", "expected_answer", "actual_answer"
    }
    for raw in raw_examples:
        if not isinstance(raw, dict) or set(raw) != required:
            raise ValueError("RAG evaluation example has invalid shape")
        values = [raw["expected_chunks"], raw["retrieved_chunks"]]
        if not all(
            isinstance(value, list) and all(isinstance(item, str) for item in value)
            for value in values
        ):
            raise ValueError("RAG evaluation chunks must be string lists")
        if not all(
            isinstance(raw[key], str)
            for key in ("example_id", "expected_answer", "actual_answer")
        ):
            raise ValueError("RAG evaluation identity and answers must be strings")
        evaluations.append(
            evaluate_rag_example(
                raw["example_id"],
                expected_chunks=tuple(raw["expected_chunks"]),
                retrieved_chunks=tuple(raw["retrieved_chunks"]),
                expected_answer=raw["expected_answer"],
                actual_answer=raw["actual_answer"],
            )
        )
    return summarize_rag_evaluation(tuple(evaluations), max_examples=max_examples)


def evaluate_rag_example(
    example_id: str,
    *,
    expected_chunks: tuple[str, ...],
    retrieved_chunks: tuple[str, ...],
    expected_answer: str,
    actual_answer: str,
) -> RAGEvaluation:
    """Score one bounded example without invoking a judge provider."""
    if not example_id or len(example_id) > 256 or any(c in example_id for c in "\r\n\x00"):
        raise ValueError("example_id must be a bounded single-line identifier")
    if len(expected_chunks) > 1000 or len(retrieved_chunks) > 1000:
        raise ValueError("RAG chunk lists are bounded to 1000 entries")
    duplicate_expected = len(set(expected_chunks)) != len(expected_chunks)
    duplicate_retrieved = len(set(retrieved_chunks)) != len(retrieved_chunks)
    if duplicate_expected or duplicate_retrieved:
        raise ValueError("RAG chunk identifiers must be unique")
    if not isinstance(expected_answer, str) or not isinstance(actual_answer, str):
        raise ValueError("RAG answers must be strings")
    expected = set(expected_chunks)
    retrieved = set(retrieved_chunks)
    overlap = len(expected & retrieved)
    precision = overlap / len(retrieved) if retrieved else 0.0
    recall = overlap / len(expected) if expected else (1.0 if not retrieved else 0.0)
    return RAGEvaluation(
        example_id,
        expected_chunks,
        retrieved_chunks,
        expected_answer,
        actual_answer,
        precision,
        recall,
        1.0 if expected_answer.strip() == actual_answer.strip() else 0.0,
    )


__all__ = (
    "RAGEvaluation",
    "RAGEvaluationReport",
    "evaluate_rag_example",
    "summarize_rag_evaluation",
    "evaluate_rag_payload",
)
