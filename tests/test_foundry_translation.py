from __future__ import annotations

from studio_migration import translate_python_functions


def test_foundry_python_function_translates_and_opaque_function_is_reported() -> None:
    result = translate_python_functions(
        '{"id":"foundry-1","functions":['
        '{"id":"fn-1","source":"return 1"},'
        '{"id":"fn-2","actionType":"proprietary"}]}',
    )
    assert result.workflow.pipeline.nodes[0].operator.name == "code.python"
    assert {item.status for item in result.report.objects} == {"translated", "unsupported"}
