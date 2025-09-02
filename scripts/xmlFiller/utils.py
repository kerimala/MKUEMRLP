"""
Shared utilities for NSG PDF to XML/JSON converter.
"""

import logging
import re
import unicodedata
from datetime import datetime
from functools import wraps
from typing import Optional, Dict, Any, List
import sys

# Configure logging
def setup_logging(verbose: bool = False):
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO
    format_str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger('nsg_converter')

# Text normalization utilities
def remove_umlauts(text: str) -> str:
    """Convert German umlauts to their base forms."""
    replacements = {
        'ä': 'ae', 'Ä': 'Ae',
        'ö': 'oe', 'Ö': 'Oe',
        'ü': 'ue', 'Ü': 'Ue',
        'ß': 'ss'
    }
    for umlaut, replacement in replacements.items():
        text = text.replace(umlaut, replacement)
    return text

def normalize_for_comparison(text: str) -> str:
    """Normalize text for case/umlaut-insensitive comparison."""
    if not text:
        return ""
    
    # Remove umlauts
    text = remove_umlauts(text)
    
    # Convert to lowercase
    text = text.lower()
    
    # Remove accents
    text = ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')
    
    # Replace multiple spaces with single space
    text = re.sub(r'\s+', ' ', text)
    
    # Remove leading/trailing whitespace
    text = text.strip()
    
    # Replace hyphens and underscores with spaces
    text = text.replace('-', ' ').replace('_', ' ')
    
    return text

def normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text."""
    if not text:
        return ""
    
    # Replace various whitespace characters with regular space
    text = re.sub(r'[\t\r\n\f\v]+', ' ', text)
    
    # Replace multiple spaces with single space
    text = re.sub(r' +', ' ', text)
    
    # Remove leading/trailing whitespace
    return text.strip()

# Date/Time parsing utilities
def parse_german_date(date_str: str) -> Optional[datetime]:
    """Parse German date format (dd.mm.yyyy)."""
    patterns = [
        r'(\d{1,2})\.(\d{1,2})\.(\d{4})',  # dd.mm.yyyy
        r'(\d{1,2})\. (\d{1,2})\. (\d{4})',  # dd. mm. yyyy
        r'(\d{1,2})\.(\d{1,2})\.(\d{2})',  # dd.mm.yy
    ]
    
    for pattern in patterns:
        match = re.search(pattern, date_str)
        if match:
            day, month, year = match.groups()
            if len(year) == 2:
                year = '20' + year if int(year) < 50 else '19' + year
            try:
                return datetime(int(year), int(month), int(day))
            except ValueError:
                continue
    return None

def parse_time(time_str: str) -> Optional[str]:
    """Parse time string to HH:MM format."""
    patterns = [
        r'(\d{1,2}):(\d{2})',  # HH:MM
        r'(\d{1,2})\.(\d{2})',  # HH.MM
        r'(\d{1,2}) ?[Uu]hr',  # HH Uhr
    ]
    
    for pattern in patterns:
        match = re.search(pattern, time_str)
        if match:
            if len(match.groups()) == 1:
                hour = match.group(1)
                return f"{int(hour):02d}:00"
            else:
                hour, minute = match.groups()[:2]
                return f"{int(hour):02d}:{int(minute):02d}"
    return None

# Regex pattern constants
class Patterns:
    """Common regex patterns used throughout the application."""
    
    # Paragraph detection
    PARAGRAPH = re.compile(r'^§\s*(\d+[a-z]?)', re.MULTILINE)
    
    # Distance patterns
    DISTANCE = re.compile(
        r'(uferstreifen|schutzstreifen|abstand|entfernung)'
        r'.*?(\d+(?:[\.,]\d+)?)\s*(m|meter|km|kilometer)',
        re.IGNORECASE
    )
    
    # Quantity patterns
    QUANTITY = re.compile(
        r'(\d+(?:[\.,]\d+)?)\s*'
        r'(kW|PS|km/h|kmh|Personen|Person|kg|t|ha|m²|m2|Stück|Stuck)',
        re.IGNORECASE
    )
    
    # Date range pattern
    DATE_RANGE = re.compile(
        r'(\d{1,2}\.\d{1,2}\.(?:\d{2}|\d{4}))'
        r'\s*(?:bis|-)\s*'
        r'(\d{1,2}\.\d{1,2}\.(?:\d{2}|\d{4}))'
    )
    
    # Time range pattern
    TIME_RANGE = re.compile(
        r'(\d{1,2}(?::\d{2})?)\s*(?:bis|-|–)\s*(\d{1,2}(?::\d{2})?)\s*[Uu]hr'
    )
    
    # Season patterns
    SEASONS = {
        'fruehling': re.compile(r'\b(frühjahr|frühling|frühjahrs)\b', re.IGNORECASE),
        'sommer': re.compile(r'\b(sommer|sommers)\b', re.IGNORECASE),
        'herbst': re.compile(r'\b(herbst|herbsts)\b', re.IGNORECASE),
        'winter': re.compile(r'\b(winter|winters)\b', re.IGNORECASE),
    }
    
    # Holiday patterns
    HOLIDAYS = {
        'ostern': re.compile(r'\b(ostern|oster[a-z]*)\b', re.IGNORECASE),
        'pfingsten': re.compile(r'\b(pfingsten|pfingst[a-z]*)\b', re.IGNORECASE),
        'weihnachten': re.compile(r'\b(weihnachten|weihnachts[a-z]*)\b', re.IGNORECASE),
        'neujahr': re.compile(r'\b(neujahr|neujahrs[a-z]*)\b', re.IGNORECASE),
    }
    
    # Weather patterns
    WEATHER = {
        'schnee': re.compile(r'\b(schnee|verschneit|schneebedeckt)\b', re.IGNORECASE),
        'eis': re.compile(r'\b(eis|vereist|gefroren)\b', re.IGNORECASE),
        'regen': re.compile(r'\b(regen|regnet|regnerisch)\b', re.IGNORECASE),
        'naesse': re.compile(r'\b(nässe|nass|feucht)\b', re.IGNORECASE),
    }

# Error handling decorators
def handle_errors(default_return=None):
    """Decorator to handle errors gracefully."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger = logging.getLogger('nsg_converter')
                logger.error(f"Error in {func.__name__}: {str(e)}")
                return default_return
        return wrapper
    return decorator

# Helper functions
def clean_number(text: str) -> Optional[float]:
    """Extract and clean a number from text."""
    if not text:
        return None
    
    # Replace comma with dot for decimal
    text = text.replace(',', '.')
    
    # Extract number
    match = re.search(r'\d+(?:\.\d+)?', text)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None

def extract_comparison_operator(text: str) -> str:
    """Extract comparison operator from text."""
    if any(word in text.lower() for word in ['mindestens', 'min.', 'minimum', 'ab']):
        return '>='
    elif any(word in text.lower() for word in ['höchstens', 'max.', 'maximum', 'bis']):
        return '<='
    elif any(word in text.lower() for word in ['genau', 'exakt']):
        return '='
    elif any(word in text.lower() for word in ['unter', 'weniger']):
        return '<'
    elif any(word in text.lower() for word in ['über', 'mehr']):
        return '>'
    elif any(word in text.lower() for word in ['zwischen', 'von']):
        return 'between'
    else:
        return '>='  # Default to "at least"

def split_paragraphs(text: str) -> List[Dict[str, Any]]:
    """Split text into paragraphs based on § markers."""
    paragraphs = []
    
    # Find all paragraph markers
    for match in Patterns.PARAGRAPH.finditer(text):
        start = match.start()
        nummer = match.group(1)
        
        # Find the end of this paragraph (start of next § or end of text)
        next_match = Patterns.PARAGRAPH.search(text, match.end())
        end = next_match.start() if next_match else len(text)
        
        # Extract paragraph text
        content = text[start:end].strip()
        
        paragraphs.append({
            'nummer': nummer,
            'content': content,
            'start_pos': start,
            'end_pos': end
        })
    
    return paragraphs

def is_relevant_paragraph(content: str) -> bool:
    """Check if a paragraph contains relevant rules."""
    relevant_keywords = [
        'verboten', 'untersagt', 'nicht gestattet',
        'erlaubt', 'gestattet', 'zulässig',
        'ausnahme', 'befreiung', 'genehmigung',
        'ordnungswidrigkeit', 'owi', 'bußgeld'
    ]
    
    content_lower = content.lower()
    return any(keyword in content_lower for keyword in relevant_keywords)

def determine_rubrum(content: str) -> Optional[str]:
    """Determine the section type (rubrum) from paragraph content."""
    content_lower = content.lower()
    
    if any(word in content_lower for word in ['verboten', 'untersagt', 'nicht gestattet']):
        return 'Verbote'
    elif any(word in content_lower for word in ['erlaubt', 'gestattet', 'zulässig']):
        return 'Erlaubnisse'
    elif any(word in content_lower for word in ['ausnahme', 'befreiung']):
        return 'Ausnahmen'
    elif any(word in content_lower for word in ['ordnungswidrigkeit', 'owi', 'bußgeld']):
        return 'OWi'
    else:
        return None

def merge_dict_values(dict1: Dict, dict2: Dict) -> Dict:
    """Merge two dictionaries, combining list values."""
    result = dict1.copy()
    
    for key, value in dict2.items():
        if key in result:
            if isinstance(result[key], list) and isinstance(value, list):
                # Merge lists, avoiding duplicates
                for item in value:
                    if item not in result[key]:
                        result[key].append(item)
            elif isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge dicts
                result[key] = merge_dict_values(result[key], value)
            else:
                # Override with new value
                result[key] = value
        else:
            result[key] = value
    
    return result