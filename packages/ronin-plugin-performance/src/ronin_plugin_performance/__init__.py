"""Ronin Performance Intelligence: explainable diagnostics for assets and runtimes."""

from .adapters import (
    normalize_madlava_snapshots,
    normalize_madmamba_records,
    normalize_spark_events,
)
from .analyzer import analyze_run
from .assets import inventory_asset
from .correlation import compare_runs, correlate
from .plugin import PerformancePlugin, factory
from .policy import PerformancePolicy
from .renderer import render_report
from .resources import load_config_schema, load_ui_manifest
from .service import analyze_performance

__all__ = [
    "PerformancePlugin",
    "PerformancePolicy",
    "analyze_performance",
    "analyze_run",
    "compare_runs",
    "correlate",
    "factory",
    "inventory_asset",
    "normalize_madmamba_records",
    "normalize_madlava_snapshots",
    "normalize_spark_events",
    "render_report",
    "load_config_schema",
    "load_ui_manifest",
]
