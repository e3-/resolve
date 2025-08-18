from typing import Annotated
from typing import ClassVar
from typing import Dict

import numpy as np
import pandas as pd
import pyomo.environ as pyo
from pydantic import Field

from new_modeling_toolkit.core import component
from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.custom_model import units
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.system.electric.load_component import Load
from new_modeling_toolkit.system.electric.resources import GenericResource
from new_modeling_toolkit.system.generics.energy import Electricity
from new_modeling_toolkit.system.generics.generic_linkages import FromZoneToFuelStorage
from new_modeling_toolkit.system.generics.generic_linkages import ToZoneToFuelStorage
from new_modeling_toolkit.system.generics.generic_linkages import ZoneToDemand
from new_modeling_toolkit.system.generics.generic_linkages import ZoneToPlant
from new_modeling_toolkit.system.generics.generic_linkages import ZoneToProduct
from new_modeling_toolkit.system.generics.generic_linkages import ZoneToTransportation
from new_modeling_toolkit.system.pollution.sequestration import Sequestration


class Zone(component.Component):
    SAVE_PATH: ClassVar[str] = "zones"
    """This class defines a zone object and its methods."""

    ######################
    # Mapping Attributes #
    ######################
    # TODO: Clean up linkage dictionaries
    assets: Annotated[dict[str, linkage.AssetToZone], Metadata(linkage_order="from")] = {}
    biomass_resources: Annotated[dict[str, linkage.AssetToZone], Metadata(linkage_order="from")] = {}
    electrofuel_resources: Annotated[dict[str, linkage.AssetToZone], Metadata(linkage_order="from")] = {}
    flexible_resources: Annotated[dict[str, linkage.AssetToZone], Metadata(linkage_order="from")] = {}
    final_fuel_demands: dict[str, linkage.Linkage] = {}

    transportations: dict[str, ZoneToTransportation] = {}
    products: dict[str, ZoneToProduct] = {}
    consuming_generic_demands: dict[str, ZoneToDemand] = {}  # TODO: Decide how we want to handle linkages defining
    # separate input and output relationships but still share the same names
    producing_generic_demands: dict[str, ZoneToDemand] = {}
    consuming_generic_plants: dict[str, ZoneToPlant] = {}
    producing_generic_plants: dict[str, ZoneToPlant] = {}
    consuming_fuel_production_plants: dict[str, ZoneToPlant] = {}
    producing_fuel_production_plants: dict[str, ZoneToPlant] = {}
    consuming_fuel_storage_plants: dict[str, FromZoneToFuelStorage] = {}
    producing_fuel_storage_plants: dict[str, ToZoneToFuelStorage] = {}

    hydro_resources: Annotated[dict[str, linkage.AssetToZone], Metadata(linkage_order="from")] = {}
    loads: dict[str, linkage.LoadToZone] = {}
    emissions_policies: dict[str, linkage.AllToPolicy] = {}
    annual_energy_policies: dict[str, linkage.AllToPolicy] = {}
    hourly_energy_policies: dict[str, linkage.AllToPolicy] = {}
    prm_policies: dict[str, linkage.AllToPolicy] = {}
    erm_policies: dict[str, linkage.AllToPolicy] = {}
    reserves: dict[str, linkage.ReserveToZone] = {}
    # TODO: why are these AssetToZone and not ResourceToZone? how does it separate out by resource types?
    resources: Annotated[dict[str, linkage.AssetToZone], Metadata(linkage_order="from")] = {}
    shed_dr_resources: Annotated[dict[str, linkage.AssetToZone], Metadata(linkage_order="from")] = {}
    storage_resources: Annotated[dict[str, linkage.AssetToZone], Metadata(linkage_order="from")] = {}
    variable_resources: Annotated[dict[str, linkage.AssetToZone], Metadata(linkage_order="from")] = {}
    thermal_resources: Annotated[dict[str, linkage.AssetToZone], Metadata(linkage_order="from")] = {}
    tx_paths: dict[str, linkage.ZoneToTransmissionPath] = {}
    stock_rollover_subsectors: dict[str, linkage.Linkage] = {}
    energy_demand_subsectors: dict[str, linkage.Linkage] = {}
    non_energy_subsectors: dict[str, linkage.Linkage] = {}

    #######################################
    # Overgen / Unserved Energy Penalties #
    #######################################
    penalty_overgen: Annotated[
        float, Metadata(category=FieldCategory.OPERATIONS, units=units.dollar / units.megawatt_hour)
    ] = Field(
        10000,
        description="Modeled penalty for overgeneration.",
        title=f"Over-Generation Penalty",
    )
    penalty_unserved_energy: Annotated[
        float, Metadata(category=FieldCategory.OPERATIONS, units=units.dollar / units.megawatt_hour)
    ] = Field(
        10000,
        description="Modeled penalty for unserved load.",
        title=f"Unserved Energy Penalty",
    )

    # @property
    # def products(self):
    #     """All products linked to zone"""
    #     relevant_linkages = self.generic_products | self.candidate_fuels
    #
    #     return {_linkage.product.name: _linkage.product for _linkage in relevant_linkages.values()}

    @property
    def non_electricity_products(self):
        return {
            name: product for name, product in self.products.items() if not isinstance(product.product, Electricity)
        }

    @property
    def electricity_products(self):
        return {
            name: product
            for name, product in self.products.items()
            if product not in self.non_electricity_products.values()
        }

    # TODO (MK): clean up linkages and properties when refactoring Zone
    @property
    def consuming_demands(self):
        """All demands in the zone that consume products"""
        # TODO: add other demands later
        # consuming_generic_demands = {
        #     demand_name: demand_linkage
        #     for (demand_name, demand_linkage) in self.consuming_generic_demands.items()
        #     if demand_linkage.from_zone
        # }
        # return consuming_generic_demands

        return self.consuming_generic_demands
        # | self.consuming_energy_demands
        # | self.consuming_negative_emission_technologies
        # | self.consuming_sequestrations

    @property
    def producing_demands(self):
        """All demands in the zone that produce products"""
        # TODO: add other demands later
        # producing_generic_demands = {
        #     demand_name: demand_linkage
        #     for (demand_name, demand_linkage) in self.demands.items()
        #     if demand_linkage.to_zone
        # }
        # return producing_generic_demands
        return self.producing_generic_demands
        # | self.producing_energy_demands
        # | self.producing_negative_emission_technologies

    @property
    def consuming_plants(self):
        """All plants in the zone that consume products"""
        # consuming_plants = {
        #     plant_name: plant_linkage for (plant_name, plant_linkage) in self.plants.items() if plant_linkage.from_zone
        # }
        # consuming_fuel_production_plants = {
        #     fuel_plant_name: fuel_plant_linkage
        #     for (fuel_plant_name, fuel_plant_linkage) in self.fuel_production_plants.items()
        #     if fuel_plant_linkage.from_zone
        # }
        return (
            self.consuming_generic_plants | self.consuming_fuel_production_plants | self.consuming_fuel_storage_plants
        )

    @property
    def producing_plants(self):
        """All plants in the zone that produce products"""
        # producing_plants = {
        #     plant_name: plant_linkage for (plant_name, plant_linkage) in self.plants.items() if plant_linkage.to_zone
        # }
        # producing_fuel_production_plants = {
        #     fuel_plant_name: fuel_plant_linkage
        #     for (fuel_plant_name, fuel_plant_linkage) in self.fuel_production_plants.items()
        #     if fuel_plant_linkage.to_zone
        # }
        return (
            self.producing_generic_plants | self.producing_fuel_production_plants | self.producing_fuel_storage_plants
        )

    @property
    def sequestering_plants(self):
        """All plants in the zone that sequester products (specific type of production)"""
        # sequestering_plants = {
        #     sequestering_plant_name: sequestering_plant_linkage
        # }
        sequestering_plants = {
            name: linkage
            for name, linkage in self.producing_plants.items()
            if isinstance(linkage.instance_to, Sequestration)
        }
        return sequestering_plants

    @property
    def policies(self):
        return (
            self.emissions_policies
            | self.annual_energy_policies
            | self.hourly_energy_policies
            | self.prm_policies
            | self.erm_policies
        )
    @property
    def resource_instances(self) -> Dict[str, GenericResource]:
        resources = (
            {name: linkage.instance_from for name, linkage in self.resources.items()}
            if self.resources is not None
            else None
        )
        return resources

    @property
    def load_instances(self) -> Dict[str, Load]:
        loads = (
            {name: linkage.instance_from for name, linkage in self.loads.items()} if self.loads is not None else None
        )
        return loads

    @property
    def transportation_instances_to_zone(self) -> dict | None:
        """All transportations to zone"""
        instances_to = (
            {name: linkage.instance_to for name, linkage in self.transportations.items() if linkage.to_zone}
            if self.transportations is not None
            else None
        )
        return instances_to

    @property
    def transportation_instances_from_zone(self) -> dict | None:
        """All transportations from zone"""
        instances_from = (
            {name: linkage.instance_to for name, linkage in self.transportations.items() if linkage.from_zone}
            if self.transportations is not None
            else None
        )
        return instances_from

    @property
    def tx_path_instances_to_zone(self) -> Dict:
        paths_to = (
            {name: linkage.instance_to for name, linkage in self.tx_paths.items() if linkage.to_zone}
            if self.tx_paths is not None
            else None
        )

        return paths_to

    @property
    def tx_path_instances_from_zone(self) -> Dict:
        paths_from = (
            {name: linkage.instance_to for name, linkage in self.tx_paths.items() if linkage.from_zone}
            if self.tx_paths is not None
            else None
        )

        return paths_from

    @property
    def annual_results_column_order(self):
        """This property defines the ordering of columns in the component's annual results summary out of Resolve.
        The name of the model field or formulation_block pyomo component can be used.
        """
        return [
            "annual_unserved_energy",
            "annual_overgen",
            "annual_provide_power",
            "annual_input_load",
            "annual_increase_load",
            "annual_gross_imports",
            "annual_gross_exports",
            "annual_net_imports",
            "annual_curtailment",
            "annual_total_investment_cost",
            "annual_total_operational_cost",
            "annual_total_slack_operational_cost",
        ]

    def get_aggregated_load(self, modeled_year: int, weather_year_timestamp: pd.Timestamp) -> float:
        """
        Queries aggregated load in zone at given timepoint
        """
        if self.load_instances is not None:
            return sum(load.get_load(modeled_year, weather_year_timestamp) for load in self.load_instances.values())
        else:
            return 0

    def get_aggregated_load_profile(self, modeled_year) -> pd.Series:
        """
        Queries aggregated load profile in zone
        """
        agg_load_profile = 0
        for inst in self.loads.keys():
            agg_load_profile += self.loads[inst].instance_from.modeled_year_profiles[modeled_year].data

        return agg_load_profile

    def _construct_operational_rules(self, model: "ModelTemplate", construct_costs: bool):
        pyomo_components = dict()
        PRODUCTS = pyo.Set(initialize=self.products.keys())
        NONELECTRIC_PRODUCTS = pyo.Set(initialize=self.non_electricity_products.keys())
        pyomo_components.update(PRODUCTS=PRODUCTS, NONELECTRIC_PRODUCTS=NONELECTRIC_PRODUCTS)
        #############
        # Variables #
        #############

        if self.electricity_products or self.resources:
            """Unserved energy in this zone in each hour"""
            pyomo_components.update(
                unserved_energy=pyo.Var(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    within=pyo.NonNegativeReals,
                    doc="Hourly Unserved Energy (MW)",
                )
            )
            """Overgeneration of energy in this zone in each hour"""
            pyomo_components.update(
                overgen=pyo.Var(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    within=pyo.NonNegativeReals,
                    doc="Hourly Overgeneration (MW)",
                )
            )

        if self.non_electricity_products:
            """Unmet demand in this zone in each hour"""
            pyomo_components.update(
                unmet_demand=pyo.Var(
                    NONELECTRIC_PRODUCTS,
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    within=pyo.NonNegativeReals,
                    doc="Hourly Unmet Demand (Product Units per hour)",
                )
            )
            """Overproduction of energy in this zone in each hour"""
            pyomo_components.update(
                overproduction=pyo.Var(
                    NONELECTRIC_PRODUCTS,
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    within=pyo.NonNegativeReals,
                    doc="Hourly Overproduction (Product Units per hour)",
                )
            )

        ##########################
        # Expressions and Params #
        ##########################
        if self.electricity_products or self.resources:
            """Net power produced in this zone by all resources"""
            pyomo_components.update(
                zonal_resource_provide_power=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_resource_provide_power,
                    doc="Resource Power Output (MW)",
                ),
                zonal_plant_provide_power=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_plant_provide_power,
                    doc="Plant Power Output (MW)",
                ),
                zonal_demand_provide_power=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_demand_provide_power,
                    doc="Demand Power Output (MW)",
                ),
                zonal_provide_power=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_provide_power,
                    doc="Power Output (MW)",
                ),
            )

            pyomo_components.update(
                zonal_synchronous_condenser_increase_load=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_synchronous_condenser_increase_load,
                    doc="Synchronous Condenser Increase Load (MW)",
                ),
                zonal_resource_increase_load=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_resource_increase_load,
                    doc="Resource Power Input (MW)",
                ),
                zonal_plant_increase_load=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_plant_increase_load,
                    doc="Plant Power Input (MW)",
                ),
                zonal_demand_increase_load=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_demand_increase_load,
                    doc="Demand Power Input (MW)",
                ),
                zonal_increase_load=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_increase_load,
                    doc="Power Input (MW)",
                ),
            )

            pyomo_components.update(
                input_load=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    initialize=lambda block, modeled_year, dispatch_window, timestamp: self.get_aggregated_load(
                        modeled_year.year, timestamp
                    ),
                    doc="Input Load (MW)",
                )
            )

            pyomo_components.update(
                zonal_net_imports=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_net_imports,
                    doc="Zonal Net Imports (MW)",
                )
            )

        if self.non_electricity_products:
            """Hourly zonal production by product"""
            pyomo_components.update(
                zonal_plant_production_by_product=pyo.Expression(
                    NONELECTRIC_PRODUCTS,
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_plant_production_by_product,
                    doc="Zonal Plant Production by Product (Product Unit per hour)",
                ),
                zonal_demand_production_by_product=pyo.Expression(
                    NONELECTRIC_PRODUCTS,
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_demand_production_by_product,
                    doc="Zonal Demand Production by Product (Product Unit per hour)",
                ),
                zonal_production_by_product=pyo.Expression(
                    NONELECTRIC_PRODUCTS,
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_production_by_product,
                    doc="Zonal Production by Product (Product Unit per hour)",
                ),
            )
            """Hourly zonal consumption by product"""
            pyomo_components.update(
                zonal_plant_consumption_by_product=pyo.Expression(
                    NONELECTRIC_PRODUCTS,
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_plant_consumption_by_product,
                    doc="Zonal Plant Consumption by Product (Product Unit per hour)",
                ),
                zonal_demand_consumption_by_product=pyo.Expression(
                    NONELECTRIC_PRODUCTS,
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_demand_consumption_by_product,
                    doc="Zonal Demand Consumption by Product (Product Unit per hour)",
                ),
                zonal_resource_consumption_by_product=pyo.Expression(
                    NONELECTRIC_PRODUCTS,
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_resource_consumption_by_product,
                    doc="Zonal Resource Consumption by Product (Product Unit per hour)",
                ),
                zonal_consumption_by_product=pyo.Expression(
                    NONELECTRIC_PRODUCTS,
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_consumption_by_product,
                    doc="Zonal Consumption by Product (Product Unit per hour)",
                ),
            )
            """Hourly zonal sequestration by product"""
            pyomo_components.update(
                zonal_sequestration_by_product=pyo.Expression(
                    NONELECTRIC_PRODUCTS,
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_sequestration_by_product,
                    doc="Zonal Sequestration by Product (Product Unit per hour)",
                )
            )
            """Hourly zonal net imports by product"""
            pyomo_components.update(
                zonal_net_imports_by_product=pyo.Expression(
                    NONELECTRIC_PRODUCTS,
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_net_imports_by_product,
                    doc="Zonal Net Imports by Product (Product Unit per hour)",
                )
            )

        ###############
        # Constraints #
        ###############
        if self.electricity_products or self.resources:
            """The sum of all in-zone power production and net transmission flow equals the zone's load in each timepoint."""
            pyomo_components.update(
                zonal_power_balance_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_power_balance_constraint,
                )
            )
        if self.non_electricity_products:
            """The sum of all in-zone production and net transportation flow equals consumption in each timepoint."""
            pyomo_components.update(
                zonal_flow_balance_by_product=pyo.Constraint(
                    NONELECTRIC_PRODUCTS,
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._zonal_flow_balance_by_product,
                )
            )

        if construct_costs:
            pyomo_components.update(
                annual_total_slack_operational_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_slack_operational_cost,
                    doc="Annual Total Slack Operational Cost($)",
                ),
                annual_total_operational_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_operational_cost,
                    doc="Annual Total Operational Cost ($)",
                )
            )

        return pyomo_components

    #####################
    # Output Expressions#
    #####################

    def _construct_output_expressions(self, construct_costs: bool):

        if construct_costs:
            if self.electricity_products or self.resources:
                self.formulation_block.hourly_energy_prices_unweighted = pyo.Expression(
                    self.formulation_block.model().MODELED_YEARS,
                    self.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._hourly_energy_prices_unweighted,
                    doc="Hourly Energy Price Unweighted ($/MWh)",
                )

                self.formulation_block.hourly_energy_prices_weighted = pyo.Expression(
                    self.formulation_block.model().MODELED_YEARS,
                    self.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._hourly_energy_prices_weighted,
                    doc="Hourly Energy Price Weighted ($/MWh)",
                )

            if self.non_electricity_products:
                self.formulation_block.hourly_energy_prices_by_product_unweighted = pyo.Expression(
                    self.formulation_block.NONELECTRIC_PRODUCTS,
                    self.formulation_block.model().MODELED_YEARS,
                    self.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._hourly_energy_prices_by_product_unweighted,
                    doc="Hourly Energy Price Unweighted ($ per Product Unit)",
                )

                self.formulation_block.hourly_energy_prices_by_product_weighted = pyo.Expression(
                    self.formulation_block.NONELECTRIC_PRODUCTS,
                    self.formulation_block.model().MODELED_YEARS,
                    self.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._hourly_energy_prices_by_product_weighted,
                    doc="Hourly Energy Price Weighted ($ per Product Unit)",
                )

        if self.electricity_products or self.resources:
            self.formulation_block.zonal_gross_imports = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS,
                self.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._zonal_gross_imports,
                doc="Zonal Gross Imports (MW)",
            )

            self.formulation_block.zonal_gross_exports = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS,
                self.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._zonal_gross_exports,
                doc="Zonal Gross Exports (MW)",
            )

            self.formulation_block.annual_unserved_energy = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_unserved_energy,
                doc="Annual Unserved Energy (MWh)",
            )

            self.formulation_block.annual_overgen = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_overgen,
                doc="Annual Overgeneration (MWh)",
            )

            self.formulation_block.annual_resource_provide_power = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_resource_provide_power,
                doc="Annual Resource Provide Power (MWh)",
            )

            self.formulation_block.annual_plant_provide_power = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_plant_provide_power,
                doc="Annual Plant Provide Power (MWh)",
            )

            self.formulation_block.annual_demand_provide_power = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_demand_provide_power,
                doc="Annual Demand Provide Power (MWh)",
            )

            self.formulation_block.annual_provide_power = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS, rule=self._annual_provide_power, doc="Provide Power (MWh)"
            )

            self.formulation_block.annual_input_load = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS, rule=self._annual_input_load, doc="Input Load (MWh)"
            )

            self.formulation_block.annual_resource_increase_load = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_resource_increase_load,
                doc="Annual Resource Increase Load (MWh)",
            )

            self.formulation_block.annual_plant_increase_load = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_plant_increase_load,
                doc="Annual Plant Increase Load (MWh)",
            )

            self.formulation_block.annual_demand_increase_load = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_demand_increase_load,
                doc="Annual Demand Increase Load (MWh)",
            )

            self.formulation_block.annual_increase_load = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS, rule=self._annual_increase_load, doc="Increase Load (MWh)"
            )

            self.formulation_block.annual_gross_imports = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS, rule=self._annual_gross_imports, doc="Gross Imports (MWh)"
            )

            self.formulation_block.annual_gross_exports = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS, rule=self._annual_gross_exports, doc="Gross Exports (MWh)"
            )

            self.formulation_block.annual_net_imports = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS, rule=self._annual_net_imports, doc="Net Imports (MWh)"
            )

            self.formulation_block.curtailment = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS,
                self.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._curtailment,
                doc="Curtailment (MW)",
            )

            self.formulation_block.annual_curtailment = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_curtailment,
                doc="Total Annual Curtailment (MWh)",
            )

        if self.non_electricity_products:
            self.formulation_block.annual_unmet_demand = pyo.Expression(
                self.formulation_block.NONELECTRIC_PRODUCTS,
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_unmet_demand,
                doc="Annual Unmet Demand (Product Units)",
            )

            self.formulation_block.annual_overproduction = pyo.Expression(
                self.formulation_block.NONELECTRIC_PRODUCTS,
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_overproduction,
                doc="Annual Overproduction (Product Units)",
            )

            self.formulation_block.annual_plant_production_by_product = pyo.Expression(
                self.formulation_block.NONELECTRIC_PRODUCTS,
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_plant_production_by_product,
                doc="Annual Plant Production (Product Units)",
            )

            self.formulation_block.annual_demand_production_by_product = pyo.Expression(
                self.formulation_block.NONELECTRIC_PRODUCTS,
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_demand_production_by_product,
                doc="Annual Demand Production (Product Units)",
            )

            self.formulation_block.annual_zonal_production_by_product = pyo.Expression(
                self.formulation_block.NONELECTRIC_PRODUCTS,
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_zonal_production_by_product,
                doc="Annual Zonal Production (Product Units)",
            )

            self.formulation_block.annual_resource_consumption_by_product = pyo.Expression(
                self.formulation_block.NONELECTRIC_PRODUCTS,
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_resource_consumption_by_product,
                doc="Annual Resource Consumption (Product Units)",
            )

            self.formulation_block.annual_plant_consumption_by_product = pyo.Expression(
                self.formulation_block.NONELECTRIC_PRODUCTS,
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_plant_consumption_by_product,
                doc="Annual Plant Consumption (Product Units)",
            )

            self.formulation_block.annual_demand_consumption_by_product = pyo.Expression(
                self.formulation_block.NONELECTRIC_PRODUCTS,
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_demand_consumption_by_product,
                doc="Annual Demand Consumption (Product Units)",
            )

            self.formulation_block.annual_zonal_consumption_by_product = pyo.Expression(
                self.formulation_block.NONELECTRIC_PRODUCTS,
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_zonal_consumption_by_product,
                doc="Annual Zonal Consumption (Product Units)",
            )

            self.formulation_block.annual_zonal_sequestration_by_product = pyo.Expression(
                self.formulation_block.NONELECTRIC_PRODUCTS,
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_zonal_sequestration_by_product,
                doc="Annual Zonal Sequestration (Product Units)",
            )

            self.formulation_block.annual_zonal_net_imports_by_product = pyo.Expression(
                self.formulation_block.NONELECTRIC_PRODUCTS,
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_zonal_net_imports_by_product,
                doc="Annual Zonal Net Imports (Product Units)",
            )

            self.formulation_block.annual_zonal_net_release_by_product = pyo.Expression(
                self.formulation_block.NONELECTRIC_PRODUCTS,
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_zonal_net_release_by_product,
                doc="Annual Zonal Net Release (Product Units)",
            )

            self.formulation_block.annual_gross_imports_by_product = pyo.Expression(
                self.formulation_block.NONELECTRIC_PRODUCTS,
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_gross_imports_by_product,
                doc="Annual Zonal Gross Imports (Product Units)",
            )

            self.formulation_block.annual_gross_exports_by_product = pyo.Expression(
                self.formulation_block.NONELECTRIC_PRODUCTS,
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_gross_exports_by_product,
                doc="Annual Zonal Gross Exports (Product Units)",
            )


    #########
    # Rules #
    #########

    def _zonal_resource_provide_power(self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp):
        """Power output from resources."""
        return sum(
            (
                resource.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
                if hasattr(resource.formulation_block, "power_output")
                else 0
            )
            for resource in self.resource_instances.values()
        )

    def _zonal_plant_provide_power(self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp):
        """Power output from plants. Electricity product units are by default kWh, while this expression is in units
        of MWh, hence a division by 1e3."""
        return (
            sum(
                producing_plant.plant.formulation_block.produced_product_to_zone[
                    product, modeled_year, dispatch_window, timestamp
                ]
                # TODO: Change electricity units from kWh to MWh
                for producing_plant in self.producing_plants.values()
                if producing_plant.plant.has_operational_rules
                for product in producing_plant.plant.formulation_block.OUTPUTS
                if product in self.electricity_products.keys()
            )
            / 1e3
        )

    def _zonal_demand_provide_power(self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp):
        """Power output from demands. Electricity product units are by default kWh, while this expression is in units
        of MWh, hence a division by 1e3."""

        return (
            sum(
                producing_demand.demand.formulation_block.produced_product_to_zone[
                    product, modeled_year, dispatch_window, timestamp
                ]
                for producing_demand in self.producing_demands.values()
                if producing_demand.demand.processes
                for product in producing_demand.demand.formulation_block.OUTPUTS
                if product in self.electricity_products.keys()
            )
            / 1e3
        )

    def _zonal_provide_power(self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp):
        """Power output from resources, plants, and demands. Electricity product units are by default kWh,
        while this expression is in units of MWh, hence a division by 1e3 for plant and demand power output."""
        return (
            block.zonal_resource_provide_power[modeled_year, dispatch_window, timestamp]
            + block.zonal_plant_provide_power[modeled_year, dispatch_window, timestamp]
            + block.zonal_demand_provide_power[modeled_year, dispatch_window, timestamp]
        )

    def _zonal_synchronous_condenser_increase_load(
        self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp
    ):
        """Increase in load from synchronous condensers."""
        return sum(
            (
                thermal_uc_resource.formulation_block.synchronous_condenser_addition_to_load[
                    modeled_year, dispatch_window, timestamp
                ]
                if hasattr(thermal_uc_resource.formulation_block, "synchronous_condenser_addition_to_load")
                else 0
            )
            for thermal_uc_resource in self.resource_instances.values()
        )

    def _zonal_resource_increase_load(self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp):
        """Power consumption by resources."""
        return sum(
            (
                resource.formulation_block.power_input[modeled_year, dispatch_window, timestamp]
                if hasattr(resource.formulation_block, "power_input")
                else 0
            )
            for resource in self.resource_instances.values()
        )

    def _zonal_plant_increase_load(self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp):
        """Power consumption by plants. Electricity product units are by default kWh, while this expression is in
        units of MWh, hence a division by 1e3 for plant and demand power output."""
        return (
            sum(
                consuming_plant.plant.formulation_block.consumed_product_from_zone[
                    product, modeled_year, dispatch_window, timestamp
                ]
                # TODO: Change electricity units to MWh instead of kWh and get rid of 1e3 factors
                for consuming_plant in self.consuming_plants.values()
                if consuming_plant.plant.has_operational_rules
                for product in consuming_plant.plant.formulation_block.INPUTS
                if product in self.electricity_products.keys()
            )
            / 1e3
        )

    def _zonal_demand_increase_load(self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp):
        """Power consumption by demands. Electricity product units are by default kWh, while this expression is in
        units of MWh, hence a division by 1e3 for plant and demand power output."""

        return (
            sum(
                consuming_demand.demand.formulation_block.consumed_product_from_zone[
                    product, modeled_year, dispatch_window, timestamp
                ]
                for consuming_demand in self.consuming_demands.values()
                for product in consuming_demand.demand.formulation_block.INPUTS
                if product in self.electricity_products.keys()
            )
            / 1e3
        )

    def _zonal_increase_load(self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp):
        """Power consumption by resources, plants, demands, and synchronous condensers. Electricity product units are by default kWh,
        while this expression is in units of MWh, hence a division by 1e3 for plant and demand power output."""

        return (
            block.zonal_resource_increase_load[modeled_year, dispatch_window, timestamp]
            + block.zonal_plant_increase_load[modeled_year, dispatch_window, timestamp]
            + block.zonal_demand_increase_load[modeled_year, dispatch_window, timestamp]
            + block.zonal_synchronous_condenser_increase_load[modeled_year, dispatch_window, timestamp]
        )

    def _zonal_net_imports(self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp):
        net_imports = 0
        for tx_path_from_zone in self.tx_path_instances_from_zone.values():
            if tx_path_from_zone.has_operational_rules:
                net_imports -= tx_path_from_zone.formulation_block.net_transmit_power[
                    modeled_year, dispatch_window, timestamp
                ]
        for tx_path_to_zone in self.tx_path_instances_to_zone.values():
            if tx_path_to_zone.has_operational_rules:
                net_imports += tx_path_to_zone.formulation_block.net_transmit_power[
                    modeled_year, dispatch_window, timestamp
                ]
        return net_imports

    def _annual_total_slack_operational_cost(self, block, modeled_year: pd.Timestamp):
        """The total annual operational costs of the zone (for unserved energy and overgen). This term is not
        discounted (i.e. it is not multiplied by the discount factor for the relevant model year)."""
        if hasattr(block, "unserved_energy"):
            total_electric_operational_cost = (
                block.model().sum_timepoint_component_slice_to_annual(block.unserved_energy[modeled_year, :, :])
                * self.penalty_unserved_energy
                + block.model().sum_timepoint_component_slice_to_annual(block.overgen[modeled_year, :, :])
                * self.penalty_overgen
            )
        else:
            total_electric_operational_cost = 0

        if hasattr(block, "unmet_demand"):
            total_fuels_operational_cost = sum(
                block.model().sum_timepoint_component_slice_to_annual(block.unmet_demand[product, modeled_year, :, :])
                * self.products[product].penalty_unmet_demand
                for product in block.NONELECTRIC_PRODUCTS
            ) + sum(
                block.model().sum_timepoint_component_slice_to_annual(block.overproduction[product, modeled_year, :, :])
                * self.products[product].penalty_overproduction
                for product in block.NONELECTRIC_PRODUCTS
            )
        else:
            total_fuels_operational_cost = 0

        return total_electric_operational_cost + total_fuels_operational_cost

    def _annual_total_operational_cost(self, block, modeled_year: pd.Timestamp):
        """Equal to the slack operational costs from unserved energy, overgeneration, unmet demand, and overproduction."""

        return block.annual_total_slack_operational_cost[modeled_year]

    def _zonal_power_balance_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp):
        """The sum of all in-zone power production and net transmission flow equals the zone's load in each timepoint.
        Resources may increase load; the demand from these resources is added to the zone's load in each timepoint.
        resources with storage both increase load and provide power, and are therefore included on both sides of the constraint.
        Plants can demand or produce electricity, thus also being included in both sides of the equation.
        Two slack variables for unserved energy and overgeneration are included.
        Scheduled curtailment is not explicitly included here because Provide_Power
        will be less than the resource's potential power production during times of scheduled curtailment. If
        electricity is considered a commodity product, i.e. it's production and pricing is not optimized in the case
        of a fuels-only optimization, this constraint is skipped.

        Args:
          model:
          timepoint:
          zone:

        Returns: pyo.Constraint
        """
        if all(linkage.product.commodity for linkage in self.electricity_products.values()):
            return pyo.Constraint.Skip
        else:
            return (
                block.zonal_provide_power[modeled_year, dispatch_window, timestamp]
                + block.zonal_net_imports[modeled_year, dispatch_window, timestamp]
                + block.unserved_energy[modeled_year, dispatch_window, timestamp]
                == block.input_load[modeled_year, dispatch_window, timestamp]
                + block.zonal_increase_load[modeled_year, dispatch_window, timestamp]
                + block.overgen[modeled_year, dispatch_window, timestamp]
            )

    def _hourly_energy_prices_unweighted(
        self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """Hourly unweighted electricity prices. Electricity products, if explicitly parameterized, are included
        here. If there is no power balance constraint, assumes that there is only one Electricity commodity product linked
        to the zone."""

        if not all(linkage.product.commodity for linkage in self.electricity_products.values()):
            zonal_resource_balance_dual = self.formulation_block.zonal_power_balance_constraint[
                modeled_year, dispatch_window, timestamp
            ].get_suffix_value("dual", default=np.nan)
        else:
            # Assumes that there is a single electricity product linked to zone
            zonal_resource_balance_dual = self.electricity_products[
                list(self.electricity_products.keys())[0]
            ].product.price_per_unit.data.at[timestamp.replace(year=modeled_year.year)]

        annual_discount_factor = block.model().temporal_settings.modeled_year_discount_factors.data.at[modeled_year]
        num_days_in_modeled_year = block.model().num_days_per_modeled_year[modeled_year]
        dispatch_window_weight = block.model().temporal_settings.dispatch_window_weights.at[dispatch_window]
        timestamp_duration_hours = block.model().timestamp_durations_hours[dispatch_window, timestamp]

        return (
            zonal_resource_balance_dual
            / annual_discount_factor
            / num_days_in_modeled_year
            / dispatch_window_weight
            / timestamp_duration_hours
        )

    def _hourly_energy_prices_weighted(
        self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """Hourly weighted electricity prices. Electricity products, if explicitly parametrized, are included here.
        If there is no power balance constraint, assumes that there is only one Electricity commodity product linked
        to the zone."""
        if not all(linkage.product.commodity for linkage in self.electricity_products.values()):
            zonal_resource_balance_dual = self.formulation_block.zonal_power_balance_constraint[
                modeled_year, dispatch_window, timestamp
            ].get_suffix_value("dual", default=np.nan)
        else:
            # Assumes that there is a single electricity product linked to zone
            zonal_resource_balance_dual = self.electricity_products[
                list(self.electricity_products.keys())[0]
            ].product.price_per_unit.data.at[timestamp.replace(year=modeled_year.year)]

        return zonal_resource_balance_dual

    def _zonal_gross_imports(
        self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        gross_imports = 0
        for tx_path_from_zone in self.tx_path_instances_from_zone.values():
            if tx_path_from_zone.has_operational_rules:
                gross_imports += tx_path_from_zone.formulation_block.transmit_power_reverse[
                    modeled_year, dispatch_window, timestamp
                ]
        for tx_path_to_zone in self.tx_path_instances_to_zone.values():
            if tx_path_to_zone.has_operational_rules:
                gross_imports += tx_path_to_zone.formulation_block.transmit_power_forward[
                    modeled_year, dispatch_window, timestamp
                ]
        return gross_imports

    def _zonal_gross_exports(
        self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        gross_exports = 0
        for tx_path_from_zone in self.tx_path_instances_from_zone.values():
            if tx_path_from_zone.has_operational_rules:
                gross_exports += tx_path_from_zone.formulation_block.transmit_power_forward[
                    modeled_year, dispatch_window, timestamp
                ]
        for tx_path_to_zone in self.tx_path_instances_to_zone.values():
            if tx_path_to_zone.has_operational_rules:
                gross_exports += tx_path_to_zone.formulation_block.transmit_power_reverse[
                    modeled_year, dispatch_window, timestamp
                ]
        return gross_exports

    def _annual_unserved_energy(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(block.unserved_energy[modeled_year, :, :])

    def _annual_overgen(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(block.overgen[modeled_year, :, :])

    def _annual_resource_provide_power(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.zonal_resource_provide_power[modeled_year, :, :]
        )

    def _annual_plant_provide_power(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.zonal_plant_provide_power[modeled_year, :, :]
        )

    def _annual_demand_provide_power(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.zonal_demand_provide_power[modeled_year, :, :]
        )

    def _annual_provide_power(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(block.zonal_provide_power[modeled_year, :, :])

    def _annual_input_load(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(block.input_load[modeled_year, :, :])

    def _annual_resource_increase_load(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.zonal_resource_increase_load[modeled_year, :, :]
        )

    def _annual_plant_increase_load(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.zonal_plant_increase_load[modeled_year, :, :]
        )

    def _annual_demand_increase_load(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.zonal_demand_increase_load[modeled_year, :, :]
        )

    def _annual_increase_load(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(block.zonal_increase_load[modeled_year, :, :])

    # TODO: Add unit tests for annual gross exports and annual gross imports
    def _annual_gross_imports(self, block: pyo.Block, modeled_year: pd.Timestamp):
        annual_gross_imports = 0
        for tx_path_from_zone in self.tx_path_instances_from_zone.values():
            if tx_path_from_zone.has_operational_rules:
                annual_gross_imports += block.model().sum_timepoint_component_slice_to_annual(
                    tx_path_from_zone.formulation_block.transmit_power_reverse[modeled_year, :, :]
                )
        for tx_path_to_zone in self.tx_path_instances_to_zone.values():
            if tx_path_to_zone.has_operational_rules:
                annual_gross_imports += block.model().sum_timepoint_component_slice_to_annual(
                    tx_path_to_zone.formulation_block.transmit_power_forward[modeled_year, :, :]
                )
        return annual_gross_imports

    def _annual_gross_exports(self, block: pyo.Block, modeled_year: pd.Timestamp):
        annual_gross_exports = 0
        for tx_path_from_zone in self.tx_path_instances_from_zone.values():
            if tx_path_from_zone.has_operational_rules:
                annual_gross_exports += block.model().sum_timepoint_component_slice_to_annual(
                    tx_path_from_zone.formulation_block.transmit_power_forward[modeled_year, :, :]
                )
        for tx_path_to_zone in self.tx_path_instances_to_zone.values():
            if tx_path_to_zone.has_operational_rules:
                annual_gross_exports += block.model().sum_timepoint_component_slice_to_annual(
                    tx_path_to_zone.formulation_block.transmit_power_reverse[modeled_year, :, :]
                )
        return annual_gross_exports

    def _annual_net_imports(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.annual_gross_imports[modeled_year] - block.annual_gross_exports[modeled_year]

    def _curtailment(
        self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        return sum(
            [
                resource.formulation_block.scheduled_curtailment[modeled_year, dispatch_window, timestamp]
                for resource in self.resource_instances.values()
                if hasattr(resource.formulation_block, "scheduled_curtailment")
            ],
            start=0,
        )

    def _annual_curtailment(self, block: pyo.Block, modeled_year: pd.Timestamp):
        annual_curtailment = 0
        for resource in self.resource_instances.values():
            if hasattr(resource.formulation_block, "scheduled_curtailment"):
                annual_curtailment += block.model().sum_timepoint_component_slice_to_annual(
                    resource.formulation_block.scheduled_curtailment[modeled_year, :, :]
                )
        return annual_curtailment

    ###########################
    # Fuel Optimization Rules #
    ###########################

    def _zonal_plant_production_by_product(self, block, product, modeled_year, dispatch_window, timestamp):
        """Zonal production by product for plants."""
        return sum(
            producing_plant.plant.formulation_block.produced_product_to_zone[
                product, modeled_year, dispatch_window, timestamp
            ]
            for producing_plant in self.producing_plants.values()
            if producing_plant.plant.has_operational_rules and product in producing_plant.plant.produced_products.keys()
        )

    def _zonal_demand_production_by_product(self, block, product, modeled_year, dispatch_window, timestamp):
        """Zonal production by product for demands."""
        return sum(
            producing_demand.demand.formulation_block.produced_product_to_zone[
                product, modeled_year, dispatch_window, timestamp
            ]
            for producing_demand in self.producing_demands.values()
            if product in producing_demand.demand.produced_products.keys()
        )

    def _zonal_production_by_product(
        self,
        block: pyo.Block,
        product: str,
        modeled_year: pd.Timestamp,
        dispatch_window: pd.Timestamp,
        timestamp: pd.Timestamp,
    ):
        """Zonal production by product currently only accounts for plant and demand production to zone. This means
        that resource production to zone is always considered to be 0, even if a resource nominally has product
        capture. This is fine, as resources only produce electricity products (in the case of storage, accounted for
        in zonal produce power) or pollutants. In the latter case, pollutants are assumed to be released entirely to
        atmosphere."""
        return (
            block.zonal_plant_production_by_product[product, modeled_year, dispatch_window, timestamp]
            + block.zonal_demand_production_by_product[product, modeled_year, dispatch_window, timestamp]
        )

    def _zonal_plant_consumption_by_product(self, block, product, modeled_year, dispatch_window, timestamp):
        """Zonal consumption by product for plants."""
        return sum(
            consuming_plant.plant.formulation_block.consumed_product_from_zone[
                product, modeled_year, dispatch_window, timestamp
            ]
            for consuming_plant in self.consuming_plants.values()
            if consuming_plant.plant.has_operational_rules and product in consuming_plant.plant.consumed_products.keys()
        )

    def _zonal_demand_consumption_by_product(self, block, product, modeled_year, dispatch_window, timestamp):
        """Zonal consumption by product for demands."""
        return sum(
            consuming_demand.demand.formulation_block.consumption[product, modeled_year, dispatch_window, timestamp]
            for consuming_demand in self.consuming_demands.values()
            if product in consuming_demand.demand.consumed_products.keys()
        )

    def _zonal_resource_consumption_by_product(self, block, product, modeled_year, dispatch_window, timestamp):
        """Zonal consumption by product for resources."""
        return sum(
            resource.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
                product, modeled_year, dispatch_window, timestamp
            ]
            for resource in self.resource_instances.values()
            if hasattr(resource, "candidate_fuels") and resource.has_operational_rules
            if product in resource.candidate_fuels.keys()
        )

    def _zonal_consumption_by_product(
        self,
        block: pyo.Block,
        product: str,
        modeled_year: pd.Timestamp,
        dispatch_window: pd.Timestamp,
        timestamp: pd.Timestamp,
    ):
        """Zonal consumption by product for plants, demands, and resources production."""
        return (
            block.zonal_plant_consumption_by_product[product, modeled_year, dispatch_window, timestamp]
            + block.zonal_demand_consumption_by_product[product, modeled_year, dispatch_window, timestamp]
            + block.zonal_resource_consumption_by_product[product, modeled_year, dispatch_window, timestamp]
        )

    def _zonal_sequestration_by_product(
        self,
        block: pyo.Block,
        product: str,
        modeled_year: pd.Timestamp,
        dispatch_window: pd.Timestamp,
        timestamp: pd.Timestamp,
    ):
        return sum(
            sequestering_plant.plant.formulation_block.produced_product_sequestered[
                product, modeled_year, dispatch_window, timestamp
            ]
            for sequestering_plant in self.sequestering_plants.values()
            if sequestering_plant.plant.has_operational_rules and product == sequestering_plant.plant.primary_product
        )

    def _zonal_net_imports_by_product(
        self,
        block: pyo.Block,
        product: str,
        modeled_year: pd.Timestamp,
        dispatch_window: pd.Timestamp,
        timestamp: pd.Timestamp,
    ):
        net_imports = sum(
            transportation.formulation_block.net_transmit_product[product, modeled_year, dispatch_window, timestamp]
            for transportation in self.transportation_instances_to_zone.values()
            if product in transportation.products.keys()
        ) - sum(
            transportation.formulation_block.net_transmit_product[product, modeled_year, dispatch_window, timestamp]
            for transportation in self.transportation_instances_from_zone.values()
            if product in transportation.products.keys()
        )
        return net_imports

    def _zonal_flow_balance_by_product(
        self,
        block: pyo.Block,
        product: str,
        modeled_year: pd.Timestamp,
        dispatch_window: pd.Timestamp,
        timestamp: pd.Timestamp,
    ):
        if self.products[product].instance_to.commodity:
            return pyo.Constraint.Skip
        else:
            """Flow balance by product must be maintained"""
            return (
                block.zonal_production_by_product[product, modeled_year, dispatch_window, timestamp]
                + block.zonal_net_imports_by_product[product, modeled_year, dispatch_window, timestamp]
                + block.unmet_demand[product, modeled_year, dispatch_window, timestamp]
                == block.zonal_consumption_by_product[product, modeled_year, dispatch_window, timestamp]
                + block.overproduction[product, modeled_year, dispatch_window, timestamp]
            )

    # TODO: Test gross imports and exports
    def _hourly_energy_prices_by_product_unweighted(
        self,
        block: pyo.Block,
        product_name: str,
        modeled_year: pd.Timestamp,
        dispatch_window: pd.Timestamp,
        timestamp: pd.Timestamp,
    ):
        """Hourly unweighted product prices. If the product is a commodity product, then the price of the product is
        provided. Otherwise, the dual, unweighted by relevant factors, is calculated. Electricity products are
        excluded from this."""
        product = self.products[product_name].instance_to
        if product.commodity:
            return product.price_per_unit.data.at[timestamp.replace(year=modeled_year.year)]
        else:
            zonal_flow_balance_dual = self.formulation_block.zonal_flow_balance_by_product[
                product_name,
                modeled_year,
                dispatch_window,
                timestamp,
            ].get_suffix_value("dual", default=np.nan)

            annual_discount_factor = block.model().temporal_settings.modeled_year_discount_factors.data.at[modeled_year]
            num_days_in_modeled_year = block.model().num_days_per_modeled_year[modeled_year]
            dispatch_window_weight = block.model().temporal_settings.dispatch_window_weights.at[dispatch_window]
            timestamp_duration_hours = block.model().timestamp_durations_hours[dispatch_window, timestamp]

            return (
                zonal_flow_balance_dual
                / annual_discount_factor
                / num_days_in_modeled_year
                / dispatch_window_weight
                / timestamp_duration_hours
            )

    def _hourly_energy_prices_by_product_weighted(
        self,
        block: pyo.Block,
        product_name: str,
        modeled_year: pd.Timestamp,
        dispatch_window: pd.Timestamp,
        timestamp: pd.Timestamp,
    ):
        """Hourly weighted product prices. If the product is a commodity product, then the price of the product,
        weighted by relevant factors, is provided. Otherwise, the dual is calculated. Electricity products are
        excluded from this."""
        product = self.products[product_name].instance_to
        if product.commodity:

            annual_discount_factor = block.model().temporal_settings.modeled_year_discount_factors.data.at[modeled_year]
            num_days_in_modeled_year = block.model().num_days_per_modeled_year[modeled_year]
            dispatch_window_weight = block.model().temporal_settings.dispatch_window_weights.at[dispatch_window]
            timestamp_duration_hours = block.model().timestamp_durations_hours[dispatch_window, timestamp]

            return (
                product.price_per_unit.data.at[timestamp.replace(year=modeled_year.year)]
                * annual_discount_factor
                * num_days_in_modeled_year
                * dispatch_window_weight
                * timestamp_duration_hours
            )
        else:
            zonal_flow_balance_dual = self.formulation_block.zonal_flow_balance_by_product[
                product_name,
                modeled_year,
                dispatch_window,
                timestamp,
            ].get_suffix_value("dual", default=np.nan)

        return zonal_flow_balance_dual

    def _annual_unmet_demand(self, block: pyo.Block, product: str, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(block.unmet_demand[product, modeled_year, :, :])

    def _annual_overproduction(self, block: pyo.Block, product: str, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(block.overproduction[product, modeled_year, :, :])

    def _annual_plant_production_by_product(self, block: pyo.Block, product: str, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.zonal_plant_production_by_product[product, modeled_year, :, :]
        )

    def _annual_demand_production_by_product(self, block: pyo.Block, product: str, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.zonal_demand_production_by_product[product, modeled_year, :, :]
        )

    def _annual_zonal_production_by_product(self, block: pyo.Block, product: str, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.zonal_production_by_product[product, modeled_year, :, :]
        )

    def _annual_resource_consumption_by_product(self, block: pyo.Block, product: str, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.zonal_resource_consumption_by_product[product, modeled_year, :, :]
        )

    def _annual_plant_consumption_by_product(self, block: pyo.Block, product: str, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.zonal_plant_consumption_by_product[product, modeled_year, :, :]
        )

    def _annual_demand_consumption_by_product(self, block: pyo.Block, product: str, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.zonal_demand_consumption_by_product[product, modeled_year, :, :]
        )

    def _annual_zonal_consumption_by_product(self, block: pyo.Block, product: str, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.zonal_consumption_by_product[product, modeled_year, :, :]
        )

    def _annual_zonal_sequestration_by_product(self, block: pyo.Block, product: str, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.zonal_sequestration_by_product[product, modeled_year, :, :]
        )

    def _annual_zonal_net_imports_by_product(self, block: pyo.Block, product: str, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.zonal_net_imports_by_product[product, modeled_year, :, :]
        )

    def _annual_zonal_net_release_by_product(self, block: pyo.Block, product: str, modeled_year: pd.Timestamp):
        """Annual net release to atmosphere by product. This currently does not include resource emissions"""
        model: ModelTemplate = block.model()

        gross_capture = sum(
            model.sum_timepoint_component_slice_to_annual(
                plant_linkage.plant.formulation_block.consumed_product_capture[product, modeled_year, :, :]
            )
            for plant_linkage in self.consuming_plants.values()
            if product in plant_linkage.plant.consumed_products.keys() and plant_linkage.plant.has_operational_rules
        )

        gross_release = sum(
            model.sum_timepoint_component_slice_to_annual(
                plant_linkage.plant.formulation_block.produced_product_release[product, modeled_year, :, :]
            )
            for plant_linkage in self.producing_plants.values()
            if product in plant_linkage.plant.produced_products.keys() and plant_linkage.plant.has_operational_rules
        ) + sum(
            model.sum_timepoint_component_slice_to_annual(
                demand_linkage.demand.formulation_block.produced_product_release[product, modeled_year, :, :]
            )
            for demand_linkage in self.producing_demands.values()
            if product in demand_linkage.demand.produced_products.keys()
        )

        return gross_release - gross_capture

    # TODO: Need to write tests for this and exports below
    def _annual_gross_imports_by_product(self, block: pyo.Block, product, modeled_year: pd.Timestamp):
        """Annual gross imports by product, similar to annual gross imports."""
        model: ModelTemplate = block.model()
        annual_gross_imports = sum(
            model.sum_timepoint_component_slice_to_annual(
                transportation_from_zone.formulation_block.transmit_product_reverse[product, modeled_year, :, :]
            )
            for transportation_from_zone in self.transportation_instances_from_zone.values()
            if product in transportation_from_zone.products.keys()
        )
        annual_gross_imports += sum(
            model.sum_timepoint_component_slice_to_annual(
                transportation_to_zone.formulation_block.transmit_product_forward[product, modeled_year, :, :]
            )
            for transportation_to_zone in self.transportation_instances_to_zone.values()
            if product in transportation_to_zone.products.keys()
        )

        return annual_gross_imports

    def _annual_gross_exports_by_product(self, block: pyo.Block, product, modeled_year: pd.Timestamp):
        """Annual gross exports by product, similar to annual gross exports."""
        model: ModelTemplate = block.model()
        annual_gross_exports = sum(
            model.sum_timepoint_component_slice_to_annual(
                transportation_from_zone.formulation_block.transmit_product_forward[product, modeled_year, :, :]
            )
            for transportation_from_zone in self.transportation_instances_from_zone.values()
            if product in transportation_from_zone.products.keys()
        )
        annual_gross_exports += sum(
            model.sum_timepoint_component_slice_to_annual(
                transportation_to_zone.formulation_block.transmit_product_reverse[product, modeled_year, :, :]
            )
            for transportation_to_zone in self.transportation_instances_to_zone.values()
            if product in transportation_to_zone.products.keys()
        )

        return annual_gross_exports
