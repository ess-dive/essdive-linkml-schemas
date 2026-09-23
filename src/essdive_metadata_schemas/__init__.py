"""Reviewed ESS-DIVE metadata schema package."""

from pathlib import Path

SCHEMA_DIRECTORY = Path(__file__).parent / "schema"
MAIN_SCHEMA_PATH = SCHEMA_DIRECTORY / "essdive_metadata_schemas.yaml"

try:
    from importlib.metadata import version
    __version__ = version("essdive-metadata-schemas")
except ImportError:
    __version__ = "0.0.0"
