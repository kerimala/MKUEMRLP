"""Utility functions for NSG extraction."""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


def setup_logging(log_dir: str = "logs") -> logging.Logger:
    """Set up structured logging."""
    Path(log_dir).mkdir(exist_ok=True)
    
    # Create logger
    logger = logging.getLogger("nsgx")
    logger.setLevel(logging.INFO)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler for general logs
    file_handler = logging.FileHandler(os.path.join(log_dir, "run.log"))
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)
    
    # Error handler
    error_handler = logging.FileHandler(os.path.join(log_dir, "errors.log"))
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(file_format)
    logger.addHandler(error_handler)
    
    return logger


def extract_doc_id_from_filename(filename: str) -> str:
    """Extract document ID from filename using NSG pattern."""
    # Try to extract NSG-XXXX-XXX pattern
    match = re.search(r'NSG-\d{4}-\d{3}', filename)
    if match:
        return match.group(0)
    
    # Fallback: use filename without extension
    return Path(filename).stem


def normalize_string_for_comparison(text: str) -> str:
    """Normalize string for comparison and clustering."""
    # Convert to lowercase
    text = text.lower()
    
    # Remove special characters and extra whitespace
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    # Replace common variations
    replacements = {
        'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
        'und': '', 'oder': '', 'sowie': '', 'bzw': '',
        'mit': '', 'ohne': '', 'von': '', 'zu': '', 'bei': '',
        'in': '', 'an': '', 'auf': '', 'unter': '', 'über': ''
    }
    
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Remove extra spaces again
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def to_snake_case(text: str) -> str:
    """Convert text to snake_case."""
    # First normalize
    text = normalize_string_for_comparison(text)
    
    # Replace spaces and hyphens with underscores
    text = re.sub(r'[\s-]+', '_', text)
    
    # Remove any remaining special characters
    text = re.sub(r'[^\w_]', '', text)
    
    # Ensure it doesn't start with a number
    if text and text[0].isdigit():
        text = f"_{text}"
    
    return text.lower()


def load_json_file(filepath: str) -> Dict[str, Any]:
    """Load JSON file with error handling."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Required file not found: {filepath}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {filepath}: {e}")


def save_json_file(data: Any, filepath: str, ensure_dir: bool = True) -> None:
    """Save data to JSON file with directory creation."""
    if ensure_dir:
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def chunk_text_smart(text: str, max_chars: int = 4000) -> List[str]:
    """Smart text chunking with preference for section breaks."""
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    
    # First try to split by sections (§)
    section_pattern = r'(\n\s*§\s*\d+)'
    sections = re.split(section_pattern, text)
    
    current_chunk = ""
    
    for i, section in enumerate(sections):
        # If this is a section marker, combine it with the next part
        if re.match(r'\n\s*§\s*\d+', section) and i + 1 < len(sections):
            if current_chunk and len(current_chunk + section + sections[i + 1]) > max_chars:
                # Save current chunk and start new one
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                current_chunk = section + sections[i + 1]
                sections[i + 1] = ""  # Mark as processed
            else:
                current_chunk += section + (sections[i + 1] if i + 1 < len(sections) else "")
                if i + 1 < len(sections):
                    sections[i + 1] = ""  # Mark as processed
        elif section and not re.match(r'\n\s*§\s*\d+', section):
            if len(current_chunk + section) > max_chars and current_chunk.strip():
                # Save current chunk
                chunks.append(current_chunk.strip())
                current_chunk = section
            else:
                current_chunk += section
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    # If chunks are still too large, split by paragraphs
    final_chunks = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            final_chunks.append(chunk)
        else:
            # Split by paragraphs
            paragraphs = chunk.split('\n\n')
            current_para_chunk = ""
            
            for para in paragraphs:
                if len(current_para_chunk + para + '\n\n') > max_chars and current_para_chunk.strip():
                    final_chunks.append(current_para_chunk.strip())
                    current_para_chunk = para + '\n\n'
                else:
                    current_para_chunk += para + '\n\n'
            
            if current_para_chunk.strip():
                final_chunks.append(current_para_chunk.strip())
    
    # Final fallback: hard split by sentences
    result_chunks = []
    for chunk in final_chunks:
        if len(chunk) <= max_chars:
            result_chunks.append(chunk)
        else:
            # Split by sentences
            sentences = re.split(r'(?<=[.!?])\s+', chunk)
            current_sent_chunk = ""
            
            for sentence in sentences:
                if len(current_sent_chunk + sentence + ' ') > max_chars and current_sent_chunk.strip():
                    result_chunks.append(current_sent_chunk.strip())
                    current_sent_chunk = sentence + ' '
                else:
                    current_sent_chunk += sentence + ' '
            
            if current_sent_chunk.strip():
                result_chunks.append(current_sent_chunk.strip())
    
    return [chunk for chunk in result_chunks if chunk.strip()]


def merge_conditions(conditions_list: List[List]) -> List[Dict[str, Any]]:
    """Merge overlapping conditions."""
    if not conditions_list:
        return []
    
    # Group conditions by type
    by_type = {}
    for conditions in conditions_list:
        for condition in conditions:
            cond_type = condition.get("type", "")
            if cond_type not in by_type:
                by_type[cond_type] = []
            by_type[cond_type].append(condition)
    
    merged = []
    
    for cond_type, cond_list in by_type.items():
        if cond_type == "datumspanne":
            # Merge overlapping date ranges
            merged.extend(_merge_date_ranges(cond_list))
        elif cond_type == "tageszeit":
            # Merge overlapping time ranges
            merged.extend(_merge_time_ranges(cond_list))
        else:
            # For other types, take unique values
            unique_values = set()
            for cond in cond_list:
                if "value" in cond:
                    unique_values.add(cond["value"])
            
            if len(unique_values) == 1:
                merged.append(cond_list[0])
            else:
                # Keep all unique conditions
                merged.extend(cond_list)
    
    return merged


def _merge_date_ranges(date_conditions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge overlapping date ranges."""
    if not date_conditions:
        return []
    
    ranges = []
    for cond in date_conditions:
        if "from" in cond and "to" in cond:
            ranges.append((cond["from"], cond["to"], cond))
    
    if not ranges:
        return date_conditions
    
    # Sort by start date
    ranges.sort(key=lambda x: x[0])
    
    merged_ranges = []
    current_start, current_end, current_cond = ranges[0]
    
    for start, end, cond in ranges[1:]:
        if start <= current_end:  # Overlapping
            current_end = max(current_end, end)
            # Keep the condition with higher confidence or first one
            if cond.get("confidence", 0) > current_cond.get("confidence", 0):
                current_cond = cond
        else:
            # Non-overlapping, save current and start new
            merged_ranges.append({
                **current_cond,
                "from": current_start,
                "to": current_end
            })
            current_start, current_end, current_cond = start, end, cond
    
    # Add the last range
    merged_ranges.append({
        **current_cond,
        "from": current_start,
        "to": current_end
    })
    
    return merged_ranges


def _merge_time_ranges(time_conditions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge overlapping time ranges."""
    if not time_conditions:
        return []
    
    ranges = []
    for cond in time_conditions:
        if "from" in cond and "to" in cond:
            ranges.append((cond["from"], cond["to"], cond))
    
    if not ranges:
        return time_conditions
    
    # Sort by start time
    ranges.sort(key=lambda x: x[0])
    
    merged_ranges = []
    current_start, current_end, current_cond = ranges[0]
    
    for start, end, cond in ranges[1:]:
        if start <= current_end:  # Overlapping
            current_end = max(current_end, end)
            if cond.get("confidence", 0) > current_cond.get("confidence", 0):
                current_cond = cond
        else:
            merged_ranges.append({
                **current_cond,
                "from": current_start,
                "to": current_end
            })
            current_start, current_end, current_cond = start, end, cond
    
    merged_ranges.append({
        **current_cond,
        "from": current_start,
        "to": current_end
    })
    
    return merged_ranges