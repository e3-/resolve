# This file defines two fuel classes. Candidate fuels are options (e.g. biodiesel, fossil diesel)
# for different ways to make a final fuel (e.g. diesel).
from typing import Optional

import pandas as pd
from pydantic import condecimal
from pydantic import Field
from pydantic import root_validator

from new_modeling_toolkit import get_units
from new_modeling_toolkit.core import component
from new_modeling_toolkit.core import dir_str
from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core import three_way_linkage
from new_modeling_toolkit.core.temporal import timeseries as ts


class CandidateFuel(component.Component):
    """A candidate fuel is one type of fuel that can be used to meet a final fuel demand.

    Gasoline is a *final fuel*; E85 ethanol and fossil gasoline are *candidate fuels*.

    Every candidate fuel has three ways in which it can be made, which can be turned on and off via parameters
    as applicable: 1) production from fossil extraction, 2) conversion from a biomass resource, and 3) conversion from
    an electrolytic fuel production tech.

    Methods:
        from_csv: instantiate fuel objects from a csv input file

    TODO: check that either biomass production cost or commodity cost is specified for a given candidate fuel

    """

    ######################
    # Mapping Attributes #
    ######################
    biomass_resources: dict[str, linkage.Linkage] = {}
    electrolyzers: dict[str, linkage.Linkage] = {}
    fuel_storages: dict[str, linkage.Linkage] = {}
    fuel_transportations: dict[str, linkage.Linkage] = {}
    fuel_zones: dict[str, linkage.Linkage] = {}
    emission_types: dict[str, linkage.Linkage] = {}
    fuel_conversion_plants: dict[str, linkage.Linkage] = {}
    final_fuels: dict[str, linkage.Linkage] = {}
    resources: dict[str, linkage.Linkage] = {}
    policies: dict[str, linkage.Linkage] = {}
    pollutants: dict[str, linkage.Linkage] = {}
    sector_candidate_fuel_blending: dict[tuple[str, str], three_way_linkage.ThreeWayLinkage] = {}

    ######################
    # Attributes #
    ######################
    fuel_is_commodity_bool: bool = Field(
        True,
        description='Set to `False` if this fuel is an electrolytic fuel; otherwise, it will be considered a "commodity" fuel with a fixed price stream.',
    )

    # used to make sure demand for electricity is not included in fuels optimization
    fuel_is_electricity: bool = False

    apply_electrofuel_SOC: bool = Field(False, description="Track hourly electrolytical fuel storage.")

    electrofuel_parasitic_loss: Optional[condecimal(ge=0, le=1)] = Field(
        None,
        description="[For candidate fuels that are electrofuels] Hourly state of charge losses,"
        "if SOC constraints are being applied.",
        units=get_units("electrofuel_parasitic_loss"),
    )

    electrofuel_storage_limit_mmbtu: Optional[ts.NumericTimeseries] = Field(
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        description="[For candidate fuels that are electrofuels] Storage reservoir size (mmbtu),"
        "if SOC constraints are being applied",
        units=get_units("electrofuel_storage_limit_mmbtu"),
    )

    # TODO: Rename to something else
    fuel_price_per_mmbtu: Optional[ts.NumericTimeseries] = Field(
        None, default_freq="H", up_method="ffill", down_method="mean", units=get_units("fuel_price_per_mmbtu")
    )

    monthly_price_multiplier: Optional[ts.NumericTimeseries] = Field(
        None, default_freq="M", up_method=None, down_method=None
    )
    annual_price: Optional[ts.NumericTimeseries] = Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units("annual_price")
    )

    @property
    def fuel_production_plants(self):
        if self.electrolyzers is None and self.fuel_conversion_plants is None:
            electrofuel_plants = None
        else:
            electrofuel_plants = (self.electrolyzers or dict()) | (self.fuel_conversion_plants or dict())

        return electrofuel_plants

    @root_validator
    def validate_or_calculate_hourly_fuel_prices(cls, values):
        """Hourly price stream or combination of monthly price shape + annual price shape must be passed.

        # TODO 2022-03-31: This should be rewritten/made more robust. The current implementation should work
                           in most cases but takes a brute-force approach.

        Steps to calculate the monthly price shape from the monthly shape and annual price:
            #. Interpolate & extrapolate annual price to 2000-2100 (this is currently hard-coded)
            #. Resample to monthly
            #. Map monthly price shape to all months in the 2000-2100 time horizon
            #. Multiply annual price by monthly_price_multiplier
        """
        if values["fuel_is_commodity_bool"] == 0:
            assert (values["fuel_price_per_mmbtu"] is None) and (values["annual_price"] is None), (
                "If fuel is not a commodity (i.e., connected to fuel production components), fuel prices should not be "
                "defined"
            )
            return values
        if values["fuel_price_per_mmbtu"] is not None:
            assert not any([values["monthly_price_multiplier"], values["annual_price"]]), (
                f"For {values['name']}, if `fuel_price_per_mmbtu` is provided, `monthly_price_multiplier` and "
                f"`annual_price` cannot be passed."
            )
        elif all([values["monthly_price_multiplier"], values["annual_price"]]):
            assert values["fuel_price_per_mmbtu"] is None, (
                f"For {values['name']}, if `monthly_price_multiplier` and `annual_price` are provided, "
                f"`fuel_price_per_mmbtu` cannot be passed"
            )
            # TODO 2022-03-31: Can just warn that one will be ignored

            # Calculate hourly price shape from two other attributes (first to interpolate annual prices, aligned with
            #   field settings, then to monthly ffill)
            df = values["annual_price"].data.resample("YS").interpolate().resample("H", closed="right").ffill()

            # Multiply by monthly_price_multiplier
            temp = values["monthly_price_multiplier"].data.copy(deep=True)
            temp.index = temp.index.month
            multipliers = pd.Series(df.index.month.map(temp), index=df.index)
            df = df * multipliers

            values["fuel_price_per_mmbtu"] = ts.NumericTimeseries(data=df, name="fuel_price_per_mmbtu")

        else:
            raise ValueError(
                f"For {values['name']}, fuel price can be entered via `fuel_price_per_mmbtu` or by providing both `monthly_price_multiplier` and `annual_price`"
            )

        return values

    production_limit_mmbtu: Optional[ts.NumericTimeseries] = Field(
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        units=get_units("production_limit_mmbtu"),
    )

    opt_candidate_fuel_production_for_final_fuel_demands: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized production for final fuel demands.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )

    opt_candidate_fuel_production_from_biomass_mt: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized candidate fuel production from biomass in metric tons.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )

    opt_candidate_fuel_commodity_production_mmbtu: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized candidate fuel production from commodity pathway in MMBTU.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )

    @root_validator
    def check_fuel_price(cls, values):
        """Check that fuel price is specified if commodity_bool is True."""
        if (values["fuel_is_commodity_bool"] == 1) and (values["fuel_price_per_mmbtu"] is None):
            raise ValueError(
                "Error in fuel {}: fuel_price_per_mmbtu must be specified if fuel_is_commodity_bool is set to 1.".format(
                    values["name"]
                )
            )
        else:
            return values


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

    ######################
    # Mapping Attributes #
    ######################
    ccs_plants: dict[str, linkage.Linkage] = {}
    devices: dict[str, linkage.Linkage] = {}
    energy_demand_subsectors: dict[str, linkage.Linkage] = {}
    negative_emissions_technologies: dict[str, linkage.Linkage] = {}
    fuel_switchings: Optional[dict[tuple[str, str], three_way_linkage.ThreeWayLinkage]] = None
    candidate_fuels: dict[str, linkage.Linkage] = {}
    policies: dict[str, linkage.Linkage] = {}
    sector_candidate_fuel_blending: Optional[dict[tuple[str, str], three_way_linkage.ThreeWayLinkage]] = None
    energy_demand_subsector_to_final_fuel_to_ccs_plant: Optional[
        dict[tuple[str, str], three_way_linkage.ThreeWayLinkage]
    ] = None
    fuel_zones: dict[str, linkage.Linkage] = {}

    ######################
    # Attributes #
    ######################
    name: str

    # used to make sure demand for electricity is not included in fuels optimization
    fuel_is_electricity: bool = False

    demand: Optional[ts.NumericTimeseries] = Field(
        None,
        default_freq="H",
        up_method="interpolate",
        down_method="sum",
        units=get_units,
        description="Annual fuel demand.",
    )
    fuel_price_per_mmbtu_override: Optional[ts.NumericTimeseries] = Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units
    )
    fuel_is_using_emissions_trajectory_override: bool = False

    def revalidate(self):
        # validate that fuel is electricity if emissions trajectory override is being used
        if self.fuel_is_using_emissions_trajectory_override and not self.fuel_is_electricity:
            raise NotImplementedError(
                "Error in final fuel {}: emissions trajectory override is not implemented for fuels other "
                "than electricity".format(self.name)
            )


if __name__ == "__main__":
    # path to data folder
    data_path = dir_str.data_dir / "interim" / "candidate_fuels"
    # instantiate fuel objects
    candidate_fuels = CandidateFuel.from_dir(data_path, scenarios=["base"])

    # path to data folder
    data_path = dir_str.data_dir / "interim" / "final_fuels"
    # instantiate fuel objects
    final_fuels = FinalFuel.from_dir(data_path)
