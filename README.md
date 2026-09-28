# essdive-metadata-schemas

Reviewed LinkML schema for ESS-DIVE Dataset metadata and its dependent classes.
The authoritative file in this repository is
[`src/essdive_metadata_schemas/schema/essdive_metadata_schemas.yaml`](src/essdive_metadata_schemas/schema/essdive_metadata_schemas.yaml).
It contains the latest reviewed converter output, including curated descriptions.
Alternative conversion drafts and the template's Person examples are not included.

## Development

```bash
uv sync --locked --group dev
just test
just lint
just site
```

`just site` generates JSON Schema, element documentation, and a local MkDocs site.
`just testdoc` serves the documentation locally. Lint currently reports the known
schema.org HTTP/HTTPS canonical-prefix warning. LinkML is pinned to 1.11.1.

## Repository structure

- `src/essdive_metadata_schemas/schema/`: the single reviewed source schema.
- `tests/data/`: valid and invalid Dataset metadata examples.
- `docs/`: documentation sources and generated element pages.
- `project/`: generated JSON Schema (not a second source schema).

## Updating the schema

The converter lives in the admin repository at
[`essdive_schema_converter/`](https://github.com/ess-dive/essdive-admin/tree/main/essdive_schema_converter).
From that directory, run `uv run --locked python -m essdive_metadata_schemas`, review
the output, and copy `dist/essdive_metadata_schema.yaml` over this repository's
source schema. Run the checks above before accepting the change. The admin branch
must be merged before the link to its main branch becomes available.

Project and package names are `essdive-metadata-schemas` and
`essdive_metadata_schemas`. The schema's existing internal name and URI are retained
so this move does not change its identity or validation rules.

## Validation scope

The schema preserves source JSON-LD keys, lengths, patterns, numeric bounds, and
role requirements. Where OpenAPI accepts either a string or list of strings, or an
object or list of objects, with identical item constraints, this schema accepts only
the list. Each affected field has an inline YAML comment describing that change; other
alternatives remain. It is a curated draft, not an exact replacement for the
ESS-DIVE API validator. With LinkML 1.11.1,
native `list_elements_unique` does not produce JSON Schema `uniqueItems`; some
format annotations are also unenforced, optional null values may be accepted, and
generated JSON Schema does not honor per-class `extra_slots`. See schema comments
for the provider interpretation and other modeling choices.

## Credits

Project scaffolding is adapted from
[linkml-project-copier](https://github.com/linkml/linkml-project-copier).

## Copyright
Environmental Systems Science Data Infrastructure for a Virtual Ecosystem (ESS-DIVE)
Copyright (c) 2026, The Regents of the University of California, through Lawrence Berkeley National Laboratory (subject to receipt of any required approvals from the U.S. Dept. of Energy). All rights reserved.

If you have questions about your rights to use or distribute this software, please contact Berkeley Lab's Intellectual Property Office at IPO@lbl.gov.

NOTICE. This Software was developed under funding from the U.S. Department of Energy and the U.S. Government consequently retains certain rights. As such, the U.S. Government has been granted for itself and others acting on its behalf a paid-up, nonexclusive, irrevocable, worldwide license in the Software to reproduce, distribute copies to the public, prepare derivative works, and perform publicly and display publicly, and to permit other to do so.
