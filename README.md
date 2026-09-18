# ESS-DIVE schemas

Tools for publishing ESS-DIVE metadata schemas  in alternate formates, starting 
with Dataset metadata in LinkML.

Currently this project fetches the public API's `openapi.json`, selects **Dataset
and every schema it references**, and writes them to `dist/dataset.schema.json`.
It does not require package-service, toolset, API credentials, or a local server.
This approach may need to evolve.

**LinkML conversion and post-processing are not implemented.** Both stages are
explicit TODOs and currently return their input unchanged.

## Run

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then from
the repository root:

```bash
uv sync --locked
uv run --locked python -m ess_dive_schemas
```

Python 3.12 is selected by `.python-version`; uv manages the local `.venv`.
There are no third-party runtime or test dependencies. `uv.lock` is committed.
The same commands work in the existing ESS-DIVE development container if uv
is available. No special container or network service is required.

Use a local snapshot or choose a different output file:

```bash
uv run python -m ess_dive_schemas --input openapi.json --output dist/dataset.schema.json
```

Use `--url` to explicitly select another OpenAPI endpoint. The default is
https://api.ess-dive.lbl.gov/openapi.json.

## Test locally

```bash
uv run --locked python -m unittest discover -s tests -v
```

Tests use synthetic metadata and mocked HTTP responses; no network is needed.
They verify complete Dataset selection, nested dependencies, cycles, unchanged
fields/options, reference errors, and writing the output file.

## Output and pipeline

```text
Fetch OpenAPI -> select Dataset + dependencies -> convert (TODO)
             -> post-process (TODO) -> validate -> write JSON
```

The file is an **OpenAPI components fragment**, preserving existing reference paths:

```json
{"components": {"schemas": {"Dataset": {}, "Person": {}}}}
```

The empty definitions above are placeholders for illustration. Actual schemas
are copied whole, including properties, anyOf/oneOf/allOf alternatives, defaults,
examples, required fields, and constraints. JSON formatting may change, but
definition content does not. Unrelated schemas and API endpoints are excluded.

This is not a standalone JSON Schema, a complete OpenAPI document, or LinkML yet.
Validation currently checks source equality and resolution of all selected local
schema references. It does not correct upstream inconsistencies or reproduce
Python-only validators. External references fail rather than being silently lost.

## GitHub Actions

- Pull requests: offline tests only.
- Pushes to `main` and manual runs: tests, then fetch/extract and upload the JSON.
- Download `dataset-schema` from the workflow run's **Artifacts** section.

No secrets are needed. Artifacts expire after 30 days. No website or GitHub release
is deployed. A failed fetch or validation prevents a new artifact from being
uploaded. Changes to the upstream API do not automatically trigger a workflow;
run it manually when a new snapshot is needed.

## Contributing

Open an issue to discuss schema requirements or submit a pull request with tests.
Keep the current pass-through contract until LinkML conversion is explicitly
implemented. To change dependencies, use `uv add` (or `uv add --dev`) and commit
both `pyproject.toml` and `uv.lock`.

Before Bridge consumes versioned LinkML output, implement conversion,
post-processing, compatibility tests, and durable versioned publication. For now,
the purpose is a small, inspectable extraction pipeline.
