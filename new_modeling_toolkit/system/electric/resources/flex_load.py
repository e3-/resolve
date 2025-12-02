from typing import ClassVar

import pandas as pd
import pyomo.environ as pyo
from pydantic import Field
from pydantic import model_validator
from typing_extensions import Annotated

from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.temporal.settings import DispatchWindowEdgeEffects
from new_modeling_toolkit.system.electric.resources.shed_dr import ShedDrResource
from new_modeling_toolkit.system.electric.resources.shed_dr import ShedDrResourceGroup
from new_modeling_toolkit.system.electric.resources.storage import StorageResource
from new_modeling_toolkit.system.electric.resources.storage import StorageResourceGroup
from new_modeling_toolkit.system.electric.resources.unit_commitment import UnitCommitmentMethod


class FlexLoadResource(ShedDrResource, StorageResource):
    SAVE_PATH: ClassVar[str] = "resources/shift"
    ###########################
    # Flexible Load Attribute #
    ###########################

    adjacency: Annotated[int, Field(gt=0), Metadata(category=FieldCategory.OPERATIONS)] = Field(
        ...,
        description="Number of adjacent hours to constrain energy shifting. Adjacency constraints ensure that if load is shifted down in one hour, an equivalent amount of load is shifted up at most X hours away, and vice versa. [hours]",
    )

    @property
    def adjacency_offset(self) -> int:
        if getattr(self, "_adjacency_offset", None) is None:
            hour_offsets = int(2 * self.adjacency + 1)
            self._adjacency_offset = hour_offsets
        return self._adjacency_offset

    @model_validator(mode="after")
    def validate_erm_policies_empty(cls, values):
        """FlexLoad resources do not support ERM policies; enforce empty dict.

        This validator raises if `erm_policies` is provided and is not an empty dictionary.
        """
        # Some ancestors define `erm_policies` default as {}. Only error if non-empty.
        erm = getattr(values, "erm_policies", None)
        if isinstance(erm, dict) and len(erm) > 0:
            raise ValueError(
                f"FlexLoadResource {getattr(values, 'name', '')} does not support ERM policies; expected an empty dictionary for `erm_policies`."
            )
        return values

    #####################################################################################################
    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = LastUpdatedOrderedDict()
        pyomo_components.update(
            # The separation of power_input and power_output tracking is only needed for correct `adjacency` and `max_call_duration` constraints for FlexLoadResource
            committed_units_power_input=pyo.Var(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                within=self.unit_commitment_mode.var_type,
                doc="Number of Power Input Committed Units",
            ),
            # tracking variables for power output only
            start_units_power_output=pyo.Var(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                within=pyo.NonNegativeReals,
                doc="Number of Power Output Start Units",
            ),
            shutdown_units_power_output=pyo.Var(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                within=pyo.NonNegativeReals,
                doc="Number of Power Output Shutdown Units",
            ),
            committed_units_power_output=pyo.Var(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                within=self.unit_commitment_mode.var_type,
                doc="Number of Power Output Committed Units",
            ),
        )

        if self.unit_commitment_mode == UnitCommitmentMethod.SINGLE_UNIT:
            pyomo_components.update(
                committed_capacity_mw_power_output=pyo.Var(
                    model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, within=pyo.NonNegativeReals
                ),
                committed_capacity_mw_power_input=pyo.Var(
                    model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, within=pyo.NonNegativeReals
                ),
                committed_capacity_mw_power_output_ub=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._committed_capacity_mw_power_output_ub_constraint,
                ),
                committed_capacity_mw_power_output_unit_size_max=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._committed_capacity_mw_power_output_unit_size_max_constraint,
                ),
                committed_capacity_mw_power_output_unit_size_min=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._committed_capacity_mw_power_output_unit_size_min_constraint,
                ),
                committed_capacity_mw_power_input_ub=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._committed_capacity_mw_power_input_ub_constraint,
                ),
                committed_capacity_mw_power_input_unit_size_max=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._committed_capacity_mw_power_input_unit_size_max_constraint,
                ),
                committed_capacity_mw_power_input_unit_size_min=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._committed_capacity_mw_power_input_unit_size_min_constraint,
                ),
            )
        else:
            pyomo_components.update(
                committed_capacity_mw_power_output=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._committed_capacity_mw_power_output,
                ),
                committed_capacity_mw_power_input=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._committed_capacity_mw_power_input,
                ),
            )

        # Note: call super after commitment variable expressions so inheritance works correctly
        pyomo_components.update(super()._construct_operational_rules(model=model, construct_costs=construct_costs))

        pyomo_components.update(
            committed_unit_constraint=pyo.Constraint(
                model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, rule=self._committed_unit_constraint
            ),
            commitment_power_output_tracking_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._commitment_power_output_tracking_constraint,
            ),
        )

        pyomo_components.update(
            power_output_adjacency_constraint=pyo.Constraint(
                model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, rule=self._power_output_adjacency_constraint
            ),
            power_input_adjacency_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._power_input_adjacency_constraint,
            ),
        )

        if (
            model.dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
            and self.allow_inter_period_sharing
        ):
            pyomo_components.update(
                power_output_inter_adjacency_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.CHRONO_PERIODS,
                    pyo.RangeSet(0, self.adjacency),
                    rule=self._power_output_inter_adjacency_constraint,
                ),
                power_input_inter_adjacency_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.CHRONO_PERIODS,
                    pyo.RangeSet(0, self.adjacency),
                    rule=self._power_input_inter_adjacency_constraint,
                ),
            )

        return pyomo_components

    def _committed_capacity(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        return block.committed_units[modeled_year, dispatch_window, timestamp]

    def _max_dr_call_duration_intra_period_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Define dr call window for a shift dr event - power output only.
        I.e., length  of one DR call in terms of hours.
        """
        hour_offsets = range(0, self.max_call_duration)
        return self.formulation_block.committed_units_power_output[modeled_year, dispatch_window, timestamp] <= sum(
            self.formulation_block.start_units_power_output[
                modeled_year,
                self.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS.prevw(
                    (dispatch_window, timestamp), step=t
                ),
            ]
            for t in hour_offsets
        )

    def _annual_dr_call_limit_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Max # of call per year."""
        constraint = block.model().sum_timepoint_component_slice_to_annual(
            block.start_units_power_output[modeled_year, :, :]
        ) <= self.max_annual_calls.data.at[f"01-01-{modeled_year.year}"] * self._annual_num_units(modeled_year)

        return constraint

    def _monthly_dr_call_limit_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp, month: pd.Timestamp):
        """Max number of calls per month"""
        constraint = sum(
            block.start_units_power_output[modeled_year, dispatch_period, timestamp]
            for dispatch_period, timestamp in block.model().MONTH_TO_TIMESTAMPS_MAPPING[month]
        ) <= self.max_monthly_calls.data.at[f"{month.month}-01-{modeled_year.year}"] * self._annual_num_units(
            modeled_year
        )
        return constraint

    def _daily_dr_call_limit_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp, day: pd.Timestamp):
        """Max # of calls per day"""
        constraint = sum(
            block.start_units_power_output[modeled_year, dispatch_period, timestamp]
            for dispatch_period, timestamp in block.model().DAY_TO_TIMESTAMPS_MAPPING[day]
        ) <= self.max_daily_calls.data.at[f"{day.month}-{day.day}-{modeled_year.year}"] * self._annual_num_units(
            modeled_year
        )

        return constraint

    def _committed_capacity_mw_power_output(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Committed units * size of units in MW available for power output
        """
        return (
            self.formulation_block.committed_units_power_output[modeled_year, dispatch_window, timestamp]
            * self.formulation_block.unit_size[modeled_year]
        )

    def _committed_capacity_mw_power_input(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Committed units * size of units in MW available for power input
        """
        return (
            self.formulation_block.committed_units_power_input[modeled_year, dispatch_window, timestamp]
            * self.formulation_block.unit_size[modeled_year]
        )

    def _power_input_max(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Derate hourly operational (or committed) capacity by `increase_load_potential_profile`
        """
        return (
            self.formulation_block.committed_capacity_mw_power_input[modeled_year, dispatch_window, timestamp]
            * self.power_input_max.data.at[timestamp]
        )

    def _power_input_min(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Derate hourly operational (or committed) capacity by `increase_load_potential_profile`
        """
        return (
            self.formulation_block.committed_capacity_mw_power_input[modeled_year, dispatch_window, timestamp]
            * self.power_input_min.data.at[timestamp]
        )

    def _power_output_max(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Derate hourly operational (or committed) capacity by `provide_power_potential_profile`.
        """
        return (
            self.formulation_block.committed_capacity_mw_power_output[modeled_year, dispatch_window, timestamp]
            * self.power_output_max.data.at[timestamp]
        )

    def _power_output_min(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Derate hourly operational (or committed) capacity by `provide_power_potential_profile`.
        """
        return (
            self.formulation_block.committed_capacity_mw_power_output[modeled_year, dispatch_window, timestamp]
            * self.power_output_min.data.at[timestamp]
        )

    def _committed_unit_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Total committed units are the sum of committed units available for power output and committed units available for power input, which forces the total of the two to be less than operational units
        """
        return (
            self.formulation_block.committed_units[modeled_year, dispatch_window, timestamp]
            == self.formulation_block.committed_units_power_input[modeled_year, dispatch_window, timestamp]
            + self.formulation_block.committed_units_power_output[modeled_year, dispatch_window, timestamp]
        )

    def _commitment_power_output_tracking_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """Track unit commitment status of power output only. Needed for call_duration and adjacency constraints"""
        next_timestamp = self.formulation_block.model().TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window].nextw(timestamp)
        return (
            self.formulation_block.committed_units_power_output[modeled_year, dispatch_window, next_timestamp]
            == self.formulation_block.committed_units_power_output[modeled_year, dispatch_window, timestamp]
            + self.formulation_block.start_units_power_output[modeled_year, dispatch_window, next_timestamp]
            - self.formulation_block.shutdown_units_power_output[modeled_year, dispatch_window, next_timestamp]
        )

    def _power_output_adjacency_constraint(
        self, block, model_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """Handles adjacency constraints for timepoints **within** a representative period.

        If any the adjacency range spans **across** representative periods, that is handled by the
        `Increase_Load_Adjacency_Across_Rep_Period_Constraint`.

        the constraint is formulated as:
            Provide_Power_MW[t+n] <= sum(L[t+n] for n in range(2*n + 1)
        Again, note how it's constraining on t+n hour instead of the t hour
        """
        if (
            block.model().dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
            and self.allow_inter_period_sharing
        ) and any(
            timestamp + pd.Timedelta(hours=offset)
            > self.formulation_block.model().last_timepoint_in_dispatch_window[dispatch_window]
            for offset in range(self.adjacency_offset)
        ):
            # if inter_period_sharing is turned on, skip the constraint on the first timepoint in the dispatch window because this will be written in the min_uptime_inter_constraint. Otherwise it will loop around
            return pyo.Constraint.Skip
        else:
            return self.formulation_block.power_output[
                model_year,
                self.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS.nextw(
                    (dispatch_window, timestamp), step=self.adjacency
                ),
            ] <= sum(
                self.formulation_block.power_input[
                    model_year,
                    self.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS.nextw(
                        (dispatch_window, timestamp), step=offset
                    ),
                ]
                for offset in range(self.adjacency_offset)
            )

    def _power_input_inter_adjacency_constraint(
        self, block, model_year: pd.Timestamp, chrono_period: pd.Timestamp, hour_offset: int
    ):
        """Handles adjacency constraints for timepoints **between** representative periods."""
        model = self.formulation_block.model()

        return self.formulation_block.power_input[
            model_year,
            model.find_next_chronological_dispatch_window_and_timepoint(chrono_period, self.adjacency - hour_offset),
        ] <= sum(
            self.formulation_block.power_output[
                model_year, model.find_next_chronological_dispatch_window_and_timepoint(chrono_period, t - hour_offset)
            ]
            for t in range(self.adjacency_offset)
        )

    def _power_output_inter_adjacency_constraint(
        self, block, model_year: pd.Timestamp, chrono_period: pd.Timestamp, hour_offset: int
    ):
        """Handles adjacency constraints for timepoints **between** representative periods."""
        model = self.formulation_block.model()
        return self.formulation_block.power_output[
            model_year,
            model.find_next_chronological_dispatch_window_and_timepoint(chrono_period, self.adjacency - hour_offset),
        ] <= sum(
            self.formulation_block.power_input[
                model_year, model.find_next_chronological_dispatch_window_and_timepoint(chrono_period, t - hour_offset)
            ]
            for t in range(self.adjacency_offset)
        )

    def _power_input_adjacency_constraint(
        self, block, model_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """Handles adjacency constraints for timepoints **within** a representative period.

        If any the adjacency range spans **across** representative periods, that is handled by the
        `Increase_Load_Adjacency_Across_Rep_Period_Constraint`.

        the constraint is formulated as:
            Increase_Load_MW[t+n] <= sum(P[t+n] for n in range(2*n + 1)

        Note how it's constraining on t+n instead of t.
        """
        if (
            block.model().dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
            and self.allow_inter_period_sharing
        ) and any(
            timestamp + pd.Timedelta(hours=offset)
            > self.formulation_block.model().last_timepoint_in_dispatch_window[dispatch_window]
            for offset in range(self.adjacency_offset)
        ):
            # if inter_period_sharing is turned on, skip the constraint on the first timepoint in the dispatch window because this will be written in the min_uptime_inter_constraint. Otherwise it will loop around
            return pyo.Constraint.Skip

        else:
            return self.formulation_block.power_input[
                model_year,
                self.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS.nextw(
                    (dispatch_window, timestamp), step=self.adjacency
                ),
            ] <= sum(
                self.formulation_block.power_output[
                    model_year,
                    self.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS.nextw(
                        (dispatch_window, timestamp), step=offset
                    ),
                ]
                for offset in range(self.adjacency_offset)
            )

    def _committed_capacity_mw_power_output_ub_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Upper-bound constraint: power output committed capacity cannot exceed the product of
        maximum potential and the unit commitment indicator.

        - This constraint enforces that if the unit is not committed (committed_units = 0), then committed capacity is zero.
        - When committed, the capacity is limited by the resource's maximum potential.

        Returns: pyo.Constraint: power_output_committed_capacity <= max_potential * power_output_committed_units

        """
        return (
            block.committed_capacity_mw_power_output[modeled_year, dispatch_window, timestamp]
            <= block.max_potential[modeled_year]
            * block.committed_units_power_output[modeled_year, dispatch_window, timestamp]
        )

    def _committed_capacity_mw_power_output_unit_size_max_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Upper-bound constraint: power output committed capacity cannot exceed the unit size.

        This constraint enforces a physical limit: the committed capacity
        of a resource in any period cannot exceed the installed unit size
        available in that modeled year.

        Returns: pyomo.Constraint: power_output_committed_capacity <= unit_size
        """
        return (
            block.committed_capacity_mw_power_output[modeled_year, dispatch_window, timestamp]
            <= block.unit_size[modeled_year]
        )

    def _committed_capacity_mw_power_output_unit_size_min_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Lower-bound constraint: power output committed capacity must be at least the unit size
        when the resource is committed, and can relax to zero when not committed.

        - If committed_units = 1, the inequality reduces to:
            committed_capacity >= unit_size
          enforcing that the full unit size is available.
        - If committed_units = 0, the RHS relaxes to a large negative value,
          effectively removing the lower bound and allowing committed_capacity = 0.

        Returns: pyomo.Constraint: power_output_committed_capacity >= unit_size - max_potential * (1 - power_output_committed_units)
        """
        return block.committed_capacity_mw_power_output[modeled_year, dispatch_window, timestamp] >= block.unit_size[
            modeled_year
        ] - block.max_potential[modeled_year] * (
            1 - block.committed_units_power_output[modeled_year, dispatch_window, timestamp]
        )

    def _committed_capacity_mw_power_input_ub_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Upper-bound constraint: power input committed capacity cannot exceed the product of
        maximum potential and the unit commitment indicator.

        - This constraint enforces that if the unit is not committed (committed_units = 0), then committed capacity is zero.
        - When committed, the capacity is limited by the resource's maximum potential.

        Returns: pyo.Constraint: power_input_committed_capacity <= max_potential * power_input_committed_units

        """
        return (
            block.committed_capacity_mw_power_input[modeled_year, dispatch_window, timestamp]
            <= block.max_potential[modeled_year]
            * block.committed_units_power_input[modeled_year, dispatch_window, timestamp]
        )

    def _committed_capacity_mw_power_input_unit_size_max_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Upper-bound constraint: power input committed capacity cannot exceed the unit size.

        This constraint enforces a physical limit: the committed capacity
        of a resource in any period cannot exceed the installed unit size
        available in that modeled year.

        Returns: pyomo.Constraint: power_input_committed_capacity <= unit_size
        """
        return (
            block.committed_capacity_mw_power_input[modeled_year, dispatch_window, timestamp]
            <= block.unit_size[modeled_year]
        )

    def _committed_capacity_mw_power_input_unit_size_min_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Lower-bound constraint: power input committed capacity must be at least the unit size
        when the resource is committed, and can relax to zero when not committed.

        - If committed_units = 1, the inequality reduces to:
            committed_capacity >= unit_size
          enforcing that the full unit size is available.
        - If committed_units = 0, the RHS relaxes to a large negative value,
          effectively removing the lower bound and allowing committed_capacity = 0.

        Returns: pyomo.Constraint: power_input_committed_capacity >= unit_size - max_potential * (1 - power_input_committed_units)
        """
        return block.committed_capacity_mw_power_input[modeled_year, dispatch_window, timestamp] >= block.unit_size[
            modeled_year
        ] - block.max_potential[modeled_year] * (
            1 - block.committed_units_power_input[modeled_year, dispatch_window, timestamp]
        )


class FlexLoadResourceGroup(ShedDrResourceGroup, StorageResourceGroup, FlexLoadResource):
    SAVE_PATH: ClassVar[str] = "resources/shift/groups"
    _NAME_PREFIX: ClassVar[str] = "shift_dr_resource_group"
    _GROUPING_CLASS = FlexLoadResource

    def _committed_capacity_mw_power_output_ub_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Different than on resource because it needs to look at group cumulative capacity rather than resource potential
        """
        return (
            block.committed_capacity_mw_power_output[modeled_year, dispatch_window, timestamp]
            <= self.cumulative_potential.data.at[modeled_year]
            * block.committed_units_power_output[modeled_year, dispatch_window, timestamp]
        )

    def _committed_capacity_mw_power_input_ub_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        return (
            block.committed_capacity_mw_power_input[modeled_year, dispatch_window, timestamp]
            <= self.cumulative_potential.data.at[modeled_year]
            * block.committed_units_power_input[modeled_year, dispatch_window, timestamp]
        )
