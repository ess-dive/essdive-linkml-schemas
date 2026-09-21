"""Black-box conformance tests against the canonical toolset validator."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from linkml.validator import Validator
from linkml.validator.plugins import JsonschemaValidationPlugin

from ess_dive_schemas.linkml import write_linkml
from ess_dive_schemas.publish import load_toolset_schema


ROOT = Path(__file__).parents[1]
TOOLSET_FIXTURES = ROOT / "vendor/essdive-toolset/tests/resources/metadata/jsonld"
ORACLE = Path(__file__).with_name("toolset_oracle.py")
PRODUCTION_SCHEMA = ROOT / "tests/fixtures/ess_dive_dataset_full.json"

VALID_CASES = (
    "correct_package",
    "correct_package_minimal",
    "added_citation",
    "valid_contributor",
    "many_creators",
    "email_added_funder",
    "string_measurmenttechnique",
    "valid_jobtitle_member_provider",
    "multiple_places_spacial_coverage",
    "single_object_spatial_geo",
    "valid_orcid",
    "long_description",
    "long_measurementTechnique",
    "long_spatialCoverage_description",
)

# These cases exercise constraints represented in the generated LinkML. The
# toolset also has invalid cases for custom checks and known conversion gaps;
# those are intentionally not claimed as LinkML conformance yet.
INVALID_CASES = (
    "invalid_same_as",
    "typo_context",
    "empty_creators",
    "no_creators",
    "empty_description_array",
    "multiple_editors",
    "no_editor",
    "no_email_editors",
    "no_family_name_editors",
    "lower_case_geo_names_spacial_coverage",
    "wrong_geo_names_spacial_coverage",
    "identifier_not_allowed_spatial_coverage",
    "more_than_two_geo_coordinates",
    "typo_startdate_temporalcoverage",
    "no_provider_id",
)


class ToolsetConformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        """Generate one final schema and initialize both independent validators."""
        default_python = ROOT / ".toolset-venv/bin/python"
        cls.toolset_python = Path(
            os.environ.get("ESSDIVE_TOOLSET_PYTHON", default_python)
        )
        if not cls.toolset_python.is_file():
            raise RuntimeError(
                "toolset validator environment is missing; run "
                "`uv venv .toolset-venv` and then `uv pip install --python "
                ".toolset-venv/bin/python ./vendor/essdive-toolset`"
            )

        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary_directory.cleanup)
        output = Path(cls.temporary_directory.name) / "essdive_metadata_schema.yaml"
        fragment = load_toolset_schema(cls.toolset_python)
        write_linkml(fragment, output)
        cls.validator = Validator(
            output,
            validation_plugins=[JsonschemaValidationPlugin(closed=True)],
        )

    @classmethod
    def canonical_results(cls, names: tuple[str, ...]) -> dict[str, bool]:
        """Classify fixtures with the toolset's installed production validator."""
        paths = [TOOLSET_FIXTURES / f"{name}.jsonld" for name in names]
        result = subprocess.run(
            [str(cls.toolset_python), str(ORACLE), *map(str, paths)],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    @classmethod
    def linkml_accepts(cls, name: str) -> bool:
        """Validate one fixture through LinkML's official JSON Schema plugin."""
        path = TOOLSET_FIXTURES / f"{name}.jsonld"
        data = json.loads(path.read_text(encoding="utf-8"))
        return not any(cls.validator.iter_results(data, "Dataset"))

    def test_all_canonical_valid_records_are_accepted(self) -> None:
        """Prevent false negatives for every valid toolset metadata fixture."""
        canonical = self.canonical_results(VALID_CASES)
        for name in VALID_CASES:
            with self.subTest(name=name):
                self.assertTrue(canonical[f"{name}.jsonld"])
                self.assertTrue(self.linkml_accepts(name))

    def test_represented_invalid_records_are_rejected(self) -> None:
        """Require parity for canonical failures covered by current LinkML."""
        canonical = self.canonical_results(INVALID_CASES)
        for name in INVALID_CASES:
            with self.subTest(name=name):
                self.assertFalse(canonical[f"{name}.jsonld"])
                self.assertFalse(self.linkml_accepts(name))

    def test_production_openapi_drift_is_explicit(self) -> None:
        """Keep API/model drift separate from behavioral conversion failures."""
        canonical = load_toolset_schema(self.toolset_python)["components"]["schemas"]
        provider_name = canonical["Dataset"]["properties"].pop("providerName")

        production = json.loads(PRODUCTION_SCHEMA.read_text(encoding="utf-8"))
        self.assertNotIn(
            "providerName",
            production["components"]["schemas"]["Dataset"]["properties"],
        )
        self.assertEqual(provider_name["type"], "string")
        self.assertEqual(canonical, production["components"]["schemas"])


if __name__ == "__main__":
    unittest.main()
