from models import CapexProject


def merge_projects(projects):

    consolidated = {}

    for project in projects:

        key = (
            project.project_name
            or project.location
            or "unknown"
        )

        if key not in consolidated:
            consolidated[key] = project.model_copy()

        else:
            existing = consolidated[key]

            for field, value in project.model_dump().items():

                if value is not None:

                    if getattr(existing, field) is None:
                        setattr(existing, field, value)

    return list(consolidated.values())