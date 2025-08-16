"""Merge chunk results into document-level results."""

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from .models import ChunkResult, DocumentResult, Rule, Candidate
from .utils import save_json_file, merge_conditions


def load_chunk_results(input_dir: str, logger: logging.Logger) -> Dict[str, List[ChunkResult]]:
    """Load all chunk results grouped by document ID."""
    results_by_doc = defaultdict(list)
    input_path = Path(input_dir)
    
    if not input_path.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    
    chunk_files = list(input_path.glob("*.json"))
    logger.info(f"Found {len(chunk_files)} chunk result files")
    
    for chunk_file in chunk_files:
        try:
            with open(chunk_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            chunk_result = ChunkResult.from_dict(data)
            results_by_doc[chunk_result.doc_id].append(chunk_result)
            
        except Exception as e:
            logger.warning(f"Failed to load chunk result {chunk_file}: {e}")
            continue
    
    logger.info(f"Loaded results for {len(results_by_doc)} documents")
    return dict(results_by_doc)


def merge_rules(rules: List[Rule], logger: logging.Logger) -> List[Rule]:
    """Merge equivalent rules, combining their conditions."""
    if not rules:
        return []
    
    # Group rules by equivalence key (activity, place, permission, zone)
    rule_groups = defaultdict(list)
    
    for rule in rules:
        # Create a key for grouping equivalent rules
        zone_key = None
        if rule.zone:
            zone_key = (rule.zone.zone_typ, rule.zone.zone_name)
        
        key = (rule.activity, rule.place, rule.permission, zone_key)
        rule_groups[key].append(rule)
    
    merged_rules = []
    
    for group_rules in rule_groups.values():
        if len(group_rules) == 1:
            # Single rule, no merging needed
            merged_rules.append(group_rules[0])
        else:
            # Merge multiple rules
            base_rule = group_rules[0]
            
            # Collect all conditions
            all_conditions = [rule.conditions for rule in group_rules]
            merged_conditions_data = merge_conditions(
                [[c.to_dict() for c in conds] for conds in all_conditions]
            )
            
            # Convert back to Condition objects
            from .models import Condition
            merged_conditions = [Condition.from_dict(cond) for cond in merged_conditions_data]
            
            # Collect all citations (deduplicated)
            all_citations = set()
            for rule in group_rules:
                all_citations.update(rule.citations)
            
            # Use highest confidence
            max_confidence = max(rule.confidence for rule in group_rules)
            
            # Combine normalization reasons
            reasons = [rule.normalization_reason for rule in group_rules if rule.normalization_reason]
            combined_reason = "; ".join(set(reasons)) if reasons else base_rule.normalization_reason
            
            # Create merged rule
            merged_rule = Rule(
                activity=base_rule.activity,
                place=base_rule.place,
                permission=base_rule.permission,
                zone=base_rule.zone,
                conditions=merged_conditions,
                citations=sorted(list(all_citations)),
                confidence=max_confidence,
                normalization_reason=combined_reason
            )
            
            merged_rules.append(merged_rule)
            
            logger.debug(f"Merged {len(group_rules)} rules for {base_rule.activity}/{base_rule.place}")
    
    return merged_rules


def merge_candidates(candidates_lists: List[Dict[str, List[Candidate]]], logger: logging.Logger) -> Dict[str, List[Candidate]]:
    """Merge candidate lists from multiple chunks."""
    merged_candidates = defaultdict(list)
    
    for candidates_dict in candidates_lists:
        for category, candidates in candidates_dict.items():
            merged_candidates[category].extend(candidates)
    
    # Deduplicate candidates within each category
    final_candidates = {}
    
    for category, candidates in merged_candidates.items():
        if not candidates:
            continue
        
        # Group by key_snake to deduplicate
        by_key = defaultdict(list)
        for candidate in candidates:
            by_key[candidate.key_snake].append(candidate)
        
        deduped_candidates = []
        for key, cand_group in by_key.items():
            if len(cand_group) == 1:
                deduped_candidates.append(cand_group[0])
            else:
                # Merge candidates with same key
                base_candidate = cand_group[0]
                
                # Collect all quotes
                all_quotes = [c.quote for c in cand_group if c.quote]
                combined_quote = "; ".join(set(all_quotes)) if all_quotes else base_candidate.quote
                
                # Use highest confidence
                max_confidence = max(c.confidence for c in cand_group)
                
                # Combine why_new explanations
                why_new_parts = [c.why_new for c in cand_group if c.why_new]
                combined_why_new = "; ".join(set(why_new_parts)) if why_new_parts else base_candidate.why_new
                
                merged_candidate = Candidate(
                    key_snake=base_candidate.key_snake,
                    original=base_candidate.original,
                    quote=combined_quote[:500],  # Limit quote length
                    confidence=max_confidence,
                    why_new=combined_why_new
                )
                
                deduped_candidates.append(merged_candidate)
        
        final_candidates[category] = deduped_candidates
        logger.debug(f"Category {category}: {len(deduped_candidates)} unique candidates")
    
    return final_candidates


def merge_document_chunks(doc_id: str, chunk_results: List[ChunkResult], logger: logging.Logger) -> DocumentResult:
    """Merge all chunk results for a single document."""
    logger.info(f"Merging {len(chunk_results)} chunks for document {doc_id}")
    
    # Collect all rules
    all_rules = []
    for chunk_result in chunk_results:
        all_rules.extend(chunk_result.rules)
    
    logger.debug(f"Document {doc_id}: {len(all_rules)} total rules before merging")
    
    # Merge equivalent rules
    merged_rules = merge_rules(all_rules, logger)
    logger.info(f"Document {doc_id}: {len(merged_rules)} rules after merging")
    
    # Collect and merge candidates
    all_candidates = [chunk_result.new_candidates for chunk_result in chunk_results]
    merged_candidates = merge_candidates(all_candidates, logger)
    
    total_candidates = sum(len(candidates) for candidates in merged_candidates.values())
    logger.info(f"Document {doc_id}: {total_candidates} unique candidates")
    
    return DocumentResult(
        doc_id=doc_id,
        rules_merged=merged_rules,
        new_candidates=merged_candidates
    )


def merge_chunk_results(
    input_dir: str,
    output_dir: str,
    force: bool,
    logger: logging.Logger
) -> None:
    """Merge all chunk results into document-level results."""
    logger.info(f"Starting merge process: {input_dir} -> {output_dir}")
    
    # Load chunk results
    results_by_doc = load_chunk_results(input_dir, logger)
    
    if not results_by_doc:
        logger.warning("No chunk results found to merge")
        return
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Process each document
    successful_docs = 0
    failed_docs = 0
    
    for doc_id, chunk_results in results_by_doc.items():
        try:
            # Check if already exists
            doc_file = output_path / f"{doc_id}.json"
            if doc_file.exists() and not force:
                logger.debug(f"Document result already exists: {doc_id}")
                successful_docs += 1
                continue
            
            # Merge chunks for this document
            doc_result = merge_document_chunks(doc_id, chunk_results, logger)
            
            # Save result
            save_json_file(doc_result.to_dict(), str(doc_file))
            successful_docs += 1
            
            logger.info(f"Merged document {doc_id}: {len(doc_result.rules_merged)} rules")
            
        except Exception as e:
            logger.error(f"Failed to merge document {doc_id}: {e}")
            failed_docs += 1
    
    # Save merge summary
    summary = {
        "total_documents": len(results_by_doc),
        "successful_documents": successful_docs,
        "failed_documents": failed_docs,
        "output_directory": str(output_path)
    }
    
    summary_file = output_path / "merge_summary.json"
    save_json_file(summary, str(summary_file))
    
    logger.info(
        f"Merge completed: {successful_docs} successful, {failed_docs} failed, "
        f"summary saved to {summary_file}"
    )