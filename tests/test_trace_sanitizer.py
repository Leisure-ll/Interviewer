from __future__ import annotations

from interview_agent_runtime.observability import TraceSanitizer


def test_trace_sanitizer_does_not_store_sensitive_content():
    result = TraceSanitizer().sanitize(
        {
            "agent": "EvaluatorAgent",
            "answer_text": "candidate private answer",
            "score": 82.0,
            "nested": {"prompt": "private prompt"},
        }
    )

    assert result["agent"] == "EvaluatorAgent"
    assert result["answer_text_length"] > 0
    assert result["score"] == 82.0
    assert "prompt" not in result["nested"]
    assert "prompt_length" in result["nested"]
