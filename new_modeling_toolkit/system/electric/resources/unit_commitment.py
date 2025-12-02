import enum
from abc import ABC
from typing import ClassVar

import numpy as np
import pandas as pd
import pyomo.environ as pyo
from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator
from pydantic import NonNegativeFloat
from pydantic import PositiveFloat
from pydantic import PositiveInt
from pydantic import ValidationInfo
from pyomo.environ import RangeSet
from typing_extensions import Annotated

from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.model import ModelType
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.temporal.settings import DispatchWindowEdgeEffects
from new_modeling_toolkit.system.electric.resources.generic import GenericResource
from new_modeling_toolkit.system.electric.resources.generic import GenericResourceGroup


@enum.unique
class UnitCommitmentMethod(enum.Enum):
    """
    Formulation options for unit commitment tracking.

    This enum defines how unit commitment is represented in the optimization model,
    controlling whether units can be partially committed, must be integer counts,
    or represented as a single aggregate binary unit.

    Methods
    -------
    INTEGER
        Integer (discrete) unit commitment formulation.
        - Committed_units is an integer count of how many units are online.
        - Allows values greater than 1 when multiple units exist.
        - Provides accurate representation of unit on/off status.
        - Solved as a Mixed-Integer Linear Program (MILP), which is
          computationally more expensive but physically realistic.
        - Best for short-term operations and reliability studies.

    LINEAR
        Linear (continuous) unit commitment formulation.
        - Committed_units is a continuous variable (>=0) representing
          the fraction or number of units online.
        - Can take fractional values (e.g., 0.5 units), which improves tractability
          but may be less realistic.
        - Allows values greater than 1 if multiple units exist.
        - Simplifies the model into a Linear Program (LP), improving scalability
          for capacity expansion or long-term planning.

    SINGLE_UNIT
        Single-unit capacity commitment formulation.
        - Represents the resource as a single binary on/off variable.
        - Commitment is 0 (off) or 1 (on), with unit_size defining the installed capacity.
        - Used when unit_size is itself an optimization decision or when
          aggregating a fleet into one equivalent resource.
        - Captures aggregate behavior but cannot differentiate individual units.

    Attributes
    ----------
    value : str
        The string identifier for the unit commitment method.

    Returns
    -------
    var_type : pyomo.Set
        The appropriate Pyomo domain for the commitment variable:
        - INTEGER → `pyo.NonNegativeIntegers`
        - LINEAR → `pyo.NonNegativeReals`
        - SINGLE_UNIT → `pyo.Binary`
    """

    INTEGER = "integer"
    LINEAR = "linear"
    SINGLE_UNIT = "single_unit"

    @property
    def var_type(self):
        if self.value == "integer":
            return pyo.NonNegativeIntegers
        elif self.value == "linear":
            return pyo.NonNegativeReals
        elif self.value == "single_unit":
            return pyo.Binary


class UnitCommitmentResource(GenericResource, ABC):
    """
    Aggregate similar but non-identical units to reduce decision variables while still capturing individual unit decisions and constraints.
    Most constraints in this class are based on IEEE paper"Heterogeneous Unit Clustering for Efficient Operational Flexibility Modeling"
    See ReadTheDocs documentation for a link to the paper
    """

    # todo: this messes up the outages in recap
    unit_size: Annotated[PositiveFloat, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        1.0,
        description="Size of each unit that can be independently committed, in MW.",
        alias="unit_size_mw",
        title=f"Unit Size",
    )
    unit_commitment_mode: Annotated[UnitCommitmentMethod, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        UnitCommitmentMethod.LINEAR,
        description="To strictly the number of shift events, set to 'integer' or 'single_unit'. Otherwise, the default is ‘linear’ and does not fully limit the number of events. Linear is the default, because this is a much simpler optimization problem and you will see minimal increase in run time. This is an acceptable assumption for many projects if you are modeling a large area which could have several Demand Response programs in different locations, each with their own call limits. When modeling smaller geographic areas, or if the project needs strict call limits set the unit_commitment attribute to ‘integer’. Note that this will increase the run time. How much will vary depending on the model complexity, but a good rule of thumb is to assume 1.5x the run time if the variables were linear.",
        title=f"Unit Commitment Method",
    )
    min_down_time: Annotated[PositiveInt | None, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        None,
        description="Minimum downtime between commitments (hours).",
        title=f"Min Down Time",
    )
    min_up_time: Annotated[PositiveInt | None, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        None,
        description="Minimum uptime during a commitment (hours).",
        title=f"Min Up Time",
    )

    min_stable_level: Annotated[float, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        0,
        description="Minimum stable level when committed",
        title=f"Min Stable Level",
        ge=0,
        le=1,
    )

    start_cost: Annotated[NonNegativeFloat, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        0.0,
        description="Cost for each unit startup ($/unit start). "
        "If using linearized UC, this cost will be linearized as well.",
        title=f"Start Cost",
    )

    shutdown_cost: Annotated[NonNegativeFloat, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        0.0,
        description="Cost for each unit shutdown ($/unit shutdown). "
        "If using linearized UC, this cost will be linearized as well.",
        title=f"Shutdown Cost",
    )

    initial_committed_units: Annotated[pd.Series | None, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        None, description="For fixed initial condition, how many units are already committed/on"
    )

    @model_validator(mode="after")
    def check_potential_required(self):
        if self.unit_commitment_mode == UnitCommitmentMethod.SINGLE_UNIT and (
            self.potential is None or self.potential == float("inf")
        ):
            raise ValueError(
                f"Potential required for unit commitment resource while in 'single_unit' "
                f"unit commitment mode: {self.name}"
            )
        return self

    @field_validator("min_up_time", "min_down_time", mode="before")
    @classmethod
    def convert_min_up_down_time_to_int(cls, v):
        if v is None:
            return v
        elif isinstance(v, str):
            return int(round(float(v)))
        else:
            return int(round(v))

    @field_validator("ramp_rate_2_hour", "ramp_rate_3_hour", "ramp_rate_4_hour")
    @classmethod
    def base_attribute_must_be_none(cls, v, info: ValidationInfo):
        if v is not None:
            raise ValueError(
                f"Multi hour ramp rates are not implemented for UnitCommitment resources. {info.field_name} must be None for {info.data['name']}"
            )
        return v

    @model_validator(mode="after")
    def warn_if_default_unit_size(self):
        """Log a warning if `unit_size` is not explicitly provided and default value is used.

        This helps users notice when unit commitment constraints rely on the implicit 1.0 MW unit size.
        """
        try:
            fields_set = getattr(self, "model_fields_set", set())
        except Exception:
            fields_set = set()
        if "unit_size" not in fields_set and self.unit_size == 1.0:
            from loguru import logger

            logger.warning(
                f"UnitCommitmentResource {self.name}: using default unit_size=1.0 MW. "
                f"Consider setting `unit_size` explicitly if this is unintended."
            )
        return self

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_investment_rules(model=model, construct_costs=construct_costs)
        if self.unit_commitment_mode == UnitCommitmentMethod.SINGLE_UNIT:
            pyomo_components.update(
                unit_size=pyo.Expression(model.MODELED_YEARS, rule=self._dynamic_unit_size, doc="Unit Size (MW)"),
                max_potential=pyo.Param(
                    model.MODELED_YEARS,
                    initialize=self.potential,
                ),
            )
        else:
            pyomo_components.update(
                unit_size=pyo.Param(model.MODELED_YEARS, initialize=self.unit_size, doc="Unit Size (MW)")
            )
        return pyomo_components

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = LastUpdatedOrderedDict()

        # tracking variables for power input and/or power output
        pyomo_components.update(
            start_units=pyo.Var(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                within=self.unit_commitment_mode.var_type,
                doc="Number of Starts",
            ),
            annual_start_units=pyo.Expression(
                model.MODELED_YEARS, rule=self._annual_start_units, doc="Annual Number of Starts"
            ),
            shutdown_units=pyo.Var(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                within=self.unit_commitment_mode.var_type,
                doc="Number of Shutdowns",
            ),
            annual_shutdown_units=pyo.Expression(
                model.MODELED_YEARS, rule=self._annual_shutdown_units, doc="Annual Number of Shutdowns"
            ),
        )

        if construct_costs:
            pyomo_components.update(
                start_cost_in_timepoint=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._start_cost_in_timepoint,
                    doc="Start Cost ($)",
                ),
                shutdown_cost_in_timepoint=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._shutdown_cost_in_timepoint,
                    doc="Shutdown Cost ($)",
                ),
                annual_start_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=self._annual_start_cost, doc="Annual Start Cost ($)"
                ),
                annual_shutdown_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=self._annual_shutdown_cost, doc="Annual Shutdown Cost ($)"
                ),
                annual_start_and_shutdown_cost=pyo.Expression(
                    model.MODELED_YEARS, rule=self._annual_start_and_shutdown_cost
                ),
                annual_total_operational_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_operational_cost,
                    doc="Annual Total Operational Cost ($)",
                ),
            )

        pyomo_components.update(
            committed_units=pyo.Var(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                within=pyo.NonNegativeReals,
                doc="Number of Committed Units",
            ),
            operational_units_in_timepoint=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._operational_units_in_timepoint,
                doc="Number of available units",
            ),
        )

        if self.unit_commitment_mode == UnitCommitmentMethod.SINGLE_UNIT:
            pyomo_components.update(
                committed_capacity=pyo.Var(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    within=pyo.NonNegativeReals,
                ),
                committed_capacity_ub=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._committed_capacity_ub,
                ),
                committed_capacity_unit_size_max=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._committed_capacity_unit_size_max,
                ),
                committed_capacity_unit_size_min=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._committed_capacity_unit_size_min,
                ),
            )
        else:
            pyomo_components.update(
                committed_capacity=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._committed_capacity,
                )
            )

        # Note: call super after commitment variable expressions so inheritance works correctly
        pyomo_components.update(super()._construct_operational_rules(model=model, construct_costs=construct_costs))

        # Ensure that the min power output constraint is constructed if a min stable level is defined
        # Note: GenericResource will skip writing this constraint if power_output_min profile is all 0's
        # todo: I actually think this might be wrong? We also want it to call if power_output_min profile is non-zero
        if self.min_stable_level > 0:
            pyomo_components.update(
                power_output_min_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._power_output_min_constraint,
                )
            )

        pyomo_components.update(
            committed_units_ub_constraint=pyo.Constraint(
                model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, rule=self._committed_units_ub_constraint
            ),
            start_units_ub_constraint=pyo.Constraint(
                model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, rule=self._start_units_ub_constraint
            ),
            shutdown_units_ub_constraint=pyo.Constraint(
                model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, rule=self._shutdown_units_ub_constraint
            ),
            commitment_tracking_constraint=pyo.Constraint(
                model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, rule=self._commitment_tracking_constraint
            ),
        )

        # if not inter period sharing or fixed initial condition, the default is to loop over each dispatch window
        if (
            model.dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
            and self.allow_inter_period_sharing
        ):
            pyomo_components.update(
                commitment_tracking_inter_period_constraint=pyo.Constraint(
                    model.MODELED_YEARS, model.CHRONO_PERIODS, rule=self._commitment_tracking_inter_period_constraint
                )
            )

            if self.min_up_time is not None:
                pyomo_components.update(
                    min_uptime_constraint_inter=pyo.Constraint(
                        model.MODELED_YEARS,
                        model.CHRONO_PERIODS,
                        RangeSet(0, self.min_up_time - 1),
                        rule=self._min_uptime_inter_constraint,
                    )
                )

            if self.min_down_time is not None:
                pyomo_components.update(
                    min_downtime_constraint_inter=pyo.Constraint(
                        model.MODELED_YEARS,
                        model.CHRONO_PERIODS,
                        RangeSet(0, self.min_down_time - 1),
                        rule=self._min_downtime_inter_constraint,
                    )
                )

        if (
            model.TYPE == ModelType.RECAP
            and model.dispatch_window_edge_effects == DispatchWindowEdgeEffects.FIXED_INITIAL_CONDITION
        ):
            # If the model is set to fixed initial conditions and the UnitCommitmentResource force the initial committed and start units to be equal to defined input

            pyomo_components.update(
                initial_committed_units=pyo.Constraint(
                    model.MODELED_YEARS, model.DISPATCH_WINDOWS, rule=self._initial_committed_units
                ),
                initial_start_units=pyo.Constraint(
                    model.MODELED_YEARS, model.DISPATCH_WINDOWS, rule=self._initial_start_units
                ),
                initial_committed_units_in_last_timepoint=pyo.Constraint(
                    model.MODELED_YEARS, model.DISPATCH_WINDOWS, rule=self._initial_committed_units_in_last_timepoint
                ),
            )

        if self.min_up_time is not None:
            pyomo_components.update(
                min_uptime_constraint=pyo.Constraint(
                    model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, rule=self._min_uptime_intra_constraint
                )
            )

        if self.min_down_time is not None:
            pyomo_components.update(
                min_downtime_constraint=pyo.Constraint(
                    model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, rule=self._min_downtime_intra_constraint
                )
            )

        return pyomo_components

    def _annual_start_units(self, block, modeled_year: pd.Timestamp):
        """
        Sum of all timepoint unit starts in model year

        Args:
            block: pyomo Block
            modeled_year: Model year to sum

        Returns: Annual starts

        """
        return block.model().sum_timepoint_component_slice_to_annual(block.start_units[modeled_year, :, :])

    def _annual_shutdown_units(self, block, modeled_year: pd.Timestamp):
        """
        Sum of all timepoint unit shutdowns in model year

        Args:
            block: pyomo Block
            modeled_year: Model year to sum

        Returns: Annual shutdowns

        """
        return block.model().sum_timepoint_component_slice_to_annual(block.shutdown_units[modeled_year, :, :])

    def _ramp_up_ub(
        self, rr: float, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Ramp up constraint, right hand side. In these relations, the first term includes the core units that run in both time periods,
        the second corrects for startup/shutdowns to prevent artificial inflation of the ramping limits for the core units,
        and the third captures the allowable extra change in cluster production due to shut- down/startup.
        """
        return (
            rr
            * self.formulation_block.unit_size[modeled_year]
            * (
                self.formulation_block.committed_units[(modeled_year, dispatch_window, timestamp)]
                - self.formulation_block.start_units[(modeled_year, dispatch_window, timestamp)]
            )
            - (
                self.min_stable_level
                * self.formulation_block.unit_size[modeled_year]
                * self.formulation_block.shutdown_units[(modeled_year, dispatch_window, timestamp)]
            )
            + (
                max(self.min_stable_level, rr)
                * self.formulation_block.unit_size[modeled_year]
                * self.formulation_block.start_units[(modeled_year, dispatch_window, timestamp)]
            )
        )

    def _ramp_down_ub(
        self, rr: float, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Ramp down constraint, right hand side. In these relations, the first term includes the core units that run in both time periods,
        the second corrects for startup/shutdowns to prevent artificial inflation of the ramping limits for the core units,
        and the third captures the allowable extra change in cluster production due to shut- down/startup.
        """
        return (
            rr
            * self.formulation_block.unit_size[modeled_year]
            * (
                self.formulation_block.committed_units[(modeled_year, dispatch_window, timestamp)]
                - self.formulation_block.start_units[(modeled_year, dispatch_window, timestamp)]
            )
            - (
                self.min_stable_level
                * self.formulation_block.unit_size[modeled_year]
                * self.formulation_block.start_units[(modeled_year, dispatch_window, timestamp)]
            )
            + (
                max(self.min_stable_level, rr)
                * self.formulation_block.unit_size[modeled_year]
                * self.formulation_block.shutdown_units[(modeled_year, dispatch_window, timestamp)]
            )
        )

    def _annual_num_units(self, modeled_year):
        """
        Operational capacity in mw divided by size of units in mw = number of units available
        """
        if self.unit_commitment_mode == UnitCommitmentMethod.SINGLE_UNIT:
            return 1
        else:
            return (
                self.formulation_block.operational_capacity[modeled_year]
                / self.formulation_block.unit_size[modeled_year]
            )

    def _operational_units_in_timepoint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Operational units is equal to number of units in that model year
        """
        return self._annual_num_units(modeled_year)

    def _committed_capacity(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Committed units * size of units in MW available for power output
        """
        return (
            self.formulation_block.committed_units[modeled_year, dispatch_window, timestamp]
            * block.unit_size[modeled_year]
        )

    def _power_input_max(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Derate hourly operational (or committed) capacity by `increase_load_potential_profile`
        """
        return (
            self.formulation_block.committed_capacity[modeled_year, dispatch_window, timestamp]
            * self.power_input_max.data.at[timestamp]
        )

    def _power_output_max(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Derate hourly operational (or committed) capacity by `provide_power_potential_profile`.
        """
        return (
            self.formulation_block.committed_capacity[modeled_year, dispatch_window, timestamp]
            * self.power_output_max.data.at[timestamp]
        )

    def _power_output_min(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        allow user to set a lower bound on hourly generation
        note that there is a separate pmin constraint for unit commitment resources
        """
        return self.formulation_block.committed_capacity[modeled_year, dispatch_window, timestamp] * max(
            self.min_stable_level, self.power_output_min.data.at[timestamp]
        )

    def _initial_committed_units(self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp):
        """
        Forces first timepoint in each dispatch window to have predefined committed units so that the model has to make an intentional choice to turn it on
        """
        initial_units = (
            self.initial_committed_units.at[dispatch_window] if self.initial_committed_units is not None else 0
        )

        timestamp = (self.formulation_block.model().TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window].first(),)

        return self.formulation_block.committed_units[modeled_year, dispatch_window, timestamp] == initial_units

    def _initial_committed_units_in_last_timepoint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp
    ):
        """
        Forces last timepoint in each dispatch window to have predefined committed units
        """
        initial_units = (
            self.initial_committed_units.at[dispatch_window] if self.initial_committed_units is not None else 0
        )

        timestamp = (self.formulation_block.model().TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window].last(),)

        return self.formulation_block.committed_units[modeled_year, dispatch_window, timestamp] == initial_units

    def _initial_start_units(self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp):
        """
        Forces first timepoint in each dispatch window to have predefined start units so that the model has to make an intentional choice to turn it on
        """
        initial_units = (
            self.initial_committed_units.at[dispatch_window] if self.initial_committed_units is not None else 0
        )
        timestamp = (self.formulation_block.model().TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window].first(),)
        return self.formulation_block.start_units[modeled_year, dispatch_window, timestamp] == initial_units

    def _committed_units_ub_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Calculate the maximum number of units that can be committed based on operational capacity in model year.
        """
        return (
            self.formulation_block.committed_units[modeled_year, dispatch_window, timestamp]
            <= self.formulation_block.operational_units_in_timepoint[modeled_year, dispatch_window, timestamp]
        )

    def _start_units_ub_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """Calculate the maximum number of units that can be started based on operational capacity in model year."""
        return (
            self.formulation_block.start_units[modeled_year, dispatch_window, timestamp]
            <= self.formulation_block.operational_units_in_timepoint[modeled_year, dispatch_window, timestamp]
        )

    def _shutdown_units_ub_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """Calculate the maximum number of units that can be shutdown based on operational capacity in model year."""
        return (
            self.formulation_block.shutdown_units[modeled_year, dispatch_window, timestamp]
            <= self.formulation_block.operational_units_in_timepoint[modeled_year, dispatch_window, timestamp]
        )

    def _commitment_tracking_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Track unit commitment status.
        Committed units[t] = committed_units[t-1] + start_units[t] - shutdown_units[t]
        """
        if (
            block.model().dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
            and self.allow_inter_period_sharing
        ) and (timestamp == block.model().last_timepoint_in_dispatch_window[dispatch_window]):
            # if inter_period_sharing is turned on, skip the constraint on the last timepoint in the dispatch window because this will be writeen in the commitment_tracking_inter_period_constraint
            return pyo.Constraint.Skip
        else:
            next_timestamp = (
                self.formulation_block.model().TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window].nextw(timestamp)
            )
            return (
                self.formulation_block.committed_units[modeled_year, dispatch_window, next_timestamp]
                == self.formulation_block.committed_units[modeled_year, dispatch_window, timestamp]
                + self.formulation_block.start_units[modeled_year, dispatch_window, next_timestamp]
                - self.formulation_block.shutdown_units[modeled_year, dispatch_window, next_timestamp]
            )

    def _commitment_tracking_inter_period_constraint(self, block, modeled_year: pd.Timestamp, chrono_period):
        """
        Track unit commitment status between chrono periods
        Committed units[t] = committed_units[t-1] + start_units[t] - shutdown_units[t]
        """

        (
            chrono_period_1_index,
            chrono_period_2_index,
        ) = self.formulation_block.model().return_timepoints_connecting_chrono_periods(modeled_year, chrono_period)

        return (
            self.formulation_block.committed_units[chrono_period_2_index]
            == self.formulation_block.committed_units[chrono_period_1_index]
            + self.formulation_block.start_units[chrono_period_2_index]
            - self.formulation_block.shutdown_units[chrono_period_2_index]
        )

    def _min_uptime_intra_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Constrain minimum up time for unit commitment resources.
        committed_units[t] ≥ Σ Start Units for t to t-min_up_time
        Args:
            block: The block object associated with the constraint.
            modeled_year (pd.Timestamp): The timestamp representing the modeled year.
            dispatch_window (pd.Timestamp): The timestamp representing the dispatch window.
            timestamp (pd.Timestamp): The timestamp for which the constraint is being evaluated.

        Returns:
            pyo.Constraint.Skip or pyo.Constraint: Skip the constraint if inter_period_sharing is turned on and the current timestamp is within the minimum up time period. Otherwise, return the constraint expression ensuring that the committed units remain active for the specified minimum up time.

        """
        hour_offsets = range(0, self.min_up_time)
        if (
            block.model().dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
            and self.allow_inter_period_sharing
        ) and any(
            timestamp - pd.Timedelta(hours=offset)
            <= self.formulation_block.model().first_timepoint_in_dispatch_window[dispatch_window]
            for offset in hour_offsets
        ):
            # if inter_period_sharing is turned on, skip the constraint on the first timepoint in the dispatch window because this will be written in the min_uptime_inter_constraint. Otherwise it will loop around
            return pyo.Constraint.Skip
        else:
            return self.formulation_block.committed_units[modeled_year, dispatch_window, timestamp] >= sum(
                self.formulation_block.start_units[
                    modeled_year,
                    dispatch_window,
                    self.formulation_block.model().TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window].prevw(timestamp, t),
                ]
                for t in hour_offsets
            )

    def _min_downtime_intra_constraint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Constrain minimum down time for unit commitment resources.

        operational_units[t] - committed_units[t] ≥ Σ Shutdown Units for t to t-min_down_time

        Args:
            block: The block object associated with the constraint.
            modeled_year (pd.Timestamp): The timestamp representing the modeled year.
            dispatch_window (pd.Timestamp): The timestamp representing the dispatch window.
            timestamp (pd.Timestamp): The timestamp for which the constraint is being evaluated.

        Returns:
            pyo.Constraint.Skip or pyo.Constraint: Skip the constraint if inter_period_sharing is turned on and the current timestamp is within the minimum down time period. Otherwise, return the constraint expression ensuring that the operational units remain inactive for the specified minimum down time.

        """
        hour_offsets = range(0, self.min_down_time)

        if (
            block.model().dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
            and self.allow_inter_period_sharing
        ) and any(
            timestamp - pd.Timedelta(hours=offset)
            <= self.formulation_block.model().first_timepoint_in_dispatch_window[dispatch_window]
            for offset in hour_offsets
        ):
            # if inter_period_sharing is turned on, skip the constraint on the first timepoint in the dispatch window because this will be written in the min_uptime_inter_constraint. Otherwise it will loop around
            return pyo.Constraint.Skip
        else:
            return self.formulation_block.operational_units_in_timepoint[
                modeled_year, dispatch_window, timestamp
            ] - self.formulation_block.committed_units[modeled_year, dispatch_window, timestamp] >= sum(
                self.formulation_block.shutdown_units[
                    modeled_year,
                    dispatch_window,
                    self.formulation_block.model().TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window].prevw(timestamp, t),
                ]
                for t in hour_offsets
            )

    def _min_uptime_inter_constraint(
        self, block, modeled_year: pd.Timestamp, chrono_period: pd.Timestamp, min_up_time_offset: int
    ):
        """
        Constrain minimum up time for unit commitment resources for inter period
        committed_units[t] ≥ Σ Start Units for t to t-min_up_time
        In this constraint, t = (modeled_year, dispatch_window for NEXT chrono_period, first timestamp of the 'next' dispatch window + min_up_time_offset.

        For example, if the min_up_time is 5 hours and the offset is 3 hours:
            - t = 3rd hour of the next chrono period
            - The constraint would need to sum the start units for the last 2 hours of the current chrono period + the first 3 hours of the next chrono period

        Args:
            block: The block of the formulation.
            modeled_year (pd.Timestamp): Modeled year.
            chrono_period (pd.Timestamp): Chronological period.
            min_up_time_offset (int): Minimum up time offset.

        Returns: pyo.Constraint

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
                (next_dispatch_window, first_timestamp_next_chrono_period), min_up_time_offset
            ),
        ] >= (
            sum(
                self.formulation_block.start_units[
                    modeled_year,
                    dispatch_window,
                    self.formulation_block.model()
                    .TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window]
                    .prevw(last_timestamp_chrono_period, t),
                ]
                for t in range(0, self.min_up_time - min_up_time_offset - 1)
            )
            + sum(
                self.formulation_block.start_units[
                    modeled_year,
                    next_dispatch_window,
                    self.formulation_block.model()
                    .TIMESTAMPS_IN_DISPATCH_WINDOWS[next_dispatch_window]
                    .nextw(first_timestamp_next_chrono_period, t),
                ]
                for t in range(0, min_up_time_offset + 1)
            )
        )

    def _min_downtime_inter_constraint(
        self, block, modeled_year: pd.Timestamp, chrono_period: pd.Timestamp, min_down_time_offset: int
    ):
        """
        Constrain minimum down time for unit commitment resources.

        operational_units[t] - committed_units[t] ≥ Σ Shutdown Units for t to t-min_down_time
        In this constraint, t = (modeled_year, dispatch_window for NEXT chrono_period, first timestamp of the 'next' dispatch window + min_down_time_offset.

        For example, if the min_down_time is 5 hours and the offset is 3 hours:
            - t = 3rd hour of the next chrono period
            - The constraint would need to sum the shutdown units for the last 2 hours of the current chrono period + the first 3 hours of the next chrono period

        Args:
            block: The block of the formulation.
            modeled_year (pd.Timestamp): Modeled year.
            chrono_period (pd.Timestamp): Chronological period.
            min_up_time_offset (int): Minimum up time offset.

        Returns: pyo.Constraint

        """
        (
            chrono_period_1_index,
            chrono_period_2_index,
        ) = self.formulation_block.model().return_timepoints_connecting_chrono_periods(modeled_year, chrono_period)
        _, dispatch_window, last_timestamp_chrono_period = chrono_period_1_index
        _, next_dispatch_window, first_timestamp_next_chrono_period = chrono_period_2_index
        return self.formulation_block.operational_units_in_timepoint[
            modeled_year,
            block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS.nextw(
                (next_dispatch_window, first_timestamp_next_chrono_period), min_down_time_offset
            ),
        ] - self.formulation_block.committed_units[
            modeled_year,
            block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS.nextw(
                (next_dispatch_window, first_timestamp_next_chrono_period), min_down_time_offset
            ),
        ] >= (
            sum(
                self.formulation_block.shutdown_units[
                    modeled_year,
                    dispatch_window,
                    self.formulation_block.model()
                    .TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window]
                    .prevw(last_timestamp_chrono_period, t),
                ]
                for t in range(0, self.min_down_time - min_down_time_offset - 1)
            )
            + sum(
                self.formulation_block.shutdown_units[
                    modeled_year,
                    next_dispatch_window,
                    self.formulation_block.model()
                    .TIMESTAMPS_IN_DISPATCH_WINDOWS[next_dispatch_window]
                    .nextw(first_timestamp_next_chrono_period, t),
                ]
                for t in range(0, min_down_time_offset + 1)
            )
        )

    def _start_cost_in_timepoint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Number of units started * the cost of starting a unit
        """
        return self.formulation_block.start_units[modeled_year, dispatch_window, timestamp] * self.start_cost

    def _shutdown_cost_in_timepoint(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Sum shutdown costs in timepoint.
        # of shutdown units * shutdown costs
        """
        return self.formulation_block.shutdown_units[modeled_year, dispatch_window, timestamp] * self.shutdown_cost

    def _annual_start_cost(self, block, modeled_year: pd.Timestamp):
        """
        Sum of all timepoint unit start costs in model year

        Args:
            block: pyomo Block
            modeled_year: Model year to sum

        Returns: Annual start costs

        """
        return block.model().sum_timepoint_component_slice_to_annual(block.start_cost_in_timepoint[modeled_year, :, :])

    def _annual_shutdown_cost(self, block, modeled_year: pd.Timestamp):
        """
        Sum of all timepoint unit shutdown costs in model year

        Args:
            block: pyomo Block
            modeled_year: Model year to sum

        Returns: Annual shutdown costs
        """
        return block.model().sum_timepoint_component_slice_to_annual(
            block.shutdown_cost_in_timepoint[modeled_year, :, :]
        )

    def _annual_start_and_shutdown_cost(self, block, modeled_year: pd.Timestamp):
        """
        Sum start and shutdown costs in model year
        """
        return block.annual_start_cost[modeled_year] + block.annual_shutdown_cost[modeled_year]

    def _annual_total_operational_cost(self, block, modeled_year: pd.Timestamp):
        """The total annual operational costs of the Resource. This term is not discounted (i.e. it is not
        multiplied by the discount factor for the relevant model year)."""
        total_operational_cost = (
            super()._annual_total_operational_cost(block, modeled_year)
            + block.annual_start_and_shutdown_cost[modeled_year]
        )

        return total_operational_cost

    def _dynamic_unit_size(self, block, modeled_year: pd.Timestamp):
        return block.operational_capacity[modeled_year]

    def _committed_capacity_ub(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Upper-bound constraint: committed capacity cannot exceed the product of
        maximum potential and the unit commitment indicator.

        - This constraint enforces that if the unit is not committed (committed_units = 0), then committed capacity is zero.
        - When committed, the capacity is limited by the resource's maximum potential.

        Returns: pyo.Constraint: committed_capacity <= max_potential * committed_units

        """
        return (
            block.committed_capacity[modeled_year, dispatch_window, timestamp]
            <= block.max_potential[modeled_year] * block.committed_units[modeled_year, dispatch_window, timestamp]
        )

    def _committed_capacity_unit_size_max(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Upper-bound constraint: committed capacity cannot exceed the unit size.

        This constraint enforces a physical limit: the committed capacity
        of a resource in any period cannot exceed the installed unit size
        available in that modeled year.

        Returns: pyomo.Constraint: committed_capacity <= unit_size
        """
        return block.committed_capacity[modeled_year, dispatch_window, timestamp] <= block.unit_size[modeled_year]

    def _committed_capacity_unit_size_min(
        self, block, modeled_year: pd.Timestamp, dispatch_window: pd.Timestamp, timestamp: pd.Timestamp
    ):
        """
        Lower-bound constraint: committed capacity must be at least the unit size
        when the resource is committed, and can relax to zero when not committed.

        - If committed_units = 1, the inequality reduces to:
            committed_capacity >= unit_size
          enforcing that the full unit size is available.
        - If committed_units = 0, the RHS relaxes to a large negative value,
          effectively removing the lower bound and allowing committed_capacity = 0.

        Returns: pyomo.Constraint: committed_capacity >= unit_size - max_potential * (1 - committed_units)
        """
        return block.committed_capacity[modeled_year, dispatch_window, timestamp] >= block.unit_size[
            modeled_year
        ] - block.max_potential[modeled_year] * (1 - block.committed_units[modeled_year, dispatch_window, timestamp])


class UnitCommitmentResourceGroup(GenericResourceGroup, UnitCommitmentResource):
    _NAME_PREFIX: ClassVar[str] = "unit_commitment_resource_group"
    _GROUPING_CLASS = UnitCommitmentResource

    @model_validator(mode="after")
    def check_potential_required(self):
        """
        Validate that a resource group using the 'single_unit' unit commitment mode
        specifies a valid cumulative potential.

        Validation logic
        ----------------
        - If `unit_commitment_mode` is `SINGLE_UNIT` and `cumulative_potential` is
          missing (`None`), raise a `ValueError`.
        - If `cumulative_potential` is provided as a `NumericTimeseries` but contains
          any infinite (`np.inf`) values, raise a `ValueError`.

        Returns
        -------
        self : UnitCommitmentResourceGroup
            The validated model instance if all checks pass.

        Raises
        ------
        ValueError
            If `unit_commitment_mode` is `SINGLE_UNIT` and `cumulative_potential` is
            either missing or contains invalid (infinite) values.

        Purpose
        -------
        Ensures that when modeling resource groups under the 'single_unit' commitment
        formulation, the `cumulative_potential` is always present and finite. This
        prevents infeasible or undefined model behavior during capacity commitment.
        """
        if self.unit_commitment_mode == UnitCommitmentMethod.SINGLE_UNIT and self.cumulative_potential == None:
            raise ValueError(
                f"Cumulative potential required for unit commitment resource group while in 'single_unit' unit commitment mode: {self.name}"
            )
        elif isinstance(self.cumulative_potential, ts.NumericTimeseries):
            if any(np.isinf(self.cumulative_potential.data.values)):
                raise ValueError(
                    f"Cumulative potential required for unit commitment resource group while in 'single_unit' unit commitment mode: {self.name}"
                )
        return self

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_investment_rules(model=model, construct_costs=construct_costs)
        if self.unit_commitment_mode == UnitCommitmentMethod.SINGLE_UNIT:
            pyomo_components.update(
                unit_size=pyo.Expression(model.MODELED_YEARS, rule=self._dynamic_unit_size, doc="Unit Size (MW)"),
                max_potential=pyo.Param(
                    model.MODELED_YEARS, initialize=self.cumulative_potential.data.loc[list(model.MODELED_YEARS)]
                ),
            )
        else:
            pyomo_components.update(
                unit_size=pyo.Param(model.MODELED_YEARS, initialize=self.unit_size, doc="Unit Size (MW)")
            )
        return pyomo_components
