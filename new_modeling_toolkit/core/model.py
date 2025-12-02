import calendar
import enum
import operator
import pathlib
from abc import ABC
from collections import OrderedDict
from typing import Any
from typing import Optional
from typing import Tuple
from typing import TYPE_CHECKING

import pandas as pd
import pyomo.environ as pyo
from loguru import logger
from pyomo.core.base.indexed_component_slice import IndexedComponent_slice
from pyomo.opt import SolverFactory
from pyomo.opt import TerminationCondition
from tqdm import tqdm

from new_modeling_toolkit.core.custom_model import ModelType
from new_modeling_toolkit.core.temporal.settings import DispatchWindowEdgeEffects
from new_modeling_toolkit.core.temporal.settings import TemporalSettings
from new_modeling_toolkit.core.utils.core_utils import timer
from new_modeling_toolkit.core.utils.pyomo_utils import get_index_labels

if TYPE_CHECKING:
    from new_modeling_toolkit.system import System


@enum.unique
class ConstraintOperator(enum.Enum):
    GREATER_THAN_OR_EQUAL_TO = operator.ge, ">=", "ge"
    LESS_THAN_OR_EQUAL_TO = operator.le, "<=", "le"
    EQUAL_TO = operator.eq, "==", "eq"

    def __new__(cls, _, *values):
        obj = object.__new__(cls)
        # first value is canonical value
        obj._value_ = values[0]
        for other_value in values[1:]:
            cls._value2member_map_[other_value] = obj
        obj._all_values = values
        return obj

    def __init__(self, operator, *args):
        self.operator = operator

    def __repr__(self):
        return f"<{self.__class__.__name__}.{self._name_}: {', '.join([repr(v) for v in self._all_values])}>"


# TODO (BKW 12/10/2024): Add an attribute here or on the system class to identify if the optimization is
#  electric-only, fuels-only, or mixed.
class ModelTemplate(pyo.ConcreteModel, ABC):
    """Can't make a child class that inherits both from Pydantic and Pyomo, so seems like this is all I can do for now."""

    TYPE: ModelType = ModelType.TEMPLATE

    def __init__(
        self,
        temporal_settings: TemporalSettings,
        system: "System",
        construct_investment_rules: bool,
        construct_operational_rules: bool,
        construct_costs: bool,
        solver_options: Optional[dict[str, dict[str, Any]]] = None,
        **kwargs,
    ):
        """Initialize and construct the model.

        Args:
            temporal_settings: TemporalSettings to use for the model
            system: the System to use for model construction
            construct_investment_rules: whether to construct investment rules for each component
            construct_operational_rules: whether to construct operational rules for each component
            construct_costs: whether to construct costs for each component
            solver_options: nested dictionary of {solver name: {solver option name: solver option value}}
                (e.g. {"gurobi": {"Crossover": 0}})
            **kwargs: additional keyword arguments for pyo.ConcreteModel
        """
        super().__init__(**kwargs)

        self.system = system
        self.temporal_settings = temporal_settings
        self.dispatch_window_edge_effects = temporal_settings.dispatch_window_edge_effects
        self.construct_investment_rules = construct_investment_rules
        self.construct_operational_rules = construct_operational_rules
        self.construct_costs = construct_costs
        self.solver_options = solver_options

        assert self.dispatch_window_edge_effects in [
            DispatchWindowEdgeEffects.LOOPBACK,
            DispatchWindowEdgeEffects.INTER_PERIOD_SHARING,
            DispatchWindowEdgeEffects.FIXED_INITIAL_CONDITION,
        ], f"State-of-charge tracking for specified edge effect type `{self.dispatch_window_edge_effects}` is not implemented."

        # Speed up model construction by creating SOME sets.
        self.MODELED_YEARS = pyo.Set(
            initialize=sorted(
                self.temporal_settings.modeled_years.data.loc[self.temporal_settings.modeled_years.data].index
            ),
            ordered=True,
        )

        self.DISPATCH_WINDOWS_AND_TIMESTAMPS = pyo.Set(
            initialize=self.temporal_settings.dispatch_windows_and_timestamps,
            ordered=True,
            doc=("DISPATCH_WINDOWS", "TIMESTAMPS"),
        )
        self.DISPATCH_WINDOWS = pyo.Set(initialize=self.temporal_settings.dispatch_windows, ordered=True)
        self.TIMESTAMPS = pyo.Set(
            initialize=self.temporal_settings.timestamps,
            ordered=True,
        )

        self.dispatch_window_weights = pyo.Param(
            self.DISPATCH_WINDOWS, initialize=self.temporal_settings.dispatch_window_weights.to_dict()
        )
        self.num_days_per_modeled_year = pyo.Param(
            self.MODELED_YEARS,
            initialize=lambda m, modeled_year: (
                366 if (calendar.isleap(modeled_year.year) and self.temporal_settings.include_leap_day) else 365
            ),
        )

        self.timestamp_durations_hours = pyo.Param(
            self.DISPATCH_WINDOWS_AND_TIMESTAMPS,
            initialize=self.temporal_settings.timestamp_duration_hours.to_dict(),
        )
        self.dispatch_window_duration_hours = pyo.Param(
            self.DISPATCH_WINDOWS,
            initialize=self.temporal_settings.timestamp_duration_hours.groupby("dispatch_window").sum().to_dict(),
        )

        self.TIMESTAMPS_IN_DISPATCH_WINDOWS = pyo.Set(
            self.DISPATCH_WINDOWS,
            ordered=True,
            initialize=lambda m, window: self.temporal_settings.dispatch_window_groups.get_group(
                window
            ).index.get_level_values(1),
            doc=("TIMESTAMPS", "DISPATCH_WINDOWS"),
        )

        self.WEATHER_YEARS = pyo.Set(
            initialize=self.temporal_settings.timestamps.to_period("Y").to_timestamp().unique(),
        )
        self.WEATHER_YEARS_IN_DISPATCH_WINDOWS = pyo.Set(
            self.DISPATCH_WINDOWS,
            initialize=lambda m, window: self.temporal_settings.dispatch_window_groups.get_group(window)
            .index.get_level_values(1)
            .to_period("Y")
            .to_timestamp()
            .unique(),
        )
        self.WEATHER_YEAR_TO_TIMESTAMPS_MAPPING = pyo.Set(
            self.WEATHER_YEARS,
            initialize=self.temporal_settings.dispatch_windows_map.index.to_series()
            .groupby(self.temporal_settings.timestamps.to_period("Y").to_timestamp())
            .groups,
        )
        self.DAYS = pyo.Set(initialize=self.temporal_settings.timestamps.to_period("D").to_timestamp().unique())
        self.DAYS_IN_DISPATCH_WINDOWS = pyo.Set(
            self.DISPATCH_WINDOWS,
            initialize=lambda m, window: self.temporal_settings.dispatch_window_groups.get_group(window)
            .index.get_level_values(1)
            .to_period("D")
            .to_timestamp()
            .unique(),
        )
        self.DAY_TO_TIMESTAMPS_MAPPING = pyo.Set(
            self.DAYS,
            initialize=self.temporal_settings.dispatch_windows_map.index.to_series()
            .groupby(self.temporal_settings.timestamps.to_period("D").to_timestamp())
            .groups,
        )

        self.RAMP_DURATIONS = pyo.Set(within=pyo.PositiveIntegers, initialize=[1, 2, 3, 4], ordered=True)

        self.PRODUCTS = pyo.Set(initialize=system.products.keys())

        if self.temporal_settings.weather_years_to_use is not None:
            # If user specified weather years for inter-period sharing or ERM dispatch, use those
            logger.info(
                "User-specified weather years will define chronological periods for inter-period sharing and ERM policies."
            )
            self.SELECT_WEATHER_YEARS = pyo.Set(
                initialize=sorted(
                    self.temporal_settings.weather_years_to_use.data.loc[
                        self.temporal_settings.weather_years_to_use.data
                    ].index
                ),
                ordered=True,
            )
        else:
            # Else, use all weather years
            self.SELECT_WEATHER_YEARS = pyo.Set(
                initialize=self.temporal_settings.timestamps.to_period("Y").to_timestamp().unique(),
            )
        select_weather_years = {timestamp.year for timestamp in self.SELECT_WEATHER_YEARS}
        if len(select_weather_years) == 0 and (
            self.dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
            or len(self.system.erm_policies) > 0
        ):
            raise ValueError(
                f"No weather years were selected for ERM or inter-period sharing optimization. You must "
                f"set at least one value to TRUE for the `weather_years_to_use` attribute in your temporal "
                f"settings."
            )
        if self.dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING:
            assert (
                self.temporal_settings.chrono_periods_map is not None
            ), "A chrono period to dispatch window mapping must be specified in order to use inter-period sharing."
            self.CHRONO_PERIODS = pyo.Set(
                ordered=True,
                initialize=[
                    chrono_period
                    for chrono_period in sorted(self.temporal_settings.chrono_periods_map.to_dict().keys())
                    if chrono_period.year in select_weather_years
                ],
            )
            self.chrono_periods_map = pyo.Param(
                self.CHRONO_PERIODS,
                within=pyo.Any,
                initialize=self.temporal_settings.chrono_periods_map.loc[self.CHRONO_PERIODS].to_dict(),
            )
            self.CHRONO_PERIODS_AND_TIMESTAMPS = pyo.Set(
                ordered=True,
                initialize=[
                    (chrono_period, timestamp)
                    for chrono_period in self.CHRONO_PERIODS
                    for timestamp in self.TIMESTAMPS_IN_DISPATCH_WINDOWS[self.chrono_periods_map[chrono_period]]
                ],
            )
            self.CHRONO_PERIODS_DISPATCH_WINDOWS_AND_TIMESTAMPS = pyo.Set(
                ordered=True,
                initialize=[
                    (chrono_period, timestamp.floor("D"), timestamp)  # chrono period, dispatch_window, timestamp
                    for chrono_period in self.CHRONO_PERIODS
                    for timestamp in self.TIMESTAMPS_IN_DISPATCH_WINDOWS[self.chrono_periods_map[chrono_period]]
                ],
            )
        else:
            self.CHRONO_PERIODS = pyo.Set(ordered=True, initialize=list(self.DISPATCH_WINDOWS))
            self.chrono_periods_map = pyo.Param(
                self.CHRONO_PERIODS,
                within=pyo.Any,
                initialize={dispatch_window: dispatch_window for dispatch_window in self.DISPATCH_WINDOWS},
            )
            self.CHRONO_PERIODS_AND_TIMESTAMPS = pyo.Set(
                ordered=True,
                initialize=list(self.DISPATCH_WINDOWS_AND_TIMESTAMPS),
                doc=("CHRONO_PERIODS", "TIMESTAMPS"),
            )

        # The following sets are of all hours within the selected weather years. Currently only used in ERM policies
        # When ERM and inter-period sharing are both used, WEATHER_PERIODS and CHRONO_PERIODS are the same set
        if self.temporal_settings.chrono_periods_map is not None:
            self.WEATHER_PERIODS = pyo.Set(
                ordered=True,
                initialize=[
                    chrono_period
                    for chrono_period in sorted(self.temporal_settings.chrono_periods_map.to_dict().keys())
                    if chrono_period.year in select_weather_years
                ],
            )
            self.weather_periods_map = pyo.Param(
                self.WEATHER_PERIODS,
                within=pyo.Any,
                initialize=self.temporal_settings.chrono_periods_map.loc[self.WEATHER_PERIODS].to_dict(),
            )
            self.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS = pyo.Set(
                ordered=True,
                initialize=[
                    (
                        weather_period,
                        timestamp.replace(year=weather_period.year, month=weather_period.month, day=weather_period.day),
                    )
                    for weather_period in self.WEATHER_PERIODS
                    if weather_period.year in select_weather_years
                    for timestamp in self.TIMESTAMPS_IN_DISPATCH_WINDOWS[self.weather_periods_map[weather_period]]
                ],
            )
            self.WEATHER_TIMESTAMPS = pyo.Set(
                ordered=True,
                initialize=[ts for _, ts in self.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS],
            )
            self.WEATHER_TIMESTAMPS_IN_WEATHER_PERIODS = pyo.Set(
                self.WEATHER_PERIODS,
                initialize=lambda model, weather_period: [
                    WEATHER_TIMESTAMP
                    for wp, WEATHER_TIMESTAMP in model.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS
                    if wp == weather_period
                ],
            )
        elif self.system.erm_policies:
            raise ValueError(
                f"A chrono period to dispatch window mapping must be specified in order to model Energy "
                f"Reserve Margin policies."
            )

        self.first_timepoint_in_dispatch_window = pyo.Param(
            self.DISPATCH_WINDOWS,
            within=pyo.Any,
            initialize={
                dispatch_window: min(self.TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window])
                for dispatch_window in self.DISPATCH_WINDOWS
            },
        )

        self.last_timepoint_in_dispatch_window = pyo.Param(
            self.DISPATCH_WINDOWS,
            within=pyo.Any,
            initialize={
                dispatch_window: max(self.TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window])
                for dispatch_window in self.DISPATCH_WINDOWS
            },
        )

        self.MONTHS = pyo.Set(initialize=self.temporal_settings.timestamps.to_period("M").to_timestamp().unique())
        self.MONTH_TO_TIMESTAMPS_MAPPING = pyo.Set(
            self.MONTHS,
            initialize=self.temporal_settings.dispatch_windows_map.index.to_series()
            .groupby(self.temporal_settings.timestamps.to_period("M").to_timestamp())
            .groups,
        )

        self.components_to_construct = OrderedDict(
            (
                (component.name, component)
                if not isinstance(component.name, tuple)
                else ("-".join(component.name), component)
            )
            for component in self.system._optimization_construction_order
        )
        for component_name, component in tqdm(
            self.components_to_construct.items(),
            desc=f"Constructing optimization blocks".rjust(50),
            bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
        ):
            logger.debug(f"Constructing block for `{component_name}`")

            # Check if operational rules should be skipped for the component (if it is in an operational group)
            construct_operational_rules = self.construct_operational_rules
            if hasattr(component, "operational_group"):
                construct_operational_rules = construct_operational_rules and component.operational_group is None

            setattr(
                self,
                component_name,
                component.construct_modeling_block(
                    self,
                    construct_investment_rules=construct_investment_rules,
                    construct_operational_rules=construct_operational_rules,
                    construct_costs=construct_costs,
                ),
            )

        # Construct Custom Constraints
        if system.three_way_linkages.get("CustomConstraintLinkage") is not None:
            for custom_constraint in system.three_way_linkages.get("CustomConstraintLinkage"):
                custom_constraint.validate_custom_constraint_linkage()
        else:
            logger.debug(f"No custom constraints for {system.name} system")

    @property
    def blocks(self) -> dict[str, pyo.Block]:
        return {block.name: block for block in self.component_objects(ctype=pyo.Block, descend_into=False)}

    @property
    def integer_variables_list(self) -> list[pyo.Var]:
        """
        Return a list of all integer or binary variable components
        """
        int_list = []
        for comp in list(self.component_objects(pyo.Var, active=True)):
            if comp.is_indexed() and len(comp) > 0:
                if comp[comp.index_set()[1]].domain in [pyo.NonNegativeIntegers, pyo.Binary]:
                    int_list.append(comp)
            else:
                for index in comp:
                    if comp[index].domain in [pyo.NonNegativeIntegers, pyo.Binary]:
                        int_list.append(comp)
        return int_list

    @property
    def contains_integer_variables(self) -> bool:
        """

        Returns: True if integer variables exist in the model

        """
        if len(self.integer_variables_list) > 0:
            return True
        else:
            return False

    def sum_timepoint_component_slice_to_annual(self, model_component_slice: IndexedComponent_slice):
        """Computes the "annual sum" using dispatch-window-weights of a slice of a modeling component that is indexed
        by DISPATCH_WINDOWS and TIMESTAMPS, among other things. For example, if the power output of a resource is
        defined as:

        block.power_output = pyo.Expression(model.MODELED_YEARS, model.DISPATCH_WINDOWS_AND_TIMESTAMPS, rule=_power_output_rule)

        Then the "total annual power output" as determined using dispatch-window-weights for the 2030 snapshot year can
        be calculated by doing

            sum_timepoint_component_slice_to_annual(block.power_output[2030, :, :])

        Args:
            model_component_slice: the slice of the component that should be summed

        Returns:
            annual_sum: an Expression of the weighted annual sum of the slice
        """
        index_set_names = get_index_labels(model_component=model_component_slice.parent_component()[0])
        modeled_year_pos = index_set_names.index(self.MODELED_YEARS.name)
        dispatch_window_pos = index_set_names.index(self.DISPATCH_WINDOWS.name)
        timestamp_pos = index_set_names.index(self.TIMESTAMPS.name)
        annual_sum = pyo.quicksum(
            map(
                lambda component: (
                    component
                    * self.dispatch_window_weights[component.index()[dispatch_window_pos]]
                    * self.num_days_per_modeled_year[component.index()[modeled_year_pos]]
                    * self.timestamp_durations_hours[
                        component.index()[dispatch_window_pos], component.index()[timestamp_pos]
                    ]
                ),
                model_component_slice,
            )
        )

        return annual_sum

    def return_timepoints_connecting_chrono_periods(
        self, modeled_year: pd.Timestamp, chrono_period: pd.Timestamp
    ) -> Tuple[Tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp], Tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
        """
        Return the dispatch window indexes that connect two chrono periods- last timepoint of dispatch_window[t] <-> first timepoint of dispatch_window[t+1]

        Args:
            modeled_year: pd.Timestamp of model year index
            chrono_period: pd.Timestamp of chrono_period[t] index

        Returns: chrono_period_1_index(modeled_year: pd.Timestamp, dispatch_window[t]: pd.Timestamp, last timepoint in dispatch_window[t]),
                chrono_period_2_index(modeled_year: pd.Timestamp, dispatch_window[t+1]: pd.Timestamp, first timepoint in dispatch_window[t+1])

        """
        dispatch_window = self.chrono_periods_map[chrono_period]
        next_chrono_period = self.CHRONO_PERIODS.nextw(chrono_period)
        next_dispatch_window = self.chrono_periods_map[next_chrono_period]

        last_timestamp_chrono_period = self.last_timepoint_in_dispatch_window[dispatch_window]

        first_timestamp_next_chrono_period = self.first_timepoint_in_dispatch_window[next_dispatch_window]

        chrono_period_1_index = (modeled_year, dispatch_window, last_timestamp_chrono_period)
        chrono_period_2_index = (modeled_year, next_dispatch_window, first_timestamp_next_chrono_period)
        return chrono_period_1_index, chrono_period_2_index

    def find_previous_chronological_dispatch_window_and_timepoint(
        self, chrono_period: pd.Timestamp, prior_offset: int
    ) -> Tuple[pd.Timestamp, pd.Timestamp]:
        chrono_period_dispatch_window = self.chrono_periods_map[chrono_period]
        first_tp_chrono_period = self.first_timepoint_in_dispatch_window[self.chrono_periods_map[chrono_period]]
        _, dispatch_window, timestamp = self.CHRONO_PERIODS_DISPATCH_WINDOWS_AND_TIMESTAMPS.prevw(
            (chrono_period, chrono_period_dispatch_window, first_tp_chrono_period), prior_offset
        )
        return dispatch_window, timestamp

    def find_next_chronological_dispatch_window_and_timepoint(
        self, chrono_period: pd.Timestamp, prior_offset: int
    ) -> Tuple[pd.Timestamp, pd.Timestamp]:
        chrono_period_dispatch_window = self.chrono_periods_map[chrono_period]
        first_tp_chrono_period = self.first_timepoint_in_dispatch_window[self.chrono_periods_map[chrono_period]]
        _, dispatch_window, timestamp = self.CHRONO_PERIODS_DISPATCH_WINDOWS_AND_TIMESTAMPS.nextw(
            (chrono_period, chrono_period_dispatch_window, first_tp_chrono_period), prior_offset
        )
        return dispatch_window, timestamp

    def export_temporal_settings(self, output_dir: pathlib.Path):
        self.temporal_settings.modeled_years.data.to_csv(output_dir.joinpath("modeled_years.csv"))
        self.temporal_settings.modeled_year_discount_factors.data.to_csv(
            output_dir.joinpath("modeled_year_discount_factors.csv")
        )
        self.temporal_settings.dispatch_windows_map.to_csv(output_dir.joinpath("dispatch_windows_map.csv"))
        if self.temporal_settings.chrono_periods_map is not None:
            self.temporal_settings.chrono_periods_map.to_csv(output_dir.joinpath("chrono_periods_map.csv"))
        self.temporal_settings.dispatch_window_weights.to_csv(output_dir.joinpath("dispatch_window_weights.csv"))
        pd.Series(
            data={
                "dollar_year": self.temporal_settings.dollar_year,
                "end_effect_years": self.temporal_settings.end_effect_years,
                "dispatch_window_edge_effects": self.temporal_settings.dispatch_window_edge_effects.value,
            },
            name="value",
        ).rename_axis("attribute").to_csv(output_dir.joinpath("attributes.csv"))

    def sum_weather_timestamp_component_slice_to_annual(self, model_component_slice: IndexedComponent_slice):
        """Computes the "annual sum" using a slice of a modeling component that is indexed
        by WEATHER_PERIODS and WEATHER_TIMESTAMPS. This works similarly to
        sum_timepoint_component_slice_to_annual, except there is no weighting by dispatch window.

        That is, the sum of a weather_timestamp-indexed variable is simply the average value multiplied by number of
        hours in the modeled year.

        Args:
            model_component_slice: the slice of the component that should be summed

        Returns:
            annual_sum: an Expression of the weighted annual sum of the slice
        """
        index_set_names = get_index_labels(model_component=model_component_slice.parent_component()[0])
        modeled_year_pos = index_set_names.index(self.MODELED_YEARS.name)
        modeled_year = model_component_slice.index()[0][modeled_year_pos]
        num_days_per_year = self.num_days_per_modeled_year[modeled_year]
        average_component_slice_value = sum(model_component_slice) / len(list(model_component_slice))

        return average_component_slice_value * 24 * num_days_per_year

    @timer
    def solve(
        self,
        output_dir: pathlib.Path,
        solver_name: str,
        keep_model_files: bool = False,
        symbolic_solver_labels: bool = False,
        solver_options: Optional[dict[str, Any]] = None,
    ):
        """Initialize specified solver, associated solver options & solve model.

        If the initial solution is infeasible, the model will be re-written and re-solved using symbolic solver labels
        and model formulation and infeasibility files will be generated (if the specified solver supports IIS
        computation).

        Args:
            output_dir: directory to save model formulation, solution, and infeasibility files
            solver_name: name of the solver to use
            keep_model_files: whether to keep model files and logs. If the
            symbolic_solver_labels: whether to use full Pyomo variable/expression/constraint names in the model formulation
                file. For large models, setting this to True may cause the model solution to be un-parsable.
            solver_options: optional solver options to add or override with those specified on the Model instance

        Returns:
            solution: the Pyomo solution object
        """
        solver = SolverFactory(solver_name)

        if symbolic_solver_labels:
            self.write(str(output_dir / "formulation.lp"), io_options=dict(symbolic_solver_labels=True))

        match solver_name:
            case "gurobi":
                solver.options["IISMethod"] = 0
                solver.options["ResultFile"] = str(output_dir / "infeasibility.ilp")
            case "amplxpress":
                solver.options["IIS"] = ""
                self.iis = pyo.Suffix(direction=pyo.Suffix.IMPORT)

        # Pull solver options from the Model instance and update with values from `solver_options` argument, if specified
        if self.solver_options is not None:
            all_solver_options = self.solver_options.get(solver_name, dict())
        else:
            all_solver_options = dict()
        if solver_options is not None:
            all_solver_options.update(solver_options)

        for option, value in all_solver_options.items():
            solver.options[option] = value

        # Start solver (which will write out LP file, then call solver executable)
        logger.info("Writing problem file & starting solver...")

        # Add a Suffix to the model so that dual values can be calculated
        # Note: if the model contains integer variables, the Suffix cannot be added until after the model has been
        #  solved with integer values fixed. See Pyomo documentation for more info about Suffix
        if not self.contains_integer_variables:
            self.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)

        # Solve the model with the specified solver
        solution = solver.solve(
            self, keepfiles=keep_model_files, tee=True, symbolic_solver_labels=symbolic_solver_labels
        )

        # Raise an appropriate error if the solver returned an infeasible solution
        if solution.solver.termination_condition == TerminationCondition.infeasible:
            # Re-solve the model using symbolic solver labels if the solver supports IIS computation to produce a more
            #  useful output for debugging
            if solver_name in {"gurobi", "cplex"} and not symbolic_solver_labels:
                if not keep_model_files:
                    logger.warning(
                        "Model was infeasible; re-solving model with `symbolic_solver_labels=True` to provide better "
                        "Irreducible Infeasible Set (IIS) information."
                    )
                    solver.solve(self, keepfiles=True, tee=True, symbolic_solver_labels=True)

                raise RuntimeError(
                    f"Model was infeasible; check ILP file for infeasible constraints "
                    f"{(output_dir / 'infeasibility.ilp').absolute()}"
                )

            elif solver_name == "amplxpress":
                raise RuntimeError(
                    "Solver identified the following constraints to be infeasible: \n"
                    + "\n  ".join(sorted(c.name for c in self.iis))
                )
            else:
                raise RuntimeError(
                    "Model was infeasible. Use CPLEX, Gurobi, or XPRESS (AMPL) to get better Irreducible Infeasible "
                    "Set (IIS) information."
                )

        # Fix all integer variable values to their current solution and re-solve the model
        if self.contains_integer_variables:
            for component in self.integer_variables_list:
                for idx in component:
                    component[idx].fix()

            solution = solver.solve(
                self, keepfiles=keep_model_files, tee=True, symbolic_solver_labels=symbolic_solver_labels
            )

        # Note: if dual isn't defined at least once, will cause an error in results reporting. But if its defined too
        # early when there are integer components, it will not solve
        if self.contains_integer_variables:
            self.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)

        return solution
