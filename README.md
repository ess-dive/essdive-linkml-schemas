# essdive-linkml-schemas

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

`just site` generates JSON Schema as an auxiliary documentation artifact, element
documentation, and a local MkDocs site. It is not a conversion target.
`just testdoc` serves the documentation locally. Lint currently reports the known
schema.org HTTP/HTTPS canonical-prefix warning. LinkML is pinned to 1.11.1.

## Repository structure

- `src/essdive_metadata_schemas/schema/`: the single reviewed source schema.
- `tests/data/`: valid and invalid Dataset metadata examples.
- `docs/`: documentation sources and generated element pages.
- `project/`: generated JSON Schema (not a second source schema).

## Updating the schema

Schema is built from our JSON-LD public schema. A converter tool lives in the 
private admin repository, which generates the the linkml yaml file.

## Validation scope

The schema preserves source JSON-LD keys, lengths, patterns, numeric bounds, and
role requirements. Where OpenAPI accepts either a string or list of strings, or an
object or list of objects, with identical item constraints, this schema accepts only
the list. Each affected field has an inline YAML comment describing that change; other
alternatives remain. This is a one-way, curated representation of the OpenAPI
metadata. Native `list_elements_unique` records source uniqueness on list-only
slots; source defaults and formats remain informational annotations. Consult the
OpenAPI source for exact API validation behavior. See schema comments for the
provider interpretation and other modeling choices.

## Credits

Project scaffolding is adapted from
[linkml-project-copier](https://github.com/linkml/linkml-project-copier).

## Copyright
Environmental Systems Science Data Infrastructure for a Virtual Ecosystem (ESS-DIVE)
Copyright (c) 2026, The Regents of the University of California, through Lawrence Berkeley National Laboratory (subject to receipt of any required approvals from the U.S. Dept. of Energy). All rights reserved.

If you have questions about your rights to use or distribute this software, please contact Berkeley Lab's Intellectual Property Office at IPO@lbl.gov.

NOTICE. This Software was developed under funding from the U.S. Department of Energy and the U.S. Government consequently retains certain rights. As such, the U.S. Government has been granted for itself and others acting on its behalf a paid-up, nonexclusive, irrevocable, worldwide license in the Software to reproduce, distribute copies to the public, prepare derivative works, and perform publicly and display publicly, and to permit other to do so.
