"""
Text processing module for NSG PDF to XML/JSON converter.
Handles text normalization, cleaning, and paragraph segmentation.
"""

import re
import logging
from collections import Counter
from typing import List, Dict, Any, Optional, Tuple
from utils import normalize_whitespace, split_paragraphs, determine_rubrum

logger = logging.getLogger('nsg_converter.text_processor')


class TextProcessor:
    """Process and clean extracted PDF text."""
    
    def __init__(self):
        """Initialize text processor."""
        self.header_patterns = []
        self.footer_patterns = []
        
    def process_text(self, extracted: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process extracted PDF text.
        
        Args:
            extracted: Result from PDFExtractor
        
        Returns:
            Processed text with paragraphs and metadata
        """
        # Get raw text
        text = extracted.get('text', '')
        pages = extracted.get('pages', [])
        
        # Clean and normalize
        text = self.remove_headers_footers(text, pages)
        text = self.dehyphenate(text)
        text = self.normalize_text(text)
        
        # Segment into paragraphs
        paragraphs = self.segment_paragraphs(text)
        
        # Enhance paragraph metadata
        paragraphs = self.enhance_paragraphs(paragraphs)
        
        return {
            'original_text': extracted.get('text', ''),
            'cleaned_text': text,
            'paragraphs': paragraphs,
            'metadata': extracted.get('metadata', {})
        }
    
    def remove_headers_footers(self, text: str, pages: List[Dict]) -> str:
        """
        Remove repeating headers and footers.
        
        Args:
            text: Full text
            pages: List of page data
        
        Returns:
            Text with headers/footers removed
        """
        if len(pages) < 3:
            return text
        
        # Collect lines from each page
        page_lines = []
        for page in pages:
            page_text = page.get('text', '')
            lines = page_text.split('\n')
            page_lines.append(lines)
        
        # Find repeating lines at top (headers)
        header_candidates = Counter()
        for lines in page_lines:
            if lines:
                # Check first 3 lines
                for line in lines[:3]:
                    line = line.strip()
                    if line and len(line) > 5:
                        header_candidates[line] += 1
        
        # Find repeating lines at bottom (footers)
        footer_candidates = Counter()
        for lines in page_lines:
            if lines:
                # Check last 3 lines
                for line in lines[-3:]:
                    line = line.strip()
                    if line and len(line) > 5:
                        footer_candidates[line] += 1
        
        # Identify headers/footers (appear on >50% of pages)
        threshold = len(pages) * 0.5
        headers = [line for line, count in header_candidates.items() if count > threshold]
        footers = [line for line, count in footer_candidates.items() if count > threshold]
        
        # Remove headers and footers
        cleaned_lines = []
        for line in text.split('\n'):
            line_stripped = line.strip()
            if line_stripped not in headers and line_stripped not in footers:
                # Also filter out page numbers (common patterns)
                if not self._is_page_number(line_stripped):
                    cleaned_lines.append(line)
        
        logger.debug(f"Removed {len(headers)} headers and {len(footers)} footers")
        return '\n'.join(cleaned_lines)
    
    def _is_page_number(self, line: str) -> bool:
        """Check if a line is likely a page number."""
        line = line.strip()
        
        # Common page number patterns
        patterns = [
            r'^-?\s*\d{1,4}\s*-?$',  # Just a number, possibly with dashes
            r'^Seite\s+\d+$',  # "Seite N"
            r'^Page\s+\d+$',  # "Page N"
            r'^\d+\s*/\s*\d+$',  # "N/M"
            r'^-\s*\d+\s*von\s*\d+\s*-$',  # "- N von M -"
        ]
        
        for pattern in patterns:
            if re.match(pattern, line, re.IGNORECASE):
                return True
        
        return False
    
    def dehyphenate(self, text: str) -> str:
        """
        Join hyphenated words at line breaks.
        
        Args:
            text: Text with hyphenation
        
        Returns:
            Dehyphenated text
        """
        # Pattern for hyphenation at line break
        # Word-hyphen at end of line followed by lowercase letter at start of next
        pattern = r'(\w+)-\n([a-zäöüß])'
        
        # Replace with joined word
        text = re.sub(pattern, r'\1\2', text)
        
        # Also handle cases with extra spaces
        pattern2 = r'(\w+)-\s*\n\s*([a-zäöüß])'
        text = re.sub(pattern2, r'\1\2', text)
        
        return text
    
    def normalize_text(self, text: str) -> str:
        """
        Normalize text for processing.
        
        Args:
            text: Raw text
        
        Returns:
            Normalized text
        """
        # Normalize whitespace
        text = normalize_whitespace(text)
        
        # Fix common OCR errors
        text = self.fix_common_ocr_errors(text)
        
        # Normalize quotes
        text = re.sub(r'[""„"‚'']', '"', text)
        
        # Normalize dashes
        text = re.sub(r'[–—]', '-', text)
        
        # Remove multiple blank lines
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        
        return text.strip()
    
    def fix_common_ocr_errors(self, text: str) -> str:
        """Fix common OCR errors in German text."""
        replacements = {
            # Common OCR mistakes
            'ß': 'ß',  # Sometimes ß is misread
            '1st': 'ist',  # 1 misread as i
            '0rt': 'Ort',  # 0 misread as O
            'Naturschutzgeb1et': 'Naturschutzgebiet',
            # Add more as needed
        }
        
        for wrong, correct in replacements.items():
            text = text.replace(wrong, correct)
        
        return text
    
    def segment_paragraphs(self, text: str) -> List[Dict[str, Any]]:
        """
        Segment text into paragraphs.
        
        Args:
            text: Cleaned text
        
        Returns:
            List of paragraph dictionaries
        """
        paragraphs = []
        
        # Find all § markers
        pattern = re.compile(r'^(§\s*\d+[a-z]?)\s*(.*?)(?=^§\s*\d+|$)', 
                           re.MULTILINE | re.DOTALL)
        
        for match in pattern.finditer(text):
            marker = match.group(1)
            content = match.group(2).strip()
            
            # Extract paragraph number
            nummer_match = re.match(r'§\s*(\d+[a-z]?)', marker)
            nummer = nummer_match.group(1) if nummer_match else None
            
            if nummer:
                # Calculate sort index
                base_num = re.match(r'(\d+)', nummer).group(1)
                sort_index = int(base_num) * 100
                
                # Add letter offset if present
                if len(nummer) > len(base_num):
                    letter = nummer[len(base_num)]
                    sort_index += ord(letter) - ord('a')
                
                paragraphs.append({
                    'nummer': nummer,
                    'marker': marker,
                    'content': content,
                    'sort_index': sort_index,
                    'start_pos': match.start(),
                    'end_pos': match.end()
                })
        
        # Sort by sort_index
        paragraphs.sort(key=lambda x: x['sort_index'])
        
        logger.info(f"Found {len(paragraphs)} paragraphs")
        return paragraphs
    
    def enhance_paragraphs(self, paragraphs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enhance paragraphs with additional metadata.
        
        Args:
            paragraphs: List of basic paragraph data
        
        Returns:
            Enhanced paragraph list
        """
        for para in paragraphs:
            content = para['content']
            
            # Determine rubrum (section type)
            para['rubrum'] = determine_rubrum(content)
            
            # Check if it's a relevant paragraph
            para['is_relevant'] = self._is_relevant_paragraph(content)
            
            # Extract title if present
            para['title'] = self._extract_paragraph_title(content)
            
            # Identify rule type
            para['rule_type'] = self._identify_rule_type(content)
            
            # Extract referenced paragraphs
            para['references'] = self._extract_references(content)
        
        return paragraphs
    
    def _is_relevant_paragraph(self, content: str) -> bool:
        """Check if paragraph contains relevant rules."""
        relevant_keywords = [
            'verboten', 'untersagt', 'nicht gestattet', 'unzulässig',
            'erlaubt', 'gestattet', 'zulässig',
            'ausnahme', 'befreiung', 'genehmigung',
            'ordnungswidrigkeit', 'owi', 'bußgeld',
            'naturschutzgebiet', 'schutzgebiet'
        ]
        
        content_lower = content.lower()
        return any(keyword in content_lower for keyword in relevant_keywords)
    
    def _extract_paragraph_title(self, content: str) -> Optional[str]:
        """Extract title from paragraph content."""
        lines = content.split('\n')
        
        # Check if first line looks like a title
        if lines:
            first_line = lines[0].strip()
            # Titles are often in parentheses or all caps
            if first_line.startswith('(') and first_line.endswith(')'):
                return first_line[1:-1]
            elif first_line.isupper() and len(first_line) < 100:
                return first_line
            elif re.match(r'^[A-ZÄÖÜ][a-zäöüß]+(?:\s+[A-ZÄÖÜ][a-zäöüß]+)*$', first_line):
                # Title case
                return first_line
        
        return None
    
    def _identify_rule_type(self, content: str) -> str:
        """Identify the type of rule in the paragraph."""
        content_lower = content.lower()
        
        if 'verboten' in content_lower or 'untersagt' in content_lower:
            return 'verbot'
        elif 'erlaubt' in content_lower and 'nicht' not in content_lower:
            return 'erlaubnis'
        elif 'ausnahme' in content_lower or 'befreiung' in content_lower:
            return 'ausnahme'
        elif 'ordnungswidrigkeit' in content_lower:
            return 'owi'
        else:
            return 'sonstiges'
    
    def _extract_references(self, content: str) -> List[str]:
        """Extract references to other paragraphs."""
        references = []
        
        # Pattern for paragraph references
        patterns = [
            r'§\s*(\d+[a-z]?)',  # § 3
            r'§§\s*(\d+[a-z]?)\s*(?:bis|und|-)\s*(\d+[a-z]?)',  # §§ 3 bis 5
            r'Absatz\s+(\d+)',  # Absatz 2
            r'Satz\s+(\d+)',  # Satz 1
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                references.append(match.group(0))
        
        return references
    
    def extract_document_metadata(self, text: str) -> Dict[str, Any]:
        """
        Extract document-level metadata from text.
        
        Args:
            text: Full document text
        
        Returns:
            Document metadata
        """
        metadata = {}
        
        # Try to find document title
        title_patterns = [
            r'Verordnung\s+über\s+das\s+Naturschutzgebiet\s+"([^"]+)"',
            r'Naturschutzgebiet\s+"([^"]+)"',
            r'NSG\s+"([^"]+)"',
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                metadata['schutzgebiet_name'] = match.group(1)
                break
        
        # Try to find document date
        date_patterns = [
            r'vom\s+(\d{1,2}\.\s*\w+\s+\d{4})',
            r'vom\s+(\d{1,2}\.\d{1,2}\.\d{4})',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                metadata['datum'] = match.group(1)
                break
        
        # Try to find issuing authority
        authority_patterns = [
            r'(Bezirksregierung\s+\w+)',
            r'(Landkreis\s+[\w\s-]+)',
            r'(Stadt\s+\w+)',
        ]
        
        for pattern in authority_patterns:
            match = re.search(pattern, text)
            if match:
                metadata['behoerde'] = match.group(1)
                break
        
        return metadata