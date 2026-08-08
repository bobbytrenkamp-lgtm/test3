from __future__ import annotations

from .bea import BEARegional
from .bls import BLSLAUS
from .building_permits import CensusBuildingPermits
from .census import CensusACS
from .fred import FredPublic

SOURCE_ADAPTERS = {adapter.source_id: adapter for adapter in (CensusACS(), BLSLAUS(), BEARegional(), FredPublic(), CensusBuildingPermits())}
ALIASES = {"census": "census_acs", "bls": "bls_laus_ces", "bea": "bea_regional", "fred": "fred_public", "building_permits": "census_bps"}


def get_adapter(source: str):
    source_id = ALIASES.get(source, source)
    try:
        return SOURCE_ADAPTERS[source_id]
    except KeyError as exc:
        raise ValueError(f"no automatic public-data adapter for {source}") from exc
