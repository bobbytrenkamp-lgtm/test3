"""Governed, immutable analytical feature tables built from warehouse evidence."""

from .builder import FeatureBuildResult, build_feature_table
from .panel import FeaturePanel
from .registry import FEATURE_REGISTRY, FeatureSpec, registry_fingerprint

__all__ = (
    "FEATURE_REGISTRY", "FeatureBuildResult", "FeaturePanel", "FeatureSpec",
    "build_feature_table", "registry_fingerprint",
)
