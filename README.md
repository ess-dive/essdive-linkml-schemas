# ESS-DIVE Dataset metadata to LinkML

This repository contains a local command-line script for extracting the ESS-DIVE
Dataset metadata schema from the canonical toolset models and converting it to
LinkML. It can also process the public OpenAPI document explicitly. It does not
build or import package-service, publish a release, or deploy generated files.

## Set up

Install [uv](https://docs.astral.sh/uv/), then install the locked dependencies:

```bash
git submodule update --init --recursive
uv sync --locked
uv venv .toolset-venv
uv pip install --python .toolset-venv/bin/python ./vendor/essdive-toolset
```

The project requires Python 3.12 or newer. uv uses the version selected in
`.python-version` and manages the local virtual environment. The
`vendor/essdive-toolset` submodule pins the canonical ESS-DIVE metadata models
used by the compatibility test. Its separate environment is required because
the toolset uses Pydantic v1 while LinkML uses Pydantic v2.

## Run locally

From the repository root:

```bash
uv run --locked python -m ess_dive_schemas
```

By default, the script reads the canonical model from the pinned
`vendor/essdive-toolset` submodule through its isolated environment. It does not
access the network. It writes:

- `dist/essdive_metadata_schema.json`: Dataset and its recursively referenced
  canonical schema definitions.
- `dist/essdive_metadata_schema.yaml`: the generated LinkML schema.

To compare against the current production OpenAPI document explicitly:

```bash
uv run --locked python -m ess_dive_schemas \
  --url https://api.ess-dive.lbl.gov/openapi.json \
  --raw-output dist/openapi.json
```

For a repeatable offline run, provide a previously downloaded OpenAPI document:

```bash
uv run --locked python -m ess_dive_schemas \
  --input openapi.json \
  --raw-output dist/openapi.json \
  --output dist/essdive_metadata_schema.json \
  --linkml-output dist/essdive_metadata_schema.yaml
```

`--input` and `--url` are mutually exclusive. With neither option, the pinned
canonical toolset model is used. `ESSDIVE_TOOLSET_PYTHON` or
`--toolset-python` can select a different toolset environment.

## What the script does

The local pipeline is:

```text
load canonical toolset model, or explicitly fetch/read OpenAPI
  -> select Dataset and its transitive schema dependencies
  -> import with Schema Automator
  -> apply source-aware LinkML corrections
  -> validate against the LinkML metamodel
  -> write local files
```

The selected JSON preserves the source definitions and their existing
`#/components/schemas/...` references. It is an OpenAPI components fragment, not
a standalone JSON Schema document.

The LinkML correction layer restores property-level `anyOf` alternatives,
including ESS-DIVE's single-value-or-list fields, and property-level `allOf`
references. Role-local requirements such as `editor.email` remain local to that
use of `Person`. The conversion preserves branch cardinality and patterns
directly where LinkML supports them. Source constraints without an equivalent
anonymous LinkML expression are retained as `json_schema_*` annotations rather
than silently discarded.

## Current limitations

The LinkML output is still a draft. Schema Automator does not preserve every
constraint on ordinary, non-composed properties. Remaining known gaps include
string length and format constraints, defaults, numeric bounds, and some
patterns. Valid LinkML output does not yet imply semantic equivalence with every
accepted or rejected ESS-DIVE metadata instance. These limitations are recorded
here and in the generated schema description rather than emitted as a runtime
warning.

The pinned toolset model currently has an optional `Dataset.providerName` field
that is absent from the production-derived OpenAPI fixture. A dedicated drift
test asserts that this is the only difference between the two sources, keeping
source drift separate from LinkML conversion behavior.

The full downloaded OpenAPI document and selected JSON should be retained beside
the YAML when reviewing a generated result.

## Test locally

```bash
uv run --locked python -m unittest discover -s tests -v
```

The tests are offline. They cover recursive selection, source preservation,
reference failures, LinkML serialization and metamodel validation, focused
ESS-DIVE `anyOf` and `allOf` cases, and one end-to-end conversion of the complete
production-derived Dataset schema fixture. The conformance tests run the
toolset's own validator in its isolated environment and LinkML's official JSON
Schema validation plugin against the same canonical metadata records. All
toolset-valid records must pass LinkML validation; selected invalid records cover
the constraints the current LinkML conversion claims to represent.

## GitHub Actions

GitHub Actions only installs the locked environment and runs the offline test
suite for pull requests, pushes to `main`, and manual dispatches. It does not
fetch the production API, generate distributable artifacts, or publish schemas.
Run the script locally when generated files are needed.

Because `essdive-toolset` is a separate private repository, Actions must have a
repository secret named `ESSDIVE_TOOLSET_TOKEN` with read access to it. The
workflow falls back to the normal repository token when cross-repository access
is already available.
