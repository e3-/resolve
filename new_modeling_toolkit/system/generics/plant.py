from __future__ import annotations

from typing import Annotated
from typing import ClassVar
from typing import Union

import numpy as np
import pandas as pd
from loguru import logger
from pydantic import computed_field
from pydantic import Field
from pydantic import model_validator
from pyomo import environ as pyo

from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.custom_model import units
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.temporal.timeseries import FractionalTimeseries
from new_modeling_toolkit.core.temporal.timeseries import NumericTimeseries
from new_modeling_toolkit.system import Asset
from new_modeling_toolkit.system import AssetGroup
from new_modeling_toolkit.system.generics.generic_linkages import FromZoneToPlant
from new_modeling_toolkit.system.generics.generic_linkages import ToZoneToPlant
from new_modeling_toolkit.system.generics.process import Process


# TODO (BKW 10/4/2024): There seems to be additional pmin/pmax code on the resource class that accounts for planned
#  builds. Speak with BM about whether this needs to be implemented on the plant class as well.
class Plant(Asset):
    SAVE_PATH: ClassVar[str] = "plants"

    @property
    def results_reporting_category(self):
        return "Plant"

    @property
    def results_reporting_folder(self):
        return f"{self.results_reporting_category}/{self.__class__.__name__}"

    # TODO: update to primary_produced_product for consistency with Demand.primary_consumed_product?
    primary_product: Annotated[str, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        default="", description="This string defines the primary produced product of this plant."
    )
    processes: Annotated[dict[Union[tuple[str, str], str], Process], Metadata(category=FieldCategory.OPERATIONS)] = (
        Field(
            default_factory=dict,
            description="These three-way linkages define the input-output relationships between products on a plant",
        )
    )
    input_zones: Annotated[dict[str, FromZoneToPlant], Metadata(category=FieldCategory.OPERATIONS)] = Field(
        default_factory=dict, description="These zones are those from which the plant consumes product."
    )
    output_zones: Annotated[dict[str, ToZoneToPlant], Metadata(category=FieldCategory.OPERATIONS)] = Field(
        default_factory=dict, description="These zones are those to which the plant produces product."
    )

    @property
    def produced_products(self):
        """Unique output products."""
        return {process.produced_product.name: process.produced_product for process in self.processes.values()}

    @property
    def consumed_products(self):
        """Unique input products."""
        return {process.consumed_product.name: process.consumed_product for process in self.processes.values()}

    @property
    def products(self):
        return self.consumed_products | self.produced_products

    @property
    def primary_product_unit(self):
        return self.products[self.primary_product].unit

    @property
    def capacity_unit(self):
        return self.primary_product_unit / units.hour

    @property
    def primary_output_processes(self):
        return [process for process in self.processes.values() if process.produced_product.name == self.primary_product]

    @property
    def primary_process_output_capture_rate(self):
        # TODO: make dict rather than list for consistency
        return [process.output_capture_rate for process in self.primary_output_processes][0]

    ramp_up_limit: Annotated[float, Metadata(category=FieldCategory.OPERATIONS, units=1 / units.hour)] = Field(
        default=1,
        description="Single-hour ramp up rate.",
        down_method="none",
    )
    ramp_down_limit: Annotated[float, Metadata(category=FieldCategory.OPERATIONS, units=1 / units.hour)] = Field(
        default=1,
        description="Single-hour ramp down rate.",
        down_method="none",
    )

    min_output_profile: Annotated[FractionalTimeseries, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        default_factory=FractionalTimeseries.zero,
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
        operational_attribute=True,
    )
    max_output_profile: Annotated[FractionalTimeseries, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        default_factory=FractionalTimeseries.one,
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
        operational_attribute=True,
    )
    # TODO: For many attributes, including variable costs and ptc, we need some way of changing the units to match the
    #  primary product of the Plant.
    ###################
    # Cost Attributes #
    ###################
    variable_cost: Annotated[
        NumericTimeseries,
        Metadata(
            category=FieldCategory.OPERATIONS,
            excel_short_title="VO&M In",
        ),
    ] = Field(
        default_factory=NumericTimeseries.zero,
        description="Variable O&M cost per unit product generated.",  # TODO: Need a way to dynamically specify capacity/energy units
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        weather_year=True,
        operational_attribute=True,
        title=f"Variable O&M Cost",
    )
    # TODO: move ptc attributes and properties to Asset, share with GenericResource
    # current issue - ptc attributes and properties on GenericResource have specific units associated with them
    production_tax_credit: Annotated[
        float | None,
        Metadata(excel_short_title="PTC"),
    ] = Field(
        None,
        title=f"Production Tax Credit",
    )
    ptc_term: Annotated[
        int | None,
        Metadata(units=units.years, excel_short_title="PTC Term"),
    ] = Field(
        None,
        title=f"PTC Term",
    )

    @model_validator(mode="after")
    def check_ptc_term(self):
        """If PTC is defined, it needs a PTC term."""
        if self.production_tax_credit is not None and self.production_tax_credit != 0:
            assert self.ptc_term is not None, "PTC term (years) is missing"
        if self.ptc_term is not None:
            assert self.production_tax_credit is not None, "PTC ($/MWh) is missing"

        return self

    @property
    def production_tax_credit_ts(self) -> ts.NumericTimeseries:
        if self.production_tax_credit is None:
            return ts.NumericTimeseries.zero()
        return ts.NumericTimeseries(
            name="PTC timeseries",
            data=pd.Series(
                self.production_tax_credit, index=pd.date_range(start=self.build_year, freq="YS", periods=self.ptc_term)
            ),
            weather_year=False,
            default_freq="YS",
        )

    def revalidate(self):
        super().revalidate()

        if self.potential is None:
            self.potential = np.inf

        if len(self.input_zones) == 0:
            raise AssertionError(f"`{self.__class__.__name__}` `{self.name}` is not linked to any Input Zone")

        if len(self.output_zones) == 0:
            raise AssertionError(f"`{self.__class__.__name__}` `{self.name}` is not linked to any Output Zone")

        if len(self.consumed_products) == 0:
            raise AssertionError(f"`{self.__class__.__name__}` should have at least one consumed product")

        if len(self.produced_products) == 0:
            raise AssertionError(f"`{self.__class__.__name__}` should have at least one produced product")

        if any(product.commodity for product in self.produced_products.values()):
            raise AssertionError(
                f"No produced products for `{self.__class__.__name__}` `{self.name}` can be a commodity."
            )

        if self.primary_product not in self.produced_products.keys():
            raise AssertionError(
                f"`{self.__class__.__name__}` `{self.name}`'s primary product not linked as an "
                f"output product of any of its processes. Check your `three_way_linkages.csv` file."
            )

        if len(self.processes) == 0:
            raise AssertionError(f"`{self.__class__.__name__}` should have at least one defined process")

        # All consumed products must be linked to the plant's primary_product via a process
        for consumed_product in self.consumed_products.values():
            count = len(
                [
                    process
                    for process in self.processes.values()
                    if (consumed_product.name == process.consumed_product.name)
                    & (process.produced_product.name == self.primary_product)
                ]
            )
            if count == 0:
                raise AssertionError(
                    f"`{self.__class__.__name__}` `{self.name}`'s consumed product `{consumed_product.name}` "
                    f"is not linked to the plant's primary product `{self.primary_product}` via any process. Check your "
                    f"`three_way_linkages.csv` file."
                )

        # Consumed products should be linked to plant's input zones, produced products to output zones
        input_zone = set(self.input_zones.keys())
        output_zone = set(self.output_zones.keys())

        for process in self.processes.values():
            if not any(key in input_zone for key in process.consumed_product.zones.keys()):
                raise ValueError(
                    f"Consumed product `{process.consumed_product.name}` from process "
                    f"`{process.consumed_product.name} → {self.name} → {process.produced_product.name}` "
                    f"is not linked to any the input zones of `{self.__class__.__name__}` `{self.name}`. Check your `linkages.csv` file."
                )

            if not any(key in output_zone for key in process.produced_product.zones.keys()):
                raise ValueError(
                    f"Produced product `{process.produced_product.name}` from process "
                    f"`{process.consumed_product.name} → {self.name} → {process.produced_product.name}` "
                    f"is not linked to any the output zones of `{self.__class__.__name__}` `{self.name}`. Check your `linkages.csv` file."
                )

        # Ensure that all primary processes have the same output rate
        if len(set(process.output_capture_rate for process in self.primary_output_processes)) > 1:
            logger.warning(
                f"`{self.__class__.__name__}` `{self.name}` primary processes must have the same output capture rate. "
                f"This `{self.__class__.__name__}` will assume that the first primary process's output capture rate is "
                f"the output capture rate for all primary processes."
            )

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_investment_rules(model, construct_costs=construct_costs)
        pyomo_components["selected_capacity"].doc = f"Selected Capacity ({self.capacity_unit:e3})"
        pyomo_components["retired_capacity"].doc = f"Retired Capacity ({self.capacity_unit:e3})"
        pyomo_components["operational_capacity"].doc = f"Operational Capacity ({self.capacity_unit:e3})"

        return pyomo_components

    def _construct_operational_rules(
        self, model: ModelTemplate, construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

        INPUTS = pyo.Set(initialize=self.consumed_products.keys())
        OUTPUTS = pyo.Set(initialize=self.produced_products.keys())
        pyomo_components.update(
            INPUTS=INPUTS,
            OUTPUTS=OUTPUTS,
            operation=pyo.Var(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                within=pyo.NonNegativeReals,
                initialize=0,
                doc=f"Hourly Operation ({self.capacity_unit:e3})",
            ),
            scaled_min_output_profile=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._scaled_min_output_profile,
            ),
            scaled_max_output_profile=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._scaled_max_output_profile,
            ),
            consumption=pyo.Expression(
                INPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._consumption,
                doc=f"Hourly Consumption of Input Product (Product Units per hour)",
            ),
            production=pyo.Expression(
                OUTPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._production,
                doc=f"Hourly Production of Output Product (Product Units per hour)",
            ),
            consumed_product_capture=pyo.Expression(
                INPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._consumed_product_capture,
                doc="Hourly Consumed Product Capture (Product Units per hour)",
            ),
            consumed_product_from_zone=pyo.Expression(
                INPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._consumed_product_from_zone,
                doc="Hourly Consumed Product From Zone (Product Units per hour)",
            ),
            produced_product_to_zone=pyo.Expression(
                OUTPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._produced_product_to_zone,
                doc="Hourly Produced Product To Zone (Product Units per hour)",
            ),
            produced_product_release=pyo.Expression(
                OUTPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._produced_product_release,
                doc="Hourly Produced Product Release (Product Units per hour)",
            ),
            min_output_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._min_output_constraint,
            ),
            max_output_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._max_output_constraint,
            ),
        )

        if construct_costs:
            pyomo_components.update(
                variable_cost_dispatched=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._variable_cost_dispatched,
                ),
                production_tax_credit=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._production_tax_credit,
                    doc="Production Tax Credit ($)",
                ),
                annual_variable_cost_dispatched=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_variable_cost_dispatched,
                ),
                annual_variable_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=self._annual_variable_cost, doc="Annual Total Variable Cost ($)"
                ),
                annual_production_tax_credit=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_production_tax_credit,
                    doc="Annual Production Tax Credit ($)",
                ),
                consumed_commodity_product_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._consumed_commodity_product_cost,
                ),
                annual_consumed_commodity_product_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_consumed_commodity_product_cost,
                    doc="Annual Total Consumed Commodity Product Cost ($)",
                ),
                annual_total_operational_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_operational_cost,
                    doc="Annual Total Operational Cost ($)",
                ),
            )
        return pyomo_components

    def _construct_output_expressions(self, construct_costs: bool):
        super()._construct_output_expressions(construct_costs)
        model: ModelTemplate = self.formulation_block.model()

        if self.has_operational_rules:
            self.formulation_block.annual_consumption = pyo.Expression(
                self.formulation_block.INPUTS,
                model.MODELED_YEARS,
                rule=self._annual_consumption,
                doc="Annual Product Consumption (Product Units)",
            )
            self.formulation_block.annual_production = pyo.Expression(
                self.formulation_block.OUTPUTS,
                model.MODELED_YEARS,
                rule=self._annual_production,
                doc="Annual Product Production (Product Units)",
            )
            self.formulation_block.annual_consumed_product_capture = pyo.Expression(
                self.formulation_block.INPUTS,
                model.MODELED_YEARS,
                rule=self._annual_consumed_product_capture,
                doc="Annual Consumed Product Capture (Product Units)",
            )
            self.formulation_block.annual_consumed_product_from_zone = pyo.Expression(
                self.formulation_block.INPUTS,
                model.MODELED_YEARS,
                rule=self._annual_consumed_product_from_zone,
                doc="Annual Consumed Product From Zone (Product Units)",
            )
            self.formulation_block.annual_produced_product_to_zone = pyo.Expression(
                self.formulation_block.OUTPUTS,
                model.MODELED_YEARS,
                rule=self._annual_produced_product_to_zone,
                doc="Annual Produced Product To Zone (Product Units)",
            )
            self.formulation_block.annual_produced_product_release = pyo.Expression(
                self.formulation_block.OUTPUTS,
                model.MODELED_YEARS,
                rule=self._annual_produced_product_release,
                doc="Annual Produced Product Release (Product Units)",
            )

    def _annual_capital_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Capital costs for Plant. Nearly the same as Asset, except capacity costs and capacity are both expressed
        in the same units"""
        return super()._annual_capital_cost(block, modeled_year) / 1e3

    def _annual_fixed_om_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Fixed O&M costs of capacity for Plant in each year. Nearly the same as Asset, except capacity costs and
        capacity are expressed in the same units"""
        return super()._annual_fixed_om_cost(block, modeled_year) / 1e3

    def _scaled_min_output_profile(self, block, modeled_year, dispatch_window, timestamp):
        return block.operational_capacity[modeled_year] * self.min_output_profile.data.at[timestamp]

    def _scaled_max_output_profile(self, block, modeled_year, dispatch_window, timestamp):
        return block.operational_capacity[modeled_year] * self.max_output_profile.data.at[timestamp]

    def _consumption(self, block, input, modeled_year, dispatch_window, timestamp):
        """Consumption of inputs are calculated based on processes that produce this plant's primary product. It is
        implicitly assumed that there are no processes that map the same input-output relationship on this plant and
        that all inputs have a process defined for the primary output. In other words, the sum below should be over a
        single unique process for each input."""
        return sum(
            block.operation[modeled_year, dispatch_window, timestamp] / process.conversion_rate
            for process in self.primary_output_processes
            if process.consumed_product.name == input
        )

    def _consumed_product_capture(self, block, input, modeled_year, dispatch_window, timestamp):
        """This represents the consumption of inputs derived by some capture process. This capture process is assumed to
        pull in product that exists **externally** to the system. In general, this will be 0, unless it is
        believed that the product is some form of captured atmospheric pollutant."""
        return sum(
            block.operation[modeled_year, dispatch_window, timestamp]
            / process.conversion_rate
            * process.input_capture_rate
            for process in self.primary_output_processes
            if process.consumed_product.name == input
        )

    def _consumed_product_from_zone(self, block, input, modeled_year, dispatch_window, timestamp):
        """This represents the consumption of inputs pulled directly from the plant's linked zone. This will
        typically equal the value of the consumption expression, unless it is believed that the product is some form
        of captured atmospheric pollutant."""
        return (
            block.consumption[input, modeled_year, dispatch_window, timestamp]
            - block.consumed_product_capture[input, modeled_year, dispatch_window, timestamp]
        )

    def _production(self, block, output, modeled_year, dispatch_window, timestamp):
        """This formulation assumes that primary product production is equal to plant operation. All other outputs'
        productions are assumed to be the sum of their contributing processes."""
        if output == self.primary_product:
            return block.operation[modeled_year, dispatch_window, timestamp]
        else:
            return sum(
                block.consumption[process.consumed_product.name, modeled_year, dispatch_window, timestamp]
                * process.conversion_rate
                for process in self.processes.values()
                if process.produced_product.name == output
            )

    def _produced_product_to_zone(self, block, output, modeled_year, dispatch_window, timestamp):
        """This represents capture of output product, i.e. injection of output product into the plant's linked zone.
        This typically will equal the value of the production expression, unless it is believed that the output
        product is instead a released atmospheric pollution"""
        if output == self.primary_product:
            return block.operation[modeled_year, dispatch_window, timestamp] * self.primary_process_output_capture_rate
        else:
            return sum(
                block.consumption[process.consumed_product.name, modeled_year, dispatch_window, timestamp]
                * process.conversion_rate
                * process.output_capture_rate
                for process in self.processes.values()
                if process.produced_product.name == output
            )

    def _produced_product_release(self, block, output, modeled_year, dispatch_window, timestamp):
        """This represents release of output product **external** of the system. This will typically be 0,
        unless it is believed that the output product is instead a released atmospheric pollutant."""
        return (
            block.production[output, modeled_year, dispatch_window, timestamp]
            - block.produced_product_to_zone[output, modeled_year, dispatch_window, timestamp]
        )

    def _variable_cost_dispatched(self, block, modeled_year, dispatch_window, timestamp):
        return block.operation[modeled_year, dispatch_window, timestamp] * self.variable_cost.data.at[timestamp]

    def _production_tax_credit(self, block, modeled_year, dispatch_window, timestamp):
        """The production tax credit earned by the Plant in a given timepoint for producing the Plant's primary product.
        This term is not discounted (i.e. it is not multiplied by the discount factor for the relevant model year)."""
        if (
            self.production_tax_credit is None
            or modeled_year < self.build_year
            or modeled_year
            >= self.build_year.replace(year=self.build_year.year + (self.ptc_term if self.ptc_term is not None else 0))
        ):
            return 0
        return (
            self.formulation_block.production[self.primary_product, modeled_year, dispatch_window, timestamp]
            * self.production_tax_credit_ts.data.at[modeled_year]
        )

    def _annual_variable_cost_dispatched(self, block, modeled_year):
        model: ModelTemplate = block.model()
        return model.sum_timepoint_component_slice_to_annual(block.variable_cost_dispatched[modeled_year, :, :])

    def _annual_variable_cost(self, block, modeled_year):
        """
        Variable O&M costs
        """
        return block.annual_variable_cost_dispatched[modeled_year]

    def _annual_production_tax_credit(self, block, modeled_year: pd.Timestamp):
        """The production tax credit earned by the Resource in a given timepoint. This term is not discounted
        (i.e. it is not multiplied by the discount factor for the relevant model year)."""
        return self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.production_tax_credit[modeled_year, :, :]
        )

    def _consumed_commodity_product_cost(self, block, modeled_year, dispatch_window, timestamp):
        """Operational cost from consuming commodity product"""
        return sum(
            block.consumption[product_name, modeled_year, dispatch_window, timestamp]
            * product.price_per_unit.data.at[timestamp.replace(year=modeled_year.year)]
            for product_name, product in self.consumed_products.items()
            if product.commodity
        )

    def _annual_consumed_commodity_product_cost(self, block, modeled_year):
        """Annual operational cost from consuming commodity product"""
        return block.model().sum_timepoint_component_slice_to_annual(
            block.consumed_commodity_product_cost[modeled_year, :, :]
        )

    def _annual_total_operational_cost(self, block, modeled_year):
        """The total annual operational costs of the Plant, including both variable O&M, consumed product costs, and
        production tax credits. This term is not discounted (i.e. it is not multiplied by the discount factor for the
        relevant model year)."""
        return (
            block.annual_variable_cost[modeled_year]
            + block.annual_consumed_commodity_product_cost[modeled_year]
            - block.annual_production_tax_credit[modeled_year]
        )

    def _min_output_constraint(self, block, modeled_year, dispatch_window, timestamp):
        """Constrain minimum plant operation."""
        return (
            block.operation[modeled_year, dispatch_window, timestamp]
            >= block.scaled_min_output_profile[modeled_year, dispatch_window, timestamp]
        )

    def _max_output_constraint(self, block, modeled_year, dispatch_window, timestamp):
        """Constrain maximum plant operation."""
        return (
            block.operation[modeled_year, dispatch_window, timestamp]
            <= block.scaled_max_output_profile[modeled_year, dispatch_window, timestamp]
        )

    def _annual_consumption(self, block, product, modeled_year):
        model: ModelTemplate = block.model()
        return model.sum_timepoint_component_slice_to_annual(block.consumption[product, modeled_year, :, :])

    def _annual_production(self, block, product, modeled_year):
        model: ModelTemplate = block.model()
        return model.sum_timepoint_component_slice_to_annual(block.production[product, modeled_year, :, :])

    def _annual_consumed_product_capture(self, block, input, modeled_year):
        """Annual consumed product capture."""
        return block.model().sum_timepoint_component_slice_to_annual(
            block.consumed_product_capture[input, modeled_year, :, :]
        )

    def _annual_consumed_product_from_zone(self, block, input, modeled_year):
        """Annual consumed product from zone."""
        return (
            block.annual_consumption[input, modeled_year] - block.annual_consumed_product_capture[input, modeled_year]
        )

    def _annual_produced_product_to_zone(self, block, output, modeled_year):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.produced_product_to_zone[output, modeled_year, :, :]
        )

    def _annual_produced_product_release(self, block, output, modeled_year):
        return (
            block.annual_production[output, modeled_year] - block.annual_produced_product_to_zone[output, modeled_year]
        )


class PlantGroup(AssetGroup, Plant):
    SAVE_PATH: ClassVar[str] = "plants/plant_groups"
    _NAME_PREFIX: ClassVar[str] = "plant_groups"
    _GROUPING_CLASS = Plant

    @computed_field(title="Plant List")
    @property
    def list_of_plant_names(self) -> list:
        return list(self.asset_instances.keys())

    @property
    def results_reporting_category(self):
        return "PlantGroup"

    @property
    def production_tax_credit_ts(self) -> ts.NumericTimeseries:
        if self.production_tax_credit is None:
            return ts.NumericTimeseries.zero()
        else:
            return ts.NumericTimeseries(
                name="PTC timeseries",
                data=pd.Series(
                    self.production_tax_credit,
                    index=pd.date_range(start=self.earliest_build_year, freq="YS", periods=self.ptc_term),
                ),
                weather_year=False,
                default_freq="YS",
            )

    def _production_tax_credit(self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp):
        """The production tax credit earned by the Resource in a given timepoint. This term is not discounted
        (i.e. it is not multiplied by the discount factor for the relevant model year)."""
        # TODO: PTC credit calculation on operational groups does not account for different start and end dates of
        #  PTC term for different build years within the group
        if (
            self.production_tax_credit is None
            or modeled_year < self.earliest_build_year
            or modeled_year
            >= self.earliest_build_year.replace(
                year=self.earliest_build_year.year + (self.ptc_term if self.ptc_term is not None else 0)
            )
        ):
            return 0
        return (
            self.formulation_block.production[self.primary_product, modeled_year, dispatch_window, timestamp]
            * self.production_tax_credit_ts.data.at[modeled_year]
        )
