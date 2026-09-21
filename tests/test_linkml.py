"""Integration tests for Schema Automator import and LinkML correction passes."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from linkml_runtime.loaders import yaml_loader
from linkml_runtime.linkml_model import SchemaDefinition

from ess_dive_schemas.linkml import convert_to_linkml, write_linkml
from ess_dive_schemas.publish import select_dataset


FIXTURES = Path(__file__).parent / "fixtures"


def fragment() -> dict:
    """Return a compact fragment for baseline importer behavior."""
    return {
        "components": {
            "schemas": {
                "Dataset": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string", "description": "Dataset name"},
                        "creator": {
                            "type": "array",
                            "items": {"$ref": "#/components/schemas/Person"},
                        },
                        "status": {"type": "string", "enum": ["draft", "published"]},
                        "count": {"type": "integer"},
                    },
                },
                "Person": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Person name"}
                    },
                },
            }
        }
    }


def all_of_fragment() -> dict:
    """Return representative plain and role-constrained ``allOf`` properties."""
    return {
        "components": {
            "schemas": {
                "Dataset": {
                    "type": "object",
                    "required": ["editor"],
                    "properties": {
                        "editor": {
                            "allOf": [{"$ref": "#/components/schemas/Person"}],
                            "required": ["email"],
                            "description": "Dataset contact",
                        },
                        "temporalCoverage": {
                            "allOf": [
                                {"$ref": "#/components/schemas/TemporalCoverage"}
                            ],
                        },
                    },
                },
                "Person": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string"},
                        "familyName": {"type": "string"},
                    },
                },
                "TemporalCoverage": {
                    "type": "object",
                    "properties": {"startDate": {"type": "string"}},
                },
            }
        }
    }


class LinkMLTests(unittest.TestCase):
    def test_import_basics_and_source_preservation(self) -> None:
        source = fragment()
        before = deepcopy(source)
        result = convert_to_linkml(source)
        self.assertEqual(source, before)
        self.assertEqual(set(result.classes), {"Dataset", "Person"})
        dataset = result.classes["Dataset"]
        self.assertTrue(dataset.tree_root)
        self.assertTrue(dataset.attributes["name"].required)
        self.assertEqual(dataset.attributes["name"].description, "Dataset name")
        self.assertEqual(
            result.classes["Person"].attributes["name"].description,
            "Person name",
        )
        self.assertEqual(dataset.attributes["creator"].range, "Person")
        self.assertTrue(dataset.attributes["creator"].multivalued)
        self.assertEqual(dataset.attributes["count"].range, "integer")
        enum = result.enums[dataset.attributes["status"].range]
        self.assertEqual(set(enum.permissible_values), {"draft", "published"})

    def test_requires_dataset(self) -> None:
        with self.assertRaisesRegex(ValueError, "Dataset"):
            convert_to_linkml({})

    def test_ess_dive_single_or_list_any_of_is_preserved(self) -> None:
        source = json.loads((FIXTURES / "ess_dive_dataset_anyof.json").read_text())
        fragment = select_dataset(source)
        before = deepcopy(fragment)

        schema = convert_to_linkml(fragment)

        self.assertEqual(fragment, before)
        creator = schema.classes["Dataset"].attributes["creator"]
        self.assertTrue(creator.required)
        self.assertEqual(
            creator.description,
            source["components"]["schemas"]["Dataset"]["properties"]["creator"][
                "description"
            ],
        )
        self.assertEqual(len(creator.any_of), 2)
        scalar, collection = creator.any_of
        self.assertEqual(scalar.range, "Person")
        self.assertFalse(scalar.multivalued)
        self.assertTrue(scalar.inlined)
        self.assertEqual(collection.range, "Person")
        self.assertTrue(collection.multivalued)
        self.assertTrue(collection.inlined)
        self.assertEqual(collection.minimum_cardinality, 1)

        description = schema.classes["Dataset"].attributes["description"]
        scalar, collection = description.any_of
        self.assertEqual(scalar.range, "string")
        self.assertFalse(scalar.multivalued)
        self.assertEqual(scalar.annotations["json_schema_minLength"].value, 1)
        self.assertEqual(scalar.annotations["json_schema_maxLength"].value, 5000)
        self.assertEqual(collection.range, "string")
        self.assertTrue(collection.multivalued)
        self.assertEqual(collection.minimum_cardinality, 1)

        keywords_collection = schema.classes["Dataset"].attributes["keywords"].any_of[1]
        self.assertTrue(keywords_collection.annotations["json_schema_uniqueItems"].value)
        same_as = schema.classes["Dataset"].attributes["sameAs"].any_of
        self.assertEqual(same_as[0].pattern, "^http[s]?://(dx.|)doi.org/")
        self.assertEqual(same_as[0].annotations["json_schema_format"].value, "uri")
        geo_collection = schema.classes["Place"].attributes["geo"].any_of[1]
        self.assertEqual(geo_collection.range, "GeoCoordinates")
        self.assertEqual(geo_collection.minimum_cardinality, 1)
        self.assertEqual(geo_collection.maximum_cardinality, 2)

    def test_ess_dive_any_of_serialization_passes_metamodel_validation(self) -> None:
        source = json.loads((FIXTURES / "ess_dive_dataset_anyof.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "schema.yaml"
            write_linkml(select_dataset(source), output)
            schema = yaml_loader.load(str(output), target_class=SchemaDefinition)
        self.assertEqual(len(schema.classes["Dataset"].attributes["creator"].any_of), 2)

    def test_all_of_preserves_reference_and_role_local_requirements(self) -> None:
        source = all_of_fragment()
        before = deepcopy(source)
        with self.assertNoLogs(level="ERROR"):
            schema = convert_to_linkml(source)

        self.assertEqual(source, before)
        editor = schema.classes["Dataset"].attributes["editor"]
        self.assertTrue(editor.required)
        self.assertTrue(editor.inlined)
        self.assertEqual(editor.range_expression.is_a, "Person")
        self.assertTrue(editor.range_expression.slot_conditions["email"].required)
        self.assertIsNone(schema.classes["Person"].attributes["email"].required)

        temporal = schema.classes["Dataset"].attributes["temporalCoverage"]
        self.assertEqual(temporal.range, "TemporalCoverage")
        self.assertTrue(temporal.inlined)

    def test_full_production_metadata_converts_without_errors(self) -> None:
        source = FIXTURES / "ess_dive_dataset_full.json"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected, linkml = root / "dataset.json", root / "dataset.yaml"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ess_dive_schemas",
                    "--input",
                    str(source),
                    "--output",
                    str(selected),
                    "--linkml-output",
                    str(linkml),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            schema = yaml_loader.load(str(linkml), target_class=SchemaDefinition)

        self.assertEqual(len(schema.classes), 12)
        any_of_slots = [
            attribute
            for class_definition in schema.classes.values()
            for attribute in class_definition.attributes.values()
            if attribute.any_of
        ]
        self.assertEqual(len(any_of_slots), 18)
        dataset = schema.classes["Dataset"]
        self.assertEqual(dataset.attributes["editor"].range_expression.is_a, "Person")
        self.assertTrue(
            dataset.attributes["editor"].range_expression.slot_conditions["email"].required
        )
        self.assertEqual(
            dataset.attributes["provider"].range_expression.is_a,
            "ProjectOrganizationIdentifier",
        )
        self.assertTrue(
            dataset.attributes["provider"].range_expression.slot_conditions["member"].required
        )
        self.assertEqual(dataset.attributes["temporalCoverage"].range, "TemporalCoverage")
        self.assertEqual(
            schema.classes["ProjectOrganizationIdentifier"].attributes["identifier"].range,
            "PropertyValueEssDive",
        )

    def test_unknown_any_of_shape_fails_instead_of_weakening_schema(self) -> None:
        source = fragment()
        source["components"]["schemas"]["Dataset"]["properties"]["choice"] = {
            "anyOf": [{"type": "string", "const": "only"}, {"type": "integer"}]
        }
        with self.assertRaisesRegex(ValueError, "Unsupported anyOf branch keywords.*const"):
            convert_to_linkml(source)

    def test_invalid_linkml_is_not_published(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "schema.yaml"
            with patch(
                "ess_dive_schemas.linkml.validate_linkml",
                side_effect=ValueError("invalid"),
            ):
                with self.assertRaisesRegex(ValueError, "invalid"):
                    write_linkml(fragment(), output)
            self.assertFalse(output.exists())

    def test_cli_writes_json_and_loadable_linkml(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.json"
            output = root / "schema.json"
            linkml = root / "schema.yaml"
            source.write_text(json.dumps(fragment()), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ess_dive_schemas",
                    "--input",
                    str(source),
                    "--output",
                    str(output),
                    "--linkml-output",
                    str(linkml),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(result.stderr, "")
            self.assertIn(f"Wrote LinkML schema to {linkml}", result.stdout)
            self.assertEqual(json.loads(output.read_text()), fragment())
            schema = yaml_loader.load(str(linkml), target_class=SchemaDefinition)
            self.assertTrue(schema.classes["Dataset"].attributes["name"].required)

    def test_output_collision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = str(Path(directory) / "same.json")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ess_dive_schemas",
                    "--output",
                    output,
                    "--linkml-output",
                    output,
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must differ", result.stderr)
            self.assertFalse(Path(output).exists())
