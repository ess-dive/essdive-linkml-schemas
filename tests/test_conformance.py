"""Behavioral checks independent of converter internals or the toolset environment."""

import copy
import json
from pathlib import Path
import unittest

from jsonschema import Draft201909Validator
from linkml.generators.jsonschemagen import JsonSchemaGenerator

from ess_dive_schemas.linkml import convert_to_linkml
from ess_dive_schemas.publish import select_dataset

ROOT = Path(__file__).parents[1]
base={'name':'Example','description':'Description','datePublished':'2026','creator':{'familyName':'Researcher'},'keywords':['soil'],'funder':{'name':'Funder'},'editor':{'familyName':'Contact','email':'a@example.org'},'provider':{'identifier':{'value':'project-id'},'member':{'familyName':'PI','jobTitle':'Principal Investigator'}}}
cases=[]
def case(label,path,value,valid):
 d=copy.deepcopy(base);at=d
 for k in path[:-1]:at=at[k]
 if value is DELETE:del at[path[-1]]
 else:at[path[-1]]=value
 cases.append((label,d,valid))
DELETE=object()
cases.append(('minimal scalar shapes',base,True))
case('creator array',['creator'],[base['creator']],True)
case('description array',['description'],['One','Two'],True)
case('keyword scalar',['keywords'],'soil',True)
case('empty creators',['creator'],[],False)
case('empty keyword array',['keywords'],[],False)
case('empty description',['description'],'',False)
case('empty description array',['description'],[],False)
case('name boundary',['name'],'x'*512,True)
case('name too long',['name'],'x'*513,False)
case('name newline boundary',['name'],'x'*512+'\n',False)
case('empty name',['name'],'',False)
case('missing editor email',['editor','email'],DELETE,False)
case('bad date',['datePublished'],'not a date',False)
case('full date',['datePublished'],'2026-09-22',True)
case('missing provider identifier',['provider','identifier'],DELETE,False)
case('missing provider member',['provider','member'],DELETE,False)
case('bad dataset id',['@id'],'ess-dive-123',False)
case('long dataset id',['@id'],'x'*2049,False)
case('long keyword',['keywords'],['x'*176],False)
case('extra dataset field',['unexpected'],True,False)
place={'description':'Site','geo':{'name':'Northwest','latitude':45,'longitude':-120}}
case('scalar coordinates',['spatialCoverage'],place,True)
bad=copy.deepcopy(place);bad['geo']['latitude']=91;case('latitude bounds',['spatialCoverage'],bad,False)
bad=copy.deepcopy(place);bad['geo']=[bad['geo']]*3;case('coordinate cardinality',['spatialCoverage'],bad,False)
bad=copy.deepcopy(place);bad['geo']['name']='northwest';case('coordinate enum',['spatialCoverage'],bad,False)


class BehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        document = json.loads((ROOT / 'openapi.json').read_text())
        schema = convert_to_linkml(select_dataset(document))
        generated = json.loads(JsonSchemaGenerator(schema, not_closed=False).serialize())
        Draft201909Validator.check_schema(generated)
        cls.validator = Draft201909Validator(generated)

    def test_acceptance_and_boundary_cases(self):
        for label, data, expected in cases:
            with self.subTest(label=label):
                errors = list(self.validator.iter_errors(data))
                self.assertEqual(not errors, expected, [e.message for e in errors])

    def test_known_generator_gaps_are_explicit(self):
        for data in [dict(base, keywords=['soil', 'soil']), dict(base, license=None)]:
            self.assertTrue(self.validator.is_valid(data))
        data = copy.deepcopy(base)
        data['creator']['extra_field'] = 'allowed by source, closed by generator'
        self.assertFalse(self.validator.is_valid(data))

    def test_inline_enum_and_exclusive_alternatives(self):
        document = {'components': {'schemas': {'Dataset': {
            'type': 'object', 'required': ['status', 'choice'], 'properties': {
                'status': {'type': 'string', 'enum': ['draft', 'published']},
                'choice': {'oneOf': [{'type': 'integer'}, {'type': 'number'}]},
            }}}}}
        generated = json.loads(JsonSchemaGenerator(convert_to_linkml(document), not_closed=False).serialize())
        validator = Draft201909Validator(generated)
        self.assertTrue(validator.is_valid({'status': 'draft', 'choice': 1.5}))
        self.assertFalse(validator.is_valid({'status': 'draft', 'choice': 1}))
        self.assertFalse(validator.is_valid({'status': 'unknown', 'choice': 1.5}))
