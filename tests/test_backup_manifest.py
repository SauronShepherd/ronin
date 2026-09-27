import hashlib

from studio_storage import BackupManifest, sha256_file


def test_backup_manifest_round_trip_binds_database_and_artifacts(tmp_path):
    database = tmp_path / "dump.bin"
    database.write_bytes(b"database-dump")
    database_digest = hashlib.sha256(database.read_bytes()).hexdigest()
    artifact = hashlib.sha256(b"artifact").hexdigest()
    manifest = BackupManifest(database_digest, (artifact,))
    assert BackupManifest.from_json(manifest.to_json()) == manifest
    assert sha256_file(database) == database_digest
