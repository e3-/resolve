from typing import Annotated
from typing import ClassVar

import numpy as np
import pandas as pd
from pydantic import Field
from pyomo import environ as pyo

from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.custom_model import units
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.system import Asset
from new_modeling_toolkit.system.generics.generic_linkages import ProductToTransportation
from new_modeling_toolkit.system.generics.generic_linkages import ZoneToTransportation


class Transportation(Asset):
    # TODO: copied from TxPath - clean up/possibly combine later rather than copying code
    SAVE_PATH: ClassVar[str] = "transportations"

    #############
    # Linkages #
    #############

    zones: Annotated[dict[str, ZoneToTransportation], Metadata(linkage_order="from")] = {}
    products: Annotated[dict[str, ProductToTransportation], Metadata(linkage_order="from")] = {}

    ##########################
    # Operational Attributes #
    ##########################

    forward_rating_profile: Annotated[
        ts.FractionalTimeseries | None, Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Forward Rating")
    ] = Field(
        default_factory=ts.FractionalTimeseries.one,
        description="Normalized fixed shape of Transportation's potential forward rating",
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
        title="Forward Rating Profile",
    )

    reverse_rating_profile: Annotated[
        ts.FractionalTimeseries | None, Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Forward Rating")
    ] = Field(
        default_factory=ts.FractionalTimeseries.one,
        description="Normalized fixed shape of Transportation's potential reverse rating",
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
        title="Reverse Rating Profile",
    )

    ###################
    # Cost Attributes #
    ###################

    @property
    def unit(self):
        if self.products:
            return list(product.product.unit for product in self.products.values())[0]

    @property
    def capacity_unit(self):
        return self.unit / units.hour

    ###########
    # Methods #
    ###########

    @property
    def from_zone(self):
        if self.zones:
            zones = [z for z in self.zones.values() if z.from_zone]
            if len(zones) > 1:
                raise ValueError(
                    f"Multiple zones ({zones}) are marked as being on the 'from' side of path '{self.name}'."
                )
            elif len(zones) == 0:
                raise ValueError(f"No zones assigned as 'from' zone of path '{self.name}'.")
            else:
                # Return first (only) zone in the list
                return zones[0]

    @property
    def to_zone(self):
        if self.zones:
            zones = [z for z in self.zones.values() if z.to_zone]
            if len(zones) > 1:
                raise ValueError(
                    f"Multiple zones ({zones}) are marked as being on the 'to' side of path '{self.name}'."
                )
            elif len(zones) == 0:
                raise ValueError("No zones assigned as 'to' zone of path '{self.name}'.")
            else:
                # Return first (only) zone in the list
                return zones[0]

    def revalidate(self):
        def all_product_units_are_equal():
            return len(set(product.product.unit for product in self.products.values())) <= 1

        def products_are_subset_of_connected_zones():
            return set(product_linkage.instance_to.name for product_linkage in list(self.products.values())).issubset(
                set(zone_linkage.instance_to.name for zone_linkage in list(self.zones.values()))
            )

        if self.potential is None:
            self.potential = np.inf

        if self.from_zone is None:
            raise ValueError(
                f"Transportation `{self.name}` has no `from_zone` assigned. Check your `linkages.csv` file."
            )
        if self.to_zone is None:
            raise ValueError(f"Transportation `{self.name}` has no `to_zone` assigned. Check your `linkages.csv` file.")
        if self.from_zone == self.to_zone:
            raise ValueError(
                f"Transportation `{self.name}` has the same input and output zone assigned. Check your `linkages.csv` file."
            )
        if len(self.products) > 1:
            if not all_product_units_are_equal():
                raise ValueError(f"Products linked to Transportation `{self.name}` must have the same unit.")
        if not products_are_subset_of_connected_zones():
            raise ValueError(f"Products linked to Transportation `{self.name}` must be a subset of connected zones.")

    ################
    # Optimization #
    ################
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

        PRODUCTS = pyo.Set(initialize=self.products.keys())
        pyomo_components.update(PRODUCTS=PRODUCTS)

        #############
        # Variables #
        #############

        """Amount of product transmitted from "from_zone" to "to_zone" in product units per hour in each modeled
        timepoint (non-negative)."""
        pyomo_components.update(
            transmit_product_forward=pyo.Var(
                PRODUCTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                within=pyo.NonNegativeReals,
                doc=f"Transmit Product Forward by Product ({self.unit:e3} per hour)",
            )
        )
        """Amount of product transmitted from "to_zone" to "from_zone" in product units per hour in each modeled
        timepoint (non-negative)."""
        pyomo_components.update(
            transmit_product_reverse=pyo.Var(
                PRODUCTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                within=pyo.NonNegativeReals,
                doc=f"Transmit Product Reverse by Product ({self.unit:e3} per hour)",
            )
        )
        """Forward transportation is limited by operational capacity"""
        pyomo_components.update(
            transmit_product_forward_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._transmit_product_forward_constraint,
            ),
        )
        """Reverse transportation is limited by operational capacity"""
        pyomo_components.update(
            transmit_product_reverse_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._transmit_product_reverse_constraint,
            )
        )
        """Transportation hourly mileage should be constrained by forward and reverse rating capacities"""
        pyomo_components.update(
            transportation_mileage_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._transportation_mileage_constraint,
            )
        )

        ###############
        # Expressions #
        ###############
        """Net amount of product transmitted in each modeled timepoint (can be positive or negative)"""
        pyomo_components.update(
            net_transmit_product=pyo.Expression(
                PRODUCTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._net_transmit_product,
                doc=f"Net Transmit by Product ({self.unit:e3} per hour)",
            )
        )

        if construct_costs:
            """Forward hurdle cost in each modeled timepoint"""
            pyomo_components.update(
                hurdle_cost_forward=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._hurdle_cost_forward,
                )
            )

            """Reverse hurdle cost in each modeled timepoint"""
            pyomo_components.update(
                hurdle_cost_reverse=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._hurdle_cost_reverse,
                )
            )

            pyomo_components.update(
                annual_total_operational_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_operational_cost,
                    doc="Annual Total Operational Cost ($)",
                )
            )

        return pyomo_components

    def _construct_output_expressions(self, construct_costs: bool):
        self.formulation_block.from_zone = pyo.Param(
            self.formulation_block.model().MODELED_YEARS,
            initialize=self.from_zone.instance_from.name,
            doc="Zone From",
            within=pyo.Any,
        )
        self.formulation_block.to_zone = pyo.Param(
            self.formulation_block.model().MODELED_YEARS,
            initialize=self.to_zone.instance_from.name,
            doc="Zone To",
            within=pyo.Any,
        )
        self.formulation_block.annual_gross_forward_flow_by_product = pyo.Expression(
            self.formulation_block.PRODUCTS,
            self.formulation_block.model().MODELED_YEARS,
            rule=self._annual_gross_forward_flow_by_product,
            doc=f"Gross Forward Flow by Product ({self.unit:e3})",
        )
        self.formulation_block.annual_gross_reverse_flow_by_product = pyo.Expression(
            self.formulation_block.PRODUCTS,
            self.formulation_block.model().MODELED_YEARS,
            rule=self._annual_gross_reverse_flow_by_product,
            doc=f"Gross Reverse Flow by Product ({self.unit:e3})",
        )
        self.formulation_block.annual_net_forward_flow_by_product = pyo.Expression(
            self.formulation_block.PRODUCTS,
            self.formulation_block.model().MODELED_YEARS,
            rule=self._annual_net_forward_flow_by_product,
            doc=f"Net Forward Flow by Product ({self.unit:e3})",
        )
        self.formulation_block.annual_gross_forward_flow = pyo.Expression(
            self.formulation_block.model().MODELED_YEARS,
            rule=self._annual_gross_forward_flow,
            doc=f"Total Gross Forward Flow ({self.unit:e3})",
        )
        self.formulation_block.annual_gross_reverse_flow = pyo.Expression(
            self.formulation_block.model().MODELED_YEARS,
            rule=self._annual_gross_reverse_flow,
            doc=f"Total Gross Reverse Flow ({self.unit:e3})",
        )
        self.formulation_block.annual_net_forward_flow = pyo.Expression(
            self.formulation_block.model().MODELED_YEARS,
            rule=self._annual_net_forward_flow,
            doc=f"Total Net Forward Flow ({self.unit:e3})",
        )
        self.formulation_block.annual_forward_hurdle_cost = pyo.Expression(
            self.formulation_block.model().MODELED_YEARS,
            rule=self._annual_forward_hurdle_cost,
            doc="Forward Hurdle Cost ($)",
        )
        self.formulation_block.annual_reverse_hurdle_cost = pyo.Expression(
            self.formulation_block.model().MODELED_YEARS,
            rule=self._annual_reverse_hurdle_cost,
            doc="Reverse Hurdle Cost ($)",
        )

    def _annual_capital_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return super()._annual_capital_cost(block, modeled_year) / 1e3

    def _annual_fixed_om_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return super()._annual_fixed_om_cost(block, modeled_year) / 1e3

    def _transmit_product_forward_constraint(self, block, modeled_year, dispatch_window, timestamp):
        return (
            sum(
                block.transmit_product_forward[product, modeled_year, dispatch_window, timestamp]
                for product in block.PRODUCTS
            )
            <= block.operational_capacity[modeled_year] * self.forward_rating_profile.data.at[timestamp]
        )

    def _transmit_product_reverse_constraint(self, block, modeled_year, dispatch_window, timestamp):
        return (
            sum(
                block.transmit_product_reverse[product, modeled_year, dispatch_window, timestamp]
                for product in block.PRODUCTS
            )
            <= block.operational_capacity[modeled_year] * self.reverse_rating_profile.data.at[timestamp]
        )

    def _transportation_mileage_constraint(self, block, modeled_year, dispatch_window, timestamp):
        return sum(
            block.transmit_product_forward[product, modeled_year, dispatch_window, timestamp]
            for product in block.PRODUCTS
        ) + sum(
            block.transmit_product_reverse[product, modeled_year, dispatch_window, timestamp]
            for product in block.PRODUCTS
        ) <= (
            max(self.forward_rating_profile.data.at[timestamp], self.reverse_rating_profile.data.at[timestamp])
            * block.operational_capacity[modeled_year]
        )

    def _net_transmit_product(
        self,
        block: pyo.Block,
        product: str,
        modeled_year: pd.Timestamp,
        dispatch_window: pd.Timestamp,
        timestamp: pd.Timestamp,
    ):
        return (
            block.transmit_product_forward[product, modeled_year, dispatch_window, timestamp]
            - block.transmit_product_reverse[product, modeled_year, dispatch_window, timestamp]
        )

    def _hurdle_cost_forward(
        self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        return sum(
            block.transmit_product_forward[product, modeled_year, dispatch_window, timestamp]
            * self.products[product].hurdle_rate_forward_direction.data.at[modeled_year]
            for product in self.products.keys()
        )

    def _hurdle_cost_reverse(
        self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        return sum(
            block.transmit_product_reverse[product, modeled_year, dispatch_window, timestamp]
            * self.products[product].hurdle_rate_reverse_direction.data.at[modeled_year]
            for product in self.products.keys()
        )

    def _annual_total_operational_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        total_operational_cost = block.model().sum_timepoint_component_slice_to_annual(
            block.hurdle_cost_forward[modeled_year, :, :]
        ) + block.model().sum_timepoint_component_slice_to_annual(block.hurdle_cost_reverse[modeled_year, :, :])
        return total_operational_cost

    def _annual_gross_forward_flow_by_product(self, block: pyo.Block, product: str, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.transmit_product_forward[product, modeled_year, :, :]
        )

    def _annual_gross_forward_flow(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return sum(
            block.annual_gross_forward_flow_by_product[product, modeled_year] for product in self.products.keys()
        )

    def _annual_gross_reverse_flow_by_product(self, block: pyo.Block, product: str, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.transmit_product_reverse[product, modeled_year, :, :]
        )

    def _annual_gross_reverse_flow(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return sum(
            block.annual_gross_reverse_flow_by_product[product, modeled_year] for product in self.products.keys()
        )

    def _annual_net_forward_flow_by_product(self, block: pyo.Block, product: str, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(
            block.net_transmit_product[product, modeled_year, :, :]
        )

    def _annual_net_forward_flow(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return sum(block.annual_net_forward_flow_by_product[product, modeled_year] for product in self.products.keys())

    def _annual_forward_hurdle_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(block.hurdle_cost_forward[modeled_year, :, :])

    def _annual_reverse_hurdle_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(block.hurdle_cost_reverse[modeled_year, :, :])
