"""Generate candidate proposals and DBML patches."""

import csv
import json
import logging
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

from rapidfuzz import fuzz
from rapidfuzz.process import extract

from .models import DocumentResult, Candidate
from .utils import load_json_file, save_json_file, normalize_string_for_comparison, to_snake_case


class CandidateAnalyzer:
    """Analyzes candidates and generates proposals."""
    
    def __init__(self, known_enums: Dict[str, List[str]], min_doc_count: int, logger: logging.Logger):
        self.known_enums = known_enums
        self.min_doc_count = min_doc_count
        self.logger = logger
        
        # Normalize known enums for comparison
        self.normalized_enums = {}
        for category, values in known_enums.items():
            self.normalized_enums[category] = {
                value: normalize_string_for_comparison(value) 
                for value in values
            }
    
    def analyze_candidates(self, all_candidates: Dict[str, List[Tuple[Candidate, str]]]) -> Dict[str, List[Dict]]:
        """Analyze all candidates and generate decisions."""
        decisions = {}
        
        for category, candidates_with_docs in all_candidates.items():
            self.logger.info(f"Analyzing {len(candidates_with_docs)} candidates in category: {category}")
            decisions[category] = self._analyze_category_candidates(category, candidates_with_docs)
        
        return decisions
    
    def _analyze_category_candidates(self, category: str, candidates_with_docs: List[Tuple[Candidate, str]]) -> List[Dict]:
        """Analyze candidates for a specific category."""
        # Group candidates by key_snake
        by_key = defaultdict(list)
        for candidate, doc_id in candidates_with_docs:
            by_key[candidate.key_snake].append((candidate, doc_id))
        
        decisions = []
        
        for key_snake, candidate_instances in by_key.items():
            # Count unique documents
            doc_count = len(set(doc_id for _, doc_id in candidate_instances))
            
            # Get best candidate (highest confidence)
            best_candidate = max(candidate_instances, key=lambda x: x[0].confidence)[0]
            
            # Collect example quotes
            quotes = [c.quote for c, _ in candidate_instances if c.quote]
            example_quote = quotes[0] if quotes else ""
            
            # Determine decision
            decision_info = self._make_decision(category, best_candidate, doc_count)
            
            decision = {
                "candidate": best_candidate.original,
                "key_snake": key_snake,
                "decision": decision_info["decision"],
                "target_or_key": decision_info.get("target", key_snake),
                "reason": decision_info["reason"],
                "doc_count": doc_count,
                "example_quote": example_quote[:200],  # Limit length
                "confidence": best_candidate.confidence,
                "why_new": getattr(best_candidate, 'why_new', '')
            }
            
            decisions.append(decision)
        
        # Sort by document count (descending) and confidence
        decisions.sort(key=lambda x: (-x["doc_count"], -x["confidence"]))
        
        return decisions
    
    def _make_decision(self, category: str, candidate: Candidate, doc_count: int) -> Dict[str, str]:
        """Make a decision for a single candidate."""
        # Map category to enum key
        enum_key_mapping = {
            "activities": "aktivitaet",
            "zone_terms": "zone_typ",
            "place_terms": "ort"
        }
        
        enum_key = enum_key_mapping.get(category)
        if not enum_key or enum_key not in self.known_enums:
            return {
                "decision": "IGNORE",
                "reason": f"Unknown category: {category}"
            }
        
        known_values = self.known_enums[enum_key]
        
        # Check for exact match
        if candidate.key_snake in known_values:
            return {
                "decision": "MAP_TO_EXISTING",
                "target": candidate.key_snake,
                "reason": "Exact match with existing enum value"
            }
        
        # Check for fuzzy matches
        normalized_candidate = normalize_string_for_comparison(candidate.original)
        
        best_matches = extract(
            normalized_candidate,
            self.normalized_enums[enum_key].values(),
            scorer=fuzz.ratio,
            limit=3
        )
        
        if best_matches and best_matches[0][1] >= 80:  # 80% similarity threshold
            # Find the original enum value
            for orig_value, norm_value in self.normalized_enums[enum_key].items():
                if norm_value == best_matches[0][0]:
                    return {
                        "decision": "MAP_TO_EXISTING",
                        "target": orig_value,
                        "reason": f"High similarity match (score: {best_matches[0][1]})"
                    }
        
        # Check if it could be represented as existing + conditions
        if category == "activities":
            # Apply anti-explosion rules for activities
            if self._can_be_represented_with_conditions(candidate, known_values):
                return {
                    "decision": "MAP_TO_EXISTING",
                    "target": self._suggest_base_activity(candidate, known_values),
                    "reason": "Can be represented as existing activity + conditions"
                }
        
        # Check document frequency requirement
        if doc_count < self.min_doc_count:
            return {
                "decision": "IGNORE",
                "reason": f"Insufficient document frequency ({doc_count} < {self.min_doc_count})"
            }
        
        # Default to ADD_NEW if it passes all checks
        return {
            "decision": "ADD_NEW",
            "reason": f"Genuinely new term, appears in {doc_count} documents"
        }
    
    def _can_be_represented_with_conditions(self, candidate: Candidate, known_activities: List[str]) -> bool:
        """Check if activity can be represented with existing activity + conditions."""
        text = candidate.original.lower()
        
        # Check for qualifiers that should be conditions
        qualifier_patterns = [
            "elektrisch", "motor", "ps", "kw", "lang", "breit", "meter", "m",
            "personen", "gruppe", "winter", "sommer", "nacht", "tag",
            "schnell", "langsam", "groß", "klein", "leise", "laut"
        ]
        
        has_qualifiers = any(pattern in text for pattern in qualifier_patterns)
        
        if has_qualifiers:
            # Check if base activity exists
            for activity in known_activities:
                if activity in text or any(part in activity for part in text.split()):
                    return True
        
        return False
    
    def _suggest_base_activity(self, candidate: Candidate, known_activities: List[str]) -> str:
        """Suggest base activity for candidates with qualifiers."""
        text = candidate.original.lower()
        
        # Try to find best matching base activity
        best_match = extract(
            text,
            known_activities,
            scorer=fuzz.partial_ratio,
            limit=1
        )
        
        if best_match and best_match[0][1] >= 60:
            return best_match[0][0]
        
        # Fallback suggestions based on keywords
        if any(water_word in text for water_word in ["boot", "schiff", "paddle", "ruder", "motor"]):
            if "motor" in text:
                return "wasserfahrzeuge_motorisiert"
            else:
                return "wasserfahrzeuge_ohne_motor"
        
        if any(air_word in text for air_word in ["fliegen", "luft", "drohne", "ballon"]):
            return "drohnen_flugmodelle"
        
        # Default fallback
        return known_activities[0] if known_activities else "unknown"


def load_document_results(docs_dir: str, logger: logging.Logger) -> List[DocumentResult]:
    """Load all document results."""
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        raise FileNotFoundError(f"Documents directory not found: {docs_dir}")
    
    doc_files = list(docs_path.glob("*.json"))
    logger.info(f"Found {len(doc_files)} document result files")
    
    documents = []
    for doc_file in doc_files:
        try:
            with open(doc_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            doc_result = DocumentResult.from_dict(data)
            documents.append(doc_result)
            
        except Exception as e:
            logger.warning(f"Failed to load document result {doc_file}: {e}")
    
    logger.info(f"Loaded {len(documents)} document results")
    return documents


def collect_all_candidates(documents: List[DocumentResult]) -> Dict[str, List[Tuple[Candidate, str]]]:
    """Collect all candidates with their source document IDs."""
    all_candidates = defaultdict(list)
    
    for doc in documents:
        for category, candidates in doc.new_candidates.items():
            for candidate in candidates:
                all_candidates[category].append((candidate, doc.doc_id))
    
    return dict(all_candidates)


def generate_review_csv(decisions: Dict[str, List[Dict]], output_file: str, logger: logging.Logger) -> None:
    """Generate candidates review CSV file."""
    logger.info(f"Generating review CSV: {output_file}")
    
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'category', 'candidate', 'decision', 'target_or_key', 'reason', 
            'doc_count', 'example_quote', 'confidence', 'why_new'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        total_candidates = 0
        for category, category_decisions in decisions.items():
            for decision in category_decisions:
                writer.writerow({
                    'category': category,
                    **decision
                })
                total_candidates += 1
        
        logger.info(f"Written {total_candidates} candidates to review CSV")


def generate_dbml_patches(decisions: Dict[str, List[Dict]], output_dir: str, logger: logging.Logger) -> None:
    """Generate DBML enum addition patches."""
    logger.info("Generating DBML patches")
    
    # Collect new enum values to add
    enum_additions = defaultdict(list)
    
    category_to_enum = {
        "activities": "aktivitaet_enum",
        "zone_terms": "zone_typ_enum", 
        "place_terms": "ort_enum"
    }
    
    for category, category_decisions in decisions.items():
        enum_name = category_to_enum.get(category)
        if not enum_name:
            continue
        
        for decision in category_decisions:
            if decision["decision"] == "ADD_NEW":
                enum_additions[enum_name].append(decision["target_or_key"])
    
    # Generate DBML content
    dbml_content = "// Generated DBML enum additions\n"
    dbml_content += f"// Generated on: {datetime.now().isoformat()}\n\n"
    
    if not enum_additions:
        dbml_content += "// No new enum values to add\n"
    else:
        for enum_name, new_values in enum_additions.items():
            dbml_content += f"// Add to {enum_name}:\n"
            for value in sorted(new_values):
                dbml_content += f"//   {value}\n"
            dbml_content += "\n"
            
            # Generate the actual enum extension
            dbml_content += f"Enum {enum_name} {{\n"
            for value in sorted(new_values):
                dbml_content += f"  {value}\n"
            dbml_content += "}\n\n"
    
    # Save DBML file
    output_path = Path(output_dir) / "dbml_patches"
    output_path.mkdir(parents=True, exist_ok=True)
    
    dbml_file = output_path / "enum_additions.dbml"
    with open(dbml_file, 'w', encoding='utf-8') as f:
        f.write(dbml_content)
    
    logger.info(f"Generated DBML patches: {dbml_file}")


def generate_changelog(decisions: Dict[str, List[Dict]], output_file: str, logger: logging.Logger) -> None:
    """Generate changelog for new additions."""
    logger.info(f"Generating changelog: {output_file}")
    
    # Collect new additions
    new_additions = []
    for category, category_decisions in decisions.items():
        for decision in category_decisions:
            if decision["decision"] == "ADD_NEW":
                new_additions.append((category, decision))
    
    # Generate changelog content
    content = "# NSG Data Model Changes\n\n"
    content += f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    if not new_additions:
        content += "## No new enum values added\n\n"
        content += "All candidates were either mapped to existing values or ignored.\n"
    else:
        content += f"## New Enum Values ({len(new_additions)} additions)\n\n"
        
        by_category = defaultdict(list)
        for category, decision in new_additions:
            by_category[category].append(decision)
        
        for category, additions in by_category.items():
            content += f"### {category.replace('_', ' ').title()}\n\n"
            
            for decision in sorted(additions, key=lambda x: x["target_or_key"]):
                content += f"**{decision['target_or_key']}**\n"
                content += f"- Original term: {decision['candidate']}\n"
                content += f"- Found in {decision['doc_count']} documents\n"
                content += f"- Example: \"{decision['example_quote'][:100]}...\"\n"
                if decision.get('why_new'):
                    content += f"- Rationale: {decision['why_new']}\n"
                content += "\n"
    
    # Statistics section
    total_candidates = sum(len(decisions[cat]) for cat in decisions)
    mapped_count = sum(1 for cat in decisions.values() for dec in cat if dec["decision"] == "MAP_TO_EXISTING")
    ignored_count = sum(1 for cat in decisions.values() for dec in cat if dec["decision"] == "IGNORE")
    
    content += "## Summary Statistics\n\n"
    content += f"- Total candidates analyzed: {total_candidates}\n"
    content += f"- New enum values added: {len(new_additions)}\n"
    content += f"- Mapped to existing values: {mapped_count}\n"
    content += f"- Ignored (low frequency/quality): {ignored_count}\n"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info(f"Generated changelog with {len(new_additions)} new additions")


def generate_model_update_proposal(decisions: Dict[str, List[Dict]], output_file: str, logger: logging.Logger) -> None:
    """Generate model update proposal document."""
    logger.info(f"Generating model update proposal: {output_file}")
    
    new_count = sum(1 for cat in decisions.values() for dec in cat if dec["decision"] == "ADD_NEW")
    high_confidence_count = sum(1 for cat in decisions.values() for dec in cat 
                               if dec["decision"] == "ADD_NEW" and dec["confidence"] > 0.7)
    
    content = "# NSG Data Model Update Proposal\n\n"
    content += f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    content += "## Executive Summary\n\n"
    content += f"This proposal suggests adding {new_count} new enum values to the NSG data model "
    content += "based on automated extraction and analysis of regulation documents.\n\n"
    
    if high_confidence_count > 0:
        content += f"**High Priority**: {high_confidence_count} candidates have confidence > 0.7 "
        content += "and should be reviewed first.\n\n"
    
    content += "## Methodology\n\n"
    content += "1. **Text Extraction**: PDFs processed with multiple extraction methods\n"
    content += "2. **AI Analysis**: DeepSeek API used for rule extraction with conservative prompts\n"
    content += "3. **Anti-Explosion Policy**: Qualifiers mapped to conditions, not new activities\n"
    content += "4. **Frequency Filtering**: Only terms appearing in ≥5 documents considered\n"
    content += "5. **Similarity Matching**: Fuzzy matching used to avoid duplicates\n\n"
    
    content += "## Rationale\n\n"
    content += "The existing enum values may not cover all activities, zones, and places "
    content += "mentioned in current NSG regulations. This analysis identifies genuinely new "
    content += "concepts that cannot be represented with existing values plus conditions.\n\n"
    
    content += "## Quality Assurance\n\n"
    content += "- All candidates include source document references\n"
    content += "- Examples quotes provided for context\n"
    content += "- Confidence scores from AI extraction included\n"
    content += "- Manual review required before implementation\n\n"
    
    content += "## Next Steps\n\n"
    content += "1. Review `review/candidates_review.csv` for detailed analysis\n"
    content += "2. Validate high-confidence candidates first\n"
    content += "3. Check example quotes for context and accuracy\n"
    content += "4. Apply `dbml_patches/enum_additions.dbml` to data model\n"
    content += "5. Update application code to handle new enum values\n"
    content += "6. Test with affected NSG documents\n\n"
    
    content += "## Open Issues\n\n"
    content += "- Some candidates may need manual verification\n"
    content += "- Synonym detection could be improved\n"
    content += "- Regional variations in terminology may exist\n"
    content += "- Cross-references between documents not analyzed\n"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info("Generated model update proposal")


def generate_proposals(
    docs_dir: str,
    output_dir: str,
    min_doc_count: int,
    force: bool,
    logger: logging.Logger
) -> None:
    """Generate all proposals and DBML patches."""
    logger.info(f"Starting proposal generation: min_doc_count={min_doc_count}")
    
    # Load known enums
    known_enums = load_json_file("prompts/known_enums.json")
    logger.info(f"Loaded known enums for {len(known_enums)} categories")
    
    # Load document results
    documents = load_document_results(docs_dir, logger)
    
    if not documents:
        logger.warning("No documents found for proposal generation")
        return
    
    # Collect all candidates
    all_candidates = collect_all_candidates(documents)
    total_candidates = sum(len(candidates) for candidates in all_candidates.values())
    logger.info(f"Collected {total_candidates} candidates across {len(all_candidates)} categories")
    
    # Analyze candidates
    analyzer = CandidateAnalyzer(known_enums, min_doc_count, logger)
    decisions = analyzer.analyze_candidates(all_candidates)
    
    # Create output directories
    output_path = Path(output_dir)
    review_dir = output_path / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate outputs
    try:
        # Review CSV
        review_csv = review_dir / "candidates_review.csv"
        if force or not review_csv.exists():
            generate_review_csv(decisions, str(review_csv), logger)
        
        # DBML patches
        if force or not (output_path / "dbml_patches" / "enum_additions.dbml").exists():
            generate_dbml_patches(decisions, str(output_path), logger)
        
        # Changelog
        changelog_file = output_path / "CHANGELOG.md"
        if force or not changelog_file.exists():
            generate_changelog(decisions, str(changelog_file), logger)
        
        # Model update proposal
        proposal_file = output_path / "model_update_proposal.md"
        if force or not proposal_file.exists():
            generate_model_update_proposal(decisions, str(proposal_file), logger)
        
        # Generate summary
        summary = {
            "total_documents": len(documents),
            "total_candidates": total_candidates,
            "decisions_summary": {
                category: {
                    "total": len(cat_decisions),
                    "add_new": len([d for d in cat_decisions if d["decision"] == "ADD_NEW"]),
                    "map_existing": len([d for d in cat_decisions if d["decision"] == "MAP_TO_EXISTING"]),
                    "ignore": len([d for d in cat_decisions if d["decision"] == "IGNORE"])
                }
                for category, cat_decisions in decisions.items()
            },
            "min_doc_count": min_doc_count
        }
        
        summary_file = output_path / "propose_summary.json"
        save_json_file(summary, str(summary_file))
        
        logger.info(f"Proposal generation completed successfully, summary saved to {summary_file}")
        
    except Exception as e:
        logger.error(f"Failed to generate proposals: {e}")
        raise