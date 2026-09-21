# ESS-DIVE Dataset metadata to LinkML

This repository contains a local command-line script for extracting the ESS-DIVE
Dataset metadata schema from the public OpenAPI document and converting it to
LinkML. It does not build or import package-service, publish a release, or deploy
the generated files.

## Set up

Install [uv](https://docs.astral.sh/uv/), then install the locked dependencies:

```bash
git submodule update --init --recursive
uv sync --locked
```

The project requires Python 3.12 or newer. uv uses the version selected in
`.python-version` and manages the local virtual environment. The
`vendor/essdive-toolset` submodule pins the canonical ESS-DIVE metadata models
used by the compatibility test.

## Run locally

From the repository root:

```bash
uv run --locked python -m ess_dive_schemas
```

By default, the script fetches the current public OpenAPI document from
`https://api.ess-dive.lbl.gov/openapi.json` and writes:

- `dist/essdive_metadata_schema.json`: Dataset and its recursively referenced OpenAPI
  schema definitions, copied without modification.
- `dist/essdive_metadata_schema.yaml`: the generated LinkML schema.

To keep the complete downloaded OpenAPI document as well:

```bash
uv run --locked python -m ess_dive_schemas \
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

`--input` and `--url` are mutually exclusive. Use `--url` to select an endpoint
other than the production default.

## What the script does

The local pipeline is:

```text
fetch or read OpenAPI
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
that is absent from the production-derived OpenAPI fixture. The compatibility
test exercises the canonical model directly, while the end-to-end production
fixture continues to preserve what the API actually published. This drift should
be resolved upstream or deliberately reconciled before claiming that the two
sources are identical.

The full downloaded OpenAPI document and selected JSON should be retained beside
the YAML when reviewing a generated result.

## Test locally

```bash
uv run --locked python -m unittest discover -s tests -v
```

The tests are offline. They cover recursive selection, source preservation,
reference failures, LinkML serialization and metamodel validation, focused
ESS-DIVE `anyOf` and `allOf` cases, and one end-to-end conversion of the complete
production-derived Dataset schema fixture. A separate integration test exports
the pinned toolset's Pydantic `Dataset` model, converts its complete dependency
closure, and checks the final LinkML classes, enums, properties, and required
fields against that canonical model.

## GitHub Actions

GitHub Actions only installs the locked environment and runs the offline test
suite for pull requests, pushes to `main`, and manual dispatches. It does not
fetch the production API, generate distributable artifacts, or publish schemas.
Run the script locally when generated files are needed.

Because `essdive-toolset` is a separate private repository, Actions must have a
repository secret named `ESSDIVE_TOOLSET_TOKEN` with read access to it. The
workflow falls back to the normal repository token when cross-repository access
is already available.
