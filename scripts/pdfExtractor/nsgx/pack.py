"""PDF to text chunks conversion."""

import json
import logging
import subprocess
from pathlib import Path
from typing import Iterator, List, Optional

import pypdf
from pdfminer.high_level import extract_text as pdfminer_extract
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfpage import PDFPage
from pdfminer.converter import TextConverter
from pdfminer.layout import LAParams
from io import StringIO

from .models import TextChunk
from .utils import extract_doc_id_from_filename, chunk_text_smart, save_json_file


def extract_text_pdfminer(pdf_path: str) -> Optional[str]:
    """Extract text using pdfminer.six."""
    try:
        return pdfminer_extract(pdf_path)
    except Exception as e:
        logging.getLogger("nsgx").debug(f"pdfminer extraction failed for {pdf_path}: {e}")
        return None


def extract_text_pypdf(pdf_path: str) -> Optional[str]:
    """Extract text using pypdf."""
    try:
        with open(pdf_path, 'rb') as file:
            reader = pypdf.PdfReader(file)
            text_parts = []
            
            for page in reader.pages:
                try:
                    text_parts.append(page.extract_text())
                except Exception as e:
                    logging.getLogger("nsgx").debug(f"pypdf page extraction failed: {e}")
                    continue
            
            return '\n'.join(text_parts) if text_parts else None
    except Exception as e:
        logging.getLogger("nsgx").debug(f"pypdf extraction failed for {pdf_path}: {e}")
        return None


def extract_text_pdftotext(pdf_path: str) -> Optional[str]:
    """Extract text using pdftotext command-line tool."""
    try:
        result = subprocess.run(
            ['pdftotext', '-layout', pdf_path, '-'],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            return result.stdout
        else:
            logging.getLogger("nsgx").debug(f"pdftotext failed for {pdf_path}: {result.stderr}")
            return None
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
        logging.getLogger("nsgx").debug(f"pdftotext extraction failed for {pdf_path}: {e}")
        return None


def extract_text_from_pdf(pdf_path: str) -> Optional[str]:
    """Extract text from PDF using fallback chain."""
    logger = logging.getLogger("nsgx")
    
    # Try pdfminer first
    text = extract_text_pdfminer(pdf_path)
    if text and text.strip():
        logger.debug(f"Successfully extracted text using pdfminer for {pdf_path}")
        return text.strip()
    
    # Try pypdf
    text = extract_text_pypdf(pdf_path)
    if text and text.strip():
        logger.debug(f"Successfully extracted text using pypdf for {pdf_path}")
        return text.strip()
    
    # Try pdftotext as fallback
    text = extract_text_pdftotext(pdf_path)
    if text and text.strip():
        logger.debug(f"Successfully extracted text using pdftotext for {pdf_path}")
        return text.strip()
    
    logger.warning(f"Failed to extract text from {pdf_path} using all methods")
    return None


def find_pdf_files(directory: str) -> Iterator[Path]:
    """Find all PDF files recursively."""
    path = Path(directory)
    if not path.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")
    
    if not path.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {directory}")
    
    # Find PDF files recursively
    for pdf_file in path.rglob("*.pdf"):
        if pdf_file.is_file():
            yield pdf_file


def process_pdf_to_chunks(pdf_path: Path, max_chars: int, logger: logging.Logger) -> List[TextChunk]:
    """Process a single PDF file into text chunks."""
    logger.info(f"Processing PDF: {pdf_path}")
    
    # Extract document ID from filename
    doc_id = extract_doc_id_from_filename(pdf_path.name)
    
    # Extract text
    text = extract_text_from_pdf(str(pdf_path))
    if not text:
        logger.error(f"Failed to extract text from {pdf_path}")
        return []
    
    logger.debug(f"Extracted {len(text)} characters from {pdf_path}")
    
    # Chunk the text
    text_chunks = chunk_text_smart(text, max_chars)
    logger.debug(f"Created {len(text_chunks)} chunks for {pdf_path}")
    
    # Create TextChunk objects
    chunks = []
    for i, chunk_text in enumerate(text_chunks):
        chunk_id = f"chunk_{i:03d}"
        chunk = TextChunk(
            doc_id=doc_id,
            chunk_id=chunk_id,
            text=chunk_text
        )
        chunks.append(chunk)
    
    return chunks


def pack_pdfs_to_chunks(
    pdf_directory: str,
    max_chars: int,
    output_dir: str,
    logger: logging.Logger
) -> None:
    """Pack all PDFs in directory to chunks JSONL file."""
    logger.info(f"Starting PDF packing from {pdf_directory}")
    
    # Find all PDF files
    pdf_files = list(find_pdf_files(pdf_directory))
    logger.info(f"Found {len(pdf_files)} PDF files")
    
    if not pdf_files:
        logger.warning(f"No PDF files found in {pdf_directory}")
        return
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Process each PDF
    all_chunks = []
    successful_files = 0
    failed_files = 0
    
    for pdf_file in pdf_files:
        try:
            chunks = process_pdf_to_chunks(pdf_file, max_chars, logger)
            if chunks:
                all_chunks.extend(chunks)
                successful_files += 1
                logger.debug(f"Successfully processed {pdf_file}: {len(chunks)} chunks")
            else:
                failed_files += 1
                logger.warning(f"No chunks created for {pdf_file}")
        except Exception as e:
            failed_files += 1
            logger.error(f"Failed to process {pdf_file}: {e}")
    
    # Write chunks to JSONL file
    chunks_file = output_path / "chunks.jsonl"
    logger.info(f"Writing {len(all_chunks)} chunks to {chunks_file}")
    
    try:
        with open(chunks_file, 'w', encoding='utf-8') as f:
            for chunk in all_chunks:
                json.dump(chunk.to_dict(), f, ensure_ascii=False)
                f.write('\n')
        
        logger.info(
            f"Pack completed successfully: {successful_files} files processed, "
            f"{failed_files} files failed, {len(all_chunks)} total chunks"
        )
        
        # Write summary
        summary = {
            "total_files": len(pdf_files),
            "successful_files": successful_files,
            "failed_files": failed_files,
            "total_chunks": len(all_chunks),
            "max_chars_per_chunk": max_chars,
            "output_file": str(chunks_file)
        }
        
        summary_file = output_path / "pack_summary.json"
        save_json_file(summary, str(summary_file))
        logger.info(f"Pack summary saved to {summary_file}")
        
    except Exception as e:
        logger.error(f"Failed to write chunks file: {e}")
        raise