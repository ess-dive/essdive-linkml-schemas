# About essdive-metadata-schemas

This project contains the reviewed ESS-DIVE Dataset metadata model. Its project
scaffolding was migrated from linkmltest; conversion tooling now lives separately
in essdive-admin/essdive_schema_converter.

The migration used the final `dist/essdive_metadata_schema.yaml` output from the
converter, including the approved Northwest and Southeast descriptions. The source
schema was copied without changes. Its SHA-256 at migration was
`fbd8ebbba190947f7aa559dcb0670e5c8e8816390247e141d6e3a64cd9dfbe69`.

The LinkML schema records source provenance and modeling decisions in a one-way
conversion from OpenAPI. It is a curated metadata model; consult the OpenAPI source
for exact API validation behavior.
