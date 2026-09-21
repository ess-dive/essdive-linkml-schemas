"""Experimental OpenAPI-to-LinkML import; not a lossless metadata contract."""

from copy import deepcopy
from pathlib import Path
import warnings

from linkml_runtime.dumpers import yaml_dumper
from linkml_runtime.linkml_model import SchemaDefinition
from schema_automator.importers.jsonschema_import_engine import JsonSchemaImportEngine

from ess_dive_schemas.publish import JsonObject


def convert_to_linkml(fragment: JsonObject) -> SchemaDefinition:
    """Import the selected OpenAPI components using Schema Automator.

    Class-local attributes prevent identically named fields in different classes
    from overwriting each other's definitions. Work on a copy so the original
    JSON remains available for comparison with this lossy first pass.

    TODO: review and implement mappings for unions, nullable values, defaults,
    patterns, bounds, JSON-LD keys/URIs, and other omitted source constraints.
    TODO: validate semantic equivalence using real accepted/rejected datasets
    before treating this draft as a schema suitable for Bridge.
    """
    if "Dataset" not in fragment.get("components", {}).get("schemas", {}):
        raise ValueError("Expected selected OpenAPI components containing Dataset")
    warnings.warn(
        "Draft LinkML import is lossy: unions and other source constraints may "
        "be omitted. Post-processing and semantic validation are unimplemented.",
        UserWarning, stacklevel=2,
    )
    engine = JsonSchemaImportEngine(is_openapi=True, use_attributes=True)
    schema = engine.loads(deepcopy(fragment), name="ess_dive_dataset", root_class_name="Dataset")
    # Use the repository URI rather than the importer's example.org default.
    schema.id = "https://github.com/ess-dive/ess-dive-schemas"
    schema.prefixes[schema.default_prefix].prefix_reference = str(schema.id) + "/"
    schema.classes["Dataset"].tree_root = True
    schema.description = (
        "DRAFT: generated from ESS-DIVE OpenAPI; lossy import requiring review. "
        "LinkML post-processing and semantic validation are not implemented."
    )
    return schema


def write_linkml(fragment: JsonObject, output: Path) -> SchemaDefinition:
    """Serialize the imported LinkML model as YAML, leaving the JSON untouched."""
    schema = convert_to_linkml(fragment)
    content = yaml_dumper.dumps(schema)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return schema
