"""OpenAPI-to-LinkML import with source-aware corrections."""

from copy import deepcopy
from pathlib import Path
from tempfile import NamedTemporaryFile
import warnings

from linkml.linter.linter import Linter
from linkml_runtime.dumpers import yaml_dumper
from linkml_runtime.linkml_model import SchemaDefinition
from linkml_runtime.linkml_model.annotations import Annotation
from linkml_runtime.linkml_model.meta import AnonymousSlotExpression
from schema_automator.importers.jsonschema_import_engine import JsonSchemaImportEngine

from ess_dive_schemas.publish import JsonObject, resolve_schema_ref


SCALAR_RANGES = {
    "boolean": "boolean",
    "integer": "integer",
    "number": "float",
    "string": "string",
}
ANNOTATED_CONSTRAINTS = (
    "default",
    "enum",
    "format",
    "maxLength",
    "minLength",
    "uniqueItems",
)
SUPPORTED_BRANCH_KEYS = {
    "$ref",
    "description",
    "items",
    "maxItems",
    "minItems",
    "pattern",
    "title",
    "type",
} | set(ANNOTATED_CONSTRAINTS)


def _constraint_annotations(*schemas: JsonObject) -> dict[str, Annotation]:
    """Retain constraints that have no equivalent anonymous LinkML expression."""
    annotations: dict[str, Annotation] = {}
    for source in schemas:
        for keyword in ANNOTATED_CONSTRAINTS:
            if keyword in source:
                tag = f"json_schema_{keyword}"
                annotations[tag] = Annotation(tag=tag, value=deepcopy(source[keyword]))
    return annotations


def _range_for_schema(fragment: JsonObject, source: JsonObject) -> tuple[str, bool]:
    """Return the LinkML range and whether it is a class-valued reference."""
    if "$ref" in source:
        name, _ = resolve_schema_ref(fragment, source["$ref"])
        return name, True
    source_type = source.get("type")
    if source_type not in SCALAR_RANGES:
        raise ValueError(f"Unsupported anyOf branch type: {source_type!r}")
    return SCALAR_RANGES[source_type], False


def _translate_any_of_branch(fragment: JsonObject, branch: JsonObject) -> AnonymousSlotExpression:
    """Translate one scalar/ref or array branch without collapsing the alternatives."""
    unsupported = set(branch) - SUPPORTED_BRANCH_KEYS
    if unsupported:
        raise ValueError(f"Unsupported anyOf branch keywords: {sorted(unsupported)}")

    is_array = branch.get("type") == "array"
    value_schema = branch.get("items") if is_array else branch
    if not isinstance(value_schema, dict):
        raise ValueError("An array anyOf branch must have an object-valued items schema")
    unsupported_items = set(value_schema) - SUPPORTED_BRANCH_KEYS
    if unsupported_items:
        raise ValueError(f"Unsupported anyOf item keywords: {sorted(unsupported_items)}")

    range_name, class_valued = _range_for_schema(fragment, value_schema)
    return AnonymousSlotExpression(
        range=range_name,
        multivalued=is_array,
        inlined=True if class_valued else None,
        minimum_cardinality=branch.get("minItems") if is_array else None,
        maximum_cardinality=branch.get("maxItems") if is_array else None,
        pattern=value_schema.get("pattern"),
        title=value_schema.get("title") or branch.get("title"),
        description=value_schema.get("description") or branch.get("description"),
        annotations=_constraint_annotations(branch, value_schema),
    )


def correct_any_of(schema: SchemaDefinition, fragment: JsonObject) -> None:
    """Restore property-level JSON Schema anyOf alternatives omitted by the importer."""
    definitions = fragment["components"]["schemas"]
    for class_name, definition in definitions.items():
        if class_name not in schema.classes:
            continue
        for property_name, source_property in definition.get("properties", {}).items():
            alternatives = source_property.get("anyOf")
            if alternatives is None:
                continue
            if not isinstance(alternatives, list) or not alternatives:
                raise ValueError(f"{class_name}.{property_name} has an invalid anyOf")
            slot = schema.classes[class_name].attributes.get(property_name)
            if slot is None:
                raise ValueError(f"Importer omitted {class_name}.{property_name}")
            slot.range = None
            slot.multivalued = None
            slot.inlined = None
            slot.minimum_cardinality = None
            slot.maximum_cardinality = None
            slot.any_of = [
                _translate_any_of_branch(fragment, branch)
                for branch in alternatives
            ]


def _prepare_schema_automator_input(fragment: JsonObject) -> JsonObject:
    """Give the importer placeholders for anyOf properties corrected afterward."""
    prepared = deepcopy(fragment)
    for definition in prepared["components"]["schemas"].values():
        for property_name, source_property in list(definition.get("properties", {}).items()):
            if "anyOf" not in source_property:
                continue
            placeholder = {"type": "string"}
            for keyword in ("title", "description"):
                if keyword in source_property:
                    placeholder[keyword] = source_property[keyword]
            definition["properties"][property_name] = placeholder
    return prepared


def validate_linkml(path: Path) -> None:
    """Validate serialized LinkML against the LinkML metamodel."""
    problems = list(Linter.validate_schema(str(path)))
    if problems:
        messages = "; ".join(problem.message for problem in problems)
        raise ValueError(f"Generated LinkML failed metamodel validation: {messages}")


def convert_to_linkml(fragment: JsonObject) -> SchemaDefinition:
    """Import the selected OpenAPI components using Schema Automator.

    Class-local attributes prevent identically named fields in different classes
    from overwriting each other's definitions. Work on a copy so the original
    JSON remains available for comparison with this lossy first pass.

    Property-level anyOf is corrected from the unchanged source fragment after
    import. JSON Schema constraints without an anonymous-expression equivalent
    are retained as json_schema_* annotations instead of silently discarded.

    TODO: review and implement mappings for allOf, nullable values, defaults,
    bounds, JSON-LD keys/URIs, and other omitted source constraints.
    TODO: validate semantic equivalence using real accepted/rejected datasets
    before treating this draft as a schema suitable for Bridge.
    """
    if "Dataset" not in fragment.get("components", {}).get("schemas", {}):
        raise ValueError("Expected selected OpenAPI components containing Dataset")
    warnings.warn(
        "Draft LinkML import remains lossy: allOf and other source constraints "
        "may be omitted.",
        UserWarning, stacklevel=2,
    )
    engine = JsonSchemaImportEngine(is_openapi=True, use_attributes=True)
    schema = engine.loads(
        _prepare_schema_automator_input(fragment),
        name="ess_dive_dataset",
        root_class_name="Dataset",
    )
    # Use the repository URI rather than the importer's example.org default.
    schema.id = "https://github.com/ess-dive/ess-dive-schemas"
    schema.prefixes[schema.default_prefix].prefix_reference = str(schema.id) + "/"
    schema.classes["Dataset"].tree_root = True
    correct_any_of(schema, fragment)
    schema.description = (
        "DRAFT: generated from ESS-DIVE OpenAPI. Property-level anyOf alternatives "
        "are source-corrected; other conversion gaps still require review."
    )
    return schema


def write_linkml(fragment: JsonObject, output: Path) -> SchemaDefinition:
    """Serialize and validate LinkML atomically, leaving the JSON untouched."""
    schema = convert_to_linkml(fragment)
    content = yaml_dumper.dumps(schema)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent, suffix=".yaml", delete=False
        ) as stream:
            stream.write(content)
            temporary = Path(stream.name)
        validate_linkml(temporary)
        temporary.replace(output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return schema
