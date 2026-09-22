# Test fixtures

`ess_dive_dataset_full.json` is the Dataset dependency closure selected from the
public ESS-DIVE OpenAPI document on 2026-09-21. A regression test keeps this older
snapshot convertible. The normal CLI and behavioral tests use root `openapi.json`.

`ess_dive_dataset_anyof.json` is a retained historical excerpt for manual review;
it is not needed by the direct translator tests. Neither fixture is normalized
by the converter.
