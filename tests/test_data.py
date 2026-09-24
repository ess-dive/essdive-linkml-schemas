"""Validate Dataset examples against the packaged, reviewed LinkML schema."""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft201909Validator
from linkml.generators.jsonschemagen import JsonSchemaGenerator
from linkml.linter.linter import Linter

from essdive_metadata_schemas import MAIN_SCHEMA_PATH

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="module")
def validator():
    schema = json.loads(JsonSchemaGenerator(str(MAIN_SCHEMA_PATH), not_closed=False).serialize())
    Draft201909Validator.check_schema(schema)
    return Draft201909Validator(schema)


def test_schema_metamodel():
    assert not list(Linter.validate_schema(str(MAIN_SCHEMA_PATH)))


def test_jsonld_aliases(validator):
    data = yaml.safe_load((DATA / "valid" / "Dataset-001.yaml").read_text())
    data.update({"@type": "Dataset", "@id": "doi:10.1234/example", "@context": "http://schema.org/"})
    validator.validate(data)
    data["type"] = data.pop("@type")
    assert list(validator.iter_errors(data))


@pytest.mark.parametrize("path", sorted((DATA / "valid").glob("*.yaml")))
def test_valid_data(path, validator):
    validator.validate(yaml.safe_load(path.read_text()))


@pytest.mark.parametrize("path", sorted((DATA / "invalid").glob("*.yaml")))
def test_invalid_data(path, validator):
    assert list(validator.iter_errors(yaml.safe_load(path.read_text())))
