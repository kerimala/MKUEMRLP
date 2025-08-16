"""DeepSeek API integration for chunk processing."""

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import TextChunk, ChunkResult
from .utils import load_json_file, save_json_file


class DeepSeekClient:
    """Client for DeepSeek API with retry logic."""
    
    def __init__(self, endpoint: str, model: str, api_key: str, logger: logging.Logger):
        self.logger = logger
        
        # Validate configuration
        self._validate_configuration(endpoint, model, api_key)
        
        self.endpoint = endpoint
        self.model = model
        self.api_key = api_key
        
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
        
        self.logger.info(f"DeepSeek client initialized with endpoint: {self.endpoint}")
        self.logger.info(f"Using model: {self.model}")
    
    def _validate_configuration(self, endpoint: str, model: str, api_key: str) -> None:
        """Validate API configuration parameters."""
        if not endpoint:
            raise ValueError("DEEPSEEK_ENDPOINT is required but not set")
        
        if not endpoint.startswith(('http://', 'https://')):
            raise ValueError(f"DEEPSEEK_ENDPOINT must be a valid URL, got: {endpoint}")
        
        if not model:
            raise ValueError("DEEPSEEK_MODEL is required but not set")
        
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is required but not set")
        
        if not api_key.startswith('sk-'):
            self.logger.warning("DEEPSEEK_API_KEY does not start with 'sk-', this may be incorrect")
        
        self.logger.debug("API configuration validation passed")
    
    def test_connectivity(self) -> bool:
        """Test API connectivity with a minimal request."""
        test_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a test assistant. Respond with valid JSON format."},
                {"role": "user", "content": "Return a simple JSON object with status field: {\"status\": \"ok\"}"}
            ],
            "temperature": 0.1,
            "max_tokens": 50,
            "response_format": {"type": "json_object"}
        }
        
        try:
            self.logger.info("Testing API connectivity...")
            response = self.session.post(
                self.endpoint,
                json=test_payload,
                timeout=30
            )
            
            self.logger.debug(f"Connectivity test status: {response.status_code}")
            
            if response.status_code == 401:
                self.logger.error("API authentication failed - check your API key")
                return False
            elif response.status_code == 403:
                self.logger.error("API access forbidden - check your API permissions")
                return False
            elif response.status_code == 404:
                self.logger.error("API endpoint not found - check your endpoint URL")
                return False
            elif response.status_code != 200:
                self.logger.error(f"API test failed with status {response.status_code}")
                if response.text:
                    self.logger.error(f"Response: {response.text}")
                return False
            
            # Test JSON parsing
            if not response.text:
                self.logger.error("Empty response from API test")
                return False
            
            try:
                result = response.json()
                self.logger.info("API connectivity test successful")
                self.logger.debug(f"Test response structure: {list(result.keys()) if isinstance(result, dict) else type(result)}")
                return True
            except json.JSONDecodeError:
                self.logger.error("API returned non-JSON response in connectivity test")
                self.logger.debug(f"Raw response: {response.text[:500]}")
                return False
                
        except requests.exceptions.Timeout:
            self.logger.error("API connectivity test timed out")
            return False
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"Cannot connect to API: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Connectivity test failed: {e}")
            return False
    
    def extract_from_chunk(self, chunk: TextChunk, system_prompt: str, retry_count: int = 0) -> Optional[ChunkResult]:
        """Extract rules from a text chunk using DeepSeek API."""
        self.logger.debug(f"Processing chunk {chunk.doc_id}__{chunk.chunk_id}")
        
        # Prepare request payload
        # Ensure JSON keyword requirement is met for DeepSeek API
        user_content = chunk.text
        if "json" not in system_prompt.lower() and "json" not in chunk.text.lower():
            user_content = f"Extract information from the following text and return valid JSON: {chunk.text}"
            self.logger.debug(f"Added JSON keyword to user message for {chunk.doc_id}__{chunk.chunk_id}")
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.1,
            "max_tokens": 2000,
            "response_format": {"type": "json_object"}
        }
        
        try:
            # Log request details for debugging (mask sensitive data)
            self.logger.debug(f"Making API request for {chunk.doc_id}__{chunk.chunk_id}")
            self.logger.debug(f"Request URL: {self.endpoint}")
            self.logger.debug(f"Request payload size: {len(json.dumps(payload))} chars")
            self.logger.debug(f"Chunk text length: {len(chunk.text)} chars")
            
            # Make API request with timeout
            response = self.session.post(
                self.endpoint,
                json=payload,
                timeout=60
            )
            
            # Enhanced response logging
            self.logger.debug(f"Response status: {response.status_code}")
            self.logger.debug(f"Response headers: {dict(response.headers)}")
            self.logger.debug(f"Response content length: {len(response.text)} chars")
            
            if response.status_code == 429:
                # Rate limited, wait and retry
                retry_after = int(response.headers.get('Retry-After', 60))
                self.logger.warning(f"Rate limited, waiting {retry_after} seconds")
                time.sleep(retry_after)
                return self.extract_from_chunk(chunk, system_prompt)
            
            # Check for successful status code
            if response.status_code != 200:
                self.logger.error(f"API request failed with status {response.status_code} for {chunk.doc_id}__{chunk.chunk_id}")
                self.logger.error(f"Response text: {response.text}")
                response.raise_for_status()
            
            # Validate response content
            if not response.text:
                # Handle empty response with retry logic
                if retry_count < 2:  # Allow up to 2 retries
                    self.logger.warning(f"Empty response received for {chunk.doc_id}__{chunk.chunk_id}, retrying ({retry_count + 1}/2)")
                    time.sleep(1)  # Small delay before retry
                    return self.extract_from_chunk(chunk, system_prompt, retry_count + 1)
                else:
                    self.logger.error(f"Empty response received for {chunk.doc_id}__{chunk.chunk_id} after {retry_count + 1} attempts")
                    self.logger.error("This suggests API configuration or authentication issues")
                    return None
            
            # Check content type
            content_type = response.headers.get('content-type', '')
            if 'application/json' not in content_type.lower():
                self.logger.warning(f"Unexpected content-type: {content_type} for {chunk.doc_id}__{chunk.chunk_id}")
                self.logger.debug(f"Response text: {response.text}")
            
            # Parse response JSON
            try:
                result = response.json()
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse API response JSON for {chunk.doc_id}__{chunk.chunk_id}: {e}")
                self.logger.error(f"Raw response text: {repr(response.text)}")
                self.logger.error(f"Response length: {len(response.text)} chars")
                return None
            
            # Validate response structure
            if not isinstance(result, dict):
                self.logger.error(f"API response is not a dictionary for {chunk.doc_id}__{chunk.chunk_id}: {type(result)}")
                self.logger.debug(f"Response content: {result}")
                return None
            
            # Extract content from response
            choices = result.get('choices', [])
            if not choices:
                self.logger.error(f"No choices in API response for {chunk.doc_id}__{chunk.chunk_id}")
                self.logger.debug(f"Response structure: {result}")
                return None
            
            message = choices[0].get('message', {})
            content = message.get('content', '')
            
            if not content:
                # Handle known DeepSeek JSON mode issue with empty responses
                if retry_count < 2:  # Allow up to 2 retries
                    self.logger.warning(f"Empty content received for {chunk.doc_id}__{chunk.chunk_id}, retrying ({retry_count + 1}/2)")
                    self.logger.warning("This is a known DeepSeek JSON mode issue - retrying with slight delay")
                    time.sleep(1)  # Small delay before retry
                    return self.extract_from_chunk(chunk, system_prompt, retry_count + 1)
                else:
                    self.logger.error(f"Empty content in API response for {chunk.doc_id}__{chunk.chunk_id} after {retry_count + 1} attempts")
                    self.logger.error("Known DeepSeek issue: JSON mode may occasionally return empty content")
                    self.logger.debug(f"Message structure: {message}")
                    return None
            
            # Parse the nested JSON content
            try:
                extracted_data = json.loads(content)
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse nested JSON content for {chunk.doc_id}__{chunk.chunk_id}: {e}")
                self.logger.error(f"Raw content: {repr(content)}")
                self.logger.error(f"Content length: {len(content)} chars")
                return None
            
            # Convert to ChunkResult
            chunk_result = self._parse_extraction_result(chunk, extracted_data)
            
            self.logger.debug(
                f"Successfully processed {chunk.doc_id}__{chunk.chunk_id}: "
                f"{len(chunk_result.rules)} rules, "
                f"{sum(len(candidates) for candidates in chunk_result.new_candidates.values())} candidates"
            )
            
            return chunk_result
            
        except requests.exceptions.Timeout as e:
            self.logger.error(f"Request timeout for {chunk.doc_id}__{chunk.chunk_id}: {e}")
            self.logger.error("Consider reducing chunk size or increasing timeout")
            return None
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"Connection error for {chunk.doc_id}__{chunk.chunk_id}: {e}")
            self.logger.error("Check internet connection and API endpoint URL")
            return None
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"HTTP error for {chunk.doc_id}__{chunk.chunk_id}: {e}")
            if hasattr(e.response, 'text'):
                self.logger.error(f"Error response: {e.response.text}")
            return None
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request error for {chunk.doc_id}__{chunk.chunk_id}: {e}")
            return None
        except ValueError as e:
            self.logger.error(f"Configuration error for {chunk.doc_id}__{chunk.chunk_id}: {e}")
            self.logger.error("Check your API credentials and configuration")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error processing {chunk.doc_id}__{chunk.chunk_id}: {e}")
            import traceback
            self.logger.debug(f"Full traceback: {traceback.format_exc()}")
            return None
    
    def _parse_extraction_result(self, chunk: TextChunk, data: Dict) -> ChunkResult:
        """Parse API response into ChunkResult."""
        from .models import Rule, Candidate, Condition, Zone
        
        rules = []
        for rule_data in data.get('rules', []):
            try:
                # Parse conditions
                conditions = []
                for cond_data in rule_data.get('conditions', []):
                    condition = Condition(
                        type=cond_data.get('type', ''),
                        value=cond_data.get('value'),
                        from_val=cond_data.get('from'),
                        to_val=cond_data.get('to')
                    )
                    conditions.append(condition)
                
                # Parse zone
                zone = None
                if rule_data.get('zone'):
                    zone_data = rule_data['zone']
                    zone = Zone(
                        zone_typ=zone_data.get('zone_typ', ''),
                        zone_name=zone_data.get('zone_name')
                    )
                
                # Create rule
                rule = Rule(
                    activity=rule_data.get('activity', ''),
                    place=rule_data.get('place', ''),
                    permission=rule_data.get('permission', ''),
                    zone=zone,
                    conditions=conditions,
                    citations=rule_data.get('citations', []),
                    confidence=rule_data.get('confidence', 0.0),
                    normalization_reason=rule_data.get('normalization_reason', '')
                )
                rules.append(rule)
                
            except Exception as e:
                self.logger.warning(f"Failed to parse rule in {chunk.doc_id}__{chunk.chunk_id}: {e}")
                continue
        
        # Parse candidates
        new_candidates = {}
        for category, candidates_data in data.get('new_candidates', {}).items():
            candidates = []
            for cand_data in candidates_data:
                try:
                    candidate = Candidate(
                        key_snake=cand_data.get('key_snake', ''),
                        original=cand_data.get('original', ''),
                        quote=cand_data.get('quote', ''),
                        confidence=cand_data.get('confidence', 0.0),
                        why_new=cand_data.get('why_new', '')
                    )
                    candidates.append(candidate)
                except Exception as e:
                    self.logger.warning(f"Failed to parse candidate in {chunk.doc_id}__{chunk.chunk_id}: {e}")
                    continue
            
            if candidates:
                new_candidates[category] = candidates
        
        return ChunkResult(
            doc_id=chunk.doc_id,
            chunk_id=chunk.chunk_id,
            rules=rules,
            new_candidates=new_candidates
        )


def load_system_prompt() -> str:
    """Load the system prompt and inject known enums."""
    # Load the prompt template
    prompt_file = Path("prompts/extractor_system.txt")
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


def load_chunks_from_jsonl(chunks_file: str) -> List[TextChunk]:
    """Load chunks from JSONL file."""
    chunks = []
    
    with open(chunks_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            try:
                data = json.loads(line.strip())
                chunk = TextChunk.from_dict(data)
                chunks.append(chunk)
            except json.JSONDecodeError as e:
                logging.getLogger("nsgx").warning(f"Failed to parse line {line_num} in {chunks_file}: {e}")
            except Exception as e:
                logging.getLogger("nsgx").warning(f"Failed to create chunk from line {line_num}: {e}")
    
    return chunks


def process_chunk_worker(client: DeepSeekClient, chunk: TextChunk, system_prompt: str, output_dir: str) -> Optional[str]:
    """Process a single chunk (worker function for threading)."""
    logger = logging.getLogger("nsgx")
    
    try:
        # Check if result already exists
        result_file = Path(output_dir) / "chunk_results" / f"{chunk.doc_id}__{chunk.chunk_id}.json"
        
        if result_file.exists():
            logger.debug(f"Result already exists for {chunk.doc_id}__{chunk.chunk_id}")
            return str(result_file)
        
        # Process chunk
        result = client.extract_from_chunk(chunk, system_prompt)
        
        if result:
            # Save result
            result_file.parent.mkdir(parents=True, exist_ok=True)
            save_json_file(result.to_dict(), str(result_file))
            logger.info(f"Saved result for {chunk.doc_id}__{chunk.chunk_id}")
            return str(result_file)
        else:
            logger.error(f"Failed to process {chunk.doc_id}__{chunk.chunk_id}")
            return None
            
    except Exception as e:
        logger.error(f"Worker error for {chunk.doc_id}__{chunk.chunk_id}: {e}")
        return None


def process_chunks_with_deepseek(
    chunks_file: str,
    output_dir: str,
    concurrency: int,
    force: bool,
    logger: logging.Logger
) -> None:
    """Process all chunks with DeepSeek API."""
    logger.info(f"Starting chunk processing with concurrency={concurrency}")
    
    # Load chunks
    chunks = load_chunks_from_jsonl(chunks_file)
    logger.info(f"Loaded {len(chunks)} chunks from {chunks_file}")
    
    if not chunks:
        logger.warning("No chunks to process")
        return
    
    # Load system prompt
    system_prompt = load_system_prompt()
    logger.debug(f"Loaded system prompt: {len(system_prompt)} characters")
    
    # Setup DeepSeek client
    client = DeepSeekClient(
        endpoint=os.getenv('DEEPSEEK_ENDPOINT'),
        model=os.getenv('DEEPSEEK_MODEL'),
        api_key=os.getenv('DEEPSEEK_API_KEY'),
        logger=logger
    )
    
    # Test API connectivity before processing
    if not client.test_connectivity():
        logger.error("API connectivity test failed. Please check your configuration and try again.")
        logger.error("Common issues:")
        logger.error("1. Check your API key in .env file")
        logger.error("2. Verify the endpoint URL is correct")
        logger.error("3. Ensure you have internet connectivity")
        logger.error("4. Check if the API service is available")
        raise RuntimeError("Cannot establish connection to DeepSeek API")
    
    # Filter chunks if not forcing
    if not force:
        chunks_to_process = []
        for chunk in chunks:
            result_file = Path(output_dir) / "chunk_results" / f"{chunk.doc_id}__{chunk.chunk_id}.json"
            if not result_file.exists():
                chunks_to_process.append(chunk)
        
        logger.info(f"Processing {len(chunks_to_process)} new chunks (use --force to reprocess all)")
        chunks = chunks_to_process
    
    if not chunks:
        logger.info("All chunks already processed")
        return
    
    # Process chunks with thread pool
    successful_count = 0
    failed_count = 0
    
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        # Submit all tasks
        future_to_chunk = {
            executor.submit(process_chunk_worker, client, chunk, system_prompt, output_dir): chunk
            for chunk in chunks
        }
        
        # Process results as they complete
        for future in as_completed(future_to_chunk):
            chunk = future_to_chunk[future]
            try:
                result_file = future.result()
                if result_file:
                    successful_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(f"Future exception for {chunk.doc_id}__{chunk.chunk_id}: {e}")
                failed_count += 1
    
    # Save processing summary
    summary = {
        "total_chunks": len(chunks),
        "successful_chunks": successful_count,
        "failed_chunks": failed_count,
        "concurrency": concurrency,
        "system_prompt_length": len(system_prompt)
    }
    
    summary_file = Path(output_dir) / "run_summary.json"
    save_json_file(summary, str(summary_file))
    
    logger.info(
        f"Processing completed: {successful_count} successful, {failed_count} failed, "
        f"summary saved to {summary_file}"
    )