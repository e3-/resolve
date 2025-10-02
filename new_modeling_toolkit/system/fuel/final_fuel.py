from typing import ClassVar
from typing import Optional
from typing import Union

import pandas as pd
from pydantic import Field
from pydantic import model_validator

from new_modeling_toolkit.core import component
from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core import three_way_linkage
from new_modeling_toolkit.core.custom_model import get_units
from new_modeling_toolkit.core.temporal import timeseries as ts


class FinalFuel(component.Component):
    """
    A final fuel represents a type of energy that can be consumed by a device, or by an energy demand subsector.
    A final fuel may represent several unique fuels-- for example, the "diesel" final fuel might actually represent
    the sum of fossil diesel and renewable diesel. The purpose of a final fuel is to aggregate all fuels which have
    common combustion characteristics from the perspective of a device or energy demand subsector. The term "final"
    refers to the fact that this is the fuel that is seen at the "final" point in the energy supply chain, i.e.
    the point of combustion.

    This component exists mainly so that the fuel share of service demand for devices can be specified via a linkage
    to fuels. The fuel_switchings attribute defined on a three-way linkage between final fuels and energy demand subsectors
    that dictates the extent, efficiency, and cost of fuel switching within a given energy demand subsector. Fuel
    efficiency occurs after fuel switching.
    """

    SAVE_PATH: ClassVar[str] = "products/final_fuels"

    ######################
    # Mapping Attributes #
    ######################
    ccs_plants: dict[str, linkage.Linkage] = {}
    devices: dict[str, linkage.Linkage] = {}
    energy_demand_subsectors: dict[str, linkage.Linkage] = {}
    negative_emissions_technologies: dict[str, linkage.Linkage] = {}
    fuel_switchings: Optional[dict[Union[tuple[str, str], str], three_way_linkage.ThreeWayLinkage]] = None
    candidate_fuels: dict[str, linkage.Linkage] = {}
    policies: dict[str, linkage.Linkage] = {}
    sector_candidate_fuel_blending: Optional[dict[Union[tuple[str, str], str], three_way_linkage.ThreeWayLinkage]] = (
        None
    )
    energy_demand_subsector_to_final_fuel_to_ccs_plant: Optional[
        dict[Union[tuple[str, str], str], three_way_linkage.ThreeWayLinkage]
    ] = None
    fuel_zones: dict[str, linkage.Linkage] = {}

    ######################
    # Attributes #
    ######################
    annual_demand: Optional[ts.NumericTimeseries] = Field(
        None,
        default_freq="H",
        up_method="interpolate",
        down_method="sum",
        units=get_units,
        description="Annual fuel demand.",
    )

    demand: Optional[ts.NumericTimeseries] = Field(
        None,
        default_freq="H",
        up_method="interpolate",
        down_method="sum",
        units=get_units,
        description="Annual fuel demand.",
    )

    @property
    def candidate_fuels_list(self) -> list["CandidateFuel"]:
        """

        Returns: list of CandidateFuel components linked to the FinalFuel object

        """
        return self._return_linkage_list("candidate_fuels")

    ######################
    # Attributes #
    ######################

    # used to make sure demand for electricity is not included in fuels optimization
    fuel_is_electricity: bool = False

    fuel_price_per_mmbtu_override: Optional[ts.NumericTimeseries] = Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units
    )
    fuel_is_using_emissions_trajectory_override: bool = False

    def calc_energy_demand_cost_and_emissions(self, sector: str, energy_demand: pd.Series):
        """
        Loop through CandidateFuels linked to the FinalFuel. For each candidate fuel, calculate the energy demand.
        Then loop through each pollutant on each candidate fuel and calculate emissions by pollutant type.
        Results are temporarily saved on the linkages (ex: FinalFuelToCandidateFuel and CandidateFuelToPollutant).
        After looping, results are then aggregated (by calling the `self._return_{result type}_by_candidate_fuel' functions) and saved permanently on the linked component.
        Another option is to save aggregated results on the 1:1 XToFinalFuel linkage because it will not be overwritten.

        Args:
            sector: name of sector for filtering. Ex: "Residential" or "Industrial"
            energy_demand: pd.Series of energy demand of FinalFuel in mmbtu

        Returns:

        """
        for c in self.candidate_fuels_list:
            # calculate energy demand by candidate fuel
            candidate_ed = c.calc_energy_demand(sector, energy_demand)
            # calculate fuel cost by candidate fuel
            c.calc_fuel_cost(candidate_ed)
            # calculate emissions by pollutant type for each candidate fuel
            for p in c.pollutant_list:
                cp_linkage = c.pollutants[p.name]
                p.calc_emissions(cp_linkage, candidate_ed)

    @model_validator(mode="after")
    def validate_emissions_trajectory_override_fuel(self):
        """
        Validate that fuel is electricity if emissions trajectory override is being used
        """
        if self.fuel_is_using_emissions_trajectory_override and not self.fuel_is_electricity:
            raise NotImplementedError(
                "Error in final fuel {}: emissions trajectory override is not implemented for fuels other "
                "than electricity".format(self.name)
            )

        return self
