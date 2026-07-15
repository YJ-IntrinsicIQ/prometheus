from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from knowledge.business_blueprint import BusinessBlueprint
from knowledge.company_memory import CompanyMemory

from .constants import DEFAULT_DISCOVERY_PROFILE, DEFAULT_EXTRACTION_PROFILE, SUPPORTED_TEMPLATES
from .registry import ArchetypeDefinition, Registry
from .semantic import SemanticSimilarityResult, compute_similarity_scores
from .validator import validate_classification


@dataclass(frozen=True)
class CandidateAssessment:
    archetype: ArchetypeDefinition
    raw_score: float
    normalized_score: float
    confidence: float
    margin_to_next: float
    ambiguity_flag: bool
    selected: bool
    rejected_reason: Optional[str]
    score_breakdown: Dict[str, Any]


class BusinessClassifier:
    STRONG_GROUP_WEIGHT = 4.0
    SUPPORTING_GROUP_WEIGHT = 3.0
    POSITIVE_SIGNAL_WEIGHT = 2.0
    EVIDENCE_PATTERN_WEIGHT = 2.0
    DEFINITION_OVERLAP_WEIGHT = 1.5
    NEGATIVE_SIGNAL_PENALTY = 3.5
    CONFLICT_PENALTY = 2.5
    SEMANTIC_SIMILARITY_WEIGHT = 3.0
    SEMANTIC_SIMILARITY_FLOOR = 0.28
    SEMANTIC_SIMILARITY_MAX_BOOST = 2.25
    MIN_CANDIDATE_SCORE = 4.0
    MAX_CANDIDATES_DEFAULT = 3
    MAX_CANDIDATES_AMBIGUOUS = 5
    AMBIGUITY_MARGIN = 1.75
    SCORE_MARGIN_FOR_SELECTION = 5.0

    def __init__(self, registry: Registry | None = None):
        self.registry = registry or Registry()

    def build_candidate_context(
        self,
        company_memory: CompanyMemory,
        *,
        company: Optional[str] = None,
        year: Optional[str] = None,
        max_candidates: int = 5,
        max_evidence: int = 8,
    ) -> Dict[str, Any]:
        evidence_snippets = self._build_evidence_snippets(
            company_memory,
            limit=max_evidence,
        )
        candidate_pack = self._build_ranked_candidate_pack(
            evidence_snippets=evidence_snippets,
            max_candidates=max_candidates,
        )
        return {
            "company": company or company_memory.company_id,
            "year": year,
            **candidate_pack,
        }

    def classify(self, blueprint: BusinessBlueprint) -> Dict[str, Any]:
        characteristics = [item.name for item in blueprint.characteristics]
        understanding = blueprint.business_understanding
        context_texts = [
            understanding.business_summary,
            understanding.business_model,
            understanding.value_creation,
            understanding.competitive_position,
        ]
        classification = self.registry.build_profile(
            characteristics,
            texts=context_texts,
        )
        classification.update(
            self._build_blueprint_extras(
                blueprint,
                classification.get("business_dnas", []),
            )
        )
        validate_classification(classification)
        return classification

    def finalize_classification(
        self,
        blueprint: BusinessBlueprint,
        llm_classification: Optional[Dict[str, Any]] = None,
        *,
        company: Optional[str] = None,
        year: Optional[str] = None,
    ) -> Dict[str, Any]:
        selected_dnas = self._extract_selected_dnas(llm_classification)
        allowed_dnas = set(self.registry.allowed_dnas())
        selected_dnas = [
            dna
            for dna in selected_dnas
            if dna in allowed_dnas
        ]

        if selected_dnas:
            extras = self._build_llm_extras(
                llm_classification or {},
                company=company or blueprint.metadata.company,
                year=year,
            )
            classification = self.registry.build_profile_from_dnas(
                selected_dnas,
                extras=extras,
            )
        else:
            classification = self.classify(blueprint)
            classification.update(
                self._build_llm_extras(
                    llm_classification or {},
                    company=company or blueprint.metadata.company,
                    year=year,
                )
            )

        for key, value in self._build_blueprint_extras(
            blueprint,
            classification.get("business_dnas", []),
        ).items():
            classification.setdefault(key, value)

        validate_classification(classification)
        return classification

    @staticmethod
    def _build_blueprint_extras(
        blueprint: BusinessBlueprint,
        selected_dnas: List[str],
    ) -> Dict[str, Any]:
        extras: Dict[str, Any] = {}
        candidate_signals = {item.name: item for item in blueprint.candidate_dna_signals if item.name}

        rationale: List[str] = []
        for dna in selected_dnas:
            signal = candidate_signals.get(dna)
            if signal and signal.supporting_reason:
                rationale.append(f"{dna}: {signal.supporting_reason}")
        if not rationale and selected_dnas:
            rationale.append(
                "Selected Business DNAs were inferred from the business summary, business model, value creation, and evidence-backed characteristics."
            )
        if rationale:
            extras["rationale"] = rationale

        evidence_used: List[str] = []
        if blueprint.business_understanding.business_summary:
            evidence_used.append(blueprint.business_understanding.business_summary)
        if blueprint.business_understanding.business_model:
            evidence_used.append(blueprint.business_understanding.business_model)
        evidence_used.extend(item.name for item in blueprint.characteristics if item.name)
        if evidence_used:
            extras["evidence_used"] = list(dict.fromkeys(evidence_used[:8]))

        if "confidence" not in extras and selected_dnas:
            confidence_values = [
                candidate_signals[dna].confidence
                for dna in selected_dnas
                if dna in candidate_signals
            ]
            if confidence_values:
                extras["confidence"] = round(sum(confidence_values) / len(confidence_values), 4)

        return extras

    def _build_ranked_candidate_pack(
        self,
        *,
        evidence_snippets: List[str],
        max_candidates: int,
    ) -> Dict[str, Any]:
        semantic_result = self._compute_semantic_similarity(evidence_snippets)
        assessments = self._rank_candidate_archetypes(
            evidence_snippets,
            semantic_result=semantic_result,
            max_candidates=max_candidates,
        )
        selected = [item for item in assessments if item.selected]
        rejected = [item for item in assessments if not item.selected and item.raw_score > 0]
        selected_limit = max_candidates or self.MAX_CANDIDATES_DEFAULT
        selected = selected[:selected_limit]

        top_margin = selected[0].margin_to_next if selected else 0.0
        ambiguity_flag = any(item.ambiguity_flag for item in selected[:2]) if selected else False

        return {
            "allowed_dnas": self.registry.allowed_dnas(),
            "candidate_archetypes": [
                self._serialize_candidate_archetype(item)
                for item in selected
            ],
            "candidate_scores": [
                self._serialize_candidate_score(item)
                for item in selected
            ],
            "rejected_candidates": [
                self._serialize_rejected_candidate(item)
                for item in rejected[:max(3, selected_limit)]
            ],
            "evidence_snippets": list(evidence_snippets),
            "semantic_similarity_active": semantic_result.active,
            "semantic_backend": semantic_result.backend,
            "semantic_model": semantic_result.model_name,
            "semantic_disabled_reason": semantic_result.disabled_reason,
            "ambiguity_flag": ambiguity_flag,
            "margin_to_next_candidate": round(top_margin, 4),
        }

    def _rank_candidate_archetypes(
        self,
        evidence_snippets: List[str],
        *,
        semantic_result: SemanticSimilarityResult,
        max_candidates: int,
    ) -> List[CandidateAssessment]:
        if not evidence_snippets:
            fallback = self.registry.archetypes[: max_candidates or self.MAX_CANDIDATES_DEFAULT]
            return [
                CandidateAssessment(
                    archetype=archetype,
                    raw_score=0.0,
                    normalized_score=0.0,
                    confidence=0.0,
                    margin_to_next=0.0,
                    ambiguity_flag=False,
                    selected=True,
                    rejected_reason=None,
                    score_breakdown={"reason": "fallback_no_evidence"},
                )
                for archetype in fallback
            ]

        scored = [
            self._score_archetype_candidate(
                archetype,
                evidence_snippets,
                semantic_result=semantic_result,
            )
            for archetype in self.registry.archetypes
        ]
        scored.sort(key=lambda item: (-item.raw_score, item.archetype.archetype_id))

        max_raw = max((item.raw_score for item in scored), default=0.0)
        requested_limit = max_candidates or self.MAX_CANDIDATES_DEFAULT
        default_limit = min(requested_limit, self.MAX_CANDIDATES_DEFAULT)
        extended_limit = min(requested_limit, self.MAX_CANDIDATES_AMBIGUOUS)

        finalized: List[CandidateAssessment] = []
        for index, item in enumerate(scored):
            next_score = scored[index + 1].raw_score if index + 1 < len(scored) else 0.0
            margin = item.raw_score - next_score
            confidence = self._compute_candidate_confidence(
                raw_score=item.raw_score,
                max_raw=max_raw,
                margin=margin,
                breakdown=item.score_breakdown,
            )
            ambiguity = margin <= self.AMBIGUITY_MARGIN and item.raw_score > 0
            selected, rejected_reason = self._decide_candidate_selection(
                index=index,
                raw_score=item.raw_score,
                margin=margin,
                breakdown=item.score_breakdown,
                limit=extended_limit,
                ambiguity=ambiguity,
                confidence=confidence,
            )
            normalized_score = (
                round(item.raw_score / max_raw, 4)
                if max_raw > 0
                else 0.0
            )
            finalized.append(
                CandidateAssessment(
                    archetype=item.archetype,
                    raw_score=round(item.raw_score, 4),
                    normalized_score=normalized_score,
                    confidence=confidence,
                    margin_to_next=round(margin, 4),
                    ambiguity_flag=ambiguity,
                    selected=selected,
                    rejected_reason=rejected_reason,
                    score_breakdown=item.score_breakdown,
                )
            )

        use_limit = (
            extended_limit
            if any(item.ambiguity_flag for item in finalized[:2])
            else default_limit
        )
        finalized = [
            CandidateAssessment(
                archetype=item.archetype,
                raw_score=item.raw_score,
                normalized_score=item.normalized_score,
                confidence=item.confidence,
                margin_to_next=item.margin_to_next,
                ambiguity_flag=item.ambiguity_flag,
                selected=item.selected and index < use_limit,
                rejected_reason=(
                    item.rejected_reason
                    if not (item.selected and index >= use_limit)
                    else "not_selected_under_default_candidate_limit"
                ),
                score_breakdown=item.score_breakdown,
            )
            for index, item in enumerate(finalized)
        ]

        top_raw = finalized[0].raw_score if finalized else 0.0
        top_archetype = finalized[0].archetype if finalized else None
        finalized = [
            CandidateAssessment(
                archetype=item.archetype,
                raw_score=item.raw_score,
                normalized_score=item.normalized_score,
                confidence=item.confidence,
                margin_to_next=item.margin_to_next,
                ambiguity_flag=item.ambiguity_flag,
                selected=selected,
                rejected_reason=rejected_reason,
                score_breakdown=item.score_breakdown,
            )
            for item in finalized
            for selected, rejected_reason in [
                self._apply_post_selection_filters(
                    item,
                    top_raw=top_raw,
                    top_archetype=top_archetype,
                )
            ]
        ]

        selected = [item for item in finalized if item.selected]
        if not selected:
            fallback_count = min(use_limit, len(finalized))
            rebuilt = []
            for index, item in enumerate(finalized):
                rebuilt.append(
                    CandidateAssessment(
                        archetype=item.archetype,
                        raw_score=item.raw_score,
                        normalized_score=item.normalized_score,
                        confidence=item.confidence,
                        margin_to_next=item.margin_to_next,
                        ambiguity_flag=item.ambiguity_flag,
                        selected=index < fallback_count,
                        rejected_reason=None if index < fallback_count else item.rejected_reason,
                        score_breakdown=item.score_breakdown,
                    )
                )
            return rebuilt
        return finalized

    def _score_archetype_candidate(
        self,
        archetype: ArchetypeDefinition,
        evidence_snippets: List[str],
        *,
        semantic_result: SemanticSimilarityResult,
    ) -> CandidateAssessment:
        normalized_snippets = [
            self.registry._normalize(snippet)
            for snippet in evidence_snippets
            if snippet and snippet.strip()
        ]
        normalized_text = " ".join(normalized_snippets)
        snippet_tokens = [set(snippet.split()) for snippet in normalized_snippets]
        all_tokens = set(normalized_text.split())

        strong_group_hits = self._count_group_hits(
            normalized_snippets,
            snippet_tokens,
            archetype.signals.text_keyword_groups,
        )
        supporting_group_hits = self._count_group_hits(
            normalized_snippets,
            snippet_tokens,
            archetype.signals.keyword_groups,
        )
        characteristic_hits = self._count_phrase_hits(
            normalized_text,
            all_tokens,
            archetype.signals.characteristic_patterns,
            min_overlap=0.6,
        )
        positive_signal_hits = self._count_phrase_hits(
            normalized_text,
            all_tokens,
            archetype.signals.positive_signals,
            min_overlap=0.45,
        )
        evidence_pattern_hits = self._count_phrase_hits(
            normalized_text,
            all_tokens,
            archetype.signals.evidence_patterns,
            min_overlap=0.45,
        )
        negative_signal_hits = self._count_phrase_hits(
            normalized_text,
            all_tokens,
            archetype.signals.negative_signals,
            min_overlap=0.35,
        )
        definition_overlap = self._phrase_overlap(
            normalized_text,
            all_tokens,
            archetype.definition,
        )
        conflicting_positive_hits = self._count_conflicting_positive_hits(
            normalized_text,
            all_tokens,
            archetype,
        )
        semantic_similarity = semantic_result.scores.get(archetype.archetype_id, 0.0)
        semantic_boost = self._compute_semantic_boost(
            similarity=semantic_similarity,
            core_support=strong_group_hits + supporting_group_hits + characteristic_hits,
            negative_signal_hits=negative_signal_hits,
        )

        raw_score = (
            strong_group_hits * self.STRONG_GROUP_WEIGHT
            + supporting_group_hits * self.SUPPORTING_GROUP_WEIGHT
            + characteristic_hits * self.POSITIVE_SIGNAL_WEIGHT
            + positive_signal_hits * self.POSITIVE_SIGNAL_WEIGHT
            + evidence_pattern_hits * self.EVIDENCE_PATTERN_WEIGHT
            + definition_overlap * self.DEFINITION_OVERLAP_WEIGHT
            + semantic_boost
            - negative_signal_hits * self.NEGATIVE_SIGNAL_PENALTY
            - conflicting_positive_hits * self.CONFLICT_PENALTY
        )

        core_support = strong_group_hits + supporting_group_hits + characteristic_hits
        coverage = positive_signal_hits + evidence_pattern_hits

        return CandidateAssessment(
            archetype=archetype,
            raw_score=raw_score,
            normalized_score=0.0,
            confidence=0.0,
            margin_to_next=0.0,
            ambiguity_flag=False,
            selected=False,
            rejected_reason=None,
            score_breakdown={
                "strong_group_hits": strong_group_hits,
                "supporting_group_hits": supporting_group_hits,
                "characteristic_hits": characteristic_hits,
                "positive_signal_hits": positive_signal_hits,
                "evidence_pattern_hits": evidence_pattern_hits,
                "negative_signal_hits": negative_signal_hits,
                "conflicting_positive_hits": conflicting_positive_hits,
                "definition_overlap": round(definition_overlap, 4),
                "semantic_similarity": semantic_similarity,
                "semantic_boost": round(semantic_boost, 4),
                "used_semantic_similarity": semantic_result.active,
                "semantic_backend": semantic_result.backend,
                "semantic_model": semantic_result.model_name,
                "semantic_disabled_reason": semantic_result.disabled_reason,
                "core_support": core_support,
                "coverage": coverage,
            },
        )

    def _compute_semantic_similarity(
        self,
        evidence_snippets: List[str],
    ) -> SemanticSimilarityResult:
        company_text = self._build_company_signal_text(evidence_snippets)
        archetype_texts = {
            archetype.archetype_id: self._build_archetype_semantic_text(archetype)
            for archetype in self.registry.archetypes
        }
        return compute_similarity_scores(company_text, archetype_texts)

    def _build_company_signal_text(
        self,
        evidence_snippets: List[str],
    ) -> str:
        compact = [
            snippet.strip()
            for snippet in evidence_snippets
            if snippet and snippet.strip()
        ]
        return " | ".join(compact[:8])

    def _build_archetype_semantic_text(
        self,
        archetype: ArchetypeDefinition,
    ) -> str:
        parts = [archetype.definition]
        if archetype.signals.positive_signals:
            parts.append("Positive signals: " + "; ".join(archetype.signals.positive_signals))
        if archetype.signals.evidence_patterns:
            parts.append("Typical evidence: " + "; ".join(archetype.signals.evidence_patterns))
        if archetype.signals.confidence_hints:
            parts.append("Confidence hints: " + "; ".join(archetype.signals.confidence_hints))
        return " ".join(part for part in parts if part)

    def _compute_semantic_boost(
        self,
        *,
        similarity: float,
        core_support: int,
        negative_signal_hits: int,
    ) -> float:
        if similarity <= self.SEMANTIC_SIMILARITY_FLOOR:
            return 0.0
        boost = min(
            (similarity - self.SEMANTIC_SIMILARITY_FLOOR) * self.SEMANTIC_SIMILARITY_WEIGHT,
            self.SEMANTIC_SIMILARITY_MAX_BOOST,
        )
        if core_support <= 0:
            boost = min(boost, 0.75)
        if negative_signal_hits > 0:
            boost *= 0.5
        return round(boost, 4)

    def _count_group_hits(
        self,
        normalized_snippets: List[str],
        snippet_tokens: List[set[str]],
        groups: Iterable[Iterable[str]],
    ) -> int:
        hits = 0
        for group in groups:
            normalized_group = [
                self.registry._normalize(term)
                for term in group
                if self.registry._normalize(term)
            ]
            if not normalized_group:
                continue
            if any(
                all(
                    term in snippet if " " in term else term in tokens
                    for term in normalized_group
                )
                for snippet, tokens in zip(normalized_snippets, snippet_tokens)
            ):
                hits += 1
        return hits

    def _count_phrase_hits(
        self,
        normalized_text: str,
        tokens: set[str],
        phrases: Iterable[str],
        *,
        min_overlap: float,
    ) -> int:
        hits = 0
        for phrase in phrases:
            overlap = self._phrase_overlap(normalized_text, tokens, phrase)
            if overlap >= min_overlap:
                hits += 1
        return hits

    def _phrase_overlap(
        self,
        normalized_text: str,
        tokens: set[str],
        phrase: str,
    ) -> float:
        normalized_phrase = self.registry._normalize(phrase)
        if not normalized_phrase:
            return 0.0
        if normalized_phrase in normalized_text:
            return 1.0
        phrase_tokens = self._meaningful_tokens(normalized_phrase)
        if not phrase_tokens:
            return 0.0
        matched = sum(1 for token in phrase_tokens if token in tokens)
        return matched / len(phrase_tokens)

    def _count_conflicting_positive_hits(
        self,
        normalized_text: str,
        tokens: set[str],
        archetype: ArchetypeDefinition,
    ) -> int:
        conflicting = 0
        for other in self.registry.archetypes:
            if other.archetype_id == archetype.archetype_id:
                continue
            overlap_count = self._count_phrase_hits(
                normalized_text,
                tokens,
                other.signals.positive_signals,
                min_overlap=0.55,
            )
            if overlap_count <= 0:
                continue
            if self._archetypes_conflict(archetype, other):
                conflicting += overlap_count
        return conflicting

    def _archetypes_conflict(
        self,
        left: ArchetypeDefinition,
        right: ArchetypeDefinition,
    ) -> bool:
        manufacturing_like = {"manufacturing", "semiconductor"}
        platform_like = {"enterprise_platform", "compliance_infrastructure"}
        media_like = {"ip_library_platform_monetization"}

        family_groups = [manufacturing_like, platform_like, media_like]
        left_family = next((group for group in family_groups if left.archetype_id in group), None)
        right_family = next((group for group in family_groups if right.archetype_id in group), None)

        if left_family is None or right_family is None:
            return False
        return left_family is not right_family

    def _compute_candidate_confidence(
        self,
        *,
        raw_score: float,
        max_raw: float,
        margin: float,
        breakdown: Dict[str, Any],
    ) -> float:
        if raw_score <= 0 or max_raw <= 0:
            return 0.0
        normalized_score = raw_score / max_raw
        margin_factor = 0.5 + min(max(margin, 0.0), 4.0) / 8.0
        negative_penalty = min(breakdown.get("negative_signal_hits", 0) * 0.15, 0.45)
        conflict_penalty = min(breakdown.get("conflicting_positive_hits", 0) * 0.12, 0.36)
        confidence = normalized_score * margin_factor - negative_penalty - conflict_penalty
        return round(max(0.0, min(1.0, confidence)), 4)

    def _decide_candidate_selection(
        self,
        *,
        index: int,
        raw_score: float,
        margin: float,
        breakdown: Dict[str, Any],
        limit: int,
        ambiguity: bool,
        confidence: float,
    ) -> Tuple[bool, Optional[str]]:
        if index >= limit:
            return False, "below_candidate_limit"
        if raw_score < self.MIN_CANDIDATE_SCORE:
            return False, "insufficient_positive_support"
        if index > 0 and confidence < 0.15 and not ambiguity:
            return False, "low_confidence_candidate"
        if self._fails_family_support_gate(breakdown):
            return False, "failed_family_support_gate"
        if breakdown.get("negative_signal_hits", 0) > 0 and breakdown.get("core_support", 0) < 2:
            return False, "suppressed_by_negative_signals"
        if breakdown.get("conflicting_positive_hits", 0) > breakdown.get("positive_signal_hits", 0) + 1:
            return False, "overpowered_by_neighboring_archetype"
        if index > 0 and margin < -self.SCORE_MARGIN_FOR_SELECTION:
            return False, "far_below_top_candidate"
        if breakdown.get("core_support", 0) <= 0 and breakdown.get("coverage", 0) <= 1:
            return False, "weak_evidence_coverage"
        if ambiguity and index >= self.MAX_CANDIDATES_DEFAULT and limit <= self.MAX_CANDIDATES_DEFAULT:
            return False, "not_selected_under_default_candidate_limit"
        return True, None

    def _fails_family_support_gate(
        self,
        breakdown: Dict[str, Any],
    ) -> bool:
        strong = breakdown.get("strong_group_hits", 0)
        supporting = breakdown.get("supporting_group_hits", 0)
        characteristics = breakdown.get("characteristic_hits", 0)
        positive = breakdown.get("positive_signal_hits", 0)
        coverage = breakdown.get("coverage", 0)
        core = breakdown.get("core_support", 0)

        if core <= 0 and coverage <= 1:
            return True

        return False

    def _apply_post_selection_filters(
        self,
        assessment: CandidateAssessment,
        *,
        top_raw: float,
        top_archetype: Optional[ArchetypeDefinition],
    ) -> Tuple[bool, Optional[str]]:
        if not assessment.selected:
            return assessment.selected, assessment.rejected_reason
        if assessment.raw_score <= 0:
            return False, "insufficient_positive_support"

        archetype_id = assessment.archetype.archetype_id
        strong = assessment.score_breakdown.get("strong_group_hits", 0)
        supporting = assessment.score_breakdown.get("supporting_group_hits", 0)
        characteristics = assessment.score_breakdown.get("characteristic_hits", 0)

        if archetype_id == "manufacturing" and (strong + supporting < 3 or strong < 2):
            return False, "failed_family_support_gate"
        if archetype_id == "semiconductor" and (strong < 1 or strong + characteristics < 2):
            return False, "failed_family_support_gate"
        if archetype_id == "ip_library_platform_monetization" and (strong < 2 or strong + supporting < 3):
            return False, "failed_family_support_gate"

        if (
            top_archetype is not None
            and
            top_raw > 0
            and assessment.raw_score < top_raw * 0.4
            and assessment.confidence < 0.35
            and not assessment.ambiguity_flag
            and self._archetypes_conflict(assessment.archetype, top_archetype)
        ):
            return False, "dominated_by_top_candidate"

        return True, None

    def _serialize_candidate_archetype(
        self,
        assessment: CandidateAssessment,
    ) -> Dict[str, Any]:
        archetype = assessment.archetype
        return {
            "archetype_id": archetype.archetype_id,
            "dnas": list(archetype.dnas),
            "definition": archetype.definition,
            "positive_signals": list(archetype.signals.positive_signals),
            "negative_signals": list(archetype.signals.negative_signals),
            "evidence_patterns": list(archetype.signals.evidence_patterns),
            "default_question_modules": list(archetype.defaults.question_modules),
            "default_report_template": archetype.defaults.report_template,
            "confidence": assessment.confidence,
        }

    def _serialize_candidate_score(
        self,
        assessment: CandidateAssessment,
    ) -> Dict[str, Any]:
        return {
            "archetype_id": assessment.archetype.archetype_id,
            "dnas": list(assessment.archetype.dnas),
            "raw_score": assessment.raw_score,
            "normalized_score": assessment.normalized_score,
            "confidence": assessment.confidence,
            "margin_to_next_candidate": assessment.margin_to_next,
            "ambiguity_flag": assessment.ambiguity_flag,
            "score_breakdown": assessment.score_breakdown,
        }

    def _serialize_rejected_candidate(
        self,
        assessment: CandidateAssessment,
    ) -> Dict[str, Any]:
        return {
            "archetype_id": assessment.archetype.archetype_id,
            "dnas": list(assessment.archetype.dnas),
            "raw_score": assessment.raw_score,
            "rejected_reason": assessment.rejected_reason,
            "score_breakdown": assessment.score_breakdown,
        }

    def _build_evidence_snippets(
        self,
        company_memory: CompanyMemory,
        *,
        limit: int = 8,
    ) -> List[str]:
        weighted = []
        for event in company_memory.events.values():
            snippet = (event.summary or "").strip()
            if not snippet:
                continue
            weighted.append((self._score_evidence_snippet(snippet), snippet))

        weighted.sort(key=lambda item: (-item[0], item[1]))
        snippets = [snippet for _, snippet in weighted[:limit]]
        return list(dict.fromkeys(snippets))

    @staticmethod
    def _meaningful_tokens(text: str) -> List[str]:
        stopwords = {
            "a",
            "an",
            "and",
            "are",
            "as",
            "at",
            "by",
            "for",
            "from",
            "in",
            "into",
            "is",
            "its",
            "of",
            "on",
            "or",
            "the",
            "their",
            "through",
            "to",
            "with",
            "without",
        }
        return [
            token
            for token in re.findall(r"[a-z0-9]+", text.lower())
            if token not in stopwords
        ]

    @staticmethod
    def _score_evidence_snippet(snippet: str) -> int:
        normalized = snippet.lower()
        score = 0
        weighted_terms = [
            "revenue",
            "monetization",
            "licensing",
            "platform",
            "customer",
            "distribution",
            "capacity",
            "manufacturing",
            "wafer",
            "chip",
            "export",
            "global",
            "rights",
            "streaming",
            "security",
            "compliance",
            "messaging",
            "automation",
            "technology",
            "risk",
        ]
        for term in weighted_terms:
            if term in normalized:
                score += 2
        score += min(len(normalized) // 80, 4)
        return score

    @staticmethod
    def _extract_selected_dnas(
        llm_classification: Optional[Dict[str, Any]],
    ) -> List[str]:
        if not isinstance(llm_classification, dict):
            return []

        selected = llm_classification.get("selected_dnas")
        if isinstance(selected, list):
            names = []
            for item in selected:
                if isinstance(item, dict):
                    name = (item.get("name") or "").strip()
                else:
                    name = str(item).strip()
                if name:
                    names.append(name)
            if names:
                return list(dict.fromkeys(names))

        legacy = llm_classification.get("business_dnas")
        if isinstance(legacy, list):
            return list(
                dict.fromkeys(
                    str(item).strip()
                    for item in legacy
                    if str(item).strip()
                )
            )

        return []

    def _build_llm_extras(
        self,
        llm_classification: Dict[str, Any],
        *,
        company: Optional[str],
        year: Optional[str],
    ) -> Dict[str, Any]:
        extras: Dict[str, Any] = {}
        if company:
            extras["company"] = company
        if year:
            extras["year"] = year

        rejected = []
        for item in llm_classification.get("rejected_dnas", []):
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or "").strip()
            reason = (item.get("reason") or "").strip()
            if name and reason:
                rejected.append({"name": name, "reason": reason})
        if rejected:
            extras["rejected_dnas"] = rejected

        rationale = []
        for item in llm_classification.get("rationale", []):
            text = ""
            if isinstance(item, dict):
                text = (item.get("statement") or item.get("reason") or "").strip()
            else:
                text = str(item).strip()
            if text:
                rationale.append(text)
        if rationale:
            extras["rationale"] = rationale

        evidence_used = []
        for item in llm_classification.get("evidence_used", []):
            text = str(item).strip()
            if text:
                evidence_used.append(text)
        if evidence_used:
            extras["evidence_used"] = evidence_used

        confidence = llm_classification.get("confidence")
        if isinstance(confidence, (int, float)) and 0 <= float(confidence) <= 1:
            extras["confidence"] = float(confidence)

        return extras
