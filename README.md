# ESS-DIVE Dataset metadata to LinkML

A small, direct converter for the OpenAPI 3.0 constructs used by ESS-DIVE Dataset
metadata. It preserves JSON property names and scalar-or-array alternatives,
adds explicit role profiles, and writes readable LinkML. It is not a universal
OpenAPI importer or an exact replacement for the API's validator.

## Run

```bash
uv sync --locked
uv run --locked python -m ess_dive_schemas
```

The default input is the saved `openapi.json` in the current directory. Keep this
snapshot under version control with the converter. Conversion is offline and does
not need Schema Automator, a toolset checkout, a second Python environment, or
access to a private repository.

Outputs:

- `dist/essdive_metadata_schema.json`: unchanged Dataset component definitions and
  their transitive dependencies (an OpenAPI fragment, not standalone JSON Schema).
- `dist/essdive_metadata_schema.yaml`: the curated LinkML schema.

To use another snapshot:

```bash
uv run --locked python -m ess_dive_schemas --input path/to/openapi.json
```

Network access is explicit. To review upstream changes without replacing the
saved source or normal outputs:

```bash
uv run --locked python -m ess_dive_schemas \
  --url https://api.ess-dive.lbl.gov/openapi.json \
  --raw-output dist/candidate-openapi.json \
  --output dist/candidate-components.json \
  --linkml-output dist/candidate.yaml
```

Review the source and generated differences before adopting a new snapshot.
Input/output paths must be distinct. Unsupported schema constructs fail with a
source path; conversion and LinkML validation finish before JSON outputs are
written. The YAML file is replaced atomically after validation.

## Implementation

```text
saved OpenAPI -> select Dataset dependencies -> translate -> apply policy -> validate/write
```

- `publish.py`: loading, reference selection, and CLI.
- `linkml.py`: one recursive translator shared by ordinary properties and
  composition branches, plus metamodel validation and YAML output.
- `policy.py`: explicit semantic mappings, contact/provider roles, and factoring
  of shared slot definitions. Change modeling choices here, not in generated YAML.

Supported input includes objects, named string enums, primitive properties,
string enums on properties, local references to named schemas, arrays,
property-level `anyOf`/`oneOf`, and a single-reference `allOf` with local required
fields. String lengths become reusable patterned string types. Regexes, numeric
bounds, and array cardinality are represented directly. Constraints that require
both a length and a source regex retain both. Unknown keywords and unsupported
shapes are rejected rather than silently weakened.

This deliberately bounded converter rejects OpenAPI 3.1, nested arrays, composed
array items, and general `allOf` intersections. Expand the supported subset only
when a reviewed ESS-DIVE source change needs it. Descriptive title/example data is
not part of the validation contract; source descriptions are retained, while the
original JSON fragment retains all source metadata.

## Descriptions

The converter preserves source descriptions on classes, enums, properties, and
composition branches. Generated string types describe their length bounds, and
generated role classes describe their purpose. General shared-slot descriptions
are curated in `policy.py`; source descriptions remain in class-local `slot_usage`
and are never promoted into unrelated classes.

Source wording is retained, including typos. Enum values without individual
source descriptions remain undescribed unless explicitly documented in
`policy.py`. Northwest and Southeast have curated bounding-box corner descriptions
approved for this schema. The converter does not infer domain
explanations or add filler to eliminate every documentation warning.

## Modeling choices and limits

- Original JSON keys, including `@id`, are retained. Identifiers stay optional;
  source defaults are recorded as annotations without inserting values.
- `ContactPerson` requires email specifically for Dataset.editor.
- `DatasetProvider` requires identifier and member. The source leaves member's
  value unconstrained; the curated profile uses Organization.member and declares
  optional organization fields used in existing records. The underlying
  ProjectOrganizationIdentifier stays unchanged.
- Schema.org mappings are an explicit allowlist. Shared slots retain local
  constraints through `slot_usage`; redundant serializer bookkeeping is omitted.
- Array uniqueness and format checks are retained as `json_schema_*` annotations,
  **not enforced validation rules**. Open-object behavior is represented through
  `extra_slots`, but LinkML 1.11.1's JSON Schema generator does not honor it.
  Generated schemas also admit some optional null values. These are documented
  gaps, not equivalence claims.

LinkML and its runtime are pinned to the tested 1.11.1 versions. For a generated
JSON Schema with a closed Dataset root, use:

```bash
uv run --locked gen-json-schema --closed dist/essdive_metadata_schema.yaml
```

If exact API acceptance/rejection becomes a requirement, retain source-schema
validation alongside this model rather than growing an unbounded repair layer.

## Checks

```bash
uv run --locked python -m unittest discover -s tests -v
uv run --locked linkml-lint --config .linkmllint.yaml --ignore-warnings \
  dist/essdive_metadata_schema.yaml
```

Tests cover source/reference integrity, unsupported constructs, output safety,
metamodel validity, and generated-schema behavior (scalar/list alternatives,
required fields, lengths, patterns, enum and coordinate bounds). Known generator
gaps are tested explicitly. Routine tests use saved inputs and synthetic records;
they do not execute the toolset validator or claim parity with all its custom
checks. The legacy vendor checkout is not needed by conversion or CI and is left
in place for separate manual investigations.

GitHub Actions installs the locked dependencies and runs these offline tests. It
requires neither submodule checkout nor a private toolset token, and does not
publish or deploy anything.
