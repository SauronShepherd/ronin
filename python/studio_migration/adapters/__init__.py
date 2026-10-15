"""Source adapters for Migration Studio."""

from .iics import IICS_ADAPTER_VERSION, discover_iics_zip

__all__ = ("IICS_ADAPTER_VERSION", "discover_iics_zip")
