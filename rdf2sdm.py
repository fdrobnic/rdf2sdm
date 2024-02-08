import json
import os

import rdflib.paths
import yaml
from rdflib import Graph, URIRef, Literal, RDFS, DCTERMS, OWL, XSD

import out_util
import graph_util


class Rdf2sdm:
    g: Graph
    globalDesc: str
    baseUri: str
    dataModel: str = ''
    objectRoot: URIRef  # class IRI for which the output is to be written
    subject: str  # class name (last fragment from IRI) for which the output is to be written
    schema_obj: dict
    propertyAttrs: dict

    def __init__(self, rdfFile: str, baseUri: str):
        """

        Args:
            rdfFile: path to RDF file
            baseUri: base URI
        """
        self.g = Graph()
        self.baseUri = baseUri

        result = self.g.parse(source=rdfFile)

        t = list(self.g.triples((URIRef(self.baseUri), RDFS.label, None)))
        if len(t) == 0:
            t = list(self.g.triples((URIRef(self.baseUri), DCTERMS.description, None)))

        self.globalDesc = t[0][2]

    def translate(self, data_model: str, rootUri: str) -> int:
        """

        Args:
            data_model: repository name
            rootUri: class IRI to parse

        Returns:
            status: int

        """
        self.objectRoot = URIRef(rootUri)
        self.dataModel = data_model
        self.subject = graph_util.get_subject(self.objectRoot)
        desc = list(self.g.triples((self.objectRoot, RDFS.comment, None)))[0][2]
        if isinstance(desc, Literal):
            desc = desc.value
        self.schema_obj = {
            "$schema": "http://json-schema.org/schema#",
            "$schemaVersion": "0.0.1",
            "$id": 'https://smart-data-models.github.com/dataModel.' + self.dataModel + '/' + self.subject + '/schema.json',
            "title": "Smart data models - " + self.subject + ' schema',
            "modelTags": self.dataModel + ' ' + self.subject,
            "description": desc,
            "type": "object",
            "derivedFrom": self.baseUri,
            "license": "https://opensource.org/licenses/BSD-3-Clause",  # TODO CCBY 4 ?
            "allOf": [
                {
                    "$ref": "https://smart-data-models.github.io/data-models/common-schema.json#/definitions/GSMA-Commons"
                },
                {
                    "$ref": "https://smart-data-models.github.io/data-models/common-schema.json#/definitions/Location-Commons"
                }
            ]
        }

        prop = {
            "type": {
                "type": "string",
                "description": "Property. NGSI entity type. It must be equal to `" + self.subject + "`",
                "enum": [
                    self.subject
                ]
            }
        }

        # li = graph_util.get_leaves(g)
        cl = list(rdflib.paths.eval_path(self.g, (None, RDFS.subClassOf * rdflib.paths.OneOrMore, self.objectRoot)))
        if len(cl) == 0:
            cl = [(self.objectRoot, None, None)]
        self.propertyAttrs = {}
        for r in cl:
            for l in self.g.triples((r[0], RDFS.subClassOf, None)):
                pr = list(self.g.triples((l[2], OWL.onProperty, None)))
                if len(pr) == 0:
                    continue
                k = graph_util.get_subject(pr[0][2])
                dts = list(self.g.triples((l[2], (OWL.allValuesFrom | OWL.someValuesFrom), None)))
                if len(dts) == 0:
                    dts = list(self.g.triples((pr[0][2], RDFS.range, None)))
                fmt = ''
                if dts[0][2] in [XSD.decimal, XSD.numeric, XSD.int, XSD.integer, XSD.float, XSD.double]:
                    dt = 'number'
                    mdl = 'https://schema.org/Number'
                elif dts[0][2] == XSD.string:
                    dt = 'string'
                    mdl = 'https://schema.org/Text'
                elif dts[0][2] in [XSD.date, XSD.dateTime, XSD.dateTimeStamp]:
                    dt = 'string'
                    mdl = 'https://schema.org/Text'
                    if dts[0][2] == XSD.date:
                        fmt = 'date'
                    elif dts[0][2] in [XSD.dateTime, XSD.dateTimeStamp]:
                        fmt = 'date-time'
                elif dts[0][2] == XSD.boolean:
                    dt = 'boolean'
                    mdl = 'https://schema.org/Boolean'
                else:
                    dt = '---'
                    mdl = ''
                d = ''
                for a in self.g.triples((pr[0][2], RDFS.comment, None)):
                    # dt = graph_util.get_datatype(g, l)
                    if isinstance(a[2], Literal):
                        d = a[2].value
                    else:
                        d = a[2]
                v = {
                    'type': dt,
                    # 'minimum': 0,  # TODO
                    'description': "Property. Model: '" + mdl + "'. " + d
                }
                if fmt != '':
                    v['format'] = fmt
                if k != '' and v != {}:
                    prop[k] = v
                self.propertyAttrs[k] = {'description': d, 'model': mdl, 'iri': pr[0][2].__str__()}

        self.schema_obj['allOf'].append({'properties': prop})
        self.schema_obj['required'] = [
            "id",
            "type"
        ]

        return 1

    def write_model_notes(self, outDir: str) -> None:
        """
        Writes the model notes.

        Args:
            dataModel: class name for which the output is to be written
        """
        out_util.write_notes(self.g, dataModel=self.dataModel, outDir=outDir)

    def write_subject_notes(self, outDir: str):
        """
        Writes the subject notes.

        Args:
            dataModel: repository name
            objectRoot: class IRI for which the output is to be written
        """

        out_util.write_subject_notes(dataModel=self.dataModel, root=self.objectRoot, desc=self.globalDesc, outDir=outDir)

    def write_notes_context(self, outDir: str):
        """

        Args:
            dataModel: class name for which the output is to be written
        """
        if not isinstance(self.schema_obj, dict):
            return False

        prop = {}
        for a in self.schema_obj['allOf']:
            if 'properties' in a.keys():
                prop = a['properties']
                break
        # @context:
        dirName = outDir + '/dataModel.' + self.dataModel
        try:
            os.mkdir(dirName)
        except FileExistsError:
            pass
        context_filename = dirName + '/notes_context.jsonld'
        try:
            with open(context_filename, 'r') as infile:
                c1 = json.loads(infile.read())['@context']
        except FileNotFoundError:
            c1 = {}
        c = {}
        c[self.subject] = self.objectRoot.__str__()
        for k in prop:
            if k != 'type':
                c[k] = self.propertyAttrs[k]['iri']
        for k, v in c.items():
            c1[k] = v
        co = {'@context': c1}

        with open(context_filename, "w") as outfile:
            outfile.write(json.dumps(co, indent=2))

    def write_schema(self, outDir: str):
        if not isinstance(self.schema_obj, dict):
            return False

        schema = json.dumps(self.schema_obj, indent=4)
        with open(outDir + '/dataModel.' + self.dataModel + '/' + self.subject + '/schema.json', 'w') as outfile:
            r = outfile.write(schema)

        return r

    def write_context(self, outDir: str):
        if not isinstance(self.schema_obj, dict):
            return False

        prop = {}
        for a in self.schema_obj['allOf']:
            if 'properties' in a.keys():
                prop = a['properties']
                break
        # @context:
        dirName = outDir + '/dataModel.' + self.dataModel + '/master'
        try:
            os.mkdir(dirName)
        except FileExistsError:
            pass
        context_filename = dirName + '/context.jsonld'
        try:
            with open(context_filename, 'r') as infile:
                c1 = json.loads(infile.read())['@context']
        except FileNotFoundError:
            c1 = {}
        c = {}
        c[self.subject] = 'https://smartdatamodels.org/dataModel.' + self.dataModel + '/' + self.subject
        for k in prop:
            if k != 'type':
                c[k] = 'https://smartdatamodels.org/dataModel.' + self.dataModel + '/' + k
        c["id"] = "@id"
        c["type"] = "@type"
        c["ngsi-ld"] = "https://uri.etsi.org/ngsi-ld/"
        for k, v in c.items():
            c1[k] = v
        co = {'@context': c1}

        with open(context_filename, 'w+t') as outfile:
            r = outfile.write(json.dumps(co, indent=4, sort_keys=True))

        return r

    def write_model_yaml(self, outDir: str):
        if not isinstance(self.schema_obj, dict):
            return False

        prop = {}
        for a in self.schema_obj['allOf']:
            if 'properties' in a.keys():
                prop = a['properties']
                break
        prop_y = {}
        for k, v in prop.items():
            # yaml:
            v_y = {}
            v_y['type'] = v['type']
            # 'minimum': 0,  # TODO
            if k == 'type':
                v_y['description'] = v['description']
            else:
                v_y['description'] = self.propertyAttrs[k]['description']
            if 'enum' in v.keys():
                v_y['enum'] = v['enum']
            v_y['x-ngsi'] = {
                'type': 'Property',
            }
            if k != 'type':
                v_y['x-ngsi']['model'] = self.propertyAttrs[k]['model']
            if 'format' in v.keys() and v['format'] != '':
                v_y['format'] = v['format']
            prop_y[k] = v_y

        # YAML:
        yn = {
            self.subject: {
                'description': self.schema_obj['description'],
                'properties': prop_y,
                'required': ['id', 'type'],
                'type': 'object',
                'x-derived-from': self.baseUri,
                'x-disclaimer': 'Redistribution and use in source and binary forms, with or without modification, are permitted  provided that the license conditions are met. Copyleft (c) 2022 Contributors to Smart Data Models Program',
                'x-license-url': 'https://github.com/smart-data-models/dataModel.' + self.dataModel + '/blob/master/' + self.subject + '/LICENSE.md',
                'x-model-schema': 'https://smart-data-models.github.com/dataModel.' + self.dataModel + '/' + self.subject + '/schema.json',
                'x-model-tags': self.dataModel + ' ' + self.subject,
                'x-version': '0.0.1'
            }
        }

        with open(outDir + '/dataModel.' + self.dataModel + '/' + self.subject + '/model.yaml', 'w') as file:
            doc = yaml.dump(data=yn, stream=file, Dumper=yaml.SafeDumper)

        return True

    def write_ngsi_ld_example(self, outDir: str):
        schema = json.dumps(self.schema_obj, indent=4)

        e = out_util.write_ngsi_ld_examples(schema, dataModel=self.dataModel, subject=self.subject, outDir=outDir)

        return e
