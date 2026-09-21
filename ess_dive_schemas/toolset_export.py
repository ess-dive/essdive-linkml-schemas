"""Export the canonical toolset Dataset model for the main conversion process."""

import json

from essdive.archive.schema import Dataset


def main() -> None:
    """Write the canonical Dataset dependency closure as an OpenAPI fragment."""
    dataset = Dataset.schema(ref_template="#/components/schemas/{model}")
    definitions = dataset.pop("definitions")
    definitions["Dataset"] = dataset
    print(json.dumps({"components": {"schemas": definitions}}, sort_keys=True))


if __name__ == "__main__":
    main()
