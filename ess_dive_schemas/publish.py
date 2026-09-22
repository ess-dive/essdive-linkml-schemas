"""Extract Dataset and its dependencies from a saved OpenAPI 3.0 document."""

import argparse
from collections.abc import Iterator
from copy import deepcopy
import json
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import unquote
from urllib.request import Request, urlopen

type JsonObject = dict[str, Any]
DEFAULT_URL = "https://api.ess-dive.lbl.gov/openapi.json"
DEFAULT_INPUT = Path("openapi.json")


def fetch_openapi(url: str = DEFAULT_URL) -> JsonObject:
    """Fetch an OpenAPI JSON object.

    Network, HTTP, timeout, and JSON decoding errors intentionally propagate so a
    failed fetch cannot produce a stale or partial schema.
    """
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "ess-dive-schemas/0.1"},
    )
    with urlopen(request, timeout=60) as response:
        document = json.load(response)
    if not isinstance(document, dict):
        raise ValueError("Expected an OpenAPI JSON object")
    return document


def schema_references(schema: JsonObject) -> Iterator[str]:
    """Yield references found in JSON Schema-valued positions.

    Schema keywords are enumerated deliberately. This avoids interpreting a
    literal ``$ref`` property name or a ``$ref`` inside example/default data as a
    dependency.
    """
    reference = schema.get("$ref")
    if reference is not None:
        if not isinstance(reference, str):
            raise ValueError("Schema $ref must be a string")
        yield reference
    # OpenAPI 3.0 and 3.1 / JSON Schema object-valued schema containers.
    for keyword in (
        "properties",
        "patternProperties",
        "definitions",
        "$defs",
        "dependentSchemas",
    ):
        for child in schema.get(keyword, {}).values():
            if isinstance(child, dict):
                yield from schema_references(child)
    for keyword in ("allOf", "anyOf", "oneOf", "prefixItems"):
        for child in schema.get(keyword, []):
            if isinstance(child, dict):
                yield from schema_references(child)
    for keyword in (
        "items",
        "additionalItems",
        "additionalProperties",
        "not",
        "contains",
        "if",
        "then",
        "else",
        "propertyNames",
        "unevaluatedItems",
        "unevaluatedProperties",
    ):
        child = schema.get(keyword)
        if isinstance(child, dict):
            yield from schema_references(child)
        elif isinstance(child, list):
            for item in child:
                if isinstance(item, dict):
                    yield from schema_references(item)


def resolve_schema_ref(document: JsonObject, reference: str) -> tuple[str, Any]:
    """Resolve a local ``components.schemas`` JSON Pointer.

    Returns the top-level schema name and the pointed-to value. External and
    non-schema references are rejected because they would make the extracted
    fragment incomplete.
    """
    if not reference.startswith("#/"):
        raise ValueError(f"Only local schema references are supported: {reference}")
    parts = [
        part.replace("~1", "/").replace("~0", "~")
        for part in unquote(reference[2:]).split("/")
    ]
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
    """Copy ``Dataset`` and every recursively referenced schema definition.

    The traversal is cycle-safe, preserves each definition exactly, excludes
    unrelated API schemas, and returns definitions in stable name order.
    """
    schemas = document.get("components", {}).get("schemas", {})
    if "Dataset" not in schemas:
        raise ValueError("OpenAPI document has no components.schemas.Dataset")
    selected: JsonObject = {}
    pending = ["Dataset"]
    while pending:
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


def validate_output(fragment: JsonObject, source: JsonObject) -> None:
    """Verify that an extracted fragment is unchanged and self-contained.

    This validates the selected OpenAPI JSON, not the generated LinkML. LinkML is
    validated independently before writing.
    """
    if fragment != select_dataset(source):
        raise ValueError("Output changed or omitted source schema definitions")
    for definition in fragment["components"]["schemas"].values():
        for reference in schema_references(definition):
            resolve_schema_ref(fragment, reference)


def publish(document: JsonObject, output: Path) -> JsonObject:
    """Select, validate, and write the Dataset schema fragment as formatted JSON."""
    result = select_dataset(document)
    validate_output(result, document)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result


def main() -> None:
    """Run the offline-by-default OpenAPI-to-LinkML conversion."""
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--url",
        help=f"Fetch an OpenAPI document (production: {DEFAULT_URL})",
    )
    source.add_argument(
        "--input",
        type=Path,
        help="Read a saved OpenAPI JSON file (default: openapi.json)",
    )
    parser.add_argument("--output", type=Path, default=Path("dist/essdive_metadata_schema.json"))
    parser.add_argument(
        "--raw-output",
        type=Path,
        help="Write the source schema JSON before Dataset dependency selection",
    )
    parser.add_argument(
        "--linkml-output",
        type=Path,
        default=Path("dist/essdive_metadata_schema.yaml"),
        help="Write the generated LinkML YAML",
    )
    args = parser.parse_args()
    input_path = None if args.url else (args.input or DEFAULT_INPUT)
    outputs = [args.output, args.linkml_output] + ([args.raw_output] if args.raw_output else [])
    resolved = [p.resolve() for p in outputs]
    if len(set(resolved)) != len(resolved) or (input_path and input_path.resolve() in resolved):
        parser.error("Input and output paths must differ")
    try:
        document = fetch_openapi(args.url) if args.url else json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("Expected an OpenAPI JSON object")
        if not str(document.get('openapi', '')).startswith('3.0.'):
            raise ValueError("Only OpenAPI 3.0.x is supported; select a reviewed snapshot")
        result = select_dataset(document)
        from ess_dive_schemas.linkml import write_linkml

        # Conversion must succeed before writing any JSON artifacts.
        write_linkml(result, args.linkml_output)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if args.raw_output:
            args.raw_output.parent.mkdir(parents=True, exist_ok=True)
            args.raw_output.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except URLError as error:
        parser.error(f"Unable to fetch {args.url}: {error.reason}. Use --input for an offline run.")
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"Wrote {len(result['components']['schemas'])} schema definitions to {args.output}")
    if args.linkml_output:
        print(f"Wrote LinkML schema to {args.linkml_output}")


if __name__ == "__main__":
    main()
