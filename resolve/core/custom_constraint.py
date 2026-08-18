from typing import Annotated
from typing import Any
from typing import ClassVar
from typing import Optional
from typing import Tuple
from typing import Union

import numpy as np
import pandas as pd
import pyomo.environ as pyo
from kit.core.custom_model import Metadata
from pydantic import ConfigDict
from pydantic import Field

from resolve.core import three_way_linkage
from resolve.core.component import Component
from resolve.core.component import LastUpdatedOrderedDict
from resolve.core.model import ConstraintOperator
from resolve.core.model import ModelTemplate
from resolve.core.temporal import timeseries as ts


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

    weather_year_daily_target: ts.NumericTimeseries = Field(
        default_factory=ts.NumericTimeseries.zero,
        description="The right hand side daily target of the custom constraints as a float. Will be added to the annual target if applicable.",
        default_freq="D",
        up_method="ffill",
        down_method="mean",
        weather_year=True,
    )

    weather_year_hourly_target: ts.NumericTimeseries = Field(
        default_factory=ts.NumericTimeseries.zero,
        description="The right hand side hourly target of the custom constraints as a float. Will be added to the annual target if applicable.",
        default_freq="h",
        up_method="ffill",
        down_method="mean",
        weather_year=True,
    )

    modeled_year_hourly_target: ts.NumericTimeseries = Field(
        default_factory=ts.NumericTimeseries.zero,
        description="The right hand side hourly target of the custom constraints as a float for modeled year. Hourly values for certain modeled year will be wrapped around each weather year.",
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        weather_year=False,
    )
    _hourly_target_by_modeled_year: dict[int, ts.NumericTimeseries] = {}

    @property
    def is_erm_hourly(self) -> bool:
        """
        Loop through all CustomConstraint linkage linked to the RHS target.
        If any of the constraint components are indexed ERM hourly (weather periods and weather timestamps), return True, indicating that the constraint must be constructed ERM hourly.
        Returns: bool

        """
        return any(getattr(obj, "is_erm_hourly", False) for obj in self.custom_constraints.values())

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

    @property
    def is_daily(self) -> bool:
        """Return whether the RHS should be built with daily indices.

        Returns:
            True if all linked custom constraint components are daily-indexed.
        """
        return all(getattr(obj, "is_daily", False) for obj in self.custom_constraints.values())

    def update_hourly_target_by_modeled_year(self, modeled_years: tuple[int, int], weather_years: tuple[int, int]):
        """Resample hourly modeled year target with simple extend years function"""
        if self.modeled_year_hourly_target.data.sum() != 0:
            self._hourly_target_by_modeled_year = self.modeled_year_hourly_target.modeled_year_hourly_ts_to_dict(
                modeled_years, weather_years
            )

    def revalidate(self) -> None:
        """Validate custom constraint linkages and index combinations.

        Raises:
            ValueError: If the RHS has no linked custom constraints or mixes daily with hourly indices.
            NotImplementedError: If the RHS mixes dispatch-window hourly and ERM-hourly indices.
        """
        super().revalidate()
        if self.custom_constraints == {}:
            raise ValueError(
                f"CustomConstraintRHS `{self.name}` must have at least one linked CustomConstraintLinkage."
            )
        if self.is_erm_hourly and self.is_hourly:
            raise NotImplementedError(
                f"CustomConstraintRHS `{self.name}` can only be linked to components hourly indexed by either weather "
                f"periods or dispatch windows, but not both."
            )
        if self.is_erm_hourly + self.is_hourly + self.is_daily > 1:
            raise ValueError(
                f"CustomConstraintRHS `{self.name}` cannot be implemented using both hourly and daily indices"
            )

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

        elif self.is_erm_hourly:
            pyomo_components.update(
                custom_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._custom_constraint_hourly,
                )
            )

        elif self.is_daily:
            pyomo_components.update(
                custom_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DAYS,
                    rule=self._custom_constraint_daily,
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

        # todo: add _erm_hourly_custom_constraint_dual?
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

        elif self.is_daily:
            self.formulation_block.daily_custom_constraint_dual = pyo.Expression(
                model.MODELED_YEARS,
                model.DAYS,
                rule=self._daily_custom_constraint_dual,
                doc="Daily Unweighted Dual Value ($/Unit)",
            )

    def get_rhs_target(self, index: Tuple[pd.Timestamp, ...]) -> float:
        """Return the custom constraint RHS target for an annual, hourly, or daily index.

        Args:
            index: Modeled year for annual constraints, modeled year plus dispatch window or weather period and
                timestamp for hourly constraints, or modeled year plus day for daily constraints.

        Returns:
            Annual target plus any applicable hourly or daily target adjustment.
        """
        modeled_year = index[0]
        rhs_target = self.annual_target.data.at[modeled_year]

        if self.is_hourly or self.is_erm_hourly:
            if self.weather_year_hourly_target is not None:
                # add hourly target if applicable
                timestamp = index[-1]
                rhs_target += self.weather_year_hourly_target.data.at[timestamp]

            if self._hourly_target_by_modeled_year:
                # add modeled year specific hourly target if applicable
                timestamp = index[-1]
                rhs_target += self._hourly_target_by_modeled_year[modeled_year.year].data.at[timestamp]

        if self.is_daily and self.weather_year_daily_target is not None:
            # add daily target if applicable
            day = index[-1]
            rhs_target += self.weather_year_daily_target.data.at[day]

        return rhs_target

    def _construct_custom_constraint(self, block: pyo.Block, index: Tuple[pd.Timestamp, ...]) -> Any:
        """Construct the custom constraint expression for a specific index.

        Args:
            block: Formulation block of the CustomConstraintRHS component.
            index: Modeled year for annual constraints, modeled year plus dispatch window or weather period and
                timestamp for hourly constraints, or modeled year plus day for daily constraints.

        Returns:
            A Pyomo constraint expression, or ``pyo.Constraint.Skip`` if the constraint should not be built.
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
            lhs_multiplier = cc_linkage.lhs_instance.get_lhs_multiplier(
                index, (self.is_hourly or self.is_erm_hourly), self.is_daily
            )

            # If index in pyomo_component index, add to LHS
            if cc_linkage.return_valid_index(index) in cc_linkage.pyomo_component.index_set():
                lhs += cc_linkage.pyomo_component[cc_linkage.return_valid_index(index)] * lhs_multiplier
            # If pyomo_component is not indexed, add to LHS (e.g., selected_capacity, integer_build Vars)
            elif cc_linkage.variable_index == [None]:
                lhs += cc_linkage.pyomo_component * lhs_multiplier
            # If pyomo_component has an index, but not the expected one, throw an error
            elif cc_linkage.return_valid_index(index) not in cc_linkage.pyomo_component.index_set():
                raise KeyError(
                    f"Custom Constraint pyomo component {cc_linkage.pyomo_component} does not have index {cc_linkage.return_valid_index(index)}"
                )

        # If none of the components in the custom constraint were added to the LHS (e.g., all for the wrong model year)
        if isinstance(lhs, int):
            return pyo.Constraint.Skip

        if self.is_annual:
            return self.constraint_operator.operator(
                lhs - block.custom_constraint_slack_down[index] + block.custom_constraint_slack_up[index], rhs
            )
        else:
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
        self,
        block,
        modeled_year: pd.Timestamp,
        dispatch_window_or_weather_period: pd.Timestamp,
        timestamp: pd.Timestamp,
    ) -> pyo.Constraint:
        """

        Call custom constraint constructor function with hourly index

        Args:
            block:
            modeled_year: model year: pd.Timestamp
            dispatch_window_or_weather_period: weather_year dispatch window or weather period: pd.Timestamp
            timestamp: weather_year timestamp: pd.Timestamp

        Returns: pyo.Constraint

        """
        index = (modeled_year, dispatch_window_or_weather_period, timestamp)

        return self._construct_custom_constraint(block, index)

    def _custom_constraint_daily(self, block: pyo.Block, modeled_year: pd.Timestamp, day: pd.Timestamp) -> Any:
        """Build the daily custom constraint rule for Pyomo.

        Args:
            block: Formulation block of the CustomConstraintRHS component.
            modeled_year: Modeled year for the constraint.
            day: Weather-year day for the daily constraint.

        Returns:
            A Pyomo constraint expression, or ``pyo.Constraint.Skip`` if the constraint should not be built.
        """

        index = (modeled_year, day)

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
        # Return None if constraint was not constructed for this index
        if (modeled_year, dispatch_window, timestamp) not in block.custom_constraint:
            return None

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
        # Return None if constraint was not constructed for this index
        if modeled_year not in block.custom_constraint:
            return None

        dual = block.custom_constraint[modeled_year].get_suffix_value("dual", default=np.nan)
        model: ModelTemplate = block.model()
        annual_discount_factor = model.temporal_settings.modeled_year_discount_factors.data.at[modeled_year]

        return dual / annual_discount_factor

    def _daily_custom_constraint_dual(
        self, block: pyo.Block, modeled_year: pd.Timestamp, day: pd.Timestamp
    ) -> Optional[float]:
        """Return the undiscounted daily custom constraint dual value.

        Args:
            block: Formulation block of the CustomConstraintRHS component.
            modeled_year: Modeled year for the dual expression.
            day: Weather-year day for the dual expression.

        Returns:
            Daily custom constraint dual value, or None if the constraint was skipped.
        """

        # Return None if constraint was not constructed for this index
        if (modeled_year, day) not in block.custom_constraint:
            return None

        dual = block.custom_constraint[modeled_year, day].get_suffix_value("dual", default=np.nan)

        model: ModelTemplate = block.model()
        annual_discount_factor = model.temporal_settings.modeled_year_discount_factors.data.at[modeled_year]
        num_days_in_modeled_year = model.num_days_per_modeled_year[modeled_year]

        day_weight = model.temporal_settings.dispatch_window_weights.at[day]

        return dual / annual_discount_factor / num_days_in_modeled_year / day_weight


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
        description="The left hand side annual multiplier of the instance  spyomo component as a float. Will be added to the hourly target if applicable.",
        default_freq="YS",
        up_method="ffill",
        down_method="mean",
        weather_year=False,
    )

    weather_year_daily_multiplier: Optional[ts.NumericTimeseries] = Field(
        default_factory=ts.NumericTimeseries.one,
        description="The left hand side instance daily multiplier of the instance pyomo component as a float. Will be multiplied with the annual multiplier if applicable.",
        default_freq="D",
        up_method="ffill",
        down_method="mean",
        weather_year=True,
    )

    weather_year_hourly_multiplier: Optional[ts.NumericTimeseries] = Field(
        default_factory=ts.NumericTimeseries.one,
        description="The left hand side instance hourly multiplier of the instance pyomo component as a float. Will be multiplied with the annual multiplier if applicable.",
        default_freq="h",
        up_method="ffill",
        down_method="mean",
        weather_year=True,
    )

    modeled_year_hourly_multiplier: Optional[ts.NumericTimeseries] = Field(
        default_factory=ts.NumericTimeseries.one,
        description="The left hand side hourly multiplier of the instance pyomo component for modeled year. Hourly values for certain modeled year will be wrapped around each weather year.",
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        weather_year=False,
    )
    _hourly_multiplier_by_modeled_year: dict[int, ts.NumericTimeseries] = {}

    pyomo_component_name: str = Field(description="The pyomo component name of the linked component to constrain.")

    def get_lhs_multiplier(self, index: Tuple[pd.Timestamp, ...], hourly: bool, daily: bool) -> float:
        """Return the LHS multiplier for the supplied custom constraint index.

        Args:
            index: Modeled year for annual constraints, modeled year plus dispatch window or weather period and
                timestamp for hourly constraints, or modeled year plus day for daily constraints.
            hourly: Whether to include weather-year and modeled-year hourly multipliers.
            daily: Whether to include the weather-year daily multiplier.

        Returns:
            Annual multiplier multiplied by any applicable hourly or daily multiplier.
        """
        modeled_year_multiplier = self.modeled_year_multiplier.data.at[index[0]]
        if hourly:
            if self.weather_year_hourly_multiplier is not None:
                weather_year_hourly_multiplier = self.weather_year_hourly_multiplier.data.at[index[-1]]
            else:
                weather_year_hourly_multiplier = 1.0
            if self._hourly_multiplier_by_modeled_year:
                modeled_year_hourly_multiplier = self._hourly_multiplier_by_modeled_year[index[0].year].data.at[
                    index[-1]
                ]
            else:
                modeled_year_hourly_multiplier = 1.0

            return modeled_year_multiplier * weather_year_hourly_multiplier * modeled_year_hourly_multiplier

        if daily:
            weather_year_daily_multiplier = 1.0
            if self.weather_year_daily_multiplier is not None:
                weather_year_daily_multiplier = self.weather_year_daily_multiplier.data.at[index[-1]]

            return modeled_year_multiplier * weather_year_daily_multiplier

        return modeled_year_multiplier

    def update_hourly_multiplier_by_modeled_year(self, modeled_years: tuple[int, int], weather_years: tuple[int, int]):
        """Resample hourly modeled year multiplier with simple extend years function"""
        if not (self.modeled_year_hourly_multiplier.data == 1).all():
            self._hourly_multiplier_by_modeled_year = (
                self.modeled_year_hourly_multiplier.modeled_year_hourly_ts_to_dict(modeled_years, weather_years)
            )
