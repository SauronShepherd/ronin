"""Deterministic source inventory and migration-report generation."""

from studio_migration.adapters import IICS_ADAPTER_VERSION, discover_iics_zip
from studio_migration.analysis import Finding, analyze_pyspark
from studio_migration.api import MIGRATION_ROUTES, APIResponse, MigrationAPIRouter
from studio_migration.benchmark import (
    BenchmarkResult,
    OptimizationDecision,
    benchmark,
    decide_promotion,
    promotion_evidence,
)
from studio_migration.blueprint import BlueprintContract, BlueprintRule, extract_blueprint
from studio_migration.databricks import DatabricksTranslation, translate_notebook_job
from studio_migration.dataiku import DataikuTranslation, translate_code_recipes
from studio_migration.evidence import (
    MigrationEvidence,
    publish_evidence_bundle,
    publish_migration_evidence,
    publish_promotion_evidence,
    publish_validation_evidence,
    validation_evidence,
)
from studio_migration.fabric import FabricTranslation, translate_notebook_items
from studio_migration.foundry import FoundryTranslation, translate_python_functions
from studio_migration.inventory import (
    MigrationInventory,
    SourceObject,
    inventory_json_document,
)
from studio_migration.model import MigrationUnit, ScopeSelection, SourceArtifact, SourceInventory
from studio_migration.profiles import (
    discover_databricks,
    discover_dataiku,
    discover_fabric,
    discover_foundry,
)
from studio_migration.pyspark_codegen import (
    GeneratedProgram,
    GeneratedProject,
    export_migration_script,
    generate_project,
    generate_pyspark,
)
from studio_migration.qualification import (
    GeneratedQualification,
    TranslationQualification,
    qualify_fixture,
    qualify_generated_project,
)
from studio_migration.reports import render_validation_html, render_validation_markdown
from studio_migration.runtime import (
    SparkQualificationEvidence,
    SparkRuntimePreflight,
    check_spark_python_runtime,
    qualify_spark_runtime,
    run_spark_smoke,
)
from studio_migration.scope import select_all, select_scope
from studio_migration.session import MigrationSession, MigrationSessionService
from studio_migration.session_store import SQLiteMigrationSessionStore
from studio_migration.spark_validation import SparkValidationPlan
from studio_migration.validation import ValidationCheck, ValidationReport, validate_results

__all__ = (
    "MigrationInventory",
    "SourceObject",
    "discover_dataiku",
    "discover_databricks",
    "discover_fabric",
    "discover_foundry",
    "DatabricksTranslation",
    "translate_notebook_job",
    "FabricTranslation",
    "translate_notebook_items",
    "DataikuTranslation",
    "translate_code_recipes",
    "FoundryTranslation",
    "translate_python_functions",
    "TranslationQualification",
    "qualify_fixture",
    "GeneratedQualification",
    "qualify_generated_project",
    "inventory_json_document",
    "MigrationUnit",
    "ScopeSelection",
    "SourceArtifact",
    "SourceInventory",
    "IICS_ADAPTER_VERSION",
    "discover_iics_zip",
    "select_all",
    "select_scope",
    "BlueprintContract",
    "BlueprintRule",
    "extract_blueprint",
    "GeneratedProgram",
    "GeneratedProject",
    "export_migration_script",
    "generate_project",
    "generate_pyspark",
    "ValidationCheck",
    "ValidationReport",
    "validate_results",
    "render_validation_html",
    "render_validation_markdown",
    "SparkValidationPlan",
    "SparkRuntimePreflight",
    "check_spark_python_runtime",
    "SparkQualificationEvidence",
    "qualify_spark_runtime",
    "run_spark_smoke",
    "Finding",
    "analyze_pyspark",
    "BenchmarkResult",
    "OptimizationDecision",
    "benchmark",
    "decide_promotion",
    "promotion_evidence",
    "MigrationSession",
    "MigrationSessionService",
    "SQLiteMigrationSessionStore",
    "APIResponse",
    "MIGRATION_ROUTES",
    "MigrationAPIRouter",
    "MigrationEvidence",
    "publish_migration_evidence",
    "publish_evidence_bundle",
    "publish_promotion_evidence",
    "publish_validation_evidence",
    "validation_evidence",
)
