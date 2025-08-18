from typing import ClassVar

import numpy as np
import pandas as pd
import pyomo.environ as pyo
from loguru import logger
from pydantic import Field
from typing_extensions import Annotated

from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.custom_model import ModelType
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.temporal.settings import DispatchWindowEdgeEffects
from new_modeling_toolkit.system.asset import AnyOperationalGroup
from new_modeling_toolkit.system.electric.resources.generic import _PYOMO_BUDGET_TOLERANCE
from new_modeling_toolkit.system.electric.resources.generic import GenericResourceGroup
from new_modeling_toolkit.system.electric.resources.unit_commitment import UnitCommitmentMethod
from new_modeling_toolkit.system.electric.resources.unit_commitment import UnitCommitmentResource


class ShedDrResource(UnitCommitmentResource):
    SAVE_PATH: ClassVar[str] = "resources/shed"

    max_call_duration: Annotated[int | None, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        None, description="Maximum duration of a single shed demand response event call [hrs].", gt=0
    )

    max_annual_calls: Annotated[ts.NumericTimeseries | None, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        None,
        description="Annual number of allowable calls per individual unit for a shed DR resource.",
        default_freq="YS",
        up_method="ffill",
        down_method="mean",
        weather_year=False,
    )

    max_monthly_calls: Annotated[ts.NumericTimeseries | None, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        None,
        description="Monthly number of allowable calls per individual unit for a shed DR resource.",
        default_freq="MS",
        up_method="ffill",
        down_method="mean",
        weather_year=False,
    )

    max_daily_calls: Annotated[ts.NumericTimeseries | None, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        None,
        description="Daily number of allowable calls per individual unit for a shed DR resource.",
        default_freq="D",
        up_method="ffill",
        down_method="mean",
        weather_year=False,
    )

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_investment_rules(model=model, construct_costs=construct_costs)
        if self.erm_policies:
            if self.unit_commitment_mode == UnitCommitmentMethod.INTEGER:
                logger.warning(
                    f"Integer unit commitment with an ERM policy may result in intractable model size. "
                    f"Consider linear unit commitment."
                )
            pyomo_components.update(
                erm_power_output=pyo.Var(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    within=pyo.NonNegativeReals,
                    doc="ERM Power Output (MW)",
                    initialize=0,
                ),
                erm_committed_units=pyo.Var(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    within=pyo.NonNegativeReals,
                    doc="ERM Committed Units",
                    initialize=0,
                ),
                erm_committed_capacity=pyo.Expression(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_committed_capacity,
                    doc="ERM Committed Capacity (MW)",
                ),
                erm_power_output_max_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_power_output_max_constraint,
                ),
                erm_start_units=pyo.Var(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    within=self.unit_commitment_mode.var_type,
                    doc="ERM Start Units",
                    initialize=0,
                ),
                erm_shutdown_units=pyo.Var(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    within=self.unit_commitment_mode.var_type,
                    doc="ERM Shutdown Units",
                    initialize=0,
                ),
                erm_committed_units_ub_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_committed_units_ub_constraint,
                ),
                erm_start_units_ub_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_start_units_ub_constraint,
                ),
                erm_shutdown_units_ub_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_shutdown_units_ub_constraint,
                ),
                erm_commitment_tracking_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_commitment_tracking_constraint,
                ),
            )
            if getattr(self, "energy_budget_annual", None) is not None:
                pyomo_components.update(
                    erm_annual_energy_budget_MWh=pyo.Expression(
                        model.MODELED_YEARS,
                        model.SELECT_WEATHER_YEARS,
                        rule=self._erm_energy_budget_annual_MWh,
                    ),
                    erm_annual_energy_budget_constraint=pyo.Constraint(
                        model.MODELED_YEARS,
                        model.SELECT_WEATHER_YEARS,
                        rule=self._erm_annual_energy_budget_constraint,
                    ),
                )
            if getattr(self, "energy_budget_daily", None) is not None:
                pyomo_components.update(
                    erm_daily_energy_budget_MWh=pyo.Expression(
                        model.MODELED_YEARS,
                        model.WEATHER_PERIODS,
                        rule=self._erm_energy_budget_daily_MWh,
                    ),
                    erm_daily_energy_budget_constraint=pyo.Constraint(
                        model.MODELED_YEARS,
                        model.WEATHER_PERIODS,
                        rule=self._erm_daily_energy_budget_constraint,
                    ),
                )
            if getattr(self, "max_daily_calls", None) is not None:
                pyomo_components.update(
                    erm_daily_call_limit_constraint=pyo.Constraint(
                        model.MODELED_YEARS,
                        model.WEATHER_PERIODS,
                        rule=self._erm_daily_call_limit_constraint,
                    ),
                )
            if getattr(self, "max_call_duration") is not None:
                pyomo_components.update(
                    erm_max_dr_call_duration_constraint=pyo.Constraint(
                        model.MODELED_YEARS,
                        model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                        rule=self._erm_max_dr_call_duration_constraint,
                    ),
                )

            if construct_costs:
                pyomo_components.update(
                    erm_dispatch_cost_per_MWh=pyo.Param(
                        within=pyo.Reals, initialize=0.01
                    ),  # shed DR dispatch is more costly than storage
                    erm_dispatch_cost=pyo.Expression(
                        model.MODELED_YEARS,
                        model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                        rule=self._erm_dispatch_cost,
                        doc="ERM Shed DR Dispatch Cost ($)",
                    ),
                    erm_annual_dispatch_cost=pyo.Expression(
                        model.MODELED_YEARS,
                        rule=self._erm_annual_dispatch_cost,
                        doc="ERM Annual Shed DR Dispatch Cost ($)",
                    ),
                )

        return pyomo_components

    def _construct_operational_rules(
        self, model: pyo.ConcreteModel, construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

        if self.max_annual_calls is not None:
            pyomo_components.update(
                annual_dr_call_limit_constraint=pyo.Constraint(
                    model.MODELED_YEARS, rule=self._annual_dr_call_limit_constraint
                ),
            )

        if self.max_monthly_calls is not None:
            if model.TYPE == ModelType.RESOLVE:
                logger.warning("Monthly energy budgets are not supported in RESOLVE and will be ignored.")
            else:
                # TODO (2024-06-18): Create a version of a monthly dispatch window weighting to allow for monthly DR call limits
                pyomo_components.update(
                    monthly_dr_call_limit_constraint=pyo.Constraint(
                        model.MODELED_YEARS, model.MONTHS, rule=self._monthly_dr_call_limit_constraint
                    ),
                )

        if self.max_daily_calls is not None:
            pyomo_components.update(
                daily_dr_call_limit_constraint=pyo.Constraint(
                    model.MODELED_YEARS, model.DAYS, rule=self._daily_dr_call_limit_constraint
                ),
            )

        if self.max_call_duration is not None:
            pyomo_components.update(
                max_dr_call_duration_intra_period_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._max_dr_call_duration_intra_period_constraint,
                ),
            )
            if (
                model.dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
                and self.allow_inter_period_sharing
            ):
                pyomo_components.update(
                    max_dr_call_duration_inter_period_constraint=pyo.Constraint(
                        model.MODELED_YEARS,
                        model.CHRONO_PERIODS,
                        pyo.RangeSet(0, self.max_call_duration - 1),  # RangeSet is inclusive
                        rule=self._max_dr_call_duration_inter_period_constraint,
                    )
                )

        return pyomo_components

    ###########
    ## Rules ##
    ###########
    def _annual_dr_call_limit_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Max # of call per year."""
        constraint = block.model().sum_timepoint_component_slice_to_annual(
            block.start_units[modeled_year, :, :]
        ) <= self.max_annual_calls.data.at[f"01-01-{modeled_year.year}"] * self._annual_num_units(modeled_year)

        return constraint

    # TODO (2024-06-18): Create a version of a monthly dispatch window weighting to allow for monthly DR call limits
    def _monthly_dr_call_limit_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp, month: pd.Timestamp):
        """Max number of calls per month"""
        constraint = sum(
            block.start_units[modeled_year, dispatch_period, timestamp]
            for dispatch_period, timestamp in block.model().MONTH_TO_TIMESTAMPS_MAPPING[month]
        ) <= self.max_monthly_calls.data.at[f"{month.month}-01-{modeled_year.year}"] * self._annual_num_units(
            modeled_year
        )
        return constraint

    def _daily_dr_call_limit_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp, day: pd.Timestamp):
        """Max # of calls per day"""
        constraint = sum(
            block.start_units[modeled_year, dispatch_period, timestamp]
            for dispatch_period, timestamp in block.model().DAY_TO_TIMESTAMPS_MAPPING[day]
        ) <= self.max_daily_calls.data.at[f"{day.month}-{day.day}-{modeled_year.year}"] * self._annual_num_units(
            modeled_year
        )

        return constraint

    def _max_dr_call_duration_intra_period_constraint(
        self, block: pyo.Block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Constrain maximum up time (power output) for unit commitment resources.
        I.e., length of one DR call in terms of hours (all on same day).
        """

        if (
            block.model().dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
            and self.allow_inter_period_sharing
        ) and (
            timestamp + pd.Timedelta(hours=self.max_call_duration)
            > self.formulation_block.model().last_timepoint_in_dispatch_window[dispatch_window]
        ):
            return pyo.Constraint.Skip
        else:
            hour_offsets = range(0, self.max_call_duration)
            return block.committed_units[modeled_year, dispatch_window, timestamp] <= sum(
                block.start_units[
                    modeled_year,
                    block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS.prevw((dispatch_window, timestamp), step=t),
                ]
                for t in hour_offsets
            )

    def _max_dr_call_duration_inter_period_constraint(
        self, block: pyo.Block, modeled_year: pd.Timestamp, chrono_period: pd.Timestamp, max_call_duration_offset: int
    ):
        """
        Constrain maximum up time (power output) for shed DR resources.
        I.e., length of one DR call in terms of hours (across different days with inter-period sharing).
        """
        (
            chrono_period_1_index,
            chrono_period_2_index,
        ) = self.formulation_block.model().return_timepoints_connecting_chrono_periods(modeled_year, chrono_period)
        _, dispatch_window, last_timestamp_chrono_period = chrono_period_1_index
        _, next_dispatch_window, first_timestamp_next_chrono_period = chrono_period_2_index

        return self.formulation_block.committed_units[
            modeled_year,
            block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS.nextw(
                (next_dispatch_window, first_timestamp_next_chrono_period), max_call_duration_offset
            ),
        ] <= (
            sum(
                self.formulation_block.start_units[
                    modeled_year,
                    dispatch_window,
                    self.formulation_block.model()
                    .TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window]
                    .prevw(last_timestamp_chrono_period, t),
                ]
                for t in range(0, self.max_call_duration - max_call_duration_offset - 1)
            )
            + sum(
                self.formulation_block.start_units[
                    modeled_year,
                    next_dispatch_window,
                    self.formulation_block.model()
                    .TIMESTAMPS_IN_DISPATCH_WINDOWS[next_dispatch_window]
                    .nextw(first_timestamp_next_chrono_period, t),
                ]
                for t in range(0, max_call_duration_offset + 1)
            )
        )

    def _erm_power_output_max_constraint(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        return (
            block.erm_power_output[modeled_year, weather_period, weather_timestamp]
            <= block.erm_committed_capacity[modeled_year, weather_period, weather_timestamp]
            * self.pmax_profile.at[weather_timestamp]
        )

    def _erm_energy_budget_annual_MWh(self, block: pyo.Block, modeled_year: pd.Timestamp, weather_year: pd.Timestamp):
        """Fractional annual energy budget scaled to model year's capacity, giving budget in MWh"""
        return (
            block.operational_capacity[modeled_year]
            * self.energy_budget_annual.data.at[weather_year]
            * 24
            * self.energy_budget_annual.days_in_year.at[weather_year]
        )

    def _erm_annual_energy_budget_constraint(
        self, block: pyo.Block, modeled_year: pd.Timestamp, weather_year: pd.Timestamp
    ):
        """Frequently Shed DR resources have a budget that they can't exceed (since they "produce" by turning off load/demand).
        This constraint models that restriction."""
        if self.energy_budget_annual is None or np.isinf(self.energy_budget_annual.data.at[weather_year]):
            constraint = pyo.Constraint.Skip
        else:
            constraint = (
                block.model().sum_weather_timestamp_component_slice_to_annual(
                    block.erm_power_output[modeled_year, :, :]
                )
                <= block.erm_annual_energy_budget_MWh[modeled_year, weather_year] + _PYOMO_BUDGET_TOLERANCE
            )

        return constraint

    def _erm_energy_budget_daily_MWh(self, block: pyo.Block, modeled_year: pd.Timestamp, weather_period: pd.Timestamp):
        """Fractional daily energy budget scaled to model year's capacity, giving budget in MWh"""
        # Assumes weather period is one day
        return block.operational_capacity[modeled_year] * self.energy_budget_daily.data.at[weather_period] * 24

    def _erm_daily_energy_budget_constraint(self, block, modeled_year: pd.Timestamp, weather_period: pd.Timestamp):
        """The daily power output of the Resource must not exceed its specified daily budget. Note: a
        tolerance of 1 unit is added to the budget to ensure that floating point errors do not create an
        infeasible model."""
        if self.energy_budget_daily is None or np.isinf(self.energy_budget_daily.data.at[weather_period]):
            constraint = pyo.Constraint.Skip
        else:
            constraint = (
                sum(
                    block.erm_power_output[modeled_year, weather_period, weather_timestamp]
                    for weather_timestamp in block.model().WEATHER_TIMESTAMPS_IN_WEATHER_PERIODS[weather_period]
                )
                <= block.erm_daily_energy_budget_MWh[modeled_year, weather_period] + _PYOMO_BUDGET_TOLERANCE
            )

        return constraint

    def _erm_daily_call_limit_constraint(
        self, block: pyo.Block, modeled_year: pd.Timestamp, weather_period: pd.Timestamp
    ):
        """Daily DR call limits should be respected under ERM dispatch. Assumes weather period is a single day"""
        # Skip on February 29 because 2/29/modeled_year might not exist
        if weather_period.month == 2 and weather_period.day == 29:
            return pyo.Constraint.Skip
        constraint = sum(
            block.erm_start_units[modeled_year, weather_period, weather_timestamp]
            for weather_timestamp in block.model().WEATHER_TIMESTAMPS_IN_WEATHER_PERIODS[weather_period]
        ) <= self.max_daily_calls.data.at[
            f"{weather_period.month}-{weather_period.day}-{modeled_year.year}"
        ] * self._annual_num_units(
            modeled_year
        )

        return constraint

    def _erm_max_dr_call_duration_constraint(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        """Max DR call duration constraint should be honored in ERM dispatch"""
        hour_offsets = range(0, self.max_call_duration)
        return block.erm_committed_units[modeled_year, weather_period, weather_timestamp] <= sum(
            block.erm_start_units[
                modeled_year,
                block.model().WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS.prevw((weather_period, weather_timestamp), step=t),
            ]
            for t in hour_offsets
        )

    def _erm_commitment_tracking_constraint(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        """
        Track unit commitment status.
        Committed units[t] = committed_units[t-1] + start_units[t] - shutdown_units[t]
        """
        next_timestamp = block.model().WEATHER_TIMESTAMPS_IN_WEATHER_PERIODS[weather_period].nextw(weather_timestamp)
        return (
            block.erm_committed_units[modeled_year, weather_period, next_timestamp]
            == block.erm_committed_units[modeled_year, weather_period, weather_timestamp]
            + block.erm_start_units[modeled_year, weather_period, next_timestamp]
            - block.erm_shutdown_units[modeled_year, weather_period, next_timestamp]
        )

    def _erm_dispatch_cost(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        dispatch_cost = (
            block.erm_dispatch_cost_per_MWh * block.erm_power_output[modeled_year, weather_period, weather_timestamp]
        )
        # Add a cost for start units so that model does not set start and shutdown units to the same non-zero value
        dispatch_cost += (
            block.erm_dispatch_cost_per_MWh * block.erm_start_units[modeled_year, weather_period, weather_timestamp]
        )
        # Add a cost for committed units so resource shuts down when it's not needed
        dispatch_cost += (
            block.erm_dispatch_cost_per_MWh * block.erm_committed_units[modeled_year, weather_period, weather_timestamp]
        )
        return dispatch_cost

    def _erm_annual_dispatch_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        annual_dispatch_cost = block.model().sum_weather_timestamp_component_slice_to_annual(
            block.erm_dispatch_cost[modeled_year, :, :]
        )
        return annual_dispatch_cost

    def _erm_committed_capacity(
        self,
        block: pyo.Block,
        modeled_year: pd.Timestamp,
        weather_period: pd.Timestamp,
        weather_timestamp: pd.Timestamp,
    ):
        erm_committed_capacity = (
            block.erm_committed_units[modeled_year, weather_period, weather_timestamp] * self.unit_size
        )
        return erm_committed_capacity

    def _erm_committed_units_ub_constraint(
        self, block, modeled_year: pd.Timestamp, weather_period: pd.Timestamp, weather_timestamp: pd.Timestamp
    ):
        """
        Calculate the maximum number of units that can be committed based on operational capacity in model year.
        """
        return block.erm_committed_units[modeled_year, weather_period, weather_timestamp] <= self._annual_num_units(
            modeled_year
        )

    def _erm_start_units_ub_constraint(
        self, block, modeled_year: pd.Timestamp, weather_period: pd.Timestamp, weather_timestamp: pd.Timestamp
    ):
        """Calculate the maximum number of units that can be started based on operational capacity in model year."""
        return block.erm_start_units[modeled_year, weather_period, weather_timestamp] <= self._annual_num_units(
            modeled_year
        )

    def _erm_shutdown_units_ub_constraint(
        self, block, modeled_year: pd.Timestamp, weather_period: pd.Timestamp, weather_timestamp: pd.Timestamp
    ):
        """Calculate the maximum number of units that can be shutdown based on operational capacity in model year."""
        return block.erm_shutdown_units[modeled_year, weather_period, weather_timestamp] <= self._annual_num_units(
            modeled_year
        )


class ShedDrResourceGroup(GenericResourceGroup, ShedDrResource):
    SAVE_PATH: ClassVar[str] = "resources/shed/groups"
    _NAME_PREFIX: ClassVar[str] = "shed_dr_resource_group"
    _GROUPING_CLASS = ShedDrResource

    # TODO (skramer): Figure out how to determine operational equality for unit commitment resources when selected
    #  builds can result in differing number of units
    def construct_operational_groups(cls, assets: list[ShedDrResource] = False) -> dict[str, AnyOperationalGroup]:
        raise NotImplementedError("Operational grouping not defined for unit commitment resources")

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_investment_rules(model=model, construct_costs=construct_costs)

        # ERM policy investment rules need to be re-defined because method resolution order dictates that super() will
        # reference _construct_investment_rules() on GenericResourceGroup
        if self.erm_policies:
            if self.unit_commitment_mode == UnitCommitmentMethod.INTEGER:
                logger.warning(
                    f"Integer unit commitment with an ERM policy may result in intractable model size. "
                    f"Consider linear unit commitment."
                )
            pyomo_components.update(
                erm_power_output=pyo.Var(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    within=pyo.NonNegativeReals,
                    doc="ERM Power Output (MW)",
                    initialize=0,
                ),
                erm_committed_units=pyo.Var(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    within=pyo.NonNegativeReals,
                    doc="ERM Committed Units",
                    initialize=0,
                ),
                erm_committed_capacity=pyo.Expression(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_committed_capacity,
                    doc="ERM Committed Capacity (MW)",
                ),
                erm_power_output_max_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_power_output_max_constraint,
                ),
                erm_start_units=pyo.Var(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    within=self.unit_commitment_mode.var_type,
                    doc="ERM Start Units",
                    initialize=0,
                ),
                erm_shutdown_units=pyo.Var(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    within=self.unit_commitment_mode.var_type,
                    doc="ERM Shutdown Units",
                    initialize=0,
                ),
                erm_committed_units_ub_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_committed_units_ub_constraint,
                ),
                erm_start_units_ub_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_start_units_ub_constraint,
                ),
                erm_shutdown_units_ub_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_shutdown_units_ub_constraint,
                ),
                erm_commitment_tracking_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                    rule=self._erm_commitment_tracking_constraint,
                ),
            )
            if getattr(self, "energy_budget_annual", None) is not None:
                pyomo_components.update(
                    erm_annual_energy_budget_MWh=pyo.Expression(
                        model.MODELED_YEARS,
                        model.SELECT_WEATHER_YEARS,
                        rule=self._erm_energy_budget_annual_MWh,
                    ),
                    erm_annual_energy_budget_constraint=pyo.Constraint(
                        model.MODELED_YEARS,
                        model.SELECT_WEATHER_YEARS,
                        rule=self._erm_annual_energy_budget_constraint,
                    ),
                )
            if getattr(self, "energy_budget_daily", None) is not None:
                pyomo_components.update(
                    erm_daily_energy_budget_MWh=pyo.Expression(
                        model.MODELED_YEARS,
                        model.WEATHER_PERIODS,
                        rule=self._erm_energy_budget_daily_MWh,
                    ),
                    erm_daily_energy_budget_constraint=pyo.Constraint(
                        model.MODELED_YEARS,
                        model.WEATHER_PERIODS,
                        rule=self._erm_daily_energy_budget_constraint,
                    ),
                )
            if getattr(self, "max_daily_calls", None) is not None:
                pyomo_components.update(
                    erm_daily_call_limit_constraint=pyo.Constraint(
                        model.MODELED_YEARS,
                        model.WEATHER_PERIODS,
                        rule=self._erm_daily_call_limit_constraint,
                    ),
                )
            if getattr(self, "max_call_duration") is not None:
                pyomo_components.update(
                    erm_max_dr_call_duration_constraint=pyo.Constraint(
                        model.MODELED_YEARS,
                        model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                        rule=self._erm_max_dr_call_duration_constraint,
                    ),
                )

            if construct_costs:
                pyomo_components.update(
                    erm_dispatch_cost_per_MWh=pyo.Param(
                        within=pyo.Reals, initialize=0.01
                    ),  # shed DR dispatch is more costly than storage
                    erm_dispatch_cost=pyo.Expression(
                        model.MODELED_YEARS,
                        model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS,
                        rule=self._erm_dispatch_cost,
                        doc="ERM Shed DR Dispatch Cost ($)",
                    ),
                    erm_annual_dispatch_cost=pyo.Expression(
                        model.MODELED_YEARS,
                        rule=self._erm_annual_dispatch_cost,
                        doc="ERM Annual Shed DR Dispatch Cost ($)",
                    ),
                )

        return pyomo_components
