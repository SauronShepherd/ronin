import json
from pathlib import Path

from ronin_plugin_performance.cli import main


def test_cli_emits_json_and_optional_html(tmp_path: Path, capsys):
    run = tmp_path / "run.json"
    output = tmp_path / "report.html"
    run.write_text(
        json.dumps({"run_id": "cli", "stages": [{"id": 1, "duration_ms": 10}]}), encoding="utf-8"
    )
    assert main([str(run), "--html", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["run_id"] == "cli"
    assert "Performance Studio" in output.read_text(encoding="utf-8")
