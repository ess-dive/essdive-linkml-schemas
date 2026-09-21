"""Compatibility tests against the canonical essdive-toolset metadata model."""

from pathlib import Path
import tempfile
import unittest

from linkml_runtime.loaders import yaml_loader
from linkml_runtime.linkml_model import SchemaDefinition

from ess_dive_schemas.linkml import write_linkml
from ess_dive_schemas.toolset import load_toolset_fragment, validate_model_coverage


TOOLSET = Path(__file__).parents[1] / "vendor" / "essdive-toolset"


class ToolsetCompatibilityTests(unittest.TestCase):
    def test_canonical_dataset_model_converts_without_structural_loss(self) -> None:
        """Convert the real model closure and compare the final LinkML structure."""
        canonical = load_toolset_fragment(TOOLSET)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "schema.yaml"
            write_linkml(canonical, output)
            schema = yaml_loader.load(str(output), target_class=SchemaDefinition)
        validate_model_coverage(schema, canonical)


if __name__ == "__main__":
    unittest.main()
