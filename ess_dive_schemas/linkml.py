"""Direct conversion of the OpenAPI 3.0 subset used by ESS-DIVE metadata.

One recursive translator handles ordinary properties and composition branches.
Unknown constructs fail with a source path. Curated ESS-DIVE choices live in
policy.py; this is deliberately not a general JSON Schema importer.
"""

import hashlib
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml
from linkml.linter.linter import Linter
from linkml_runtime.linkml_model import SchemaDefinition

from ess_dive_schemas.policy import apply_policy, factor_slots
from ess_dive_schemas.publish import JsonObject, resolve_schema_ref

SCALAR_RANGES = {"string": "string", "number": "decimal", "integer": "integer", "boolean": "boolean"}
METADATA = {"title", "description", "example", "examples"}


def check_keys(node: JsonObject, allowed: set[str], path: str) -> None:
    unknown = set(node) - allowed - METADATA
    if unknown:
        raise ValueError(f"{path}: unsupported keywords {sorted(unknown)}")


def convert_to_linkml(fragment: JsonObject) -> SchemaDefinition:
    """Translate without modifying the input; retain non-enforced rules as annotations."""
    definitions = fragment.get("components", {}).get("schemas", {})
    if "Dataset" not in definitions:
        raise ValueError("Expected components.schemas.Dataset")
    model = {
        "id": "https://w3id.org/ess-dive/dataset/combined",
        "name": "ess_dive_dataset",
        "title": "ESS-DIVE Dataset metadata",
        "description": "Direct, curated OpenAPI conversion; see comments for policies and limitations.",
        "prefixes": {"linkml": "https://w3id.org/linkml/", "essdive": "https://w3id.org/ess-dive/dataset/",
                     "schema": "https://schema.org/", "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
                     "xsd": "http://www.w3.org/2001/XMLSchema#"},
        "imports": ["linkml:types"], "default_prefix": "essdive",
        "annotations": {"source_fragment_sha256": hashlib.sha256(
            json.dumps(fragment, sort_keys=True).encode()).hexdigest()},
        "comments": [
            "Scope: Dataset and transitive metadata dependencies. JSON keys and scalar-or-array alternatives are retained. @id is not promoted to an identifier.",
            "String lengths are represented by reusable string patterns; source regexes and numeric bounds are preserved. Source defaults are metadata, not inserted values.",
            "ContactPerson and DatasetProvider are curated role profiles; see their comments. Semantic mappings are explicit policy, not inferred from every property spelling.",
            "LIMITATIONS: json_schema_uniqueItems and json_schema_format annotations preserve rules without enforcing them. LinkML 1.11.1 JSON Schema output also admits some optional nulls and does not honor per-class extra_slots. Use gen-json-schema --closed for a closed Dataset root. This is not exact API-validator equivalence.",
        ],
        "types": {}, "enums": {}, "classes": {},
    }

    def expression(node: JsonObject, path: str) -> JsonObject:
        result = translate_expression(node, path)
        if node.get('description'):
            result['description'] = node['description'].strip()
        return result

    def translate_expression(node: JsonObject, path: str) -> JsonObject:
        if not isinstance(node, dict):
            raise ValueError(f"{path}: expected a schema object")
        if "anyOf" in node or "oneOf" in node:
            key = "anyOf" if "anyOf" in node else "oneOf"
            check_keys(node, {key}, path)
            if not isinstance(node[key], list) or not node[key]:
                raise ValueError(f"{path}/{key}: expected nonempty alternatives")
            return {"any_of" if key == "anyOf" else "exactly_one_of": [
                expression(branch, f"{path}/{key}/{i}") for i, branch in enumerate(node[key])]}
        if "allOf" in node:
            check_keys(node, {"allOf", "required"}, path)
            branches = node["allOf"]
            if not isinstance(branches, list) or len(branches) != 1 or not isinstance(branches[0], dict) or set(branches[0]) != {"$ref"}:
                raise ValueError(f"{path}/allOf: only a single class reference is supported")
            result = expression(branches[0], path + "/allOf/0")
            if result.get("range") not in definitions or definitions[result['range']].get('type') != 'object':
                raise ValueError(f"{path}/allOf: expected a class reference")
            if node.get("required"):
                if not isinstance(node['required'], list) or not all(isinstance(k, str) for k in node['required']):
                    raise ValueError(f"{path}/required: expected property names")
                result = {"inlined": True, "range_expression": {
                    "is_a": result['range'], "slot_conditions": {
                        k: {"required": True} for k in node['required']}}}
            return result
        if "$ref" in node:
            check_keys(node, {"$ref"}, path)
            name, target = resolve_schema_ref(fragment, node['$ref'])
            if target is not definitions[name]:
                raise ValueError(f"{path}: references must target a named schema, not a nested property")
            return {"range": name, **({"inlined": True} if target.get('type') == 'object' else {})}
        if node.get('type') == 'array':
            check_keys(node, {'type', 'items', 'minItems', 'maxItems', 'uniqueItems'}, path)
            result = expression(node.get('items'), path + '/items')
            if result.get('multivalued') or 'any_of' in result or 'exactly_one_of' in result:
                raise ValueError(f"{path}: nested arrays and composed array items are unsupported")
            result['multivalued'] = True
            if result.get('inlined'):
                result['inlined_as_list'] = True
            for source, dest in [('minItems','minimum_cardinality'),('maxItems','maximum_cardinality')]:
                if source in node:
                    result[dest] = node[source]
            if 'uniqueItems' in node:
                result.setdefault('annotations', {})['json_schema_uniqueItems'] = node['uniqueItems']
            return result
        kind = node.get('type')
        allowed = {'type', 'default'}
        allowed |= {'minLength', 'maxLength', 'pattern', 'format', 'enum'} if kind == 'string' else {'minimum', 'maximum'}
        check_keys(node, allowed, path)
        if kind not in SCALAR_RANGES:
            raise ValueError(f"{path}: unsupported type {kind!r}")
        result = {'range': SCALAR_RANGES[kind]}
        if 'enum' in node:
            values = node['enum']
            if not values or not all(isinstance(v, str) for v in values):
                raise ValueError(f"{path}/enum: expected nonempty string values")
            result['equals_string_in'] = values
        if 'minLength' in node or 'maxLength' in node:
            lo, hi = node.get('minLength', 0), node.get('maxLength', '')
            name = f'text_{lo}_{hi if hi != "" else "unbounded"}'
            length = f'at least {lo}' if hi == '' else f'{lo}–{hi}'
            model['types'][name] = {'typeof': 'string', 'uri': 'xsd:string',
                                   'description': f'String containing {length} characters.',
                                   'pattern': rf'^[\s\S]{{{lo},{hi}}}(?![\s\S])'}
            result['range'] = name
        if 'pattern' in node:
            if result['range'] == 'string':
                result['pattern'] = node['pattern']
            else:
                result['all_of'] = [{'pattern': node['pattern']}]
        for source, dest in [('minimum','minimum_value'),('maximum','maximum_value')]:
            if source in node:
                result[dest] = node[source]
        for key in ['default', 'format']:
            if key in node:
                result.setdefault('annotations', {})['json_schema_' + key] = node[key]
        return result

    for name, definition in definitions.items():
        path = '#/components/schemas/' + name
        if definition.get('type') == 'string' and 'enum' in definition:
            check_keys(definition, {'type', 'enum'}, path)
            values = definition['enum']
            if not values or not all(isinstance(v, str) for v in values):
                raise ValueError(f"{path}/enum: expected nonempty string values")
            model['enums'][name] = {'permissible_values': {v: None for v in values}}
            for key in ('title', 'description'):
                if definition.get(key):
                    model['enums'][name][key] = definition[key].strip()
            continue
        check_keys(definition, {'type', 'properties', 'required', 'additionalProperties'}, path)
        if definition.get('type') != 'object':
            raise ValueError(f"{path}: expected an object or string enum")
        extra = definition.get('additionalProperties', True)
        if not isinstance(extra, bool):
            raise ValueError(f"{path}/additionalProperties: only booleans are supported")
        properties = definition.get('properties', {})
        required = definition.get('required', [])
        if not isinstance(required, list) or not all(isinstance(k, str) for k in required):
            raise ValueError(f"{path}/required: expected property names")
        missing = set(required) - properties.keys()
        if missing:
            raise ValueError(f"{path}/required: undefined properties {sorted(missing)}; resolve in the source")
        cls = {'extra_slots': {'allowed': extra}, 'attributes': {}}
        if definition.get('description'):
            cls['description'] = definition['description'].strip()
        for key, node in properties.items():
            slot = expression(node, path + '/properties/' + key)
            if key in required:
                slot['required'] = True
            cls['attributes'][key] = slot
        model['classes'][name] = cls
    model['classes']['Dataset']['tree_root'] = True
    apply_policy(model, definitions)
    factor_slots(model)
    return SchemaDefinition(**model)


def write_linkml(fragment: JsonObject, output: Path) -> SchemaDefinition:
    """Validate before atomically replacing the output; keep YAML concise."""
    from linkml_runtime.utils.schema_as_dict import schema_as_dict

    schema = convert_to_linkml(fragment)
    content = yaml.safe_dump(schema_as_dict(schema), sort_keys=False, allow_unicode=True, width=100)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(mode='w', encoding='utf-8', dir=output.parent, suffix='.yaml', delete=False) as stream:
            stream.write(content)
            temporary = Path(stream.name)
        problems = list(Linter.validate_schema(str(temporary)))
        if problems:
            raise ValueError('Invalid LinkML: ' + '; '.join(p.message for p in problems))
        temporary.replace(output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return schema
