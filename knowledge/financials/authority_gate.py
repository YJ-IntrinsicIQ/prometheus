"""Financial authority enforced where evidence is CONSUMED, not only where it is built.

The Financial Fact Registry (one per company-year) is the authority on which figures may be used. A rebuild that runs in the right order gives consistent files, but a consumer can
meet any other state: the registries are gone, a truth pack is empty, a file from an earlier build sits beside the current registries, someone edited a normalized figure that the
registry rejects. Every consumer of financial evidence (Ask loader, panel input registry, CIM / PCIM / trend builders, ratios) therefore asks this module, at read time:

  * `load_company_authority(company_dir)`  - the registries that exist NOW, their fingerprints, which (metric, year) pairs are usable and which are rejected;
  * `check_artifact(company_dir, rel_path)` - is this financial-derived artifact the one that was built against the CURRENT registries, and has it been left untouched since?
        valid | unbound (no record of what it was built from) | stale (built against other registries) | tampered (content changed since it was recorded) | no_authority (no registries);
  * `contradictions(payload, authority)`   - metric points inside a payload that disagree with the registry (a rejected figure, or a value other than the usable fact's).

Only `valid` evidence is used; every other state makes the dependent output UNAVAILABLE. Fingerprints cover every fact of the registry (identity, value, status, eligibility), derived facts included: a total debt that is the registry's sum of two components is as much an
authority as the components. An artifact is recorded again whenever its year's registry is written, so a registry rebuilt after ratios were written does not strand them.
Dependent evidence is also bound to the artifacts it was built FROM (a PCIM to its CIM, truth pack and trends; a panel analysis to the PCIM): replace or empty one of those and
everything built on it is unavailable, although its own record still matches the registries.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

REGISTRY_NAME = "financial_fact_registry.json"
MANIFEST_REL = "company_memory/financials/authority_manifest.json"
_FACT_LISTS = ("available_facts", "derived_facts", "partial_facts", "missing_facts", "precise_missing_facts", "unreliable_facts", "invalid_facts")
_USABLE = {"present_direct", "present_derived", "partial"}
_METRIC_KEYS = ("metric_id", "canonical_metric", "canonical_field", "field", "metric", "ratio_name")
_YEAR_KEYS = ("fiscal_year", "source_year", "year", "period", "current_year")
_VALUE_KEYS = ("value", "value_crore", "current_value", "numeric_value", "latest_value", "value_per_share")
# a block that lists REJECTED figures on purpose, as diagnostics, is not evidence
DIAGNOSTIC_KEYS = frozenset({"invalid_facts", "unreliable_facts", "invalid_or_quarantined_metrics", "unreliable_metrics", "invalid_or_quarantined_financial_inputs",
                             "unreliable_financial_inputs", "registry_exclusions", "withheld_metrics", "withheld_by_registry", "downstream_blockers", "missing_facts",
                             "precise_missing_facts", "quarantined_facts", "excluded_facts"})
# artifacts whose content is derived from the registries (relative to a company directory); the first three groups are deterministic projections, the last are generated interpretations
FINANCIAL_DEPENDENT_FILES = (
    "company_memory/cim_v1.json", "company_memory/pcim_v1.json",
    "company_memory/financials/financial_truth_pack.json", "company_memory/financials/financial_trends.json",
    "company_memory/financials/investor_financial_modules/",
    "company_memory/financial_truth_pack.json", "company_memory/financial_memory_summary.json", "company_memory/financial_quality_evolution.json", "company_memory/financial_year_index.json",
    "company_memory/investor_panel/",
)
YEAR_ARTIFACTS = ("financial_ratios.json", "financial_growth.json", "financial_quality_summary.json", "normalized_fundamentals.json")


def is_financial_dependent(rel_path: str) -> bool:
    rel = str(rel_path).replace("\\", "/")
    return any(rel == pattern or (pattern.endswith("/") and rel.startswith(pattern)) for pattern in FINANCIAL_DEPENDENT_FILES)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_identity(fact: Dict[str, Any]) -> List[Any]:
    return [fact.get(k) for k in ("metric_id", "fiscal_year", "value", "basis", "unit", "source_line_item", "source_page", "availability_status", "usable_downstream")]


def year_fingerprint(registry: Dict[str, Any]) -> str:
    identities = sorted(json.dumps(_source_identity(f), default=str) for key in _FACT_LISTS for f in (registry.get(key) or []) if isinstance(f, dict))
    return sha256_bytes("\n".join(identities).encode())


@dataclass
class YearAuthority:
    fiscal_year: str
    fingerprint: str
    usable: Dict[str, Dict[str, Any]] = field(default_factory=dict)       # metric -> fact the registry lets the year use
    rejected: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)  # metric -> invalid / unreliable facts (never evidence)


@dataclass
class CompanyAuthority:
    company_dir: Path
    years: Dict[str, YearAuthority] = field(default_factory=dict)

    @property
    def state(self) -> str:
        return "valid" if self.years else "no_authority"

    @property
    def fingerprint(self) -> str:
        return sha256_bytes("\n".join(f"{fy}:{y.fingerprint}" for fy, y in sorted(self.years.items())).encode())

    def year(self, fiscal_year: str) -> Optional[YearAuthority]:
        return self.years.get(_year_key(fiscal_year))

    def verdict(self, metric: str, fiscal_year: str) -> str:
        """usable | rejected | unknown for a (metric, year) pair; a year with no registry is 'unknown' (not 'usable')."""
        year = self.year(fiscal_year)
        if year is None:
            return "unknown"
        if metric in year.usable:
            return "usable"
        return "rejected" if metric in year.rejected else "unknown"


def _year_key(value: Any) -> str:
    """fyYY from 'fy24', 'FY 2023-24' (the year the period ends in), 'March 31, 2024', '31/03/2024' or a bare year; '' when none is stated."""
    text = str(value or "").strip().lower()
    for pattern, take_last in ((r"fy\s*(\d{2})\b", False), (r"\b20\d{2}\s*[-\u2013/]\s*(\d{2})\b", False), (r"\b20(\d{2})\b", False)):
        match = re.search(pattern, text)
        if match:
            return f"fy{match.group(1)}"
    return ""


def load_company_authority(company_dir: Path | str) -> CompanyAuthority:
    company_dir = Path(company_dir)
    authority = CompanyAuthority(company_dir=company_dir)
    for year_dir in sorted(company_dir.glob("fy*")):
        path = year_dir / "financials" / REGISTRY_NAME
        if not path.exists():
            continue
        try:
            registry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(registry, dict):
            continue
        year = YearAuthority(fiscal_year=year_dir.name, fingerprint=year_fingerprint(registry))
        for key in _FACT_LISTS:
            for fact in registry.get(key) or []:
                if not isinstance(fact, dict) or not fact.get("metric_id"):
                    continue
                if fact.get("usable_downstream") and fact.get("availability_status") in _USABLE:
                    year.usable.setdefault(fact["metric_id"], fact)
                elif fact.get("availability_status") in {"invalid", "unreliable"} or (key in {"invalid_facts", "unreliable_facts"}):
                    year.rejected.setdefault(fact["metric_id"], []).append(fact)
        authority.years[year_dir.name] = year
    return authority


# ---- the record of what each financial-derived artifact was built against ----------------------------------------------------------------------------------------------------------------

def _manifest_path(company_dir: Path) -> Path:
    return Path(company_dir) / MANIFEST_REL


def read_manifest(company_dir: Path | str) -> Dict[str, Any]:
    try:
        payload = json.loads(_manifest_path(Path(company_dir)).read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}


def record_artifacts(company_dir: Path | str, rel_paths: Iterable[str], *, output_root: Path | str, authorize_served_write: bool = False) -> Dict[str, Any]:
    """Record, for each artifact (relative to the company directory), its SHA-256 and the registries it was built against. Merges into the company's manifest."""
    from core.context_paths import resolve_output_root
    return _record(Path(company_dir), rel_paths, resolve_output_root(output_root, authorize_served=authorize_served_write))


def _record(company_dir: Path, rel_paths: Iterable[str], root: Path) -> Dict[str, Any]:
    from core.context_paths import guarded_write_text
    authority = load_company_authority(company_dir)
    manifest = read_manifest(company_dir)
    entries = dict(manifest.get("artifacts") or {})
    for rel in rel_paths:
        path = company_dir / rel
        if not path.exists():
            entries.pop(str(rel), None)
            continue
        scope = _scope_of(rel)
        fingerprint = authority.years[scope[1]].fingerprint if scope[0] == "year" and scope[1] in authority.years else authority.fingerprint
        entries[str(rel)] = {"sha256": sha256_bytes(path.read_bytes()), "scope": scope[0] if scope[0] == "company" else f"year:{scope[1]}", "authority_fingerprint": fingerprint,
                             "depends_on": {dep: sha256_bytes((company_dir / dep).read_bytes()) for dep in _dependencies(company_dir, str(rel))}}
    manifest = {"schema": 1, "company": company_dir.name, "authority": {"fingerprint": authority.fingerprint, "years": {fy: y.fingerprint for fy, y in sorted(authority.years.items())}},
                "artifacts": dict(sorted(entries.items()))}
    guarded_write_text(root, _manifest_path(company_dir), json.dumps(manifest, indent=1, sort_keys=True))
    return manifest


FINANCIALS_DIR = "company_memory/financials/"


def _dependencies(company_dir: Path, rel: str) -> List[str]:
    """The financial artifacts a derived artifact is built FROM (relative paths that exist now): every artifact under company_memory/financials/ for anything outside that folder
    (CIM, PCIM, mirrors, panel outputs), the CIM for the PCIM, the PCIM for the panel's analyses, the canonical truth pack / memory file for a root-level mirror."""
    rel = str(rel).replace("\\", "/")
    if rel.startswith(FINANCIALS_DIR) or re.match(r"fy\d{2}/", rel):
        return []
    deps = sorted(str(p.relative_to(company_dir)) for p in (company_dir / FINANCIALS_DIR).rglob("*.json") if p.name != "authority_manifest.json") if (company_dir / FINANCIALS_DIR).exists() else []
    if rel.startswith("company_memory/investor_panel/") or rel == "company_memory/pcim_v1.json":
        deps += [d for d in ("company_memory/cim_v1.json",) if (company_dir / d).exists() and rel != d]
    if rel.startswith("company_memory/investor_panel/") and (company_dir / "company_memory/pcim_v1.json").exists():
        deps.append("company_memory/pcim_v1.json")
    if rel in {"company_memory/cim_v1.json"}:
        deps = [d for d in deps if d != rel]
    return deps


def _scope_of(rel: str) -> Tuple[str, str]:
    match = re.match(r"(fy\d{2})/", str(rel).replace("\\", "/"))
    return ("year", match.group(1)) if match else ("company", "")


def company_artifact_paths(company_dir: Path | str) -> List[str]:
    """Every financial-derived artifact that exists now: company-level projections and each year's ratios / growth / quality / normalized files."""
    company_dir = Path(company_dir)
    found: List[str] = []
    for pattern in FINANCIAL_DEPENDENT_FILES:
        target = company_dir / pattern
        if pattern.endswith("/"):
            found += [str(p.relative_to(company_dir)) for p in sorted(target.rglob("*.json"))] if target.exists() else []
        elif target.exists():
            found.append(pattern)
    for year_dir in sorted(company_dir.glob("fy*")):
        found += [f"{year_dir.name}/financials/{name}" for name in YEAR_ARTIFACTS if (year_dir / "financials" / name).exists()]
    return found


def bind_company(company_dir: Path | str, *, output_root: Path | str, authorize_served_write: bool = False, rebind: bool = False) -> Dict[str, Any]:
    """Record every financial-derived artifact of the company against the current registries (the last step of a build). An artifact whose record still matches its content keeps that
    record - and so the inputs it was actually built from - unless `rebind` is asked for: a final bind must not vouch for a file that was built from other inputs."""
    company_dir = Path(company_dir)
    recorded = (read_manifest(company_dir).get("artifacts") or {}) if not rebind else {}
    todo = [rel for rel in company_artifact_paths(company_dir)
            if rebind or rel not in recorded or recorded[rel].get("sha256") != sha256_bytes((company_dir / rel).read_bytes()) or "depends_on" not in recorded[rel]]
    return record_artifacts(company_dir, todo, output_root=output_root, authorize_served_write=authorize_served_write)


def check_artifact(company_dir: Path | str, rel_path: str, authority: Optional[CompanyAuthority] = None) -> Tuple[str, str]:
    """(status, reason): valid | unbound | stale | tampered | no_authority | missing."""
    company_dir = Path(company_dir)
    authority = authority or load_company_authority(company_dir)
    path = company_dir / rel_path
    if not path.exists():
        return "missing", "the artifact does not exist"
    if authority.state != "valid":
        return "no_authority", "no financial fact registry exists for this company: nothing derived from financial facts can be vouched for"
    entry = (read_manifest(company_dir).get("artifacts") or {}).get(str(rel_path))
    if not entry:
        return "unbound", "no record of the registries this artifact was built against"
    scope = _scope_of(rel_path)
    current = authority.years[scope[1]].fingerprint if scope[0] == "year" and scope[1] in authority.years else authority.fingerprint
    if scope[0] == "year" and scope[1] not in authority.years:
        return "no_authority", f"the registry of {scope[1]} does not exist"
    if entry.get("authority_fingerprint") != current:
        return "stale", "built against registries that are not the current ones"
    if entry.get("sha256") != sha256_bytes(path.read_bytes()):
        return "tampered", "the content changed after it was recorded"
    for dep, recorded in (entry.get("depends_on") or {}).items():
        dep_path = company_dir / dep
        if not dep_path.exists():
            return "stale", f"it was built from {dep}, which no longer exists"
        if sha256_bytes(dep_path.read_bytes()) != recorded:
            return "stale", f"it was built from a different {dep} than the one now present"
    return "valid", ""


# ---- structural walk: metric points inside any financial projection ---------------------------------------------------------------------------------------------------------------------

def _year_of(node: Dict[str, Any], inherited: str) -> str:
    for key in _YEAR_KEYS:
        found = _year_key(node.get(key)) if node.get(key) else ""
        if found:
            return found
    return inherited


def iter_metric_points(node: Any, path: str = "", metric: str = "", year: str = "", skip_diagnostics: bool = True, known: frozenset = frozenset()) -> Iterator[Tuple[str, str, str, Dict[str, Any], str]]:
    """Yield (path, metric, fiscal_year, holder, value_key) for every numeric metric value. A metric identity is inherited by everything beneath it: a `metric` / `metric_id` / `field`
    entry of an ancestor, or the KEY of a mapping when that key is a known metric name (`metric_series/total_debt/3`, `trend_groups/debt/total_debt/series/1`) - so a year/value point in a
    nested array is attributed to its PARENT metric, never judged by its number alone. The year is likewise inherited from `year`/`fiscal_year`/`period` ancestors. Blocks that list
    rejected figures as diagnostics are skipped."""
    if isinstance(node, dict):
        metric = next((str(node[k]) for k in _METRIC_KEYS if isinstance(node.get(k), str) and node.get(k)), metric)
        year = _year_of(node, year)
        for key in _VALUE_KEYS:
            value = node.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and metric:
                yield path, metric, year, node, key
        for key, child in node.items():
            if skip_diagnostics and key in DIAGNOSTIC_KEYS:
                continue
            yield from iter_metric_points(child, f"{path}/{key}", str(key) if str(key) in known and isinstance(child, (dict, list)) else metric, year, skip_diagnostics, known)
    elif isinstance(node, list):
        for index, child in enumerate(node):
            yield from iter_metric_points(child, f"{path}/{index}", metric, year, skip_diagnostics, known)


def verification_index(company_dir: Path | str) -> Dict[Tuple[str, str], str]:
    """{(fiscal_year, metric): verification status} from each year's financial_fact_verification.json (written by tools/verify_vs_filing.py stamp), when it exists."""
    index: Dict[Tuple[str, str], str] = {}
    for year_dir in sorted(Path(company_dir).glob("fy*")):
        path = year_dir / "financials" / "financial_fact_verification.json"
        try:
            verdicts = json.loads(path.read_text(encoding="utf-8")).get("verdicts") or {}
        except (OSError, ValueError, AttributeError):
            continue
        index.update({(year_dir.name, metric): str(v.get("status")) for metric, v in verdicts.items() if isinstance(v, dict)})
    return index


def annotate_projection(payload: Any, company_dir: Path | str, authority: Optional["CompanyAuthority"] = None) -> int:
    """Carry each registry metric point's verification state into a projection (CIM, PCIM, trends): a point that was checked against the filing says so, one that was not says
    NOT_INDEPENDENTLY_VERIFIED, so the uncertainty a consumer must keep survives the copy. Returns the number of points annotated."""
    authority = authority or load_company_authority(company_dir)
    index = verification_index(company_dir)
    count = 0
    known = known_metrics(authority)
    for _path, metric, year, holder, _key in iter_metric_points(payload, known=known):
        if year and metric in known and "verification_status" not in holder:
            holder["verification_status"] = index.get((year, metric), "NOT_INDEPENDENTLY_VERIFIED")
            count += 1
    return count


def known_metrics(authority: "CompanyAuthority") -> frozenset:
    return frozenset(m for y in authority.years.values() for m in (*y.usable, *y.rejected))


def carries_financial_evidence(payload: Any) -> bool:
    """Does the payload assert financial facts (metric points, or a stored 'financial panel ready')? Only such an artifact depends on the registries; one that carries no financial
    evidence (a business summary, an empty stub) has nothing to vouch for."""
    if isinstance(payload, dict) and payload.get("financial_panel_ready") is True:
        return True
    return next(iter_metric_points(payload), None) is not None or _has_metric_keyed_series(payload)


def _has_metric_keyed_series(payload: Any) -> bool:
    """Trend-style payloads key their series by metric name with no metric field on the points; a payload that holds year/value points anywhere carries financial evidence."""
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if any(isinstance(node.get(k), (int, float)) and not isinstance(node.get(k), bool) for k in ("value", "value_crore")) and any(node.get(k) for k in ("year", "fiscal_year")):
                return True
            stack.extend(v for k, v in node.items() if k not in DIAGNOSTIC_KEYS and isinstance(v, (dict, list)))
        elif isinstance(node, list):
            stack.extend(v for v in node if isinstance(v, (dict, list)))
    return False


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.0051, 5e-4 * max(abs(a), abs(b)))


def contradictions(payload: Any, authority: CompanyAuthority, *, default_year: str = "") -> List[Dict[str, Any]]:
    """Points whose (metric, year) the registry REJECTS, or whose value is not the usable fact's value. A point is judged by its parent metric identity and its year, never by its
    number alone: an unrelated metric that happens to share a value is untouched."""
    found = []
    for path, metric, year, holder, key in iter_metric_points(payload, year=default_year, known=known_metrics(authority)):
        if not year or "/comparatives" in path:
            continue                     # a comparative column is a LATER report's statement of an earlier year (a restatement is not a contradiction of the registry's filed figure)
        verdict = authority.verdict(metric, year)
        value = holder[key]
        if verdict == "rejected":
            found.append({"path": path, "metric": metric, "fiscal_year": year, "value": value, "reason": "the registry rejects this metric for the year"})
        elif verdict == "usable":
            fact = authority.year(year).usable[metric]
            if isinstance(fact.get("value"), (int, float)) and key in {"value", "value_crore"} and not fact.get("derived") and not _close(float(value), float(fact["value"])):
                found.append({"path": path, "metric": metric, "fiscal_year": year, "value": value, "reason": f"the registry's usable value is {fact['value']}"})
    return found


# ---- recording as artifacts are written ------------------------------------------------------------------------------------------------------------------------------------------------

def _company_dir_of(path: Path) -> Optional[Path]:
    parts = Path(path).resolve().parts
    for index in range(len(parts) - 1, 0, -1):
        if parts[index] == "company_memory" or re.fullmatch(r"fy\d{2}", parts[index]):
            return Path(*parts[:index])
    return None


def _record_on_write(root: Any, path: Path) -> None:
    path = Path(path)
    if path.suffix != ".json" or path.name == "authority_manifest.json":
        return
    company_dir = _company_dir_of(path)
    if company_dir is None:
        return
    rel = str(path.resolve().relative_to(company_dir.resolve()))
    if rel.replace("\\", "/").endswith(f"financials/{REGISTRY_NAME}"):
        year = rel.split("/")[0]
        _record(company_dir, [f"{year}/financials/{n}" for n in YEAR_ARTIFACTS if (company_dir / year / "financials" / n).exists()], root)
        return
    if is_financial_dependent(rel) or (re.match(r"fy\d{2}/financials/", rel) and path.name in YEAR_ARTIFACTS):
        if load_company_authority(company_dir).state == "valid":
            _record(company_dir, [rel], root)


try:                                                   # registered once, on first import of the gate (every financial reader and writer imports it)
    from core.context_paths import register_post_write_hook
    register_post_write_hook(_record_on_write)
except ImportError:                                    # pragma: no cover
    pass


def load_vouched(path: Path | str) -> Dict[str, Any]:
    """Read a financial-derived JSON artifact for a consumer: its content if it was built against the current registries and is untouched, {} otherwise. An artifact that carries no
    financial evidence has nothing to vouch for and is returned as is. A missing or unreadable file is {} (the caller's existing 'absent' handling applies)."""
    path = Path(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    company_dir = _company_dir_of(path)
    if company_dir is None or not carries_financial_evidence(payload):
        return payload
    try:
        rel = str(path.resolve().relative_to(company_dir.resolve()))
    except ValueError:
        return {}
    return payload if check_artifact(company_dir, rel)[0] == "valid" else {}
