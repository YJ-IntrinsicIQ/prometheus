import json

from core.context_paths import (
    extraction_path,
    intelligence_path,
)

from pipelines.pipeline_context import (
    get_context,
)

from knowledge.cim import (
    initialize_cim,
    save_cim,
    get_section
)

from knowledge.constants import (
    ENTITY_CONFIG,
)

from knowledge.ids import (
    generate_id,
)

from knowledge.evidence import (
    build_observation,
    build_evidence,
)

from knowledge.entity_matcher import (
    find_matching_entity,
)
from knowledge.question_engine import QuestionRegistry

def get_company():

    return get_context().company


def get_year():

    return get_context().year

# ============================================================
# IO
# ============================================================

def load_json(filename):

    path = extraction_path(filename)

    if not path.exists():

        return []

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as f:

        return json.load(f)


def load_intelligence_json(filename):

    path = intelligence_path(filename)

    if not path.exists():

        return {}

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as f:

        return json.load(f)

def load_clean_data():

    return {

        "project":
            load_json(
                "clean_projects.json"
            ),

        "promise":
            load_json(
                "clean_promises.json"
            ),

        "risk":
            load_json(
                "clean_risks.json"
            ),

        "capacity":
            load_json(
                "clean_capacity.json"
            ),

        "capital_allocation":
            load_json(
                "clean_capital_allocation.json"
            ),

        "initiative":
            load_json(
                "clean_initiatives.json"
            ),
    }


def load_business_artifacts():

    return {
        "business_blueprint": load_intelligence_json("business_blueprint.json"),
        "business_classification": load_intelligence_json("business_classification.json"),
        "module_results": load_intelligence_json("module_results.json"),
        "discovery_runtime": load_intelligence_json("discovery_runtime.json"),
    }

# ============================================================
# Metadata
# ============================================================

def populate_metadata(cim):

    cim["metadata"]["company"] = get_company()

    cim["metadata"]["year"] = get_year()

    cim["metadata"]["document_type"] = "annual_report"

    return cim

def register_document(cim):

    cim["documents"].append(

        {

            "id":
                generate_id(
                    "document"
                ),

            "company":
                get_company(),

            "year":
                get_year(),

            "document_type":
                "annual_report",
        }
    )

    return cim


def populate_business_section(cim, artifacts):

    business = cim["business"]
    blueprint = artifacts.get("business_blueprint") or {}
    classification = artifacts.get("business_classification") or {}
    module_results = artifacts.get("module_results") or {}
    discovery_runtime = artifacts.get("discovery_runtime") or {}

    business_understanding = blueprint.get("business_understanding") or {}
    characteristics = blueprint.get("characteristics") or []
    dna_values = classification.get("business_dnas") or []
    question_modules = _resolve_question_modules(
        classification.get("question_modules") or [],
        dna_values,
    )
    executed_modules = discovery_runtime.get("executed_modules") or []

    report_template = _resolve_report_template(
        classification.get("report_template"),
        dna_values,
    )

    if dna_values or question_modules or report_template:
        business["dna"] = {
            "business_dnas": dna_values,
            "question_modules": question_modules,
            "report_template": report_template,
        }

    industry_profile = {}
    if business_understanding.get("business_summary"):
        industry_profile["business_summary"] = business_understanding["business_summary"]
    if business_understanding.get("business_model"):
        industry_profile["business_model"] = business_understanding["business_model"]
    if business_understanding.get("value_creation"):
        industry_profile["value_creation"] = business_understanding["value_creation"]
    if characteristics:
        industry_profile["characteristics"] = [
            item.get("name")
            for item in characteristics
            if isinstance(item, dict) and item.get("name")
        ]
    metadata = blueprint.get("metadata") or {}
    if metadata.get("version"):
        industry_profile["blueprint_version"] = metadata.get("version")
    if metadata.get("confidence") is not None:
        industry_profile["confidence"] = metadata.get("confidence")
    if industry_profile:
        business["industry_profile"] = industry_profile

    competitive_position = {}
    if business_understanding.get("competitive_position"):
        competitive_position["summary"] = business_understanding["competitive_position"]
    supporting_modules = []
    if executed_modules:
        supporting_modules.extend(executed_modules)
    elif isinstance(module_results, dict):
        module_results_items = module_results.get("module_results") or []
        if module_results_items:
            supporting_modules.extend([
                item.get("module_id")
                for item in module_results_items
                if isinstance(item, dict) and item.get("module_id")
            ])
    supporting_modules.extend(question_modules)
    supporting_modules = list(
        dict.fromkeys(
            module_id
            for module_id in supporting_modules
            if module_id
        )
    )
    if supporting_modules:
        competitive_position["supporting_modules"] = supporting_modules
    if competitive_position:
        business["competitive_position"] = competitive_position

    return cim


def _resolve_question_modules(current_modules, business_dnas):
    registry = QuestionRegistry()
    resolved = []

    for module_id in current_modules or []:
        resolved_id = registry.resolve_module_id(module_id)
        if resolved_id:
            resolved.append(resolved_id)

    for module in registry.modules_for_dnas(business_dnas or []):
        resolved.append(module.module_id)

    return list(dict.fromkeys(module_id for module_id in resolved if module_id))


def _resolve_report_template(current_template, business_dnas):

    if current_template and current_template != "generic_v1":
        return current_template

    dna_set = set(
        business_dnas or []
    )

    if "Semiconductor" in dna_set:
        return "semiconductor_v1"

    if dna_set.intersection({"IP Library", "Platform Monetization", "Consumer"}):
        return "media_v1"

    if "Manufacturing" in dna_set:
        return "manufacturing_v1"

    return current_template

# ============================================================
# Entity Builders
# ============================================================

def build_entity(entity_type, record):
    """
    Convert a cleaned extraction record into a canonical PCIM entity.
    """

    config = ENTITY_CONFIG[entity_type]

    entity = record.copy()

    entity["id"] = generate_id(entity_type)

    entity.setdefault("confidence", "medium")

    entity["observations"] = []

    entity["relationships"] = []

    entity["metadata"] = {
        "entity_type": entity_type,
        "company": get_company(),
        "year": get_year(),
    }

    return entity


def build_entity_evidence(record):
    """
    Create the initial evidence object for an extracted record.
    """

    return build_evidence(

        document_id=None,

        document_type="annual_report",

        page=record.get("page"),

        chunk_id=record.get("chunk_id"),

        source_file=record.get("source_file"),

        confidence=record.get(
            "confidence",
            "medium",
        ),
    )

# ============================================================
# Generic Processing
# ============================================================

def process_entity_type(
    cim,
    entity_type,
    records,
):
    """
    Generic processor for every entity type.
    """

    config = ENTITY_CONFIG[entity_type]

    section = config["section"]

    bucket = get_section(
        cim,
        section,
    )

    entities = bucket["items"]

    for record in records:

        existing = find_matching_entity(

            entity_type,

            entities,

            record,
        )

        evidence = build_entity_evidence(
            record
        )

        observation = build_observation(

            year=get_year(),

            summary=record.get(
                config["name_field"]
            ),

            evidence=[evidence],
        )

        if existing:

            existing["observations"].append(
                observation
            )

            continue

        entity = build_entity(

            entity_type,

            record,
        )

        entity["observations"].append(
            observation
        )

        entities.append(entity)

    return cim

# ============================================================
# Individual Entity Types
# ============================================================

def process_projects(
    cim,
    records,
):

    return process_entity_type(
        cim,
        "project",
        records,
    )


def process_promises(
    cim,
    records,
):

    return process_entity_type(
        cim,
        "promise",
        records,
    )


def process_risks(
    cim,
    records,
):

    return process_entity_type(
        cim,
        "risk",
        records,
    )


def process_capacity(
    cim,
    records,
):

    return process_entity_type(
        cim,
        "capacity",
        records,
    )


def process_capital_allocation(
    cim,
    records,
):

    return process_entity_type(
        cim,
        "capital_allocation",
        records,
    )


def process_initiatives(
    cim,
    records,
):

    return process_entity_type(
        cim,
        "initiative",
        records,
    )

# ============================================================
# Finalization
# ============================================================

def update_statistics(cim):
    """
    Update statistics for every entity bucket.
    """

    for config in ENTITY_CONFIG.values():

        section = config.get("section")

        if section is None:
            continue

        bucket = get_section(
            cim,
            section,
        )

        if "items" not in bucket:
            continue

        items = bucket["items"]

        bucket["statistics"] = {

            "count": len(items),

            "high_confidence": sum(
                1
                for entity in items
                if entity.get("confidence") == "high"
            ),

            "medium_confidence": sum(
                1
                for entity in items
                if entity.get("confidence") == "medium"
            ),

            "low_confidence": sum(
                1
                for entity in items
                if entity.get("confidence") == "low"
            ),
        }

    return cim


def finalize_cim(cim):

    cim = update_statistics(cim)

    save_cim(cim)

    return cim

# ============================================================
# Pipeline
# ============================================================

def build_company_intelligence():

    cim = initialize_cim()

    populate_metadata(cim)

    register_document(cim)

    clean_data = load_clean_data()
    business_artifacts = load_business_artifacts()

    populate_business_section(
        cim,
        business_artifacts,
    )

    process_projects(
        cim,
        clean_data["project"],
    )

    process_promises(
        cim,
        clean_data["promise"],
    )

    process_risks(
        cim,
        clean_data["risk"],
    )

    process_capacity(
        cim,
        clean_data["capacity"],
    )

    process_capital_allocation(
        cim,
        clean_data["capital_allocation"],
    )

    process_initiatives(
        cim,
        clean_data["initiative"],
    )

    finalize_cim(cim)

    return cim

def main():

    cim = build_company_intelligence()

    print()

    print("=" * 60)

    print("COMPANY INTELLIGENCE MODEL CREATED")

    print("=" * 60)

    print()

    print(
        f"Company : {cim['metadata']['company']}"
    )

    print(
        f"Year    : {cim['metadata']['year']}"
    )

    print()

    print("Entity Counts")

    print(
        "Projects            :",
        len(
            cim["operations"]["projects"]["items"]
        ),
    )

    print(
        "Promises            :",
        len(
            cim["management"]["promises"]["items"]
        ),
    )

    print(
        "Risks               :",
        len(
            cim["risk"]["identified"]["items"]
        ),
    )

    print(
        "Capacity            :",
        len(
            cim["operations"]["capacity"]["items"]
        ),
    )

    print(
        "Capital Allocation  :",
        len(
            cim["financial"]["capital_allocation"]["items"]
        ),
    )

    print(
        "Initiatives         :",
        len(
            cim["operations"]["initiatives"]["items"]
        ),
    )

    print()

    print("company_intelligence.json generated successfully.")

    print()


if __name__ == "__main__":

    main()
