from __future__ import annotations

from typing import Any, Dict, List

from knowledge.business_blueprint import BusinessBlueprint

from .constants import DEFAULT_DISCOVERY_PROFILE, DEFAULT_EXTRACTION_PROFILE, SUPPORTED_TEMPLATES
from .registry import Registry
from .validator import validate_classification


class BusinessClassifier:
    def __init__(self, registry: Registry | None = None):
        self.registry = registry or Registry()

    def classify(self, blueprint: BusinessBlueprint) -> Dict[str, Any]:
        characteristics = [item.name for item in blueprint.characteristics]
        classification = self.registry.build_profile(characteristics)
        validate_classification(classification)
        return classification
