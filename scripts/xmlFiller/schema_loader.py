"""
Schema loader module for NSG PDF to XML/JSON converter.
Handles loading and managing the NSG v1.3 schema and enum mappings.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from utils import normalize_for_comparison, handle_errors

logger = logging.getLogger('nsg_converter.schema_loader')


class SchemaLoader:
    """Load and manage NSG schema and enum mappings."""
    
    def __init__(self, schema_path: str, synonyms_path: Optional[str] = None):
        """
        Initialize schema loader.
        
        Args:
            schema_path: Path to NSG schema JSON file
            synonyms_path: Optional path to synonyms mapping file
        """
        self.schema_path = Path(schema_path)
        self.synonyms_path = Path(synonyms_path) if synonyms_path else None
        
        self.schema = {}
        self.enums = {}
        self.enum_lookup = {}  # Normalized text -> (enum_type, enum_value)
        self.synonyms = {}
        
        self._load_schema()
        if self.synonyms_path:
            self._load_synonyms()
        self._build_lookup_tables()
    
    @handle_errors({})
    def _load_schema(self):
        """Load the NSG schema from JSON file."""
        if not self.schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {self.schema_path}")
        
        with open(self.schema_path, 'r', encoding='utf-8') as f:
            self.schema = json.load(f)
        
        # Extract enums from schema
        if 'enums' in self.schema:
            for enum_def in self.schema['enums']:
                enum_name = enum_def['name']
                enum_items = enum_def.get('items', [])
                self.enums[enum_name] = enum_items
                logger.debug(f"Loaded enum {enum_name} with {len(enum_items)} items")
        
        logger.info(f"Loaded schema with {len(self.enums)} enum types")
    
    @handle_errors({})
    def _load_synonyms(self):
        """Load synonym mappings from JSON file."""
        if not self.synonyms_path.exists():
            logger.warning(f"Synonyms file not found: {self.synonyms_path}")
            return
        
        with open(self.synonyms_path, 'r', encoding='utf-8') as f:
            self.synonyms = json.load(f)
        
        logger.info(f"Loaded {len(self.synonyms)} synonym mappings")
    
    def _build_lookup_tables(self):
        """Build normalized lookup tables for enum matching."""
        # Build enum lookup table
        for enum_type, items in self.enums.items():
            for item in items:
                # Store original value
                normalized = normalize_for_comparison(item)
                self.enum_lookup[normalized] = (enum_type, item)
                
                # Also store with underscores replaced
                normalized_no_underscore = normalized.replace('_', ' ')
                if normalized_no_underscore != normalized:
                    self.enum_lookup[normalized_no_underscore] = (enum_type, item)
        
        # Add synonyms to lookup
        for text, mapping in self.synonyms.items():
            normalized = normalize_for_comparison(text)
            if isinstance(mapping, dict):
                enum_type = mapping.get('enum_type')
                enum_value = mapping.get('enum_value')
                if enum_type and enum_value:
                    self.enum_lookup[normalized] = (enum_type, enum_value)
            elif isinstance(mapping, str):
                # Try to find the enum value in our enums
                for enum_type, items in self.enums.items():
                    if mapping in items:
                        self.enum_lookup[normalized] = (enum_type, mapping)
                        break
        
        logger.debug(f"Built lookup table with {len(self.enum_lookup)} entries")
    
    def find_enum_value(self, text: str, enum_type: Optional[str] = None) -> Optional[str]:
        """
        Find enum value for given text.
        
        Args:
            text: Text to search for
            enum_type: Optional enum type to restrict search
        
        Returns:
            Enum value if found, None otherwise
        """
        if not text:
            return None
        
        normalized = normalize_for_comparison(text)
        
        # Check direct lookup
        if normalized in self.enum_lookup:
            found_type, found_value = self.enum_lookup[normalized]
            if enum_type is None or found_type == enum_type:
                return found_value
        
        # Try partial matching for longer texts
        words = normalized.split()
        for i in range(len(words)):
            for j in range(i + 1, len(words) + 1):
                phrase = ' '.join(words[i:j])
                if phrase in self.enum_lookup:
                    found_type, found_value = self.enum_lookup[phrase]
                    if enum_type is None or found_type == enum_type:
                        return found_value
        
        return None
    
    def find_aktivitaet(self, text: str) -> Optional[str]:
        """Find aktivitaet enum value in text."""
        return self.find_enum_value(text, 'aktivitaet_enum')
    
    def find_ort(self, text: str) -> Optional[str]:
        """Find ort enum value in text."""
        return self.find_enum_value(text, 'ort_enum')
    
    def find_erlaubnis(self, text: str) -> Optional[str]:
        """Find erlaubnis enum value in text."""
        return self.find_enum_value(text, 'erlaubnis_enum')
    
    def find_zone_typ(self, text: str) -> Optional[str]:
        """Find zone_typ enum value in text."""
        return self.find_enum_value(text, 'zone_typ_enum')
    
    def find_bedingung_typ(self, text: str) -> Optional[str]:
        """Find bedingung_typ enum value in text."""
        return self.find_enum_value(text, 'bedingung_typ_enum')
    
    def find_jahreszeit(self, text: str) -> Optional[str]:
        """Find jahreszeit enum value in text."""
        return self.find_enum_value(text, 'jahreszeit_enum')
    
    def find_tageszeit(self, text: str) -> Optional[str]:
        """Find tageszeit enum value in text."""
        return self.find_enum_value(text, 'tageszeit_enum')
    
    def find_wetterbedingung(self, text: str) -> Optional[str]:
        """Find wetterbedingung enum value in text."""
        return self.find_enum_value(text, 'wetterbedingung_enum')
    
    def find_all_aktivitaeten(self, text: str) -> List[str]:
        """Find all aktivitaet enum values in text."""
        found = []
        for item in self.enums.get('aktivitaet_enum', []):
            if self._text_contains_enum(text, item):
                found.append(item)
        return found
    
    def find_all_orte(self, text: str) -> List[str]:
        """Find all ort enum values in text."""
        found = []
        for item in self.enums.get('ort_enum', []):
            if self._text_contains_enum(text, item):
                found.append(item)
        return found
    
    def _text_contains_enum(self, text: str, enum_value: str) -> bool:
        """Check if text contains an enum value."""
        normalized_text = normalize_for_comparison(text)
        normalized_enum = normalize_for_comparison(enum_value)
        
        # Check for exact word match
        words = normalized_text.split()
        enum_words = normalized_enum.split()
        
        # For single-word enums, check word boundaries
        if len(enum_words) == 1:
            return normalized_enum in words
        
        # For multi-word enums, check if all words appear in sequence
        for i in range(len(words) - len(enum_words) + 1):
            if words[i:i+len(enum_words)] == enum_words:
                return True
        
        return False
    
    def get_enum_items(self, enum_type: str) -> List[str]:
        """Get all items for a specific enum type."""
        return self.enums.get(enum_type, [])
    
    def validate_enum_value(self, enum_type: str, value: str) -> bool:
        """Validate if a value belongs to a specific enum type."""
        return value in self.enums.get(enum_type, [])
    
    def get_tables(self) -> List[Dict[str, Any]]:
        """Get table definitions from schema."""
        return self.schema.get('tables', [])
    
    def get_table_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """Get column definitions for a specific table."""
        for table in self.get_tables():
            if table.get('name') == table_name:
                return table.get('columns', [])
        return []
    
    def get_relationships(self) -> List[Dict[str, Any]]:
        """Get relationship definitions from schema."""
        return self.schema.get('refs', [])
    
    def map_to_enum_or_unsicher(self, text: str, enum_type: str, 
                                 note: Optional[str] = None) -> Dict[str, Any]:
        """
        Map text to enum value or mark as unsicher with note.
        
        Args:
            text: Text to map
            enum_type: Target enum type
            note: Optional note for unsicher values
        
        Returns:
            Dict with 'value' and optional 'unsicher' and 'note' fields
        """
        enum_value = self.find_enum_value(text, enum_type)
        
        if enum_value:
            return {'value': enum_value}
        else:
            result = {
                'value': 'sonstiges' if 'sonstiges' in self.get_enum_items(enum_type) else None,
                'unsicher': True
            }
            if note or text:
                result['note'] = note or f"Original: {text}"
            return result
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about loaded schema and enums."""
        stats = {
            'total_enums': len(self.enums),
            'total_enum_values': sum(len(items) for items in self.enums.values()),
            'total_synonyms': len(self.synonyms),
            'enum_types': {}
        }
        
        for enum_type, items in self.enums.items():
            stats['enum_types'][enum_type] = len(items)
        
        return stats