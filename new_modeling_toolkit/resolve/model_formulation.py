import ast
import calendar
import itertools
import os
from typing import Any
from typing import Dict
from typing import Optional
from typing import Union

import numpy as np
import pandas as pd
import pyomo.core
import pyomo.environ as pyo
import scipy.optimize
from loguru import logger
from pydantic import root_validator
from pydantic import validate_model
from tqdm import tqdm

from new_modeling_toolkit.common import system
from new_modeling_toolkit.common import temporal
from new_modeling_toolkit.common.asset.plant import ResourceCategory
from new_modeling_toolkit.core.component import Component
from new_modeling_toolkit.core.linkage import DeliverabilityStatus
from new_modeling_toolkit.core.linkage import IncrementalReserveType
from new_modeling_toolkit.core.linkage import Linkage
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.three_way_linkage import ThreeWayLinkage
from new_modeling_toolkit.core.utils import util
from new_modeling_toolkit.core.utils.core_utils import timer
from new_modeling_toolkit.core.utils.pandas_utils import convert_index_levels_to_datetime
from new_modeling_toolkit.core.utils.pyomo_utils import convert_pyomo_object_to_dataframe
from new_modeling_toolkit.core.utils.pyomo_utils import mark_pyomo_component
from new_modeling_toolkit.resolve import settings
from new_modeling_toolkit.common.system import LINKAGE_TYPES
from new_modeling_toolkit.common.system import THREE_WAY_LINKAGE_TYPES
from new_modeling_toolkit.system.policy import ConstraintOperator


# TODO (RG): Figure out how to align Pyomo's ureg with new_modeling_toolkit.ureg
# Initialize units for Pyomo's units
pyo.units.load_definitions_from_strings(["USD = [currency]"])


class ResolveCase(Component):
    system: system.System

    temporal_settings: temporal.TemporalSettings
    custom_constraints: dict[str, settings.CustomConstraints]
    dir_structure: util.DirStructure

    solver_options: dict[str, dict[str, Any]]

    model: Optional[pyomo.core.ConcreteModel] = None

    production_simulation_mode: bool = False
    portfolio_build_results_dir: Optional[str] = None

    ###############################
    # Validators                 #
    ###############################
    @root_validator(pre=True)
    def get_solver_options(cls, values):
        """Convert solver options in attributes.csv to a nested dictionary with correct data types.

        It seems like CBC requires options to be of the specified data type, whereas Gurobi does not.

        Returns:
            solver_options: Nested dictionary of {solver_name: {option: value}}
        """
        solver_options = {}

        for k, v in values.items():
            logger.debug(f"Parsing solver setting: {k}")
            if "solver." in k:
                _, solver_name, option, dtype = k.split(".")

                if "bool" in dtype.lower():
                    solver_options.update({solver_name: {option: ast.literal_eval(v)}})
                elif "int" in dtype.lower():
                    solver_options.update({solver_name: {option: int(float(v))}})
                elif "float" in dtype.lower():
                    solver_options.update({solver_name: {option: float(v)}})
                else:
                    solver_options.update({solver_name: {option: v}})

        values["solver_options"] = solver_options

        return values

    ###############################
    # INITIALIZATION METHODS      #
    ###############################

    def __init__(self, **kwargs):
        """
        Initialization of the resolve model includes both the regular read in of attributes, and also
        the configuration and instantiation of optimization components.
        """
        # Get settings information here and add into the list of key word arguments
        kwargs = self._get_settings(kwargs)

        # Initialize the resolve case based on the input and settings
        super().__init__(**kwargs)

        # Set planned installed capacity values equal to optimized capacity values from previous model run
        if self.production_simulation_mode:
            logger.info("Running production simulation mode")
            self._hourly_production_simulation()

        # Configure the model based on the settings. Currently only relate to finding rep periods.
        self._configure_model()

        # Construct pyomo model by sequentially initialize params, vars, constraints and objectives
        self._construct_model()

        # Create a dual suffix component so that we can print dual values
        self.model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)

    def _get_settings(self, kwargs):
        """Load settings from file into attribute instances.

        TODO (2022-01-03): These could probably be refactored into validators, which would allow the `ResolveCase`
        to be initialized by either passing the attribute instances (e.g., `ReportingSettings`) or the string name.
        This private method currently assumes the attributes must be loaded and are not passed to `__init__()`.
        """
        dir_str = kwargs["dir_structure"]

        if (dir_str.resolve_settings_dir / "scenarios.csv").is_file():
            logger.info(f"Reading scenario settings")
            scenarios = pd.read_csv(dir_str.resolve_settings_dir / "scenarios.csv")["scenarios"].tolist()
        else:
            scenarios = []

        logger.info(f"Reading data for System instance {kwargs['system']}")
        _, system_instance = system.System.from_csv(
            filename=dir_str.data_interim_dir / "systems" / kwargs["system"] / "attributes.csv",
            scenarios=scenarios,
            data={"dir_str": dir_str, "model_name": "resolve"},
        )
        kwargs["system"] = system_instance

        # read in representative days settings
        kwargs["temporal_settings"] = temporal.TemporalSettings.from_csv(
            dir_str.resolve_settings_rep_periods_dir / "attributes.csv", data={"dir_str": dir_str}
        )["attributes"]

        # read in custom constraints
        kwargs["custom_constraints"] = settings.CustomConstraints.from_dir(
            dir_str.resolve_settings_custom_constraints_dir
        )

        return kwargs

    def _configure_model(self):
        """
        initialize input data and system construct
        Returns:

        """
        # Calculate representative periods based on raw profile data
        _ = self.temporal_settings.find_representative_periods(self.system)

        # Drop FALSE years from `self.temporal_settings.modeled_years` and sort dataframe
        self.temporal_settings.modeled_years.data = self.temporal_settings.modeled_years.data[
            self.temporal_settings.modeled_years.data.values
        ].sort_index()

        if self.production_simulation_mode:
            self.temporal_settings.modeled_year_discount_factor.data = self.temporal_settings.modeled_year_discount_factor.data.reindex(
            self.temporal_settings.modeled_years.data.index)

        # Resample `System` instance timeseries attributes to modeled years
        weather_years = (
            self.temporal_settings.chrono_periods.melt()["value"].dt.year.min(),
            self.temporal_settings.chrono_periods.melt()["value"].dt.year.max(),
        )
        modeled_years = (
            self.temporal_settings.modeled_years.data.index.year.min(),
            self.temporal_settings.modeled_years.data.index.year.max(),
        )
        self.system.resample_ts_attributes(modeled_years, weather_years)

        # when inter period dynamics are turned off, only rep periods remain in the chrono periods set
        if not self.temporal_settings.allow_inter_period_dynamics.data.any():
            # turn each of the allow inter period sharing off
            logger.info("Turning off inter-period sharing (via `allow_inter_period_dynamics` temporal setting).")
            for p in self.system.plants.values():
                p.allow_inter_period_sharing = False

        # Warn that monthly energy budgets are not supported
        for r in self.system.resources.values():
            if r.monthly_budget is not None:
                logger.warning(
                    f"Monthly energy budgets not currently implemented in RESOLVE. As such, dispatch for {r.name} "
                    f"may differ from expectation."
                )

    ##########################################
    # HOURLY PRODUCTION SIMULATION FUNCTIONS  #
    ##########################################

    def _update_planned_capacity(self, prev_model_results_file: str, attribute: str, operational_capacity_units: str):
        """
        Called in production simulation mode, this function updates the planned capacities to those selected in the
         pre-defined model build.
        Args:
            prev_model_results_file: the path of the model build case on which planned capacities will be based
            attribute: the attribute to update: either planned_installed_capacity or planned_storage_capacity
            operational_capacity_units: the units of the planned capacity that is being updated

        Returns: a dictionary where each component in this component type is the key and the updated planned capacity is the value
        """
        # Retrieve operating capacity of this system component from previous run's results_summary
        filepath = (
            self.dir_structure.output_resolve_dir.parent.parent
            / self.portfolio_build_results_dir
            / "results_summary"
            / prev_model_results_file
        )
        component_summary = pd.read_csv(filepath)

        # Loop through components in component summary (first column)
        components = component_summary.iloc[:, 0].unique()  # resources in resource_summary, assets in assets_summary, etc.
        component_planned_installed_capacity_dict = {}
        for component in components:
            # get results for this component
            operational_capacity_column = "Operational Capacity " + operational_capacity_units
            operational_capacity_results = component_summary.loc[
                (component_summary.iloc[:, 0] == component), ["Model Year", operational_capacity_column]
            ]

            # change model year to datetimeindex, reset index
            operational_capacity_results["Model Year"] = pd.DatetimeIndex(
                pd.to_datetime(operational_capacity_results["Model Year"])
            )
            operational_capacity_results.set_index("Model Year", inplace=True)

            # update new planned installed capacity
            planned_installed_capacity_name = component + ":" + attribute
            new_planned_installed_capacity = operational_capacity_results[operational_capacity_column]
            component_planned_installed_capacity_dict[component] = ts.NumericTimeseries(
                name=planned_installed_capacity_name, data=new_planned_installed_capacity
            )

        return component_planned_installed_capacity_dict

    def _hourly_production_simulation(self):
        """
        For each component class with a planned_installed_capacity and planned_storage_capacity, this function calls
            updated_planned_capacity and sets the new planned capacities to the corresponding component dictionary
        """

        missing_components = set()

        # Iterate over relevant results summary files to read nameplate capacities of components
        for results_file, attribute, component_units, target_component_dict in [
            ("resource_summary.csv", "planned_installed_capacity", "(MW)", self.system.resources),
            ("resource_summary.csv", "planned_storage_capacity", "(MWh)", self.system.resources),
            ("asset_summary.csv", "planned_installed_capacity", "(MW)", self.system.generic_assets),
            ("electrolyzer_summary.csv", "planned_installed_capacity", "(MW)", self.system.electrolyzers),
            ("fuel_conversion_plant_summary.csv", "planned_installed_capacity", "(MMBtu/hr)", self.system.fuel_conversion_plants),
            ("fuel_storage_summary.csv", "planned_installed_capacity", "(MMBtu/hr)", self.system.fuel_storages),
            ("fuel_storage_summary.csv", "planned_storage_capacity", "(MMBtu)", self.system.fuel_storages),
            ("fuel_transportation_summary.csv", "planned_installed_capacity", "(MMBtu/hr)", self.system.fuel_transportations),
            ("transmission_summary.csv", "planned_installed_capacity", "(MW)", self.system.tx_paths)
        ]:
            # Read total operational capacity of component type
            planned_capacity_dict = self._update_planned_capacity(results_file, attribute, component_units)

            # Set planned capacity of existing components equal to the total operational capacity of the loaded results
            #  and disable any changes to the portfolio build
            # Note: the relevant components are replaced with copies that are modified using `update` argument because
            #  this skips Pydantic validation. Validations may fail within the loop because components are not fully
            #  updated until all results files have been read. Pydantic validation is manually re-run below.
            for component_name, new_planned_capacity in planned_capacity_dict.items():
                if component_name not in target_component_dict:
                    missing_components.add(component_name)
                else:
                    if component_name in missing_components:
                        missing_components.remove(component_name)

                    target_component_dict[component_name] = target_component_dict[component_name].copy(
                        update={attribute: new_planned_capacity, "can_retire": False, "can_build_new": False}
                    )

            # Check for any components which are present in the current system that were not in the previous system
            #  and disable their build decisions
            components_without_previous_results = set(planned_capacity_dict.keys()).difference(
                set(planned_capacity_dict.keys())
            )
            if len(components_without_previous_results) > 0:
                logger.warning(
                    f"The following Components did not have results in the specified RESOLVE run used to construct the "
                    f"production simulation porfolio: `{components_without_previous_results}`. Only the planned capacity"
                    f"for these Components will be used, and no build decisions will be allowed."
                )
                for component_name in components_without_previous_results:
                    target_component_dict[component_name].can_retire = False
                    target_component_dict[component_name].can_build_new = False

        if len(missing_components) > 0:
            logger.warning(
                f"The following Components were found in the loaded results files for production simulation, but were"
                f"not present in the current System: `{missing_components}`. They will not be included in the current"
                f"simulation."
            )

        # Re-announce the linkages to the new components
        self.system.linkages = self.system._construct_linkages(
            linkage_subclasses_to_load=LINKAGE_TYPES, linkage_type="linkages", linkage_cls=Linkage
        )
        self.system.three_way_linkages = self.system._construct_linkages(
            linkage_subclasses_to_load=THREE_WAY_LINKAGE_TYPES,
            linkage_type="three_way_linkages",
            linkage_cls=ThreeWayLinkage,
        )

        Linkage.announce_linkage_to_instances()

        # Re-run Pydantic validation on all components that were updated
        for component in self.system.assets.values():
            *_, validation_error = validate_model(component.__class__, component.__dict__)
            if validation_error:
                logger.error(
                    f"Validation error for Component `{component.name}` encountered after updating for "
                    f"production simulation"
                )
                raise validation_error


        # Update modeled year discount factors to match the desired capacity expansion case
        temporal_settings_filepath = (
                self.dir_structure.output_resolve_dir.parent.parent
                / self.portfolio_build_results_dir
                / "results_summary"
                / "temporal_settings_summary.csv"
        )
        previous_temporal_settings = pd.read_csv(temporal_settings_filepath, index_col=["Model Year"], parse_dates=["Model Year"])
        if len(previous_temporal_settings.loc[:, "Cost Dollar Year"].unique()) != 1:
            logger.warning(
                "Temporal settings from the capacity expansion run do not have a singular value for "
               "'cost dollar year' and will be ignored. Modeled year discount factors for this run may be"
               "different from the capacity expansion case."
            )
        else:
            # Check that the dollar years are the same between the two cases
            previous_cost_dollar_year = previous_temporal_settings.loc[:, "Cost Dollar Year"].unique()[0]
            if self.temporal_settings.cost_dollar_year is not None and previous_cost_dollar_year != self.temporal_settings.cost_dollar_year:
                logger.warning(
                    "The cost dollar used in the capacity expansion run is different from the current cost dollar year."
                    "New modeled year discount factors will be calculated for this run."
                )
            else:
                logger.info("Updating modeled year discount factors to match the capacity expansion run.")
                self.temporal_settings.annual_discount_rate = None
                self.temporal_settings.end_effect_years = None
                self.temporal_settings.modeled_year_discount_factor = ts.NumericTimeseries(
                    name="modeled_year_discount_factor",
                    data=previous_temporal_settings.loc[:, "Discount Factor"]
                )


    ###############################
    # HELPER METHODS & FUNCTIONS  #
    ###############################
    def sum_timepoint_to_annual(self, model_year, attribute, *args):
        """Aggregate timepoint-based values to annual level.
        Args are the indices of the attribute, which can have different lengths."""
        return sum(
            getattr(self.model, attribute)[args, model_year, rep_period, hour]
            * self.model.rep_period_weight[rep_period]
            * self.model.rep_periods_per_model_year[model_year]
            * self.temporal_settings.timesteps.at[hour]
            for hour in self.model.HOURS
            for rep_period in self.model.REP_PERIODS
        )

    def sum_timepoints_to_annual_all_years(self, attribute: str):
        if len(getattr(self.model, attribute)) == 0:
            annual_series = None
        else:
            attribute_series = convert_pyomo_object_to_dataframe(getattr(self.model, attribute)).squeeze(axis=1)
            rep_period_weights = convert_pyomo_object_to_dataframe(self.model.rep_period_weight).squeeze(axis=1)
            rep_periods_per_model_year = convert_pyomo_object_to_dataframe(self.model.rep_periods_per_model_year).iloc[
                :, 0
            ]
            timesteps = self.temporal_settings.timesteps
            timesteps.index.name = "HOURS"

            missing_index_levels = [
                set_name
                for set_name in [self.model.MODEL_YEARS.name, self.model.REP_PERIODS.name, self.model.HOURS.name]
                if set_name not in attribute_series.index.names
            ]
            if len(missing_index_levels) > 0:
                raise ValueError(f"Expected index sets not found for attribute `{attribute}`: `{missing_index_levels}`")

            weighted_attribute_series = attribute_series * timesteps * rep_period_weights * rep_periods_per_model_year

            grouping_levels = [
                level
                for level in weighted_attribute_series.index.names
                if level not in {self.model.REP_PERIODS.name, self.model.HOURS.name}
            ]
            annual_series = weighted_attribute_series.groupby(grouping_levels).sum()

        return annual_series

    def map_model_tp_to_rep_tp(self, model_tp):
        """
        Translate model year based timepoint into rep period based tuples


        Args:
            timepoint: pd.Timestamp. Timepoint expressed as a pandas Timestamp

        Returns: Value of the current TS at the queried (model year, period, hour)

        """

        model_year = model_tp.year

        # Each model year should be broadcast to multiple weather years with the same month and date
        weather_tps = [model_tp.replace(year=wy) for wy in self.all_weather_years]

        # Gather a list of all the representative period and hour indices
        rep_timepoints = []

        for weather_tp in weather_tps:
            chrono_period_idx, hour = np.where(self.chrono_periods == weather_tp)[0]
            rep_period_idx = self.temporal_settings.map_to_rep_periods.loc[chrono_period_idx]
            rep_timepoints.append([model_year, rep_period_idx, hour])

        return rep_timepoints

    def _get(self, attr: Any, default_val: Any = 0, slice_by: Optional[Union[tuple, int]] = None):
        """Helper method to get values from attributes in the System instance.

        Args:
            attr: Attribute to inspect (e.g., self.system.[attr] or self.system.component[component].attr)
            default_val: Default value to return if attribute is None on System instance.
            slice_by: Optional call to `slice_by_year` or `slice_by_timepoint` methods on timeseries attributes

        Returns:

        """
        # "Guard clause" to immediately return default value if attribute is None
        if attr is None:
            return default_val

        # Slice timeseries data if needed
        if slice_by is None:
            return attr
        elif slice_by in self.model.TIMEPOINTS:
            # TODO (RG): Does `slice_by_timepoint` really need `temporal_settings`?
            return attr.slice_by_timepoint(self.temporal_settings, *slice_by)
        elif slice_by in self.model.MODEL_YEARS:
            return attr.slice_by_year(slice_by)
        else:
            raise ValueError(
                f"Helper method '_get' argument 'slice_by' should be either None, or an index in MODEL_YEARS or TIMEPOINTS."
            )

    @timer
    def update_load_components(self):
        """The annual energy on the rep periods may not add up to 100% of the original 8760, so do a simple re-scaling."""
        self.unadjusted_hourly_loads = pd.DataFrame.from_dict({
            name: {
                (modeled_year, period, hour):
                    obj.scaled_profile_by_modeled_year[modeled_year].slice_by_timepoint(
                        self.temporal_settings,
                        modeled_year, period, hour
                    )
                for modeled_year in self.model.MODEL_YEARS
                for period in self.model.REP_PERIODS
                for hour in self.model.HOURS
            }
            for name, obj in self.system.loads.items()
            if obj.scale_by_energy
        })

        self.temporal_settings.rep_period_weights.name = "rep_period_weights"
        rep_period_weights_reindexed = pd.merge(
            self.unadjusted_hourly_loads,
            self.temporal_settings.rep_period_weights,
            left_on=self.unadjusted_hourly_loads.index.get_level_values(1),
            right_index=True,
        )["rep_period_weights"]
        load_scalars = (
                365 *
                self.unadjusted_hourly_loads.multiply(rep_period_weights_reindexed, axis=0)
        ).groupby(self.unadjusted_hourly_loads.index.get_level_values(0)).sum()
        load_scalars.index = pd.to_datetime(load_scalars.index, format="%Y")

        # Re-scale loads to make annual energy match

        for load in tqdm(
            load_scalars.columns,
            desc=f"Re-scaling load profiles:".ljust(48),
            bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
        ):
            load_scalars[load] = (
                self.system.loads[load].annual_energy_forecast.data[load_scalars.index]
                # .multiply(self.system.loads[load].td_losses_adjustment.data[load_scalars.index])
                .div(load_scalars[load]).fillna(0)
            )

            # Update loads
            self.system.loads[load].scaled_profile_by_modeled_year = {}
            for modeled_year in self.model.MODEL_YEARS:
                logger.debug(f"Re-scaling {load} so that sampled rep period annual energy matches energy forecast")
                self.system.loads[load].forecast_load(
                    modeled_years=(
                        self.temporal_settings.modeled_years.data.index.year.min(),
                        self.temporal_settings.modeled_years.data.index.year.max(),
                    ),
                    weather_years=(
                        self.temporal_settings.chrono_periods.melt()["value"].dt.year.min(),
                        self.temporal_settings.chrono_periods.melt()["value"].dt.year.max(),
                    ),
                    custom_scalars=load_scalars,
                )

        # Get re-scaled hourly loads (for results reporting)
        self.hourly_loads = pd.DataFrame.from_dict({
            name: {
                (modeled_year, period, hour):
                    obj.scaled_profile_by_modeled_year[modeled_year].slice_by_timepoint(
                        self.temporal_settings,
                        modeled_year, period, hour
                    )
                for modeled_year in self.model.MODEL_YEARS
                for period in self.model.REP_PERIODS
                for hour in self.model.HOURS
            }
            for name, obj in self.system.loads.items()
        })

    def get_sampled_profile_cf(self, profile: ts.Timeseries) -> float:
        sampled_profile = pd.Series({
            (period, hour):
                profile.slice_by_timepoint(
                    self.temporal_settings, self.model.MODEL_YEARS.first(), period, hour
                )
            for period in self.model.REP_PERIODS
            for hour in self.model.HOURS
        }).to_frame(name="value")

        # Join rep period weights
        self.temporal_settings.rep_period_weights.name = "rep_period_weights"
        rep_period_weights_reindexed = pd.merge(
            sampled_profile,
            self.temporal_settings.rep_period_weights,
            left_on=sampled_profile.index.get_level_values(0),
            right_index=True,
        )["rep_period_weights"]

        # Calculate CFs
        sampled_cf = (365 * sampled_profile.multiply(rep_period_weights_reindexed, axis=0)).sum().value / 8760
        return sampled_cf

    def test_profile_scaling(self, scalar, profile: ts.Timeseries, target_cf: float):
        test_profile = profile.copy(deep=True)

        scale_resource_profile(profile=test_profile, scalar=scalar)

        sampled_cf = self.get_sampled_profile_cf(test_profile)

        return sampled_cf - target_cf

    @timer
    def update_resource_profiles(self):
        """Really hacky adjustment to make sure sampled CF matches original (un-sampled) CF.

        Ideally want to parallelize this, but `self` is not picklable, so need to make this a static method instead of instance method.
        """
        hash_id = hash((self.system.name, tuple(self.system.scenarios), self.temporal_settings))
        logger.info(f"Looking for re-scaled profiles using ID {hash_id}")
        rescaled_profile_dir = self.dir_structure.data_processed_dir / "resolve" / "rescaled profiles" / f"{hash_id}"
        rescaled_profile_dir.mkdir(parents=True, exist_ok=True)

        for resource, obj in tqdm(
            self.system.resources.items(),
            desc="Re-scaling resource profiles:".ljust(48),
            bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
        ):
            # Only scale solar & wind profiles
            if not any(name in resource for name in ["Solar", "PV", "Wind"]):
                continue

            # If re-scaled profile already exists
            if (rescaled_profile_dir / f"{obj.name}.csv").exists():
                obj.provide_power_potential_profile.data = pd.read_csv(rescaled_profile_dir / f"{obj.name}.csv", parse_dates=True, infer_datetime_format=True, index_col=0).squeeze(axis=1)
                obj.provide_power_potential_profile._data_dict = None

                logger.info(
                    f"Reading {resource} re-scaled profile from {(rescaled_profile_dir / f'{obj.name}.csv')}"
                )

            else:
                # Get sampled CF
                original_sampled_cf = self.get_sampled_profile_cf(obj.provide_power_potential_profile)
                # Calculate target CF
                target_cf = obj.provide_power_potential_profile.data.mean()

                # Iterate using Newton method
                scalar = scipy.optimize.newton(
                    self.test_profile_scaling, 0, args=(obj.provide_power_potential_profile, target_cf), tol=0.004, maxiter=10, disp=False,
                )

                # Get final profile & CF
                scale_resource_profile(profile=obj.provide_power_potential_profile, scalar=scalar)
                final_cf = self.get_sampled_profile_cf(obj.provide_power_potential_profile)

                obj.provide_power_potential_profile.data.to_csv(rescaled_profile_dir / f"{obj.name}.csv", index=True)

                logger.info(f"Adjusted {resource} sampled profile capacity factor from {original_sampled_cf:.2%} to {final_cf:.2%} (target of {target_cf:.2%})")

    @timer
    def update_sampled_profiles(self):
        self.update_load_components()
        self.update_resource_profiles()

    ###########################
    # MAIN FORMULATION METHOD #
    ###########################
    @timer
    def _construct_model(self):
        """
        RESOLVE model formulation and components.

        Includes intialization, validation, and fomrulation methods.
        Returns:

        """
        self.model = pyo.ConcreteModel()

        ##################################################
        # HELPER FUNCTIONS FOR TEMPORAL MOVEMENT         #
        ##################################################

        def chrono_to_rep_mapping(chrono_period, model_year):
            """
            Maps chronological periods to a sequence of representative periods
            """
            if self.temporal_settings.allow_inter_period_dynamics.data.at[f"{model_year}-01-01"]:
                rep_period = self.temporal_settings.map_to_rep_periods.loc[chrono_period]
            else:
                rep_period = chrono_period

            return rep_period

        def get_next_chrono_period(chrono_period, model_year):
            """
            Returns next chronological period
            """
            if self.temporal_settings.allow_inter_period_dynamics.data.at[f"{model_year}-01-01"]:
                pos = self.temporal_settings.chrono_periods.index.get_loc(chrono_period)
                next_pos = np.mod(pos + 1, len(self.temporal_settings.chrono_periods))
                next_chrono_period = self.temporal_settings.chrono_periods.index[next_pos]
            else:
                pos = self.temporal_settings.rep_periods.index.get_loc(chrono_period)
                next_pos = np.mod(pos + 1, len(self.temporal_settings.rep_periods))
                next_chrono_period = self.temporal_settings.rep_periods.index[next_pos]

            return next_chrono_period

        def get_previous_chrono_period(chrono_period):
            """
            Returns previous chronological period
            """
            pos = self.temporal_settings.chrono_periods.index.get_loc(chrono_period)
            prev_pos = np.mod(pos - 1, len(self.temporal_settings.chrono_periods))

            return self.temporal_settings.chrono_periods.index[prev_pos]

        def get_next_rep_timepoint(model_year, rep_period, hour):
            """
            Define a "next timepoint" when given a timepoint defined on a representative day.
            The next timepoint for the last hour of a representative day is poorly defined, so we just use the
            first hour of the current day as a stand-in
            """

            if hour == max(self.model.HOURS):
                return (model_year, rep_period, min(self.model.HOURS))
            else:
                return (model_year, rep_period, hour + 1)

        def get_previous_rep_timepoint(model_year, rep_period, hour):
            """
            Define a "previous timepoint" when given a timepoint defined on a representative day.
            The previous timepoint for the first hour of a representative day is poorly defined, so we just use the
            last hour of the current day as a stand-in
            """

            if hour == min(self.model.HOURS):
                return (model_year, rep_period, max(self.model.HOURS))
            else:
                return (model_year, rep_period, hour - 1)

        def move_chrono_time_by_steps(model_year, chrono_period, hour, move_steps):
            """
            Either move forward or backward in chronological timepoint based on the step argument

            Returns: resulting time based on current time and step
            """
            # obtain current time based on the chronological records
            current_time = self.temporal_settings.chrono_periods.loc[chrono_period, hour]

            # convert tp information into step information for modulo operation
            first_chrono_tp = self.temporal_settings.chrono_periods.iloc[0, 0]
            total_chrono_steps = self.temporal_settings.chrono_periods.size
            current_time_step = (current_time - first_chrono_tp) // pd.Timedelta("1h")
            target_step = (current_time_step + move_steps) % total_chrono_steps

            # convert the target_step back into hours
            moved_period, moved_hour = np.where(
                first_chrono_tp + target_step * pd.Timedelta("1h") == self.temporal_settings.chrono_periods
            )[0]

            return model_year, moved_period, moved_hour

        # CONSTRUCT SETS AND PARAMETERS #
        ##################################################
        # TEMPORAL SETS AND PARAMETERS                   #
        ##################################################

        # create timepoints and years mapping based on input data
        self.model.MODEL_YEARS = pyo.Set(initialize=self.temporal_settings.modeled_years.data.index.year)
        self.model.REP_PERIODS = pyo.Set(initialize=self.temporal_settings.rep_periods.index)
        self.model.HOURS = pyo.Set(initialize=self.temporal_settings.rep_periods.columns)

        chrono_periods_by_model_year = {}
        adj_rep_periods_by_model_year = {}
        for model_year in self.temporal_settings.modeled_years.data.index:
            if self.temporal_settings.allow_inter_period_dynamics.data.loc[model_year]:
                chrono_periods_by_model_year[model_year.year] = self.temporal_settings.chrono_periods.index
                adj_rep_periods_by_model_year[model_year.year] = list(
                    set(
                        (
                            chrono_to_rep_mapping(chrono_period=chrono_period, model_year=model_year.year),
                            chrono_to_rep_mapping(
                                chrono_period=get_next_chrono_period(
                                    chrono_period=chrono_period, model_year=model_year.year
                                ),
                                model_year=model_year.year,
                            ),
                        )
                        for chrono_period in self.temporal_settings.chrono_periods.index
                    )
                )
            else:
                chrono_periods_by_model_year[model_year.year] = self.temporal_settings.rep_periods.index
                adj_rep_periods_by_model_year[model_year.year] = [
                    (rep_period, rep_period) for rep_period in self.model.REP_PERIODS
                ]

        self.model.MODEL_YEARS_AND_CHRONO_PERIODS = pyo.Set(
            initialize=[
                (model_year, chrono_period)
                for model_year, chrono_periods in chrono_periods_by_model_year.items()
                for chrono_period in chrono_periods
            ]
        )
        self.model.MODEL_YEARS_AND_ADJACENT_REP_PERIODS = pyo.Set(
            initialize=[
                (model_year, rep_period_1, rep_period_2)
                for model_year, adj_rep_periods in adj_rep_periods_by_model_year.items()
                for rep_period_1, rep_period_2 in adj_rep_periods
            ],
            doc="Unique set of adjacent rep periods (to implement ramp & adjacency constraints that cross rep "
            "periods but don't need full chronological tracking like SoC constraints)",
        )

        # Another hack: Get hourly sampled loads so that we can re-scale them
        self.update_sampled_profiles()

        self.model.TIMEPOINTS = pyo.Set(
            initialize=[
                (model_year, rep_period, hour)
                for model_year in self.model.MODEL_YEARS
                for rep_period in self.model.REP_PERIODS
                for hour in self.model.HOURS
            ]
        )

        self.model.VINTAGES = pyo.Set(domain=pyo.PositiveIntegers, initialize=self.model.MODEL_YEARS, ordered=True)

        self.model.first_year = pyo.Param(domain=pyo.PositiveIntegers, initialize=min(self.model.MODEL_YEARS))

        @self.model.Param(self.model.MODEL_YEARS, within=pyo.Any)
        def previous_year(model, year):
            if year == model.first_year:
                return None
            else:
                previous_years = []
                for q in model.MODEL_YEARS:
                    if q < year:
                        previous_years.append(q)

                return max(previous_years)

        @self.model.Param(self.model.MODEL_YEARS, self.model.REP_PERIODS, within=pyo.Any)
        def first_timepoint_of_period(model, year, rep_period):
            return (year, rep_period, min(model.HOURS))

        @self.model.Param(self.model.MODEL_YEARS, self.model.REP_PERIODS, within=pyo.Any)
        def last_timepoint_of_period(model, year, rep_period):
            return (year, rep_period, max(model.HOURS))

        # weight of the different representative periods. Adds up to one.
        self.model.rep_period_weight = pyo.Param(
            self.model.REP_PERIODS,
            within=pyo.NonNegativeReals,
            initialize=lambda model, rep_period: self.temporal_settings.rep_period_weights.loc[rep_period],
        )

        # The length of each representative period
        self.model.timepoints_per_period = pyo.Param(
            initialize=sum(self.temporal_settings.timesteps.astype(int)), within=pyo.PositiveIntegers
        )

        @self.model.Param(self.model.MODEL_YEARS, within=pyo.PositiveReals)
        def rep_periods_per_model_year(model, model_year):
            hours_per_year = 8784 if calendar.isleap(model_year) else 8760
            num_periods_model_year = hours_per_year / pyo.value(model.timepoints_per_period)
            return num_periods_model_year

        # Bound min up/down times for unit commitment to rep period length
        for name, r in self.system.resources.items():
            if r.min_up_time is not None and r.min_up_time > pyo.value(self.model.timepoints_per_period):
                logger.info(
                    f"Updating {name} minimum up time from {int(r.min_up_time)} to {int(pyo.value(self.model.timepoints_per_period))} (limited by representative period duration)."
                )
                r.min_up_time = min(pyo.value(self.model.timepoints_per_period), r.min_up_time)
            if r.min_down_time is not None and r.min_down_time > pyo.value(self.model.timepoints_per_period):
                logger.info(
                    f"Updating {name} minimum down time from {int(r.min_down_time)} to {int(pyo.value(self.model.timepoints_per_period))} (limited by representative period duration)."
                )
                r.min_down_time = min(pyo.value(self.model.timepoints_per_period), r.min_down_time)

        ##################################################
        # SPATIAL SETS AND PARAMETERS                    #
        ##################################################
        self.model.ZONES = pyo.Set(initialize=self.system.zones.keys())
        self.model.TRANSMISSION_LINES = pyo.Set(initialize=self.system.tx_paths.keys())
        self.model.transmission_from = pyo.Param(
            self.model.TRANSMISSION_LINES,
            within=self.model.ZONES,
            initialize=lambda model, tx_line: [
                zone
                for zone in self.system.tx_paths[tx_line].zones
                if self.system.tx_paths[tx_line].zones[zone].from_zone
            ][0],
        )
        self.model.transmission_to = pyo.Param(
            self.model.TRANSMISSION_LINES,
            within=self.model.ZONES,
            initialize=lambda model, tx_line: [
                zone
                for zone in self.system.tx_paths[tx_line].zones
                if self.system.tx_paths[tx_line].zones[zone].to_zone
            ][0],
        )

        self.model.FUEL_ZONES = pyo.Set(initialize=self.system.fuel_zones.keys())
        self.model.FUEL_TRANSPORTATIONS = pyo.Set(initialize=self.system.fuel_transportations.keys())
        self.model.fuel_transportation_from = pyo.Param(
            self.model.FUEL_TRANSPORTATIONS,
            within=self.model.FUEL_ZONES,
            initialize=lambda model, fuel_transportation: [
                zone
                for zone in self.system.fuel_transportations[fuel_transportation].fuel_zones
                if self.system.fuel_transportations[fuel_transportation].fuel_zones[zone].from_zone
            ][0],
        )
        self.model.fuel_transportation_to = pyo.Param(
            self.model.FUEL_TRANSPORTATIONS,
            within=self.model.FUEL_ZONES,
            initialize=lambda model, fuel_transportation: [
                zone
                for zone in self.system.fuel_transportations[fuel_transportation].fuel_zones
                if self.system.fuel_transportations[fuel_transportation].fuel_zones[zone].to_zone
            ][0],
        )

        ##################################################
        # LOAD & TX SETS AND PARAMETERS                  #
        ##################################################
        self.model.input_load_mw = pyo.Param(
            self.model.ZONES,
            self.model.TIMEPOINTS,
            units=pyo.units.MW,
            initialize=lambda model, zone, model_year, rep_period, hour: self.system.zones[zone].get_aggregated_load(
                self.temporal_settings, model_year, rep_period, hour
            ),
        )
        # TODO (RG): Is it necessary to pass `temporal_settings` to get the aggregated load?

        ########################################################
        # ASSET BUILD, RETIRE, AND COST SETS AND PARAMETERS    #
        ########################################################
        # generic resources, fuel resources, and plants
        self.model.RESOURCES = pyo.Set(initialize=self.system.resources.keys())
        self.model.FUEL_PRODUCTION_PLANTS = pyo.Set(initialize=self.system.fuel_production_plants.keys())
        self.model.FUEL_CONVERSION_PLANTS = pyo.Set(initialize=self.system.fuel_conversion_plants.keys())
        self.model.FUEL_STORAGES = pyo.Set(initialize=self.system.fuel_storages.keys())
        self.model.PLANTS = pyo.Set(initialize=self.system.plants.keys())
        self.model.ASSETS = pyo.Set(initialize=self.system.assets.keys())
        self.model.RAMP_ASSET = pyo.Set(
            initialize=sorted(
                set(
                    asset
                    for asset, item in self.system.assets.items()
                    if self.system.assets[asset].ramp_rate is not None
                )
            ),
            doc="assets to loop over",
        )
        self.model.RAMP_DURATIONS = pyo.Set(within=pyo.PositiveIntegers, initialize=[1, 2, 3, 4], ordered=True)

        # TODO: Remove these two subsets
        self.model.PLANTS_THAT_PROVIDE_POWER = pyo.Set(
            initialize=[
                plant for plant, item in self.system.plants.items() if item.provide_power_potential_profile is not None
            ]
        )

        self.model.PLANTS_THAT_INCREASE_LOAD = pyo.Set(
            initialize=[
                plant for plant, item in self.system.plants.items() if item.increase_load_potential_profile is not None
            ]
        )

        self.model.UNIT_COMMITMENT_RESOURCES = pyo.Set(
            initialize=[r for r, item in self.system.resources.items() if item.unit_commitment_linear]
        )

        ##############################################################
        # PLANT AND RESOURCE BUILD AND RETIRE SETS AND PARAMETERS    #
        ##############################################################

        # resources with storage related
        self.model.RESOURCES_WITH_STORAGE = pyo.Set(
            within=self.model.RESOURCES,
            initialize=[
                key for key, resource in self.system.resources.items() if resource.charging_efficiency is not None
            ],
        )

        # TODO (RG): Adjust duration for discharging efficiency (though that may be handled by SOC_Intra?
        @self.model.Param(
            self.model.RESOURCES_WITH_STORAGE,
            self.model.MODEL_YEARS,
            units=pyo.units.MWh,
            within=pyo.NonNegativeReals,
        )
        def planned_storage_capacity_mwh(model, resource, model_year):
            """
            Either defined by user input fixed duration, or planned storage MWh
            Args:
                model:
                resource:
                model_year:

            Returns:

            """
            if self.system.resources[resource].duration is not None:
                return (
                    self._get(self.system.resources[resource].planned_installed_capacity, slice_by=model_year)
                    * self.system.resources[resource].duration
                )
            elif self.system.resources[resource].planned_storage_capacity is not None:
                return self.system.resources[resource].planned_storage_capacity.slice_by_year(model_year)
            else:
                return 0

        ##################################################
        # OPERATING RESERVES SETS AND PARAMETERS         #
        ##################################################

        self.model.RESERVES = pyo.Set(initialize=self.system.reserves.keys())

        ##################################################
        # RESOURCE OPERATIONS PARAMETERS                 #
        ##################################################

        # Generic resources

        # TODO (RG): Make variable costs hourly (in system and then formulation can be updated)
        # TODO (RG): Deleted check that if provide_power_potential_profile < 0.0001, ignore (due to conflict with pint units). Should move to System or Param initialization.

        # storage related
        def apply_parasitic_loss(SOC, parasitic_loss, period_hrs):
            return SOC * (1 - parasitic_loss) ** period_hrs

        ##################################################
        # FUEL SETS AND PARAMETERS                       #
        ##################################################
        self.model.CANDIDATE_FUELS = pyo.Set(initialize=self.system.candidate_fuels.keys())
        self.model.FINAL_FUEL_DEMANDS = pyo.Set(initialize=self.system.final_fuels.keys())
        self.model.BIOMASS_RESOURCES = pyo.Set(initialize=self.system.biomass_resources.keys())
        # TODO: 2021-11-16: Related to #380, can simplify "if [linked] is not None else {}"
        self.model.RESOURCE_CANDIDATE_FUELS = pyo.Set(
            self.model.RESOURCES,
            initialize={
                resource_name: resource.candidate_fuels.keys() if resource.candidate_fuels is not None else {}
                for resource_name, resource in self.system.resources.items()
            },
        )
        self.model.FINAL_FUEL_DEMAND_CANDIDATE_FUELS = pyo.Set(
            self.model.FINAL_FUEL_DEMANDS,
            initialize={
                final_fuel_name: final_fuel.candidate_fuels.keys() if final_fuel.candidate_fuels is not None else {}
                for final_fuel_name, final_fuel in self.system.final_fuels.items()
            },
        )
        self.model.CANDIDATE_FUEL_BIOMASS_RESOURCES = pyo.Set(
            self.model.CANDIDATE_FUELS,
            initialize={
                candidate_fuel_name: candidate_fuel.biomass_resources.keys()
                if candidate_fuel.biomass_resources is not None
                else {}
                for candidate_fuel_name, candidate_fuel in self.system.candidate_fuels.items()
            },
        )
        self.model.CANDIDATE_FUEL_ELECTROFUEL_PLANTS = pyo.Set(
            self.model.CANDIDATE_FUELS,
            initialize={
                candidate_fuel_name: candidate_fuel.fuel_production_plants.keys()
                if candidate_fuel.fuel_production_plants is not None
                else {}
                for candidate_fuel_name, candidate_fuel in self.system.candidate_fuels.items()
            },
        )
        self.model.CANDIDATE_FUEL_ELECTROFUEL_STORAGES = pyo.Set(
            self.model.CANDIDATE_FUELS,
            initialize={
                candidate_fuel_name: candidate_fuel.fuel_storages.keys()
                if candidate_fuel.fuel_storages is not None
                else {}
                for candidate_fuel_name, candidate_fuel in self.system.candidate_fuels.items()
            },
        )
        self.model.CANDIDATE_FUEL_ELECTROFUEL_TRANSPORTATIONS = pyo.Set(
            self.model.CANDIDATE_FUELS,
            initialize={
                candidate_fuel_name: candidate_fuel.fuel_transportations.keys()
                if candidate_fuel.fuel_transportations is not None
                else {}
                for candidate_fuel_name, candidate_fuel in self.system.candidate_fuels.items()
            },
        )

        ##################################################
        # POLICY SETS AND PARAMETERS                     #
        ##################################################
        self.model.POLICY_TYPES = pyo.Set(initialize=["emissions", "energy", "prm"])
        self.model.POLICIES = pyo.Set(initialize=[policy for policy in self.system.policies.keys()])
        # TODO (2021-12-08): Could connect to the list of policy types used for common.policy.Policy validator
        self.model.POLICIES_BY_TYPE = pyo.Set(
            self.model.POLICY_TYPES,
            initialize={
                policy_type: [name for name, instance in self.system.policies.items() if instance.type == policy_type]
                for policy_type in self.model.POLICY_TYPES
            },
        )

        self.model.POLICY_FINAL_FUEL_DEMANDS = pyo.Set(
            self.model.POLICIES_BY_TYPE["emissions"],
            initialize={p: v.final_fuels.keys() for p, v in self.system.emissions_policies.items()},
        )

        # TODO (2022-04-22): Need to better organize/separate sets, vars, params
        self.model.Reliability_Capacity_In_Model_Year = pyo.Var(
            self.model.POLICIES_BY_TYPE["prm"],
            self.model.ASSETS,
            self.model.MODEL_YEARS,
            within=pyo.NonNegativeReals,
        )

        self.model.RESOURCE_CANDIDATE_FUELS_FOR_EMISSIONS_POLICY = pyo.Set(
            initialize=[
                (policy_name, resource_name, fuel)
                for policy_name, policy in self.system.emissions_policies.items()
                for resource_name, resource in policy.resources.items()
                for fuel in resource._instance_from.candidate_fuels.keys()
                if fuel in policy.candidate_fuels.keys() and policy.resources[resource_name].multiplier is None
            ],
            doc="Tuple of all applicable (emissions policy, resource, candidate fuel) combinations "
            "(e.g., resources under emissions policy that do not have a per-MWh emissions rate)",
        )

        # TODO (RG): Think about how to use units defined in attributes.csv file to initialize

        self.model.ELCC_SURFACE = pyo.Set(initialize=self.system.elcc_surfaces.keys())

        if len(self.model.ELCC_SURFACE) > 0:
            self.model.allow_elcc_surface = True

            self.model.FACETS = pyo.Set(
                initialize=sorted(
                    set(facet_name for elcc in self.system.elcc_surfaces.values() for facet_name in elcc.facets.keys())
                ),
                doc="Set of all facet names across all ELCC surfaces in system.",
            )

            self.model.ELCC_SURFACE_FACETS = pyo.Set(
                self.model.ELCC_SURFACE,
                initialize={
                    s: e.facets.keys() if e.facets is not None else {} for s, e in self.system.elcc_surfaces.items()
                },
                within=self.model.FACETS,
            )

            self.model.ELCC_MW = pyo.Var(
                self.model.MODEL_YEARS, self.model.ELCC_SURFACE, units=pyo.units.MW, within=pyo.NonNegativeReals
            )

        else:
            self.model.allow_elcc_surface = False

        ##################################################
        # CUSTOM CONSTRAINTS SETS AND PARAMETERS         #
        ##################################################
        self.model.CUSTOM_CONSTRAINTS = pyo.Set(initialize=self.custom_constraints.keys())

        # CONSTRUCT VARIABLES & EXPRESSIONS #
        ##################################################
        # BUILD AND RETIREMENT VARIABLES & EXPRESSIONS   #
        ##################################################

        self.model.Operational_Planned_Capacity_In_Model_Year = pyo.Var(
            self.model.ASSETS, self.model.MODEL_YEARS, units=pyo.units.MW, within=pyo.NonNegativeReals
        )

        # Cumulative capacity
        self.model.Operational_New_Capacity_By_Vintage_In_Model_Year = pyo.Var(
            self.model.ASSETS,
            self.model.VINTAGES,
            self.model.MODEL_YEARS,
            units=pyo.units.MW,
            within=pyo.NonNegativeReals,
        )

        @mark_pyomo_component
        @self.model.Expression(self.model.ASSETS, self.model.MODEL_YEARS)
        def Operational_New_Capacity_MW(model, asset, model_year):
            """Track how much capacity of each asset is operational in each year,
            including planned capacity, new builds, and retirements
            """
            operational_new_capacity = 0
            if self.system.assets[asset].can_build_new:
                for v in model.VINTAGES:
                    if v <= model_year:
                        operational_new_capacity += model.Operational_New_Capacity_By_Vintage_In_Model_Year[
                            asset, v, model_year
                        ]

            return operational_new_capacity

        @mark_pyomo_component
        @self.model.Expression(self.model.ASSETS, self.model.MODEL_YEARS)
        def Operational_Capacity_In_Model_Year(model, asset, model_year):
            """Track how much capacity of each asset is operational in each year,
            including planned capacity, new builds, and retirements
            """
            return (
                model.Operational_Planned_Capacity_In_Model_Year[asset, model_year]
                + model.Operational_New_Capacity_MW[asset, model_year]
            )

        self.model.ASSETS_WITH_TRANCHES = pyo.Set(initialize=[a for a, obj in self.system.assets.items() if obj.tranches])

        @mark_pyomo_component
        @self.model.Constraint(self.model.ASSETS_WITH_TRANCHES, self.model.MODEL_YEARS)
        def Constrain_Tranche_Operational_Capacity(model, asset, year):
            """Sum of tranche builds should exactly match the aggregate asset build."""
            return (
                sum(model.Operational_Capacity_In_Model_Year[tranche, year] for tranche in self.system.assets[asset].tranches)
                ==
                model.Operational_Capacity_In_Model_Year[asset, year]
            )

        self.model.ASSET_GROUPS = pyo.Set(initialize=self.system.asset_groups.keys())
        @mark_pyomo_component
        @self.model.Constraint(self.model.ASSET_GROUPS, self.model.MODEL_YEARS)
        def Constrain_Asset_Group_Operational_Capacity(model, group, year):
            """Sum of tranche builds should exactly match the aggregate asset build."""
            return (
                sum(model.Operational_Capacity_In_Model_Year[asset, year] for asset in self.system.asset_groups[group].assets)
                ==
                model.Operational_Capacity_In_Model_Year[group, year]
            )

        self.model.Operational_Planned_Storage_In_Model_Year = pyo.Var(
            self.model.RESOURCES_WITH_STORAGE,
            self.model.MODEL_YEARS,
            units=pyo.units.MWh,
            within=pyo.NonNegativeReals,
        )

        # Cumulative capacity
        self.model.Operational_New_Storage_By_Vintage_In_Model_Year = pyo.Var(
            self.model.RESOURCES_WITH_STORAGE,
            self.model.VINTAGES,
            self.model.MODEL_YEARS,
            units=pyo.units.MWh,
            within=pyo.NonNegativeReals,
        )

        @mark_pyomo_component
        @self.model.Expression(self.model.RESOURCES_WITH_STORAGE, self.model.MODEL_YEARS)
        def Operational_Storage_In_Model_Year(model, resource, model_year):
            """Track how much storage capacity of each resource with storage is operational in each year,
            including planned, new builds, and retirements
            Args:
                model:
                resource:
                model_year:

            Returns:

            """
            operational_new_storage = 0
            if self.system.resources[resource].can_build_new:
                for v in model.VINTAGES:
                    if v <= model_year:
                        operational_new_storage += model.Operational_New_Storage_By_Vintage_In_Model_Year[
                            resource, v, model_year
                        ]

            return model.Operational_Planned_Storage_In_Model_Year[resource, model_year] + operational_new_storage

        ####################################################
        # OPERATING RESERVE VARIABLES & EXPRESSIONS        #
        ####################################################

        self.model.Provide_Reserve_MW = pyo.Var(
            self.model.RESOURCES,
            self.model.RESERVES,
            self.model.TIMEPOINTS,
            units=pyo.units.MW,
            within=pyo.NonNegativeReals,
        )

        @mark_pyomo_component
        @self.model.Expression(self.model.RESOURCES, self.model.TIMEPOINTS)
        def Total_Up_Reserves_By_Resource_By_Timepoint(model, resource, model_year, rep_period, hour):
            total_up_reserves = 0
            if self.system.resources[resource].reserves is not None:
                for reserve in self.system.resources[resource].reserves:
                    reserve_instance = self.system.reserves[reserve]
                    if reserve_instance.direction == "up":
                        total_up_reserves += model.Provide_Reserve_MW[resource, reserve, model_year, rep_period, hour]

            return total_up_reserves

        @mark_pyomo_component
        @self.model.Expression(self.model.RESOURCES, self.model.TIMEPOINTS)
        def Total_Down_Reserves_By_Resource_By_Timepoint(model, resource, model_year, rep_period, hour):
            total_down_reserves = 0
            if self.system.resources[resource].reserves is not None:
                for reserve in self.system.resources[resource].reserves.keys():
                    reserve_instance = self.system.reserves[reserve]
                    if reserve_instance.direction == "down":
                        total_down_reserves += model.Provide_Reserve_MW[resource, reserve, model_year, rep_period, hour]

            return total_down_reserves

        # TODO (BKW 2-20-2023): REPEAT FOR ELECTROFUEL STORAGE RESOURCES
        # CONSTRUCT VARIABLES & EXPRESSIONS #
        ####################################################################
        # ELECTROFUEL STORAGE BUILD AND RETIREMENT VARIABLES & EXPRESSIONS #
        ####################################################################

        # TODO : @SamKramer, I've implemented some variables as a means to modeling fuel storage
        # TODO: Note that the units of these resources are in MMBTU/hr
        # Should make sure to model to have two independent components (MW and MWh ratings for battery equivalent)
        # Do we want to replicate this for fuel storage?
        # If so, also need the volumetric capacities in MMBTU.
        self.model.Operational_Planned_Fuel_Storage_Capacity_In_Model_Year = pyo.Var(
            self.model.FUEL_STORAGES,
            self.model.MODEL_YEARS,
            units=pyo.units.MBtu / pyo.units.h,
            within=pyo.NonNegativeReals,
        )

        # Cumulative capacity
        self.model.Operational_New_Fuel_Storage_Capacity_By_Vintage_In_Model_Year = pyo.Var(
            self.model.FUEL_STORAGES,
            self.model.VINTAGES,
            self.model.MODEL_YEARS,
            units=pyo.units.MBtu / pyo.units.h,
            within=pyo.NonNegativeReals,
        )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_STORAGES, self.model.MODEL_YEARS)
        def Operational_New_Fuel_Storage_Capacity_MMBTU_H(model, fuel_storage, model_year):
            """Track how much capacity of each asset is operational in each year,
            including planned capacity, new builds, and retirements
            """
            operational_new_capacity = 0
            if self.system.assets[fuel_storage].can_build_new:
                for v in model.VINTAGES:
                    if v <= model_year:
                        operational_new_capacity += model.Operational_New_Capacity_By_Vintage_In_Model_Year[
                            fuel_storage, v, model_year
                        ]

            return operational_new_capacity

        self.model.Operational_Planned_Fuel_Storage_Volume_In_Model_Year = pyo.Var(
            self.model.FUEL_STORAGES,
            self.model.MODEL_YEARS,
            units=pyo.units.MBtu,
            within=pyo.NonNegativeReals,
        )

        # Cumulative capacity
        self.model.Operational_New_Fuel_Storage_Volume_By_Vintage_In_Model_Year = pyo.Var(
            self.model.FUEL_STORAGES,
            self.model.VINTAGES,
            self.model.MODEL_YEARS,
            units=pyo.units.MBtu,
            within=pyo.NonNegativeReals,
        )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_STORAGES, self.model.MODEL_YEARS)
        def Operational_New_Fuel_Storage_Volume_In_Model_Year(model, fuel_storage, model_year):
            operational_new_storage = 0
            if self.system.assets[fuel_storage].can_build_new:
                for v in model.VINTAGES:
                    if v <= model_year:
                        operational_new_storage += model.Operational_New_Fuel_Storage_Volume_By_Vintage_In_Model_Year[
                            fuel_storage, v, model_year
                        ]

            return operational_new_storage

        # TODO: (BKW 2/21/2023) We should think of different names for flow rate and capacity names for storage and fuel storage resources
        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_STORAGES, self.model.MODEL_YEARS)
        def Operational_Fuel_Storage_Volume_In_Model_Year(model, fuel_storage, model_year):
            """Track how much storage capacity of each resource with storage is operational in each year,
            including planned, new builds, and retirements
            Args:
                model:
                resource:
                model_year:

            Returns:

            """

            return (
                model.Operational_Planned_Fuel_Storage_Volume_In_Model_Year[fuel_storage, model_year]
                + model.Operational_New_Fuel_Storage_Volume_In_Model_Year[fuel_storage, model_year]
            )

        ####################################################
        # RESOURCE UC AND DISPATCH VARIABLES & EXPRESSIONS #
        ####################################################
        self.model.Provide_Power_MW = pyo.Var(
            self.model.PLANTS_THAT_PROVIDE_POWER,
            self.model.TIMEPOINTS,
            units=pyo.units.MW,
            within=pyo.NonNegativeReals,
        )
        self.model.Increase_Load_MW = pyo.Var(
            self.model.PLANTS_THAT_INCREASE_LOAD,
            self.model.TIMEPOINTS,
            units=pyo.units.MW,
            within=pyo.NonNegativeReals,
        )

        self.model.SOC_Intra_Period = pyo.Var(
            self.model.RESOURCES_WITH_STORAGE,
            self.model.TIMEPOINTS,
            units=pyo.units.MWh,
            within=pyo.Reals,
        )
        self.model.SOC_Inter_Period = pyo.Var(
            self.model.RESOURCES_WITH_STORAGE,
            self.model.MODEL_YEARS_AND_CHRONO_PERIODS,
            units=pyo.units.MWh,
            within=pyo.NonNegativeReals,
        )

        # Needed to add these vars in the case of fuel storage resources, as they can increase load on charging
        # and discharging.
        self.model.Fuel_Storage_Charging_MMBtu_per_Hr = pyo.Var(
            self.model.FUEL_STORAGES,
            self.model.TIMEPOINTS,
            units=pyo.units.MW,
            within=pyo.NonNegativeReals,
        )
        self.model.Fuel_Storage_Discharging_MMBtu_per_Hr = pyo.Var(
            self.model.FUEL_STORAGES,
            self.model.TIMEPOINTS,
            units=pyo.units.MW,
            within=pyo.NonNegativeReals,
        )

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_STORAGES, self.model.TIMEPOINTS)
        def Fuel_Storage_Charging_Max_Constraint(model, fuel_storage, model_year, rep_period, hour):
            return self.system.fuel_storages[fuel_storage].Fuel_Storage_Charging_Max_Constraint(
                model=model, model_year=model_year, rep_period=rep_period, hour=hour
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_STORAGES, self.model.TIMEPOINTS)
        def Fuel_Storage_Discharging_Max_Constraint(model, fuel_storage, model_year, rep_period, hour):
            return self.system.fuel_storages[fuel_storage].Fuel_Storage_Discharging_Max_Constraint(
                model=model, model_year=model_year, rep_period=rep_period, hour=hour
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_STORAGES, self.model.TIMEPOINTS)
        def Increase_Load_For_Charging_Fuel_Storage_MW(model, fuel_storage, model_year, rep_period, hour):
            return self.system.fuel_storages[fuel_storage].Increase_Load_For_Charging_Fuel_Storage_MW(
                model=model, model_year=model_year, rep_period=rep_period, hour=hour
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_STORAGES, self.model.TIMEPOINTS)
        def Increase_Load_For_Discharging_Fuel_Storage_MW(model, fuel_storage, model_year, rep_period, hour):
            return self.system.fuel_storages[fuel_storage].Increase_Load_For_Discharging_Fuel_Storage_MW(
                model=model, model_year=model_year, rep_period=rep_period, hour=hour
            )

        self.model.Fuel_Storage_SOC_Intra_Period = pyo.Var(
            self.model.FUEL_STORAGES,
            self.model.TIMEPOINTS,
            units=pyo.units.MBtu,
            within=pyo.Reals,
        )
        self.model.Fuel_Storage_SOC_Inter_Period = pyo.Var(
            self.model.FUEL_STORAGES,
            self.model.MODEL_YEARS_AND_CHRONO_PERIODS,
            units=pyo.units.MBtu,
            within=pyo.NonNegativeReals,
        )

        # Linear unit commitment variables

        self.model.Start_Units = pyo.Var(
            self.model.UNIT_COMMITMENT_RESOURCES, self.model.TIMEPOINTS, within=pyo.NonNegativeReals
        )

        self.model.Shutdown_Units = pyo.Var(
            self.model.UNIT_COMMITMENT_RESOURCES, self.model.TIMEPOINTS, within=pyo.NonNegativeReals
        )

        self.model.Committed_Units = pyo.Var(
            self.model.UNIT_COMMITMENT_RESOURCES, self.model.TIMEPOINTS, within=pyo.NonNegativeReals
        )

        self.model.Operational_Units_In_Timepoint = pyo.Expression(
            self.model.UNIT_COMMITMENT_RESOURCES,
            self.model.TIMEPOINTS,
            rule=lambda m, r, model_year, rep_period, hour: (
                m.Operational_Capacity_In_Model_Year[r, model_year]
                / self._get(self.system.resources[r].unit_size_mw)
                * self._get(
                    self.system.resources[r].provide_power_potential_profile, slice_by=(model_year, rep_period, hour)
                )
            ),
        )

        self.model.Committed_Capacity_MW = pyo.Expression(
            self.model.UNIT_COMMITMENT_RESOURCES,
            self.model.TIMEPOINTS,
            rule=lambda m, r, model_year, rep_period, hour: m.Committed_Units[r, model_year, rep_period, hour]
            * self._get(self.system.resources[r].unit_size_mw),
        )

        @mark_pyomo_component
        @self.model.Expression(self.model.PLANTS_THAT_INCREASE_LOAD, self.model.TIMEPOINTS)
        def Plant_Increase_Load_Capacity_In_Timepoint_MW(model, plant, model_year, rep_period, hour):
            """Derate hourly operational (or committed) capacity by `increase_load_potential_profile`."""
            if plant in model.UNIT_COMMITMENT_RESOURCES:
                capacity = model.Committed_Capacity_MW[plant, model_year, rep_period, hour]
            else:
                capacity = model.Operational_Capacity_In_Model_Year[plant, model_year] * self._get(
                    self.system.plants[plant].increase_load_potential_profile, slice_by=(model_year, rep_period, hour)
                )
            return capacity

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_STORAGES, self.model.TIMEPOINTS)
        def Fuel_Storage_Consumption_Increase_Load_Capacity_In_Timepoint_MW(
            model, fuel_storage, model_year, rep_period, hour
        ):
            return self.system.fuel_storages[
                fuel_storage
            ].Fuel_Storage_Consumption_Increase_Load_Capacity_In_Timepoint_MW(
                model, self.temporal_settings, model_year, rep_period, hour
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_STORAGES, self.model.TIMEPOINTS)
        def Fuel_Storage_Production_Increase_Load_Capacity_In_Timepoint_MW(
            model, fuel_storage, model_year, rep_period, hour
        ):
            return self.system.fuel_storages[
                fuel_storage
            ].Fuel_Storage_Production_Increase_Load_Capacity_In_Timepoint_MW(
                model, self.temporal_settings, model_year, rep_period, hour
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.PLANTS_THAT_PROVIDE_POWER, self.model.TIMEPOINTS)
        def Plant_Provide_Power_Capacity_In_Timepoint_MW(model, plant, model_year, rep_period, hour):
            """Derate hourly operational (or committed) capacity by `provide_power_potential_profile`."""
            if plant in model.UNIT_COMMITMENT_RESOURCES:
                capacity = model.Committed_Capacity_MW[plant, model_year, rep_period, hour]
            else:
                capacity = model.Operational_Capacity_In_Model_Year[plant, model_year] * self._get(
                    self.system.plants[plant].provide_power_potential_profile, slice_by=(model_year, rep_period, hour)
                )
            return capacity

        @mark_pyomo_component
        @self.model.Expression(self.model.PLANTS_THAT_PROVIDE_POWER, self.model.TIMEPOINTS)
        def Plant_Power_Min_Capacity_In_Timepoint_MW(model, plant, model_year, rep_period, hour):
            """Allow user to set a lower bound on hourly generation.

            Note that there is a separate Pmin constraint for unit commitment resources
            """
            return (
                self._get(self.system.plants[plant].provide_power_min_profile, slice_by=(model_year, rep_period, hour)) *
                model.Operational_Capacity_In_Model_Year[plant, model_year]
            )

        self.model.CURTAILABLE_RESOURCES = pyo.Set(
            initialize=[r for r, item in self.system.resources.items() if item.curtailable],
            doc="All resources that are 'curtailable' (i.e., can produce less energy than ``provide_power_potential_profile``.",
        )
        self.model.CURTAILABLE_VARIABLE_RESOURCES = pyo.Set(
            initialize=[
                r for r, item in self.system.resources.items() if item.curtailable and item.category == ResourceCategory.VARIABLE
            ],
            doc="Curtailment is only reported for variable and hydro resources.",
        )

        @mark_pyomo_component
        @self.model.Expression(self.model.CURTAILABLE_RESOURCES, self.model.TIMEPOINTS)
        def Scheduled_Curtailment_MW(model, resource, model_year, rep_period, hour):
            """Curtailment for variable & hydro resources."""
            if resource in model.CURTAILABLE_VARIABLE_RESOURCES:
                return (
                    model.Plant_Provide_Power_Capacity_In_Timepoint_MW[resource, model_year, rep_period, hour]
                    - model.Provide_Power_MW[resource, model_year, rep_period, hour]
                )
            else:
                return 0.0

        ##################################################
        # ZONAL BALANCE                                  #
        ##################################################
        @mark_pyomo_component
        @self.model.Expression(self.model.ZONES, self.model.TIMEPOINTS)
        def Zonal_Provide_Power_MW(model, zone, model_year, rep_period, hour):
            """Sum of all `Provide_Power_MW` in a given zone."""
            return sum(
                model.Provide_Power_MW[plant, model_year, rep_period, hour]
                for plant in model.PLANTS_THAT_PROVIDE_POWER
                if zone in self.system.plants[plant].zones.keys()
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.ZONES, self.model.TIMEPOINTS)
        def Zonal_Increase_Load_MW(model, zone, model_year, rep_period, hour):
            """Sum of all `Increase_Load_MW` in a given zone."""
            return sum(
                model.Increase_Load_MW[plant, model_year, rep_period, hour]
                for plant in model.PLANTS_THAT_INCREASE_LOAD
                if zone in self.system.plants[plant].zones.keys()
            )

        self.model.Transmit_Power_MW = pyo.Var(
            self.model.TRANSMISSION_LINES, self.model.TIMEPOINTS, units=pyo.units.MW, within=pyo.Reals
        )
        self.model.Transmit_Power_Forward_MW = pyo.Var(
            self.model.TRANSMISSION_LINES,
            self.model.TIMEPOINTS,
            units=pyo.units.MW,
            within=pyo.NonNegativeReals,
        )
        self.model.Transmit_Power_Reverse_MW = pyo.Var(
            self.model.TRANSMISSION_LINES,
            self.model.TIMEPOINTS,
            units=pyo.units.MW,
            within=pyo.NonNegativeReals,
        )
        self.model.Transmit_Candidate_Fuel_MMBTU_H = pyo.Var(
            self.model.FUEL_TRANSPORTATIONS,
            self.model.TIMEPOINTS,
            units=pyo.units.MBtu / pyo.units.H,
            within=pyo.NonNegativeReals,
        )
        self.model.Transmit_Candidate_Fuel_Forward_MMBTU_H = pyo.Var(
            self.model.FUEL_TRANSPORTATIONS,
            self.model.TIMEPOINTS,
            units=pyo.units.MBtu / pyo.units.H,
            within=pyo.NonNegativeReals,
        )
        self.model.Transmit_Candidate_Fuel_Reverse_MMBTU_H = pyo.Var(
            self.model.FUEL_TRANSPORTATIONS,
            self.model.TIMEPOINTS,
            units=pyo.units.MBtu / pyo.units.H,
            within=pyo.NonNegativeReals,
        )
        # Slack variables
        ## Zonal slack variables
        self.model.Unserved_Energy_MW = pyo.Var(
            self.model.ZONES,
            self.model.TIMEPOINTS,
            units=pyo.units.MWh,
            within=pyo.NonNegativeReals,
        )

        self.model.Overgen_MW = pyo.Var(
            self.model.ZONES,
            self.model.TIMEPOINTS,
            units=pyo.units.MWh,
            within=pyo.NonNegativeReals,
        )
        self.model.Unserved_Energy_MMBTU_H = pyo.Var(
            self.model.FUEL_ZONES,
            self.model.CANDIDATE_FUELS,
            self.model.TIMEPOINTS,
            units=pyo.units.MBtu / pyo.units.H,
            within=pyo.NonNegativeReals,
        )
        self.model.Overproduction_MMBTU_H = pyo.Var(
            self.model.FUEL_ZONES,
            self.model.CANDIDATE_FUELS,
            self.model.TIMEPOINTS,
            units=pyo.units.MBtu / pyo.units.H,
            within=pyo.NonNegativeReals,
        )

        ## Resource slack variables
        self.model.Unserved_Reserve_MW = pyo.Var(
            self.model.RESERVES,
            self.model.TIMEPOINTS,
            units=pyo.units.MWh,
            within=pyo.NonNegativeReals,
        )

        self.model.OPERATIONS_ASSETS = pyo.Set(initialize=self.system.operations_assets.keys())
        @mark_pyomo_component
        @self.model.Expression(self.model.OPERATIONS_ASSETS, self.model.TIMEPOINTS)
        def Asset_Net_Power_MW(model, asset, model_year, rep_period, hour):
            if asset in model.TRANSMISSION_LINES:
                return model.Transmit_Power_MW[asset, model_year, rep_period, hour]

            return (
                (model.Provide_Power_MW[asset, model_year, rep_period, hour] if asset in model.PLANTS_THAT_PROVIDE_POWER else 0) -
                (model.Increase_Load_MW[asset, model_year, rep_period, hour] if asset in model.PLANTS_THAT_INCREASE_LOAD else 0)
            )

        ######### ANNUAL AGGREGATED EXPRESSIONS ######################
        @mark_pyomo_component
        @self.model.Expression(self.model.PLANTS_THAT_PROVIDE_POWER, self.model.MODEL_YEARS)
        def Annual_Provide_Power(model, plant, model_year):
            return self.sum_timepoint_to_annual(model_year, "Provide_Power_MW", plant)

        @mark_pyomo_component
        @self.model.Expression(self.model.PLANTS_THAT_INCREASE_LOAD, self.model.MODEL_YEARS)
        def Annual_Increase_Load(model, plant, model_year):
            return self.sum_timepoint_to_annual(model_year, "Increase_Load_MW", plant)

        @mark_pyomo_component
        @self.model.Expression(self.model.TRANSMISSION_LINES, self.model.MODEL_YEARS)
        def Annual_Transmit_Power_Forward(model, line, model_year):
            return self.sum_timepoint_to_annual(model_year, "Transmit_Power_Forward_MW", line)

        @mark_pyomo_component
        @self.model.Expression(self.model.TRANSMISSION_LINES, self.model.MODEL_YEARS)
        def Annual_Transmit_Power_Reverse(model, line, model_year):
            return self.sum_timepoint_to_annual(model_year, "Transmit_Power_Reverse_MW", line)

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_TRANSPORTATIONS, self.model.MODEL_YEARS)
        def Annual_Transmit_Candidate_Fuel_Forward(model, line, model_year):
            return self.sum_timepoint_to_annual(model_year, "Transmit_Candidate_Fuel_Forward_MMBTU_H", line)

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_TRANSPORTATIONS, self.model.MODEL_YEARS)
        def Annual_Transmit_Candidate_Fuel_Reverse(model, line, model_year):
            return self.sum_timepoint_to_annual(model_year, "Transmit_Candidate_Fuel_Reverse_MMBTU_H", line)

        @mark_pyomo_component
        @self.model.Constraint(self.model.RESOURCES, self.model.MODEL_YEARS, self.model.REP_PERIODS)
        def Rep_Period_Energy_Budget_Constraint(model, resource, model_year, rep_period):
            """Pseudo-daily energy budget. If rep periods exceed a day in length, daily budgets are summed."""
            if self.system.resources[resource].daily_budget is not None:
                generation = sum(
                    model.Provide_Power_MW[resource, model_year, rep_period, hour]
                    * self.temporal_settings.timesteps.loc[hour]
                    for hour in model.HOURS
                )
                budget = (
                    model.Operational_Capacity_In_Model_Year[resource, model_year] *
                    sum(
                        self._get(self.system.resources[resource].daily_budget, slice_by=(model_year, rep_period, hour))
                        for hour in model.HOURS
                    )
                )
                if resource in model.CURTAILABLE_RESOURCES:
                    return generation <= budget
                else:
                    return generation == budget
            else:
                return pyo.Constraint.Skip


        @mark_pyomo_component
        @self.model.Constraint(self.model.RESOURCES, self.model.MODEL_YEARS)
        def Annual_Energy_Budget_Constraint(model, resource, model_year):
            """Annual energy budget constraint. If resource is curtailable, resource can produce less than budget."""
            if budget := self._get(
                self.system.resources[resource].annual_budget, slice_by=model_year, default_val=None
            ):
                budget = budget * model.Operational_Capacity_In_Model_Year[resource, model_year]
                if resource in model.CURTAILABLE_RESOURCES:
                    return model.Annual_Provide_Power[resource, model_year] <= budget
                else:
                    return model.Annual_Provide_Power[resource, model_year] == budget
            else:
                return pyo.Constraint.Skip

        self.model.SHED_DR_RESOURCES = pyo.Set(
            initialize=[
                r for r, obj in self.system.resources.items()
                if obj.max_call_duration is not None and obj.max_annual_calls is not None
            ]
        )

        @mark_pyomo_component
        @self.model.Constraint(self.model.SHED_DR_RESOURCES, self.model.MODEL_YEARS)
        def Annual_Shed_Demand_Response_Constraint(model, resource, model_year):
            return (
                self.sum_timepoint_to_annual(model_year, "Provide_Power_MW", resource)
                <=
                self.system.resources[resource].max_call_duration *
                self.system.resources[resource].max_annual_calls *
                model.Operational_Capacity_In_Model_Year[resource, model_year]
            )

        ##################################################
        # FUEL VARIABLES & EXPRESSIONS                   #
        ##################################################

        self.model.Resource_Fuel_Consumption_In_Timepoint_MMBTU = pyo.Var(
            self.model.RESOURCES,
            self.model.CANDIDATE_FUELS,
            self.model.TIMEPOINTS,
            units=pyo.units.MBtu,
            within=pyo.NonNegativeReals,
        )

        self.model.Fuel_Conversion_Plant_Consumption_In_Timepoint_MMBTU = pyo.Var(
            self.model.FUEL_CONVERSION_PLANTS,
            self.model.CANDIDATE_FUELS,
            self.model.TIMEPOINTS,
            units=pyo.units.MBtu,
            within=pyo.NonNegativeReals,
        )

        self.model.Fuel_Zone_Candidate_Fuel_Consumption_By_Final_Fuel_Demands_MMBTU_H = pyo.Var(
            self.model.FUEL_ZONES,
            self.model.CANDIDATE_FUELS,
            self.model.FINAL_FUEL_DEMANDS,
            self.model.TIMEPOINTS,
            units=pyo.units.MBtu,
            within=pyo.NonNegativeReals,
        )

        @mark_pyomo_component
        @self.model.Constraint(
            self.model.FUEL_ZONES,
            self.model.CANDIDATE_FUELS,
            self.model.FINAL_FUEL_DEMANDS,
            self.model.TIMEPOINTS,
        )
        def Hourly_Candidate_Fuel_For_Final_Fuel_Linkage_Constraint(
            model, fuel_zone, candidate_fuel, final_fuel_demand, model_year, rep_period, hour
        ):
            if candidate_fuel not in model.FINAL_FUEL_DEMAND_CANDIDATE_FUELS[final_fuel_demand]:
                constraint = (
                    model.Fuel_Zone_Candidate_Fuel_Consumption_By_Final_Fuel_Demands_MMBTU_H[
                        fuel_zone, candidate_fuel, final_fuel_demand, model_year, rep_period, hour
                    ]
                    == 0
                )
            else:
                constraint = pyo.Constraint.Skip

            return constraint

        self.model.Annual_Candidate_Fuel_Consumption_By_Final_Fuel_Demands = pyo.Var(
            self.model.CANDIDATE_FUELS,
            self.model.FINAL_FUEL_DEMANDS,
            self.model.MODEL_YEARS,
            units=pyo.units.MBtu,
            within=pyo.NonNegativeReals,
        )

        self.model.Candidate_Fuel_Commodity_Production_In_Timepoint_MMBTU_H = pyo.Var(
            self.model.CANDIDATE_FUELS,
            self.model.TIMEPOINTS,
            units=pyo.units.MBtu / pyo.units.H,
            within=pyo.NonNegativeReals,
        )

        self.model.Candidate_Fuel_Commodity_Production_MMBTU = pyo.Var(
            self.model.CANDIDATE_FUELS,
            self.model.MODEL_YEARS,
            units=pyo.units.MBtu,
            within=pyo.NonNegativeReals,
        )

        self.model.Candidate_Fuel_Production_From_Biomass_MT = pyo.Var(
            self.model.CANDIDATE_FUELS,
            self.model.BIOMASS_RESOURCES,
            self.model.MODEL_YEARS,
            units=pyo.units.Mt,
            within=pyo.NonNegativeReals,
        )

        @mark_pyomo_component
        @self.model.Expression(self.model.RESOURCES, self.model.CANDIDATE_FUELS, self.model.MODEL_YEARS)
        def Annual_Resource_Fuel_Consumption(model, resource, fuel, model_year):
            if fuel in model.RESOURCE_CANDIDATE_FUELS[resource]:
                return self.sum_timepoint_to_annual(
                    model_year,
                    "Resource_Fuel_Consumption_In_Timepoint_MMBTU",
                    resource,
                    fuel,
                )
            else:
                return None

        @mark_pyomo_component
        @self.model.Expression(self.model.CANDIDATE_FUELS, self.model.MODEL_YEARS)
        def Total_Annual_Candidate_Fuel_Consumption_All_Resources(model, candidate_fuel, model_year):
            consumption = 0
            for resource in model.RESOURCES:
                if candidate_fuel in model.RESOURCE_CANDIDATE_FUELS[resource]:
                    consumption += model.Annual_Resource_Fuel_Consumption[resource, candidate_fuel, model_year]

            return consumption

        @mark_pyomo_component
        @self.model.Expression(self.model.CANDIDATE_FUELS, self.model.TIMEPOINTS)
        def Total_Candidate_Fuel_Consumption_In_Timepoint_All_Resources(
            model, candidate_fuel, model_year, rep_period, hour
        ):
            """
            Add up candidate fuel consumption by resources for each timepoint. Used to calculate costs.
            """
            consumption = 0
            for resource in model.RESOURCES:
                if candidate_fuel in model.RESOURCE_CANDIDATE_FUELS[resource]:
                    consumption += model.Resource_Fuel_Consumption_In_Timepoint_MMBTU[
                        resource, candidate_fuel, model_year, rep_period, hour
                    ]
            for fuel_conversion_plant in model.FUEL_CONVERSION_PLANTS:
                if fuel_conversion_plant in model.CANDIDATE_FUEL_ELECTROFUEL_PLANTS[candidate_fuel]:
                    consumption += model.Fuel_Conversion_Plant_Consumption_In_Timepoint_MMBTU[
                        fuel_conversion_plant, candidate_fuel, model_year, rep_period, hour
                    ]

            return consumption

        @mark_pyomo_component
        @self.model.Expression(self.model.CANDIDATE_FUELS, self.model.MODEL_YEARS)
        def Total_Annual_Candidate_Fuel_Consumption_All_Final_Fuel_Demands(model, candidate_fuel, model_year):
            """
            Add together the consumption by all final fuel demands for the current candidate fuel.
            """
            consumption = 0
            for final_fuel_demand in model.FINAL_FUEL_DEMANDS:
                if candidate_fuel in model.FINAL_FUEL_DEMAND_CANDIDATE_FUELS[final_fuel_demand]:
                    consumption += model.Annual_Candidate_Fuel_Consumption_By_Final_Fuel_Demands[
                        candidate_fuel, final_fuel_demand, model_year
                    ]
            return consumption

        @mark_pyomo_component
        @self.model.Expression(self.model.CANDIDATE_FUELS, self.model.MODEL_YEARS)
        def Total_Annual_Candidate_Fuel_Consumption(model, candidate_fuel, model_year):
            """
            Add together the candidate fuel consumption by both resources and final fuel demands to get the total
            candidate fuel consumption.
            """
            return (
                model.Total_Annual_Candidate_Fuel_Consumption_All_Resources[candidate_fuel, model_year]
                + model.Total_Annual_Candidate_Fuel_Consumption_All_Final_Fuel_Demands[candidate_fuel, model_year]
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.CANDIDATE_FUELS, self.model.MODEL_YEARS)
        def Candidate_Fuel_Production_From_Biomass_MMBTU(model, candidate_fuel, model_year):
            """
            get total production from biomass resources for a candidate fuel in a year
            """
            production_from_biomass_mmbtu = 0.0
            for b in model.BIOMASS_RESOURCES:
                if b in model.CANDIDATE_FUEL_BIOMASS_RESOURCES[candidate_fuel]:
                    production_from_biomass_mmbtu += model.Candidate_Fuel_Production_From_Biomass_MT[
                        candidate_fuel, b, model_year
                    ] * (
                        self.system.biomass_resources[b]
                        .candidate_fuels[candidate_fuel]
                        .conversion_efficiency.slice_by_year(model_year)
                    )
            return production_from_biomass_mmbtu

        @mark_pyomo_component
        @self.model.Expression(self.model.CANDIDATE_FUELS, self.model.FUEL_PRODUCTION_PLANTS, self.model.TIMEPOINTS)
        def Candidate_Fuel_Production_From_Fuel_Production_Plant_In_Timepoint_MMBTU_H(
            model, candidate_fuel, fuel_plant, model_year, rep_period, hour
        ):
            if fuel_plant in model.CANDIDATE_FUEL_ELECTROFUEL_PLANTS[candidate_fuel]:
                production = self.system.fuel_production_plants[
                    fuel_plant
                ].Candidate_Fuel_Production_From_Fuel_Production_Plant_In_Timepoint_MMBTU_H(
                    model=model, candidate_fuel=candidate_fuel, model_year=model_year, rep_period=rep_period, hour=hour
                )
            else:
                production = 0.0

            return production

        @mark_pyomo_component
        @self.model.Expression(self.model.CANDIDATE_FUELS, self.model.FUEL_PRODUCTION_PLANTS, self.model.MODEL_YEARS)
        def Candidate_Fuel_Production_From_Fuel_Production_Plant_MMBTU(model, candidate_fuel, fuel_plants, model_year):
            if fuel_plants in model.CANDIDATE_FUEL_ELECTROFUEL_PLANTS[candidate_fuel]:
                production = self.system.fuel_production_plants[
                    fuel_plants
                ].Candidate_Fuel_Production_From_Fuel_Production_Plant_MMBTU(
                    resolve_case=self, model_year=model_year, candidate_fuel=candidate_fuel
                )
            else:
                production = 0.0

            return production

        @mark_pyomo_component
        @self.model.Expression(self.model.CANDIDATE_FUELS, self.model.MODEL_YEARS)
        def Candidate_Fuel_Production_From_Fuel_Production_Plants_MMBTU(model, candidate_fuel: str, model_year: int):
            """
            get total fuel produced from electrolyzers for a candidate fuel in a year
            """
            production_from_fuel_plants = 0.0
            for fuel_plant in model.FUEL_PRODUCTION_PLANTS:
                if fuel_plant in model.CANDIDATE_FUEL_ELECTROFUEL_PLANTS[candidate_fuel]:
                    production_from_fuel_plants += self.system.fuel_production_plants[
                        fuel_plant
                    ].Candidate_Fuel_Production_From_Fuel_Production_Plant_MMBTU(
                        resolve_case=self, model_year=model_year, candidate_fuel=candidate_fuel
                    )
            return production_from_fuel_plants

        @mark_pyomo_component
        @self.model.Expression(self.model.CANDIDATE_FUELS, self.model.TIMEPOINTS)
        def Candidate_Fuel_Production_From_Fuel_Production_Plants_In_Timepoint_MMBTU_H(
            model, candidate_fuel, model_year, rep_period, hour
        ):
            """
            get total fuel produced from electrolyzers for current candidate fuel in current timepoint
            """
            production_from_fuel_plants_in_timepoint_mmbtu_h = 0.0
            for fuel_plant in model.FUEL_PRODUCTION_PLANTS:
                if fuel_plant in model.CANDIDATE_FUEL_ELECTROFUEL_PLANTS[candidate_fuel]:
                    production_from_fuel_plants_in_timepoint_mmbtu_h += self.system.fuel_production_plants[
                        fuel_plant
                    ].Candidate_Fuel_Production_From_Fuel_Production_Plant_In_Timepoint_MMBTU_H(
                        model=model,
                        candidate_fuel=candidate_fuel,
                        model_year=model_year,
                        rep_period=rep_period,
                        hour=hour,
                    )
            return production_from_fuel_plants_in_timepoint_mmbtu_h

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_CONVERSION_PLANTS, self.model.CANDIDATE_FUELS, self.model.TIMEPOINTS)
        def Fuel_Conversion_Plant_Max_Hourly_Production_Constraint(
            model, fuel_conversion_plant, candidate_fuel, model_year, rep_period, hour
        ):
            return self.system.fuel_conversion_plants[
                fuel_conversion_plant
            ].Fuel_Conversion_Plant_Max_Hourly_Production_Constraint(
                model=model, candidate_fuel=candidate_fuel, model_year=model_year, rep_period=rep_period, hour=hour
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_CONVERSION_PLANTS, self.model.CANDIDATE_FUELS, self.model.TIMEPOINTS)
        def Fuel_Conversion_Plant_Consumed_Fuel_Constraint(
            model, fuel_conversion_plant, candidate_fuel, model_year, rep_period, hour
        ):
            return self.system.fuel_conversion_plants[
                fuel_conversion_plant
            ].Fuel_Conversion_Plant_Consumed_Fuel_Constraint(
                model=model, candidate_fuel=candidate_fuel, model_year=model_year, rep_period=rep_period, hour=hour
            )

        @mark_pyomo_component
        @self.model.Expression(
            self.model.RESOURCE_CANDIDATE_FUELS_FOR_EMISSIONS_POLICY, self.model.MODEL_YEARS
        )
        def Annual_Resource_Emissions_From_Candidate_Fuel(model, emissions_policy, resource, candidate_fuel, model_year):
            """Report emissions for each resource-candidate fuel-emissions policy combination."""
            return (
                self._get(self.system.candidate_fuels[candidate_fuel].policies[emissions_policy].multiplier, slice_by=model_year) *
                model.Annual_Resource_Fuel_Consumption[resource, candidate_fuel, model_year]
            )

        @mark_pyomo_component
        @self.model.Expression(
            self.model.RESOURCES, self.model.POLICIES_BY_TYPE["emissions"], self.model.MODEL_YEARS
        )
        def Annual_Resource_Emissions_In_Policy(model, resource, policy, model_year):
            if resource not in self.system.policies[policy].resources:
                return None

            if self.system.resources[resource].policies[policy].multiplier is not None:
                resource_emissions = model.Annual_Provide_Power[resource, model_year] * self._get(
                    self.system.resources[resource].policies[policy].multiplier, slice_by=model_year
                )
            else:
                resource_emissions = sum(
                    model.Annual_Resource_Emissions_From_Candidate_Fuel[p, r, candidate_fuel, model_year]
                    for p, r, candidate_fuel in model.RESOURCE_CANDIDATE_FUELS_FOR_EMISSIONS_POLICY
                    if p == policy and r == resource
                )

            return resource_emissions

        @mark_pyomo_component
        @self.model.Expression(
            self.model.TRANSMISSION_LINES, self.model.POLICIES_BY_TYPE["emissions"], self.model.MODEL_YEARS
        )
        def Annual_Transmission_Emissions_In_Policy(model, tx_path, policy, model_year):
            if tx_path not in self.system.policies[policy].tx_paths:
                return None

            if self.system.tx_paths[tx_path].policies[policy].multiplier is not None:
                tx_forward_rate = self._get(
                    self.system.tx_paths[tx_path].policies[policy].multiplier, slice_by=model_year
                )
                tx_reverse_rate = -self._get(
                    self.system.tx_paths[tx_path].policies[policy].multiplier, slice_by=model_year
                )
            else:
                tx_forward_rate = self._get(
                    self.system.tx_paths[tx_path].policies[policy].forward_dir_multiplier, slice_by=model_year
                )
                tx_reverse_rate = -self._get(
                    self.system.tx_paths[tx_path].policies[policy].reverse_dir_multiplier, slice_by=model_year
                )
                # TODO (2021-12-08): Should the reverse_dir_multiplier be negative?
                # TODO (2021-12-08): Clean this up. Seems like we should be able to consolidate resource/transmission emissions reporting...

            return (
                model.Annual_Transmit_Power_Forward[tx_path, model_year] * tx_forward_rate
                + model.Annual_Transmit_Power_Reverse[tx_path, model_year] * tx_reverse_rate
            )

        # CONSTRUCT CONSTRAINTS #
        ##################################################
        # BUILD & RETIREMENTS CONSTRAINTS                #
        ##################################################
        @mark_pyomo_component
        @self.model.Expression(self.model.ASSETS, self.model.VINTAGES)
        def Build_Capacity_MW(model, asset, vintage):
            """
            For plants with can build new, calculate new capacity built by vintage.
            """
            if self.system.assets[asset].can_build_new:
                # access the total new capacity built for the current vintage, by looking at the operational new
                # capacity for the current vintage when the model year is equal to the current vintage.
                build_capacity_mw = model.Operational_New_Capacity_By_Vintage_In_Model_Year[asset, vintage, vintage]
            else:
                build_capacity_mw = 0.0
            return build_capacity_mw

        @mark_pyomo_component
        @self.model.Expression(self.model.RESOURCES_WITH_STORAGE, self.model.VINTAGES)
        def Build_Storage_MWh(model, resource, vintage):
            """
            For storage resources with can build new, calculate new storage capacity built by vintage.
            """
            if self.system.resources[resource].can_build_new:
                # access the total new capacity built for the current vintage, by looking at the operational new
                # capacity for the current vintage when the model year is equal to the current vintage.
                build_capacity_mwh = model.Operational_New_Storage_By_Vintage_In_Model_Year[resource, vintage, vintage]
            else:
                build_capacity_mwh = 0.0
            return build_capacity_mwh

        @mark_pyomo_component
        @self.model.Expression(self.model.RESOURCES_WITH_STORAGE, self.model.MODEL_YEARS)
        def Cumulative_New_Storage_Energy_Capacity_MWh(model, resource, model_year):
            """
            For storage resources with can build new, calculate new storage capacity in model year
            """
            operational_new_capacity = 0
            if self.system.assets[resource].can_build_new:
                for v in model.VINTAGES:
                    if v <= model_year:
                        operational_new_capacity += model.Build_Storage_MWh[resource, v]

            return operational_new_capacity

        @mark_pyomo_component
        @self.model.Constraint(self.model.ASSETS, self.model.MODEL_YEARS)
        def Planned_Capacity_Constraint(model, asset, year):
            """
            Operational_Planned_Capacity_In_Model_Year must be less than or equal to planned installed value.
            If plant cannot retire it is equal
            """
            if self.system.assets[asset].can_retire:
                if year == model.first_year:
                    return (
                        model.Operational_Planned_Capacity_In_Model_Year[asset, year]
                        <=
                        self._get(self.system.assets[asset].planned_installed_capacity, slice_by=year)
                    )
                else:
                    # capacity increase from year to year cannot exceed the planned capacity increase;
                    # i.e. mothball not allowed
                    return (
                        model.Operational_Planned_Capacity_In_Model_Year[asset, year]
                        <=
                        self._get(self.system.assets[asset].planned_installed_capacity, slice_by=year) -
                        self._get(self.system.assets[asset].planned_installed_capacity, slice_by=model.previous_year[year]) +
                        model.Operational_Planned_Capacity_In_Model_Year[asset, model.previous_year[year]]
                    )
            else:
                return (
                    model.Operational_Planned_Capacity_In_Model_Year[asset, year]
                    ==
                    self._get(self.system.assets[asset].planned_installed_capacity, slice_by=year)
                )

        @mark_pyomo_component
        @self.model.Constraint(self.model.ASSETS, self.model.VINTAGES, self.model.MODEL_YEARS)
        def New_Capacity_Limit_Constraint(model, asset, vintage, year):
            """
            Operational_New_Capacity_By_Vintage_In_Model_Year can only decrease
            (if can retire) or stay flat (if cannot retire) over years
            """
            if self.system.assets[asset].physical_lifetime is not None:
                # Assets with physical lifetimes should be allowed to retire even if `can_retire` is False
                if year >= vintage + self.system.assets[asset].physical_lifetime:
                    return pyo.Constraint.Skip
            if vintage > year:
                return model.Operational_New_Capacity_By_Vintage_In_Model_Year[asset, vintage, year] == 0
            elif vintage == year:
                return model.Operational_New_Capacity_By_Vintage_In_Model_Year[asset, vintage, year] >= 0
            else:
                if self.system.assets[asset].can_retire:
                    return (
                        model.Operational_New_Capacity_By_Vintage_In_Model_Year[asset, vintage, year]
                        <=
                        model.Operational_New_Capacity_By_Vintage_In_Model_Year[asset, vintage, model.previous_year[year]]
                    )
                else:
                    return (
                        model.Operational_New_Capacity_By_Vintage_In_Model_Year[asset, vintage, year]
                        ==
                        model.Operational_New_Capacity_By_Vintage_In_Model_Year[asset, vintage, model.previous_year[year]]
                    )

        @mark_pyomo_component
        @self.model.Constraint(self.model.ASSETS, self.model.VINTAGES, self.model.MODEL_YEARS)
        def Lifetime_Retirement_Constraint(model, asset, vintage, modeled_year):
            """For resources with a defined `physical_lifetime`, force their retirement at end of life."""
            if self.system.assets[asset].physical_lifetime is None:
                return pyo.Constraint.Skip
            else:
                if modeled_year >= vintage + self.system.assets[asset].physical_lifetime:
                    return model.Operational_New_Capacity_By_Vintage_In_Model_Year[asset, vintage, modeled_year] == 0
                else:
                    return pyo.Constraint.Skip

        @mark_pyomo_component
        @self.model.Expression(self.model.ASSETS, self.model.MODEL_YEARS)
        def Retired_Planned_Capacity(model, asset, modeled_year):
            return (
                self._get(self.system.assets[asset].planned_installed_capacity, slice_by=modeled_year) -
                model.Operational_Planned_Capacity_In_Model_Year[asset, modeled_year]
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.ASSETS, self.model.MODEL_YEARS)
        def Retired_New_Capacity(model, asset, modeled_year):
            return (
                sum(model.Build_Capacity_MW[asset, vintage] for vintage in model.VINTAGES if vintage <= modeled_year) -
                model.Operational_New_Capacity_MW[asset, modeled_year]
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.ASSETS, self.model.MODEL_YEARS)
        def Capacity_Retired_In_Model_Year(model, asset, modeled_year):
            if modeled_year == model.MODEL_YEARS.first():
                return model.Retired_Planned_Capacity[asset, modeled_year] + model.Retired_New_Capacity[asset, modeled_year]
            else:
                return (
                    (model.Retired_Planned_Capacity[asset, modeled_year] + model.Retired_New_Capacity[asset, modeled_year]) -
                    (model.Retired_Planned_Capacity[asset, model.MODEL_YEARS.prev(modeled_year)] + model.Retired_New_Capacity[asset, model.MODEL_YEARS.prev(modeled_year)])
                )

        @mark_pyomo_component
        @self.model.Constraint(self.model.RESOURCES_WITH_STORAGE, self.model.MODEL_YEARS)
        def Planned_Storage_Constraint(model, resource, year):
            """
            Operational_Planned_Capacity_In_Model_Year must be less than or equal to planned installed value.
            If resource cannot retire it is equal
            Args:
              model:
              resource:
              year:

            Returns:

            """
            if self.system.assets[resource].can_retire:
                if year == model.first_year:
                    return (
                        model.Operational_Planned_Storage_In_Model_Year[resource, year]
                        <=
                        model.planned_storage_capacity_mwh[resource, year]
                    )
                else:
                    # capacity increase from year to year cannot exceed the planned capacity increase;
                    # i.e. mothball not allowed
                    return (
                        model.Operational_Planned_Storage_In_Model_Year[resource, year]
                        <=
                        model.planned_storage_capacity_mwh[resource, year] -
                        model.planned_storage_capacity_mwh[resource, model.previous_year[year]] +
                        model.Operational_Planned_Storage_In_Model_Year[resource, model.previous_year[year]]
                    )
            else:
                return (
                    model.Operational_Planned_Storage_In_Model_Year[resource, year]
                    ==
                    model.planned_storage_capacity_mwh[resource, year]
                )

        @mark_pyomo_component
        @self.model.Constraint(
            self.model.RESOURCES_WITH_STORAGE,
            self.model.VINTAGES,
            self.model.MODEL_YEARS,
        )
        def New_Storage_Limit_Constraint(model, resource, vintage, year):
            """
            Operational_New_Storage_By_Vintage_In_Model_Year can only decrease
            (if can retire) or stay flat (if cannot retire) over years
            """
            if self.system.assets[resource].physical_lifetime is not None:
                # Assets with physical lifetimes should be allowed to retire even if `can_retire` is False
                if year >= vintage + self.system.assets[resource].physical_lifetime:
                    return pyo.Constraint.Skip

            if vintage > year:
                return model.Operational_New_Storage_By_Vintage_In_Model_Year[resource, vintage, year] == 0
            elif vintage == year:
                return pyo.Constraint.Skip
            else:
                if self.system.assets[resource].can_retire:
                    return (
                        model.Operational_New_Storage_By_Vintage_In_Model_Year[resource, vintage, year]
                        <=
                        model.Operational_New_Storage_By_Vintage_In_Model_Year[resource, vintage, model.previous_year[year]]
                    )
                else:
                    return (
                        model.Operational_New_Storage_By_Vintage_In_Model_Year[resource, vintage, year]
                        ==
                        model.Operational_New_Storage_By_Vintage_In_Model_Year[resource, vintage, model.previous_year[year]]
                    )

        @mark_pyomo_component
        @self.model.Constraint(self.model.RESOURCES_WITH_STORAGE, self.model.VINTAGES, self.model.MODEL_YEARS)
        def Storage_Lifetime_Retirement_Constraint(model, resource, vintage, modeled_year):
            """For resources with a defined `physical_lifetime`, force their retirement at end of life."""
            if self.system.resources[resource].physical_lifetime is None:
                return pyo.Constraint.Skip
            else:
                if modeled_year >= vintage + self.system.resources[resource].physical_lifetime:
                    return model.Operational_New_Storage_By_Vintage_In_Model_Year[resource, vintage, modeled_year] == 0
                else:
                    return pyo.Constraint.Skip


        @mark_pyomo_component
        @self.model.Expression(self.model.RESOURCES_WITH_STORAGE, self.model.MODEL_YEARS)
        def Retired_New_Storage_Capacity(model, resource, modeled_year):
            return (
                sum(model.Build_Storage_MWh[resource, vintage] for vintage in model.VINTAGES if vintage <= modeled_year) -
                model.Operational_Storage_In_Model_Year[resource, modeled_year]
            )


        @mark_pyomo_component
        @self.model.Constraint(self.model.RESOURCES_WITH_STORAGE, self.model.MODEL_YEARS)
        def Storage_Duration_Constraint(model, resource, model_year):
            """
            Enforce user defined duration if relevant.
            Args:
                model:
                resource:
                model_year:

            Returns:

            """
            if self.system.resources[resource].duration is None:
                return pyo.Constraint.Skip
            else:
                return (
                    model.Operational_Storage_In_Model_Year[resource, model_year]
                    == model.Operational_Capacity_In_Model_Year[resource, model_year]
                    * self.system.resources[resource].duration
                )

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_STORAGES, self.model.MODEL_YEARS)
        def Fuel_Storage_Duration_Constraint(model, fuel_storage, model_year):
            """
            Enforce user defined duration if relevant.
            Args:
                model:
                resource:
                model_year:

            Returns:

            """
            return self.system.fuel_storages[fuel_storage].Fuel_Storage_Duration_Constraint(
                model=model, model_year=model_year
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.ASSETS, self.model.MODEL_YEARS)
        def Min_Cumulative_New_Build_Constraint(model, asset, model_year):
            if (not self.production_simulation_mode) and (
                min_cumulative_new_build := self._get(
                    self.system.assets[asset].min_cumulative_new_build, default_val=None, slice_by=model_year
                )
            ):
                return model.Operational_New_Capacity_MW[asset, model_year] >= min_cumulative_new_build
            else:
                return pyo.Constraint.Skip

        @mark_pyomo_component
        @self.model.Constraint(self.model.ASSETS, self.model.MODEL_YEARS)
        def Min_Operational_Capacity_Constraint(model, asset, model_year):
            if min_op_capacity := self._get(
                self.system.assets[asset].min_op_capacity, default_val=None, slice_by=model_year
            ):
                return model.Operational_Capacity_In_Model_Year[asset, model_year] >= min_op_capacity
            else:
                return pyo.Constraint.Skip

        self.model.Resource_Potential_Slack = pyo.Var(self.model.ASSETS, self.model.MODEL_YEARS, within=pyo.NonNegativeReals)

        @mark_pyomo_component
        @self.model.Constraint(self.model.ASSETS, self.model.MODEL_YEARS)
        def Resource_Potential_Constraint(model, asset, model_year):
            if not self.system.assets[asset].can_build_new:
                return pyo.Constraint.Skip

            potential = self._get(self.system.assets[asset].potential, default_val=None, slice_by=model_year)
            if potential is not None and potential != float("inf"):
                return (
                    model.Operational_Capacity_In_Model_Year[asset, model_year]
                    <=
                    potential +
                    model.Resource_Potential_Slack[asset, model_year]
                )
            else:
                return pyo.Constraint.Skip

        self.model.INTEGER_BUILD_RESOURCES = pyo.Set(initialize=[r for r, v in self.system.resources.items() if v.integer_build])
        self.model.Integer_Build = pyo.Var(self.model.INTEGER_BUILD_RESOURCES, self.model.VINTAGES, within=pyo.NonNegativeIntegers)
        @mark_pyomo_component
        @self.model.Constraint(self.model.INTEGER_BUILD_RESOURCES, self.model.VINTAGES)
        def Integer_Build_Constraint(model, resource, vintage):
            if vintage==self.system.resources[resource].build_year:
                if (unit_size := self.system.resources[resource].unit_size_mw) is not None:
                    build_size = unit_size
                else:
                    if self._get(self.system.resources[resource].potential, slice_by=vintage, default_val=None) is None:
                        logger.error(f"No unit size or resource potential defined for {resource} integer build.")
                    build_size = self._get(self.system.resources[resource].potential, slice_by=vintage, default_val=None)

                return (
                    model.Operational_New_Capacity_By_Vintage_In_Model_Year[resource, vintage, vintage]
                    ==
                    model.Integer_Build[resource, vintage] *
                    build_size
                )
            else:
                return model.Integer_Build[resource, vintage] == 0

        ##################################################
        # FLEXIBLE LOAD CONSTRAINTS                      #
        ##################################################
        @mark_pyomo_component
        @self.model.Constraint(self.model.RESOURCES, self.model.TIMEPOINTS)
        def Increase_Load_Intra_Period_Adjacency_Constraint(model, resource, model_year, rep_period, hour):
            """Handles adjacency constraints for timepoints **within** a representative period.

            If any the adjacency range spans **across** representative periods, that is handled by the
            `Increase_Load_Adjacency_Across_Rep_Period_Constraint`.

            the constraint is formulated as:
                Increase_Load_MW[t+n] <= sum(P[t+n] for n in range(2*n + 1)

            Note how it's constraining on t+n instead of t.
            """
            if self.system.resources[resource].adjacency is None:
                return pyo.Constraint.Skip
            else:
                adjacency_hours = self.system.resources[resource].adjacency
                hour_offsets = range(2 * adjacency_hours + 1)
                if any(
                    (model_year, rep_period, hour + offset) > model.last_timepoint_of_period[model_year, rep_period]
                    for offset in hour_offsets
                ):
                    return pyo.Constraint.Skip
                else:
                    return model.Increase_Load_MW[resource, model_year, rep_period, hour + adjacency_hours] <= sum(
                        model.Provide_Power_MW[resource, model_year, rep_period, hour + offset]
                        for offset in hour_offsets
                    )

        @mark_pyomo_component
        @self.model.Constraint(self.model.RESOURCES, self.model.MODEL_YEARS_AND_ADJACENT_REP_PERIODS, self.model.HOURS)
        def Increase_Load_Inter_Period_Adjacency_Constraint(
            model, resource, model_year, rep_period_1, rep_period_2, hour
        ):
            """Handles adjacency constraints for timepoints **between** representative periods."""
            if self.system.resources[resource].adjacency is None:
                return pyo.Constraint.Skip
            else:
                adjacency_hours = self.system.resources[resource].adjacency
                hour_offsets = range(2 * adjacency_hours + 1)
                if not any(
                    (model_year, rep_period_1, hour + offset) > model.last_timepoint_of_period[model_year, rep_period_1]
                    for offset in hour_offsets
                ):
                    return pyo.Constraint.Skip
                else:
                    # Get list of timepoints within the adjacency constraint
                    tp = []
                    for offset in hour_offsets:
                        tp_temp = (model_year, rep_period_1, hour + offset)
                        if tp_temp > model.last_timepoint_of_period[model_year, rep_period_1]:
                            # If tp crosses into second rep period
                            tp += [(model_year, rep_period_2, (hour + offset) % pyo.value(model.timepoints_per_period))]
                        else:
                            # If tp is in first rep period
                            tp += [tp_temp]
                    return model.Increase_Load_MW[resource, tp[adjacency_hours]] <= sum(
                        model.Provide_Power_MW[resource, m, r, h] for (m, r, h) in tp
                    )

        @mark_pyomo_component
        @self.model.Constraint(self.model.RESOURCES, self.model.TIMEPOINTS)
        def Provide_Power_Intra_Period_Adjacency_Constraint(model, resource, model_year, rep_period, hour):
            """Handles adjacency constraints for timepoints **within** a representative period.

            If any the adjacency range spans **across** representative periods, that is handled by the
            `Increase_Load_Adjacency_Across_Rep_Period_Constraint`.

            the constraint is formulated as:
                Provide_Power_MW[t+n] <= sum(L[t+n] for n in range(2*n + 1)
            Again, note how it's constraining on t+n hour instead of the t hour
            """
            if self.system.resources[resource].adjacency is None:
                return pyo.Constraint.Skip
            else:
                adjacency_hours = self.system.resources[resource].adjacency
                hour_offsets = range(2 * adjacency_hours + 1)
                if any(
                    (model_year, rep_period, hour + offset) > model.last_timepoint_of_period[model_year, rep_period]
                    for offset in hour_offsets
                ):
                    return pyo.Constraint.Skip
                else:
                    return model.Provide_Power_MW[resource, model_year, rep_period, hour + adjacency_hours] <= sum(
                        model.Increase_Load_MW[resource, model_year, rep_period, hour + offset]
                        for offset in hour_offsets
                    )

        @mark_pyomo_component
        @self.model.Constraint(self.model.RESOURCES, self.model.MODEL_YEARS_AND_ADJACENT_REP_PERIODS, self.model.HOURS)
        def Provide_Power_Inter_Period_Adjacency_Constraint(
            model, resource, model_year, rep_period_1, rep_period_2, hour
        ):
            """Handles adjacency constraints for timepoints **between** representative periods."""
            if self.system.resources[resource].adjacency is None:
                return pyo.Constraint.Skip
            else:
                adjacency_hours = self.system.resources[resource].adjacency
                hour_offsets = range(2 * adjacency_hours + 1)
                if not any(
                    (model_year, rep_period_1, hour + offset) > model.last_timepoint_of_period[model_year, rep_period_1]
                    for offset in hour_offsets
                ):
                    return pyo.Constraint.Skip
                else:
                    # Get list of timepoints within the adjacency constraint
                    tp = []
                    for offset in hour_offsets:
                        tp_temp = (model_year, rep_period_1, hour + offset)
                        if tp_temp > model.last_timepoint_of_period[model_year, rep_period_1]:
                            # If tp crosses into second rep period
                            tp += [(model_year, rep_period_2, (hour + offset) % pyo.value(model.timepoints_per_period))]
                        else:
                            # If tp is in first rep period
                            tp += [tp_temp]

                    return model.Provide_Power_MW[resource, tp[adjacency_hours]] <= sum(
                        model.Increase_Load_MW[resource, m, r, h] for (m, r, h) in tp
                    )

        ##################################################
        # RELIABILITY AND ELCC CONSTRAINTS               #
        ##################################################
        @mark_pyomo_component
        @self.model.Constraint(self.model.POLICIES_BY_TYPE["prm"], self.model.ASSETS, self.model.MODEL_YEARS)
        def Max_Reliability_Capacity_Constraint(model, prm_policy, asset, model_year):
            """Constraint ``Reliability_Capacity_In_Model_Year`` variable based on ``Operational_Capacity_In_Model_Year``.

            ``Reliability_Capacity_In_Model_Year`` serves the same purpose as the previous RESOLVE formulation's
            ``Reliability_Capacity_Delivered_MW`` variable, which was used in conjunction with custom constraints
            to further derate the MW that can contribute to PRM below ``Operational_Capacity_In_Model_Year``.

            Note: Unlike the previous RESOLVE formulations, the new, default formulation makes **no assumptions** about how
            ``Reliability_Capacity_In_Model_Year`` should be constrained, so derates to capture transmission deliverability,
            storage duration, or DR calls need to be added via custom constraints.
            """
            if prm_policy not in self.system.assets[asset].policies:
                return pyo.Constraint.Skip

            if self.system.assets[asset].policies[prm_policy].deliverability_status == DeliverabilityStatus.ENERGY_ONLY:
                return (
                    model.Reliability_Capacity_In_Model_Year[prm_policy, asset, model_year] == 0
                )
            elif self.system.assets[asset].policies[prm_policy].deliverability_status == DeliverabilityStatus.FULLY_DELIVERABLE:
                return (
                    model.Reliability_Capacity_In_Model_Year[prm_policy, asset, model_year]
                    ==
                    model.Operational_Capacity_In_Model_Year[asset, model_year]
                )
            else:
                return (
                    model.Reliability_Capacity_In_Model_Year[prm_policy, asset, model_year]
                    <=
                    model.Operational_Capacity_In_Model_Year[asset, model_year]
                )

        @mark_pyomo_component
        @self.model.Constraint(self.model.POLICIES_BY_TYPE["prm"], self.model.ASSETS, self.model.MODEL_YEARS)
        def Reliability_Capacity_Tracking_Constraint(model, prm_policy, asset, model_year):
            if prm_policy not in self.system.assets[asset].policies:
                return pyo.Constraint.Skip

            if model_year == model.MODEL_YEARS.first():
                return pyo.Constraint.Skip
            else:
                return (
                    model.Reliability_Capacity_In_Model_Year[prm_policy, asset, model_year]
                    >=
                    model.Reliability_Capacity_In_Model_Year[prm_policy, asset, model.MODEL_YEARS.prev(model_year)] -
                    # `Capacity_Retired_In_Model_Year` only covered retirement decisions made by Resolve, and not changes in `planned_installed_capacity` -
                    model.Capacity_Retired_In_Model_Year[asset, model_year] -
                    max(0, self._get(self.system.assets[asset].planned_installed_capacity, slice_by=model.MODEL_YEARS.prev(model_year)) - (self._get(self.system.assets[asset].planned_installed_capacity, slice_by=model_year)))
                )

        @mark_pyomo_component
        @self.model.Constraint(self.model.POLICIES_BY_TYPE["prm"], self.model.ASSETS_WITH_TRANCHES, self.model.MODEL_YEARS)
        def Constrain_Tranche_Reliability_Capacity(model, prm_policy, asset, year):
            """Sum of tranche builds should exactly match the aggregate asset build."""
            return (
                sum(
                    model.Reliability_Capacity_In_Model_Year[prm_policy, tranche, year]
                    for tranche in self.system.assets[asset].tranches
                    if tranche in self.system.policies[prm_policy].assets
                )
                ==
                model.Reliability_Capacity_In_Model_Year[prm_policy, asset, year]
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.POLICIES_BY_TYPE["prm"], self.model.ASSETS, self.model.MODEL_YEARS)
        def Energy_Only_Capacity(model, prm_policy, asset, model_year):
            if asset in self.system.policies[prm_policy].assets:
                return (
                    model.Operational_Capacity_In_Model_Year[asset, model_year] -
                    model.Reliability_Capacity_In_Model_Year[prm_policy, asset, model_year]
                )
            else:
                return None

        @mark_pyomo_component
        @self.model.Constraint(self.model.POLICIES_BY_TYPE["prm"], self.model.ASSETS, self.model.MODEL_YEARS)
        def Energy_Only_Capacity_Tracking_Constraint(model, prm_policy, asset, model_year):
            if prm_policy not in self.system.assets[asset].policies:
                return pyo.Constraint.Skip

            if model_year == model.MODEL_YEARS.first():
                return pyo.Constraint.Skip
            else:
                return (
                    model.Energy_Only_Capacity[prm_policy, asset, model_year]
                    >=
                    model.Energy_Only_Capacity[prm_policy, asset, model.MODEL_YEARS.prev(model_year)] -
                    # `Capacity_Retired_In_Model_Year` only covered retirement decisions made by Resolve, and not changes in `planned_installed_capacity` -
                    model.Capacity_Retired_In_Model_Year[asset, model_year] -
                    max(0, self._get(self.system.assets[asset].planned_installed_capacity, slice_by=model.MODEL_YEARS.prev(model_year)) - (self._get(self.system.assets[asset].planned_installed_capacity, slice_by=model_year)))
                )


        @mark_pyomo_component
        @self.model.Expression(self.model.POLICIES_BY_TYPE["prm"], self.model.ASSETS, self.model.MODEL_YEARS)
        def NQC_By_Resource(model, prm_policy, asset, model_year):
            if (
                asset not in self.system.policies[prm_policy].assets.keys() or
                self.system.policies[prm_policy].assets[asset].multiplier is None
            ):
                return 0
            else:
                return (
                    self._get(self.system.policies[prm_policy].assets[asset].multiplier, slice_by=model_year) *
                    model.Reliability_Capacity_In_Model_Year[prm_policy, asset, model_year]
                )

        @mark_pyomo_component
        @self.model.Expression(self.model.POLICIES_BY_TYPE["prm"], self.model.MODEL_YEARS)
        def NQC_LHS(model, prm_policy, model_year):
            """Calculate sum of resource NQCs for a given PRM policy."""
            return sum(
                model.NQC_By_Resource[prm_policy, resource_name, model_year]
                for resource_name in self.system.policies[prm_policy].assets.keys()
            )

        if self.model.allow_elcc_surface:
            # TODO (2021-12-09): Create a nested set for prm-elcc

            @mark_pyomo_component
            @self.model.Expression(self.model.POLICIES_BY_TYPE["prm"], self.model.MODEL_YEARS)
            def ELCC_LHS(model, prm_policy, model_year):
                """Calculate sum of linked ELCC surfaces for a given PRM policy."""
                return sum(
                    model.ELCC_MW[model_year, elcc_surface]
                    for elcc_surface in model.ELCC_SURFACE
                    if elcc_surface in self.system.policies[prm_policy].elcc_surfaces.keys()
                )

            @mark_pyomo_component
            @self.model.Expression(
                self.model.MODEL_YEARS, self.model.POLICIES_BY_TYPE["prm"], self.model.ELCC_SURFACE, self.model.FACETS
            )
            def ELCC_Facet_Value(model, model_year, prm_policy, elcc_surface, facet):
                # If ELCC facet isn't assigned to PRM policy, facet is essentially infinite
                if (
                    facet not in self.model.ELCC_SURFACE_FACETS[elcc_surface]
                    or elcc_surface not in self.system.policies[prm_policy].elcc_surfaces.keys()
                ):
                    return float("+inf")

                # Get # of ELCC axes (currently limited to two in elcc.py)
                elcc_axes = range(
                    1, max(r.elcc_axis_index for r in self.system.elcc_surfaces[elcc_surface].assets.values()) + 1
                )
                # Calculate facet value from slope-intercept
                facet_elcc_mw = (
                    # Intercept
                    self._get(self.system.elcc_surfaces[elcc_surface].facets[facet].axis_0, slice_by=model_year)
                    +
                    # Sum ``Reliability_Capacity_In_Model_Year`` of all resources assigned to this axis
                    sum(
                        self._get(
                            getattr(self.system.elcc_surfaces[elcc_surface].facets[facet], f"axis_{axis_num}"),
                            slice_by=model_year,
                        )
                        * sum(
                            r.elcc_axis_multiplier *
                            (
                                model.Reliability_Capacity_In_Model_Year[prm_policy, asset, model_year]
                                if r.attribute == "power"
                                else model.Operational_Storage_In_Model_Year[asset, model_year]
                            )
                            for asset, r in self.system.elcc_surfaces[elcc_surface].assets.items()
                            if r.elcc_axis_index == axis_num
                            and asset in self.system.policies[prm_policy].assets
                        )
                        for axis_num in elcc_axes
                    )
                )
                return facet_elcc_mw


            @mark_pyomo_component
            @self.model.Constraint(
                self.model.MODEL_YEARS, self.model.POLICIES_BY_TYPE["prm"], self.model.ELCC_SURFACE, self.model.FACETS
            )
            def ELCC_Facet_Constraint_LHS(model, model_year, prm_policy, elcc_surface, facet):
                """Constrain `ELCC_MW` variable by each ELCC facet."""
                # Guard clause exits constraint immediately
                if (
                    facet not in self.model.ELCC_SURFACE_FACETS[elcc_surface]
                    or elcc_surface not in self.system.policies[prm_policy].elcc_surfaces.keys()
                ):
                    return pyo.Constraint.Skip
                return (
                    model.ELCC_MW[model_year, elcc_surface]
                    <= model.ELCC_Facet_Value[model_year, prm_policy, elcc_surface, facet]
                )

        ##################################################
        # RESOURCE OPERATION CONSTRAINTS                 #
        ##################################################
        @mark_pyomo_component
        @self.model.Constraint(self.model.PLANTS, self.model.TIMEPOINTS)
        def Max_Provide_Power_Up_Reserve_Constraint(model, plant, model_year, rep_period, hour):
            """
            provide power - increase load + up reserves cannot exceed pre-specified timepoint max provide power
            """
            return (
                (model.Provide_Power_MW[plant, model_year, rep_period, hour] if plant in model.PLANTS_THAT_PROVIDE_POWER else 0.0) +
                (model.Total_Up_Reserves_By_Resource_By_Timepoint[plant, model_year, rep_period, hour] if plant in model.RESOURCES else 0.0) -
                (model.Increase_Load_MW[plant, model_year, rep_period, hour] if plant in model.PLANTS_THAT_INCREASE_LOAD else 0.0)
                <=
                (model.Plant_Provide_Power_Capacity_In_Timepoint_MW[plant, model_year, rep_period, hour] if plant in model.PLANTS_THAT_PROVIDE_POWER else 0.0)
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.PLANTS, self.model.TIMEPOINTS)
        def Max_Increase_Load_Down_Reserve_Constraint(model, plant, model_year, rep_period, hour):
            """
            increase load - provide power + down reserves cannot exceed pre-specified timepoint max increase load
            """
            return (
                (model.Increase_Load_MW[plant, model_year, rep_period, hour] if plant in model.PLANTS_THAT_INCREASE_LOAD else 0.0) +
                (model.Total_Down_Reserves_By_Resource_By_Timepoint[plant, model_year, rep_period, hour] if plant in model.RESOURCES else 0.0) -
                (model.Provide_Power_MW[plant, model_year, rep_period, hour] if plant in model.PLANTS_THAT_PROVIDE_POWER else 0.0)
                <=
                (model.Plant_Increase_Load_Capacity_In_Timepoint_MW[plant, model_year, rep_period, hour] if plant in model.PLANTS_THAT_INCREASE_LOAD else 0.0)
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.PLANTS_THAT_PROVIDE_POWER, self.model.TIMEPOINTS)
        def Max_Provide_Power_Domain_Constraint(model, plant, model_year, rep_period, hour):
            """
            provide power cannot exceed max provide power (restricts domain of provide power)
            """
            return (
                model.Provide_Power_MW[plant, model_year, rep_period, hour]
                <= model.Plant_Provide_Power_Capacity_In_Timepoint_MW[plant, model_year, rep_period, hour]
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.PLANTS_THAT_PROVIDE_POWER, self.model.TIMEPOINTS)
        def Min_Provide_Power_Domain_Constraint(model, plant, model_year, rep_period, hour):
            """
            provide power cannot be less than min provide power (restricts domain of provide power)
            """
            return (
                model.Provide_Power_MW[plant, model_year, rep_period, hour]
                >= model.Plant_Power_Min_Capacity_In_Timepoint_MW[plant, model_year, rep_period, hour]
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.RESOURCES_WITH_STORAGE, self.model.TIMEPOINTS)
        def Simultaneous_Charging_Constraint(model, resource, model_year, rep_period, hour):
            """Limit simultaneous charging & discharging for ``RESOURCES_WITH_STORAGE`` to what could be possible within an hour.

            In other words, storage resources can simultaneously charge & discharge as long as they "split" the hour
            (e.g., charging for half the hour and discharging for half the hour).
            """
            return model.Provide_Power_MW[resource, model_year, rep_period, hour] + model.Increase_Load_MW[
                resource, model_year, rep_period, hour
            ] + model.Total_Up_Reserves_By_Resource_By_Timepoint[
                resource, model_year, rep_period, hour
            ] + model.Total_Down_Reserves_By_Resource_By_Timepoint[
                resource, model_year, rep_period, hour
            ] <= 0.5 * (
                model.Plant_Provide_Power_Capacity_In_Timepoint_MW[resource, model_year, rep_period, hour]
                + model.Plant_Increase_Load_Capacity_In_Timepoint_MW[resource, model_year, rep_period, hour]
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_STORAGES, self.model.TIMEPOINTS)
        def Fuel_Storage_Simulataneous_Charging_Constraint(model, fuel_storage, model_year, rep_period, hour):
            """
            Limit simultaneous charging and discharging for fuel storage resources.
            Split 50-50 in a given hour.
            """
            return self.system.fuel_storages[fuel_storage].Fuel_Storage_Simultaneous_Charging_Constraint(
                model, model_year, rep_period, hour
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_STORAGES, self.model.TIMEPOINTS)
        def Fuel_Storage_Increase_Load_Constraint(model, fuel_storage, model_year, rep_period, hour):
            """
            Constrain fuel storage increase load capacity to equal the sum of increased load from both storage
            and production for all hours.
            """
            return self.system.fuel_storages[fuel_storage].Fuel_Storage_Increase_Load_Constraint(
                model, model_year, rep_period, hour
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.UNIT_COMMITMENT_RESOURCES, self.model.TIMEPOINTS)
        def Unit_Commitment_Pmin(model, resource, model_year, rep_period, hour):
            return (
                self._get(self.system.resources[resource].min_stable_level, slice_by=model_year)
                * model.Committed_Capacity_MW[resource, model_year, rep_period, hour]
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.UNIT_COMMITMENT_RESOURCES, self.model.TIMEPOINTS)
        def Unit_Commitment_Pmin_Constraint(model, resource, model_year, rep_period, hour):
            return (
                model.Provide_Power_MW[resource, model_year, rep_period, hour]
                >=
                model.Unit_Commitment_Pmin[resource, model_year, rep_period, hour]
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.PLANTS_THAT_INCREASE_LOAD, self.model.TIMEPOINTS)
        def Max_Increase_Load_Domain_Constraint(model, plant, model_year, rep_period, hour):
            """
            increase load cannot exceed max increase load (restricts domain of increase load)
            """
            return (
                model.Increase_Load_MW[plant, model_year, rep_period, hour]
                <= model.Plant_Increase_Load_Capacity_In_Timepoint_MW[plant, model_year, rep_period, hour]
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.PLANTS_THAT_PROVIDE_POWER, self.model.TIMEPOINTS)
        def Provide_Power_Curtailment_Constraint(model, plant, model_year, rep_period, hour):
            """For non-curtailable resources, for ``Provide_Power_MW`` to be equal to ``provide_power_potential_profile``.

            Notes:
                - This is only "scheduled" hourly curtailment
                - The current formulation does not include any "subhourly" curtailment due to subhourly reserves
                - The model may have numerical issues if the ``provide_power_potential_profile`` is very small
            """
            # TODO (2021-10-07): What happens in this constraint if `provide_power_potential_profile` is None but `curtailable` is False
            if plant not in model.CURTAILABLE_RESOURCES and self.system.resources[plant].daily_budget is None:
                return model.Provide_Power_MW[
                    plant, model_year, rep_period, hour
                ] == model.Operational_Capacity_In_Model_Year[plant, model_year] * self._get(
                    self.system.plants[plant].provide_power_potential_profile, slice_by=(model_year, rep_period, hour)
                )
            else:
                return pyo.Constraint.Skip

        @mark_pyomo_component
        @self.model.Constraint(self.model.UNIT_COMMITMENT_RESOURCES, self.model.TIMEPOINTS)
        def Committed_Units_UB_Constraint(model, resource, model_year, rep_period, hour):
            """Calculate the maximum number of units that can be committed based on operational capacity in model year."""
            return (
                model.Committed_Units[resource, model_year, rep_period, hour]
                <= model.Operational_Units_In_Timepoint[resource, model_year, rep_period, hour]
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.UNIT_COMMITMENT_RESOURCES, self.model.TIMEPOINTS)
        def Start_Units_UB_Constraint(model, resource, model_year, rep_period, hour):
            """Calculate the maximum number of units that can be started based on operational capacity in model year."""
            return (
                model.Start_Units[resource, model_year, rep_period, hour]
                <= model.Operational_Units_In_Timepoint[resource, model_year, rep_period, hour]
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.UNIT_COMMITMENT_RESOURCES, self.model.TIMEPOINTS)
        def Shutdown_Units_UB_Constraint(model, resource, model_year, rep_period, hour):
            """Calculate the maximum number of units that can be shutdown based on operational capacity in model year."""
            return (
                model.Shutdown_Units[resource, model_year, rep_period, hour]
                <= model.Operational_Units_In_Timepoint[resource, model_year, rep_period, hour]
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.UNIT_COMMITMENT_RESOURCES, self.model.TIMEPOINTS)
        def Commitment_Tracking_Intra_Period_Constraint(model, resource, model_year, rep_period, hour):
            """Track unit commitment status."""
            if hour < model.last_timepoint_of_period[model_year, rep_period][2]:
                next_hour = hour + 1
            else:
                next_hour = model.first_timepoint_of_period[model_year, rep_period][2]

            return (
                model.Committed_Units[resource, model_year, rep_period, next_hour]
                == model.Committed_Units[resource, model_year, rep_period, hour]
                + model.Start_Units[resource, model_year, rep_period, next_hour]
                - model.Shutdown_Units[resource, model_year, rep_period, next_hour]
            )

        # @mark_pyomo_component
        # @self.model.Constraint(
        #     self.model.UNIT_COMMITMENT_RESOURCES, self.model.MODEL_YEARS_AND_ADJACENT_REP_PERIODS, self.model.HOURS
        # )
        # def Commitment_Tracking_Inter_Period_Constraint(model, resource, model_year, rep_period_1, rep_period_2, hour):
        #     """Track unit commitment status."""
        #     if hour == model.last_timepoint_of_period[model_year, rep_period_1][2]:
        #         hour_2 = model.first_timepoint_of_period[model_year, rep_period_2][2]
        #         return (
        #             model.Committed_Units[resource, model_year, rep_period_2, hour_2]
        #             == model.Committed_Units[resource, model_year, rep_period_1, hour]
        #             + model.Start_Units[resource, model_year, rep_period_2, hour_2]
        #             - model.Shutdown_Units[resource, model_year, rep_period_2, hour_2]
        #         )
        #     else:
        #         return pyo.Constraint.Skip

        @mark_pyomo_component
        @self.model.Constraint(self.model.UNIT_COMMITMENT_RESOURCES, self.model.TIMEPOINTS)
        def Min_Uptime_Constraint(model, resource, model_year, rep_period, hour):
            """Constrain minimum up time for unit commitment resources.

            TODO (2022-02-16): Think about whether up/downtime constraints can work over chrono periods.
                Current formulation calculates start/stops within each rep period, looping around itself.
                Treat hourly datasets differently from rep_periods with variable timesteps:
                For variable timesteps, may require longer up time if min_up_time falls between timesteps
            """
            tempsum = sum(
                self.temporal_settings.timesteps[(hour - t) % pyo.value(len(self.temporal_settings.timesteps))]
                for t in range(1, self._get(self.system.resources[resource].min_up_time) + 1)
            )
            if (tempsum) == self._get(self.system.resources[resource].min_up_time):
                return model.Committed_Units[resource, model_year, rep_period, hour] >= sum(
                    model.Start_Units[
                        resource, model_year, rep_period, (hour - t) % pyo.value(len(self.temporal_settings.timesteps))
                    ]
                    for t in range(1, self._get(self.system.resources[resource].min_up_time) + 1)
                )
            else:
                i = 1
                while self._get(self.system.resources[resource].min_up_time) >= i:
                    tempsum = sum(
                        self.temporal_settings.timesteps[(hour - t) % pyo.value(len(self.temporal_settings.timesteps))]
                        for t in range(1, i + 1)
                    )
                    i += 1

                return model.Committed_Units[resource, model_year, rep_period, hour] >= sum(
                    model.Start_Units[
                        resource, model_year, rep_period, (hour - t) % pyo.value(len(self.temporal_settings.timesteps))
                    ]
                    for t in range(1, i + 1)
                )

        @mark_pyomo_component
        @self.model.Constraint(self.model.UNIT_COMMITMENT_RESOURCES, self.model.TIMEPOINTS)
        def Min_Downtime_Constraint(model, resource, model_year, rep_period, hour):
            """Constrain minimum down time for unit commitment resources.
            Treat hourly datasets differently from rep_periods with variable timesteps:
            For variable timesteps, may require longer up time if min_up_time falls between timesteps
            """
            tempsum = sum(
                self.temporal_settings.timesteps[(hour - t) % pyo.value(len(self.temporal_settings.timesteps))]
                for t in range(1, self._get(self.system.resources[resource].min_up_time) + 1)
            )
            if (tempsum) == self._get(self.system.resources[resource].min_up_time):
                return model.Operational_Units_In_Timepoint[
                    resource, model_year, rep_period, hour
                ] - model.Committed_Units[resource, model_year, rep_period, hour] >= sum(
                    model.Shutdown_Units[
                        resource, model_year, rep_period, (hour - t) % pyo.value(len(self.temporal_settings.timesteps))
                    ]
                    for t in range(1, self._get(self.system.resources[resource].min_down_time) + 1)
                )
            else:
                i = 1
                while self._get(self.system.resources[resource].min_down_time) >= i:
                    tempsum = sum(
                        self.temporal_settings.timesteps[(hour - t) % pyo.value(len(self.temporal_settings.timesteps))]
                        for t in range(1, i + 1)
                    )
                    i += 1

                return model.Operational_Units_In_Timepoint[
                    resource, model_year, rep_period, hour
                ] - model.Committed_Units[resource, model_year, rep_period, hour] >= sum(
                    model.Shutdown_Units[
                        resource, model_year, rep_period, (hour - t) % pyo.value(len(self.temporal_settings.timesteps))
                    ]
                    for t in range(1, i + 1)
                )

        @mark_pyomo_component
        @self.model.Constraint(self.model.RESOURCES_WITH_STORAGE, self.model.TIMEPOINTS)
        def SOC_Intra_Anchoring_Constraint(model, resource, model_year, rep_period, hour):
            if (
                self.system.resources[resource].allow_inter_period_sharing
                and (model_year, rep_period, hour) == model.first_timepoint_of_period[model_year, rep_period]
            ):
                return model.SOC_Intra_Period[resource, model_year, rep_period, hour] == 0
            else:
                return pyo.Constraint.Skip

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_STORAGES, self.model.TIMEPOINTS)
        def Fuel_Storage_SOC_Intra_Anchoring_Constraint(model, fuel_storage, model_year, rep_period, hour):
            return self.system.fuel_storages[fuel_storage].Fuel_Storage_SOC_Intra_Anchoring_Constraint(
                model, model_year, rep_period, hour
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.RESOURCES_WITH_STORAGE, self.model.TIMEPOINTS)
        def SOC_Intra_Tracking_Constraint(model, resource, model_year, rep_period, hour):
            """
            Tracks status of charging in resources with storage.
            SOC represents the status at the beginning of the current timepoint.
            Therefore SOC[next tp] = SOC[current tp] - provide power[current tp] + increase load[current tp]

            If we are using the default representative/chronological period representation,
            this constraint does not apply for the last timepoint of an intra period:
                 1. Any energy left in the last tp is transferred to `Soc_Inter_Period` via `SOC_Inter_Tracking_Constraint`
                 2. `Soc_Intra_Period` in the first timepoint of each representative period is anchored to 0 by
                    `SOC_Intra_Anchoring_Constraint`

            If either of the following conditions is met, this constraint **does** create a SoC constraint to loop
            the last tp of a rep period to the first tp:
                 1. A resource is set to :py:attr:`new_modeling_toolkit.common.resource.Resource.allow_inter_period_sharing`==False
                 2. :py:attr:`new_modeling_toolkit.resolve.model_formulation.ResolveCase.rep_period_method`=="manual"

            Args:
                model:
                resource:
                timepoint:

            Returns:

            """

            if (model_year, rep_period, hour) == model.last_timepoint_of_period[model_year, rep_period]:
                return pyo.Constraint.Skip
            else:
                # TODO: add operating reserves & paired resource/EV energy taken offline related later
                charged_mwh = (
                    model.Increase_Load_MW[resource, model_year, rep_period, hour]
                    * self.temporal_settings.timesteps[hour]
                    * self.system.resources[resource].charging_efficiency
                )
                discharged_mwh = (
                    model.Provide_Power_MW[resource, model_year, rep_period, hour]
                    * self.temporal_settings.timesteps[hour]
                    / self.system.resources[resource].discharging_efficiency
                )
                return (
                    model.SOC_Intra_Period[
                        resource,
                        get_next_rep_timepoint(model_year, rep_period, hour),
                    ]
                    == apply_parasitic_loss(
                        model.SOC_Intra_Period[resource, model_year, rep_period, hour],
                        self._get(self.system.resources[resource].parasitic_loss),
                        self.temporal_settings.timesteps[hour],
                    )
                    + charged_mwh
                    - discharged_mwh
                )

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_STORAGES, self.model.TIMEPOINTS)
        def Fuel_Storage_SOC_Intra_Tracking_Constraint(model, fuel_storage, model_year, rep_period, hour):
            next_rep_timepoint = get_next_rep_timepoint(model_year, rep_period, hour)
            return self.system.fuel_storages[fuel_storage].Fuel_Storage_SOC_Intra_Tracking_Constraint(
                model,
                model_year,
                rep_period,
                hour,
                self.temporal_settings,
                next_rep_timepoint,
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.RESOURCES_WITH_STORAGE, self.model.MODEL_YEARS_AND_CHRONO_PERIODS)
        def SOC_Inter_Tracking_Constraint(model, resource, model_year, chrono_period):
            """
            Inter-period SOC should change depending on final intra-period SOC of previous chronological period.

            NOTE: The definition of "get_next_chrono_period" provides that the inter-period SOC of the final
            chronological period is linked to the inter-period SOC of the first chronological period; hence,
            this constraint also enforces the "annual looping" constraint
            """

            # Get next chronological period, current representative period, and final hour
            next_chrono_period = get_next_chrono_period(chrono_period=chrono_period, model_year=model_year)
            rep_period = chrono_to_rep_mapping(chrono_period=chrono_period, model_year=model_year)
            final_hour = max(model.HOURS)
            first_hour = min(model.HOURS)

            # Get charging/discharging in final hour of the chronological period
            charged_mwh = (
                model.Increase_Load_MW[resource, model_year, rep_period, final_hour]
                * self.system.resources[resource].charging_efficiency
            )
            discharged_mwh = (
                model.Provide_Power_MW[resource, model_year, rep_period, final_hour]
                / self.system.resources[resource].discharging_efficiency
            )

            return (
                model.SOC_Inter_Period[resource, model_year, next_chrono_period]
                == apply_parasitic_loss(
                    model.SOC_Inter_Period[resource, model_year, chrono_period],
                    self._get(self.system.resources[resource].parasitic_loss),
                    self.model.timepoints_per_period,
                )
                + apply_parasitic_loss(
                    model.SOC_Intra_Period[resource, model_year, rep_period, final_hour],
                    self._get(self.system.resources[resource].parasitic_loss),
                    1,
                )
                + charged_mwh
                - discharged_mwh
                - model.SOC_Intra_Period[resource, model_year, rep_period, first_hour]
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.RESOURCES_WITH_STORAGE, self.model.MODEL_YEARS_AND_CHRONO_PERIODS)
        def SOC_Inter_Zero_Constraint(model, resource, model_year, chrono_period):
            """
            Inter-period SOC should be 0 when inter-period sharing is turned off.
            """
            if self.system.resources[resource].allow_inter_period_sharing is False:
                return model.SOC_Inter_Period[resource, model_year, chrono_period] == 0
            else:
                return pyo.Constraint.Skip

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_STORAGES, self.model.MODEL_YEARS_AND_CHRONO_PERIODS)
        def Fuel_Storage_SOC_Inter_Zero_Constraint(model, fuel_storage, model_year, chrono_period):
            """
            Inter-period SOC should be 0 when inter-period sharing is turned off.
            """
            return self.system.fuel_storages[fuel_storage].Fuel_Storage_SOC_Inter_Zero_Constraint(
                model, model_year, chrono_period
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_STORAGES, self.model.MODEL_YEARS_AND_CHRONO_PERIODS)
        def Fuel_Storage_SOC_Inter_Tracking_Constraint(model, fuel_storage, model_year, chrono_period):
            next_chrono_period = get_next_chrono_period(chrono_period=chrono_period, model_year=model_year)
            rep_period = chrono_to_rep_mapping(chrono_period=chrono_period, model_year=model_year)
            return self.system.fuel_storages[fuel_storage].Fuel_Storage_SOC_Inter_Tracking_Constraint(
                model, model_year, chrono_period, next_chrono_period, rep_period
            )

        @mark_pyomo_component
        @self.model.Expression(
            self.model.RESOURCES_WITH_STORAGE, self.model.MODEL_YEARS_AND_CHRONO_PERIODS, self.model.HOURS
        )
        def SOC_Inter_Intra_Joint(model, resource, model_year, chrono_period, hour):
            """
            Track SOC in resources with storage in all timepoints.
            """
            rep_period = chrono_to_rep_mapping(chrono_period=chrono_period, model_year=model_year)
            return (
                model.SOC_Intra_Period[resource, model_year, rep_period, hour]
                + model.SOC_Inter_Period[resource, model_year, chrono_period]
            )

        @mark_pyomo_component
        @self.model.Constraint(
            self.model.RESOURCES_WITH_STORAGE, self.model.MODEL_YEARS_AND_CHRONO_PERIODS, self.model.HOURS
        )
        def SOC_Inter_Intra_Max_Constraint(model, resource, model_year, chrono_period, hour):
            """
            SOC cannot exceed storage's total MWh capacity devided by discharging efficiency, i.e. the full tank size.
            """
            rep_period = chrono_to_rep_mapping(chrono_period=chrono_period, model_year=model_year)
            return (
                model.SOC_Inter_Intra_Joint[resource, model_year, chrono_period, hour]
                <= model.Operational_Storage_In_Model_Year[resource, model_year]
                / self.system.resources[resource].discharging_efficiency
            )

        self.model.RESOURCES_WITH_STORAGE_SOC_MIN = pyo.Set(
            initialize=[r for r, obj in self.system.resources.items() if obj.state_of_charge_min is not None],
            within=self.model.RESOURCES_WITH_STORAGE
        )
        @mark_pyomo_component
        @self.model.Constraint(
            self.model.RESOURCES_WITH_STORAGE, self.model.MODEL_YEARS_AND_CHRONO_PERIODS, self.model.HOURS
        )
        def SOC_Inter_Intra_Min_Constraint(model, resource, model_year, chrono_period, hour):
            """
            SOC must be non-negative or constrained by soc_min.
            """
            return (
                model.SOC_Inter_Intra_Joint[resource, model_year, chrono_period, hour]
                >=
                model.Operational_Storage_In_Model_Year[resource, model_year] *
                self._get(self.system.resources[resource].state_of_charge_min, default_val=0)
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_STORAGES, self.model.MODEL_YEARS_AND_CHRONO_PERIODS, self.model.HOURS)
        def Fuel_Storage_SOC_Inter_Intra_Joint(model, fuel_storage, model_year, chrono_period, hour):
            rep_period = chrono_to_rep_mapping(chrono_period=chrono_period, model_year=model_year)
            return self.system.fuel_storages[fuel_storage].Fuel_Storage_SOC_Inter_Intra_Joint(
                model, model_year, chrono_period, hour, rep_period
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_STORAGES, self.model.MODEL_YEARS_AND_CHRONO_PERIODS, self.model.HOURS)
        def Fuel_Storage_SOC_Inter_Intra_Max_Constraint(model, fuel_storage, model_year, chrono_period, hour):
            return self.system.fuel_storages[fuel_storage].Fuel_Storage_SOC_Inter_Intra_Max_Constraint(
                model, model_year, chrono_period, hour
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_STORAGES, self.model.MODEL_YEARS_AND_CHRONO_PERIODS, self.model.HOURS)
        def Fuel_Storage_SOC_Inter_Intra_Min_Constraint(model, fuel_storage, model_year, chrono_period, hour):
            return self.system.fuel_storages[fuel_storage].Fuel_Storage_SOC_Inter_Intra_Min_Constraint(
                model, model_year, chrono_period, hour
            )

        ##################################################
        # RAMP RATE CONSTRAINTS                          #
        ##################################################
        # TODO (2021-09-21): Complete implementation of multi-hour ramps
        def get_ramp_MW(asset, attr, model_year, timepoint_1, timepoint_2):
            rep_period_1, hour_1 = timepoint_1[0], timepoint_1[1]
            rep_period_2, hour_2 = timepoint_2[0], timepoint_2[1]
            return (
                getattr(self.model, attr)[asset, model_year, rep_period_2, hour_2]
                - getattr(self.model, attr)[asset, model_year, rep_period_1, hour_1]
            )

        def get_ramp_rate_limit(asset, ramp_duration):
            if ramp_duration == 1:
                rr = self.system.assets[asset].ramp_rate
            elif ramp_duration == 2:
                rr = self.system.assets[asset].ramp_rate_2_hour
            elif ramp_duration == 3:
                rr = self.system.assets[asset].ramp_rate_3_hour
            elif ramp_duration == 4:
                rr = self.system.assets[asset].ramp_rate_4_hour
            return rr

        # TODO (2022-02-16): Reorder model_year, rep_periods in index
        @mark_pyomo_component
        @self.model.Constraint(
            self.model.RAMP_ASSET,
            self.model.MODEL_YEARS_AND_ADJACENT_REP_PERIODS,
            self.model.HOURS,
            self.model.RAMP_DURATIONS,
        )
        def Ramp_Rate_Inter_Period_UB_Constraint(
            model, asset, model_year, rep_period_1, rep_period_2, hour, ramp_duration
        ):
            if not self.system.plants[asset].allow_inter_period_sharing:
                return pyo.Constraint.Skip
            rr = get_ramp_rate_limit(asset, ramp_duration)
            next_day_hour = hour - model.timepoints_per_period + ramp_duration
            # next_day_hour < 0 --> hour not subject to inter-day constraint
            if rr is not None and next_day_hour >= 0:
                timepoint_1 = rep_period_1, hour
                timepoint_2 = rep_period_2, next_day_hour
                ramp_MW = get_ramp_MW(asset, "Asset_Net_Power_MW", model_year, timepoint_1, timepoint_2)

                if asset in model.UNIT_COMMITMENT_RESOURCES:
                    UB = (
                        rr
                        * self._get(self.system.resources[asset].unit_size_mw)
                        * (
                            model.Committed_Units[asset, model_year, rep_period_2, next_day_hour]
                            - model.Start_Units[asset, model_year, rep_period_2, next_day_hour]
                        )
                        - (
                            self._get(self.system.resources[asset].min_stable_level, slice_by=model_year)
                            * self._get(self.system.resources[asset].unit_size_mw)
                            * model.Shutdown_Units[asset, model_year, rep_period_2, next_day_hour]
                        )
                        + (
                            max(
                                self._get(self.system.resources[asset].min_stable_level, slice_by=model_year)
                                * self._get(self.system.resources[asset].unit_size_mw),
                                rr * self._get(self.system.resources[asset].unit_size_mw),
                            )
                            * model.Start_Units[asset, model_year, rep_period_2, next_day_hour]
                        )
                    )
                else:
                    UB = rr * model.Operational_Capacity_In_Model_Year[asset, model_year]
                return ramp_MW <= UB
            else:
                return pyo.Constraint.Skip

        @mark_pyomo_component
        @self.model.Constraint(
            self.model.RAMP_ASSET,
            self.model.MODEL_YEARS_AND_ADJACENT_REP_PERIODS,
            self.model.HOURS,
            self.model.RAMP_DURATIONS,
        )
        def Ramp_Rate_Inter_Period_LB_Constraint(
            model, asset, model_year, rep_period_1, rep_period_2, hour, ramp_duration
        ):
            if not self.system.plants[asset].allow_inter_period_sharing:
                return pyo.Constraint.Skip
            rr = get_ramp_rate_limit(asset, ramp_duration)
            next_day_hour = hour - model.timepoints_per_period + ramp_duration
            # next_day_hour < 0 --> hour not subject to inter-day constraint
            if rr is not None and next_day_hour >= 0:
                timepoint_1 = rep_period_1, hour
                timepoint_2 = rep_period_2, next_day_hour
                # Note: Down ramp is purposely flipped (t1 - t2)
                ramp_MW = get_ramp_MW(asset, "Asset_Net_Power_MW", model_year, timepoint_2, timepoint_1)

                if asset in model.UNIT_COMMITMENT_RESOURCES:
                    UB = (
                        rr
                        * self._get(self.system.resources[asset].unit_size_mw)
                        * (
                            model.Committed_Units[asset, model_year, rep_period_2, next_day_hour]
                            - model.Start_Units[asset, model_year, rep_period_2, next_day_hour]
                        )
                        - (
                            self._get(self.system.resources[asset].min_stable_level, slice_by=model_year)
                            * self._get(self.system.resources[asset].unit_size_mw)
                            * model.Start_Units[asset, model_year, rep_period_2, next_day_hour]
                        )
                        + (
                            max(
                                self._get(self.system.resources[asset].min_stable_level, slice_by=model_year)
                                * self._get(self.system.resources[asset].unit_size_mw),
                                rr * self._get(self.system.resources[asset].unit_size_mw),
                            )
                            * model.Shutdown_Units[asset, model_year, rep_period_2, next_day_hour]
                        )
                    )
                else:
                    UB = rr * model.Operational_Capacity_In_Model_Year[asset, model_year]

                return ramp_MW <= UB
            else:
                return pyo.Constraint.Skip

        @mark_pyomo_component
        @self.model.Constraint(self.model.RAMP_ASSET, self.model.TIMEPOINTS, self.model.RAMP_DURATIONS)
        def Ramp_Rate_Intra_Period_UB_Constraint(model, asset, model_year, rep_period, hour, ramp_duration):
            rr = get_ramp_rate_limit(asset, ramp_duration)
            if (
                (not self.system.plants[asset].allow_inter_period_sharing and rr is not None) or
                (hour <= model.last_timepoint_of_period[model_year, rep_period][2] - ramp_duration and rr is not None)
            ):
                next_hour = model.HOURS.nextw(hour, step=ramp_duration)
                timepoint_1 = rep_period, hour
                timepoint_2 = rep_period, next_hour
                ramp_MW = get_ramp_MW(asset, "Asset_Net_Power_MW", model_year, timepoint_1, timepoint_2)

                if asset in model.UNIT_COMMITMENT_RESOURCES:
                    UB = (
                        rr
                        * self._get(self.system.resources[asset].unit_size_mw)
                        * (
                            model.Committed_Units[asset, model_year, rep_period, next_hour]
                            - model.Start_Units[asset, model_year, rep_period, next_hour]
                        )
                        - (
                            self._get(self.system.resources[asset].min_stable_level, slice_by=model_year)
                            * self._get(self.system.resources[asset].unit_size_mw)
                            * model.Shutdown_Units[asset, model_year, rep_period, next_hour]
                        )
                        + (
                            max(
                                self._get(self.system.resources[asset].min_stable_level, slice_by=model_year)
                                * self._get(self.system.resources[asset].unit_size_mw),
                                rr * self._get(self.system.resources[asset].unit_size_mw),
                            )
                            * model.Start_Units[asset, model_year, rep_period, next_hour]
                        )
                    )
                else:
                    UB = rr * model.Operational_Capacity_In_Model_Year[asset, model_year]
                return ramp_MW <= UB
            else:
                return pyo.Constraint.Skip

        @mark_pyomo_component
        @self.model.Constraint(self.model.RAMP_ASSET, self.model.TIMEPOINTS, self.model.RAMP_DURATIONS)
        def Ramp_Rate_Intra_Period_LB_Constraint(model, asset, model_year, rep_period, hour, ramp_duration):
            rr = get_ramp_rate_limit(asset, ramp_duration)
            if (
                (not self.system.plants[asset].allow_inter_period_sharing and rr is not None) or
                (hour <= model.last_timepoint_of_period[model_year, rep_period][2] - ramp_duration and rr is not None)
            ):
                next_hour = model.HOURS.nextw(hour, step=ramp_duration)
                timepoint_1 = rep_period, hour
                timepoint_2 = rep_period, next_hour
                # Note: Down ramp is purposely flipped (t1 - t2)
                ramp_MW = get_ramp_MW(asset, "Asset_Net_Power_MW", model_year, timepoint_2, timepoint_1)

                if asset in model.UNIT_COMMITMENT_RESOURCES:
                    UB = (
                        rr
                        * self._get(self.system.resources[asset].unit_size_mw)
                        * (
                            model.Committed_Units[asset, model_year, rep_period, next_hour]
                            - model.Start_Units[asset, model_year, rep_period, next_hour]
                        )
                        - (
                            self._get(self.system.resources[asset].min_stable_level, slice_by=model_year)
                            * self._get(self.system.resources[asset].unit_size_mw)
                            * model.Start_Units[asset, model_year, rep_period, next_hour]
                        )
                        + (
                            max(
                                self._get(self.system.resources[asset].min_stable_level, slice_by=model_year)
                                * self._get(self.system.resources[asset].unit_size_mw),
                                rr * self._get(self.system.resources[asset].unit_size_mw),
                            )
                            * model.Shutdown_Units[asset, model_year, rep_period, next_hour]
                        )
                    )
                else:
                    UB = rr * model.Operational_Capacity_In_Model_Year[asset, model_year]

                return ramp_MW <= UB
            else:
                return pyo.Constraint.Skip

        ##################################################
        # ZONAL BALANCE CONSTRAINTS                      #
        ##################################################

        self.model.Fuel_Zone_Candidate_Fuel_Commodity_Production_In_Timepoint_MMBTU_H = pyo.Var(
            self.model.FUEL_ZONES,
            self.model.CANDIDATE_FUELS,
            self.model.TIMEPOINTS,
            units=pyo.units.MBtu / pyo.units.H,
            within=pyo.NonNegativeReals,
        )

        @mark_pyomo_component
        @self.model.Constraint(self.model.ZONES, self.model.TIMEPOINTS)
        def Zonal_Power_Balance_Constraint(model, zone, model_year, rep_period, hour):
            """The sum of all in-zone power production and net transmission flow equals the zone's load in each timepoint.
            Resources may increase load; the demand from these resources is added to the zone's load in each timepoint.
            resources with storage both increase load and provide power, and are therefore included on both sides of the constraint.
            Two slack variables for unserved energy and overgeneration are included.
            Scheduled curtailment is not explicitly included here because Provide_Power_MW
            will be less than the resource's potential power production during times of scheduled curtailment

            Args:
              model:
              timepoint:
              zone:

            Returns:

            """
            # TODO: missing dedicated transmission
            imports_exports = 0.0
            for line in model.TRANSMISSION_LINES:
                if model.transmission_to[line] == zone or model.transmission_from[line] == zone:
                    if model.transmission_to[line] == zone:
                        imports_exports += model.Transmit_Power_MW[line, model_year, rep_period, hour]
                    elif model.transmission_from[line] == zone:
                        imports_exports -= model.Transmit_Power_MW[line, model_year, rep_period, hour]

            # TODO: needs more working when adding more info later
            return (
                model.Zonal_Provide_Power_MW[zone, model_year, rep_period, hour]
                + imports_exports
                + model.Unserved_Energy_MW[zone, model_year, rep_period, hour]
                - model.Overgen_MW[zone, model_year, rep_period, hour]
                == model.input_load_mw[zone, model_year, rep_period, hour]
                + model.Zonal_Increase_Load_MW[zone, model_year, rep_period, hour]
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_ZONES, self.model.CANDIDATE_FUELS, self.model.TIMEPOINTS)
        def Net_Candidate_Fuel_Imports_In_Timepoint_MMBTU_H(
            model, fuel_zone, candidate_fuel, model_year, rep_period, hour
        ):
            return self.system.fuel_zones[fuel_zone].Net_Candidate_Fuel_Imports_In_Timepoint_MMBTU_H(
                self, candidate_fuel, model_year, rep_period, hour
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_ZONES, self.model.CANDIDATE_FUELS, self.model.TIMEPOINTS)
        def Fuel_Zone_Candidate_Fuel_Production_In_Timepoint_MMBTU_H(
            model, fuel_zone, candidate_fuel, model_year, rep_period, hour
        ):
            return self.system.fuel_zones[fuel_zone].Fuel_Zone_Candidate_Fuel_Production_In_Timepoint_MMBTU_H(
                model, candidate_fuel, model_year, rep_period, hour
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_ZONES, self.model.CANDIDATE_FUELS, self.model.TIMEPOINTS)
        def Fuel_Zone_Resource_Candidate_Fuel_Consumption_In_Timepoint_MMBTU_H(
            model, fuel_zone, candidate_fuel, model_year, rep_period, hour
        ):
            return self.system.fuel_zones[fuel_zone].Fuel_Zone_Resource_Candidate_Fuel_Consumption_In_Timepoint_MMBTU_H(
                model, candidate_fuel, model_year, rep_period, hour
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_ZONES, self.model.CANDIDATE_FUELS, self.model.TIMEPOINTS)
        def Fuel_Zone_Candidate_Fuel_Storage_In_Timepoint_MMBTU_H(
            model, fuel_zone, candidate_fuel, model_year, rep_period, hour
        ):
            return self.system.fuel_zones[fuel_zone].Fuel_Zone_Candidate_Fuel_Storage_In_Timepoint_MMBTU_H(
                model, candidate_fuel, model_year, rep_period, hour, self.temporal_settings
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_ZONES, self.model.CANDIDATE_FUELS, self.model.TIMEPOINTS)
        def Net_Fuel_Zone_Candidate_Fuel_Consumption_In_Timepoint_MMBTU_H(
            model, fuel_zone, candidate_fuel, model_year, rep_period, hour
        ):
            return self.system.fuel_zones[fuel_zone].Net_Fuel_Zone_Candidate_Fuel_Consumption_In_Timepoint_MMBTU_H(
                model,
                candidate_fuel,
                model_year,
                rep_period,
                hour,
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_ZONES, self.model.CANDIDATE_FUELS, self.model.TIMEPOINTS)
        def Candidate_Fuel_Fuel_Zone_Commodity_Production_Constraint(
            model, fuel_zone, candidate_fuel, model_year, rep_period, hour
        ):
            if not self.system.candidate_fuels[candidate_fuel].fuel_is_commodity_bool:
                return (
                    model.Fuel_Zone_Candidate_Fuel_Commodity_Production_In_Timepoint_MMBTU_H[
                        fuel_zone, candidate_fuel, model_year, rep_period, hour
                    ]
                    == 0
                )
            else:
                return pyo.Constraint.Skip

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_ZONES, self.model.CANDIDATE_FUELS, self.model.TIMEPOINTS)
        def Fuel_Zone_Candidate_Fuel_Constraint(model, fuel_zone, candidate_fuel, model_year, rep_period, hour):
            """
            Ensures that net hourly inflows of candidate fuels into fuel zone is at least as great as net
            consumption of candidate fuels. Excess candidate fuels inflows will be applied to annual final fuel demands
            in another constraint.
            """

            return self.system.fuel_zones[fuel_zone].Fuel_Zone_Candidate_Fuel_Constraint(
                model, candidate_fuel, model_year, rep_period, hour
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_ZONES, self.model.CANDIDATE_FUELS, self.model.MODEL_YEARS)
        def Annual_Fuel_Zone_Candidate_Fuel_Production_MMBTU(model, fuel_zone, candidate_fuel, model_year):
            return self.sum_timepoint_to_annual(
                model_year,
                "Fuel_Zone_Candidate_Fuel_Production_In_Timepoint_MMBTU_H",
                fuel_zone,
                candidate_fuel,
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_ZONES, self.model.CANDIDATE_FUELS, self.model.MODEL_YEARS)
        def Annual_Net_Candidate_Fuel_Imports_MMBTU(model, fuel_zone, candidate_fuel, model_year):
            return self.sum_timepoint_to_annual(
                model_year, "Net_Candidate_Fuel_Imports_In_Timepoint_MMBTU_H", fuel_zone, candidate_fuel
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_ZONES, self.model.CANDIDATE_FUELS, self.model.MODEL_YEARS)
        def Annual_Net_Fuel_Zone_Candidate_Fuel_Consumption_MMBTU(model, fuel_zone, candidate_fuel, model_year):
            return self.sum_timepoint_to_annual(
                model_year, "Net_Fuel_Zone_Candidate_Fuel_Consumption_In_Timepoint_MMBTU_H", fuel_zone, candidate_fuel
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_ZONES, self.model.CANDIDATE_FUELS, self.model.MODEL_YEARS)
        def Annual_Fuel_Zone_Candidate_Fuel_Storage_MMBTU(model, fuel_zone, candidate_fuel, model_year):
            return self.sum_timepoint_to_annual(
                model_year,
                "Fuel_Zone_Candidate_Fuel_Storage_In_Timepoint_MMBTU_H",
                fuel_zone,
                candidate_fuel,
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_ZONES, self.model.CANDIDATE_FUELS, self.model.MODEL_YEARS)
        def Annual_Fuel_Zone_Resource_Candidate_Fuel_Consumption_MMBTU(model, fuel_zone, candidate_fuel, model_year):
            return self.sum_timepoint_to_annual(
                model_year,
                "Fuel_Zone_Resource_Candidate_Fuel_Consumption_In_Timepoint_MMBTU_H",
                fuel_zone,
                candidate_fuel,
            )

        @mark_pyomo_component
        @self.model.Expression(
            self.model.FUEL_ZONES,
            self.model.CANDIDATE_FUELS,
            self.model.FINAL_FUEL_DEMANDS,
            self.model.MODEL_YEARS,
        )
        def Annual_Fuel_Zone_Candidate_Fuel_Consumption_By_Final_Fuel_Demands_MMBTU(
            model, fuel_zone, candidate_fuel, final_fuel_demand, model_year
        ):
            return self.sum_timepoint_to_annual(
                model_year,
                "Fuel_Zone_Candidate_Fuel_Consumption_By_Final_Fuel_Demands_MMBTU_H",
                fuel_zone,
                candidate_fuel,
                final_fuel_demand,
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_ZONES, self.model.CANDIDATE_FUELS, self.model.MODEL_YEARS)
        def Annual_Fuel_Zone_Candidate_Fuel_Consumption_For_Final_Fuel_Demands_MMBTU(
            model, fuel_zone, candidate_fuel, model_year
        ):
            return self.system.fuel_zones[
                fuel_zone
            ].Annual_Fuel_Zone_Candidate_Fuel_Consumption_For_Final_Fuel_Demands_MMBTU(
                model, candidate_fuel, model_year
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_ZONES, self.model.CANDIDATE_FUELS, self.model.MODEL_YEARS)
        def Annual_Fuel_Zone_Candidate_Fuel_Balance(model, fuel_zone, candidate_fuel, model_year):
            return self.system.fuel_zones[fuel_zone].Annual_Fuel_Zone_Candidate_Fuel_Balance(
                model, candidate_fuel, model_year
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_ZONES, self.model.FINAL_FUEL_DEMANDS, self.model.TIMEPOINTS)
        def Satisfy_Fuel_Zone_Final_Fuel_Hourly_Demands_Constraint(
            model, fuel_zone, final_fuel_demand, model_year, rep_period, hour
        ):
            """
            Ensures that annual zonal final fuel demands are met by candidate fuel consumption for final fuel demands.
            """
            if model.FINAL_FUEL_DEMAND_CANDIDATE_FUELS[final_fuel_demand] and (
                self.system.fuel_zones[fuel_zone].final_fuels is not None
                and final_fuel_demand in self.system.fuel_zones[fuel_zone].final_fuels.keys()
                and self.system.final_fuels[final_fuel_demand].demand.freq == pd.offsets.Hour()
            ):
                constraint = self.system.fuel_zones[fuel_zone].Satisfy_Fuel_Zone_Final_Fuel_Hourly_Demands_Constraint(
                    temporal_settings=self.temporal_settings,
                    model=model,
                    final_fuel_demand=final_fuel_demand,
                    model_year=model_year,
                    rep_period=rep_period,
                    hour=hour,
                )
            else:
                constraint = pyo.Constraint.Skip

            return constraint

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_ZONES, self.model.FINAL_FUEL_DEMANDS, self.model.MODEL_YEARS)
        def Satisfy_Fuel_Zone_Final_Fuel_Annual_Demands_Constraint(model, fuel_zone, final_fuel_demand, model_year):
            """
            Ensures that annual zonal final fuel demands are met by candidate fuel consumption for final fuel demands.
            """
            if model.FINAL_FUEL_DEMAND_CANDIDATE_FUELS[final_fuel_demand] and (
                self.system.fuel_zones[fuel_zone].final_fuels is not None
                and final_fuel_demand in self.system.fuel_zones[fuel_zone].final_fuels.keys()
                and self.system.final_fuels[final_fuel_demand].demand.freq == pd.offsets.YearBegin()
            ):
                constraint = self.system.fuel_zones[fuel_zone].Satisfy_Fuel_Zone_Final_Fuel_Annual_Demands_Constraint(
                    model=model, final_fuel_demand=final_fuel_demand, model_year=model_year
                )
            else:
                constraint = pyo.Constraint.Skip

            return constraint

        # Operating reserves
        @mark_pyomo_component
        @self.model.Expression(self.model.RESERVES, self.model.TIMEPOINTS)
        def Operating_Reserve_Requirement(model, reserve, model_year, rep_period, hour):
            """The calculated operating reserve requirement, including increment reserve needs."""
            return (
                # flat requirement
                self._get(self.system.reserves[reserve].requirement, slice_by=(model_year, rep_period, hour), default_val=0) +
                # incremental requirement from zonal gross loads
                sum(
                    self._get(zone.incremental_requirement_hourly_scalar, slice_by=(model_year, rep_period, hour)) *
                    model.input_load_mw[zone._instance_to.name, model_year, rep_period, hour]
                    for zone in self.system.reserves[reserve].zones.values()
                ) +
                # incremental requirement from load components
                sum(
                    self._get(load.incremental_requirement_hourly_scalar, slice_by=(model_year, rep_period, hour)) *
                    self._get(load._instance_from.profile, slice_by=(model_year, rep_period, hour))
                    for load in self.system.reserves[reserve].loads.values()
                ) +
                # increment requirement from resources
                sum(
                    self._get(resource.incremental_requirement_hourly_scalar, slice_by=(model_year, rep_period, hour)) *
                    (
                        self._get(resource._instance_from.provide_power_potential_profile, slice_by=(model_year, rep_period, hour))
                        if resource.scalar_type == IncrementalReserveType.HOURLY_PROFILE
                        else model.Operational_Capacity_In_Model_Year[resource._instance_from.name, model_year]
                    )
                    for resource in self.system.reserves[reserve].resources.values()
                )
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.RESERVES, self.model.TIMEPOINTS)
        def Operating_Reserve_Balance_Constraint(model, reserve, model_year, rep_period, hour):
            """Operating reserve requirements must be met by eligible resources on the system.

            If a ``LoadToReserve.incremental_requirement_hourly_scalar`` is defined, this requirement will override
            any ``Reserve.requirement``. For now, this is calculated in the Pyomo model, but this seems like
            it could be calculated as a property of the ``Reserve`` instance.
            """
            return (
                sum(
                    model.Provide_Reserve_MW[resource, reserve, model_year, rep_period, hour]
                    for resource in self.system.reserves[reserve].resources.keys()
                ) +
                model.Unserved_Reserve_MW[reserve, model_year, rep_period, hour]
                ==
                model.Operating_Reserve_Requirement[reserve, model_year, rep_period, hour]
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.TRANSMISSION_LINES, self.model.TIMEPOINTS)
        def Transmission_Min_Flow_Constraint(model, line, model_year, rep_period, hour):
            """Transmission flows must obey flow limits on each line."""
            return model.Transmit_Power_MW[line, model_year, rep_period, hour] >= (
                model.Operational_Capacity_In_Model_Year[line, model_year]
                * -1
                * self._get(self.system.tx_paths[line].reverse_rating_profile, slice_by=(model_year, rep_period, hour))
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.TRANSMISSION_LINES, self.model.TIMEPOINTS)
        def Transmission_Max_Flow_Constraint(model, line, model_year, rep_period, hour):
            """Transmission flows must obey flow limits on each line."""
            return model.Transmit_Power_MW[line, model_year, rep_period, hour] <= (
                model.Operational_Capacity_In_Model_Year[line, model_year]
                * self._get(self.system.tx_paths[line].forward_rating_profile, slice_by=(model_year, rep_period, hour))
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.TRANSMISSION_LINES, self.model.TIMEPOINTS)
        def Transmit_Power_Rule_Forward(model, line, model_year, rep_period, hour):
            return (
                model.Transmit_Power_Forward_MW[line, model_year, rep_period, hour]
                >= model.Transmit_Power_MW[line, model_year, rep_period, hour]
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.TRANSMISSION_LINES, self.model.TIMEPOINTS)
        def Transmit_Power_Rule_Reverse(model, line, model_year, rep_period, hour):
            return (
                model.Transmit_Power_Reverse_MW[line, model_year, rep_period, hour]
                >= -model.Transmit_Power_MW[line, model_year, rep_period, hour]
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_TRANSPORTATIONS, self.model.TIMEPOINTS)
        def Fuel_Transportation_Min_Flow_Constraint(model, fuel_transportation, model_year, rep_period, hour):
            return self.system.fuel_transportations[fuel_transportation].Fuel_Transportation_Min_Flow_Constraint(
                model, self.temporal_settings, model_year, rep_period, hour
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_TRANSPORTATIONS, self.model.TIMEPOINTS)
        def Fuel_Transportation_Max_Flow_Constraint(model, fuel_transportation, model_year, rep_period, hour):
            return self.system.fuel_transportations[fuel_transportation].Fuel_Transportation_Max_Flow_Constraint(
                model, self.temporal_settings, model_year, rep_period, hour
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_TRANSPORTATIONS, self.model.TIMEPOINTS)
        def Fuel_Transportation_Transmit_Candidate_Fuel_Rule_Forward(
            model, fuel_transportation, model_year, rep_period, hour
        ):
            return self.system.fuel_transportations[
                fuel_transportation
            ].Fuel_Transportation_Transmit_Candidate_Fuel_Rule_Forward(model, model_year, rep_period, hour)

        @mark_pyomo_component
        @self.model.Constraint(self.model.FUEL_TRANSPORTATIONS, self.model.TIMEPOINTS)
        def Fuel_Transportation_Transmit_Candidate_Fuel_Rule_Reverse(
            model, fuel_transportation, model_year, rep_period, hour
        ):
            return self.system.fuel_transportations[
                fuel_transportation
            ].Fuel_Transportation_Transmit_Candidate_Fuel_Rule_Reverse(model, model_year, rep_period, hour)

        ##################################################
        # POLICY CONSTRAINTS                             #
        ##################################################

        ###################### POLICY CONSTRAINTS ###########################
        # TODO (2021-12-09): This should be next to NQC/ELCC expressions
        @mark_pyomo_component
        @self.model.Expression(self.model.POLICIES_BY_TYPE["emissions"], self.model.MODEL_YEARS)
        def Emissions_Constraint_LHS(model, emissions_policy, model_year):
            """Calculate emissions from final fuel demands, resources, and unspecified transmission imports."""
            # TODO JLC 01/13/2023 emissions only sector emissions need to be added for this to be economy wide
            # TODO (2021-12-09): May be better to have expressions for each of these
            final_fuel_demand_emissions = sum(
                sum(
                    self._get(self.system.policies[emissions_policy].candidate_fuels[candidate_fuel].multiplier)
                    * model.Annual_Candidate_Fuel_Consumption_By_Final_Fuel_Demands[candidate_fuel, demand, model_year]
                    for candidate_fuel in model.FINAL_FUEL_DEMAND_CANDIDATE_FUELS[demand]
                    if candidate_fuel in self.system.policies[emissions_policy].candidate_fuels.keys()
                )
                for demand in model.POLICY_FINAL_FUEL_DEMANDS[emissions_policy]
            )

            resource_emissions = sum(
                model.Annual_Resource_Emissions_In_Policy[resource, emissions_policy, model_year]
                for resource in self.system.policies[emissions_policy].resources.keys()
            )

            # get import & export emissions
            tx_emissions = sum(
                model.Annual_Transmission_Emissions_In_Policy[tx_path, emissions_policy, model_year]
                for tx_path in self.system.policies[emissions_policy].tx_paths.keys()
            )

            return final_fuel_demand_emissions + resource_emissions + tx_emissions

        @mark_pyomo_component
        @self.model.Expression(self.model.POLICIES_BY_TYPE["energy"], self.model.RESOURCES, self.model.MODEL_YEARS)
        def Energy_Policy_Annual_Contribution_By_Resource(model, policy, resource, model_year):
            if resource not in self.system.policies[policy].resources:
                return 0
            return (
                self._get(self.system.policies[policy].resources[resource].multiplier, slice_by=model_year)
                * model.Annual_Provide_Power[resource, model_year]
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.POLICIES_BY_TYPE["energy"], self.model.MODEL_YEARS)
        def Energy_Constraint_LHS(model, policy, model_year):
            """Calculate sum of energy contributing to annual energy policy (e.g., RPS, CES)."""
            # return sum(
            #     self._get(self.system.policies[policy].resources[resource].multiplier, slice_by=model_year) *
            #     model.Annual_Provide_Power[resource, model_year]
            #     for resource in self.system.policies[policy].resources.keys()
            # )
            return sum(
                model.Energy_Policy_Annual_Contribution_By_Resource[policy, resource, model_year]
                for resource in self.system.policies[policy].resources.keys()
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.POLICIES, self.model.MODEL_YEARS)
        def Policy_LHS(model, policy, model_year):
            """Construct policy constraints.

            If target is inf/-inf, the policy constraint will not be constructed.
            """
            if self._get(self.system.policies[policy].target, slice_by=model_year) in [
                float("+inf"),
                float("-inf"),
            ]:
                return pyo.Constraint.Skip

            # TODO (2021-12-09): Should we consolidate LHS expressions? Probably better to keep them separate?
            if self.system.policies[policy].type == "emissions":
                lhs = model.Emissions_Constraint_LHS[policy, model_year]
            elif self.system.policies[policy].type == "energy":
                lhs = model.Energy_Constraint_LHS[policy, model_year]
            elif self.system.policies[policy].type == "prm":
                lhs = model.NQC_LHS[policy, model_year] + model.ELCC_LHS[policy, model_year]
                # TODO: Add tx reliability contribution
            else:
                raise ValueError(f"Policy {policy} type {self.system.policies[policy].type} not recognized.")

            return lhs

        self.model.Policy_Slack = pyo.Var(self.model.POLICIES, self.model.MODEL_YEARS, within=pyo.NonNegativeReals)

        @mark_pyomo_component
        @self.model.Constraint(self.model.POLICIES, self.model.MODEL_YEARS)
        def Policy_Constraint(model, policy, model_year):
            """Construct policy constraints.

            If target is inf/-inf, the policy constraint will not be constructed.
            """
            if self.production_simulation_mode and self.system.policies[policy].type == "prm":
                logger.warning(f"Disabling PRM policy `{policy}` for production simulation mode")
                return pyo.Constraint.Skip

            if self.system.policies[policy].target is None:
                return pyo.Constraint.Skip

            policy_target_adjusted = self._get(self.system.policies[policy].target, slice_by=model_year) + self._get(
                self.system.policies[policy].target_adjustment, slice_by=model_year
            )

            # Construct >=, ==, or <= constraints, as defined by user.
            if self.system.policies[policy].constraint_operator == ConstraintOperator.LESS_THAN_OR_EQUAL_TO:
                return model.Policy_LHS[policy, model_year]\
                    <= policy_target_adjusted + model.Policy_Slack[policy, model_year]
            elif self.system.policies[policy].constraint_operator == ConstraintOperator.EQUAL_TO:
                return model.Policy_LHS[policy, model_year]\
                    == policy_target_adjusted
            elif self.system.policies[policy].constraint_operator == ConstraintOperator.GREATER_THAN_OR_EQUAL_TO:
                return model.Policy_LHS[policy, model_year]\
                    >= policy_target_adjusted - model.Policy_Slack[policy, model_year]
            else:
                raise ValueError(f"Policy operator {self.system.policies[policy].constraint_operator}")

        self.model.blocks = pyo.Block(pyo.Set(initialize=sorted(self.system.hourly_energy_policies.keys())))
        for policy in self.system.hourly_energy_policies.values():
            logger.info(f"Constructing hourly CES policy: {policy}")
            policy.construct_constraints(self.model, self.temporal_settings)

        ##################################################
        # CUSTOM CONSTRAINTS                             #
        ##################################################
        self.model.Custom_Constraint_Slack_Up = pyo.Var(self.model.CUSTOM_CONSTRAINTS, within=pyo.NonNegativeReals)
        self.model.Custom_Constraint_Slack_Down = pyo.Var(self.model.CUSTOM_CONSTRAINTS, within=pyo.NonNegativeReals)
        @mark_pyomo_component
        @self.model.Constraint(self.model.CUSTOM_CONSTRAINTS)
        def Custom_Constraint(model, constraint_ID):
            """Create custom constraints.

            Also does wildcard parsing, as only after full model is constructed (e.g., all sets), can we do
            wildcard parsing fully.

            This custom constraint works because we just need to be passing a tuple in the correct order as an index
            to any Pyomo model component, so we do this through `getattr()[idx]`.
            """
            # lhs_sum keeps track of all things being summed in the left hand side
            lhs = 0

            # get operator and right hand side
            operator = self.custom_constraints[constraint_ID].operator
            rhs = self.custom_constraints[constraint_ID].target

            if rhs in [
                float("+inf"),
                float("-inf"),
            ]:
                return pyo.Constraint.Skip

            # iterate through each variable and its index combinations to be included
            for component_name, lhs_df in self.custom_constraints[constraint_ID].LHS.items():
                # TODO: Check that the user has used proper column name for each index. Send warning.

                cmp = getattr(model, component_name)

                for _, row in lhs_df.iterrows():
                    # separate each row into index and multiplier information
                    multiplier = row.iloc[-1]
                    indices = row.iloc[:-1]

                    # If any index has a "*" wildcard, user itertools.product to create all possible indices
                    if "*" in indices.values:
                        expanded_wildcard_indices = list(
                            itertools.product(
                                *[
                                    [idx for idx in getattr(model, r)] if indices[r] == "*" else [indices[r]]
                                    for r in indices.index
                                ]
                            )
                        )
                        # TODO (2021-12-14) There probably is a more performant way to figure out whether
                        #  `expanded_wildcard_indices` has any entries that aren't in the `cmp` index
                        for idx in expanded_wildcard_indices:
                            # If index in variable index, add to LHS
                            if idx in cmp:
                                lhs += cmp[idx] * multiplier

                    else:
                        # If index in variable index, add to LHS
                        if tuple(indices) in cmp:
                            lhs += cmp[tuple(indices)] * multiplier

            # If none of the components in the custom constraint were added to the LHS (e.g., all for the wrong model year)
            if isinstance(lhs, int):
                return pyo.Constraint.Skip

            # Finally, construct the (in-)equality constraint
            logger.debug(f"Writing custom constraint {constraint_ID}")
            if operator in ["<=", "lt"]:
                return lhs - model.Custom_Constraint_Slack_Down[constraint_ID] <= rhs
            elif operator in ["==", "eq"]:
                return lhs + model.Custom_Constraint_Slack_Up[constraint_ID] - model.Custom_Constraint_Slack_Down[constraint_ID] == rhs
            else:
                return lhs + model.Custom_Constraint_Slack_Up[constraint_ID] >= rhs

        ##################################################
        # FUEL CONSTRAINTS                               #
        ##################################################
        @mark_pyomo_component
        @self.model.Constraint(self.model.RESOURCES, self.model.TIMEPOINTS)
        def Resource_Fuel_Consumption_Constraint(model, resource, model_year, rep_period, hour):
            """The sum of the power provided by a resource's candidate fuels should
            equal the resource's total Provide_Power_MW."""
            # TODO (6/8): This constraint doesn't seem quite right. Come back to this.
            if model.RESOURCE_CANDIDATE_FUELS[resource]:
                linearized_fuel_burn = (
                    self._get(self.system.resources[resource].fuel_burn_slope)
                    * model.Provide_Power_MW[resource, model_year, rep_period, hour]
                )
                if resource in model.UNIT_COMMITMENT_RESOURCES:
                    commitment_fuel_burn = model.Committed_Units[resource, model_year, rep_period, hour] * self._get(
                        self.system.resources[resource].fuel_burn_intercept
                    )
                    start_fuel_use = model.Start_Units[resource, model_year, rep_period, hour] * self._get(
                        self.system.resources[resource].start_fuel_use
                    )
                else:
                    commitment_fuel_burn = 0
                    start_fuel_use = 0

                return linearized_fuel_burn + commitment_fuel_burn + start_fuel_use == sum(
                    model.Resource_Fuel_Consumption_In_Timepoint_MMBTU[resource, fuel, model_year, rep_period, hour]
                    for fuel in model.RESOURCE_CANDIDATE_FUELS[resource]
                )
            else:
                return pyo.Constraint.Skip

        @mark_pyomo_component
        @self.model.Constraint(self.model.FINAL_FUEL_DEMANDS, self.model.MODEL_YEARS)
        def Satisfy_Final_Fuel_Demands_Constraint(model, final_fuel_demand, model_year):
            """
            The sum of candidate fuel consumption for each final fuel demand should be greater than or equal the demand.
            """
            if model.FINAL_FUEL_DEMAND_CANDIDATE_FUELS[final_fuel_demand]:
                return sum(
                    model.Annual_Candidate_Fuel_Consumption_By_Final_Fuel_Demands[
                        candidate_fuel, final_fuel_demand, model_year
                    ]
                    for candidate_fuel in model.FINAL_FUEL_DEMAND_CANDIDATE_FUELS[final_fuel_demand]
                ) == self.system.final_fuels[final_fuel_demand].demand.slice_by_year(model_year)
            else:
                return pyo.Constraint.Skip

        @mark_pyomo_component
        @self.model.Constraint(
            self.model.FINAL_FUEL_DEMANDS,
            self.model.CANDIDATE_FUELS,
            self.model.MODEL_YEARS,
        )
        def Final_Fuel_Demand_Blend_Limit_Constraint(model, final_fuel_demand, candidate_fuel, model_year):
            """
            Candidate fuel consumption by final fuel demands must not exceed blend limit.
            """
            if model.FINAL_FUEL_DEMAND_CANDIDATE_FUELS[final_fuel_demand] and (
                candidate_fuel in model.FINAL_FUEL_DEMAND_CANDIDATE_FUELS[final_fuel_demand]
            ):
                return model.Annual_Candidate_Fuel_Consumption_By_Final_Fuel_Demands[
                    candidate_fuel, final_fuel_demand, model_year
                ] <= (
                    self.system.final_fuels[final_fuel_demand].demand.slice_by_year(model_year)
                    * (
                        self.system.candidate_fuels[candidate_fuel]
                        .final_fuels[final_fuel_demand]
                        .blend_limit_fraction.slice_by_year(model_year)
                    )
                )
            else:
                return pyo.Constraint.Skip

        @mark_pyomo_component
        @self.model.Constraint(self.model.CANDIDATE_FUELS, self.model.MODEL_YEARS)
        def Candidate_Fuel_Supply_Demand_Balance_Constraint(model, candidate_fuel, model_year):
            """
            supply for candidate fuels must be >= demand (consumption)
            """
            candidate_fuel_supply = (
                model.Candidate_Fuel_Commodity_Production_MMBTU[candidate_fuel, model_year]
                + model.Candidate_Fuel_Production_From_Biomass_MMBTU[candidate_fuel, model_year]
                + model.Candidate_Fuel_Production_From_Fuel_Production_Plants_MMBTU[candidate_fuel, model_year]
            )
            return candidate_fuel_supply >= model.Total_Annual_Candidate_Fuel_Consumption[candidate_fuel, model_year]

        @mark_pyomo_component
        @self.model.Constraint(self.model.CANDIDATE_FUELS, self.model.MODEL_YEARS)
        def Candidate_Fuel_Commodity_Production_Constraint(model, candidate_fuel, model_year):
            """
            Production from commodity sources (aka x amount of fuel at y price) must be restricted by the input
            fuel_is_commodity_bool.
            """
            return model.Candidate_Fuel_Commodity_Production_MMBTU[
                candidate_fuel, model_year
            ] <= model.Total_Annual_Candidate_Fuel_Consumption[candidate_fuel, model_year] * self._get(
                int(self.system.candidate_fuels[candidate_fuel].fuel_is_commodity_bool)
            )

        @mark_pyomo_component
        @self.model.Constraint(self.model.CANDIDATE_FUELS, self.model.MODEL_YEARS)
        def Candidate_Fuel_Production_Limit_Constraint(model, candidate_fuel, model_year):
            """
            Constrain total candidate fuel production in a year by the production limit input.
            """
            if self.system.candidate_fuels[candidate_fuel].production_limit_mmbtu is not None:
                return model.Total_Annual_Candidate_Fuel_Consumption[
                    candidate_fuel, model_year
                ] <= self.system.candidate_fuels[candidate_fuel].production_limit_mmbtu.slice_by_year(model_year)
            else:
                return pyo.Constraint.Skip

        @mark_pyomo_component
        @self.model.Constraint(self.model.BIOMASS_RESOURCES, self.model.MODEL_YEARS)
        def Biomass_Resource_Production_Constraint(model, biomass_resource, model_year):
            """
            Production of candidate fuels from biomass resources must not exceeded specified limit.
            """
            return sum(
                model.Candidate_Fuel_Production_From_Biomass_MT[c, biomass_resource, model_year]
                for c in model.CANDIDATE_FUELS
                if biomass_resource in model.CANDIDATE_FUEL_BIOMASS_RESOURCES[c]
            ) <= self.system.biomass_resources[biomass_resource].feedstock_limit_metric_tons.slice_by_year(model_year)

        ##################################################
        # COST EXPRESSIONS                               #
        ##################################################
        @mark_pyomo_component
        @self.model.Expression(self.model.ASSETS, self.model.MODEL_YEARS)
        def Asset_New_Investment_Cost_In_Model_Year_Dollars(model, asset, year):
            new_installed_cost = sum(
                model.Build_Capacity_MW[asset, vintage]
                * (
                    self._get(self.system.assets[asset]._new_capacity_annualized_all_in_fixed_cost_by_vintage, slice_by=vintage) -
                    self._get(self.system.assets[asset]._new_capacity_fixed_om_by_vintage, slice_by=vintage)
                )
                * 10 ** 3
                for vintage in model.VINTAGES
                if year >= vintage
            )
            if asset in model.RESOURCES_WITH_STORAGE:
                new_storage_installed_cost = sum(
                    model.Build_Storage_MWh[asset, vintage]
                    * (
                        self._get(self.system.assets[asset]._new_storage_annual_fixed_cost_dollars_per_kwh_yr_by_vintage, slice_by=vintage) -
                        self._get(self.system.assets[asset]._new_storage_capacity_fixed_om_by_vintage, slice_by=vintage)
                    )
                    * 10 ** 3
                    for vintage in model.VINTAGES
                    if year >= vintage
                )
            else:
                new_storage_installed_cost = 0

            return (new_installed_cost + new_storage_installed_cost)


        @mark_pyomo_component
        @self.model.Expression(self.model.ASSETS, self.model.MODEL_YEARS)
        def Asset_Fixed_OM_Cost_In_Model_Year_Dollars(model, asset, year):
            planned_asset_fixed_cost = (
                model.Operational_Planned_Capacity_In_Model_Year[asset, year]
                * self._get(self.system.assets[asset]._planned_fixed_om_by_model_year, slice_by=year)
                * 10**3
            )
            # Fixed o&m for planned storage
            if asset in model.RESOURCES_WITH_STORAGE:
                planned_storage_fixed_cost = (
                    model.Operational_Planned_Storage_In_Model_Year[asset, year]
                    * self._get(
                        self.system.assets[asset]._planned_storage_capacity_fixed_om_by_model_year, slice_by=year
                    )
                    * 10**3
                )
            else:
                planned_storage_fixed_cost = 0.0


            if self.system.assets[asset].can_build_new:
                new_fixed_om_cost = sum(
                    model.Operational_New_Capacity_By_Vintage_In_Model_Year[asset, vintage, year]
                    * self._get(self.system.assets[asset]._new_capacity_fixed_om_by_vintage, slice_by=vintage)
                    * 10 ** 3
                    for vintage in model.VINTAGES
                    if year >= vintage
                )

                if asset in model.RESOURCES_WITH_STORAGE:
                    new_storage_fixed_om = sum(
                        model.Operational_New_Storage_By_Vintage_In_Model_Year[asset, vintage, year]
                        * self._get(
                            self.system.assets[asset]._new_storage_capacity_fixed_om_by_vintage, slice_by=vintage
                        )
                        * 10 ** 3
                        for vintage in model.VINTAGES
                        if year >= vintage
                    )
                else:
                    new_storage_fixed_om = 0
            else:
                new_fixed_om_cost = 0
                new_storage_fixed_om = 0

            return (
                planned_asset_fixed_cost +
                planned_storage_fixed_cost +
                new_fixed_om_cost +
                new_storage_fixed_om
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.ASSETS, self.model.MODEL_YEARS)
        def Asset_Total_Annual_Fixed_Cost_In_Model_Year_Dollars(model, asset, year):
            """
            For existing resources, just fixed o&m;
            For candidate resources, fixed o&m plus capital, i.e. _total_annualized_fixed_cost
            """
            return (
                model.Asset_New_Investment_Cost_In_Model_Year_Dollars[asset, year] +
                model.Asset_Fixed_OM_Cost_In_Model_Year_Dollars[asset, year]
            )

        self.model.PLANTS_WITH_VARIABLE_COST = pyo.Set(
            initialize=[r for r, obj in self.system.plants.items() if obj.variable_cost_provide_power is not None or obj.variable_cost_increase_load is not None]
        )

        @mark_pyomo_component
        @self.model.Expression(self.model.PLANTS_WITH_VARIABLE_COST, self.model.TIMEPOINTS)
        def Plant_Variable_Cost_In_Timepoint(model, plant, model_year, rep_period, hour):
            """Derived variable that represents the variable cost of each resource in each timepoint (not weighted or discounted)
            All resources are included here, even if variable cost is zero

            Args:
              model:
              timepoint:
              resource:

            Returns:

            """
            # variable cost to increase load
            if plant in model.PLANTS_THAT_INCREASE_LOAD:
                load_cost = model.Increase_Load_MW[plant, model_year, rep_period, hour] * self._get(
                    self.system.plants[plant]._variable_cost_increase_load, slice_by=model_year
                )
            else:
                load_cost = 0.0

            # variable cost to provide power
            if plant in model.PLANTS_THAT_PROVIDE_POWER:
                power_cost = model.Provide_Power_MW[plant, model_year, rep_period, hour] * self._get(
                    self.system.plants[plant]._variable_cost_provide_power, slice_by=(model_year, rep_period, hour)
                )
            else:
                power_cost = 0.0

            if plant in model.FUEL_CONVERSION_PLANTS:
                other_variable_cost = self.system.fuel_conversion_plants[
                    plant
                ].Fuel_Conversion_Plant_Variable_Cost_In_Timepoint(
                    model=model,
                    model_year=model_year,
                    rep_period=rep_period,
                    hour=hour,
                )
            else:
                other_variable_cost = 0.0

            return load_cost + power_cost + other_variable_cost

        @mark_pyomo_component
        @self.model.Expression(self.model.UNIT_COMMITMENT_RESOURCES, self.model.TIMEPOINTS)
        def Start_Cost_In_Timepoint(model, resource, model_year, rep_period, hour):
            return model.Start_Units[resource, model_year, rep_period, hour] * self._get(
                self.system.resources[resource].start_cost
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.UNIT_COMMITMENT_RESOURCES, self.model.TIMEPOINTS)
        def Shutdown_Cost_In_Timepoint(model, resource, model_year, rep_period, hour):
            return model.Shutdown_Units[resource, model_year, rep_period, hour] * self._get(
                self.system.resources[resource].shutdown_cost
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.CURTAILABLE_RESOURCES, self.model.TIMEPOINTS)
        def Resource_Curtailment_Cost_In_Timepoint(model, resource, model_year, rep_period, hour):
            """Cost of curtailed energy from variable or hydro resources.

            For certain variable (e.g., outside modeled RPS policy) or hydro resources, the ``curtailment_cost`` attribute
            can be used to represent the opportunity cost with curtailing or spilling energy. This expression represents
            the total $/hour associated with curtailed/spilled energy from the resource.
            """
            # variable cost to increase load
            if resource in model.CURTAILABLE_RESOURCES:
                return model.Scheduled_Curtailment_MW[resource, model_year, rep_period, hour] * self._get(
                    self.system.resources[resource].curtailment_cost, slice_by=(model_year, rep_period, hour)
                )
            else:
                return None

        # TODO (2021-10-06): Revisit small penalty terms
        @mark_pyomo_component
        @self.model.Expression(self.model.TRANSMISSION_LINES, self.model.TIMEPOINTS)
        def Tx_Hurdle_Cost_In_Timepoint_Forward(model, line, model_year, rep_period, hour):
            """
            returns hurdle costs of transmission flow in the forward direction
            Args:
                model:
                line:
                timepoint:

            Returns:

            """
            # add a regularization term to make sure that Transmit_Power_Forward_MW will not
            # be bigger than is needs to be. Currently if the hurdle rate is 0 it might be larger.
            return model.Transmit_Power_Forward_MW[line, model_year, rep_period, hour] * (
                self._get(self.system.tx_paths[line].hurdle_rate_forward_direction, slice_by=model_year) + 0.001
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_TRANSPORTATIONS, self.model.TIMEPOINTS)
        def Fuel_Transportation_Hurdle_Cost_In_Timepoint_Forward(
            model, fuel_transportation, model_year, rep_period, hour
        ):
            return self.system.fuel_transportations[
                fuel_transportation
            ].Fuel_Transportation_Hurdle_Cost_In_Timepoint_Forward(model, model_year, rep_period, hour)

        @mark_pyomo_component
        @self.model.Expression(self.model.TRANSMISSION_LINES, self.model.TIMEPOINTS)
        def Tx_Hurdle_Cost_In_Timepoint_Reverse(model, line, model_year, rep_period, hour):
            """
            returns hurdle costs of transmission flow in the forward direction
            Args:
                model:
                line:
                timepoint:

            Returns:

            """
            return model.Transmit_Power_Reverse_MW[line, model_year, rep_period, hour] * (
                self._get(self.system.tx_paths[line].hurdle_rate_reverse_direction, slice_by=model_year) + 0.001
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_TRANSPORTATIONS, self.model.TIMEPOINTS)
        def Fuel_Transportation_Hurdle_Cost_In_Timepoint_Reverse(
            model, fuel_transportation, model_year, rep_period, hour
        ):
            return self.system.fuel_transportations[
                fuel_transportation
            ].Fuel_Transportation_Hurdle_Cost_In_Timepoint_Reverse(model, model_year, rep_period, hour)

        # TODO: Need to borrow this so that I can track commodity fuel burn on an hourly basis
        @mark_pyomo_component
        @self.model.Expression(self.model.TIMEPOINTS)
        def Costs_Fuel_Resource_Burn_In_Timepoint(model, model_year, rep_period, hour):
            """
            Return costs of the fuel burned from electric sector resources
            """
            return sum(
                model.Total_Candidate_Fuel_Consumption_In_Timepoint_All_Resources[c, model_year, rep_period, hour]
                * self.system.candidate_fuels[c].fuel_price_per_mmbtu.slice_by_timepoint(
                    self.temporal_settings, model_year, rep_period, hour
                )
                if self._get(self.system.candidate_fuels[c].fuel_is_commodity_bool)
                else 0
                for c in model.CANDIDATE_FUELS
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.MODEL_YEARS)
        def Costs_Fuel_Final_Fuel_Demands_In_Model_Year(model, model_year):
            """
            Return commodity costs for fuels consumed by final fuel demands
            """
            return sum(
                model.Total_Annual_Candidate_Fuel_Consumption_All_Final_Fuel_Demands[c, model_year]
                * self.system.candidate_fuels[c].fuel_price_per_mmbtu.slice_by_year(model_year)
                if self._get(self.system.candidate_fuels[c].fuel_is_commodity_bool)
                else 0
                for c in model.CANDIDATE_FUELS
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.RESOURCES, self.model.TIMEPOINTS)
        def Resource_Fuel_Cost(model, resource, model_year, rep_period, hour):
            fuel_costs = sum(
                model.Resource_Fuel_Consumption_In_Timepoint_MMBTU[resource, fuel, model_year, rep_period, hour]
                * self.system.candidate_fuels[fuel].fuel_price_per_mmbtu.slice_by_timepoint(
                    self.temporal_settings, model_year, rep_period, hour
                )
                for fuel in model.RESOURCE_CANDIDATE_FUELS[resource]
                if self._get(self.system.candidate_fuels[fuel].fuel_is_commodity_bool)
            )

            return fuel_costs

        @mark_pyomo_component
        @self.model.Expression(self.model.FUEL_CONVERSION_PLANTS, self.model.TIMEPOINTS)
        def Fuel_Conversion_Plant_Fuel_Cost(model, fuel_conversion_plant, model_year, rep_period, hour):
            fuel_costs = sum(
                model.Fuel_Conversion_Plant_Consumption_In_Timepoint_MMBTU[
                    fuel_conversion_plant, fuel, model_year, rep_period, hour
                ]
                * self.system.candidate_fuels[fuel].fuel_price_per_mmbtu.slice_by_timepoint(
                    self.temporal_settings, model_year, rep_period, hour
                )
                for fuel in model.CANDIDATE_FUELS
                if self._get(self.system.candidate_fuels[fuel].fuel_is_commodity_bool)
            )

            return fuel_costs

        @mark_pyomo_component
        @self.model.Expression(self.model.MODEL_YEARS)
        def Total_Fixed_Cost_In_Model_Year(model, model_year):
            return sum(
                model.Asset_Total_Annual_Fixed_Cost_In_Model_Year_Dollars[asset, model_year] for asset in model.ASSETS
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.MODEL_YEARS)
        def Total_Variable_Cost_In_Model_Year(model, model_year):
            return sum(
                self.sum_timepoint_to_annual(model_year, "Plant_Variable_Cost_In_Timepoint", p) for p in model.PLANTS_WITH_VARIABLE_COST
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.MODEL_YEARS)
        def Total_Start_And_Shutdown_Cost_In_Model_Year(model, model_year):
            return sum(
                self.sum_timepoint_to_annual(model_year, "Start_Cost_In_Timepoint", r)
                + self.sum_timepoint_to_annual(model_year, "Shutdown_Cost_In_Timepoint", r)
                for r in model.UNIT_COMMITMENT_RESOURCES
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.MODEL_YEARS)
        def Total_Curtailment_Cost_In_Model_Year(model, model_year):
            return sum(
                self.sum_timepoint_to_annual(model_year, "Resource_Curtailment_Cost_In_Timepoint", r)
                for r in model.CURTAILABLE_RESOURCES
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.MODEL_YEARS)
        def Total_Tx_Hurdle_Cost_In_Model_Year(model, model_year):
            return sum(
                self.sum_timepoint_to_annual(model_year, "Tx_Hurdle_Cost_In_Timepoint_Forward", line)
                + self.sum_timepoint_to_annual(model_year, "Tx_Hurdle_Cost_In_Timepoint_Reverse", line)
                for line in model.TRANSMISSION_LINES
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.MODEL_YEARS)
        def Total_Fuel_Transportation_Hurdle_Cost_In_Model_Year(model, model_year):
            return sum(
                self.sum_timepoint_to_annual(
                    model_year, "Fuel_Transportation_Hurdle_Cost_In_Timepoint_Forward", transport
                )
                + self.sum_timepoint_to_annual(
                    model_year, "Fuel_Transportation_Hurdle_Cost_In_Timepoint_Reverse", transport
                )
                for transport in model.FUEL_TRANSPORTATIONS
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.MODEL_YEARS)
        def Total_Commodity_Fuel_Cost_In_Model_Year(model, model_year):
            return self.sum_timepoint_to_annual(model_year, "Costs_Fuel_Resource_Burn_In_Timepoint")

        @mark_pyomo_component
        @self.model.Expression(self.model.MODEL_YEARS)
        def Total_Biomass_Fuel_Production_Cost_In_Model_Year(model, model_year):
            return sum(
                model.Candidate_Fuel_Production_From_Biomass_MT[c, b, model_year]
                * self.system.candidate_fuels[c].biomass_resources[b].conversion_cost.slice_by_year(model_year)
                if b in model.CANDIDATE_FUEL_BIOMASS_RESOURCES[c]
                else 0
                for b in model.BIOMASS_RESOURCES
                for c in model.CANDIDATE_FUELS
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.MODEL_YEARS)
        def Total_Zonal_Unserved_Energy_And_Overgen_Cost_In_Model_Year(model, model_year):
            return sum(
                (
                    self.system.zones[zone].penalty_unserved_energy
                    * self.sum_timepoint_to_annual(model_year, "Unserved_Energy_MW", zone)
                )
                + (
                    self.system.zones[zone].penalty_overgen
                    * self.sum_timepoint_to_annual(model_year, "Overgen_MW", zone)
                )
                for zone in model.ZONES
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.MODEL_YEARS)
        def Total_Fuel_Zone_Unserved_And_Overproduction_Cost_In_Model_Year(model, model_year):
            return sum(
                (
                    self.system.fuel_zones[ef_zone].penalty_unserved_energy
                    * self.sum_timepoint_to_annual(model_year, "Unserved_Energy_MMBTU_H", ef_zone, candidate_fuel)
                )
                + (
                    self.system.fuel_zones[ef_zone].penalty_overproduction
                    * self.sum_timepoint_to_annual(model_year, "Overproduction_MMBTU_H", ef_zone, candidate_fuel)
                )
                for ef_zone in model.FUEL_ZONES
                for candidate_fuel in model.CANDIDATE_FUELS
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.MODEL_YEARS)
        def Total_Unserved_Reserves_Cost_In_Model_Year(model, model_year):
            return sum(
                self.system.reserves[reserve].penalty_unserved_reserve
                * self.sum_timepoint_to_annual(model_year, "Unserved_Reserve_MW", reserve)
                for reserve in model.RESERVES
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.MODEL_YEARS)
        def Total_Policy_Cost_In_Model_Year(model, model_year: int):
            return sum(
                self._get(self.system.policies[policy].price, default_val=0, slice_by=model_year)
                * model.Policy_LHS[policy, model_year]
                for policy in model.POLICIES
            )

        @mark_pyomo_component
        @self.model.Expression(self.model.MODEL_YEARS)
        def Total_Cost_In_Model_Year(model, model_year):
            """
            Return total cost for objective function in model year
            """

            return (
                # fixed cost for all assets
                model.Total_Fixed_Cost_In_Model_Year[model_year]
                # variable cost for all plants
                + model.Total_Variable_Cost_In_Model_Year[model_year]
                # start and shutdown costs
                + model.Total_Start_And_Shutdown_Cost_In_Model_Year[model_year]
                # curtailment costs
                + model.Total_Curtailment_Cost_In_Model_Year[model_year]
                # hurdle cost for transmission lines
                + model.Total_Tx_Hurdle_Cost_In_Model_Year[model_year]
                # hurdle cost for fuel transportation
                + model.Total_Fuel_Transportation_Hurdle_Cost_In_Model_Year[model_year]
                # commodity costs for fuels consumed by resources
                + model.Total_Commodity_Fuel_Cost_In_Model_Year[model_year]
                # commodity costs for fuels consumed by final fuel demands
                + model.Costs_Fuel_Final_Fuel_Demands_In_Model_Year[model_year]
                # cost of production from biomass for candidate fuels that can be produced by biomass resources
                + model.Total_Biomass_Fuel_Production_Cost_In_Model_Year[model_year]
                # zonal penalty function to prevent hard zonal constraints
                + model.Total_Zonal_Unserved_Energy_And_Overgen_Cost_In_Model_Year[model_year]
                # zonal penalty function for fuel zones
                + model.Total_Fuel_Zone_Unserved_And_Overproduction_Cost_In_Model_Year[model_year]
                # reserve penalty function to prevent hard operating reserve constraint
                + model.Total_Unserved_Reserves_Cost_In_Model_Year[model_year]
                # Policy costs
                + model.Total_Policy_Cost_In_Model_Year[model_year]
                + sum(10_000 * model.Policy_Slack[policy, model_year] if policy not in model.POLICIES_BY_TYPE["prm"] else 10_000_000 * model.Policy_Slack[policy, model_year] for policy in model.POLICIES)
                - sum(0.001 * model.ELCC_MW[model_year, elcc_surface] for elcc_surface in model.ELCC_SURFACE)
                + sum(50_000_000 * model.Custom_Constraint_Slack_Up[constraint] for constraint in model.CUSTOM_CONSTRAINTS)
                + sum(50_000_000 * model.Custom_Constraint_Slack_Down[constraint] for constraint in model.CUSTOM_CONSTRAINTS)
                + sum(50_000_000 * model.Resource_Potential_Slack[asset, model_year] for asset in model.ASSETS)
            )

        # CONSTRUCT OBJECTIVE FUNCTION #
        @mark_pyomo_component
        @self.model.Objective(sense=pyo.minimize)
        def Total_Cost(model):
            """Get NPV of total cost in each model year"""
            return sum(
                (
                    model.Total_Cost_In_Model_Year[model_year] +
                    sum(
                        model.blocks[policy].slack_penalty[model_year]
                        for policy in self.system.hourly_energy_policies.keys()
                    )
                ) * self._get(self.temporal_settings.modeled_year_discount_factor, slice_by=model_year)
                for model_year in self.model.MODEL_YEARS
            )

    def _update_components_with_solver_results(
        self,
        component_dict: Dict[str, Component],
        component_index_level: Optional[Union[str, int]] = None,
        model_component_attribute_mapping: Optional[Dict[str, str]] = None,
        timepoint_model_component_attribute_mapping: Optional[Dict[str, str]] = None,
    ):
        """Updates components of the System with results from the solved RESOLVE model.

        IMPORTANT: attributes in the `timepoint_model_component_attribute_mapping` argument will be summed to annual
        values by scaling based on the number of rep periods in a year and rep period weightings. They will not be kept
        as timepoint-indexed values. If you want to avoid summing to annual, you can put the key-value pair in
        `model_component_attribute_mapping` instead.

        Also note that `model_component_attribute_mapping` and `timepoint_model_component_attribute_mapping` cannot
        contain any of the same keys. If you want to write the same timepoint-indexed pyomo expression as both a
        timepoint-indexed attribute and as an annual attribute, you can call this function two separate times.

        Finally, this method currently writes only the dual values for any Constraint instance, rather than including
        the lower bound, upper bound, and body.

        For example, to update all Assets in the system with their optimized new-build operational capacity by model
        year (`self.model.Operational_New_Capacity_MW`) by storing these values in the attribute
        `Asset.opt_operational_new_capacity_mw`, run the following:

            _update_components_with_solver_results(
                component_dict=self.system.assets,
                model_component_attribute_mapping={
                    "Operational_New_Capacity_MW": "opt_operational_new_capacity_mw",
                },
            )

        Args:
            component_dict: dictionary containing component names as keys and the Component instances as values.
                e.g. `self.system.resources`
            model_component_attribute_mapping: dictionary mapping from the name of the RESOLVE model attribute
                (pyomo Var, Param, or Expression) to the attribute of the Component where it should be written. Items
                in this dictionary will attempt to be converted to Timeseries instances if possible, otherwise they will
                be assigned as pandas Series objects.
            timepoint_model_component_attribute_mapping: dictionary mapping from the name of the timepoint-indexed
                RESOLVE model attribute (pyomo Var, Param, or Expression) to the attribute of the Component where it
                should be written. Items in this dictionary will attempt to be converted to Timeseries instances if
                possible, otherwise they will be assigned as pandas Series objects.
        """
        # Check that the user has specified at least one mapping with no overlapping keys
        if model_component_attribute_mapping is None and timepoint_model_component_attribute_mapping is None:
            raise ValueError(
                "Must specify one of `annual_model_component_attribute_mapping` or "
                "`timepoint_model_component_attribute_mapping`"
            )
        if (
            model_component_attribute_mapping is not None
            and timepoint_model_component_attribute_mapping is not None
            and (
                len(
                    set(model_component_attribute_mapping.keys()).intersection(
                        set(timepoint_model_component_attribute_mapping.keys())
                    )
                )
                > 0
            )
        ):
            raise ValueError(
                "`model_component_attribute_mapping` and `timepoint_model_attribute_mapping` cannot contain duplicate "
                "keys."
            )

        # Extract non-timepoint attributes from the pyomo model
        if model_component_attribute_mapping is not None:
            extracted_annual_attributes = {
                attribute: convert_pyomo_object_to_dataframe(getattr(self.model, attribute), dual_only=True).squeeze(
                    axis=1
                )
                for attribute in model_component_attribute_mapping.keys()
            }
        else:
            extracted_annual_attributes = {}

        # Extract timepoint attributes from the model and sum them to annual values
        if timepoint_model_component_attribute_mapping is not None:
            extracted_timepoint_attributes = {
                attribute: self.sum_timepoints_to_annual_all_years(attribute=attribute)
                for attribute in timepoint_model_component_attribute_mapping.keys()
            }
        else:
            extracted_timepoint_attributes = {}

        # Combine the timepoint-indexed expressions and non-timepoint expressions into a single dictionary
        #   for iteration
        attribute_mapping = dict()
        if model_component_attribute_mapping is not None:
            attribute_mapping.update(model_component_attribute_mapping)
        if timepoint_model_component_attribute_mapping is not None:
            attribute_mapping.update(timepoint_model_component_attribute_mapping)
        extracted_attributes = dict(**extracted_annual_attributes, **extracted_timepoint_attributes)

        for component_name, component in component_dict.items():
            logger.debug(f"Updating component `{component_name}` with optimized decisions.")
            for model_attribute, series in extracted_attributes.items():
                component_attribute = attribute_mapping[model_attribute]

                if series is None:
                    assigned_value = None
                else:
                    # Extract the data for the current Component
                    series_subset = series.xs(component_name, level=component_index_level)

                    # Convert the data to a Timeseries, if possible
                    if series_subset.index.nlevels > 1:
                        assigned_value = series_subset.rename(component_attribute)
                    else:
                        assigned_value = ts.NumericTimeseries.from_annual_series(
                            name=component_attribute, data=series_subset
                        )

                setattr(component, component_attribute, assigned_value)

    def _update_assets_with_solver_results(self):
        self._update_components_with_solver_results(
            component_dict=self.system.assets,
            model_component_attribute_mapping={
                "Operational_Planned_Capacity_In_Model_Year": "opt_operational_planned_capacity",
                "Retired_New_Capacity": "opt_retired_new_capacity",
                "Operational_New_Capacity_MW": "opt_operational_new_capacity",
                "Asset_New_Investment_Cost_In_Model_Year_Dollars": "opt_annual_installed_cost_dollars",
                "Asset_Fixed_OM_Cost_In_Model_Year_Dollars": "opt_annual_fixed_om_cost_dollars",
            },
        )

    def _update_plants_with_solver_results(self):
        self._update_components_with_solver_results(
            component_dict={
                name: plant
                for name, plant in self.system.plants.items()
                if name in self.model.PLANTS_THAT_PROVIDE_POWER
            },
            model_component_attribute_mapping={
                "Provide_Power_MW": "opt_provide_power_mw",
            },
        )
        self._update_components_with_solver_results(
            component_dict={
                name: plant
                for name, plant in self.system.plants.items()
                if name in self.model.PLANTS_THAT_PROVIDE_POWER
            },
            timepoint_model_component_attribute_mapping={
                "Provide_Power_MW": "opt_annual_provide_power_mwh",
            },
        )
        # TODO 2023-06-28: For now turned off reporting reserve provision reporting
        self._update_components_with_solver_results(
            component_dict={name: obj for name, obj in self.system.plants.items() if name in self.model.PLANTS_WITH_VARIABLE_COST},
            model_component_attribute_mapping=None,
            timepoint_model_component_attribute_mapping={
                "Plant_Variable_Cost_In_Timepoint": "opt_annual_variable_cost_dollars",
            },
        )

        # Update only plants that can increase load with data related to increasing load
        self._update_components_with_solver_results(
            component_dict={
                name: plant
                for name, plant in self.system.plants.items()
                if name in self.model.PLANTS_THAT_INCREASE_LOAD
            },
            model_component_attribute_mapping={
                "Increase_Load_MW": "opt_increase_load_mw",
            },
        )
        self._update_components_with_solver_results(
            component_dict={
                name: plant
                for name, plant in self.system.plants.items()
                if name in self.model.PLANTS_THAT_INCREASE_LOAD
            },
            timepoint_model_component_attribute_mapping={
                "Increase_Load_MW": "opt_annual_increase_load_mwh",
            },
        )

    def _update_resources_with_solver_results(self):
        self._update_components_with_solver_results(
            component_dict=self.system.resources,
            timepoint_model_component_attribute_mapping={
                "Resource_Fuel_Consumption_In_Timepoint_MMBTU": "opt_annual_fuel_consumption_by_fuel_mmbtu",
                "Resource_Fuel_Cost": "opt_annual_fuel_cost_dollars",
            },
        )
        self._update_components_with_solver_results(
            component_dict={name: obj for name, obj in self.system.resources.items() if name in self.model.CURTAILABLE_RESOURCES},
            timepoint_model_component_attribute_mapping={
                "Scheduled_Curtailment_MW": "opt_annual_curtailment_mwh",
                "Resource_Curtailment_Cost_In_Timepoint": "opt_annual_curtailment_cost_dollars",
            },
        )
        self._update_components_with_solver_results(
            component_dict={
                name: resource
                for name, resource in self.system.resources.items()
                if name in self.model.RESOURCES_WITH_STORAGE
            },
            model_component_attribute_mapping={
                "Operational_Planned_Storage_In_Model_Year": "opt_operational_planned_storage_capacity",
                "Retired_New_Storage_Capacity": "opt_retired_new_storage_capacity",
                "SOC_Intra_Period": "opt_soc_intra_period",
                "SOC_Inter_Period": "opt_soc_inter_period",
                "SOC_Inter_Intra_Joint": "opt_soc_inter_intra_joint",
            },
        )

        self._update_components_with_solver_results(
            component_dict={
                name: resource
                for name, resource in self.system.resources.items()
                if name in self.model.UNIT_COMMITMENT_RESOURCES
            },
            timepoint_model_component_attribute_mapping={
                "Start_Cost_In_Timepoint": "opt_annual_start_cost_dollars",
                "Shutdown_Cost_In_Timepoint": "opt_annual_shutdown_cost_dollars",
                "Start_Units": "opt_annual_start_units",
                "Shutdown_Units": "opt_annual_shutdown_units",
            },
        )

        operational_new_storage_by_vintage_mwh = convert_pyomo_object_to_dataframe(
            self.model.Operational_New_Storage_By_Vintage_In_Model_Year,
        ).squeeze(axis=1)
        operational_new_storage_mwh = operational_new_storage_by_vintage_mwh.groupby(
            [self.model.RESOURCES_WITH_STORAGE.name, self.model.MODEL_YEARS.name]
        ).sum()

        for name, resource in self.system.resources.items():
            if name in self.model.RESOURCES_WITH_STORAGE:
                resource.opt_operational_new_storage_capacity = ts.NumericTimeseries.from_annual_series(
                    name="opt_operational_new_storage_capacity",
                    data=operational_new_storage_mwh.xs(name, level=self.model.RESOURCES_WITH_STORAGE.name).rename(
                        "opt_operational_new_storage_capacity"
                    ),
                )

    def _update_fuel_production_plants_with_solver_results(self):
        self._update_components_with_solver_results(
            component_dict=self.system.fuel_conversion_plants,
            timepoint_model_component_attribute_mapping={
                "Fuel_Conversion_Plant_Consumption_In_Timepoint_MMBTU": "opt_annual_fuel_consumption_by_fuel_mmbtu",
                "Fuel_Conversion_Plant_Fuel_Cost": "opt_annual_fuel_cost_dollars",
            },
        )

        annual_candidate_fuel_production = convert_pyomo_object_to_dataframe(
            self.model.Candidate_Fuel_Production_From_Fuel_Production_Plant_MMBTU
        ).squeeze(axis=1)
        annual_candidate_fuel_production = annual_candidate_fuel_production.groupby(
            [self.model.FUEL_PRODUCTION_PLANTS.name, self.model.MODEL_YEARS.name]
        ).sum()
        annual_candidate_fuel_production = convert_index_levels_to_datetime(
            annual_candidate_fuel_production, levels=self.model.MODEL_YEARS.name, format="%Y"
        )

        for fuel_production_plant in self.system.fuel_production_plants.values():
            fuel_production_plant.opt_annual_produced_fuel_mmbtu = ts.NumericTimeseries(
                name="opt_annual_produced_fuel_mmbtu",
                data=annual_candidate_fuel_production.xs(
                    fuel_production_plant.name, level=self.model.FUEL_PRODUCTION_PLANTS.name
                ),
            )

    def _update_fuel_storages_with_solver_results(self):
        self._update_components_with_solver_results(
            component_dict=self.system.fuel_storages,
            model_component_attribute_mapping={
                "Operational_Planned_Fuel_Storage_Volume_In_Model_Year": "opt_operational_planned_storage_capacity",
                "Operational_New_Fuel_Storage_Volume_In_Model_Year": "opt_operational_new_storage_capacity",
                "Fuel_Storage_SOC_Intra_Period": "opt_soc_intra_period",
                "Fuel_Storage_SOC_Inter_Period": "opt_soc_inter_period",
                "Fuel_Storage_SOC_Inter_Intra_Joint": "opt_soc_inter_intra_joint",
                "Increase_Load_For_Charging_Fuel_Storage_MW": "opt_increase_load_charging_mw",
                "Increase_Load_For_Discharging_Fuel_Storage_MW": "opt_increase_load_discharging_mw",
            },
        )
        self._update_components_with_solver_results(
            component_dict=self.system.fuel_storages,
            timepoint_model_component_attribute_mapping={
                "Increase_Load_For_Charging_Fuel_Storage_MW": "opt_annual_increase_load_charging_mwh",
                "Increase_Load_For_Discharging_Fuel_Storage_MW": "opt_annual_increase_load_discharging_mwh",
            },
        )

        for fuel_storage in self.system.fuel_storages.values():
            fuel_storage.opt_increase_load_mw = (
                fuel_storage.opt_increase_load_charging_mw + fuel_storage.opt_increase_load_discharging_mw
            )
            fuel_storage.opt_annual_increase_load_mwh = ts.NumericTimeseries(
                name="opt_annual_increase_load_mwh",
                data=fuel_storage.opt_annual_increase_load_charging_mwh.data
                + fuel_storage.opt_annual_increase_load_discharging_mwh.data,
            )

    def _update_fuel_transportations_with_solver_results(self):
        self._update_components_with_solver_results(
            component_dict=self.system.fuel_transportations,
            model_component_attribute_mapping={
                "Annual_Transmit_Candidate_Fuel_Forward": "opt_annual_flow_forward_mmbtu",
                "Annual_Transmit_Candidate_Fuel_Reverse": "opt_annual_flow_reverse_mmbtu",
                "Transmit_Candidate_Fuel_Forward_MMBTU_H": "opt_flow_forward_mmbtu_h",
                "Transmit_Candidate_Fuel_Reverse_MMBTU_H": "opt_flow_reverse_mmbtu_h",
            },
            timepoint_model_component_attribute_mapping={
                "Fuel_Transportation_Hurdle_Cost_In_Timepoint_Forward": "opt_annual_hurdle_cost_forward_dollars",
                "Fuel_Transportation_Hurdle_Cost_In_Timepoint_Reverse": "opt_annual_hurdle_cost_reverse_dollars",
            },
        )

    def _update_tx_paths_with_solver_results(self):
        self._update_components_with_solver_results(
            component_dict=self.system.tx_paths,
            model_component_attribute_mapping={
                "Annual_Transmit_Power_Forward": "opt_annual_transmit_power_forward_mwh",
                "Annual_Transmit_Power_Reverse": "opt_annual_transmit_power_reverse_mwh",
                "Transmit_Power_Forward_MW": "opt_transmit_power_forward_mw",
                "Transmit_Power_Reverse_MW": "opt_transmit_power_reverse_mw",
            },
            timepoint_model_component_attribute_mapping={
                "Tx_Hurdle_Cost_In_Timepoint_Forward": "opt_annual_hurdle_cost_forward_dollars",
                "Tx_Hurdle_Cost_In_Timepoint_Reverse": "opt_annual_hurdle_cost_reverse_dollars",
            },
        )

        # Calculate value of transmission flows based on to_/from_zone energy prices
        hourly_energy_prices = convert_pyomo_object_to_dataframe(self.model.Zonal_Power_Balance_Constraint).loc[
            :, "Dual"
        ]
        hourly_energy_prices = convert_index_levels_to_datetime(
            hourly_energy_prices, levels=self.model.MODEL_YEARS.name, format="%Y"
        )

        model_year_discount_factors = self.temporal_settings.modeled_year_discount_factor.data.rename_axis(
            index=self.model.MODEL_YEARS.name
        )
        rep_period_weights = convert_pyomo_object_to_dataframe(self.model.rep_period_weight).squeeze(axis=1)
        rep_periods_per_year = convert_pyomo_object_to_dataframe(self.model.rep_periods_per_model_year).squeeze(axis=1)
        rep_periods_per_year.index = pd.to_datetime(rep_periods_per_year.index, format="%Y")

        hourly_energy_prices_unweighted = (
            hourly_energy_prices.div(model_year_discount_factors, level=self.model.MODEL_YEARS.name)
            .div(rep_period_weights, level=self.model.REP_PERIODS.name)
            .div(rep_periods_per_year, level=self.model.MODEL_YEARS.name)
        )

        for tx_name, tx_path in self.system.tx_paths.items():
            # Get gross flows
            forward_flows = convert_index_levels_to_datetime(
                tx_path.opt_transmit_power_forward_mw, levels=self.model.MODEL_YEARS.name, format="%Y"
            )
            reverse_flows = convert_index_levels_to_datetime(
                tx_path.opt_transmit_power_reverse_mw, levels=self.model.MODEL_YEARS.name, format="%Y"
            )
            to_zone_price = hourly_energy_prices_unweighted.xs(
                tx_path.to_zone._instance_from.name, level=self.model.ZONES.name
            )
            from_zone_price = hourly_energy_prices_unweighted.xs(
                tx_path.from_zone._instance_from.name, level=self.model.ZONES.name
            )

            # Calculate all four possible valuations
            forward_flow_to_zone_value = (
                (forward_flows * to_zone_price * rep_period_weights * rep_periods_per_year)
                .groupby(self.model.MODEL_YEARS.name)
                .sum()
            )
            forward_flow_from_zone_value = (
                (forward_flows * from_zone_price * rep_period_weights * rep_periods_per_year)
                .groupby(self.model.MODEL_YEARS.name)
                .sum()
            )
            reverse_flow_to_zone_value = (
                (reverse_flows * to_zone_price * rep_period_weights * rep_periods_per_year)
                .groupby(self.model.MODEL_YEARS.name)
                .sum()
            )
            reverse_flow_from_zone_value = (
                (reverse_flows * from_zone_price * rep_period_weights * rep_periods_per_year)
                .groupby(self.model.MODEL_YEARS.name)
                .sum()
            )

            # Assign the attributes
            for attribute, series in [
                ("opt_forward_flow_to_zone_value", forward_flow_to_zone_value),
                ("opt_forward_flow_from_zone_value", forward_flow_from_zone_value),
                ("opt_reverse_flow_to_zone_value", reverse_flow_to_zone_value),
                ("opt_reverse_flow_from_zone_value", reverse_flow_from_zone_value),
            ]:
                setattr(tx_path, attribute, ts.NumericTimeseries(name=attribute, data=series))

    def _update_zones_with_solver_results(self):
        self._update_components_with_solver_results(
            component_dict=self.system.zones,
            timepoint_model_component_attribute_mapping={
                "Overgen_MW": "opt_annual_overgeneration_mwh",
                "Unserved_Energy_MW": "opt_annual_unserved_energy_mwh",
                "input_load_mw": "opt_annual_input_load_mwh",
            },
        )

        self._update_components_with_solver_results(
            component_dict=self.system.zones,
            model_component_attribute_mapping={
                "Zonal_Power_Balance_Constraint": "opt_hourly_energy_price_dollars_per_mwh"
            },
        )

    def _update_zones_with_energy_prices(self):
        hourly_energy_prices = convert_pyomo_object_to_dataframe(self.model.Zonal_Power_Balance_Constraint).loc[
            :, "Dual"
        ]
        hourly_energy_prices = convert_index_levels_to_datetime(
            hourly_energy_prices, levels=self.model.MODEL_YEARS.name, format="%Y"
        )

        model_year_discount_factors = self.temporal_settings.modeled_year_discount_factor.data.rename_axis(
            index=self.model.MODEL_YEARS.name
        )
        rep_period_weights = convert_pyomo_object_to_dataframe(self.model.rep_period_weight).squeeze(axis=1)
        rep_periods_per_year = convert_pyomo_object_to_dataframe(self.model.rep_periods_per_model_year).squeeze(axis=1)
        rep_periods_per_year.index = pd.to_datetime(rep_periods_per_year.index, format="%Y")

        hourly_energy_prices_unweighted = (
            hourly_energy_prices.div(model_year_discount_factors, level=self.model.MODEL_YEARS.name)
            .div(rep_period_weights, level=self.model.REP_PERIODS.name)
            .div(rep_periods_per_year, level=self.model.MODEL_YEARS.name)
        )

        for zone_name, zone in self.system.zones.items():
            zone.opt_hourly_energy_price_unweighted_dollars_per_mwh = hourly_energy_prices_unweighted.xs(
                zone_name, level=self.model.ZONES.name
            )

    def _update_policies_with_solver_results(self):
        self._update_components_with_solver_results(
            component_dict={
                policy_name: policy
                for policy_name, policy in self.system.policies.items()
                if policy_name in self.model.POLICIES_BY_TYPE["energy"]
            },
            model_component_attribute_mapping={
                "Energy_Policy_Annual_Contribution_By_Resource": "opt_annual_contribution_by_resource_mwh",
            },
        )

        self._update_components_with_solver_results(
            component_dict={
                policy_name: policy
                for policy_name, policy in self.system.policies.items()
                if policy_name in self.model.POLICIES
            },
            model_component_attribute_mapping={
                "Policy_LHS": "opt_policy_lhs",
            },
        )

        self._update_components_with_solver_results(
            component_dict={
                policy_name: policy
                for policy_name, policy in self.system.policies.items()
                if policy_name in self.model.POLICIES_BY_TYPE["emissions"]
            },
            model_component_attribute_mapping={
                "Annual_Resource_Emissions_In_Policy": "opt_annual_contribution_by_resource",
                "Annual_Transmission_Emissions_In_Policy": "opt_annual_contribution_by_tx_path",
            },
            component_index_level="POLICIES_BY_TYPE[emissions]",
        )

        # Resource PRM contributions
        self._update_components_with_solver_results(
            component_dict={
                policy_name: policy
                for policy_name, policy in self.system.policies.items()
                if policy_name in self.model.POLICIES_BY_TYPE["prm"]
            },
            model_component_attribute_mapping={
                "Reliability_Capacity_In_Model_Year": "opt_resource_reliability_capacity",
                "Energy_Only_Capacity": "opt_resource_energy_only_capacity",
                "NQC_By_Resource": "opt_resource_nqc",
            },
            component_index_level="POLICIES_BY_TYPE[prm]",
        )

        # TODO (2022-06-02): It should be possible to post-process an average & marginal ELCC for each resource on a surface and report that

        if len(self.model.Policy_Constraint) > 0:
            policy_dual_values = convert_index_levels_to_datetime(
                convert_pyomo_object_to_dataframe(self.model.Policy_Constraint).loc[:, "Dual"],
                levels=self.model.MODEL_YEARS.name,
                format="%Y",
            )
            discount_factors = self.temporal_settings.modeled_year_discount_factor.data.rename_axis(
                self.model.MODEL_YEARS.name
            )

            unweighted_dual_values = policy_dual_values.div(discount_factors, level=self.model.MODEL_YEARS.name)

            for policy_name, policy in self.system.policies.items():
                if policy_name in unweighted_dual_values.index.unique(level=self.model.POLICIES.name):
                    policy.opt_dual_value_unweighted = ts.NumericTimeseries(
                        name="opt_dual_value_unweighted",
                        data=unweighted_dual_values.xs(policy_name, level=self.model.POLICIES.name),
                    )

    def update_system_with_solver_results(self):
        ####################################################################################################
        # Demo putting back optimized results into `System` instance for structuring results in an OOP way #
        ####################################################################################################
        logger.info("Updating assets with solver results")
        self._update_assets_with_solver_results()
        logger.info("Updating plants with solver results")
        self._update_plants_with_solver_results()
        logger.info("Updating resources with solver results")
        self._update_resources_with_solver_results()
        logger.info("Updating Tx paths with solver results")
        self._update_tx_paths_with_solver_results()
        logger.info("Updating zones with solver results")
        self._update_zones_with_solver_results()
        self._update_zones_with_energy_prices()
        logger.info("Updating policies with solver results")
        self._update_policies_with_solver_results()
        logger.info("Updating fuel components with solver results")
        self._update_fuel_production_plants_with_solver_results()
        self._update_fuel_storages_with_solver_results()
        self._update_fuel_transportations_with_solver_results()



def scale_resource_profile(*, profile: ts.Timeseries, scalar: float) -> ts.Timeseries:
    if "Solar" or "PV" in profile.name:
        profile.data = (profile.data * scalar).clip(upper=1.0)

    elif "Wind" in profile.name:
        # =MIN(IFERROR(MAX(((1-4*F$2)+F$2*$E7^(-1/3)+F$2*3*$E7^(-2/3)),0)*$E7,0),1)
        scalar = (
        1
        - 4 * scalar
        + scalar * profile.data ** (-1 / 3)
        + scalar * 3 * profile.data ** (-2 / 3)
    )
        profile.data = (scalar * profile.data).clip(lower=0.0, upper=1.0).fillna(0)
    else:
        raise ValueError("!")

    profile._data_dict = None

if __name__ == "__main__":
    resolve = ResolveCase("system_input_new", dir_str.data_interim_dir / "systems")
    resolve.model.ELCC_Facet_Constraint_LHS.pprint()

    solver = pyo.SolverFactory(
        "cbc",
        executable=os.path.join(dir_str.proj_dir, "solvers", "cbc.exe"),
        solver_io="lp",
    )
    solution = solver.solve(resolve.model, keepfiles=True, tee=True, symbolic_solver_labels=True)
