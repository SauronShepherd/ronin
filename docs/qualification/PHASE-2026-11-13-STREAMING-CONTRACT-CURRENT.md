# Qualification receipt — streaming contracts and local runtime current

- Date: 2026-11-13
- Source checkout: `0ceb55083f2bc03acd66d20ccd7e4533b7d1a3ee`
- Command: `python -m pytest -q tests/test_stream_table.py tests/test_stream_scheduler_bridge.py tests/test_streaming_bundle.py tests/test_streaming_health.py tests/test_streaming_kafka.py tests/test_streaming_runtime.py tests/test_streaming_windows.py tests/integration/test_workspace_project_http_api.py -k streaming`.
- Result: **30 passed, 0 failed**; 57 unrelated cases were deselected.
- Scope: checkpoint-addressed table writes, scheduler bridge, portable Bundle import/export, health, Kafka polling, runtime sinks, event-time windows and streaming HTTP routes.
- Boundary: this closes the current local contract/runtime lane and complements the real Redpanda receipt; provider breadth, long-running distributed stateful operation, external schema registry, full-family release qualification and legal/provider gates remain open.
