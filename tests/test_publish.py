"""Offline contract tests; fixtures are synthetic, not an ESS-DIVE schema copy."""

from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from ess_dive_schemas.publish import (
    convert_to_linkml, fetch_openapi, postprocess, publish, resolve_schema_ref,
    schema_references, select_dataset, validate_output,
)


def openapi_fixture() -> dict:
    """Exercise direct, nested, shared, and composition-based dependencies."""
    return {
        "openapi": "3.0.2",
        "components": {"schemas": {
            "Dataset": {
                "type": "object", "required": ["name", "creator"],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "maxLength": 512},
                    "creator": {"anyOf": [
                        {"$ref": "#/components/schemas/Person"},
                        {"type": "array", "minItems": 1, "items": {"$ref": "#/components/schemas/Person"}},
                    ]},
                    "editor": {"allOf": [{"$ref": "#/components/schemas/Person"}], "required": ["email"]},
                    "provider": {"oneOf": [{"$ref": "#/components/schemas/Organization"}]},
                    "@context": {"type": "string", "default": "http://schema.org/"},
                },
                "example": {"name": "Example dataset", "$ref": "literal example data"},
            },
            "Person": {"type": "object", "properties": {
                "affiliation": {"$ref": "#/components/schemas/Organization"}}},
            "Organization": {"type": "object", "properties": {"name": {"type": "string"}}},
            "DatasetDistribution": {"allOf": [{"$ref": "#/components/schemas/Dataset"}]},
            "UnrelatedError": {"type": "object"},
        }},
    }


class SelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = openapi_fixture()

    def test_selects_only_root_and_transitive_dependencies(self) -> None:
        result = select_dataset(self.source)["components"]["schemas"]
        self.assertEqual(set(result), {"Dataset", "Person", "Organization"})
        for name, definition in result.items():
            self.assertEqual(definition, self.source["components"]["schemas"][name])

    def test_preserves_all_properties_and_nine_alternatives(self) -> None:
        dataset = self.source["components"]["schemas"]["Dataset"]
        for index in range(9):
            dataset["properties"][f"option{index}"] = {"type": "string", "default": str(index)}
        dataset["properties"]["choice"] = {"anyOf": [
            {"type": "string", "enum": [str(index)]} for index in range(9)]}
        result = select_dataset(self.source)["components"]["schemas"]["Dataset"]
        self.assertEqual(result, dataset)
        self.assertEqual(len(result["properties"]["choice"]["anyOf"]), 9)

    def test_does_not_mutate_or_share_source_definitions(self) -> None:
        before = deepcopy(self.source)
        result = select_dataset(self.source)
        result["components"]["schemas"]["Dataset"]["required"].append("changed")
        self.assertEqual(self.source, before)

    def test_handles_cycles(self) -> None:
        self.source["components"]["schemas"]["Organization"]["properties"]["dataset"] = {
            "$ref": "#/components/schemas/Dataset"}
        result = select_dataset(self.source)
        self.assertEqual(len(result["components"]["schemas"]), 3)
        validate_output(result, self.source)

    def test_root_only(self) -> None:
        result = select_dataset({"components": {"schemas": {"Dataset": {"type": "object"}}}})
        self.assertEqual(set(result["components"]["schemas"]), {"Dataset"})

    def test_missing_dataset(self) -> None:
        with self.assertRaisesRegex(ValueError, "no components.schemas.Dataset"):
            select_dataset({})

    def test_missing_dependency(self) -> None:
        del self.source["components"]["schemas"]["Person"]
        with self.assertRaisesRegex(ValueError, "Unresolved"):
            select_dataset(self.source)

    def test_external_and_non_schema_refs_fail(self) -> None:
        for reference in ["https://example.org/schema.json", "#/components/responses/Result"]:
            with self.subTest(reference=reference), self.assertRaises(ValueError):
                resolve_schema_ref(self.source, reference)

    def test_nested_pointer_and_escaped_name(self) -> None:
        self.source["components"]["schemas"]["A/B~C"] = {
            "properties": {"name": {"type": "string"}}}
        reference = "#/components/schemas/A~1B~0C/properties/name"
        self.source["components"]["schemas"]["Dataset"]["properties"]["special"] = {"$ref": reference}
        result = select_dataset(self.source)
        self.assertIn("A/B~C", result["components"]["schemas"])
        validate_output(result, self.source)

    def test_examples_and_literal_ref_property_are_not_dependencies(self) -> None:
        schema = {"example": {"$ref": "not a reference"}, "default": {"$ref": "nor this"},
                  "properties": {"$ref": {"type": "string"}}}
        self.assertEqual(list(schema_references(schema)), [])

    def test_array_map_and_negation_dependencies(self) -> None:
        schema = {"items": {"$ref": "#/components/schemas/A"},
                  "additionalProperties": {"$ref": "#/components/schemas/B"},
                  "not": {"$ref": "#/components/schemas/C"}}
        self.assertEqual(set(schema_references(schema)), {
            "#/components/schemas/A", "#/components/schemas/B", "#/components/schemas/C"})

    def test_unimplemented_stages_and_validation(self) -> None:
        result = select_dataset(self.source)
        self.assertEqual(postprocess(convert_to_linkml(result)), select_dataset(self.source))
        validate_output(result, self.source)
        result["components"]["schemas"]["Dataset"]["required"] = []
        with self.assertRaisesRegex(ValueError, "changed or omitted"):
            validate_output(result, self.source)


class PipelineTests(unittest.TestCase):
    def test_fetch(self) -> None:
        source = openapi_fixture()
        with patch("ess_dive_schemas.publish.urlopen", return_value=BytesIO(json.dumps(source).encode())) as fetch:
            self.assertEqual(fetch_openapi(), source)
            self.assertEqual(fetch.call_args.kwargs["timeout"], 60)

    def test_fetch_failures_propagate(self) -> None:
        with patch("ess_dive_schemas.publish.urlopen", side_effect=HTTPError("url", 503, "Unavailable", {}, None)):
            with self.assertRaises(HTTPError):
                fetch_openapi()
        with patch("ess_dive_schemas.publish.urlopen", return_value=BytesIO(b"not JSON")):
            with self.assertRaises(json.JSONDecodeError):
                fetch_openapi()

    def test_publish_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "dist/dataset.schema.json"
            source = openapi_fixture()
            publish(source, output)
            self.assertEqual(json.loads(output.read_text()), select_dataset(source))

    def test_invalid_input_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.json"
            with self.assertRaises(ValueError):
                publish({}, output)
            self.assertFalse(output.exists())

    def test_offline_cli(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "openapi.json"
            output = Path(directory) / "schema.json"
            source.write_text(json.dumps(openapi_fixture()), encoding="utf-8")
            subprocess.run([sys.executable, "-m", "ess_dive_schemas", "--input", str(source),
                            "--output", str(output)], check=True, capture_output=True)
            self.assertEqual(json.loads(output.read_text()), select_dataset(openapi_fixture()))


if __name__ == "__main__":
    unittest.main()
