from typing import ClassVar
from typing import Union

import pandas as pd
import pint
from loguru import logger
from pydantic import Field
from typing_extensions import Annotated

from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core import three_way_linkage
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.custom_model import units
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.system import Asset
from new_modeling_toolkit.system.electric.resources import ThermalResource
from new_modeling_toolkit.system.generics.demand import Demand
from new_modeling_toolkit.system.generics.energy import _EnergyCarrier
from new_modeling_toolkit.system.generics.plant import Plant

class CandidateFuel(_EnergyCarrier):
    """A candidate fuel is one type of fuel that can be used to meet a final fuel demand, be produced by a fuel
    production plant, or consumed by a plant or thermal resource.

    Gasoline is a *final fuel*; E85 ethanol and fossil gasoline are *candidate fuels*.

    Every candidate fuel is either a commodity, which can be parametrized to have an upper limit of availability and
    prices, or can be produced via a fuel conversion plant. Currently, the only form of fuel conversion possible is
    fuel-to-fuel or electricity-to-fuel.

    Methods:
        from_csv: instantiate fuel objects from a csv input file

    """

    SAVE_PATH: ClassVar[str] = "candidate_fuels"
    unit: pint.Unit | str = units.MMBtu

    commodity: Annotated[bool, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        True,
        alias="fuel_is_commodity_bool",
        description=_EnergyCarrier.model_fields["commodity"].description,
    )
    availability: Annotated[
        ts.NumericTimeseries | None,
        Metadata(category=FieldCategory.OPERATIONS, units=units.MMBtu_per_year, excel_short_title="Availability"),
    ] = Field(
        None,
        default_freq="YS",
        up_method="interpolate",
        down_method="sum",
        description=_EnergyCarrier.model_fields["availability"].description,
    )

    ######################
    # Mapping Attributes #
    ######################

    # TODO: Update with "Annotated" syntax
    electrolyzers: dict[str, linkage.Linkage] = {}
    fuel_storages: dict[str, linkage.Linkage] = {}
    fuel_transportations: dict[str, linkage.Linkage] = {}
    fuel_zones: dict[str, linkage.Linkage] = {}
    emission_types: dict[str, linkage.Linkage] = {}
    fuel_production_plants: dict[str, linkage.Linkage] = {}

    # TODO: Used in PATHWAYS. Leave as is, but discuss with broader PATHWAYS team on integration.
    final_fuels: dict[str, linkage.Linkage] = {}

    resources: Annotated[dict[str, linkage.CandidateFuelToResource], Metadata(linkage_order="to")] = {}
    emissions_policies: Annotated[
        dict[str, linkage.EmissionsContribution], Metadata(category=FieldCategory.OPERATIONS, linkage_order="to")
    ] = {}
    annual_energy_policies: Annotated[
        dict[str, linkage.AnnualEnergyStandardContribution],
        Metadata(category=FieldCategory.OPERATIONS, linkage_order="to"),
    ] = {}
    pollutants: dict[str, linkage.Linkage] = {}

    # TODO: Used in PATHWAYS. Leave as is, but discuss with broader PATHWAYS team on integration.
    sector_candidate_fuel_blending: dict[Union[tuple[str, str], str], three_way_linkage.ThreeWayLinkage] = {}

    ###################################
    # Attributes Used in Optimization #
    ###################################

    price_per_unit: Annotated[
        ts.NumericTimeseries | None,
        Metadata(category=FieldCategory.OPERATIONS, units=units.dollar / units.MMBtu, excel_short_title="Price"),
    ] = Field(
        None, default_freq="H", up_method="ffill", down_method="mean", weather_year=False, alias="fuel_price_per_mmbtu"
    )

    monthly_price_multiplier: Annotated[
        ts.NumericTimeseries | None, Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Multiplier")
    ] = Field(None, default_freq="MS", up_method="ffill", down_method="mean")

    annual_price: Annotated[
        ts.NumericTimeseries | None,
        Metadata(category=FieldCategory.OPERATIONS, units=units.dollar / units.MMBtu, excel_short_title="Annual Price"),
    ] = Field(None, default_freq="YS", up_method="interpolate", down_method="sum")

    @property
    def fuel_is_commodity_bool(self):
        return self.commodity

    @property
    def fuel_price_per_mmbtu(self):
        return self.price_per_unit

    # TODO: Used in PATHWAYS. Leave as is, but discuss with broader PATHWAYS team on integration.
    @property
    def final_fuel_name(self):
        return list(self.final_fuels.keys())[0]

    # TODO: Used in PATHWAYS. Leave as is, but discuss with broader PATHWAYS team on integration.
    @property
    def pollutant_list(self):
        return self._return_linkage_list("pollutants")

    @property
    def thermal_resource_instances(self) -> dict[str]:
        return (
            {
                name: linkage.instance_to
                for name, linkage in self.resources.items()
                if isinstance(linkage.instance_to, ThermalResource)
            }
            if self.resources is not None
            else None
        )

    def revalidate(self):
        # Call Product.revalidate()
        super().revalidate()

        # Check that if candidate fuel is linked to annual energy policies, then the thermal resource(s) its linked
        # to is also linked to the same policy
        if self.annual_energy_policies:
            # Give warning if (1) candidate fuel is not linked to any thermal resources
            if not self.thermal_resource_instances:
                logger.warning(
                    f"{self.__class__.__name__} instance {self.name} is linked to AnnualEnergyStandard policies but is "
                    f"not linked to any Thermal Resources that burn the fuel. Check your linkages.csv."
                )
            else:
                # Give warning if (2) candidate fuel's linked thermal resources are not linked to the same policies
                for policy_linkage in self.annual_energy_policies.values():
                    policy = policy_linkage.instance_to
                    if not set(self.thermal_resource_instances.keys()).intersection(set(policy.resources.keys())):
                        logger.warning(
                            f"{self.__class__.__name__} instance {self.name} is linked to the "
                            f"{policy.__class__.__name__} instance {policy.name}, but none of its linked Thermal "
                            f"Resources are linked to this policy. Check our linkages.csv."
                        )

    def _total_consumption(self, block, modeled_year, dispatch_window, timestamp):
        return sum(
            consumer.formulation_block.consumption[self.name, modeled_year, dispatch_window, timestamp]
            for consumer in self.consumers.values()
            if isinstance(consumer, Demand) or (isinstance(consumer, Plant) and consumer.has_operational_rules)
        ) + sum(
            consumer.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
                self.name, modeled_year, dispatch_window, timestamp
            ]
            for consumer in self.consumers.values()
            if hasattr(consumer.formulation_block, "resource_fuel_consumption_in_timepoint_mmbtu")
        )

    # TODO: Used in PATHWAYS. Leave as is, but discuss with broader PATHWAYS team on integration.
    def candidate_fuel_blend(self, sector: str) -> pd.Series:
        """

        Args:
            sector: str of Sector name

        Returns: pd.Series of blend_override data for the input sector name saved on the SectorCandidateFuelBlending ThreeWayLinkage

        """
        return self.sector_candidate_fuel_blending[(sector, self.final_fuel_name)].blend_override.data

    # TODO: Used in PATHWAYS. Leave as is, but discuss with broader PATHWAYS team on integration.
    def calc_energy_demand(self, sector: str, final_fuel_energy_demand: pd.Series) -> pd.Series:
        """
        CandidateFuel energy demand = FinalFuel energy demand * candidate fuel blending %

        Args:
            sector: str of Sector name, used for filtering input data
            final_fuel_energy_demand: pd.Series of energy demand for the FinalFuel

        Returns: pd.Series of energy demand for the CandidateFuel

        """
        ed = final_fuel_energy_demand * self.candidate_fuel_blend(sector).loc[final_fuel_energy_demand.index]

        # temporarily save the candidate fuel energy demand results on the FinalFuelToCandidateFuel linkage, used for aggregating results in PW on the FinalFuel component
        # this will be overwritten since many sectors/subsectors can have the same FinalFuelToCandidateFuel linkage
        fuel_linkage = self.final_fuels[self.final_fuel_name]
        getattr(fuel_linkage, "out_energy_demand").data = ed
        return ed

    # TODO: Used in PATHWAYS. Leave as is, but discuss with broader PATHWAYS team on integration.
    def calc_fuel_cost(self, candidate_fuel_energy_demand: pd.Series):
        """
        CandidateFuel fuel cost = CandidateFuel energy demand * candidate fuel fuel_price per mmbtu

        Args:
            candidate_fuel_energy_demand: pd.Series of calculated CandidateFuel energy demand in mmbtu

        Returns: pd.Series of CandidateFuel fuel cost in $

        """
        fuel_linkage = self.final_fuels[self.final_fuel_name]
        # temporarily save the candidate fuel cost results on the FinalFuelToCandidateFuel linkage, used for aggregating results in PW on the FinalFuel component
        # this will be overwritten since many sectors/subsectors can have the same FinalFuelToCandidateFuel linkage
        fuel_cost = (
            candidate_fuel_energy_demand * self.fuel_price_per_mmbtu.data.loc[candidate_fuel_energy_demand.index]
        )
        getattr(fuel_linkage, "out_fuel_cost").data = fuel_cost
        return fuel_cost

    def _consumers(self) -> dict[str, Asset]:
        parent_consumers = super()._consumers()
        return parent_consumers | {
            resource.instance_to.name: resource.instance_to
            for resource in self.resources.values()
            if hasattr(resource.instance_to, resource.component_type_from_)
        }
