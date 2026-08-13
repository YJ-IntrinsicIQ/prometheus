"""Risk Evolution output writing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def write_json_file(
    path: Path,
    data: Dict[str, Any] | List[Any],
    indent: int = 2,
    sort_keys: bool = False,
) -> None:
    """Write a JSON file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to temp file first
    temp_path = path.with_suffix(".tmp")
    
    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, sort_keys=sort_keys, default=str)
    
    # Atomic move
    temp_path.replace(path)


def write_risk_registry(
    path: Path,
    risks: List[Dict[str, Any]],
    metadata: Dict[str, Any] | None = None,
) -> None:
    """Write the risk registry JSON file."""
    payload = {
        **(metadata or {}),
        "risks": risks,
    }
    
    write_json_file(path, payload)


def write_risk_timelines(
    path: Path,
    timelines: List[Dict[str, Any]],
    metadata: Dict[str, Any] | None = None,
) -> None:
    """Write the risk timelines JSON file."""
    payload = {
        **(metadata or {}),
        "timelines": timelines,
    }
    
    write_json_file(path, payload)


def write_risk_assessments(
    path: Path,
    assessments: List[Dict[str, Any]],
    metadata: Dict[str, Any] | None = None,
) -> None:
    """Write the risk assessments JSON file."""
    payload = {
        **(metadata or {}),
        "assessments": assessments,
    }
    
    write_json_file(path, payload)


def write_risk_validation(
    path: Path,
    validation_report: Dict[str, Any],
) -> None:
    """Write the risk validation report JSON file."""
    write_json_file(path, validation_report)


def write_risk_manifest(
    path: Path,
    manifest: Dict[str, Any],
) -> None:
    """Write the risk manifest JSON file."""
    write_json_file(path, manifest)


def write_all_risk_outputs(
    company_root: Path,
    risks: List[Dict[str, Any]],
    timelines: List[Dict[str, Any]],
    assessments: List[Dict[str, Any]],
    validation_report: Dict[str, Any],
    manifest: Dict[str, Any],
) -> Dict[str, Path]:
    """
    Write all risk evolution artifacts.
    
    Returns a dict mapping artifact names to their written paths.
    """
    # Create risk directory
    risk_dir = company_root / "company_memory" / "risks"
    risk_dir.mkdir(parents=True, exist_ok=True)
    
    output_paths = {}
    metadata = {
        "company": manifest.get("company_slug") or manifest.get("company"),
        "generated_at": manifest.get("generated_at"),
        "generator_version": manifest.get("generator_version"),
    }
    metadata = {key: value for key, value in metadata.items() if value}
    
    # Write each artifact
    registry_path = risk_dir / "risk_registry.json"
    write_risk_registry(registry_path, risks, metadata)
    output_paths["risk_registry.json"] = registry_path
    
    timelines_path = risk_dir / "risk_timelines.json"
    write_risk_timelines(timelines_path, timelines, metadata)
    output_paths["risk_timelines.json"] = timelines_path
    
    assessments_path = risk_dir / "risk_assessments.json"
    write_risk_assessments(assessments_path, assessments, metadata)
    output_paths["risk_assessments.json"] = assessments_path
    
    validation_path = risk_dir / "risk_validation.json"
    write_risk_validation(validation_path, validation_report)
    output_paths["risk_validation.json"] = validation_path
    
    manifest_path = risk_dir / "risk_manifest.json"
    write_risk_manifest(manifest_path, manifest)
    output_paths["risk_manifest.json"] = manifest_path
    
    return output_paths


def print_risk_summary(
    company: str,
    risks: List[Dict[str, Any]],
    validation: Dict[str, Any],
) -> None:
    """Print a concise summary of the risk evolution run."""
    
    # Count statuses
    status_counts = {}
    for risk in risks:
        status = risk.get("current_status", "unable_to_verify")
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print("\n[RISK EVOLUTION]")
    print(f"Company: {company}")
    print(f"Risks detected: {len(risks)}")
    
    for status in ["emerging", "increasing", "persistent", "stable", "reducing", "mitigated", "resolved", "unable_to_verify"]:
        count = status_counts.get(status, 0)
        if count > 0:
            print(f"  {status}: {count}")
    
    # Count materiality
    high = sum(1 for r in risks if r.get("materiality", {}).get("level") == "high")
    if high > 0:
        print(f"High materiality: {high}")
    
    # Validation status
    val_status = validation.get("status", "unknown")
    print(f"Validation: {val_status.upper()}")
    
    if validation.get("error_count", 0) > 0:
        print(f"  Errors: {validation.get('error_count')}")
    
    if validation.get("warning_count", 0) > 0:
        print(f"  Warnings: {validation.get('warning_count')}")
