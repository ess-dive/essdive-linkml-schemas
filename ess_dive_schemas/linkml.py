"""Convert the selected ESS-DIVE OpenAPI schemas to validated LinkML.

Schema Automator provides the baseline import. A narrow correction layer then
reconstructs the property-level ``anyOf`` and ``allOf`` structures used by the
ESS-DIVE Dataset model, using the unchanged OpenAPI fragment as the source of
truth.
"""

from copy import deepcopy
from pathlib import Path
from tempfile import NamedTemporaryFile

from linkml.linter.linter import Linter
from linkml_runtime.dumpers import yaml_dumper
from linkml_runtime.linkml_model import EnumDefinition, SchemaDefinition, SlotDefinition
from linkml_runtime.linkml_model.annotations import Annotation
from linkml_runtime.linkml_model.meta import AnonymousClassExpression, AnonymousSlotExpression
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
SUPPORTED_ALL_OF_KEYS = {"allOf", "description", "required", "title"}
SUPPORTED_ALL_OF_BRANCH_KEYS = {"$ref"}


def _constraint_annotations(*schemas: JsonObject) -> dict[str, Annotation]:
    """Encode otherwise-unrepresentable branch constraints as LinkML annotations.

    Anonymous LinkML slot expressions cannot directly express every JSON Schema
    keyword used by ESS-DIVE. Keeping those values under deterministic
    ``json_schema_*`` annotations prevents silent information loss while leaving
    the generated schema valid LinkML.
    """
    annotations: dict[str, Annotation] = {}
    for source in schemas:
        for keyword in ANNOTATED_CONSTRAINTS:
            if keyword in source:
                tag = f"json_schema_{keyword}"
                annotations[tag] = Annotation(tag=tag, value=deepcopy(source[keyword]))
    return annotations


def _range_for_schema(fragment: JsonObject, source: JsonObject) -> tuple[str, bool]:
    """Map a JSON Schema scalar or local reference to a LinkML range.

    The boolean result distinguishes class references from primitive ranges so
    callers can request inline object representation only where appropriate.
    """
    if "$ref" in source:
        name, _ = resolve_schema_ref(fragment, source["$ref"])
        return name, True
    source_type = source.get("type")
    if source_type not in SCALAR_RANGES:
        raise ValueError(f"Unsupported composition branch type: {source_type!r}")
    return SCALAR_RANGES[source_type], False


def _translate_any_of_branch(
    fragment: JsonObject, branch: JsonObject
) -> AnonymousSlotExpression:
    """Translate one ``anyOf`` alternative into an anonymous slot expression.

    A direct scalar or reference becomes a single-valued expression. An array
    becomes a multivalued expression whose range comes from ``items`` and whose
    collection cardinality remains local to that alternative.
    """
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


def _correct_any_of(schema: SchemaDefinition, fragment: JsonObject) -> None:
    """Restore property-level ``anyOf`` alternatives omitted by Schema Automator."""
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
                _translate_any_of_branch(fragment, branch) for branch in alternatives
            ]


def _correct_all_of(schema: SchemaDefinition, fragment: JsonObject) -> None:
    """Restore property-level ``allOf`` references and role-local requirements.

    A single unqualified reference becomes the slot range. When a property adds
    requirements—such as requiring ``email`` only for ``Dataset.editor``—a range
    expression carries those slot conditions without modifying the referenced
    class globally.
    """
    definitions = fragment["components"]["schemas"]
    for class_name, definition in definitions.items():
        if class_name not in schema.classes:
            continue
        for property_name, source_property in definition.get("properties", {}).items():
            alternatives = source_property.get("allOf")
            if alternatives is None:
                continue
            unsupported = set(source_property) - SUPPORTED_ALL_OF_KEYS
            if unsupported:
                raise ValueError(
                    f"Unsupported allOf property keywords on {class_name}.{property_name}: "
                    f"{sorted(unsupported)}"
                )
            if not isinstance(alternatives, list) or not alternatives:
                raise ValueError(f"{class_name}.{property_name} has an invalid allOf")

            ranges: list[str] = []
            for branch in alternatives:
                if not isinstance(branch, dict):
                    raise ValueError(f"{class_name}.{property_name} has a non-object allOf branch")
                unsupported_branch = set(branch) - SUPPORTED_ALL_OF_BRANCH_KEYS
                if unsupported_branch or "$ref" not in branch:
                    raise ValueError(
                        f"Unsupported allOf branch on {class_name}.{property_name}: {branch}"
                    )
                range_name, class_valued = _range_for_schema(fragment, branch)
                if not class_valued:
                    raise ValueError(
                        f"allOf branch on {class_name}.{property_name} must reference a class"
                    )
                ranges.append(range_name)

            required_names = source_property.get("required", [])
            if not isinstance(required_names, list) or not all(
                isinstance(name, str) for name in required_names
            ):
                raise ValueError(f"{class_name}.{property_name} has an invalid required list")
            slot_conditions = {
                name: SlotDefinition(name=name, required=True) for name in required_names
            }

            slot = schema.classes[class_name].attributes.get(property_name)
            if slot is None:
                raise ValueError(f"Importer omitted {class_name}.{property_name}")
            slot.range = None
            slot.range_expression = None
            slot.inlined = True
            if len(ranges) == 1 and not slot_conditions:
                slot.range = ranges[0]
            elif len(ranges) == 1:
                slot.range_expression = AnonymousClassExpression(
                    is_a=ranges[0], slot_conditions=slot_conditions
                )
            else:
                slot.range_expression = AnonymousClassExpression(
                    all_of=[AnonymousClassExpression(is_a=name) for name in ranges],
                    slot_conditions=slot_conditions,
                )


def _correct_named_enums(schema: SchemaDefinition, fragment: JsonObject) -> None:
    """Convert named JSON Schema string enums misclassified as empty classes.

    Schema Automator correctly imports inline enums, but currently represents a
    referenced definition such as ``GeoCoordinatesName`` as a class. That makes
    downstream JSON Schema generators expect an object where the canonical model
    expects one of a small set of strings.
    """
    for name, definition in fragment["components"]["schemas"].items():
        values = definition.get("enum")
        if definition.get("type") != "string" or values is None:
            continue
        if not isinstance(values, list) or not values or not all(
            isinstance(value, str) for value in values
        ):
            raise ValueError(f"{name} has an invalid string enum definition")
        schema.classes.pop(name, None)
        schema.enums[name] = EnumDefinition(
            name=name,
            title=definition.get("title"),
            description=definition.get("description"),
            permissible_values=values,
        )


def _correct_project_organization(schema: SchemaDefinition) -> None:
    """Model the organization fields accepted for a Dataset provider.

    The canonical Pydantic annotation names ``ProjectOrganizationIdentifier``
    but accepts the organization fields mixed into ``ProjectOrganization``.
    Pydantic's JSON Schema represents those fields as open-object extras, while
    LinkML validators close classes. Copying the known organization attributes
    preserves the accepted metadata shape without making every class open.
    """
    project = schema.classes.get("ProjectOrganizationIdentifier")
    organization = schema.classes.get("Organization")
    if project is None or organization is None:
        return
    for name, source_slot in organization.attributes.items():
        if name in project.attributes:
            continue
        slot = deepcopy(source_slot)
        slot.required = None
        project.attributes[name] = slot


def _prepare_schema_automator_input(fragment: JsonObject) -> JsonObject:
    """Replace handled composition properties with importer-safe placeholders.

    Schema Automator logs property-level ``anyOf`` and ``allOf`` as translation
    errors. The placeholders let it create the owning slots and preserve their
    descriptions and required status. The correction pass then rebuilds each
    slot from the original, unmodified fragment.
    """
    prepared = deepcopy(fragment)
    for definition in prepared["components"]["schemas"].values():
        for property_name, source_property in list(definition.get("properties", {}).items()):
            if "anyOf" not in source_property and "allOf" not in source_property:
                continue
            placeholder = {"type": "string"}
            for keyword in ("title", "description"):
                if keyword in source_property:
                    placeholder[keyword] = source_property[keyword]
            definition["properties"][property_name] = placeholder
    return prepared


def validate_linkml(path: Path) -> None:
    """Raise ``ValueError`` when a serialized schema violates the LinkML metamodel."""
    problems = list(Linter.validate_schema(str(path)))
    if problems:
        messages = "; ".join(problem.message for problem in problems)
        raise ValueError(f"Generated LinkML failed metamodel validation: {messages}")


def convert_to_linkml(fragment: JsonObject) -> SchemaDefinition:
    """Convert a selected ESS-DIVE OpenAPI fragment into a LinkML schema model.

    Schema Automator imports class-local attributes so identically named fields in
    different classes remain independent. The importer receives a deep copy, and
    correction passes read from the unchanged source fragment.

    Property-level ``anyOf`` and ``allOf`` are reconstructed after import. JSON
    Schema constraints without an anonymous-expression equivalent are retained as
    ``json_schema_*`` annotations instead of being silently discarded.

    The returned object conforms to the LinkML runtime model but is not serialized
    or metamodel-validated until :func:`write_linkml` is called.
    """
    if "Dataset" not in fragment.get("components", {}).get("schemas", {}):
        raise ValueError("Expected selected OpenAPI components containing Dataset")
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
    _correct_any_of(schema, fragment)
    _correct_all_of(schema, fragment)
    _correct_named_enums(schema, fragment)
    _correct_project_organization(schema)
    schema.description = (
        "DRAFT: generated from ESS-DIVE OpenAPI. Property-level anyOf and allOf "
        "expressions are source-corrected; other conversion gaps still require review."
    )
    return schema


def write_linkml(fragment: JsonObject, output: Path) -> SchemaDefinition:
    """Convert, validate, and atomically write a LinkML YAML schema.

    Validation happens on a temporary file in the destination directory. The
    requested output is replaced only after metamodel validation succeeds, so an
    invalid conversion cannot overwrite an earlier usable schema.
    """
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
