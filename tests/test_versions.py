from studio_core.versions import compare_releases, parse_comparable_release


def test_release_comparison_orders_prerelease_before_final_in_both_directions() -> None:
    assert compare_releases("3.11.0rc1", "3.11.0") == -1
    assert compare_releases("3.11.0", "3.11.0rc1") == 1


def test_release_comparison_orders_prerelease_markers_and_numbers() -> None:
    assert compare_releases("1.0beta2", "1.0rc1") == -1
    assert compare_releases("1.0rc2", "1.0rc1") == 1
    assert compare_releases("1.0rc1", "1.0rc1") == 0


def test_release_parser_rejects_non_numeric_leading_value() -> None:
    assert parse_comparable_release("latest") is None
    assert compare_releases("latest", "1.0") is None
    assert compare_releases("1.0", "latest") is None
