# Commands for the reviewed ESS-DIVE schema project.
schema := "src/essdive_metadata_schemas/schema/essdive_metadata_schemas.yaml"

_default:
    @just --list

install:
    uv sync --locked --group dev

test:
    uv run --locked python -m pytest

lint:
    uv run --locked linkml-lint --config .linkmllint.yaml --ignore-warnings {{schema}}

# Generate the validation target used by the tests.
gen-project:
    mkdir -p project/jsonschema
    uv run --locked gen-json-schema --closed {{schema}} > project/jsonschema/essdive_metadata_schemas.schema.json

# Keep the published YAML byte-identical to the reviewed source.
gen-doc:
    mkdir -p docs/elements docs/schema
    cp {{schema}} docs/schema/essdive_metadata_schemas.yaml
    uv run --locked gen-doc -d docs/elements {{schema}}

site: gen-project gen-doc
    uv run --locked mkdocs build

testdoc: gen-doc
    uv run --locked mkdocs serve

import "project.justfile"
