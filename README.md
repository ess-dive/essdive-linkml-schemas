# ESS-DIVE schema publication framework

When complete, this project will pull a specified version of the ess-dive api from essdive-package-service, convert that schema to LinkML, using their conversion code, perform any needed corrections, and publish a versioned LinkML metadata schema to be used in formatting ess-dive metadata fror BRIDGE. Package-service is a build dependency; Bridge only needs the published schema artifact.

Steps to complete:
1) ingest openapi/json metadata schemas (partially cimplete/needs validation)
2) LinkML conversion
3) validation/revision
4) dist publication (partially complete, pipeline draft written)

## Pipeline

1. Read repository, release ref, and optional commit lock from `source.json`.
2. Check out that release and its recorded toolset submodule.
3. Install their dependencies.
4. Import `essdive_package_service.asgi:app` and call `app.openapi()`.
5. Extract Dataset and recursively referenced definitions.
6. Conversion and post-processing currently pass through unchanged.
7. Validate reference completeness and source equality; upload artifacts.

No server or ASGI lifespan/startup handlers run. Import-time code still executes
and may require configuration, certificates, or network access. Import failures
stop publication: there is no fallback to a live API or reconstructed app.

## Source selection

`source.json` initially selects `v2.5.1`. This tag has not been verified against
the private repository here. Adjust it if necessary. `expected_commit` is null
because no verified package-service commit SHA was available. After checkout:

```bash
git -C .upstream/package-service rev-parse HEAD
```

Set `expected_commit` to that full SHA. The build will reject moved tags or wrong
checkouts. Alternatively set both `ref` and `expected_commit` to the SHA. Changes
to this file are the reviewable mechanism for adopting upstream releases.

The toolset revision comes from the release's submodule. A clean, dedicated
checkout is required; tracked modifications and mismatched submodules fail.
Imported package-service and toolset module paths are checked against that checkout.

This locks source once the SHA is set, but does not yet lock all pip dependencies.
The recorded build environment is an audit record, not a lockfile. Add a tested
dependency lock or a release-matched image pinned by digest before claiming fully
reproducible builds. If production uses a different toolset image from its source
submodule, reconcile that before claiming exact production equivalence.

## Offline local tests

From this project's root, using Python 3.10+ (no pip dependencies needed):

```bash
python -m unittest discover -s tests -v
python scripts/publish_schema.py --input tests/fixtures/openapi.json --output-dir dist
```

The fixture is synthetic. Tests cover extraction, reference failures, cycles,
unchanged definitions, provenance, source-revision checks, and a fake app export.
They do not establish real ESS-DIVE import compatibility.

## Local source build

Use WSL or your development container. Git needs read access to both private
repositories. Your container may not inherit WSL's GitHub login: clone in WSL first
if necessary. Never put credentials in clone URLs.

```bash
mkdir -p .upstream
git clone https://github.com/ess-dive/essdive-package-service.git .upstream/package-service
git -C .upstream/package-service checkout --detach v2.5.1
git -C .upstream/package-service submodule update --init --recursive
python scripts/build_from_source.py --check-only
```

Use the ref from your config if different. Set `expected_commit` as described
above. Install into a separate environment so these release dependencies do not
replace your development checkout's editable installations:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ./.upstream/package-service/toolset -e ./.upstream/package-service
.venv/bin/python -m pip check
.venv/bin/python scripts/build_from_source.py --output-dir dist
```

Your image must provide the source project's system dependencies. The Actions
workflow installs LDAP/SASL, SSL, XML/XSLT development libraries and a compiler.
If imports fail, inspect the error and supply the release's required non-production
configuration. This skeleton does not invent settings or disable authentication.

You can select an existing clean checkout at the configured revision:

```bash
python scripts/build_from_source.py --source-dir /path/to/checkout --output-dir dist
```

Use an interpreter containing that release's dependencies. Local generation does
not install dependencies or modify the source checkout.

## Outputs

- `dataset.schema.json`: Dataset and its referenced definitions, unchanged.
- `manifest.json`: API version, checksums, included schemas, source provenance.
- `openapi.json`: complete generated source snapshot, retained for replay.
- `source-provenance.json`: requested ref and package-service/toolset commits.
- `build-environment.json`: Python and distribution versions, without credentials.

The extracted output is an OpenAPI components fragment, retaining reference paths:

```json
{"components": {"schemas": {"Dataset": {}, "Person": {}}}}
```

Empty definitions above are illustrative. Actual definitions, including upstream
inconsistencies, are preserved. Whitespace/key ordering may differ. It is not a
standalone JSON Schema, complete OpenAPI document, or LinkML. Current checks verify
faithful extraction and local reference resolution, not metadata validity or
preservation of Python-only validators.

## GitHub Actions

Copy the project including `.github` into the target repository. Add an Actions
secret named `SOURCE_REPO_TOKEN`: a fine-grained token with Contents: read on
package-service, toolset, and any nested submodule repositories. Organization
approval may be needed. The default workflow token generally cannot access a
second private repository. Checkout does not persist credentials.

Offline tests run on pull requests, pushes to main, and manual dispatch. Source
build and artifact upload run only on main pushes or manual dispatch after tests
pass. External PRs do not need the secret. Review workflow/config changes before
merging; building executes the selected upstream source code.

Download results at Actions -> Test and publish Dataset schema -> run -> Artifacts.
Retention is 30 days. No Pages site, release, commit, or API deployment is created.
Upstream releases do not automatically trigger this workflow: update the pin and
run it to adopt a release.

## Optional explicit snapshot/live modes

No implicit live fetch remains. The extractor can still consume an explicit input:

```bash
python scripts/publish_schema.py --input /path/to/openapi.json --output-dir dist
python scripts/publish_schema.py --url https://api.ess-dive.lbl.gov/openapi.json --output-dir dist
```

## Future stages

Implement LinkML conversion in `convert()` and reviewed refinements in
`postprocess()`. Replace source-equality validation with LinkML and compatibility
tests at that point, keeping the original snapshot and provenance.

## Verification limits

Offline tests are available. The real private release, its dependencies,
import-time configuration, and GitHub-hosted workflow still need an authenticated
end-to-end run before this is relied upon for publication.
