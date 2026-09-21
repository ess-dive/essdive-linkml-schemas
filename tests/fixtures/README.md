# Test fixtures

`ess_dive_dataset_anyof.json` is a small excerpt of the public ESS-DIVE OpenAPI
schema. It isolates the scalar-or-list, reference-or-list, cardinality, pattern,
and annotation cases exercised by the focused `anyOf` tests.

`ess_dive_dataset_full.json` is the complete `Dataset` dependency closure selected
from `https://api.ess-dive.lbl.gov/openapi.json` on 2026-09-21. The end-to-end test
uses this snapshot so conversion and LinkML metamodel validation remain offline and
repeatable. Refresh it deliberately when adopting upstream metadata schema changes.

Both fixtures preserve their source definitions. They should not be manually
normalized to make conversion easier; corrections belong in the conversion code.
