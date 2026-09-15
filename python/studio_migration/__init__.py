"""Deterministic source inventory and migration-report generation."""

from studio_migration.inventory import (
    MigrationInventory,
    SourceObject,
    inventory_json_document,
)
from studio_migration.profiles import (
    discover_dataiku,
    discover_databricks,
    discover_fabric,
    discover_foundry,
)
from studio_migration.databricks import DatabricksTranslation, translate_notebook_job
from studio_migration.fabric import FabricTranslation, translate_notebook_items
from studio_migration.dataiku import DataikuTranslation, translate_code_recipes
from studio_migration.foundry import FoundryTranslation, translate_python_functions
from studio_migration.qualification import TranslationQualification, qualify_fixture

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
    "inventory_json_document",
)
