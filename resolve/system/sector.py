from typing import ClassVar
from typing import Dict
from typing import Optional
from typing import Union

from resolve.core import component
from resolve.core.linkage import Linkage
from resolve.core.three_way_linkage import ThreeWayLinkage


class Sector(component.Component):
    """This class defines a Sector object and its methods."""

    SAVE_PATH: ClassVar[str] = "sectors"

    ######################
    # Mapping Attributes #
    ######################
    building_shell_subsectors: Optional[Dict[str, Linkage]] = None
    stock_rollover_subsectors: dict[str, Linkage] = {}
    energy_demand_subsectors: dict[str, Linkage] = {}
    non_energy_subsectors: dict[str, Linkage] = {}
    sector_candidate_fuel_blending: Optional[dict[Union[tuple[str, str], str], ThreeWayLinkage]] = None
    negative_emissions_technologies: dict[str, Linkage] = {}
