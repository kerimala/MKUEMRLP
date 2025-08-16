"""Minimal enum-diff tool for identifying missing enum values from NSG PDFs."""

import csv
import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from rapidfuzz import fuzz
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .pack import extract_text_from_pdf, find_pdf_files
from .utils import extract_doc_id_from_filename, normalize_string_for_comparison, save_json_file, load_json_file


@dataclass
class EnumProposal:
    """Represents a proposal for an enum addition."""
    type: str  # aktivitaet|zone|ort
    candidate: str
    decision: str  # ADD_NEW|MAP_TO_EXISTING|IGNORE|UNSURE
    target_or_key: str
    reason: str
    citation: str
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "candidate": self.candidate,
            "decision": self.decision,
            "target_or_key": self.target_or_key,
            "reason": self.reason,
            "citation": self.citation,
            "confidence": self.confidence
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnumProposal":
        return cls(
            type=data["type"],
            candidate=data["candidate"],
            decision=data["decision"],
            target_or_key=data["target_or_key"],
            reason=data["reason"],
            citation=data["citation"],
            confidence=data["confidence"]
        )


@dataclass
class ParagraphResult:
    """Result of processing a single paragraph."""
    doc_id: str
    para_id: str
    proposals: List[EnumProposal] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "para_id": self.para_id,
            "proposals": [p.to_dict() for p in self.proposals]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParagraphResult":
        proposals = [EnumProposal.from_dict(p) for p in data.get("proposals", [])]
        return cls(
            doc_id=data["doc_id"],
            para_id=data["para_id"],
            proposals=proposals
        )


@dataclass
class CandidateAggregate:
    """Aggregated information about a candidate."""
    type: str
    candidate: str
    decision: str
    target_or_key: str
    reason: str
    doc_count: int
    example_quote: str
    confidence_avg: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "candidate": self.candidate,
            "decision": self.decision,
            "target_or_key": self.target_or_key,
            "reason": self.reason,
            "doc_count": self.doc_count,
            "example_quote": self.example_quote,
            "confidence_avg": self.confidence_avg
        }


class DeepSeekEnumClient:
    """DeepSeek client specialized for enum-diff tasks."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        
        # Load configuration
        self.endpoint = os.getenv('DEEPSEEK_ENDPOINT')
        self.chat_model = os.getenv('DEEPSEEK_MODEL_CHAT', 'deepseek-chat')
        self.reasoner_model = os.getenv('DEEPSEEK_MODEL_REASONER', 'deepseek-reasoner')
        self.api_key = os.getenv('DEEPSEEK_API_KEY')
        
        # Fallback to DEEPSEEK_MODEL only if both specific models are not set
        fallback_model = os.getenv('DEEPSEEK_MODEL', 'deepseek-chat')
        if not os.getenv('DEEPSEEK_MODEL_CHAT'):
            self.chat_model = fallback_model
        if not os.getenv('DEEPSEEK_MODEL_REASONER'):
            self.reasoner_model = fallback_model
        
        # Validate configuration
        self._validate_configuration()
        
        # Setup session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            backoff_factor=1,
            allowed_methods=["POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Default headers
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        })
        
        self.logger.info(f"DeepSeek client initialized with chat model: {self.chat_model}")
        self.logger.info(f"Reasoner model: {self.reasoner_model}")
    
    def _validate_configuration(self) -> None:
        """Validate API configuration."""
        if not self.endpoint:
            raise ValueError("DEEPSEEK_ENDPOINT is required but not set")
        if not self.endpoint.startswith(('http://', 'https://')):
            raise ValueError(f"DEEPSEEK_ENDPOINT must be a valid URL, got: {self.endpoint}")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY is required but not set")
        if not self.api_key.startswith('sk-'):
            self.logger.warning("DEEPSEEK_API_KEY does not start with 'sk-', this may be incorrect")
    
    def process_paragraph(self, doc_id: str, para_id: str, paragraph: str, 
                         system_prompt: str, use_reasoner: bool = False, retry_count: int = 0) -> Optional[ParagraphResult]:
        """Process a single paragraph to extract enum proposals."""
        model = self.reasoner_model if use_reasoner else self.chat_model
        mode_text = "reasoner" if use_reasoner else "chat"
        self.logger.debug(f"Processing {doc_id}:{para_id} with {mode_text} model: {model}")
        
        if retry_count > 0:
            self.logger.debug(f"Retry attempt {retry_count} for {doc_id}:{para_id}")
        
        # Prepare request payload
        # Ensure JSON keyword requirement is met
        user_content = paragraph
        if "json" not in system_prompt.lower() and "json" not in paragraph.lower():
            user_content = f"Analyze this paragraph and return valid JSON: {paragraph}"
            self.logger.debug(f"Added JSON keyword to user message for {doc_id}:{para_id}")
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.1 if use_reasoner else 0.2,
            "max_tokens": 1500,
            "response_format": {"type": "json_object"}
        }
        
        try:
            # Make API request
            response = self.session.post(
                self.endpoint,
                json=payload,
                timeout=90 if use_reasoner else 60
            )
            
            if response.status_code == 429:
                # Rate limited, wait and retry
                retry_after = int(response.headers.get('Retry-After', 60))
                self.logger.warning(f"Rate limited, waiting {retry_after} seconds")
                time.sleep(retry_after)
                return self.process_paragraph(doc_id, para_id, paragraph, system_prompt, use_reasoner)
            
            if response.status_code != 200:
                self.logger.error(f"API request failed with status {response.status_code} for {doc_id}:{para_id}")
                self.logger.error(f"Response text: {response.text}")
                return None
            
            if not response.text:
                self.logger.error(f"Empty response for {doc_id}:{para_id}")
                return None
            
            # Parse response
            try:
                result = response.json()
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse API response JSON for {doc_id}:{para_id}: {e}")
                return None
            
            # Extract content
            choices = result.get('choices', [])
            if not choices:
                self.logger.error(f"No choices in API response for {doc_id}:{para_id}")
                return None
            
            message = choices[0].get('message', {})
            content = message.get('content', '')
            
            if not content:
                # Handle empty content with retry logic (known DeepSeek issue)
                if retry_count < 2:  # Allow up to 2 retries
                    self.logger.warning(f"Empty content received for {doc_id}:{para_id}, retrying ({retry_count + 1}/2)")
                    self.logger.warning("This is a known DeepSeek JSON mode issue - retrying with slight delay")
                    time.sleep(1)  # Small delay before retry
                    return self.process_paragraph(doc_id, para_id, paragraph, system_prompt, use_reasoner, retry_count + 1)
                else:
                    self.logger.error(f"Empty content in API response for {doc_id}:{para_id} after {retry_count + 1} attempts")
                    self.logger.error("Known DeepSeek issue: JSON mode may occasionally return empty content")
                    return None
            
            # Parse nested JSON content
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse nested JSON content for {doc_id}:{para_id}: {e}")
                return None
            
            # Convert to ParagraphResult
            proposals = []
            for prop_data in data.get('proposals', []):
                try:
                    proposal = EnumProposal(
                        type=prop_data.get('type', ''),
                        candidate=prop_data.get('candidate', ''),
                        decision=prop_data.get('decision', ''),
                        target_or_key=prop_data.get('target_or_key', ''),
                        reason=prop_data.get('reason', ''),
                        citation=prop_data.get('citation', ''),
                        confidence=prop_data.get('confidence', 0.0)
                    )
                    proposals.append(proposal)
                except Exception as e:
                    self.logger.warning(f"Failed to parse proposal in {doc_id}:{para_id}: {e}")
                    continue
            
            result = ParagraphResult(
                doc_id=doc_id,
                para_id=para_id,
                proposals=proposals
            )
            
            self.logger.debug(f"Successfully processed {doc_id}:{para_id}: {len(proposals)} proposals")
            return result
            
        except requests.exceptions.Timeout as e:
            self.logger.error(f"Request timeout for {doc_id}:{para_id}: {e}")
            return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request error for {doc_id}:{para_id}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error processing {doc_id}:{para_id}: {e}")
            return None


class EnumDiffCache:
    """SQLite cache for API responses."""
    
    def __init__(self, cache_file: str):
        self.cache_file = cache_file
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the cache database."""
        Path(self.cache_file).parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.cache_file) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS paragraph_cache (
                    doc_id TEXT,
                    para_hash TEXT,
                    model TEXT,
                    response_json TEXT,
                    timestamp INTEGER,
                    PRIMARY KEY (doc_id, para_hash, model)
                )
            ''')
            conn.commit()
    
    def get_cached_response(self, doc_id: str, paragraph: str, model: str) -> Optional[Dict[str, Any]]:
        """Get cached response for a paragraph."""
        para_hash = hashlib.sha256(paragraph.encode()).hexdigest()[:16]
        
        with sqlite3.connect(self.cache_file) as conn:
            cursor = conn.execute(
                'SELECT response_json FROM paragraph_cache WHERE doc_id = ? AND para_hash = ? AND model = ?',
                (doc_id, para_hash, model)
            )
            row = cursor.fetchone()
            
            if row:
                try:
                    return json.loads(row[0])
                except json.JSONDecodeError:
                    return None
        
        return None
    
    def cache_response(self, doc_id: str, paragraph: str, model: str, response: Dict[str, Any]) -> None:
        """Cache a response for a paragraph."""
        para_hash = hashlib.sha256(paragraph.encode()).hexdigest()[:16]
        timestamp = int(time.time())
        
        with sqlite3.connect(self.cache_file) as conn:
            conn.execute(
                '''INSERT OR REPLACE INTO paragraph_cache 
                   (doc_id, para_hash, model, response_json, timestamp) VALUES (?, ?, ?, ?, ?)''',
                (doc_id, para_hash, model, json.dumps(response), timestamp)
            )
            conn.commit()


def load_system_prompt() -> str:
    """Load the enum-diff system prompt."""
    prompt_file = Path("prompts/enumdiff_system.txt")
    if not prompt_file.exists():
        raise FileNotFoundError(f"System prompt file not found: {prompt_file}")
    
    with open(prompt_file, 'r', encoding='utf-8') as f:
        prompt_template = f.read()
    
    # Load known enums
    enums_file = Path("prompts/known_enums.json")
    if not enums_file.exists():
        raise FileNotFoundError(f"Known enums file not found: {enums_file}")
    
    known_enums = load_json_file(str(enums_file))
    known_enums_json = json.dumps(known_enums, indent=2, ensure_ascii=False)
    
    # Inject enums into prompt
    system_prompt = prompt_template.replace("{{KNOWN_ENUMS_JSON}}", known_enums_json)
    
    return system_prompt


def extract_paragraphs_from_pdf(pdf_path: str) -> List[Tuple[str, str]]:
    """Extract rule-bearing paragraphs from PDF."""
    text = extract_text_from_pdf(pdf_path)
    if not text:
        return []
    
    # Split into paragraphs by blank lines
    paragraphs = re.split(r'\n\s*\n', text)
    
    # Filter to rule-bearing paragraphs
    rule_patterns = [
        r'verboten|untersagt|zulässig',
        r'Ausnahme|Genehmigung|Befreiung',
        r'Ordnungswidrigkeit',
        r'§\s*[34]'
    ]
    rule_regex = re.compile('|'.join(rule_patterns), re.IGNORECASE)
    
    # Filter out preambles, signatures, annexes
    skip_patterns = [
        r'Bekanntmachung|Verkündung|Amtsblatt',
        r'Unterschrift|gez\.|gezeichnet',
        r'Anlage|Anhang|Karte|Plan',
        r'Inhaltsverzeichnis|Gliederung'
    ]
    skip_regex = re.compile('|'.join(skip_patterns), re.IGNORECASE)
    
    filtered_paragraphs = []
    for i, paragraph in enumerate(paragraphs):
        paragraph = paragraph.strip()
        
        # Skip if too short or matches skip patterns
        if len(paragraph) < 50 or skip_regex.search(paragraph):
            continue
        
        # Keep if matches rule patterns
        if rule_regex.search(paragraph):
            para_id = f"para_{i:03d}"
            filtered_paragraphs.append((para_id, paragraph))
    
    return filtered_paragraphs


def process_single_pdf(pdf_path: Path, client: DeepSeekEnumClient, cache: EnumDiffCache,
                      system_prompt: str, provider_mode: str, logger: logging.Logger) -> List[ParagraphResult]:
    """Process a single PDF file."""
    doc_id = extract_doc_id_from_filename(pdf_path.name)
    logger.debug(f"Processing PDF: {pdf_path} -> {doc_id}")
    
    # Extract paragraphs
    paragraphs = extract_paragraphs_from_pdf(str(pdf_path))
    if not paragraphs:
        logger.warning(f"No rule-bearing paragraphs found in {pdf_path}")
        return []
    
    logger.info(f"Extracted {len(paragraphs)} paragraphs from {doc_id}")
    
    results = []
    for para_id, paragraph in paragraphs:
        # Check cache first
        if provider_mode == "auto":
            # Try chat model first
            cached_response = cache.get_cached_response(doc_id, paragraph, client.chat_model)
            if cached_response:
                try:
                    result = ParagraphResult.from_dict(cached_response)
                    results.append(result)
                    logger.debug(f"Used cached response for {doc_id}:{para_id}")
                    continue
                except Exception as e:
                    logger.warning(f"Failed to parse cached response for {doc_id}:{para_id}: {e}")
        
        # Process with API
        use_reasoner = provider_mode == "reasoner"
        result = client.process_paragraph(doc_id, para_id, paragraph, system_prompt, use_reasoner)
        
        if result:
            # Check if we need to escalate to reasoner (auto mode only)
            if provider_mode == "auto" and not use_reasoner:
                needs_reasoner = False
                for proposal in result.proposals:
                    if proposal.decision == "UNSURE" or proposal.confidence < 0.65:
                        needs_reasoner = True
                        break
                
                if needs_reasoner:
                    logger.info(f"Escalating {doc_id}:{para_id} to reasoner model")
                    
                    # Check reasoner cache
                    cached_response = cache.get_cached_response(doc_id, paragraph, client.reasoner_model)
                    if cached_response:
                        try:
                            result = ParagraphResult.from_dict(cached_response)
                            logger.debug(f"Used cached reasoner response for {doc_id}:{para_id}")
                        except Exception as e:
                            logger.warning(f"Failed to parse cached reasoner response: {e}")
                            # Re-process with reasoner
                            result = client.process_paragraph(doc_id, para_id, paragraph, system_prompt, True)
                    else:
                        # Process with reasoner
                        result = client.process_paragraph(doc_id, para_id, paragraph, system_prompt, True)
                        
                        # Cache reasoner result
                        if result:
                            cache.cache_response(doc_id, paragraph, client.reasoner_model, result.to_dict())
            
            # Cache the result
            model_used = client.reasoner_model if use_reasoner else client.chat_model
            cache.cache_response(doc_id, paragraph, model_used, result.to_dict())
            results.append(result)
        else:
            logger.error(f"Failed to process {doc_id}:{para_id}")
    
    return results


def aggregate_candidates(all_results: List[ParagraphResult], 
                        min_doc_count: int, logger: logging.Logger) -> List[CandidateAggregate]:
    """Aggregate candidates across all results."""
    logger.info(f"Aggregating candidates with min_doc_count={min_doc_count}")
    
    # Collect all proposals by normalized key
    candidate_map: Dict[str, List[Tuple[EnumProposal, str]]] = {}  # key -> [(proposal, doc_id), ...]
    
    for result in all_results:
        for proposal in result.proposals:
            if proposal.decision == "ADD_NEW":
                # Normalize candidate key for clustering
                normalized_key = normalize_string_for_comparison(proposal.candidate)
                key = f"{proposal.type}:{normalized_key}"
                
                if key not in candidate_map:
                    candidate_map[key] = []
                candidate_map[key].append((proposal, result.doc_id))
    
    # Cluster similar candidates using fuzzy matching
    clusters: Dict[str, List[Tuple[EnumProposal, str]]] = {}
    processed_keys: Set[str] = set()
    
    for key, proposals in candidate_map.items():
        if key in processed_keys:
            continue
        
        # Find similar keys
        cluster_keys = [key]
        for other_key in candidate_map:
            if other_key != key and other_key not in processed_keys:
                if key.split(':', 1)[0] == other_key.split(':', 1)[0]:  # Same type
                    similarity = fuzz.ratio(key, other_key)
                    if similarity >= 80:  # 80% similarity threshold
                        cluster_keys.append(other_key)
        
        # Merge all proposals from similar keys
        all_cluster_proposals = []
        for cluster_key in cluster_keys:
            all_cluster_proposals.extend(candidate_map[cluster_key])
            processed_keys.add(cluster_key)
        
        clusters[key] = all_cluster_proposals
    
    # Create aggregates
    aggregates = []
    for key, proposals in clusters.items():
        if not proposals:
            continue
        
        # Count unique documents
        doc_ids = set(doc_id for _, doc_id in proposals)
        doc_count = len(doc_ids)
        
        if doc_count < min_doc_count:
            continue
        
        # Find best proposal (highest confidence)
        best_proposal = max(proposals, key=lambda x: x[0].confidence)[0]
        
        # Calculate average confidence
        avg_confidence = sum(p.confidence for p, _ in proposals) / len(proposals)
        
        # Find best quote (shortest non-empty one)
        best_quote = min(
            (p.citation for p, _ in proposals if p.citation.strip()),
            key=len,
            default=best_proposal.citation
        )
        
        aggregate = CandidateAggregate(
            type=best_proposal.type,
            candidate=best_proposal.candidate,
            decision=best_proposal.decision,
            target_or_key=best_proposal.target_or_key,
            reason=best_proposal.reason,
            doc_count=doc_count,
            example_quote=best_quote,
            confidence_avg=avg_confidence
        )
        aggregates.append(aggregate)
    
    # Sort by document count (descending) then by confidence (descending)
    aggregates.sort(key=lambda x: (-x.doc_count, -x.confidence_avg))
    
    logger.info(f"Generated {len(aggregates)} candidate aggregates")
    return aggregates


def write_review_csv(aggregates: List[CandidateAggregate], output_file: str) -> None:
    """Write candidates review CSV."""
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'type', 'candidate', 'decision', 'target_or_key', 'reason', 
            'doc_count', 'example_quote', 'confidence_avg'
        ])
        
        for agg in aggregates:
            writer.writerow([
                agg.type, agg.candidate, agg.decision, agg.target_or_key,
                agg.reason, agg.doc_count, agg.example_quote, agg.confidence_avg
            ])


def write_dbml_patches(aggregates: List[CandidateAggregate], output_file: str) -> None:
    """Write DBML enum addition patches."""
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    
    # Group by enum type
    enum_additions = {
        'aktivitaet': [],
        'zone': [],
        'ort': []
    }
    
    for agg in aggregates:
        if agg.decision == "ADD_NEW":
            enum_type = {
                'aktivitaet': 'aktivitaet',
                'zone': 'zone',
                'ort': 'ort'
            }.get(agg.type, agg.type)
            
            if enum_type in enum_additions:
                # Convert to snake_case key
                key = normalize_string_for_comparison(agg.candidate).replace(' ', '_')
                enum_additions[enum_type].append(key)
    
    # Write DBML
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("// DBML Enum Additions\n")
        f.write("// Add these values to your existing enum definitions\n\n")
        
        for enum_type, values in enum_additions.items():
            if values:
                f.write(f"// Add to {enum_type}_enum:\n")
                for value in values:
                    f.write(f"  {value}\n")
                f.write("\n")


def write_changelog(aggregates: List[CandidateAggregate], output_file: str) -> None:
    """Write changelog with new enum values."""
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("# Enum Additions Changelog\n\n")
        f.write(f"Generated on {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # Group by type
        by_type = {}
        for agg in aggregates:
            if agg.decision == "ADD_NEW":
                if agg.type not in by_type:
                    by_type[agg.type] = []
                by_type[agg.type].append(agg)
        
        for enum_type, values in by_type.items():
            f.write(f"## {enum_type.title()} Enum Additions\n\n")
            for agg in values:
                f.write(f"- **{agg.candidate}**: {agg.reason}\n")
                f.write(f"  - Found in {agg.doc_count} documents\n")
                f.write(f"  - Example: \"{agg.example_quote}\"\n")
                f.write(f"  - Confidence: {agg.confidence_avg:.2f}\n\n")


def run_enumdiff(
    pdfdir: str,
    output_dir: str,
    provider_mode: str,
    concurrency: int,
    min_doc_count: int,
    force: bool,
    logger: logging.Logger
) -> None:
    """Run the enum-diff extraction process."""
    logger.info(f"Starting enum-diff with pdfdir={pdfdir}, concurrency={concurrency}")
    
    # Setup output directories
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    proposals_file = output_path / "proposals.jsonl"
    cache_file = output_path / "cache.sqlite"
    review_dir = output_path / "review"
    dbml_dir = output_path / "dbml_patches"
    
    # Clear existing outputs if force
    if force:
        if proposals_file.exists():
            proposals_file.unlink()
        logger.info("Cleared existing outputs (--force)")
    
    # Find PDF files
    pdf_files = list(find_pdf_files(pdfdir))
    if not pdf_files:
        logger.error(f"No PDF files found in {pdfdir}")
        return
    
    logger.info(f"Found {len(pdf_files)} PDF files")
    
    # Load system prompt
    system_prompt = load_system_prompt()
    logger.debug(f"Loaded system prompt: {len(system_prompt)} characters")
    
    # Initialize components
    client = DeepSeekEnumClient(logger)
    cache = EnumDiffCache(str(cache_file))
    
    # Process PDFs
    all_results = []
    successful_count = 0
    failed_count = 0
    
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        # Submit all tasks
        future_to_pdf = {
            executor.submit(process_single_pdf, pdf_file, client, cache, system_prompt, provider_mode, logger): pdf_file
            for pdf_file in pdf_files
        }
        
        # Process results as they complete
        for future in as_completed(future_to_pdf):
            pdf_file = future_to_pdf[future]
            try:
                results = future.result()
                if results:
                    all_results.extend(results)
                    successful_count += 1
                    logger.info(f"Processed {pdf_file.name}: {len(results)} paragraphs")
                else:
                    failed_count += 1
                    logger.warning(f"No results from {pdf_file.name}")
            except Exception as e:
                logger.error(f"Failed to process {pdf_file.name}: {e}")
                failed_count += 1
    
    logger.info(f"Processing completed: {successful_count} successful, {failed_count} failed")
    
    if not all_results:
        logger.warning("No results to process")
        return
    
    # Write proposals to JSONL
    with open(proposals_file, 'w', encoding='utf-8') as f:
        for result in all_results:
            f.write(json.dumps(result.to_dict(), ensure_ascii=False) + '\n')
    
    logger.info(f"Wrote {len(all_results)} paragraph results to {proposals_file}")
    
    # Aggregate candidates
    aggregates = aggregate_candidates(all_results, min_doc_count, logger)
    
    if not aggregates:
        logger.warning("No candidates meet the minimum document count threshold")
        return
    
    # Write outputs
    review_csv = review_dir / "candidates_review.csv"
    dbml_patch = dbml_dir / "enum_additions.dbml"
    changelog = output_path / "CHANGELOG.md"
    
    write_review_csv(aggregates, str(review_csv))
    write_dbml_patches(aggregates, str(dbml_patch))
    write_changelog(aggregates, str(changelog))
    
    logger.info(f"Generated outputs:")
    logger.info(f"  - Review CSV: {review_csv}")
    logger.info(f"  - DBML patches: {dbml_patch}")
    logger.info(f"  - Changelog: {changelog}")
    logger.info(f"  - Cache: {cache_file}")
    
    # Summary
    summary = {
        "total_pdfs": len(pdf_files),
        "successful_pdfs": successful_count,
        "failed_pdfs": failed_count,
        "total_paragraphs": len(all_results),
        "total_proposals": sum(len(r.proposals) for r in all_results),
        "aggregated_candidates": len(aggregates),
        "provider_mode": provider_mode,
        "concurrency": concurrency,
        "min_doc_count": min_doc_count
    }
    
    summary_file = output_path / "enumdiff_summary.json"
    save_json_file(summary, str(summary_file))
    logger.info(f"Summary saved to {summary_file}")