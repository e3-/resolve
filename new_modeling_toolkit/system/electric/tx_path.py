# Should transmission just be a subclass of GenericResource? A lot of the attributes are overlapping, just with different names
from typing import Annotated
from typing import ClassVar
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pyomo.environ as pyo
from loguru import logger
from pydantic import Field

from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.system.asset import Asset
from new_modeling_toolkit.system.asset import AssetGroup

if TYPE_CHECKING:
    from new_modeling_toolkit.core.model import ModelTemplate


class TxPath(Asset):
    SAVE_PATH: ClassVar[str] = "tx_paths"
    ######################
    # Linkages #
    ######################
    zones: Annotated[dict[str, linkage.ZoneToTransmissionPath], Metadata(linkage_order="from")] = {}
    pollutants: dict[str, linkage.Linkage] = {}

    ##############
    # Attributes #
    ##############

    forward_rating_profile: Annotated[
        ts.FractionalTimeseries | None, Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Forward Rating")
    ] = Field(
        default_factory=ts.NumericTimeseries.one,
        description="Normalized fixed shape of TXPath's potential forward rating",
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
        title=f"Forward Rating Profile",
    )

    reverse_rating_profile: Annotated[
        ts.FractionalTimeseries | None, Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Reverse Rating")
    ] = Field(
        default_factory=ts.NumericTimeseries.one,
        description="Normalized fixed shape of TXPath's potential reverse rating",
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
        title=f"Reverse Rating Profile",
    )

    hurdle_rate_forward_direction: Annotated[
        ts.NumericTimeseries, Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Forward Hurdle")
    ] = Field(
        default_factory=ts.NumericTimeseries.zero,
        default_freq="YS",
        up_method="interpolate",
        down_method="mean",
        title=f"Forward Hurdle Rate ($/MWh)",
    )
    hurdle_rate_reverse_direction: Annotated[
        ts.NumericTimeseries, Metadata(category=FieldCategory.OPERATIONS, excel_short_title="Reverse Hurdle")
    ] = Field(
        default_factory=ts.NumericTimeseries.zero,
        default_freq="YS",
        up_method="interpolate",
        down_method="mean",
        title=f"Reverse Hurdle Rate ($/MWh)",
    )

    ###########
    # Methods #
    ###########
    # TODO (5/13): These properties only validate the # of linkages when called.
    #  Think whether we can validate # of linkages earlier (during `announce_linkage_to_components`)
    @property
    def from_zone(self):
        if self.zones:
            zones = [z for z in self.zones.values() if z.from_zone]
            if len(zones) > 1:
                raise ValueError(
                    f"Multiple zones ({zones}) are marked as being on the 'from' side of path '{self.name}'."
                )
            elif len(zones) == 0:
                raise ValueError("No zones assigned as 'from' zone of path '{self.name}'.")
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

    @property
    def annual_results_column_order(self):
        """This property defines the ordering of columns in the component's annual results summary out of Resolve.
        The name of the model field or formulation_block pyomo component can be used.
        """
        return [
            # Topology
            "zone_names_string",
            "from_zone",
            "to_zone",
            # Investment data
            # "vintage_parent_group",  # Can add this after TxPathGroup is created
            "max_forward_capacity",
            "max_reverse_capacity",
            "selected_capacity",
            "operational_capacity",
            "retired_capacity",
            "planned_capacity",
            "potential",
            # Operational data
            "annual_gross_forward_flow",
            "annual_gross_reverse_flow",
            "annual_net_forward_flow",
            # Operational costs
            "hurdle_rate_forward_direction",
            "hurdle_rate_reverse_direction",
            "annual_forward_hurdle_cost",
            "annual_reverse_hurdle_cost",
            "annual_forward_flow_value_to_zone",
            "annual_reverse_flow_value_to_zone",
            "annual_forward_flow_value_from_zone",
            "annual_reverse_flow_value_from_zone",
            "annual_total_operational_cost",
            # Investment costs
            "annual_capital_cost",
            "annual_fixed_om_cost",
            "annual_total_investment_cost",
            # Slacks
            "asset_potential_slack",
            "asset_potential_slack_cost",
            "annual_total_slack_investment_cost",
            "annual_total_slack_operational_cost",
            # Integer Build
            "integer_build",
            "integer_build_increment",
        ]

    def revalidate(self):
        if self.from_zone is None:
            raise ValueError(f"TXPath `{self.name}` has no `from_zone` assigned. Check your `linkages.csv` file.")
        if self.to_zone is None:
            raise ValueError(f"TXPath `{self.name}` has no `to_zone` assigned. Check your `linkages.csv` file.")

        if len(self.custom_constraints) > 0 and self.operational_group is not None:
            raise ValueError(
                f"`{self.__class__.__name__}` instance `{self.name}` is assigned to both an operational group and a "
                f"custom constraint. Custom constraints cannot be enforced correctly if the Asset is linked to an "
                f"operational group. Either remove the custom constraint linkage or apply the custom constraint to the "
                f"entire operational group."
            )

        if self.potential is None:
            self.potential = np.inf

        if self.integer_build_increment:
            if self.integer_build_increment > self.potential:
                raise ValueError(f"{self.name}: potential must be greater than integer_build_increment.")
            if ~np.isinf(self.potential) & (self.potential % self.integer_build_increment != 0):
                potential_modeled = (
                    np.floor(self.potential / self.integer_build_increment) * self.integer_build_increment
                )
                logger.warning(
                    f"{self.name}: potential not divisible by integer_build_increment. Input potential {self.potential} cannot be reached; maximum potential due to integer_build_limit is {potential_modeled})"
                )

        for year in self.planned_capacity.data.index:
            if self.planned_capacity.data.loc[year] > self.potential:
                raise ValueError(
                    f"`{self.__class__.__name__}` instance `{self.name}` has a potential of {self.potential}, "
                    f"which is less than the planned capacity of {self.planned_capacity.data.loc[year]} in {year.year}."
                )

    def _construct_operational_rules(self, model: "ModelTemplate", construct_costs: bool):
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

        #############
        # Variables #
        #############

        """Amount of power transmitted from "from zone" to "to zone" in MW in each modeled timepoint (non-negative)"""
        pyomo_components.update(
            transmit_power_forward=pyo.Var(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                units=pyo.units.MW,
                within=pyo.NonNegativeReals,
                doc="Transmit Power Forward (MW)",
            )
        )

        """Amount of power transmitted from "to zone" to "from zone" in MW in each modeled timepoint (non-negative)"""
        pyomo_components.update(
            transmit_power_reverse=pyo.Var(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                units=pyo.units.MW,
                within=pyo.NonNegativeReals,
                doc="Transmit Power Reverse (MW)",
            )
        )

        ###############
        # Expressions #
        ###############
        """Amount of power transmitted in MW in each modeled timepoint (can be positive or negative)"""
        pyomo_components.update(
            net_transmit_power=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._net_transmit_power,
                doc="Net Transmit Power (MW)",
            )
        )

        if construct_costs:
            """Hurdle costs of transmission flow in the forward direction"""
            pyomo_components.update(
                tx_hurdle_cost_forward=pyo.Expression(
                    model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, rule=self._tx_hurdle_cost_forward
                )
            )

            """Hurdle costs of transmission flow in the reverse direction"""
            pyomo_components.update(
                tx_hurdle_cost_reverse=pyo.Expression(
                    model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, rule=self._tx_hurdle_cost_reverse
                )
            )

            # Overwrite the annual total operational cost inherited from Asset
            pyomo_components.update(
                annual_total_operational_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_operational_cost,
                    doc="Annual Total Operational Cost ($)",
                )
            )

        ###############
        # Constraints #
        ###############
        """Transmission flows must obey flow limits on each line."""
        pyomo_components.update(
            transmission_max_flow_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._transmission_max_flow_constraint,
            )
        )

        """Transmission flows must obey flow limits on each line."""
        pyomo_components.update(
            transmission_min_flow_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._transmission_min_flow_constraint,
            )
        )

        pyomo_components.update(
            transmission_mileage_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._transmission_mileage_constraint,
            )
        )

        return pyomo_components

    #####################
    # Output Expressions#
    #####################

    def _construct_output_expressions(self, construct_costs: bool):

        to_zone_hourly_energy_price_flag = hasattr(
            self.to_zone.instance_from.formulation_block, "hourly_energy_prices_weighted"
        )
        from_zone_hourly_energy_price_flag = hasattr(
            self.from_zone.instance_from.formulation_block, "hourly_energy_prices_weighted"
        )

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

        self.formulation_block.max_forward_capacity = pyo.Expression(
            self.formulation_block.model().MODELED_YEARS,
            rule=self._max_forward_capacity,
            doc="Max Forward Capacity (MW)",
        )

        self.formulation_block.max_reverse_capacity = pyo.Expression(
            self.formulation_block.model().MODELED_YEARS,
            rule=self._max_reverse_capacity,
            doc="Max Reverse Capacity (MW)",
        )

        if self.has_operational_rules:
            self.formulation_block.annual_gross_forward_flow = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_gross_forward_flow,
                doc="Gross Forward Flow (MWh)",
            )

            self.formulation_block.annual_gross_reverse_flow = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_gross_reverse_flow,
                doc="Gross Reverse Flow (MWh)",
            )

            self.formulation_block.annual_net_forward_flow = pyo.Expression(
                self.formulation_block.model().MODELED_YEARS,
                rule=self._annual_net_forward_flow,
                doc="Net Forward Flow (MWh)",
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

            if to_zone_hourly_energy_price_flag:
                self.formulation_block.annual_forward_flow_value_to_zone = pyo.Expression(
                    self.formulation_block.model().MODELED_YEARS,
                    rule=self._annual_forward_flow_value_to_zone,
                    doc="Forward Flow Value (To Zone) ($)",
                )

                self.formulation_block.annual_reverse_flow_value_to_zone = pyo.Expression(
                    self.formulation_block.model().MODELED_YEARS,
                    rule=self._annual_reverse_flow_value_to_zone,
                    doc="Reverse Flow Value (To Zone) ($)",
                )

            if from_zone_hourly_energy_price_flag:
                self.formulation_block.annual_forward_flow_value_from_zone = pyo.Expression(
                    self.formulation_block.model().MODELED_YEARS,
                    rule=self._annual_forward_flow_value_from_zone,
                    doc="Forward Flow Value (From Zone) ($)",
                )

                self.formulation_block.annual_reverse_flow_value_from_zone = pyo.Expression(
                    self.formulation_block.model().MODELED_YEARS,
                    rule=self._annual_reverse_flow_value_from_zone,
                    doc="Reverse Flow Value (From Zone) ($)",
                )

    #########
    # Rules #
    #########

    def _net_transmit_power(self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp):
        """Amount of power transmitted in MW in each timepoint from zone to zone (can be positive or negative)"""
        return (
            block.transmit_power_forward[modeled_year, dispatch_window, timestamp]
            - block.transmit_power_reverse[modeled_year, dispatch_window, timestamp]
        )

    def _tx_hurdle_cost_forward(self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp):
        """Returns hurdle costs in the forward direction"""
        return (
            block.transmit_power_forward[modeled_year, dispatch_window, timestamp]
            * self.hurdle_rate_forward_direction.data.at[modeled_year]
        )

    def _tx_hurdle_cost_reverse(self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp):
        """Returns hurdle costs in the reverse direction"""
        return (
            block.transmit_power_reverse[modeled_year, dispatch_window, timestamp]
            * self.hurdle_rate_reverse_direction.data.at[modeled_year]
        )

    def _transmission_max_flow_constraint(
        self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp
    ):
        """Transmission flows must obey flow limits on each line."""
        return block.transmit_power_forward[modeled_year, dispatch_window, timestamp] <= (
            block.operational_capacity[modeled_year] * self.forward_rating_profile.data.at[timestamp]
        )

    def _transmission_min_flow_constraint(
        self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp
    ):
        """Transmission flows must obey flow limits on each line."""
        return block.transmit_power_reverse[modeled_year, dispatch_window, timestamp] <= (
            block.operational_capacity[modeled_year] * self.reverse_rating_profile.data.at[timestamp]
        )

    def _transmission_mileage_constraint(
        self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window, timestamp
    ):
        return (
            block.transmit_power_forward[modeled_year, dispatch_window, timestamp]
            + block.transmit_power_reverse[modeled_year, dispatch_window, timestamp]
        ) <= (
            max(self.forward_rating_profile.data.at[timestamp], self.reverse_rating_profile.data.at[timestamp])
            * block.operational_capacity[modeled_year]
        )

    def _annual_total_operational_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """The total annual operational costs of the TxPath. This term is not discounted (i.e. it is not
        multiplied by the discount factor for the relevant model year)."""
        total_operational_cost = block.model().sum_timepoint_component_slice_to_annual(
            block.tx_hurdle_cost_forward[modeled_year, :, :]
        ) + block.model().sum_timepoint_component_slice_to_annual(block.tx_hurdle_cost_reverse[modeled_year, :, :])
        return total_operational_cost

    def _max_forward_capacity(self, block: pyo.Block, modeled_year: pd.Timestamp):
        max_forward_rating = self.forward_rating_profile.data.max()
        return max_forward_rating * block.operational_capacity[modeled_year]

    def _max_reverse_capacity(self, block: pyo.Block, modeled_year: pd.Timestamp):
        max_reverse_rating = self.reverse_rating_profile.data.max()
        return max_reverse_rating * block.operational_capacity[modeled_year]

    def _annual_gross_forward_flow(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(block.transmit_power_forward[modeled_year, :, :])

    def _annual_gross_reverse_flow(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(block.transmit_power_reverse[modeled_year, :, :])

    def _annual_net_forward_flow(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.annual_gross_forward_flow[modeled_year] - block.annual_gross_reverse_flow[modeled_year]

    def _annual_forward_hurdle_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(block.tx_hurdle_cost_forward[modeled_year, :, :])

    def _annual_reverse_hurdle_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        return block.model().sum_timepoint_component_slice_to_annual(block.tx_hurdle_cost_reverse[modeled_year, :, :])

    def _annual_forward_flow_value_to_zone(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Weighted energy prices are used in order to sum to correct annual flow value"""
        to_zone_energy_prices = self.to_zone.instance_from.formulation_block.hourly_energy_prices_weighted
        forward_flows = block.transmit_power_forward
        return sum(
            to_zone_energy_prices[modeled_year, dispatch_window, timestamp]
            * forward_flows[modeled_year, dispatch_window, timestamp]
            for dispatch_window, timestamp in block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS
        )

    def _annual_reverse_flow_value_to_zone(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Weighted energy prices are used in order to sum to correct annual flow value"""
        to_zone_energy_prices = self.to_zone.instance_from.formulation_block.hourly_energy_prices_weighted
        reverse_flows = block.transmit_power_reverse
        return sum(
            to_zone_energy_prices[modeled_year, dispatch_window, timestamp]
            * reverse_flows[modeled_year, dispatch_window, timestamp]
            for dispatch_window, timestamp in block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS
        )

    def _annual_forward_flow_value_from_zone(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Weighted energy prices are used in order to sum to correct annual flow value"""
        from_zone_energy_prices = self.from_zone.instance_from.formulation_block.hourly_energy_prices_weighted
        forward_flows = block.transmit_power_forward
        return sum(
            from_zone_energy_prices[modeled_year, dispatch_window, timestamp]
            * forward_flows[modeled_year, dispatch_window, timestamp]
            for dispatch_window, timestamp in block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS
        )

    def _annual_reverse_flow_value_from_zone(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Weighted energy prices are used in order to sum to correct annual flow value"""
        from_zone_energy_prices = self.from_zone.instance_from.formulation_block.hourly_energy_prices_weighted
        reverse_flows = block.transmit_power_reverse
        return sum(
            from_zone_energy_prices[modeled_year, dispatch_window, timestamp]
            * reverse_flows[modeled_year, dispatch_window, timestamp]
            for dispatch_window, timestamp in block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS
        )


class TxPathGroup(AssetGroup, TxPath):
    SAVE_PATH: ClassVar[str] = "tx_paths/groups"
    _NAME_PREFIX: ClassVar[str] = "tx_path_group"
    _GROUPING_CLASS = TxPath

    # Override Asset-defined zones dictionary
    zones: Annotated[dict[str, linkage.ZoneToTransmissionPath], Metadata(linkage_order="from")] = {}

    def revalidate(self):
        super().revalidate()

        if self.from_zone is None:
            raise ValueError(f"TxPathGroup `{self.name}` has no `from_zone` assigned. Check your `linkages.csv` file.")
        if self.to_zone is None:
            raise ValueError(f"TxPathGroup `{self.name}` has no `to_zone` assigned. Check your `linkages.csv` file.")
