"""Load and compare the canonical metadata models from essdive-toolset.

The toolset still defines its schema with Pydantic v1 while LinkML depends on
Pydantic v2. This module loads only ``essdive.archive.schema`` through
Pydantic's bundled v1 compatibility layer, avoiding installation of the
toolset's unrelated service dependencies.
"""

from contextlib import contextmanager
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from typing import Iterator

import pydantic.v1 as pydantic_v1
from linkml_runtime.linkml_model import SchemaDefinition

from ess_dive_schemas.publish import JsonObject


DEFAULT_TOOLSET = Path("vendor/essdive-toolset")


@contextmanager
def _toolset_imports(toolset: Path) -> Iterator[None]:
    """Temporarily provide the minimal imports required by the model module."""
    names = (
        "pydantic",
        "email_validator",
        "essdive",
        "essdive.utilities",
        "essdive.archive",
        "essdive.archive.schema",
    )
    previous = {name: sys.modules.get(name) for name in names}
    try:
        sys.modules["pydantic"] = pydantic_v1

        # EmailStr checks for this optional package while constructing a model.
        # Schema export does not validate addresses, so no implementation is needed.
        email_validator = ModuleType("email_validator")
        email_validator.EmailNotValidError = ValueError  # type: ignore[attr-defined]
        sys.modules["email_validator"] = email_validator

        package = ModuleType("essdive")
        package.__path__ = [str(toolset / "essdive")]  # type: ignore[attr-defined]
        sys.modules["essdive"] = package

        utilities = ModuleType("essdive.utilities")
        utilities.to_camelcase = lambda value: "".join(  # type: ignore[attr-defined]
            index and part[0].upper() + part[1:] or part
            for index, part in enumerate(value.split("_"))
        )
        sys.modules["essdive.utilities"] = utilities

        archive = ModuleType("essdive.archive")
        archive.__path__ = [str(toolset / "essdive" / "archive")]  # type: ignore[attr-defined]
        sys.modules["essdive.archive"] = archive
        yield
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def load_toolset_fragment(toolset: Path = DEFAULT_TOOLSET) -> JsonObject:
    """Export the toolset's ``Dataset`` model as an OpenAPI components fragment.

    Raises a clear error when the submodule has not been initialized. Definitions
    are returned in the same shape consumed by the LinkML converter.
    """
    model_path = toolset / "essdive" / "archive" / "schema.py"
    if not model_path.is_file():
        raise FileNotFoundError(
            f"Canonical model not found at {model_path}; run "
            "`git submodule update --init --recursive`"
        )

    with _toolset_imports(toolset):
        spec = importlib.util.spec_from_file_location(
            "essdive.archive.schema", model_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Unable to load canonical model from {model_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        dataset = module.Dataset.schema(
            ref_template="#/components/schemas/{model}"
        )

    definitions = dataset.pop("definitions")
    definitions["Dataset"] = dataset
    return {"components": {"schemas": definitions}}


def validate_model_coverage(
    schema: SchemaDefinition, canonical: JsonObject
) -> None:
    """Verify that LinkML classes, enums, properties, and requiredness cover a model.

    This intentionally checks the structural contract rather than claiming full
    JSON Schema equivalence. Constraints with no direct LinkML representation are
    handled separately by the converter's annotations and documented limitations.
    """
    problems: list[str] = []
    for name, definition in canonical["components"]["schemas"].items():
        if definition.get("type") == "string" and "enum" in definition:
            enum = schema.enums.get(name)
            if enum is None:
                problems.append(f"missing enum {name}")
            elif set(enum.permissible_values) != set(definition["enum"]):
                problems.append(f"enum values differ for {name}")
            continue

        class_definition = schema.classes.get(name)
        if class_definition is None:
            problems.append(f"missing class {name}")
            continue
        expected_properties = set(definition.get("properties", {}))
        actual_properties = set(class_definition.attributes)
        if expected_properties != actual_properties:
            missing = sorted(expected_properties - actual_properties)
            extra = sorted(actual_properties - expected_properties)
            problems.append(f"{name} properties differ (missing={missing}, extra={extra})")
        expected_required = set(definition.get("required", []))
        actual_required = {
            slot_name
            for slot_name, slot in class_definition.attributes.items()
            if slot.required
        }
        if expected_required != actual_required:
            problems.append(
                f"{name} required properties differ "
                f"(expected={sorted(expected_required)}, actual={sorted(actual_required)})"
            )

    if problems:
        raise ValueError("LinkML does not cover the canonical toolset model: " + "; ".join(problems))
