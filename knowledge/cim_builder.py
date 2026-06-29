import json

from core.context_paths import (
    extraction_path,
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