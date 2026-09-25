import pytest

from studio_storage import SourceCheckpointConflict, SqliteSourceCheckpointStore


def test_source_checkpoint_store_advances_only_from_expected_generation(tmp_path) -> None:
    with SqliteSourceCheckpointStore(tmp_path / "checkpoints.db") as store:
        first = store.compare_and_set("asset-1", None, "cursor-1")
        second = store.compare_and_set("asset-1", first, "cursor-2")
        assert second.generation == 2
        with pytest.raises(SourceCheckpointConflict):
            store.compare_and_set("asset-1", first, "cursor-3")
