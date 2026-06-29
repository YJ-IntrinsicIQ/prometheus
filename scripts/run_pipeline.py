import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from extractors.capex_extractor import extract_capex
from consolidators.capex_consolidator import merge_projects

chunks = [

"""
The company plans to invest ₹500 Cr
in a new Gujarat manufacturing facility.
""",

"""
The project is expected to increase
cable production capacity by 40%.
""",

"""
Commercial production is expected
to begin by FY28.
"""
]

all_projects = []

for chunk in chunks:

    project = extract_capex(chunk)

    print("\nRAW EXTRACTION:")
    print(project)

    all_projects.append(project)

merged_projects = merge_projects(
    all_projects
)

print("\nMERGED PROJECTS:")
print(merged_projects)
    