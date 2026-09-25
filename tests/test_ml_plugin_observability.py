"""ML Studio run observability contract tests."""

import pytest

from studio_ml.plugin import MachineLearningStudioPlugin


class _Registry:
    def get_run(self, _workspace_id, _run_id):
        return None


def test_get_run_reports_missing_run() -> None:
    plugin = MachineLearningStudioPlugin()
    plugin._registry = _Registry()
    with pytest.raises(KeyError):
        plugin.get_run("ws", "missing")
