"""Exhaustive product contracts for high-cardinality historical survivors."""

from __future__ import annotations

import pytest
from studio_core import (
    ActionType,
    AssetId,
    AssetRef,
    AssetVersion,
    CapabilityRequirement,
    ExecutionProfile,
    KnowledgeObject,
    KnowledgeObjectRef,
    LinkType,
    ObjectType,
    Project,
    ProjectId,
    ProjectManifest,
    PropertyDefinition,
    RepositoryBinding,
    ResourceScope,
    RuntimeProfileRef,
    execute_ontology_action,
    grants,
    materialize_object_type,
    project_manifest,
    resolve_link_type,
)


def _requirement(action: str = "read", kind: str = "project", identifier: str | None = "p-1"):
    return grants.Requirement(action, ResourceScope(kind, identifier))


@pytest.mark.parametrize(
    ("decoder", "value", "name"),
    [
        (project_manifest._repository_from_data, [], "repository"),
        (project_manifest._execution_from_data, "invalid", "execution"),
        (project_manifest._requirement_from_data, None, "requirement"),
    ],
)
def test_manifest_nested_decoders_fail_closed_on_non_objects(decoder, value, name) -> None:
    with pytest.raises(TypeError, match=rf"^{name} must be an object with string keys$"):
        decoder(value)


@pytest.mark.parametrize(
    "value",
    [None, 1, "", " ", " leading", "trailing ", "line\nvalue", "line\rvalue", "nul\x00value"],
)
def test_grant_text_contract_rejects_noncanonical_values(value: object) -> None:
    with pytest.raises(ValueError, match="."):
        grants._require_text(value, "field")  # type: ignore[arg-type]


@pytest.mark.parametrize("action", sorted(grants.ACTIONS))
def test_grant_action_validator_accepts_only_every_declared_action(action: str) -> None:
    assert grants._require_action(action) == action


@pytest.mark.parametrize("kind", sorted(grants.RESOURCE_KINDS))
def test_grant_resource_kind_validator_accepts_only_every_declared_kind(kind: str) -> None:
    assert grants._require_resource_kind(kind) == kind


@pytest.mark.parametrize("value", ["admin", "PROJECT", "", " project"])
def test_grant_action_validator_is_fail_closed(value: str) -> None:
    with pytest.raises(ValueError, match="^unsupported authorization action$"):
        grants._require_action(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["dataset", "PROJECT", "", " project"])
def test_grant_resource_kind_validator_is_fail_closed(value: str) -> None:
    with pytest.raises(ValueError, match="^unsupported authorization resource kind$"):
        grants._require_resource_kind(value)  # type: ignore[arg-type]


def test_constraint_items_preserve_mapping_and_tuple_inputs_exactly() -> None:
    assert grants._constraint_items({"z": "last", "a": "first"}) == (
        ("a", "first"),
        ("z", "last"),
    )
    assert grants._constraint_items((("z", "last"), ("a", "first"))) == (
        ("a", "first"),
        ("z", "last"),
    )


@pytest.mark.parametrize("items", [[(1, "value")], [("key", 1)], [(1, 1)]])
def test_constraint_items_require_string_keys_and_values(
    items: list[tuple[object, object]],
) -> None:
    with pytest.raises(
        ValueError, match="^authorization constraint keys and values must be strings$"
    ):
        grants._constraint_items(tuple(items))  # type: ignore[arg-type]


def test_constraint_items_reports_key_and_value_context_and_duplicate_keys() -> None:
    with pytest.raises(ValueError, match="^authorization constraint key must be non-empty"):
        grants._constraint_items({"": "value"})
    with pytest.raises(ValueError, match="^authorization constraint value must be non-empty"):
        grants._constraint_items({"key": ""})
    with pytest.raises(ValueError, match="^authorization constraint keys must be unique$"):
        grants._constraint_items((("key", "one"), ("key", "two")))


@pytest.mark.parametrize(
    "term",
    [
        "password",
        "secret",
        "token",
        "credential",
        "api_key",
        "api-key",
        "private_key",
        "private-key",
        "access_key",
        "access-key",
    ],
)
def test_constraint_items_reject_each_sensitive_key_marker_case_insensitively(term: str) -> None:
    with pytest.raises(
        ValueError, match="^authorization constraints must not contain credential material$"
    ):
        grants._constraint_items({f"prefix-{term.upper()}-suffix": "value"})


@pytest.mark.parametrize("value", ["Bearer opaque", "-----BEGIN PRIVATE KEY-----secret"])
def test_constraint_items_reject_credential_value_shapes(value: str) -> None:
    with pytest.raises(
        ValueError, match="^authorization constraints must not contain credential material$"
    ):
        grants._constraint_items({"team": value})


def test_constraint_items_distinguishes_safe_near_misses_and_enforces_limits() -> None:
    assert grants._constraint_items({"team": "bearerish", "material": "private key"}) == (
        ("material", "private key"),
        ("team", "bearerish"),
    )
    with pytest.raises(ValueError, match="^authorization constraints must contain at most"):
        grants._constraint_items({f"k{i}": str(i) for i in range(grants.MAX_CONSTRAINTS + 1)})


@pytest.mark.parametrize(
    ("grant", "requirement", "covered"),
    [
        (ResourceScope("*", None), ResourceScope("project", "p"), True),
        (ResourceScope("project", None), ResourceScope("project", "p"), True),
        (ResourceScope("project", None), ResourceScope("project", None), True),
        (ResourceScope("project", "p"), ResourceScope("project", "p"), True),
        (ResourceScope("project", "p"), ResourceScope("project", "q"), False),
        (ResourceScope("project", "p"), ResourceScope("job", "p"), False),
        (ResourceScope("project", "p"), ResourceScope("project", None), False),
    ],
)
def test_resource_coverage_is_exact_for_global_kind_and_identifiers(
    grant: ResourceScope, requirement: ResourceScope, covered: bool
) -> None:
    assert grants._resource_covers(grant, requirement) is covered


@pytest.mark.parametrize(
    ("scope", "expected"),
    [
        (ResourceScope("*", None), 0),
        (ResourceScope("project", None), 1),
        (ResourceScope("project", "p"), 2),
    ],
)
def test_resource_specificity_has_three_stable_levels(scope: ResourceScope, expected: int) -> None:
    assert grants._specificity(scope) == expected


@pytest.mark.parametrize(
    ("requirement", "encoded"),
    [
        (_requirement("read", "project", "p-1"), "ronin:v1:read:project:p-1"),
        (
            _requirement("evidence:read", "evidence", "a/b"),
            "ronin:v1:evidence%3Aread:evidence:a%2Fb",
        ),
        (_requirement("list", "project", None), "ronin:v1:list:project:*"),
    ],
)
def test_bearer_scope_encoding_is_exact_for_normal_escaped_and_wildcard_values(
    requirement: grants.Requirement, encoded: str
) -> None:
    assert grants.requirement_to_bearer_scope(requirement) == encoded
    assert grants.parse_bearer_scope(encoded) == requirement


def test_bearer_scope_parser_requires_canonical_encoding_and_exact_components() -> None:
    with pytest.raises(ValueError, match="^bearer scope must use canonical v1 encoding$"):
        grants.parse_bearer_scope("ronin:v1:read:project:p%2f1")
    with pytest.raises(ValueError, match="^bearer scope identifier cannot encode the wildcard$"):
        grants.parse_bearer_scope("ronin:v1:read:project:%2A")


def _object_type(name: str = "Order") -> ObjectType:
    return ObjectType(
        name,
        AssetRef(AssetId(name.lower()), AssetVersion("1")),
        ("id",),
        (
            PropertyDefinition("id", "string", "id", True),
            PropertyDefinition("label", "string", "label"),
        ),
    )


def _objects(name: str, rows: tuple[dict[str, object], ...]) -> tuple[KnowledgeObject, ...]:
    return materialize_object_type(_object_type(name), rows)


def test_ontology_action_dispatch_enforces_target_inputs_authorization_and_output_mapping() -> None:
    action = ActionType("rename", "Order", ("label",))
    target = KnowledgeObjectRef("Order", (("id", "o1"),))
    with pytest.raises(ValueError, match="target type"):
        execute_ontology_action(
            action,
            KnowledgeObjectRef("Customer", (("id", "c1"),)),
            {"label": "x"},
            authorize=lambda _: True,
            write=lambda *_: {},
        )
    with pytest.raises(ValueError, match="inputs must exactly"):
        execute_ontology_action(action, target, {}, authorize=lambda _: True, write=lambda *_: {})
    with pytest.raises(ValueError, match="write executor must return"):
        execute_ontology_action(
            action, target, {"label": "x"}, authorize=lambda _: True, write=lambda *_: None
        )  # type: ignore[return-value]


def test_ontology_action_dispatch_denies_requirements_and_records_idempotent_execution() -> None:
    requirement = _requirement("execute", "job", "job-1")
    action = ActionType("approve", "Order", requirements=(requirement,), idempotent=True)
    target = KnowledgeObjectRef("Order", (("id", "o1"),))
    with pytest.raises(ValueError, match="require an idempotency_key"):
        execute_ontology_action(action, target, {}, authorize=lambda _: True, write=lambda *_: {})
    with pytest.raises(PermissionError, match="authorization requirement"):
        execute_ontology_action(
            action, target, {}, authorize=lambda _: False, write=lambda *_: {}, idempotency_key="r1"
        )
    recorded: list[object] = []
    result = execute_ontology_action(
        action,
        target,
        {},
        authorize=lambda _: True,
        write=lambda *_: {"ok": True},
        idempotency_key="r1",
        record_idempotent=recorded.append,
    )
    assert result.output == {"ok": True}
    assert recorded == [result]


def test_materialization_enforces_limits_and_preserves_properties() -> None:
    obj = _object_type()
    assert materialize_object_type(obj, ({"id": 1, "label": "one"},))[0].properties == (
        ("id", 1),
        ("label", "one"),
    )
    with pytest.raises(ValueError, match="max_objects"):
        materialize_object_type(obj, (), max_objects=0)
    with pytest.raises(ValueError, match="missing required fields"):
        materialize_object_type(obj, ({"label": "missing"},))
    with pytest.raises(ValueError, match="missing/null key field"):
        materialize_object_type(obj, ({"id": None, "label": "null"},))
    with pytest.raises(ValueError, match="key is duplicated"):
        materialize_object_type(obj, ({"id": 1}, {"id": 1}))
    with pytest.raises(ValueError, match="exceeds configured limit"):
        materialize_object_type(obj, ({"id": 1}, {"id": 2}), max_objects=1)


def test_link_resolution_enforces_type_limits_and_cardinality() -> None:
    source = _objects("Source", ({"id": "s1", "label": "x"},))
    target = _objects("Target", ({"id": "t1", "label": "x"}, {"id": "t2", "label": "x"}))
    link = LinkType("link", "Source", "Target", "many-to-many", ("label",), ("label",))
    assert len(resolve_link_type(link, source, target)) == 2
    with pytest.raises(ValueError, match="max_links"):
        resolve_link_type(link, source, target, max_links=0)
    with pytest.raises(ValueError, match="source objects"):
        resolve_link_type(link, target, target)
    one_to_one = LinkType("link", "Source", "Target", "one-to-one", ("label",), ("label",))
    with pytest.raises(ValueError, match="source-side cardinality"):
        resolve_link_type(one_to_one, source, target)


def _manifest_data() -> dict[str, object]:
    project = Project(
        ProjectId("orders"),
        "Orders",
        (RepositoryBinding("code", "https://example.test/orders.git", role="primary"),),
        ExecutionProfile(
            RuntimeProfileRef("python", "3.13"), (CapabilityRequirement("python"),), "strict"
        ),
    )
    return ProjectManifest.from_project(project).to_data()


def test_project_manifest_parser_accepts_optional_null_runtime_and_constraint() -> None:
    data = _manifest_data()
    project = data["project"]
    assert isinstance(project, dict)
    execution = project["execution"]
    assert isinstance(execution, dict)
    execution["runtime"] = None
    requirement = execution["requirements"][0]
    assert isinstance(requirement, dict)
    requirement["constraint"] = None
    restored = ProjectManifest.from_data(data)
    assert restored.project.execution.runtime is None
    assert restored.project.execution.requirements[0].constraint is None


@pytest.mark.parametrize("field", ["role", "sync_policy"])
def test_project_manifest_repository_enum_fields_fail_closed(field: str) -> None:
    data = _manifest_data()
    repository = data["project"]["repositories"][0]  # type: ignore[index]
    repository[field] = "unsupported"  # type: ignore[index]
    with pytest.raises(ValueError, match=rf"repository\.{field}"):
        ProjectManifest.from_data(data)


def test_project_manifest_parser_validates_optional_and_required_nested_types() -> None:
    data = _manifest_data()
    repository = data["project"]["repositories"][0]  # type: ignore[index]
    repository["subdirectory"] = 1  # type: ignore[index]
    with pytest.raises(TypeError, match="subdirectory"):
        ProjectManifest.from_data(data)
    data = _manifest_data()
    requirement = data["project"]["execution"]["requirements"][0]  # type: ignore[index]
    requirement["constraint"] = 1  # type: ignore[index]
    with pytest.raises(TypeError, match="constraint"):
        ProjectManifest.from_data(data)
    data = _manifest_data()
    data["project"]["execution"]["resolution"] = "unknown"  # type: ignore[index]
    with pytest.raises(ValueError, match="execution.resolution"):
        ProjectManifest.from_data(data)


def test_project_manifest_private_shape_helpers_distinguish_mapping_sequence_and_string() -> None:
    assert project_manifest._require_mapping({"x": 1}, "value")["x"] == 1
    assert project_manifest._require_sequence([1, 2], "value") == [1, 2]
    with pytest.raises(TypeError, match="value must be an object"):
        project_manifest._require_mapping({1: "bad"}, "value")
    with pytest.raises(TypeError, match="value must be an array"):
        project_manifest._require_sequence("text", "value")
    with pytest.raises(TypeError, match="value must be a string"):
        project_manifest._require_str(1, "value")


def test_project_manifest_exact_keys_reports_both_missing_and_extra_keys() -> None:
    with pytest.raises(ValueError, match=r"^value keys mismatch; missing=\['b'\], extra=\['c'\]$"):
        project_manifest._require_exact_keys({"a": 1, "c": 2}, {"a", "b"}, "value")


@pytest.mark.parametrize("field", ["alias", "uri", "default_ref", "adapter_id"])
def test_project_manifest_repository_requires_each_text_field(field: str) -> None:
    data = _manifest_data()
    repository = data["project"]["repositories"][0]  # type: ignore[index]
    repository[field] = 1  # type: ignore[index]
    with pytest.raises(TypeError, match=rf"repository\.{field} must be a string"):
        ProjectManifest.from_data(data)


def test_project_manifest_execution_requires_array_runtime_and_valid_resolution_shapes() -> None:
    data = _manifest_data()
    execution = data["project"]["execution"]  # type: ignore[index]
    execution["requirements"] = "not-an-array"  # type: ignore[index]
    with pytest.raises(TypeError, match="execution.requirements must be an array"):
        ProjectManifest.from_data(data)
    data = _manifest_data()
    execution = data["project"]["execution"]  # type: ignore[index]
    execution["runtime"] = "not-an-object"  # type: ignore[index]
    with pytest.raises(TypeError, match="execution.runtime must be an object"):
        ProjectManifest.from_data(data)
    data = _manifest_data()
    execution = data["project"]["execution"]  # type: ignore[index]
    execution["resolution"] = 1  # type: ignore[index]
    with pytest.raises(TypeError, match="execution.resolution must be a string"):
        ProjectManifest.from_data(data)


@pytest.mark.parametrize("field", ["name", "level"])
def test_project_manifest_requirement_requires_text_fields_and_supported_level(field: str) -> None:
    data = _manifest_data()
    requirement = data["project"]["execution"]["requirements"][0]  # type: ignore[index]
    requirement[field] = 1  # type: ignore[index]
    with pytest.raises(TypeError, match=rf"requirement\.{field} must be a string"):
        ProjectManifest.from_data(data)
    data = _manifest_data()
    requirement = data["project"]["execution"]["requirements"][0]  # type: ignore[index]
    requirement["level"] = "optional"  # type: ignore[index]
    with pytest.raises(ValueError, match="requirement.level"):
        ProjectManifest.from_data(data)


def test_project_manifest_runtime_payload_round_trips_all_optional_fields() -> None:
    data = _manifest_data()
    restored = ProjectManifest.from_data(data)
    encoded = restored.to_json()
    assert ProjectManifest.from_json(encoded) == restored
