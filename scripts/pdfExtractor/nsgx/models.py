"""Data models for NSG extraction."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union
import json


@dataclass
class Condition:
    """Represents a condition in a rule."""
    type: str
    value: Optional[Union[str, int, float]] = None
    from_val: Optional[str] = None  # for ranges like datumspanne, tageszeit
    to_val: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"type": self.type}
        if self.value is not None:
            result["value"] = self.value
        if self.from_val is not None:
            result["from"] = self.from_val
        if self.to_val is not None:
            result["to"] = self.to_val
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Condition":
        return cls(
            type=data["type"],
            value=data.get("value"),
            from_val=data.get("from"),
            to_val=data.get("to")
        )


@dataclass
class Zone:
    """Represents a zone in a rule."""
    zone_typ: str
    zone_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "zone_typ": self.zone_typ,
            "zone_name": self.zone_name
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Zone":
        return cls(
            zone_typ=data["zone_typ"],
            zone_name=data.get("zone_name")
        )


@dataclass
class Rule:
    """Represents an extracted rule."""
    activity: str
    place: str
    permission: str
    zone: Optional[Zone] = None
    conditions: List[Condition] = field(default_factory=list)
    citations: List[str] = field(default_factory=list)
    confidence: float = 0.0
    normalization_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "activity": self.activity,
            "place": self.place,
            "permission": self.permission,
            "zone": self.zone.to_dict() if self.zone else None,
            "conditions": [c.to_dict() for c in self.conditions],
            "citations": self.citations,
            "confidence": self.confidence,
            "normalization_reason": self.normalization_reason
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Rule":
        zone = Zone.from_dict(data["zone"]) if data.get("zone") else None
        conditions = [Condition.from_dict(c) for c in data.get("conditions", [])]
        return cls(
            activity=data["activity"],
            place=data["place"],
            permission=data["permission"],
            zone=zone,
            conditions=conditions,
            citations=data.get("citations", []),
            confidence=data.get("confidence", 0.0),
            normalization_reason=data.get("normalization_reason", "")
        )

    def is_equivalent(self, other: "Rule") -> bool:
        """Check if two rules are equivalent (same activity, place, permission, zone)."""
        return (
            self.activity == other.activity and
            self.place == other.place and
            self.permission == other.permission and
            self.zone == other.zone
        )


@dataclass
class Candidate:
    """Represents a candidate for new enum values."""
    key_snake: str
    original: str
    quote: str
    confidence: float = 0.0
    why_new: str = ""  # for activities

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "key_snake": self.key_snake,
            "original": self.original,
            "quote": self.quote,
            "confidence": self.confidence
        }
        if self.why_new:
            result["why_new"] = self.why_new
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Candidate":
        return cls(
            key_snake=data["key_snake"],
            original=data["original"],
            quote=data["quote"],
            confidence=data.get("confidence", 0.0),
            why_new=data.get("why_new", "")
        )


@dataclass
class ChunkResult:
    """Represents the result of processing a text chunk."""
    doc_id: str
    chunk_id: str
    rules: List[Rule] = field(default_factory=list)
    new_candidates: Dict[str, List[Candidate]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "rules": [r.to_dict() for r in self.rules],
            "new_candidates": {
                k: [c.to_dict() for c in v] 
                for k, v in self.new_candidates.items()
            }
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChunkResult":
        rules = [Rule.from_dict(r) for r in data.get("rules", [])]
        candidates = {}
        for k, v in data.get("new_candidates", {}).items():
            candidates[k] = [Candidate.from_dict(c) for c in v]
        
        return cls(
            doc_id=data["doc_id"],
            chunk_id=data["chunk_id"],
            rules=rules,
            new_candidates=candidates
        )


@dataclass
class DocumentResult:
    """Represents the merged result for a document."""
    doc_id: str
    rules_merged: List[Rule] = field(default_factory=list)
    new_candidates: Dict[str, List[Candidate]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "rules_merged": [r.to_dict() for r in self.rules_merged],
            "new_candidates": {
                k: [c.to_dict() for c in v] 
                for k, v in self.new_candidates.items()
            }
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentResult":
        rules = [Rule.from_dict(r) for r in data.get("rules_merged", [])]
        candidates = {}
        for k, v in data.get("new_candidates", {}).items():
            candidates[k] = [Candidate.from_dict(c) for c in v]
        
        return cls(
            doc_id=data["doc_id"],
            rules_merged=rules,
            new_candidates=candidates
        )


@dataclass
class TextChunk:
    """Represents a text chunk for processing."""
    doc_id: str
    chunk_id: str
    text: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "chunk_id": self.chunk_id,
            "text": self.text
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TextChunk":
        return cls(
            doc_id=data["doc_id"],
            chunk_id=data["chunk_id"],
            text=data["text"]
        )