"""Small, explicit ESS-DIVE modeling choices, separate from source translation."""

from copy import deepcopy

# These mappings are curated, not inferred for arbitrary property names.
SCHEMA_PROPERTIES = set('name description datePublished alternateName creator keywords variableMeasured license spatialCoverage award funder citation editor provider contributor temporalCoverage measurementTechnique hasPart archivedAt identifier sameAs email givenName familyName affiliation member jobTitle geo latitude longitude startDate endDate url propertyID value'.split())
CLASS_URIS = {name: 'schema:' + name for name in ['Dataset', 'Person', 'Organization', 'Place', 'GeoCoordinates', 'WebPage']}
CLASS_URIS.update(OrganizationMember='schema:Person', PropertyValueDOI='schema:PropertyValue', PropertyValueEssDive='schema:PropertyValue')
SHARED = '@type name description email givenName familyName affiliation propertyID value'.split()


def apply_policy(model, source):
    classes = model['classes']
    for name, cls in classes.items():
        if name in CLASS_URIS:
            cls['class_uri'] = CLASS_URIS[name]
        for key, slot in cls['attributes'].items():
            if key in SCHEMA_PROPERTIES:
                slot['slot_uri'] = 'schema:' + key
            elif key == '@type':
                slot['slot_uri'] = 'rdf:type'
    dataset = classes['Dataset']['attributes']
    for field, base, profile, required in [
        ('editor', 'Person', 'ContactPerson', ['email']),
        ('provider', 'ProjectOrganizationIdentifier', 'DatasetProvider', ['member']),
    ]:
        original = source['Dataset'].get('properties', {}).get(field, {})
        if original.get('allOf') != [{'$ref': '#/components/schemas/' + base}]:
            continue
        if original.get('required') != required:
            raise ValueError(f'Dataset.{field}: role requirements changed; review policy.py')
        if profile in classes:
            raise ValueError(f'{profile}: source conflicts with curated profile name')
        role = {'is_a': base, 'extra_slots': deepcopy(classes[base]['extra_slots'])}
        if field == 'editor':
            if 'email' not in classes[base]['attributes']:
                raise ValueError('Person.email missing; review contact policy')
            role.update(class_uri='schema:Person', slot_usage={'email': {'required': True}},
                        comments=['Source-derived role: email is required only for the dataset contact.'])
        else:
            if 'Organization' not in classes or 'member' not in classes['Organization']['attributes']:
                raise ValueError('Organization.member missing; review provider policy')
            role['attributes'] = deepcopy(classes['Organization']['attributes'])
            for slot in role['attributes'].values():
                slot.pop('required', None)
            role['attributes']['member']['required'] = True
            role['comments'] = ['CURATED: the source requires member without constraining its value. This profile uses Organization.member and optional organization fields found in existing provider records. ProjectOrganizationIdentifier itself is unchanged.']
        classes[profile] = role
        dataset[field].pop('range_expression', None)
        dataset[field]['range'] = profile


def factor_slots(model):
    """Factor shared definitions once, retaining class-specific constraints locally."""
    model['slots'] = {}
    for key in SHARED:
        owners = [c for c in model['classes'].values() if key in c.get('attributes', {})]
        if len(owners) < 2:
            continue
        definitions = [c['attributes'][key] for c in owners]
        common = {k: v for k, v in definitions[0].items()
                  if k not in {'required', 'description', 'annotations'} and all(d.get(k) == v for d in definitions)}
        if not common:
            continue
        model['slots'][key] = common
        for cls in owners:
            local = {k: v for k, v in cls['attributes'].pop(key).items() if k not in common}
            cls.setdefault('slots', []).append(key)
            if local:
                cls.setdefault('slot_usage', {}).setdefault(key, {}).update(local)
