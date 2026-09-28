"""Validate Dataset examples against the packaged, reviewed LinkML schema."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft201909Validator
from linkml.generators.jsonschemagen import JsonSchemaGenerator
from linkml.linter.linter import Linter

from essdive_metadata_schemas import MAIN_SCHEMA_PATH

DATA = Path(__file__).parent / "data"


def as_linkml_record(source):
    """Adapt source-valid scalar examples to this schema's list-only fields."""
    record = deepcopy(source)
    for field in ("description", "creator", "funder", "spatialCoverage"):
        if field in record and not isinstance(record[field], list):
            record[field] = [record[field]]

    provider = record.get("provider", {})
    if "member" in provider and not isinstance(provider["member"], list):
        provider["member"] = [provider["member"]]

    for place in record.get("spatialCoverage", []):
        for field in ("description", "geo"):
            if field in place and not isinstance(place[field], list):
                place[field] = [place[field]]
    return record


@pytest.fixture(scope="module")
def validator():
    schema = json.loads(JsonSchemaGenerator(str(MAIN_SCHEMA_PATH), not_closed=False).serialize())
    Draft201909Validator.check_schema(schema)
    return Draft201909Validator(schema)


def test_schema_metamodel():
    assert not list(Linter.validate_schema(str(MAIN_SCHEMA_PATH)))


@pytest.mark.parametrize("path", sorted((DATA / "valid").glob("*.yaml")))
def test_valid_data(path, validator):
    source = yaml.safe_load(path.read_text())
    # These original OpenAPI examples use scalar forms intentionally narrowed here.
    source_errors = list(validator.iter_errors(source))
    assert source_errors
    assert all(
        error.validator == "type"
        and (
            error.schema.get("type") == "array"
            or "array" in error.schema.get("type", [])
        )
        for error in source_errors
    )
    validator.validate(as_linkml_record(source))


@pytest.mark.parametrize(
    ("filename", "expected_path"),
    [
        ("Dataset-latitude-out-of-range.yaml", ("spatialCoverage", 0, "geo", 0, "latitude")),
        ("Dataset-missing-contact-email.yaml", ("editor",)),
    ],
)
def test_invalid_data(filename, expected_path, validator):
    source = yaml.safe_load((DATA / "invalid" / filename).read_text())
    errors = list(validator.iter_errors(as_linkml_record(source)))
    assert {tuple(error.path) for error in errors} == {expected_path}
