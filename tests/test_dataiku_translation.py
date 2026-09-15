from __future__ import annotations

from studio_migration import translate_code_recipes


def test_dataiku_code_recipes_translate_and_opaque_recipe_is_reported() -> None:
    result = translate_code_recipes(
        '{"id":"dataiku-1","recipes":[{"id":"py-1","type":"python","source":"print(1)"},{"id":"sql-1","type":"sql","source":"select 1"},{"id":"visual-1","type":"visual"}]}',
    )
    assert {node.operator.name for node in result.workflow.pipeline.nodes} == {"code.python", "sql.query"}
    assert {item.status for item in result.report.objects} == {"translated", "unsupported"}
