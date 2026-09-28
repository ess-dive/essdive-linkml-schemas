# Dataset examples

These are unchanged examples from the source format. Valid examples exercise both
single objects and arrays. The LinkML model deliberately requires lists for fields
whose source allows either form, so the tests wrap those scalar values in lists in
memory before validating. They also verify that the original source-valid records
fail only because of those list-only fields. Invalid examples omit the required
contact email or exceed the latitude bound; the tests verify those specific errors
after wrapping scalar values.

Tests use generated JSON Schema as an auxiliary check of the LinkML model, not as
an output of the OpenAPI-to-LinkML conversion.
