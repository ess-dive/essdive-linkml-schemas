"""Publish Dataset and its dependencies from the deployed OpenAPI document.

Definitions are copied whole: no properties, alternatives, defaults, or examples
are filtered out. Existing references retain their components.schemas paths.
"""

import argparse
from collections.abc import Iterator
from copy import deepcopy
import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote
from urllib.request import Request, urlopen

JsonObject = dict[str, Any]
DEFAULT_URL = "https://api.ess-dive.lbl.gov/openapi.json"


def fetch_openapi(url: str = DEFAULT_URL) -> JsonObject:
    """Read the public API specification; HTTP, timeout, and JSON errors propagate."""
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "ess-dive-schemas/0.1"})
    with urlopen(request, timeout=60) as response:
        document = json.load(response)
    if not isinstance(document, dict):
        raise ValueError("Expected an OpenAPI JSON object")
    return document


def schema_references(schema: JsonObject) -> Iterator[str]:
    """Visit schema-valued keywords, not example/default payloads.

    Enumerating schema positions avoids treating a literal '$ref' property name
    or a '$ref' inside example data as an actual schema reference.
    """
    reference = schema.get("$ref")
    if reference is not None:
        if not isinstance(reference, str):
            raise ValueError("Schema $ref must be a string")
        yield reference
    # OpenAPI 3.0 and 3.1 / JSON Schema object-valued schema containers.
    for keyword in ("properties", "patternProperties", "definitions", "$defs", "dependentSchemas"):
        for child in schema.get(keyword, {}).values():
            if isinstance(child, dict):
                yield from schema_references(child)
    for keyword in ("allOf", "anyOf", "oneOf", "prefixItems"):
        for child in schema.get(keyword, []):
            if isinstance(child, dict):
                yield from schema_references(child)
    for keyword in ("items", "additionalItems", "additionalProperties", "not", "contains",
                    "if", "then", "else", "propertyNames", "unevaluatedItems", "unevaluatedProperties"):
        child = schema.get(keyword)
        if isinstance(child, dict):
            yield from schema_references(child)
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, dict):
                    yield from schema_references(item)


def resolve_schema_ref(document: JsonObject, reference: str) -> tuple[str, Any]:
    """
    Resolve a local components.schemas JSON Pointer and return its model name.

    External references are deliberately unsupported: publishing unresolved
    dependencies would produce an incomplete artifact.
    """
    if not reference.startswith("#/"):
        raise ValueError(f"Only local schema references are supported: {reference}")
    parts = [part.replace("~1", "/").replace("~0", "~")
             for part in unquote(reference[2:]).split("/")]
    if len(parts) < 3 or parts[:2] != ["components", "schemas"]:
        raise ValueError(f"Reference is outside components.schemas: {reference}")
    value: Any = document
    try:
        for part in parts:
            value = value[int(part)] if isinstance(value, list) else value[part]
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ValueError(f"Unresolved schema reference: {reference}") from error
    return parts[2], value


def select_dataset(document: JsonObject) -> JsonObject:
    """
    Copy Dataset and its transitive dependency closure; safely handle cycles.

    Args:
        document (JsonObject): currently an openAPI 3 json representation

    Raises:
        ValueError: Dataset is not in your schema
        ValueError: malformed object definition

    Returns:
        JsonObject: Dataset and its transitive dependency closure
    """
    schemas = document.get("components", {}).get("schemas", {})
    if "Dataset" not in schemas:
        raise ValueError("OpenAPI document has no components.schemas.Dataset")
    selected: JsonObject = {}
    pending = ["Dataset"]
    while pending: #
        name = pending.pop()
        if name in selected:
            continue
        definition = schemas[name]
        if not isinstance(definition, dict):
            raise ValueError(f"Expected an object definition for {name}")
        selected[name] = deepcopy(definition)
        for reference in schema_references(definition):
            dependency, _ = resolve_schema_ref(document, reference)
            pending.append(dependency)
    return {"components": {"schemas": dict(sorted(selected.items()))}}


def postprocess(fragment: JsonObject) -> JsonObject:
    """JSON pass-through; LinkML refinement belongs in the draft conversion stage."""
    return fragment


def validate_output(fragment: JsonObject, source: JsonObject) -> None:
    """Check pass-through equality and reference completeness, not API semantics.

    TODO: replace source-equality checks with LinkML validation and compatibility
    tests when conversion is implemented. This is NOT LinkML validation today.
    """
    if fragment != select_dataset(source):
        raise ValueError("Output changed or omitted source schema definitions")
    for definition in fragment["components"]["schemas"].values():
        for reference in schema_references(definition):
            resolve_schema_ref(fragment, reference)


def publish(document: JsonObject, output: Path) -> JsonObject:
    """Run the pipeline and write only after all integrity checks succeed."""
    result = postprocess(select_dataset(document))
    validate_output(result, document)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--url", default=DEFAULT_URL, help="OpenAPI URL (default: production ESS-DIVE)")
    source.add_argument("--input", type=Path, help="Read a saved OpenAPI JSON file instead of fetching")
    parser.add_argument("--output", type=Path, default=Path("dist/essdive_metadata_schema.json"))
    parser.add_argument("--raw-output", type=Path, help="Write the unfiltered OpenAPI JSON to a file")
    parser.add_argument("--linkml-output", type=Path, default=Path("dist/essdive_metadata_schema.yaml"),
                        help="Also write draft LinkML YAML (requires review; conversion is lossy)")
    args = parser.parse_args()
    if args.linkml_output and args.linkml_output.resolve() == args.output.resolve():
        parser.error("JSON and LinkML output paths must differ")
    document = json.loads(args.input.read_text(encoding="utf-8")) if args.input else fetch_openapi(args.url)
    if  args.raw_output:
        raw_path = args.raw_output.resolve()
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if not isinstance(document, dict):
        raise ValueError("Expected an OpenAPI JSON object")
    result = publish(document, args.output)
    if args.linkml_output:
        from ess_dive_schemas.linkml import write_linkml
        write_linkml(result, args.linkml_output)
    print(f"Wrote {len(result['components']['schemas'])} schema definitions to {args.output}")
    if args.linkml_output:
        print(f"Wrote LinkML schema to {args.linkml_output}")


if __name__ == "__main__":
    main()
