"""Exercise the actual importer and serializer, not a mocked conversion."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from linkml_runtime.loaders import yaml_loader
from linkml_runtime.linkml_model import SchemaDefinition

from ess_dive_schemas.linkml import convert_to_linkml


def fragment() -> dict:
    return {"components": {"schemas": {
        "Dataset": {"type": "object", "required": ["name"], "properties": {
            "name": {"type": "string", "description": "Dataset name"},
            "creator": {"type": "array", "items": {"$ref": "#/components/schemas/Person"}},
            "status": {"type": "string", "enum": ["draft", "published"]},
            "count": {"type": "integer"},
        }},
        "Person": {"type": "object", "properties": {
            "name": {"type": "string", "description": "Person name"}}},
    }}}


class LinkMLTests(unittest.TestCase):
    def test_import_basics_and_source_preservation(self) -> None:
        source = fragment()
        before = deepcopy(source)
        with self.assertWarnsRegex(UserWarning, "lossy"):
            result = convert_to_linkml(source)
        self.assertEqual(source, before)
        self.assertEqual(set(result.classes), {"Dataset", "Person"})
        dataset = result.classes["Dataset"]
        self.assertTrue(dataset.tree_root)
        self.assertTrue(dataset.attributes["name"].required)
        self.assertEqual(dataset.attributes["name"].description, "Dataset name")
        self.assertEqual(result.classes["Person"].attributes["name"].description, "Person name")
        self.assertEqual(dataset.attributes["creator"].range, "Person")
        self.assertTrue(dataset.attributes["creator"].multivalued)
        self.assertEqual(dataset.attributes["count"].range, "integer")
        enum = result.enums[dataset.attributes["status"].range]
        self.assertEqual(set(enum.permissible_values), {"draft", "published"})

    def test_requires_dataset(self) -> None:
        with self.assertRaisesRegex(ValueError, "Dataset"):
            convert_to_linkml({})

    def test_cli_writes_json_and_loadable_linkml(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, linkml = root / "input.json", root / "schema.json", root / "schema.yaml"
            source.write_text(json.dumps(fragment()), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-m", "ess_dive_schemas", "--input", str(source),
                 "--output", str(output), "--linkml-output", str(linkml)],
                capture_output=True, text=True, check=True,
            )
            self.assertIn("lossy", result.stderr)
            self.assertEqual(json.loads(output.read_text()), fragment())
            schema = yaml_loader.load(str(linkml), target_class=SchemaDefinition)
            self.assertTrue(schema.classes["Dataset"].attributes["name"].required)

    def test_output_collision_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = str(Path(directory) / "same.json")
            result = subprocess.run(
                [sys.executable, "-m", "ess_dive_schemas", "--output", output,
                 "--linkml-output", output], capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must differ", result.stderr)
            self.assertFalse(Path(output).exists())
