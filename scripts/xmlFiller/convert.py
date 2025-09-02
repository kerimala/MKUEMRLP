#!/usr/bin/env python3
"""
NSG PDF to XML/JSON Converter
Converts NSG (Naturschutzgebiet) PDF documents to structured XML and JSON formats
following the NSG-Datenmodell v1.3 schema.

Usage:
    python convert.py --pdf-dir ./pdfs --schema ./schemas/NSGv1.3.json --out ./out

Author: NSG Converter Team
Version: 1.0.0
"""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

# Import our modules
from utils import setup_logging
from schema_loader import SchemaLoader
from pdf_extractor import PDFExtractor
from text_processor import TextProcessor
from rule_extractor import RuleExtractor
from serializer import Serializer

# Version
__version__ = "1.0.0"


class NSGConverter:
    """Main converter class orchestrating the conversion pipeline."""
    
    def __init__(self, schema_path: str, synonyms_path: Optional[str] = None,
                 use_ocr: bool = False, verbose: bool = False):
        """
        Initialize NSG converter.
        
        Args:
            schema_path: Path to NSG schema JSON
            synonyms_path: Optional path to synonyms JSON
            use_ocr: Whether to use OCR for scanned PDFs
            verbose: Enable verbose logging
        """
        # Setup logging
        self.logger = setup_logging(verbose)
        self.logger.info(f"NSG Converter v{__version__} initializing...")
        
        # Initialize components
        try:
            self.schema_loader = SchemaLoader(schema_path, synonyms_path)
            self.pdf_extractor = PDFExtractor(use_ocr)
            self.text_processor = TextProcessor()
            self.rule_extractor = RuleExtractor(self.schema_loader)
            self.serializer = Serializer(self.schema_loader)
        except Exception as e:
            self.logger.error(f"Failed to initialize converter: {str(e)}")
            raise
        
        # Statistics
        self.stats = {
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'total_time': 0
        }
    
    def convert_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """
        Convert a single PDF file.
        
        Args:
            pdf_path: Path to PDF file
        
        Returns:
            Conversion result
        """
        start_time = time.time()
        pdf_path = Path(pdf_path)
        
        self.logger.info(f"Processing {pdf_path.name}")
        
        try:
            # Step 1: Extract text from PDF
            self.logger.debug("Extracting text from PDF...")
            extracted = self.pdf_extractor.extract_text(pdf_path)
            
            if not extracted.get('text'):
                raise ValueError("No text extracted from PDF")
            
            # Step 2: Process and clean text
            self.logger.debug("Processing text...")
            processed = self.text_processor.process_text(extracted)
            
            # Step 3: Extract rules
            self.logger.debug("Extracting rules...")
            rules = self.rule_extractor.extract_rules(processed)
            
            # Step 4: Add document metadata
            doc_metadata = self.text_processor.extract_document_metadata(
                processed.get('cleaned_text', '')
            )
            for rule in rules:
                rule['document_metadata'] = doc_metadata
            
            elapsed = time.time() - start_time
            
            return {
                'success': True,
                'pdf_file': pdf_path.name,
                'rules': rules,
                'statistics': {
                    'extraction_method': extracted.get('method'),
                    'total_paragraphs': len(processed.get('paragraphs', [])),
                    'relevant_paragraphs': sum(1 for p in processed.get('paragraphs', []) 
                                              if p.get('is_relevant')),
                    'total_rules': len(rules),
                    'processing_time': elapsed
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error processing {pdf_path.name}: {str(e)}")
            return {
                'success': False,
                'pdf_file': pdf_path.name,
                'error': str(e),
                'rules': []
            }
    
    def convert_directory(self, pdf_dir: str, output_dir: str, 
                         generate_report: bool = False) -> Dict[str, Any]:
        """
        Convert all PDFs in a directory.
        
        Args:
            pdf_dir: Directory containing PDFs
            output_dir: Output directory
            generate_report: Whether to generate reports
        
        Returns:
            Overall results
        """
        pdf_dir = Path(pdf_dir)
        output_dir = Path(output_dir)
        
        if not pdf_dir.exists():
            raise FileNotFoundError(f"PDF directory not found: {pdf_dir}")
        
        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Find all PDF files
        pdf_files = sorted(pdf_dir.glob("*.pdf"))
        
        if not pdf_files:
            self.logger.warning(f"No PDF files found in {pdf_dir}")
            return {'total': 0, 'results': []}
        
        self.logger.info(f"Found {len(pdf_files)} PDF files to process")
        
        results = []
        
        for pdf_file in pdf_files:
            # Convert PDF
            result = self.convert_pdf(pdf_file)
            
            # Update statistics
            self.stats['processed'] += 1
            if result['success']:
                self.stats['successful'] += 1
                
                # Serialize outputs
                try:
                    filename_base = pdf_file.stem
                    output_paths = self.serializer.serialize(
                        result['rules'],
                        output_dir,
                        filename_base,
                        generate_report
                    )
                    result['outputs'] = output_paths
                    self.logger.info(f"✓ {pdf_file.name} converted successfully")
                except Exception as e:
                    self.logger.error(f"Failed to serialize {pdf_file.name}: {str(e)}")
                    result['success'] = False
                    result['error'] = f"Serialization failed: {str(e)}"
                    self.stats['failed'] += 1
            else:
                self.stats['failed'] += 1
                self.logger.error(f"✗ {pdf_file.name} conversion failed")
            
            results.append(result)
        
        return {
            'total': len(pdf_files),
            'successful': self.stats['successful'],
            'failed': self.stats['failed'],
            'results': results
        }
    
    def print_summary(self):
        """Print conversion summary."""
        print("\n" + "="*60)
        print("CONVERSION SUMMARY")
        print("="*60)
        print(f"Total PDFs processed: {self.stats['processed']}")
        print(f"Successful: {self.stats['successful']}")
        print(f"Failed: {self.stats['failed']}")
        
        if self.stats['processed'] > 0:
            success_rate = (self.stats['successful'] / self.stats['processed']) * 100
            print(f"Success rate: {success_rate:.1f}%")
        
        # Print schema statistics
        schema_stats = self.schema_loader.get_statistics()
        print(f"\nSchema loaded with:")
        print(f"  - {schema_stats['total_enums']} enum types")
        print(f"  - {schema_stats['total_enum_values']} total enum values")
        print(f"  - {schema_stats['total_synonyms']} synonyms")
        print("="*60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Convert NSG PDF documents to XML and JSON',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert all PDFs in a directory
  python convert.py --pdf-dir ./pdfs --schema ./schemas/NSGv1.3.json --out ./out
  
  # With synonym mappings
  python convert.py --pdf-dir ./pdfs --schema ./schemas/NSGv1.3.json \\
                    --mapping ./synonyms.json --out ./out
  
  # With OCR support for scanned PDFs
  python convert.py --pdf-dir ./pdfs --schema ./schemas/NSGv1.3.json \\
                    --out ./out --ocr
  
  # Generate reports
  python convert.py --pdf-dir ./pdfs --schema ./schemas/NSGv1.3.json \\
                    --out ./out --report
        """
    )
    
    parser.add_argument(
        '--pdf-dir',
        required=True,
        help='Directory containing PDF files to convert'
    )
    
    parser.add_argument(
        '--schema',
        required=True,
        help='Path to NSG schema JSON file (NSGv1.3.json)'
    )
    
    parser.add_argument(
        '--out',
        required=True,
        help='Output directory for XML and JSON files'
    )
    
    parser.add_argument(
        '--mapping',
        help='Optional path to synonyms mapping JSON file'
    )
    
    parser.add_argument(
        '--ocr',
        action='store_true',
        help='Enable OCR for scanned PDFs (requires tesseract)'
    )
    
    parser.add_argument(
        '--report',
        action='store_true',
        help='Generate processing report for each PDF'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version=f'NSG Converter v{__version__}'
    )
    
    args = parser.parse_args()
    
    try:
        # Initialize converter
        converter = NSGConverter(
            schema_path=args.schema,
            synonyms_path=args.mapping,
            use_ocr=args.ocr,
            verbose=args.verbose
        )
        
        # Process PDFs
        results = converter.convert_directory(
            pdf_dir=args.pdf_dir,
            output_dir=args.out,
            generate_report=args.report
        )
        
        # Print summary
        converter.print_summary()
        
        # Exit with appropriate code
        if results['failed'] == 0:
            sys.exit(0)
        elif results['successful'] > 0:
            sys.exit(1)  # Partial success
        else:
            sys.exit(2)  # Complete failure
            
    except KeyboardInterrupt:
        print("\n\nConversion interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nFATAL ERROR: {str(e)}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()