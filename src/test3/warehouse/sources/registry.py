from __future__ import annotations

from .bea import BEARegional
from .bls import BLSLAUS
from .building_permits import CensusBuildingPermits
from .census import CensusACS
from .census_crosswalk import CensusCBSACrosswalk
from .fred import FredPublic
from .hud import HUDFairMarketRents

SOURCE_ADAPTERS = {adapter.source_id: adapter for adapter in (CensusACS(), BLSLAUS(), BEARegional(), FredPublic(), CensusBuildingPermits(), CensusCBSACrosswalk(), HUDFairMarketRents())}
ALIASES = {"census": "census_acs", "bls": "bls_laus_ces", "bea": "bea_regional", "fred": "fred_public", "building_permits": "census_bps", "crosswalk": "census_cbsa_crosswalk", "hud": "hud_public"}


def get_adapter(source: str):
    source_id = ALIASES.get(source, source)
    try:
        return SOURCE_ADAPTERS[source_id]
    except KeyError as exc:
        raise ValueError(f"no automatic public-data adapter for {source}") from exc
