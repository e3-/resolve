from typing import Annotated
from typing import ClassVar
from typing import Optional
from typing import Tuple
from typing import Union

import numpy as np
import pandas as pd
import pyomo.environ as pyo
from pydantic import ConfigDict
from pydantic import Field

from new_modeling_toolkit.core import three_way_linkage
from new_modeling_toolkit.core.component import Component
from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.model import ConstraintOperator
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.core.temporal import timeseries as ts


class CustomConstraintRHS(Component):
    SAVE_PATH: ClassVar[str] = "custom_constraints/rhs"
    constraint_operator: ConstraintOperator = Field(description=("RHS {greater than, less than, equal to} sum(LHS)"))
    penalty: float = 50_000_000

    custom_constraints: Annotated[
        dict[Union[tuple, str], three_way_linkage.CustomConstraintLinkage],
        Metadata(linkage_order=1, default_exclude=True),
    ] = Field({}, description="Component variables to sum together as the lhs of the custom constraint")

    annual_target: ts.NumericTimeseries = Field(
        default_factory=ts.NumericTimeseries.zero,
        description="The right hand side annual target of the custom constraints as a float. Will be added to the hourly target if applicable.",
        default_freq="YS",
        up_method="ffill",
        down_method="mean",
        weather_year=False,
    )

    weather_year_hourly_target: ts.NumericTimeseries = Field(
        default_factory=ts.NumericTimeseries.zero,
        description="The right hand side hourly target of the custom constraints as a float. Will be added to the annual target if applicable.",
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        weather_year=True,
    )

    @property
    def is_hourly(self) -> bool:
        """
        Loop through all CustomConstraint linkage linked to the RHS target.
        If any of the constraint components are indexed hourly, return True, indicating that the constraint must be constructed hourly.
        Returns: bool

        """
        return any(getattr(obj, "is_hourly", False) for obj in self.custom_constraints.values())

    @property
    def is_annual(self) -> bool:
        """
        Loop through all CustomConstraint linkage linked to the RHS target.
        If all of the constraint components are indexed annually, return True indicating the constraint will only be constructed annually
        Returns: bool

        """

        return all(getattr(obj, "is_annual", False) for obj in self.custom_constraints.values())

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

        if self.is_hourly:
            pyomo_components.update(
                custom_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._custom_constraint_hourly,
                )
            )

        elif self.is_annual:
            pyomo_components.update(
                custom_constraint_slack_down=pyo.Var(
                    model.MODELED_YEARS, within=pyo.NonNegativeReals, doc="Constraint Slack Down"
                ),
                custom_constraint_slack_up=pyo.Var(
                    model.MODELED_YEARS, within=pyo.NonNegativeReals, doc="Constraint Slack Up"
                ),
            )
            pyomo_components.update(
                custom_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    rule=self._custom_constraint_annual,
                )
            )

        if construct_costs:
            if self.is_annual:
                pyomo_components.update(
                    annual_slack_up_cost=pyo.Expression(
                        model.MODELED_YEARS,
                        rule=self._annual_slack_up_cost,
                    ),
                    annual_slack_down_cost=pyo.Expression(
                        model.MODELED_YEARS,
                        rule=self._annual_slack_down_cost,
                    ),
                    annual_total_slack_operational_cost=pyo.Expression(
                        model.MODELED_YEARS,
                        rule=self._annual_total_slack_operational_cost,
                        doc="Annual Total Slack Operational Cost ($)",
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

        if self.is_hourly:
            self.formulation_block.hourly_custom_constraint_dual = pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._hourly_custom_constraint_dual,
                doc="Hourly Unweighted Dual Value ($/Unit)",
            )
        elif self.is_annual:
            self.formulation_block.annual_custom_constraint_dual = pyo.Expression(
                model.MODELED_YEARS,
                rule=self._annual_custom_constraint_dual,
                doc="Annual Unweighted Dual Value ($/Unit)",
            )

    def get_rhs_target(self, index: Tuple[pd.Timestamp]) -> float:
        """
        Return the custom constraint RHS target. All RHS have an annual target.
        If the constraint is indexed hourly as well, add the annual target to the hourly target.
        Args:
            index: [modeled_year] for annual only or [modeled_year, dispatch_window, timestamp] for hourly

        Returns: annual target at model year timestamp + hourly target at weather year hour timestamp (if applicable)

        """
        rhs_target = self.annual_target.data.at[index[0]]
        if self.is_hourly and self.weather_year_hourly_target is not None:
            # add hourly target if applicable
            rhs_target += self.weather_year_hourly_target.data.at[index[-1]]

        return rhs_target

    def _construct_custom_constraint(self, block, index: Tuple[pd.Timestamp]):
        """

        Args:
            block: formulation block of the CustomConstraintRHS component
            index: [modeled_year] for annual only or [modeled_year, dispatch_window, timestamp] for hourly

        Returns:

        """

        rhs = self.get_rhs_target(index)

        if rhs in [
            float("+inf"),
            float("-inf"),
        ]:
            return pyo.Constraint.Skip

        # lhs_sum keeps track of all things being summed in the left hand side
        lhs = 0

        # iterate through each variable and its index combinations to be included
        for cc_linkage in self.custom_constraints.values():
            lhs_multiplier = cc_linkage.lhs_instance.get_lhs_multiplier(index, self.is_hourly)

            # If index in variable index, add to LHS
            lhs += cc_linkage.pyomo_component[cc_linkage.return_valid_index(index)] * lhs_multiplier

        # If none of the components in the custom constraint were added to the LHS (e.g., all for the wrong model year)
        if isinstance(lhs, int):
            return pyo.Constraint.Skip

        if self.is_annual:
            return self.constraint_operator.operator(
                lhs - block.custom_constraint_slack_down[index] + block.custom_constraint_slack_up[index], rhs
            )
        elif self.is_hourly:
            return self.constraint_operator.operator(lhs, rhs)

    def _custom_constraint_annual(self, block, modeled_year: pd.Timestamp) -> pyo.Constraint:
        """
        Call custom constraint constructor function with annual index

        Args:
            block: formulation block of the CustomConstraintRHS component
            modeled_year: [modeled_year: pd.Timestamp] for annual only

        Returns: pyo.Constraint

        """

        index = (modeled_year,)

        return self._construct_custom_constraint(block, index)

    def _custom_constraint_hourly(
        self, block, modeled_year: pd.Timestamp, dispatch_window, timestamp: pd.Timestamp
    ) -> pyo.Constraint:
        """

        Call custom constraint constructor function with hourly index

        Args:
            block:
            modeled_year: model year: pd.Timestamp
            dispatch_window: weather_year dispatch window: pd.Timestamp
            timestamp: weather_year timestamp: pd.Timestamp

        Returns: pyo.Constraint

        """
        index = (modeled_year, dispatch_window, timestamp)

        return self._construct_custom_constraint(block, index)

    def _hourly_slack_up_cost(self, block, modeled_year, dispatch_window, timestamp):
        return self.penalty * block.custom_constraint_slack_up[modeled_year, dispatch_window, timestamp]

    def _annual_slack_up_cost(self, block, modeled_year):
        if self.is_hourly:
            model: ModelTemplate = block.model()
            return model.sum_timepoint_component_slice_to_annual(block.hourly_slack_up_cost[modeled_year, :, :])
        elif self.is_annual:
            return self.penalty * block.custom_constraint_slack_up[modeled_year]

    def _hourly_slack_down_cost(self, block, modeled_year, dispatch_window, timestamp):
        return self.penalty * block.custom_constraint_slack_down[modeled_year, dispatch_window, timestamp]

    def _annual_slack_down_cost(self, block, modeled_year):
        if self.is_hourly:
            model: ModelTemplate = block.model()
            return model.sum_timepoint_component_slice_to_annual(block.hourly_slack_down_cost[modeled_year, :, :])
        elif self.is_annual:
            return self.penalty * block.custom_constraint_slack_down[modeled_year]

    def _annual_total_slack_operational_cost(self, block, modeled_year):
        return block.annual_slack_up_cost[modeled_year] + block.annual_slack_down_cost[modeled_year]

    def _annual_total_operational_cost(self, block, modeled_year):
        return block.annual_total_slack_operational_cost[modeled_year]

    def _hourly_custom_constraint_dual(self, block, modeled_year, dispatch_window, timestamp):
        dual = block.custom_constraint[modeled_year, dispatch_window, timestamp].get_suffix_value(
            "dual", default=np.nan
        )

        model: ModelTemplate = block.model()
        annual_discount_factor = model.temporal_settings.modeled_year_discount_factors.data.at[modeled_year]
        num_days_in_modeled_year = model.num_days_per_modeled_year[modeled_year]
        dispatch_window_weight = model.temporal_settings.dispatch_window_weights.at[dispatch_window]
        timestamp_duration_hours = model.timestamp_durations_hours[dispatch_window, timestamp]

        return (
            dual / annual_discount_factor / num_days_in_modeled_year / dispatch_window_weight / timestamp_duration_hours
        )

    def _annual_custom_constraint_dual(self, block, modeled_year):
        dual = block.custom_constraint[modeled_year].get_suffix_value("dual", default=np.nan)
        model: ModelTemplate = block.model()
        annual_discount_factor = model.temporal_settings.modeled_year_discount_factors.data.at[modeled_year]

        return dual / annual_discount_factor


class CustomConstraintLHS(Component):
    """Note: stylistically, the team chose not to put any Pyomo blocks on linkages, so the workaround for
    custom constraints was to create a LHS component for the multipliers. In my opinion, this is confusing because
    making sure that `CustomConstraintRHS`, `CustomConstraintLHS`, and `CustomConstraintLinkage` are all correctly
    connected is challenging from a user experience standpoint."""
    SAVE_PATH: ClassVar[str] = "custom_constraints/lhs"
    # Override the protected namespaces to suppress warnings created by the `modeled_year_multiplier` Field, defined below
    model_config = ConfigDict(protected_namespaces=())

    custom_constraints: Annotated[
        dict[Union[tuple, str], three_way_linkage.CustomConstraintLinkage],
        Metadata(linkage_order=2, default_exclude=True),
    ] = {}

    additional_index: Optional[str] = Field(
        None, description=("Additional variable index before the timestamp. Ex: for policy constraints")
    )

    modeled_year_multiplier: ts.NumericTimeseries = Field(
        default_factory=ts.NumericTimeseries.one,
        description="The left hand side annual multiplier of the instance pyomo component as a float. Will be added to the hourly target if applicable.",
        default_freq="YS",
        up_method="ffill",
        down_method="mean",
        weather_year=False,
    )

    weather_year_hourly_multiplier: Optional[ts.NumericTimeseries] = Field(
        default_factory=ts.NumericTimeseries.one,
        description="The left hand side instance hourly multiplier of the instance pyomo component as a float. Will be multiplied with the annual multiplier if applicable.",
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        weather_year=True,
    )

    pyomo_component_name: str = Field(description="The pyomo component name of the linked component to constrain.")

    def get_lhs_multiplier(self, index: Tuple[pd.Timestamp], hourly: bool) -> float:
        """

        Args:
            index:
            hourly: bool, True if the RHS is hourly, include both annual and hourly multipliers

        Returns: annual LHS component multiplier * hourly LHS component multiplier (if applicable)

        """
        modeled_year_multiplier = self.modeled_year_multiplier.data.at[index[0]]
        if hourly and self.weather_year_hourly_multiplier is not None:
            weather_year_hourly_multiplier = self.weather_year_hourly_multiplier.data.at[index[-1]]
        else:
            weather_year_hourly_multiplier = 1

        return modeled_year_multiplier * weather_year_hourly_multiplier
