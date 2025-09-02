"""
PDF text extraction module for NSG PDF to XML/JSON converter.
Handles extraction using PyMuPDF (primary) and pdfminer.six (fallback).
"""

import logging
from pathlib import Path
from typing import Optional, Dict, List, Any
from utils import handle_errors, normalize_whitespace

logger = logging.getLogger('nsg_converter.pdf_extractor')

# Try to import PDF libraries
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("PyMuPDF not available, will use pdfminer.six")

try:
    from pdfminer.high_level import extract_text as pdfminer_extract
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LAParams, LTTextContainer
    PDFMINER_AVAILABLE = True
except ImportError:
    PDFMINER_AVAILABLE = False
    logger.warning("pdfminer.six not available")

# Optional OCR support
try:
    import pytesseract
    from PIL import Image
    import io
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    logger.info("OCR support not available (pytesseract not installed)")


class PDFExtractor:
    """Extract text from PDF files using multiple methods."""
    
    def __init__(self, use_ocr: bool = False):
        """
        Initialize PDF extractor.
        
        Args:
            use_ocr: Whether to use OCR for scanned PDFs
        """
        self.use_ocr = use_ocr and OCR_AVAILABLE
        
        if self.use_ocr and not OCR_AVAILABLE:
            logger.warning("OCR requested but pytesseract not available")
        
        if not PYMUPDF_AVAILABLE and not PDFMINER_AVAILABLE:
            raise RuntimeError("No PDF extraction library available. "
                             "Please install PyMuPDF or pdfminer.six")
    
    def extract_text(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extract text from PDF file.
        
        Args:
            pdf_path: Path to PDF file
        
        Returns:
            Dict with 'text', 'pages', 'method', and 'metadata'
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        result = {
            'text': '',
            'pages': [],
            'method': 'unknown',
            'metadata': {
                'filename': pdf_path.name,
                'path': str(pdf_path)
            }
        }
        
        # Try PyMuPDF first (usually better results)
        if PYMUPDF_AVAILABLE:
            extracted = self._extract_with_pymupdf(pdf_path)
            if extracted and extracted['text'].strip():
                result.update(extracted)
                result['method'] = 'pymupdf'
                logger.info(f"Extracted text from {pdf_path.name} using PyMuPDF")
                return result
        
        # Fallback to pdfminer.six
        if PDFMINER_AVAILABLE:
            extracted = self._extract_with_pdfminer(pdf_path)
            if extracted and extracted['text'].strip():
                result.update(extracted)
                result['method'] = 'pdfminer'
                logger.info(f"Extracted text from {pdf_path.name} using pdfminer.six")
                return result
        
        # Try OCR if enabled and previous methods failed
        if self.use_ocr and PYMUPDF_AVAILABLE:
            extracted = self._extract_with_ocr(pdf_path)
            if extracted and extracted['text'].strip():
                result.update(extracted)
                result['method'] = 'ocr'
                logger.info(f"Extracted text from {pdf_path.name} using OCR")
                return result
        
        logger.warning(f"Could not extract text from {pdf_path.name}")
        return result
    
    @handle_errors({'text': '', 'pages': []})
    def _extract_with_pymupdf(self, pdf_path: Path) -> Dict[str, Any]:
        """Extract text using PyMuPDF."""
        if not PYMUPDF_AVAILABLE:
            return {'text': '', 'pages': []}
        
        doc = fitz.open(str(pdf_path))
        pages = []
        full_text = []
        
        try:
            for page_num, page in enumerate(doc, 1):
                page_text = page.get_text()
                pages.append({
                    'page_num': page_num,
                    'text': page_text,
                    'width': page.rect.width,
                    'height': page.rect.height
                })
                full_text.append(page_text)
            
            # Extract metadata
            metadata = doc.metadata or {}
            
            return {
                'text': '\n'.join(full_text),
                'pages': pages,
                'metadata': {
                    'page_count': len(doc),
                    'title': metadata.get('title', ''),
                    'author': metadata.get('author', ''),
                    'subject': metadata.get('subject', ''),
                    'keywords': metadata.get('keywords', ''),
                    'creator': metadata.get('creator', ''),
                    'producer': metadata.get('producer', '')
                }
            }
        finally:
            doc.close()
    
    @handle_errors({'text': '', 'pages': []})
    def _extract_with_pdfminer(self, pdf_path: Path) -> Dict[str, Any]:
        """Extract text using pdfminer.six."""
        if not PDFMINER_AVAILABLE:
            return {'text': '', 'pages': []}
        
        # Extract full text
        full_text = pdfminer_extract(str(pdf_path))
        
        # Extract page-by-page with layout analysis
        pages = []
        laparams = LAParams(
            line_overlap=0.5,
            char_margin=2.0,
            word_margin=0.1,
            boxes_flow=0.5,
            detect_vertical=False
        )
        
        for page_num, page_layout in enumerate(extract_pages(str(pdf_path), laparams=laparams), 1):
            page_text = []
            
            for element in page_layout:
                if isinstance(element, LTTextContainer):
                    page_text.append(element.get_text())
            
            pages.append({
                'page_num': page_num,
                'text': ''.join(page_text),
                'width': page_layout.width,
                'height': page_layout.height
            })
        
        return {
            'text': full_text,
            'pages': pages,
            'metadata': {
                'page_count': len(pages)
            }
        }
    
    @handle_errors({'text': '', 'pages': []})
    def _extract_with_ocr(self, pdf_path: Path) -> Dict[str, Any]:
        """Extract text using OCR (for scanned PDFs)."""
        if not OCR_AVAILABLE or not PYMUPDF_AVAILABLE:
            return {'text': '', 'pages': []}
        
        doc = fitz.open(str(pdf_path))
        pages = []
        full_text = []
        
        try:
            for page_num, page in enumerate(doc, 1):
                # First try to get text normally
                page_text = page.get_text()
                
                # If no text or very little text, try OCR
                if len(page_text.strip()) < 50:
                    # Render page as image
                    mat = fitz.Matrix(2, 2)  # 2x zoom for better OCR
                    pix = page.get_pixmap(matrix=mat)
                    img_data = pix.tobytes("png")
                    
                    # OCR the image
                    image = Image.open(io.BytesIO(img_data))
                    ocr_text = pytesseract.image_to_string(image, lang='deu')  # German
                    
                    if ocr_text.strip():
                        page_text = ocr_text
                        logger.debug(f"Used OCR for page {page_num}")
                
                pages.append({
                    'page_num': page_num,
                    'text': page_text,
                    'width': page.rect.width,
                    'height': page.rect.height
                })
                full_text.append(page_text)
            
            return {
                'text': '\n'.join(full_text),
                'pages': pages,
                'metadata': {
                    'page_count': len(doc),
                    'ocr_used': True
                }
            }
        finally:
            doc.close()
    
    def extract_from_directory(self, directory: str, 
                              pattern: str = "*.pdf") -> List[Dict[str, Any]]:
        """
        Extract text from all PDFs in a directory.
        
        Args:
            directory: Directory containing PDFs
            pattern: File pattern to match
        
        Returns:
            List of extraction results
        """
        directory = Path(directory)
        
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        
        results = []
        pdf_files = sorted(directory.glob(pattern))
        
        for pdf_file in pdf_files:
            logger.info(f"Processing {pdf_file.name}")
            try:
                result = self.extract_text(pdf_file)
                result['filename'] = pdf_file.name
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing {pdf_file.name}: {str(e)}")
                results.append({
                    'filename': pdf_file.name,
                    'text': '',
                    'pages': [],
                    'method': 'error',
                    'error': str(e)
                })
        
        return results
    
    def check_extraction_quality(self, extracted: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check the quality of extracted text.
        
        Args:
            extracted: Extraction result
        
        Returns:
            Quality metrics
        """
        text = extracted.get('text', '')
        pages = extracted.get('pages', [])
        
        # Calculate metrics
        metrics = {
            'total_chars': len(text),
            'total_words': len(text.split()),
            'total_pages': len(pages),
            'avg_chars_per_page': len(text) / len(pages) if pages else 0,
            'empty_pages': sum(1 for p in pages if len(p.get('text', '').strip()) < 10),
            'likely_scanned': False,
            'quality_score': 0
        }
        
        # Check if likely scanned (very low text content)
        if metrics['avg_chars_per_page'] < 100 and not extracted.get('metadata', {}).get('ocr_used'):
            metrics['likely_scanned'] = True
        
        # Calculate quality score (0-100)
        if metrics['total_chars'] > 1000:
            metrics['quality_score'] = min(100, (metrics['total_chars'] / 100))
        else:
            metrics['quality_score'] = (metrics['total_chars'] / 1000) * 100
        
        # Adjust for empty pages
        if metrics['empty_pages'] > 0:
            penalty = (metrics['empty_pages'] / metrics['total_pages']) * 20
            metrics['quality_score'] = max(0, metrics['quality_score'] - penalty)
        
        return metrics