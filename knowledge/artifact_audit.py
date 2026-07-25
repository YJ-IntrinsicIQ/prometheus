from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core.company_context import CompanyContext
from intelligence.investor_panel.committee_brief_qa import CommitteeBriefQAGate
from knowledge.ai.input_packs import DEFAULT_STAGE_TOKEN_BUDGETS
from knowledge.business_identity import (
    DEPRECATED_BLUEPRINT_DNAS_STATUS,
    validate_business_identity,
)
from knowledge.capital_allocation_taxonomy import validate_capital_allocation_items
from knowledge.company_memory.pcim_multi_year_builder import audit_saved_pcim_manifest
from knowledge.evidence_layer import build_evidence_layer_summary, validate_cleaned_item


RAW_DOC_SUFFIXES = {".pdf", ".txt", ".md"}
DISCOVERY_OUTPUT_FILES = [
    "project_discovery_results.json",
    "promise_discovery_results.json",
    "risk_discovery_results.json",
    "capacity_discovery_results.json",
    "capital_allocation_discovery_results.json",
    "initiative_discovery_results.json",
    "commentary_discovery_results.json",
]
EXTRACTION_OUTPUT_FILES = [
    "extracted_projects.json",
    "extracted_promises.json",
    "extracted_risks.json",
    "extracted_capacity.json",
    "extracted_capital_allocation.json",
    "extracted_initiatives.json",
    "extracted_commentary.json",
]
CLEANING_OUTPUTS = {
    "clean_projects.json": "projects",
    "clean_promises.json": "promises",
    "clean_risks.json": "risks",
    "clean_capacity.json": "capacity_expansions",
    "clean_capital_allocation.json": "capital_allocations",
    "clean_initiatives.json": "initiatives",
}
COMMENTARY_OUTPUT_FILE = "clean_commentary.json"
YEAR_INTELLIGENCE_OUTPUTS = [
    "business_blueprint.json",
    "business_classification.json",
    "company_intelligence.json",
    "management_summary.json",
]
PANEL_ANALYSTS = ["graham", "buffett", "fisher", "munger", "lynch"]
FORBID_SOURCE_CHUNK_IN_MANIFESTS = {
    "business_understanding",
    "investor_panel_analyst",
    "committee_synthesis",
}
STAGE_MANIFESTS = {
    "business_understanding": "business_understanding_llm_call_manifest.json",
    "business_intelligence": "business_intelligence_llm_call_manifest.json",
    "committee_synthesis": "committee_llm_call_manifest.json",
    "investor_panel_analyst": "investor_panel_llm_call_manifest.json",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _merge_status(current: str, incoming: str) -> str:
    order = {"pass": 0, "warning": 1, "fail": 2}
    return incoming if order[incoming] > order[current] else current


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "__malformed_json__"


def _write_json(path: Path, payload: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _contains_source_chunk(payload: Any) -> bool:
    try:
        return '"source_chunk"' in json.dumps(payload, ensure_ascii=False)
    except TypeError:
        return False


def _collect_years(company_root: Path) -> List[str]:
    years = [
        path.name
        for path in sorted(company_root.iterdir())
        if path.is_dir() and path.name.lower().startswith("fy")
    ] if company_root.exists() else []
    return years


class ArtifactAudit:
    def __init__(self, company: str, *, companies_root: Path | str = Path("companies"), fix_safe: bool = False):
        self.company = company
        self.companies_root = Path(companies_root)
        self.company_root = self.companies_root / company
        self.fix_safe = fix_safe
        self.artifacts_checked: List[str] = []
        self.checks: List[Dict[str, Any]] = []
        self.critical_failures: List[str] = []
        self.warnings: List[str] = []
        self.recommendations: List[str] = []
        self.status = "pass"

    def _add_check(
        self,
        *,
        check_name: str,
        status: str,
        artifact: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        recommendation: Optional[str] = None,
    ) -> None:
        self.artifacts_checked.append(artifact)
        self.status = _merge_status(self.status, status)
        payload = {
            "check_name": check_name,
            "status": status,
            "artifact": artifact,
            "message": message,
            "details": details or {},
        }
        self.checks.append(payload)
        if status == "fail":
            if message not in self.critical_failures:
                self.critical_failures.append(message)
        elif status == "warning":
            if message not in self.warnings:
                self.warnings.append(message)
        if recommendation and recommendation not in self.recommendations:
            self.recommendations.append(recommendation)

    def _check_json_file(self, path: Path, *, check_name: str, required: bool = False) -> Any:
        artifact = str(path)
        if not path.exists():
            if required:
                self._add_check(
                    check_name=check_name,
                    status="warning",
                    artifact=artifact,
                    message=f"Missing artifact: {path.name}",
                )
            return None
        payload = _load_json(path)
        if payload == "__malformed_json__":
            self._add_check(
                check_name=check_name,
                status="fail",
                artifact=artifact,
                message=f"Malformed JSON: {path.name}",
            )
            return None
        self.artifacts_checked.append(artifact)
        return payload

    def _audit_year_artifacts(self, year: str) -> None:
        context = CompanyContext(company=self.company, year=year)
        year_root = self.company_root / year
        context.create_directories()
        raw_docs = [
            path.name
            for path in context.raw_dir.iterdir()
            if path.is_file() and path.suffix.lower() in RAW_DOC_SUFFIXES
        ] if context.raw_dir.exists() else []
        if raw_docs:
            self._add_check(
                check_name="raw_docs",
                status="pass",
                artifact=str(context.raw_dir),
                message=f"Found {len(raw_docs)} raw document(s) for {year}.",
                details={"files": raw_docs},
            )
        else:
            self._add_check(
                check_name="raw_docs",
                status="warning",
                artifact=str(context.raw_dir),
                message=f"No raw documents found for {year}.",
                recommendation="Add the annual report PDF/TXT/MD for this year if discovery needs to be reproducible.",
            )

        for filename in DISCOVERY_OUTPUT_FILES:
            self._check_json_file(context.raw_dir / filename, check_name="discovery_output")
        for filename in EXTRACTION_OUTPUT_FILES:
            self._check_json_file(context.extracted_dir / filename, check_name="extraction_output")

        for filename, module_name in CLEANING_OUTPUTS.items():
            payload = self._check_json_file(context.extracted_dir / filename, check_name="cleaned_output")
            if not isinstance(payload, list):
                continue
            if module_name == "capital_allocations":
                validation = validate_capital_allocation_items(payload)
                for error in validation["errors"]:
                    self._add_check(
                        check_name="capital_allocation_taxonomy",
                        status="fail",
                        artifact=str(context.extracted_dir / filename),
                        message=error,
                    )
                for warning in validation["warnings"]:
                    self._add_check(
                        check_name="capital_allocation_taxonomy",
                        status="warning",
                        artifact=str(context.extracted_dir / filename),
                        message=warning,
                    )
            for index, item in enumerate(payload, start=1):
                validation = validate_cleaned_item(item, module_name=module_name)
                for error in validation["errors"]:
                    self._add_check(
                        check_name="evidence_hygiene",
                        status="fail",
                        artifact=str(context.extracted_dir / filename),
                        message=f"{filename} item {index}: {error}",
                    )
                for warning in validation["warnings"]:
                    self._add_check(
                        check_name="evidence_hygiene",
                        status="warning",
                        artifact=str(context.extracted_dir / filename),
                        message=f"{filename} item {index}: {warning}",
                    )
                confidence = str(item.get("confidence") or "").lower()
                if confidence in {"low", "medium"} and not item.get("uncertainty_reason"):
                    self._add_check(
                        check_name="evidence_hygiene",
                        status="warning",
                        artifact=str(context.extracted_dir / filename),
                        message=f"{filename} item {index}: low/medium confidence item is missing uncertainty_reason",
                    )

        commentary = self._check_json_file(
            context.extracted_dir / COMMENTARY_OUTPUT_FILE,
            check_name="cleaned_output",
        )
        if isinstance(commentary, dict):
            validation = commentary.get("validation") or {}
            if validation.get("errors"):
                for error in validation.get("errors", []):
                    self._add_check(
                        check_name="management_context_routing",
                        status="fail",
                        artifact=str(context.extracted_dir / COMMENTARY_OUTPUT_FILE),
                        message=str(error),
                    )
            if validation.get("warnings"):
                for warning in validation.get("warnings", []):
                    self._add_check(
                        check_name="management_context_routing",
                        status="warning",
                        artifact=str(context.extracted_dir / COMMENTARY_OUTPUT_FILE),
                        message=str(warning),
                    )
            if _contains_source_chunk(commentary):
                self._add_check(
                    check_name="evidence_hygiene",
                    status="fail",
                    artifact=str(context.extracted_dir / COMMENTARY_OUTPUT_FILE),
                    message="source_chunk leakage detected in clean_commentary.json",
                )

        blueprint = self._check_json_file(
            context.intelligence_dir / "business_blueprint.json",
            check_name="year_intelligence_output",
        )
        classification = self._check_json_file(
            context.intelligence_dir / "business_classification.json",
            check_name="year_intelligence_output",
        )
        company_intelligence = self._check_json_file(
            context.intelligence_dir / "company_intelligence.json",
            check_name="year_intelligence_output",
        )
        management_summary = self._check_json_file(
            context.intelligence_dir / "management_summary.json",
            check_name="year_intelligence_output",
        )

        if isinstance(blueprint, dict) and isinstance(classification, dict):
            identity = validate_business_identity(blueprint, classification)
            level = "fail" if identity["failures"] else ("warning" if identity["warnings"] else "pass")
            self._add_check(
                check_name="business_identity_consistency",
                status=level,
                artifact=str(context.intelligence_dir / "business_classification.json"),
                message=f"Business identity contract status for {year}: {identity['conflict_status']}",
                details=identity,
                recommendation=(
                    "Use business_classification.business_dnas as the only authoritative Business DNA source."
                    if level != "pass"
                    else None
                ),
            )
            if self.fix_safe:
                self._apply_safe_blueprint_marker_fix(
                    context.intelligence_dir / "business_blueprint.json",
                    blueprint,
                    classification,
                )

        if isinstance(company_intelligence, dict) and isinstance(classification, dict):
            official = list(classification.get("business_dnas") or [])
            downstream = (((company_intelligence.get("business") or {}).get("dna") or {}).get("business_dnas") or [])
            if official != downstream:
                self._add_check(
                    check_name="business_identity_consistency",
                    status="fail",
                    artifact=str(context.intelligence_dir / "company_intelligence.json"),
                    message=(
                        f"company_intelligence business.dna disagrees with business_classification for {year}: "
                        f"{downstream} vs {official}"
                    ),
                )

        if isinstance(management_summary, dict):
            routing = management_summary.get("routing_validation") or {}
            routing_status = str(routing.get("status") or "pass").lower()
            if routing_status == "fail":
                self._add_check(
                    check_name="management_context_routing",
                    status="fail",
                    artifact=str(context.intelligence_dir / "management_summary.json"),
                    message="management_summary routing validation failed",
                    details=routing,
                )
            elif routing.get("warnings"):
                self._add_check(
                    check_name="management_context_routing",
                    status="warning",
                    artifact=str(context.intelligence_dir / "management_summary.json"),
                    message="management_summary routing validation reported warnings",
                    details=routing,
                )
            management_consistency = (
                ((management_summary.get("management_consistency") or {}).get("consistency_observations"))
                or []
            )
            for item in management_consistency:
                evidence = json.dumps(item, ensure_ascii=False).lower()
                if "external_" in evidence:
                    self._add_check(
                        check_name="management_context_routing",
                        status="fail",
                        artifact=str(context.intelligence_dir / "management_summary.json"),
                        message="External context leaked into management_consistency observations",
                    )
                    break

        if isinstance(company_intelligence, dict):
            external_context = (((company_intelligence.get("management") or {}).get("summary") or {}).get("external_context")) or []
            management_quality = (((company_intelligence.get("management") or {}).get("summary") or {}).get("management_quality_inputs")) or []
            if external_context and management_quality and any("external_" in json.dumps(item, ensure_ascii=False).lower() for item in management_quality):
                self._add_check(
                    check_name="management_context_routing",
                    status="warning",
                    artifact=str(context.intelligence_dir / "company_intelligence.json"),
                    message="Potential external-context leakage into company_intelligence management-quality structures",
                )

        self._audit_year_freshness(context)
        self._audit_llm_cost_hygiene(context)

    def _audit_year_freshness(self, context: CompanyContext) -> None:
        intelligence_path = context.intelligence_dir / "company_intelligence.json"
        management_summary_path = context.intelligence_dir / "management_summary.json"
        classification_path = context.intelligence_dir / "business_classification.json"
        blueprint_path = context.intelligence_dir / "business_blueprint.json"
        commentary_path = context.extracted_dir / COMMENTARY_OUTPUT_FILE
        if intelligence_path.exists() and classification_path.exists():
            if intelligence_path.stat().st_mtime < classification_path.stat().st_mtime:
                self._add_check(
                    check_name="artifact_freshness",
                    status="warning",
                    artifact=str(intelligence_path),
                    message="company_intelligence.json is older than business_classification.json",
                )
        if management_summary_path.exists() and commentary_path.exists():
            if management_summary_path.stat().st_mtime < commentary_path.stat().st_mtime:
                self._add_check(
                    check_name="artifact_freshness",
                    status="warning",
                    artifact=str(management_summary_path),
                    message="management_summary.json is older than clean_commentary.json",
                )
        if classification_path.exists() and blueprint_path.exists():
            if classification_path.stat().st_mtime + 1 < blueprint_path.stat().st_mtime:
                self._add_check(
                    check_name="artifact_freshness",
                    status="warning",
                    artifact=str(classification_path),
                    message="business_classification.json is older than business_blueprint.json",
                )

    def _audit_llm_cost_hygiene(self, context: CompanyContext) -> None:
        summary = build_evidence_layer_summary(context)
        cost = summary.get("cost_estimate") or {}
        self._add_check(
            check_name="llm_cost_hygiene",
            status=summary.get("status") or "pass",
            artifact=str(context.year_root / "evidence_layer_summary.json"),
            message=(
                f"Evidence layer summary: llm_calls={cost.get('llm_calls', 0)}, "
                f"estimated_prompt_tokens={cost.get('estimated_prompt_tokens', 0)}"
            ),
            details=summary,
        )

        manifests: List[Tuple[str, Path, bool]] = [
            (
                "business_understanding",
                context.intelligence_dir / STAGE_MANIFESTS["business_understanding"],
                any((context.intelligence_dir / name).exists() for name in ("business_blueprint.json", "business_classification.json")),
            ),
            (
                "business_intelligence",
                context.intelligence_dir / STAGE_MANIFESTS["business_intelligence"],
                any((context.intelligence_dir / name).exists() for name in ("module_results.json", "discovery_runtime.json")),
            ),
        ]
        for filename in EXTRACTION_OUTPUT_FILES:
            manifests.append(
                (
                    "extraction",
                    context.extracted_dir / f"{Path(filename).stem}_llm_call_manifest.json",
                    (context.extracted_dir / filename).exists(),
                )
            )

        for stage, path, required in manifests:
            payload = self._check_json_file(path, check_name="llm_manifest", required=required)
            if payload is None:
                continue
            budget = DEFAULT_STAGE_TOKEN_BUDGETS.get(stage, 5000)
            entries = payload.get("entries") or []
            if not entries:
                self._add_check(
                    check_name="llm_cost_hygiene",
                    status="warning",
                    artifact=str(path),
                    message=f"{path.name} exists but has no entries",
                )
            for entry in entries:
                prompt_tokens = int(entry.get("estimated_prompt_tokens") or 0)
                if prompt_tokens > int(budget * 1.25):
                    self._add_check(
                        check_name="llm_cost_hygiene",
                        status="fail",
                        artifact=str(path),
                        message=f"{path.name} exceeds budget heavily: {prompt_tokens} > {budget}",
                        details={"stage": stage, "budget": budget, "estimated_prompt_tokens": prompt_tokens},
                    )
                elif prompt_tokens > budget:
                    self._add_check(
                        check_name="llm_cost_hygiene",
                        status="warning",
                        artifact=str(path),
                        message=f"{path.name} exceeds budget: {prompt_tokens} > {budget}",
                        details={"stage": stage, "budget": budget, "estimated_prompt_tokens": prompt_tokens},
                    )
            if stage in FORBID_SOURCE_CHUNK_IN_MANIFESTS and _contains_source_chunk(payload):
                self._add_check(
                    check_name="llm_cost_hygiene",
                    status="fail",
                    artifact=str(path),
                    message=f"source_chunk leaked into {stage} LLM manifest/input payload",
                )
            text = json.dumps(payload, ensure_ascii=False).lower()
            for forbidden in ("validation_report", "source_manifest"):
                if forbidden in text:
                    self._add_check(
                        check_name="llm_cost_hygiene",
                        status="warning",
                        artifact=str(path),
                        message=f"{path.name} appears to include {forbidden} in prompt-facing data",
                    )

    def _apply_safe_blueprint_marker_fix(
        self,
        path: Path,
        blueprint: Dict[str, Any],
        classification: Dict[str, Any],
    ) -> None:
        blueprint_dnas = [item.get("name") for item in blueprint.get("dnas", []) if isinstance(item, dict) and item.get("name")]
        official_dnas = [str(item) for item in classification.get("business_dnas", []) if str(item).strip()]
        current_status = blueprint.get("dnas_status")
        if not blueprint_dnas or current_status == DEPRECATED_BLUEPRINT_DNAS_STATUS:
            return
        if blueprint_dnas != official_dnas and blueprint_dnas:
            return
        updated = dict(blueprint)
        updated["dnas_status"] = DEPRECATED_BLUEPRINT_DNAS_STATUS
        _write_json(path, updated)
        self._add_check(
            check_name="fix_safe",
            status="warning",
            artifact=str(path),
            message="Applied safe fix: marked business_blueprint.dnas as deprecated_not_authoritative",
        )

    def _audit_company_level(self, years: Sequence[str]) -> None:
        company_memory_dir = self.company_root / "company_memory"
        multi_year_dir = company_memory_dir / "multi_year"
        pcim_path = company_memory_dir / "pcim_v1.json"
        cim_path = company_memory_dir / "cim_v1.json"
        panel_dir = company_memory_dir / "investor_panel"

        cim = self._check_json_file(cim_path, check_name="company_level_artifact")
        pcim = self._check_json_file(pcim_path, check_name="company_level_artifact")
        company_year_index = self._check_json_file(multi_year_dir / "company_year_index.json", check_name="company_level_artifact")
        multi_year_index = self._check_json_file(multi_year_dir / "multi_year_index.json", check_name="company_level_artifact")

        if isinstance(pcim, dict):
            manifest = pcim.get("pcim_source_manifest") or {}
            freshness = audit_saved_pcim_manifest(
                self.company_root,
                manifest,
                saved_multi_year_inputs=pcim.get("multi_year_inputs"),
                expected_years=years,
            )
            status = freshness["status"]
            self._add_check(
                check_name="pcim_freshness",
                status=status,
                artifact=str(pcim_path),
                message=f"PCIM source manifest freshness status: {status}",
                details=freshness,
                recommendation=(
                    "Rebuild CIM/PCIM after updating multi-year artifacts."
                    if status != "pass"
                    else None
                ),
            )
            if _contains_source_chunk(pcim):
                self._add_check(
                    check_name="evidence_hygiene",
                    status="fail",
                    artifact=str(pcim_path),
                    message="source_chunk leakage detected in pcim_v1.json",
                )
            identity_manifest = pcim.get("business_identity_manifest") or {}
            official_dnas = identity_manifest.get("official_business_dnas") or []
            latest_view_dnas = [
                item.get("value")
                for item in (((pcim.get("business_understanding") or {}).get("latest_business_view") or {}).get("business_dnas") or [])
                if isinstance(item, dict) and item.get("value")
            ]
            if official_dnas and latest_view_dnas and official_dnas != latest_view_dnas:
                self._add_check(
                    check_name="business_identity_consistency",
                    status="fail",
                    artifact=str(pcim_path),
                    message=(
                        "PCIM latest_business_view.business_dnas does not match PCIM business_identity_manifest "
                        f"({latest_view_dnas} vs {official_dnas})"
                    ),
                )
            management_quality = (pcim.get("management_quality_inputs") or {}).get("management_grouped_by_year") or []
            for bucket in management_quality:
                if "external_context" in bucket:
                    self._add_check(
                        check_name="management_context_routing",
                        status="fail",
                        artifact=str(pcim_path),
                        message="PCIM management_quality_inputs must not embed external_context buckets",
                    )
                    break

        if isinstance(cim, dict) and isinstance(pcim, dict):
            cim_dnas = (((cim.get("business") or {}).get("dna") or {}).get("business_dnas")) or []
            pcim_dnas = ((pcim.get("business_identity_manifest") or {}).get("official_business_dnas")) or []
            if cim_dnas and pcim_dnas and cim_dnas != pcim_dnas:
                self._add_check(
                    check_name="business_identity_consistency",
                    status="fail",
                    artifact=str(company_memory_dir),
                    message=f"CIM and PCIM disagree on official business DNAs: {cim_dnas} vs {pcim_dnas}",
                )

        if isinstance(company_year_index, dict) and isinstance(multi_year_index, dict):
            available = list(company_year_index.get("available_years", []) or [])
            covered = list(multi_year_index.get("years_covered", []) or [])
            missing = [year for year in available if year not in covered]
            if missing:
                self._add_check(
                    check_name="multi_year_coverage",
                    status="warning" if len(available) > 1 else "pass",
                    artifact=str(multi_year_index),
                    message=f"Multi-year coverage is partial: missing {missing}",
                    details={"available_years": available, "years_covered": covered, "missing_years": missing},
                )
            elif available:
                self._add_check(
                    check_name="multi_year_coverage",
                    status="pass",
                    artifact=str(multi_year_index),
                    message="Multi-year coverage matches detected available years.",
                    details={"available_years": available, "years_covered": covered},
                )

        if panel_dir.exists():
            if not isinstance(pcim, dict):
                self._add_check(
                    check_name="panel_readiness",
                    status="fail",
                    artifact=str(panel_dir),
                    message="Panel artifacts exist but pcim_v1.json is missing or malformed",
                )
            for analyst in PANEL_ANALYSTS:
                path = panel_dir / f"{analyst}_analysis.json"
                payload = self._check_json_file(path, check_name="panel_artifact")
                if not isinstance(payload, dict):
                    continue
                status = str(payload.get("evidence_grounding_status") or "").lower()
                unresolved = list(((payload.get("evidence_id_normalization") or {}).get("unresolved_ids")) or [])
                if status == "fail":
                    self._add_check(
                        check_name="panel_readiness",
                        status="fail",
                        artifact=str(path),
                        message=f"{analyst} analyst output failed evidence grounding",
                    )
                elif unresolved and status == "pass":
                    self._add_check(
                        check_name="panel_readiness",
                        status="fail",
                        artifact=str(path),
                        message=f"{analyst} analyst output passed with unresolved evidence IDs",
                    )
                elif unresolved or status == "warning":
                    self._add_check(
                        check_name="panel_readiness",
                        status="warning",
                        artifact=str(path),
                        message=f"{analyst} analyst output has evidence-grounding warnings",
                        details={"unresolved_ids": unresolved, "status": status},
                    )

            committee_synthesis = self._check_json_file(panel_dir / "committee_synthesis.json", check_name="panel_artifact")
            committee_brief = panel_dir / "committee_brief.md"
            qa = self._check_json_file(panel_dir / "committee_brief_qa.json", check_name="panel_artifact")
            if isinstance(committee_synthesis, dict):
                unresolved = list(((committee_synthesis.get("evidence_id_normalization") or {}).get("unresolved_ids")) or [])
                if unresolved:
                    self._add_check(
                        check_name="panel_readiness",
                        status="fail",
                        artifact=str(panel_dir / "committee_synthesis.json"),
                        message="committee_synthesis still contains unresolved evidence IDs",
                        details={"unresolved_ids": unresolved},
                    )
            if committee_brief.exists():
                self.artifacts_checked.append(str(committee_brief))
                if isinstance(qa, dict):
                    qa_status = str(qa.get("status") or "").lower()
                    if qa_status == "fail":
                        self._add_check(
                            check_name="panel_readiness",
                            status="fail",
                            artifact=str(panel_dir / "committee_brief_qa.json"),
                            message="committee brief QA failed",
                            details=qa,
                        )
                    elif qa_status == "warning":
                        self._add_check(
                            check_name="panel_readiness",
                            status="warning",
                            artifact=str(panel_dir / "committee_brief_qa.json"),
                            message="committee brief QA reported warnings",
                            details=qa,
                        )
                else:
                    self._add_check(
                        check_name="panel_readiness",
                        status="warning",
                        artifact=str(panel_dir),
                        message="committee_brief.md exists but committee_brief_qa.json is missing",
                    )
                try:
                    CommitteeBriefQAGate(self.company, companies_root=self.companies_root).build()
                except Exception as exc:
                    self._add_check(
                        check_name="panel_readiness",
                        status="fail",
                        artifact=str(committee_brief),
                        message=f"committee brief QA re-check failed: {exc}",
                    )

        for stage, filename in [
            ("committee_synthesis", STAGE_MANIFESTS["committee_synthesis"]),
            ("investor_panel_analyst", STAGE_MANIFESTS["investor_panel_analyst"]),
        ]:
            path = panel_dir / filename
            payload = self._check_json_file(path, check_name="llm_manifest")
            if isinstance(payload, dict) and _contains_source_chunk(payload):
                self._add_check(
                    check_name="llm_cost_hygiene",
                    status="fail",
                    artifact=str(path),
                    message=f"source_chunk leaked into {stage} manifest/input payload",
                )

    def run(self) -> Dict[str, Any]:
        years = _collect_years(self.company_root)
        if not years:
            self._add_check(
                check_name="company_root",
                status="fail",
                artifact=str(self.company_root),
                message=f"No fiscal-year directories found for {self.company}",
            )
        elif len(years) == 1:
            self._add_check(
                check_name="coverage_limits",
                status="warning",
                artifact=str(self.company_root),
                message="Only one fiscal year is available; multi-year conclusions remain provisional.",
            )
        for year in years:
            self._audit_year_artifacts(year)
        self._audit_company_level(years)

        payload = {
            "company": self.company,
            "status": self.status,
            "years_detected": years,
            "artifacts_checked": sorted(dict.fromkeys(self.artifacts_checked)),
            "checks": self.checks,
            "critical_failures": self.critical_failures,
            "warnings": self.warnings,
            "recommendations": self.recommendations,
            "generated_at": _now_iso(),
        }
        return payload


def render_markdown_report(payload: Dict[str, Any]) -> str:
    lines = [
        f"# Company Artifact Audit — {payload.get('company', 'unknown')}",
        "",
        f"- Status: `{payload.get('status', 'unknown')}`",
        f"- Years detected: {', '.join(payload.get('years_detected', [])) or 'None'}",
        f"- Artifacts checked: {len(payload.get('artifacts_checked', []))}",
        "",
    ]
    if payload.get("critical_failures"):
        lines.extend(["## Critical Failures", ""])
        lines.extend([f"- {item}" for item in payload["critical_failures"]])
        lines.append("")
    if payload.get("warnings"):
        lines.extend(["## Warnings", ""])
        lines.extend([f"- {item}" for item in payload["warnings"]])
        lines.append("")
    if payload.get("recommendations"):
        lines.extend(["## Recommendations", ""])
        lines.extend([f"- {item}" for item in payload["recommendations"]])
        lines.append("")
    lines.extend(["## Checks", ""])
    for check in payload.get("checks", []):
        lines.append(
            f"- [{check['status']}] `{check['check_name']}` on `{check['artifact']}`: {check['message']}"
        )
    lines.append("")
    return "\n".join(lines)


def run_company_artifact_audit(
    company: str,
    *,
    companies_root: Path | str = Path("companies"),
    fix_safe: bool = False,
) -> Dict[str, Path]:
    auditor = ArtifactAudit(company, companies_root=companies_root, fix_safe=fix_safe)
    payload = auditor.run()
    company_root = Path(companies_root) / company
    audit_dir = company_root / "audit"
    json_path = _write_json(audit_dir / "company_artifact_audit.json", payload)
    md_path = _write_text(audit_dir / "company_artifact_audit.md", render_markdown_report(payload))
    return {
        "company_artifact_audit.json": json_path,
        "company_artifact_audit.md": md_path,
    }
