import copy
import enum
from typing import ClassVar

import pandas as pd
import pyomo.environ as pyo
from loguru import logger
from pydantic import Field
from pydantic import root_validator
from typing_extensions import Annotated

from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.custom_model import units
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.system.asset import AnyOperationalGroup
from new_modeling_toolkit.system.electric.resources.generic import GenericResourceGroup
from new_modeling_toolkit.system.electric.resources.shed_dr import ShedDrResource
from new_modeling_toolkit.system.electric.resources.storage import StorageResource


@enum.unique
class FlexLoadShiftDirection(enum.Enum):
    PRE_CONSUMPTION = "pre_consumption"
    DEFERRED_CONSUMPTION = "deferred_consumption"
    EITHER = "either"


# todo: move the power_ouput tracking variables from unit commitment to flex loads only


class FlexLoadResource(ShedDrResource, StorageResource):
    SAVE_PATH: ClassVar[str] = "resources/shift"
    ###########################
    # Flexible Load Attribute #
    ###########################

    adjacency: Annotated[int, Field(gt=0)] = Field(
        ...,
        description="Number of adjacent hours to constrain energy shifting. Adjacency constraints ensure that if load is shifted down in one hour, an equivalent amount of load is shifted up at most X hours away, and vice versa. [hours]",
    )

    shift_direction: FlexLoadShiftDirection = Field(
        ...,
        description="If pre_consumption, flexible load resources always need to increase load first before providing power."
        "An example of this is pre-cooling."
        "If deferred_consumption, flexible load resources always will provide power first before increasing load."
        "An example of this is deferring to use appliances. If either, the resource can do provide power or increase load first depending on what is optimal.",
    )

    duration: Annotated[
        ts.NumericTimeseries, Metadata(category=FieldCategory.OPERATIONS, show_year_headers=False, units=units.hour)
    ] = Field(
        None,
        description="Operational time of the battery at a specified power level before it runs out of energy [hours]. Note: not all flex load resources will require a duration. Only EV resources. For all others, the duration will default to the length of the adjacency window.",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
        alias="flex_storage_duration",
    )

    energy_budget_daily: ts.FractionalTimeseries = Field(
        None,
        description="Daily fraction of energy capacity allowed for daily dispatch [dimensionless].",
        default_freq="D",
        up_method="ffill",
        down_method="mean",
        weather_year=True,
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        logger.warning(f"Setting {self.name} resource unit size equal to planned capacity.")
        self.unit_size.data = self.capacity_planned.data

    @root_validator(skip_on_failure=True)
    def update_duration_default(cls, values):
        """
        Set default of duration equal to adjacency if not provided
        """
        adjacency = values.get("adjacency")
        duration = values.get("duration")

        if duration is None and adjacency is not None:
            new_duration = ts.NumericTimeseries(
                name="storage_capacity_planned",
                data=copy.deepcopy(values["capacity_planned"].data),
            )
            new_duration.data[:] = adjacency
            new_duration.name = "duration"
            values["duration"] = new_duration
            values["_scaled_SOC_max_profile"] = None
        return values

    def _identify_initial_SOC(self, dispatch_window_df: pd.DataFrame, modeled_year: int):
        """
        Set the initial storage SOC (needed for storage constraints) based on shift direction inputs
        """
        dispatch_window_df["initial_SOC"] = self.power_input_max.data.loc[dispatch_window_df["index"].values].values
        initial_soc = dispatch_window_df.groupby(dispatch_window_df.index.get_level_values(0)).first()["initial_SOC"]
        self.initial_storage_SOC = pd.Series(initial_soc)
        if self.shift_direction == FlexLoadShiftDirection.PRE_CONSUMPTION:
            self.initial_storage_SOC.loc[:] = 0
        elif self.shift_direction == FlexLoadShiftDirection.DEFERRED_CONSUMPTION:
            self.initial_storage_SOC.loc[:] = self.storage_capacity_planned.slice_by_year(modeled_year)
        else:
            self.initial_storage_SOC.loc[:] = self.storage_capacity_planned.slice_by_year(modeled_year) / 2

    #####################################################################################################
    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = LastUpdatedOrderedDict()
        pyomo_components.update(
            # The separation of power_input and power_output tracking is only needed for correct `adjacency` and `max_call_duration` constraints for FlexLoadResource
            committed_units_power_input=pyo.Var(
                model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, within=self.unit_commitment_mode.var_type
            ),
            # tracking variables for power output only
            start_units_power_output=pyo.Var(
                model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, within=pyo.NonNegativeReals
            ),
            shutdown_units_power_output=pyo.Var(
                model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, within=pyo.NonNegativeReals
            ),
            committed_units_power_output=pyo.Var(
                model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, within=self.unit_commitment_mode.var_type
            ),
            committed_capacity_mw_power_output=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._committed_capacity_mw_power_output,
            ),
            committed_capacity_mw_power_input=pyo.Expression(
                model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, rule=self._committed_capacity_mw_power_input
            ),
        )

        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

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

        return pyomo_components

        # self._identify_initial_SOC(
        #     model.temporal_settings.dispatch_windows_map.index.to_frame(), model.temporal_settings.modeled_years[0]
        # )
        #
        # block = model.blocks[self.name]
        # super()._construct_operational_rules(model)
        #
        # @block.Constraint(model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS)
        # def adjacency_constraint(block, modeled_year, dispatch_window, timestamp):
        #     """
        #     Define adjacency window for a shift dr event. The SOC of the resource must return to the initial state
        #     within x hours before or after the DR (power output only) event.
        #     I.e., length of one DR call in terms of hours.
        #     """
        #     if getattr(self, "max_call_duration") is not None:
        #         hour_offsets = range(0, int(self.max_call_duration) + 2 * self.adjacency + 1)
        #     else:
        #         hour_offsets = range(0, 2 * self.adjacency + 1)
        #     return block.committed_units[modeled_year, dispatch_window, timestamp] <= sum(
        #         block.start_units[
        #             modeled_year, model.DISPATCH_WINDOWS_AND_TIMESTAMPS.prevw((dispatch_window, timestamp), step=t)
        #         ]
        #         for t in hour_offsets
        #     )
        #
        # @block.Constraint(model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS)
        # def energy_balance_committed_units_constraint(block, modeled_year, dispatch_window, timestamp):
        #     """
        #     Coupled with energy_balance_uncommitted_units_constraint: Forces hours where units are uncommited to return to the initial state of charge
        #     When committed_units is 0: state_of_charge <= initial_charge
        #     """
        #     initial_charge = self.initial_storage_SOC[dispatch_window]
        #     return (
        #         block.state_of_charge[modeled_year, dispatch_window, timestamp] - initial_charge
        #         <= self.scaled_SOC_max_profile[modeled_year].at[timestamp]
        #         * block.committed_units[modeled_year, dispatch_window, timestamp]
        #     )
        #
        # @block.Constraint(model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS)
        # def energy_balance_uncommitted_units_constraint(block, modeled_year, dispatch_window, timestamp):
        #     """
        #     Coupled with energy_balance_committed_units_constarint: Forces hours where units are uncommited to return to the initial state of charge
        #     When committed_units is 0 (aka uncommitted): state_of_charge >= initial_charge
        #     """
        #     initial_charge = self.initial_storage_SOC[dispatch_window]
        #     return (
        #         block.state_of_charge[modeled_year, dispatch_window, timestamp]
        #         >= initial_charge * (block.committed_units[modeled_year, dispatch_window, timestamp] - 1) * -1
        #     )
        #
        # @block.Constraint(model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS)
        # def start_and_shutdown_unit_exclusivity_constraint(block, modeled_year, dispatch_window, timestamp):
        #     """
        #     Prevents a unit from starting and shutting down in the same hour. Necessary to enforce the energy balance constraints
        #     """
        #     return (
        #         block.start_units[modeled_year, dispatch_window, timestamp]
        #         + block.shutdown_units[modeled_year, dispatch_window, timestamp]
        #         <= 1
        #     )
        #
        # if self.shift_direction is not FlexLoadShiftDirection.EITHER:
        #
        #     @block.Constraint(model.MODELED_YEARS, model.DISPATCH_WINDOWS)
        #     def shift_direction_constraint(block, modeled_year, dispatch_window):
        #         """
        #         Constraint to direct the shift direction of flexible load resources
        #         If pre_consumption = True, flexible load resources always need to increase load first before providing power.
        #         An example of this is pre-cooling.
        #         If deferred_consumption = True, flexible load resources always will provide power first before increasing load.
        #         An example of this is deferring to use appliances.
        #
        #         model: model
        #         year: modeled_year in timestep format
        #         tp_index: timepoint index of the variable in a tuple format. Example: RECAP (hour,), RESOLVE (year, rep_period,hour,)
        #         variable_name: variable name to apply the constraint. Example: RECAP: "Storage_SOC_MWh", RESOLVE "SOC_Intra_Period"
        #         """
        #         if self.shift_direction == FlexLoadShiftDirection.PRE_CONSUMPTION:
        #             return (
        #                 block.state_of_charge[
        #                     modeled_year, dispatch_window, model.TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window].first()
        #                 ]
        #                 == 0
        #             )
        #
        #         elif self.shift_direction == FlexLoadShiftDirection.DEFERRED_CONSUMPTION:
        #             full_charge = self.storage_capacity_planned.slice_by_year(modeled_year)
        #             return (
        #                 block.state_of_charge[
        #                     modeled_year, dispatch_window, model.TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window].first()
        #                 ]
        #                 == full_charge
        #             )
        #         else:
        #             raise NotImplementedError(
        #                 f"Flex load shift direction constraint for shift direction `{self.shift_direction}` is not "
        #                 f"implemented."
        #             )
        #
        # @block.Constraint(model.MODELED_YEARS, model.DISPATCH_WINDOWS)
        # def first_hour_state_of_charge_tracking(block, modeled_year, dispatch_window):
        #     """
        #     Handle the edge case where the first timestamp has a fixed initial SOC
        #     """
        #     timestamp = model.TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window].first()
        #     prev_timestamp = model.TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window].prevw(timestamp)
        #     constraint = block.state_of_charge[modeled_year, dispatch_window, timestamp] == (
        #         block.state_of_charge[modeled_year, dispatch_window, prev_timestamp]
        #         + block.power_input[modeled_year, dispatch_window, prev_timestamp]
        #         * self.charging_efficiency.data.at[timestamp]
        #         - block.power_output[modeled_year, dispatch_window, prev_timestamp]
        #         / self.discharging_efficiency.data.at[timestamp]
        #     )
        #
        #     return constraint

    def _committed_capacity_mw_power_output(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Committed units * size of units in MW available for power output
        """
        return (
            self.formulation_block.committed_units_power_output[modeled_year, dispatch_window, timestamp]
            * self.unit_size
        )

    def _committed_capacity_mw_power_input(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Committed units * size of units in MW available for power input
        """
        return (
            self.formulation_block.committed_units_power_input[modeled_year, dispatch_window, timestamp]
            * self.unit_size
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


class FlexLoadResourceGroup(GenericResourceGroup, FlexLoadResource):
    SAVE_PATH: ClassVar[str] = "resources/shed/groups"
    _NAME_PREFIX: ClassVar[str] = "shed_dr_resource_group"
    _GROUPING_CLASS = FlexLoadResource

    # TODO (skramer): Figure out how to determine operational equality for unit commitment resources when selected
    #  builds can result in differing number of units
    def construct_operational_groups(cls, assets: list[FlexLoadResource] = False) -> dict[str, AnyOperationalGroup]:
        raise NotImplementedError("Operational grouping not defined for unit commitment resources")
