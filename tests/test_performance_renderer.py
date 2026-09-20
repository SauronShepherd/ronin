from ronin_plugin_performance.renderer import render_report


def test_renderer_is_accessible_and_escapes_stage_labels():
    html = render_report(
        {
            "score": 88,
            "series": {
                "stages": [
                    {"id": "<stage>", "duration_ms": 10, "shuffle_bytes": 20, "spill_bytes": 0}
                ]
            },
        }
    )
    assert "Performance Studio" in html
    assert "&lt;stage&gt;" in html
    assert 'scope="row"' in html
