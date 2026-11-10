from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_posix_contract_qualification.ps1"


def test_posix_runner_is_digest_pinned_and_mounts_checkout_read_only() -> None:
    script = RUNNER.read_text(encoding="utf-8")

    assert "sha256:fb9029dad0d8d5aade4bb5809c8a4e027f416a158fedc633c65667d0b21b01b8" in script
    assert "^sha256:[0-9a-f]{64}$" in script
    assert "-c /workspace/requirements-test.lock" in script
    assert "-r /workspace/tools/posix-test-requirements.lock" in script
    assert "--require-hashes" in script
    assert '$mountRepo = "type=bind,source=$repoRoot,target=/workspace,readonly"' in script
    assert '"--network", "bridge", "--user", "0:0"' in script
    assert '$dockerArgs += @("--env", $name)' in script
    assert '$runtimeScript = $runtimeScript -replace "`r`n", "`n"' in script


def test_posix_runner_selects_the_complete_previously_skipped_platform_set() -> None:
    script = RUNNER.read_text(encoding="utf-8")

    expected = (
        "test_untracked_executable_mode_changes_dirty_identity",
        "test_mounted_file_secret_resolver_rejects_symlinks",
        "test_safe_checkout_path_rejects_escape_and_symlink",
        "test_posix_returncode_fallback_does_not_poll_and_reap_native_process",
        "test_source_text_rejects_nul_and_safe_checkout_rejects_symlink_components",
        "test_safe_checkout_path_rejects_escape_and_symlink_traversal",
        "test_mounted_file_secret_rejects_broad_permissions",
        "test_connector_rejects_symlink",
    )
    assert all(script.count(nodeid) >= 2 for nodeid in expected)
    assert "$skipped -ne 0" in script
    assert "$failed -ne 0" in script
    assert "$timingSummary.executed -ne $expectedTests.Count" in script


def test_posix_runner_retains_junit_timing_git_version_and_cleanup_evidence() -> None:
    script = RUNNER.read_text(encoding="utf-8")

    assert '"posix-junit.xml"' in script
    assert '"pytest-timings.json"' in script
    assert '"git-version.txt"' in script
    assert "cleanup_status = $cleanupStatus" in script
    assert '"succeeded"' in script
    assert "docker ps -a --filter" in script
