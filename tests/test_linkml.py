"""Conversion contract: source preservation, failures, and safe output."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from linkml.linter.linter import Linter
from linkml_runtime.loaders import yaml_loader
from linkml_runtime.linkml_model import SchemaDefinition

from ess_dive_schemas.linkml import convert_to_linkml, write_linkml
from ess_dive_schemas.publish import select_dataset

ROOT = Path(__file__).parents[1]


def source():
    return select_dataset(json.loads((ROOT / 'openapi.json').read_text()))


class ConversionTests(unittest.TestCase):
    def test_source_unchanged_and_output_valid(self):
        document = source()
        before = deepcopy(document)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'schema.yaml'
            write_linkml(document, output)
            self.assertFalse(list(Linter.validate_schema(str(output))))
            schema = yaml_loader.load(str(output), target_class=SchemaDefinition)
            self.assertIn('ContactPerson', schema.classes)
            self.assertNotIn('providerName', schema.classes['Dataset'].attributes)
            self.assertEqual(document, before)
            self.assertNotIn('domain_of:', output.read_text())

    def test_saved_component_snapshot_still_converts(self):
        snapshot = json.loads((ROOT / 'tests/fixtures/ess_dive_dataset_full.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            write_linkml(snapshot, Path(directory) / 'schema.yaml')

    def test_unsupported_constructs_report_source_location(self):
        for bad in [{'type': 'string', 'minLenght': 1},
                    {'type': 'number', 'exclusiveMinimum': 0},
                    {'type': 'string', 'nullable': True},
                    {'type': 'array', 'items': {'type': 'array', 'items': {'type': 'string'}}},
                    {'anyOf': [{'type': 'string'}], 'pattern': 'x'},
                    {'allOf': [{'$ref': '#/components/schemas/Person'}, {'type': 'object'}]}]:
            with self.subTest(bad=bad):
                document = source()
                document['components']['schemas']['Dataset']['properties']['newField'] = bad
                with self.assertRaisesRegex(ValueError, r'Dataset/properties/newField'):
                    convert_to_linkml(document)

    def test_missing_required_property_is_not_silently_repaired(self):
        document = source()
        del document['components']['schemas']['Dataset']['properties']['description']
        with self.assertRaisesRegex(ValueError, 'undefined properties.*description'):
            convert_to_linkml(document)

    def test_role_drift_requires_review(self):
        document = source()
        document['components']['schemas']['Dataset']['properties']['provider']['required'] = ['name']
        with self.assertRaisesRegex(ValueError, 'role requirements changed'):
            convert_to_linkml(document)

    def test_bad_references_are_rejected(self):
        for ref in ['#/components/schemas/Missing', '#/components/schemas/Person/properties/email']:
            document = source()
            document['components']['schemas']['Dataset']['properties']['newField'] = {'$ref': ref}
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                convert_to_linkml(document)

    def test_failed_conversion_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'schema.yaml'
            output.write_text('previous version')
            document = source()
            document['components']['schemas']['Dataset']['properties']['bad'] = {'type': 'object'}
            with self.assertRaises(ValueError):
                write_linkml(document, output)
            self.assertEqual(output.read_text(), 'previous version')
            with patch('ess_dive_schemas.linkml.Linter.validate_schema', side_effect=ValueError('invalid')):
                with self.assertRaises(ValueError):
                    write_linkml(source(), output)
            self.assertEqual(output.read_text(), 'previous version')
            self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_cli_rejects_all_path_collisions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.json'
            path.write_text((ROOT / 'openapi.json').read_text())
            for args in [
                ['--input', str(path), '--output', str(path)],
                ['--output', str(path), '--linkml-output', str(path)],
                ['--output', str(path), '--raw-output', str(path)],
            ]:
                with self.subTest(args=args):
                    result = subprocess.run([sys.executable, '-m', 'ess_dive_schemas', *args], capture_output=True, text=True)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('paths must differ', result.stderr)

    def test_cli_rejects_unknown_dialect_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.json'
            path.write_text(json.dumps({'openapi': '3.1.0'}))
            output = Path(directory) / 'output.json'
            result = subprocess.run([sys.executable, '-m', 'ess_dive_schemas', '--input', str(path), '--output', str(output)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Only OpenAPI 3.0.x', result.stderr)
            self.assertFalse(output.exists())
