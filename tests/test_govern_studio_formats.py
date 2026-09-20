import json

import pytest
from studio_synthetic_data import (
    DeclarativeTableProvider,
    ExporterRegistry,
    FormatManifest,
    GenerationPlan,
    JsonExporter,
    TableSpec,
    XmlExporter,
    builtin_format_providers,
    builtin_table_format_manifests,
    format_availability,
    generate,
)
from studio_synthetic_data.plugin import GovernStudioPlugin


def _table():
    return generate(GenerationPlan((TableSpec("events", (), rows=0),), seed=7)).tables[0]


def test_builtin_file_formats_are_registered_and_round_trip_shapes_are_clear() -> None:
    registry = ExporterRegistry(tuple(builtin_format_providers()))
    assert registry.formats == ("csv", "json", "jsonl", "xml")
    assert json.loads(registry.export("json", _table())) == []
    assert registry.export("jsonl", _table()) == ""
    assert registry.export("xml", _table()).startswith('<table name="events"')


def test_xml_rejects_unsafe_element_names() -> None:
    with pytest.raises(ValueError, match="XML row element"):
        XmlExporter(row_element="row><evil")


def test_format_manifest_distinguishes_table_provider() -> None:
    manifest = FormatManifest("iceberg", "table", "1.0", frozenset({"snapshots"}), ("v2",))
    assert manifest.family == "table"
    assert manifest.protocol_versions == ("v2",)


def test_table_formats_are_capability_manifests_until_real_writers_are_installed() -> None:
    manifests = builtin_table_format_manifests()
    assert {manifest.format_id for manifest in manifests} == {"delta", "iceberg", "hudi"}
    provider = DeclarativeTableProvider(manifests[0])
    provider.validate_protocol(manifests[0].protocol_versions[0])
    with pytest.raises(RuntimeError, match="writer is not installed"):
        provider.export(_table())


def test_json_exporter_is_explicitly_file_family() -> None:
    assert JsonExporter.manifest.family == "file"


def test_format_availability_does_not_claim_uninstalled_table_writers() -> None:
    availability = {item.format_id: item for item in format_availability()}
    assert availability["csv"].status == "ready"
    assert availability["jsonl"].status == "ready"
    assert availability["delta"].status == "optional_missing"
    assert "deltalake" in availability["delta"].missing_dependencies


def test_plugin_exposes_format_inventory() -> None:
    formats = GovernStudioPlugin().formats()
    ids = {item["format_id"] for item in formats}
    assert {"csv", "json", "jsonl", "xml", "delta", "iceberg", "hudi"} <= ids
