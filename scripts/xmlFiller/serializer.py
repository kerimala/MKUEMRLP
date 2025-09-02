"""
Serializer module for NSG PDF to XML/JSON converter.
Handles generation of XML and JSON output files.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from lxml import etree
from collections import OrderedDict

logger = logging.getLogger('nsg_converter.serializer')


class Serializer:
    """Serialize extracted rules to XML and JSON formats."""
    
    def __init__(self, schema_loader):
        """
        Initialize serializer.
        
        Args:
            schema_loader: Schema loader instance
        """
        self.schema = schema_loader
        
    def serialize(self, rules: List[Dict[str, Any]], 
                 output_path: str,
                 filename_base: str,
                 generate_report: bool = False) -> Dict[str, str]:
        """
        Serialize rules to XML and JSON files.
        
        Args:
            rules: List of extracted rules
            output_path: Output directory path
            filename_base: Base filename (without extension)
            generate_report: Whether to generate report file
        
        Returns:
            Dict with paths to generated files
        """
        output_dir = Path(output_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Build canonical data structure
        document = self.build_document_structure(rules)
        
        # Generate XML
        xml_path = output_dir / f"{filename_base}.xml"
        self.write_xml(document, xml_path)
        
        # Generate JSON
        json_path = output_dir / f"{filename_base}.json"
        self.write_json(document, json_path)
        
        results = {
            'xml': str(xml_path),
            'json': str(json_path)
        }
        
        # Generate report if requested
        if generate_report:
            report_path = output_dir / f"{filename_base}.report.json"
            report = self.generate_report(rules, document)
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            results['report'] = str(report_path)
        
        logger.info(f"Generated outputs for {filename_base}")
        return results
    
    def build_document_structure(self, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Build canonical document structure from rules.
        
        Args:
            rules: List of extracted rules
        
        Returns:
            Canonical document structure
        """
        # Get document metadata from first rule (if available)
        doc_metadata = rules[0].get('document_metadata', {}) if rules else {}
        
        document = OrderedDict([
            ('schutzgebiet', OrderedDict([
                ('name', doc_metadata.get('schutzgebiet_name', 'Unbekannt')),
                ('kennung', doc_metadata.get('kennung', '')),
                ('datum', doc_metadata.get('datum', '')),
                ('behoerde', doc_metadata.get('behoerde', ''))
            ])),
            ('regeln', [])
        ])
        
        # Process each rule
        for rule in rules:
            regel_data = self.build_regel_structure(rule)
            document['regeln'].append(regel_data)
        
        return document
    
    def build_regel_structure(self, rule: Dict[str, Any]) -> OrderedDict:
        """
        Build structure for a single rule.
        
        Args:
            rule: Rule data
        
        Returns:
            Structured rule data
        """
        regel = OrderedDict()
        
        # Add basic fields
        if rule.get('paragraf_nummer'):
            regel['paragraf'] = rule['paragraf_nummer']
        
        if rule.get('paragraf_rubrum'):
            regel['rubrum'] = rule['paragraf_rubrum']
        
        if rule.get('aktivitaet'):
            regel['aktivitaet'] = rule['aktivitaet']
        
        if rule.get('ort'):
            regel['ort'] = rule['ort']
        
        if rule.get('erlaubnis'):
            regel['erlaubnis'] = rule['erlaubnis']
        
        # Add zone if present
        if rule.get('zone'):
            regel['zone'] = self.build_zone_structure(rule['zone'])
        
        # Add conditions
        if rule.get('bedingungen'):
            regel['bedingungen'] = self.build_bedingungen_structure(rule['bedingungen'])
        
        # Add original text as comment if available
        if rule.get('original_text'):
            regel['kommentar'] = rule['original_text'][:500]  # Limit length
        
        return regel
    
    def build_zone_structure(self, zone: Dict[str, Any]) -> OrderedDict:
        """Build zone structure."""
        zone_data = OrderedDict()
        
        if zone.get('typ'):
            zone_data['typ'] = zone['typ']
        
        if zone.get('name'):
            zone_data['name'] = zone['name']
        
        return zone_data
    
    def build_bedingungen_structure(self, bedingungen: List[Dict[str, Any]]) -> List[OrderedDict]:
        """Build conditions structure."""
        structured = []
        
        for bedingung in bedingungen:
            cond = OrderedDict()
            
            # Type is always first
            cond['typ'] = bedingung.get('typ', 'sonstiges')
            
            # Add type-specific fields
            if bedingung.get('typ') == 'abstand_m':
                if 'vergleich' in bedingung:
                    cond['vergleich'] = bedingung['vergleich']
                if 'value_num' in bedingung:
                    cond['value_num'] = bedingung['value_num']
                if 'einheit' in bedingung:
                    cond['einheit'] = bedingung['einheit']
                if 'bezugsflaeche' in bedingung:
                    cond['bezugsflaeche'] = bedingung['bezugsflaeche']
                if 'bezug' in bedingung:
                    cond['bezug'] = bedingung['bezug']
            
            elif bedingung.get('typ') == 'datumspanne':
                if 'date_from' in bedingung:
                    cond['date_from'] = bedingung['date_from']
                if 'date_to' in bedingung:
                    cond['date_to'] = bedingung['date_to']
            
            elif bedingung.get('typ') == 'tageszeit':
                if 'time_from' in bedingung:
                    cond['time_from'] = bedingung['time_from']
                if 'time_to' in bedingung:
                    cond['time_to'] = bedingung['time_to']
            
            elif bedingung.get('typ') in ['jahreszeit', 'wochentag', 'wetter']:
                if 'value' in bedingung:
                    cond['value'] = bedingung['value']
            
            elif bedingung.get('typ') == 'feiertag_event':
                if 'event_name' in bedingung:
                    cond['event_name'] = bedingung['event_name']
            
            elif bedingung.get('typ') in ['motor_leistung_kw', 'geschwindigkeit', 
                                         'personen_max', 'menge_limit']:
                if 'vergleich' in bedingung:
                    cond['vergleich'] = bedingung['vergleich']
                if 'value_num' in bedingung:
                    cond['value_num'] = bedingung['value_num']
                if 'einheit' in bedingung:
                    cond['einheit'] = bedingung['einheit']
                if 'stoff' in bedingung:
                    cond['stoff'] = bedingung['stoff']
            
            elif bedingung.get('typ') == 'zonenbezug':
                if 'zone' in bedingung:
                    cond['zone'] = bedingung['zone']
            
            # Add note or bemerkung if present
            if 'note' in bedingung:
                cond['note'] = bedingung['note']
            if 'bemerkung' in bedingung:
                cond['bemerkung'] = bedingung['bemerkung']
            
            structured.append(cond)
        
        return structured
    
    def write_xml(self, document: Dict[str, Any], output_path: Path):
        """
        Write document to XML file.
        
        Args:
            document: Document structure
            output_path: Output file path
        """
        # Create root element
        root = etree.Element('nsg_dokument')
        
        # Add schutzgebiet element
        schutzgebiet = etree.SubElement(root, 'schutzgebiet')
        for key, value in document['schutzgebiet'].items():
            if value:
                elem = etree.SubElement(schutzgebiet, key)
                elem.text = str(value)
        
        # Add regeln
        regeln = etree.SubElement(root, 'regeln')
        for regel_data in document['regeln']:
            regel = etree.SubElement(regeln, 'regel')
            self._add_regel_to_xml(regel, regel_data)
        
        # Write to file with pretty printing
        tree = etree.ElementTree(root)
        tree.write(
            str(output_path),
            pretty_print=True,
            xml_declaration=True,
            encoding='UTF-8'
        )
        
        logger.info(f"Wrote XML to {output_path}")
    
    def _add_regel_to_xml(self, parent: etree.Element, regel_data: Dict):
        """Add regel data to XML element."""
        for key, value in regel_data.items():
            if key == 'bedingungen' and isinstance(value, list):
                bedingungen = etree.SubElement(parent, 'bedingungen')
                for bedingung in value:
                    bed_elem = etree.SubElement(bedingungen, 'bedingung')
                    for bed_key, bed_value in bedingung.items():
                        bed_elem.set(bed_key, str(bed_value))
            elif key == 'zone' and isinstance(value, dict):
                zone = etree.SubElement(parent, 'zone')
                for zone_key, zone_value in value.items():
                    zone.set(zone_key, str(zone_value))
            elif value:
                elem = etree.SubElement(parent, key)
                elem.text = str(value)
    
    def write_json(self, document: Dict[str, Any], output_path: Path):
        """
        Write document to JSON file.
        
        Args:
            document: Document structure
            output_path: Output file path
        """
        # Convert OrderedDict to regular dict for JSON
        json_doc = json.loads(json.dumps(document))
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(
                json_doc,
                f,
                indent=2,
                ensure_ascii=False,
                sort_keys=False  # Preserve order
            )
        
        logger.info(f"Wrote JSON to {output_path}")
    
    def generate_report(self, rules: List[Dict[str, Any]], 
                       document: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate processing report.
        
        Args:
            rules: Original rules
            document: Processed document
        
        Returns:
            Report data
        """
        report = {
            'timestamp': datetime.now().isoformat(),
            'statistics': {
                'total_rules': len(rules),
                'total_paragraphs': len(set(r.get('paragraf_nummer') for r in rules if r.get('paragraf_nummer'))),
                'rules_with_aktivitaet': sum(1 for r in rules if r.get('aktivitaet')),
                'rules_with_ort': sum(1 for r in rules if r.get('ort')),
                'rules_with_bedingungen': sum(1 for r in rules if r.get('bedingungen')),
            },
            'coverage': self.calculate_coverage(rules),
            'unknown_values': self.find_unknown_values(rules),
            'enum_usage': self.calculate_enum_usage(rules)
        }
        
        return report
    
    def calculate_coverage(self, rules: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate coverage metrics."""
        total = len(rules) if rules else 1
        
        return {
            'aktivitaet_coverage': (sum(1 for r in rules if r.get('aktivitaet')) / total) * 100,
            'ort_coverage': (sum(1 for r in rules if r.get('ort')) / total) * 100,
            'erlaubnis_coverage': (sum(1 for r in rules if r.get('erlaubnis')) / total) * 100,
            'bedingungen_coverage': (sum(1 for r in rules if r.get('bedingungen')) / total) * 100,
        }
    
    def find_unknown_values(self, rules: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """Find values that couldn't be mapped to enums."""
        unknown = {
            'aktivitaet': [],
            'ort': [],
            'bedingungen': []
        }
        
        for rule in rules:
            # Check for sonstiges values
            if rule.get('aktivitaet') == 'sonstiges':
                if rule.get('original_text'):
                    unknown['aktivitaet'].append(rule['original_text'][:100])
            
            if rule.get('ort') == 'sonstiges':
                if rule.get('original_text'):
                    unknown['ort'].append(rule['original_text'][:100])
            
            # Check conditions
            for bedingung in rule.get('bedingungen', []):
                if bedingung.get('typ') == 'sonstiges':
                    unknown['bedingungen'].append(bedingung.get('bemerkung', '')[:100])
        
        # Remove duplicates
        for key in unknown:
            unknown[key] = list(set(unknown[key]))[:10]  # Limit to 10 examples
        
        return unknown
    
    def calculate_enum_usage(self, rules: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
        """Calculate usage statistics for enum values."""
        usage = {
            'aktivitaet': {},
            'ort': {},
            'erlaubnis': {},
            'bedingung_typ': {}
        }
        
        for rule in rules:
            # Count aktivitaet
            if rule.get('aktivitaet'):
                aktivitaet = rule['aktivitaet']
                usage['aktivitaet'][aktivitaet] = usage['aktivitaet'].get(aktivitaet, 0) + 1
            
            # Count ort
            if rule.get('ort'):
                ort = rule['ort']
                usage['ort'][ort] = usage['ort'].get(ort, 0) + 1
            
            # Count erlaubnis
            if rule.get('erlaubnis'):
                erlaubnis = rule['erlaubnis']
                usage['erlaubnis'][erlaubnis] = usage['erlaubnis'].get(erlaubnis, 0) + 1
            
            # Count bedingung types
            for bedingung in rule.get('bedingungen', []):
                typ = bedingung.get('typ')
                if typ:
                    usage['bedingung_typ'][typ] = usage['bedingung_typ'].get(typ, 0) + 1
        
        return usage