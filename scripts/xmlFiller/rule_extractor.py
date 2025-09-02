"""
Rule extraction module for NSG PDF to XML/JSON converter.
Extracts structured rules, activities, conditions from processed text.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from utils import (
    Patterns, parse_german_date, parse_time, clean_number,
    extract_comparison_operator, merge_dict_values
)
from schema_loader import SchemaLoader

logger = logging.getLogger('nsg_converter.rule_extractor')


class RuleExtractor:
    """Extract structured rules from processed paragraphs."""
    
    def __init__(self, schema_loader: SchemaLoader):
        """
        Initialize rule extractor.
        
        Args:
            schema_loader: Schema loader instance
        """
        self.schema = schema_loader
        
    def extract_rules(self, processed: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract rules from processed text.
        
        Args:
            processed: Result from TextProcessor
        
        Returns:
            List of extracted rules
        """
        paragraphs = processed.get('paragraphs', [])
        document_metadata = processed.get('metadata', {})
        
        all_rules = []
        
        for para in paragraphs:
            if not para.get('is_relevant', False):
                continue
            
            # Extract rules from this paragraph
            para_rules = self.extract_paragraph_rules(para)
            
            # Add paragraph reference to each rule
            for rule in para_rules:
                rule['paragraf_nummer'] = para['nummer']
                rule['paragraf_rubrum'] = para.get('rubrum')
                rule['document_metadata'] = document_metadata
            
            all_rules.extend(para_rules)
        
        # Merge and deduplicate rules
        merged_rules = self.merge_duplicate_rules(all_rules)
        
        logger.info(f"Extracted {len(merged_rules)} unique rules")
        return merged_rules
    
    def extract_paragraph_rules(self, paragraph: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract rules from a single paragraph.
        
        Args:
            paragraph: Paragraph data
        
        Returns:
            List of rules
        """
        content = paragraph['content']
        rules = []
        
        # Split content into sentences for better processing
        sentences = self.split_into_sentences(content)
        
        for sentence in sentences:
            # Extract base rule components
            aktivitaeten = self.extract_aktivitaeten(sentence)
            orte = self.extract_orte(sentence)
            erlaubnis = self.extract_erlaubnis(sentence)
            
            # If we found basic components, extract conditions
            if aktivitaeten or orte or erlaubnis:
                bedingungen = self.extract_bedingungen(sentence)
                zone = self.extract_zone(sentence)
                
                # Create rule for each combination
                for aktivitaet in (aktivitaeten or [None]):
                    for ort in (orte or [None]):
                        rule = {
                            'aktivitaet': aktivitaet,
                            'ort': ort,
                            'erlaubnis': erlaubnis,
                            'bedingungen': bedingungen,
                            'zone': zone,
                            'original_text': sentence
                        }
                        
                        # Only add if we have meaningful content
                        if aktivitaet or ort or bedingungen:
                            rules.append(rule)
        
        return rules
    
    def split_into_sentences(self, text: str) -> List[str]:
        """Split text into sentences for processing."""
        # Simple sentence splitting (can be improved)
        sentences = re.split(r'[.;]\s+(?=[A-ZÄÖÜ])', text)
        
        # Also split on numbered lists
        numbered_pattern = r'\n\s*\d+\.?\s+'
        result = []
        for sentence in sentences:
            parts = re.split(numbered_pattern, sentence)
            result.extend([p.strip() for p in parts if p.strip()])
        
        return result
    
    def extract_aktivitaeten(self, text: str) -> List[str]:
        """Extract activities from text."""
        found = []
        
        # Try to find all activities mentioned
        all_aktivitaeten = self.schema.find_all_aktivitaeten(text)
        
        # If none found, try common patterns
        if not all_aktivitaeten:
            activity_patterns = [
                r'\b(betreten|befahren|reiten|zelten|lagern|angeln|baden)\b',
                r'\b(fahren|parken|campen|biwakieren|fotografieren)\b',
                r'\b(sammeln|pflücken|fangen|jagen|fischen)\b',
            ]
            
            for pattern in activity_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    activity_text = match.group(1)
                    enum_value = self.schema.find_aktivitaet(activity_text)
                    if enum_value:
                        found.append(enum_value)
        else:
            found = all_aktivitaeten
        
        return list(set(found))  # Remove duplicates
    
    def extract_orte(self, text: str) -> List[str]:
        """Extract locations from text."""
        found = []
        
        # Try to find all locations mentioned
        all_orte = self.schema.find_all_orte(text)
        
        # If none found, try common patterns
        if not all_orte:
            location_patterns = [
                r'\b(wege?n?|pfade?n?|straßen?|plätze?n?)\b',
                r'\b(ufer(?:bereich)?|gewässer|seen?|flüsse?n?)\b',
                r'\b(wald|wiesen?|äcker?n?|felder?n?)\b',
                r'\b(gesamte[ns]?\s+(?:fläche|gebiet))\b',
            ]
            
            for pattern in location_patterns:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    location_text = match.group(0)
                    enum_value = self.schema.find_ort(location_text)
                    if enum_value:
                        found.append(enum_value)
        else:
            found = all_orte
        
        return list(set(found))  # Remove duplicates
    
    def extract_erlaubnis(self, text: str) -> Optional[str]:
        """Extract permission status from text."""
        text_lower = text.lower()
        
        # Check for explicit permission keywords
        if any(word in text_lower for word in ['verboten', 'untersagt', 'nicht gestattet', 'unzulässig']):
            return 'verboten'
        elif 'nur mit' in text_lower and 'erlaubnis' in text_lower:
            if 'behörd' in text_lower:
                return 'nur_mit_behoerdlicher_erlaubnis_erlaubt'
            elif 'grundbesitzer' in text_lower or 'eigentümer' in text_lower:
                return 'nur_mit_grundbesitzererlaubnis_erlaubt'
        elif any(word in text_lower for word in ['erlaubt', 'gestattet', 'zulässig']) and 'nicht' not in text_lower:
            return 'erlaubt'
        elif 'nicht empfohlen' in text_lower:
            return 'nicht_empfohlen'
        
        # Try schema lookup
        return self.schema.find_erlaubnis(text)
    
    def extract_bedingungen(self, text: str) -> List[Dict[str, Any]]:
        """Extract all conditions from text."""
        bedingungen = []
        
        # Extract different types of conditions
        bedingungen.extend(self.extract_distance_conditions(text))
        bedingungen.extend(self.extract_temporal_conditions(text))
        bedingungen.extend(self.extract_quantity_conditions(text))
        bedingungen.extend(self.extract_weather_conditions(text))
        bedingungen.extend(self.extract_zone_conditions(text))
        
        # Extract any remaining unmapped conditions
        unmapped = self.extract_unmapped_conditions(text, bedingungen)
        if unmapped:
            bedingungen.append(unmapped)
        
        return bedingungen
    
    def extract_distance_conditions(self, text: str) -> List[Dict[str, Any]]:
        """Extract distance/spacing conditions."""
        conditions = []
        
        for match in Patterns.DISTANCE.finditer(text):
            condition_type = match.group(1).lower()
            value = clean_number(match.group(2))
            unit = match.group(3).lower()
            
            if value:
                condition = {
                    'typ': 'abstand_m',
                    'vergleich': extract_comparison_operator(text[:match.start()]),
                    'value_num': value,
                    'einheit': 'm' if 'km' not in unit else 'km'
                }
                
                # Check for "beidseits" or similar
                if 'beidseits' in text.lower() or 'beiderseits' in text.lower():
                    condition['bezugsflaeche'] = 'beidseits'
                
                # Add specific reference if mentioned
                if 'ufer' in condition_type:
                    condition['bezug'] = 'uferbereich'
                elif 'schutz' in condition_type:
                    condition['bezug'] = 'schutzstreifen'
                
                conditions.append(condition)
        
        return conditions
    
    def extract_temporal_conditions(self, text: str) -> List[Dict[str, Any]]:
        """Extract time-based conditions."""
        conditions = []
        
        # Date ranges
        for match in Patterns.DATE_RANGE.finditer(text):
            date_from = parse_german_date(match.group(1))
            date_to = parse_german_date(match.group(2))
            
            if date_from and date_to:
                conditions.append({
                    'typ': 'datumspanne',
                    'date_from': date_from.strftime('%Y-%m-%d'),
                    'date_to': date_to.strftime('%Y-%m-%d')
                })
        
        # Time ranges
        for match in Patterns.TIME_RANGE.finditer(text):
            time_from = parse_time(match.group(1))
            time_to = parse_time(match.group(2))
            
            if time_from and time_to:
                conditions.append({
                    'typ': 'tageszeit',
                    'time_from': time_from,
                    'time_to': time_to
                })
        
        # Seasons
        for season_key, pattern in Patterns.SEASONS.items():
            if pattern.search(text):
                conditions.append({
                    'typ': 'jahreszeit',
                    'value': season_key
                })
        
        # Holidays
        for holiday_key, pattern in Patterns.HOLIDAYS.items():
            if pattern.search(text):
                conditions.append({
                    'typ': 'feiertag_event',
                    'event_name': holiday_key
                })
        
        # Weekdays
        weekday_pattern = r'\b(montags?|dienstags?|mittwochs?|donnerstags?|freitags?|samstags?|sonntags?)\b'
        for match in re.finditer(weekday_pattern, text, re.IGNORECASE):
            weekday = match.group(1).lower()
            conditions.append({
                'typ': 'wochentag',
                'value': weekday.rstrip('s')  # Remove plural 's'
            })
        
        return conditions
    
    def extract_quantity_conditions(self, text: str) -> List[Dict[str, Any]]:
        """Extract quantity-based conditions."""
        conditions = []
        
        for match in Patterns.QUANTITY.finditer(text):
            value = clean_number(match.group(1))
            unit = match.group(2).lower()
            
            if value:
                condition = {
                    'vergleich': extract_comparison_operator(text[:match.start()]),
                    'value_num': value
                }
                
                # Map to specific condition type based on unit
                if 'kw' in unit:
                    condition['typ'] = 'motor_leistung_kw'
                    condition['einheit'] = 'kw'
                elif 'ps' in unit:
                    # Convert PS to kW
                    condition['typ'] = 'motor_leistung_kw'
                    condition['value_num'] = value * 0.7355
                    condition['einheit'] = 'kw'
                    condition['note'] = f"Converted from {value} PS"
                elif 'km/h' in unit or 'kmh' in unit:
                    condition['typ'] = 'geschwindigkeit'
                    condition['einheit'] = 'km_h'
                elif 'person' in unit:
                    condition['typ'] = 'personen_max'
                    condition['einheit'] = 'personen'
                elif 'kg/ha' in unit:
                    condition['typ'] = 'menge_limit'
                    condition['einheit'] = 'kg_ha'
                    # Try to identify substance
                    condition['stoff'] = self.identify_substance(text[:match.start()])
                elif 'kg' in unit or 't' in unit:
                    condition['typ'] = 'menge_limit'
                    condition['einheit'] = 'kg' if 'kg' in unit else 't'
                elif 'm²' in unit or 'm2' in unit:
                    condition['typ'] = 'menge_limit'
                    condition['einheit'] = 'm2'
                elif 'ha' in unit:
                    condition['typ'] = 'menge_limit'
                    condition['einheit'] = 'ha'
                else:
                    condition['typ'] = 'sonstiges'
                    condition['einheit'] = unit
                
                conditions.append(condition)
        
        return conditions
    
    def extract_weather_conditions(self, text: str) -> List[Dict[str, Any]]:
        """Extract weather-based conditions."""
        conditions = []
        
        for weather_key, pattern in Patterns.WEATHER.items():
            if pattern.search(text):
                conditions.append({
                    'typ': 'wetter',
                    'value': weather_key
                })
        
        return conditions
    
    def extract_zone_conditions(self, text: str) -> List[Dict[str, Any]]:
        """Extract zone-related conditions."""
        conditions = []
        
        # Check for zone references
        zone_patterns = [
            r'\b(zone\s+[IVX]+|\d+)\b',
            r'\b(kern|puffer|rand)zone\b',
            r'\b(schutzstreifen|uferstreifen)\b',
            r'\b(teilgebiet|teilfläche)\s+([A-Z\d]+)\b',
        ]
        
        for pattern in zone_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                zone_ref = match.group(0)
                conditions.append({
                    'typ': 'zonenbezug',
                    'zone': zone_ref,
                    'note': f"Zone reference: {zone_ref}"
                })
        
        return conditions
    
    def extract_zone(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract zone information."""
        zone_type = self.schema.find_zone_typ(text)
        
        if zone_type:
            return {
                'typ': zone_type
            }
        
        # Try to extract zone name/id
        zone_pattern = r'Zone\s+([IVX]+|\d+|[A-Z])'
        match = re.search(zone_pattern, text, re.IGNORECASE)
        if match:
            return {
                'typ': 'sonstiges',
                'name': match.group(1)
            }
        
        return None
    
    def extract_unmapped_conditions(self, text: str, 
                                   existing_conditions: List[Dict]) -> Optional[Dict[str, Any]]:
        """Extract any conditions that couldn't be mapped to specific types."""
        # Check if there are condition keywords that weren't captured
        condition_keywords = [
            'sofern', 'soweit', 'wenn', 'falls',
            'voraussetzung', 'bedingung', 'unter der',
            'mit ausnahme', 'außer', 'ausgenommen'
        ]
        
        text_lower = text.lower()
        for keyword in condition_keywords:
            if keyword in text_lower:
                # Extract the condition text after the keyword
                pattern = rf'{keyword}\s+(.+?)(?:[,;.]|$)'
                match = re.search(pattern, text_lower)
                if match:
                    condition_text = match.group(1).strip()
                    # Check if this isn't already captured
                    if not self._condition_already_captured(condition_text, existing_conditions):
                        return {
                            'typ': 'sonstiges',
                            'bemerkung': condition_text
                        }
        
        return None
    
    def _condition_already_captured(self, text: str, conditions: List[Dict]) -> bool:
        """Check if a condition text is already captured."""
        for condition in conditions:
            if 'bemerkung' in condition and text in condition['bemerkung']:
                return True
            if 'note' in condition and text in condition['note']:
                return True
        return False
    
    def identify_substance(self, text: str) -> Optional[str]:
        """Identify substance mentioned in text."""
        substances = {
            'stickstoff': ['stickstoff', 'n-dünger', 'nitrat'],
            'phosphat': ['phosphat', 'phosphor', 'p-dünger'],
            'kalium': ['kalium', 'kali', 'k-dünger'],
            'duenger_allgemein': ['dünger', 'düngung', 'düngemittel'],
            'pestizid_biozid': ['pestizid', 'biozid', 'pflanzenschutz', 'herbizid', 'insektizid']
        }
        
        text_lower = text.lower()
        for substance_key, keywords in substances.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return substance_key
        
        return None
    
    def merge_duplicate_rules(self, rules: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Merge duplicate rules with same base components."""
        merged = {}
        
        for rule in rules:
            # Create key from base components
            key = (
                rule.get('aktivitaet'),
                rule.get('ort'),
                rule.get('erlaubnis'),
                rule.get('zone', {}).get('typ') if rule.get('zone') else None
            )
            
            if key in merged:
                # Merge conditions
                existing = merged[key]
                existing_conditions = existing.get('bedingungen', [])
                new_conditions = rule.get('bedingungen', [])
                
                # Add new conditions that don't exist
                for new_cond in new_conditions:
                    if not self._condition_exists(new_cond, existing_conditions):
                        existing_conditions.append(new_cond)
                
                existing['bedingungen'] = existing_conditions
            else:
                merged[key] = rule
        
        # Convert back to list and sort
        result = list(merged.values())
        result.sort(key=lambda x: (
            x.get('paragraf_nummer', ''),
            x.get('aktivitaet', ''),
            x.get('ort', '')
        ))
        
        return result
    
    def _condition_exists(self, condition: Dict, conditions: List[Dict]) -> bool:
        """Check if a condition already exists in the list."""
        for existing in conditions:
            if (existing.get('typ') == condition.get('typ') and
                existing.get('value') == condition.get('value') and
                existing.get('value_num') == condition.get('value_num')):
                return True
        return False