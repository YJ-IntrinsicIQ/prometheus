from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from knowledge.company_memory.company_layer import _normalize_text


PACK_FILES = (
    "archetype.json",
    "vocabulary.json",
    "themes.json",
    "risks.json",
    "metrics.json",
    "capital_allocation.json",
    "investor_questions.json",
)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _slug(value: Any) -> str:
    normalized = _normalize_text(value)
    return normalized.replace(" ", "_") or "unclassified_theme"


def _stringify(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(_stringify(item) for item in value if _stringify(item))
    if isinstance(value, dict):
        return " ".join(_stringify(item) for item in value.values() if _stringify(item))
    return str(value)


class ArchetypeRegistry:
    def __init__(
        self,
        *,
        company: str,
        business_dnas: Iterable[str],
        company_root: Path | str,
        registry_root: Optional[Path | str] = None,
    ) -> None:
        self.company = company
        self.business_dnas = list(dict.fromkeys(str(dna) for dna in business_dnas if dna))
        self.company_root = Path(company_root)
        if registry_root is None:
            registry_root = Path(__file__).resolve().parent
        self.registry_root = Path(registry_root)
        self.registry_config = _load_json(self.registry_root / "registry.json")
        self.loaded_pack_ids: List[str] = []
        self.loaded_archetypes: List[Dict[str, Any]] = []
        self.theme_entries: List[Dict[str, Any]] = []
        self.risk_entries: List[Dict[str, Any]] = []
        self.capital_entries: List[Dict[str, Any]] = []
        self.metric_entries: List[Dict[str, Any]] = []
        self.question_entries: List[Dict[str, Any]] = []
        self.vocabulary_entries: Dict[str, Dict[str, Any]] = {}
        self.review_candidates: List[Dict[str, Any]] = []
        self._review_keys: set[tuple[str, str, str, str]] = set()
        self._load()

    def _normalize_match_text(self, *parts: Any) -> str:
        return _normalize_text(" ".join(part for part in (_stringify(value) for value in parts) if part))

    def _entry_priority(self, entry: Dict[str, Any]) -> int:
        try:
            return int(entry.get("priority", 0))
        except (TypeError, ValueError):
            return 0

    def _keyword_match(
        self,
        entries: Sequence[Dict[str, Any]],
        text: str,
        key_name: str,
    ) -> Optional[Dict[str, Any]]:
        best_entry: Optional[Dict[str, Any]] = None
        best_priority = -1
        best_length = -1
        for entry in entries:
            priority = self._entry_priority(entry)
            for keyword in entry.get("keywords", []):
                keyword_normalized = _normalize_text(keyword)
                if keyword_normalized and keyword_normalized in text:
                    if priority > best_priority or (priority == best_priority and len(keyword_normalized) > best_length):
                        best_entry = entry
                        best_priority = priority
                        best_length = len(keyword_normalized)
        if best_entry is not None:
            return {
                "entry": best_entry,
                "priority": best_priority,
                "keyword_length": best_length,
            }
        return None

    def _pack_dir(self, pack_id: str) -> Path:
        return self.registry_root / pack_id

    def _pack_config(self, pack_id: str) -> Dict[str, Any]:
        pack_dir = self._pack_dir(pack_id)
        payload = {}
        for filename in PACK_FILES:
            payload[filename] = _load_json(pack_dir / filename)
        return payload

    def _merge_by_key(self, items: Iterable[Dict[str, Any]], key_name: str) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        for item in items:
            if key_name not in item:
                continue
            key = str(item[key_name])
            if key not in merged:
                merged[key] = dict(item)
                order.append(key)
                continue
            current = merged[key]
            for field, value in item.items():
                if field not in current or current[field] in (None, "", [], {}):
                    current[field] = value
                elif isinstance(current[field], list) and isinstance(value, list):
                    current[field] = list(dict.fromkeys(current[field] + value))
        return [merged[key] for key in order]

    def _resolve_pack_ids(self) -> List[str]:
        mapping = self.registry_config.get("business_dna_to_packs", {})
        pack_ids = ["universal"]
        for dna in self.business_dnas:
            for pack_id in mapping.get(dna, []):
                if pack_id not in pack_ids:
                    pack_ids.append(pack_id)
        return pack_ids

    def _load(self) -> None:
        pack_ids = self._resolve_pack_ids()
        all_themes: List[Dict[str, Any]] = []
        all_risks: List[Dict[str, Any]] = []
        all_capital: List[Dict[str, Any]] = []
        all_metrics: List[Dict[str, Any]] = []
        all_questions: List[Dict[str, Any]] = []

        for pack_id in pack_ids:
            config = self._pack_config(pack_id)
            self.loaded_pack_ids.append(pack_id)
            archetype = config["archetype.json"] or {
                "archetype_id": pack_id,
                "display_name": pack_id.replace("_", " ").title(),
                "version": "1.0",
            }
            self.loaded_archetypes.append(archetype)
            self.vocabulary_entries[pack_id] = config["vocabulary.json"] or {}
            all_themes.extend(config["themes.json"].get("themes", []))
            all_risks.extend(config["risks.json"].get("risks", []))
            all_capital.extend(config["capital_allocation.json"].get("categories", []))
            all_metrics.extend(config["metrics.json"].get("metrics", []))
            all_questions.extend(config["investor_questions.json"].get("questions", []))

        self.theme_entries = self._merge_by_key(all_themes, "canonical_theme")
        self.risk_entries = self._merge_by_key(all_risks, "canonical_risk")
        self.capital_entries = self._merge_by_key(all_capital, "category")
        self.metric_entries = self._merge_by_key(all_metrics, "metric_name")
        self.question_entries = self._merge_by_key(all_questions, "question_id")

    def normalize_theme(
        self,
        label: Any,
        *,
        category: Any = None,
        status: Any = None,
        source_year: Optional[str] = None,
        source_artifact: Optional[str] = None,
        source_item_id: Optional[str] = None,
        evidence_ids: Optional[Iterable[str]] = None,
        evidence_category: Any = None,
    ) -> Dict[str, Any]:
        normalized = self._normalize_match_text(label, category, status, source_artifact, evidence_category)
        match = self._keyword_match(self.theme_entries, normalized, "canonical_theme")
        if match is not None:
            best_match = match["entry"]
            return {
                "canonical_theme": best_match["canonical_theme"],
                "theme_group": best_match.get("theme_group", "other"),
                "needs_taxonomy_review": False,
            }

        suggestion = self._suggest_archetype(" ".join(part for part in (_stringify(label), _stringify(category), _stringify(evidence_category)) if part))
        candidate = {
            "raw_label": str(label or ""),
            "normalized_slug": _slug(label),
            "source_year": source_year,
            "source_artifact": source_artifact,
            "source_item_id": source_item_id,
            "evidence_ids": list(evidence_ids or []),
            "reason": "No loaded archetype theme matched this label.",
            "suggested_archetype_if_any": suggestion,
        }
        key = (
            candidate["raw_label"],
            candidate["source_year"] or "",
            candidate["source_artifact"] or "",
            candidate["source_item_id"] or "",
        )
        if key not in self._review_keys:
            self.review_candidates.append(candidate)
            self._review_keys.add(key)
        return {
            "canonical_theme": "unclassified_theme",
            "theme_group": "unknown",
            "candidate_label": str(label or ""),
            "needs_taxonomy_review": True,
        }

    def normalize_risk(
        self,
        label: Any,
        category: Any = None,
        *,
        severity: Any = None,
        evidence_category: Any = None,
        short_excerpt: Any = None,
    ) -> str:
        normalized = self._normalize_match_text(label, category, severity, evidence_category, short_excerpt)
        match = self._keyword_match(self.risk_entries, normalized, "canonical_risk")
        return str(match["entry"]["canonical_risk"]) if match is not None else _slug(label)

    def classify_capital_allocation(
        self,
        value: Any,
        *,
        category: Any = None,
        status: Any = None,
        purpose: Any = None,
        amount: Any = None,
        counterparty: Any = None,
        relationship: Any = None,
        evidence_category: Any = None,
    ) -> List[str]:
        normalized = self._normalize_match_text(
            value,
            category,
            status,
            purpose,
            amount,
            counterparty,
            relationship,
            evidence_category,
        )
        matches: List[tuple[int, str]] = []
        for entry in self.capital_entries:
            priority = self._entry_priority(entry)
            for keyword in entry.get("keywords", []):
                keyword_normalized = _normalize_text(keyword)
                if keyword_normalized and keyword_normalized in normalized:
                    matches.append((priority, len(keyword_normalized), str(entry["category"])))
        categories: List[str] = []
        for _, _, category in sorted(matches, key=lambda item: (-item[0], -item[1], item[2])):
            if category not in categories:
                categories.append(category)
        return categories

    def get_relevant_metrics(self) -> List[Dict[str, Any]]:
        return list(self.metric_entries)

    def get_investor_questions(self) -> List[Dict[str, Any]]:
        return list(self.question_entries)

    def get_loaded_archetypes(self) -> List[Dict[str, Any]]:
        return list(self.loaded_archetypes)

    def get_loaded_pack_ids(self) -> List[str]:
        return list(self.loaded_pack_ids)

    def get_review_candidates(self) -> List[Dict[str, Any]]:
        return list(self.review_candidates)

    def _suggest_archetype(self, label: Any) -> Optional[str]:
        normalized = _normalize_text(label)
        best_pack: Optional[str] = None
        best_length = -1
        for pack_id, vocab in self.vocabulary_entries.items():
            for section in ("core_terms", "synonyms", "product_terms", "operating_terms", "financial_terms"):
                for term in vocab.get(section, []):
                    term_normalized = _normalize_text(term)
                    if term_normalized and term_normalized in normalized and len(term_normalized) > best_length:
                        best_pack = pack_id
                        best_length = len(term_normalized)
        return best_pack
