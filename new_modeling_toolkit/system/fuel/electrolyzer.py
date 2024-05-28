from typing import Optional

from pydantic import Field

from new_modeling_toolkit.common.asset import plant
from new_modeling_toolkit.core.temporal import timeseries as ts


class Electrolyzer(plant.Plant):
    """
    Define an Electrolyzer asset, defined as an asset that can be built to take in
    electricity from the grid to be converted into an electrofuel.

    Asset and Plant attributes:
    - Mapping attributes: zones, proformas, candiate_fuels, reserves
    - Build and retirement attributes: can_build_new, can_retire, physical_lifetime, planned_installed_capacity,
        min_cumulative_new_build, min_op_capacity, potential
    - Operational attributes: ramp_rate, ramp_rate_2_hour, ramp_rate_3_hour, ramp_rate_4_hour,
        td_losses_adjustment, stochastic_outage_rate
    - Cost attributes: financial_lifetime, planned_fixed_om_by_model_year, new_capacity_annualized_all_in_fixed_cost_by_vintage,
        new_capacity_fixed_om_by_vintage
    - Optimization results: opt_operational_planned_capacity_mw, opt_operation_new_capacity_mw,
        opt_annual_fixed_om_cost_dollars, opt_annual_installed_cost_dollars
    """

    ######################
    # Mapping Attributes #
    ######################

    ###################
    # Cost Attributes #
    ###################

    ###################################
    # Operational Dispatch Attributes #
    ###################################
    provide_power_potential_profile: None = None  # Electrolyzer doesn't provide power
    increase_load_potential_profile: ts.FractionalTimeseries = Field(
        ...,
        description="Fixed shape of resource's potential power draw (e.g. flat shape for storage resources)."
        " Used in conjunction with "
        ":py:attr:`new_modeling_toolkit.common.resource.Resource.curtailable`.",
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
    )
    conversion_efficiency: float = Field(
        ..., description="Conversion efficiency of electricity into electrofuel, MMBTU/MWh"
    )

    def revalidate(self):
        if self.fuel_zones is None or len(self.fuel_zones) == 0:
            raise ValueError(
                f"Electrolyzer component `{self.name}` must be linked to a FuelZone in order to "
                f"function properly. Please add an ElectrolyzerToFuelZone linkage to your linkages.csv file."
            )

    ############################
    # Optimization Expressions #
    ############################
    def Candidate_Fuel_Production_From_Fuel_Production_Plant_In_Timepoint_MMBTU_H(
        self, model, candidate_fuel, model_year, rep_period, hour
    ):
        if candidate_fuel in self.candidate_fuels.keys():
            production_from_electrolyzer_in_timepoint_mmbtu = (
                self.conversion_efficiency * model.Increase_Load_MW[self.name, model_year, rep_period, hour]
            )
        else:
            production_from_electrolyzer_in_timepoint_mmbtu = 0.0
        return production_from_electrolyzer_in_timepoint_mmbtu

    def Candidate_Fuel_Production_From_Fuel_Production_Plant_MMBTU(self, resolve_case, model_year, candidate_fuel):
        production_from_electrolyzer_mmbtu = resolve_case.sum_timepoint_to_annual(
            model_year,
            "Candidate_Fuel_Production_From_Fuel_Production_Plant_In_Timepoint_MMBTU_H",
            candidate_fuel,
            self.name,
        )
        return production_from_electrolyzer_mmbtu

    ########################
    # Optimization Results #
    ########################
    opt_annual_embedded_emissions: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Average annual emissions embedded in electricity used to produce electrofuel by electrolyzer (MMTCO2e)",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
    )
    opt_annual_produced_fuel_mmbtu: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized annual fuel production, in MMBtu.",
        up_method=None,
        down_method="annual",
    )
