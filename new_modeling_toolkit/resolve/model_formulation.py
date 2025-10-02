import ast
import pathlib
from collections import defaultdict
from hashlib import md5

import pandas as pd
from joblib import delayed
from joblib import Parallel
from loguru import logger
from pyomo import environ as pyo
from tqdm import tqdm

from new_modeling_toolkit.core.custom_model import ModelType
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.core.temporal.settings import TemporalSettings
from new_modeling_toolkit.core.utils.core_utils import convert_to_bool
from new_modeling_toolkit.core.utils.pyomo_utils import convert_pyomo_object_to_dataframe
from new_modeling_toolkit.core.utils.util import DirStructure
from new_modeling_toolkit.system import ElectricResource
from new_modeling_toolkit.system import System
from new_modeling_toolkit.system.electric.resources import ElectricResourceGroup
from new_modeling_toolkit.system.generics.energy import Electricity


class ResolveModel(ModelTemplate):
    TYPE = ModelType.RESOLVE

    def __init__(
        self,
        temporal_settings: TemporalSettings,
        system: System,
        results_settings: dict,
        create_operational_groups: bool = False,
        production_simulation_mode: bool = False,
        save_system_to_json: bool = False,
        **kwargs,
    ):
        """Create a RESOLVE model instance

        Args:
            temporal_settings: the temporal settings for the model
            system: the system to simulate in the model
            results_settings: dictionary that defines which model outputs are written to CSV
            create_operational_groups: Whether to automatically create groups of similar assets based on their
                operational characteristics and operate them as if they were a single asset
            production_simulation_mode: whether to run the 8760 production cost model
            save_system_to_json: whether to save system and components to json files after run
        """
        # Save results reporting settings
        self.results_reporting_settings = results_settings

        # Save solver options
        if "solver_options" in kwargs.keys():
            self.solver_options = kwargs["solver_options"]

        if create_operational_groups:
            system.construct_operational_groups()

        # Resample the timeseries attributes of the System to ensure data is interpolated and extrapolated correctly
        #  to cover all required model years and weather years
        modeled_years = temporal_settings.modeled_years.data.loc[temporal_settings.modeled_years.data.values].index
        system.resample_ts_attributes(
            modeled_years=(min(modeled_years).year, max(modeled_years).year),
            weather_years=(
                min(temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
                max(temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
            ),
        )

        # Re-scale load profiles so that peak and energy values based only on dispatch windows match the target annual
        #  peak and energy
        Parallel()(
            delayed(load.update_load_components)(temporal_settings)
            for load in tqdm(
                system.loads.values(),
                desc="Rescaling load component profiles".rjust(50),
                bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
            )
        )

        # TODO: Rescale profiles by profile, not by each individual resource. Also, rescale if underlying profile has changed
        if not production_simulation_mode:  # Skip profile rescaling because using 8760 already in PS mode
            # TODO: Add check here that makes sure profiles have correct CF in production simulation mode
            # Create folder to store scaled renewable profiles (make a concatenated string to try to get the hash to be more stable)
            str_id = f"|{temporal_settings.timeseries_cluster_name}" + f"{temporal_settings.include_leap_day}|"
            hash_id = md5(str.encode(str_id), usedforsecurity=False).hexdigest()
            logger.info(f"Looking for re-scaled profiles using ID {hash_id}")

            rescaled_profile_dir = system.dir_str.data_processed_dir / "resolve" / "rescaled_profiles" / f"{hash_id}"
            rescaled_profile_dir.mkdir(parents=True, exist_ok=True)
            # Save string ID used to create the hash
            with open(rescaled_profile_dir / "hash", "w") as f:
                f.write(str_id)

            # Re-scale renewable resource and group profiles so that the capacity factor of the day draws match the original profile cf
            Parallel()(
                delayed(resource.update_resource_profiles)(temporal_settings, rescaled_profile_dir)
                for resource in tqdm(
                    (system.wind_and_solar_resources | system.wind_and_solar_resource_groups).values(),
                    desc="Rescaling generation profiles".rjust(50),
                    bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
                )
            )

        # Construct vintages here
        # Probably can also filter vintages_to_construct by the modeled years that are actually going to be modeled
        # TODO: Consider moving revalidate() method to within system.__init__ before re-merging RECAP and RESOLVE
        if not production_simulation_mode:
            system.construct_vintages(modeled_years=modeled_years)

        # TODO: Consider moving revalidate to before profile rescaling
        system.revalidate()

        # Remove unused components
        system.remove_unused_components(modeled_years=(min(modeled_years).year, max(modeled_years).year))

        self.production_simulation_mode = production_simulation_mode
        self.save_system_to_json = save_system_to_json

        super().__init__(
            temporal_settings=temporal_settings,
            system=system,
            construct_operational_rules=True,
            construct_investment_rules=True,
            construct_costs=True,
            **kwargs,
        )

        @self.Expression(self.MODELED_YEARS)
        def Total_Cost_In_Modeled_Year(model, modeled_year):
            total_cost = pyo.quicksum(
                map(
                    lambda block: block.annual_total_investment_cost[modeled_year]
                    + block.annual_total_operational_cost[modeled_year],
                    self.blocks.values(),
                )
            )

            return total_cost

        @self.Objective(sense=pyo.minimize)
        def Total_Cost(model):
            total_cost = pyo.quicksum(
                self.temporal_settings.modeled_year_discount_factors.slice_by_year(modeled_year.year)
                * model.Total_Cost_In_Modeled_Year[modeled_year]
                for modeled_year in model.MODELED_YEARS
            )

            return total_cost

    @classmethod
    def _get_solver_options(cls, solver_settings: pd.DataFrame):
        """Convert solver options in attributes.csv to a nested dictionary with correct data types.

        It seems like CBC requires options to be of the specified data type, whereas Gurobi does not.

        Returns:
            solver_options: Nested dictionary of {solver_name: {option: value}}
        """
        for column in solver_settings.columns:
            if column not in ["option", "dtype", "value"]:
                raise ValueError(
                    f"Solver settings column {column} not recognized. Table should include 'option', 'dtype', and 'value' columns."
                )
        solver_options = {}

        for index, row in solver_settings.iterrows():
            solver_name = index
            logger.debug(f"Parsing solver setting: {row['option']}")
            option = row["option"]
            dtype = row["dtype"]
            v = row["value"]

            if "bool" in dtype.lower():
                value = ast.literal_eval(v)
            elif "int" in dtype.lower():
                value = int(float(v))
            elif "float" in dtype.lower():
                value = float(v)
            else:
                value = v

            # update dict with formatted value
            if solver_name in solver_options.keys():
                solver_options[solver_name] |= {option: value}
            else:
                solver_options[solver_name] = {option: value}

        return solver_options

    @classmethod
    def from_case_dir(cls, dir_structure: DirStructure):
        attributes = pd.read_csv(dir_structure.resolve_settings_dir.joinpath("attributes.csv"), index_col="attribute")
        system_name = attributes.loc["system", "value"]

        # If user doesn't specify reporting settings, defaults to not reporting those results
        results_settings = dict()
        for setting in ["report_raw", "report_hourly", "report_chrono", "disagg_group"]:
            try:
                results_settings[setting] = convert_to_bool(attributes.loc[f"{setting}_results", "value"])
            except KeyError:
                results_settings[setting] = False
        logger.info(f"The following results reporting settings are enabled:")
        for key, value in results_settings.items():
            logger.info(f"{key} = {value}")

        # Solver settings can be defined in solver_settings.csv within the case settings directory
        if pathlib.Path(dir_structure.resolve_settings_dir.joinpath("solver_settings.csv")).exists():
            solver_settings = pd.read_csv(
                pathlib.Path(dir_structure.resolve_settings_dir.joinpath("solver_settings.csv")), index_col="solver"
            )
            if solver_settings.shape[0] > 0:  # guard clause for empty solver_settings csv
                solver_options = cls._get_solver_options(solver_settings)
                for solver, nested_dict in solver_options.items():
                    logger.info(f"The following solver options are enabled for solver {solver}:")
                    for key, value in nested_dict.items():
                        logger.info(f"{key} = {value}")
            else:
                solver_options = None
        # If no solver settings are specified, default settings are passed to solver.
        else:
            solver_options = None

        """Check if this model should create operational groups"""
        if "create_operational_groups" not in attributes.index:
            create_operational_groups = False
        else:
            create_operational_groups = convert_to_bool(attributes.loc["create_operational_groups", "value"])

        """When production simulation mode is on, a portfolio build established in a prior capacity expansion run
        is used to simulate an 8760 hourly system dispatch."""
        if "production_simulation_mode" not in attributes.index:
            production_simulation_mode = False
        else:
            production_simulation_mode = convert_to_bool(attributes.loc["production_simulation_mode", "value"])
            if production_simulation_mode:
                try:
                    # TODO: Come up with a way other than hard-coded strings to read-in the portfolio build directory
                    portfolio_build_results_dir = pathlib.Path(attributes.loc["portfolio_build_results_dir", "value"])
                except KeyError as e:
                    logger.error("A portfolio_build_results_dir must be included in production simulation mode.")
                    raise e

        """Check if system should be saved to json files after run. Default to True (save as json files)."""
        if "save_system_to_json" not in attributes.index:
            save_system_to_json = False
        else:
            save_system_to_json = convert_to_bool(attributes.loc["save_system_to_json", "value"])
        if not save_system_to_json:
            logger.info(
                "System attribute: save_system_to_json set to False, system will not be saved to json files after run."
            )

        if (dir_structure.resolve_settings_dir / "scenarios.csv").is_file():
            logger.debug(f"Reading scenario settings")
            scenarios = pd.read_csv(dir_structure.resolve_settings_dir / "scenarios.csv")
            if all(x in scenarios.columns for x in ["priority", "include"]):
                scenarios = (
                    scenarios.sort_values(by=["priority"], ascending=True)
                    .loc[scenarios["include"] == True, "scenarios"]
                    .tolist()
                )
            else:
                scenarios = scenarios["scenarios"].tolist()
        else:
            logger.warning("No scenarios.csv file found - using only default blank scenario")
            scenarios = []

        if production_simulation_mode:
            logger.info(f"Copying System instance from system of previous model build")
            system_instance = System.from_json(
                filepath=dir_structure.proj_dir / portfolio_build_results_dir,
                data={"dir_str": dir_structure},
            )
            # TODO: This is a hacky way to read renewable profiles from CSVs again (can't import from json because we
            #  want full profiles, not rescaled and resampled)
            for variable in (system_instance.variable_resources | system_instance.variable_resource_groups).values():
                variable_resource_filepath = (
                    dir_structure.data_interim_dir / variable.SAVE_PATH / f"{variable.name}.csv"
                )
                electric_resource_filepath = dir_structure.data_interim_dir / f"resources/{variable.name}.csv"
                electric_group_filepath = dir_structure.data_interim_dir / f"resources/groups/{variable.name}.csv"
                # Check if pmax profile is in resources/wind or resources/solar
                if variable_resource_filepath.exists():
                    variable.power_output_max = variable.__class__.from_csv(
                        filename=variable_resource_filepath, scenarios=scenarios
                    ).power_output_max
                # Check if pmax profile is in resources/ (i.e., instantiated as ElectricResource)
                elif electric_resource_filepath.exists():
                    variable.power_output_max = ElectricResource.from_csv(
                        filename=electric_resource_filepath, scenarios=scenarios
                    ).power_output_max
                # Check if pmax profile is in resources/groups/solar or resources/groups/wind
                elif electric_group_filepath.exists():
                    variable.power_output_max = ElectricResourceGroup.from_csv(
                        filename=electric_group_filepath, scenarios=scenarios
                    ).power_output_max
                # Check if pmax profile is in resources/groups (i.e., instantiated as ElectricResourceGroup)
                elif variable.vintage_parent_group is not None:
                    # Get power_output_max from vintage parent group
                    vintage_parent_group = variable.asset_groups[variable.vintage_parent_group].instance_to
                    vintage_group_filepath = (
                        dir_structure.data_interim_dir / f"resources/groups/{vintage_parent_group.name}.csv"
                    )
                    if vintage_group_filepath.exists():
                        variable.power_output_max = ElectricResourceGroup.from_csv(
                            filename=vintage_group_filepath, scenarios=scenarios
                        ).power_output_max
                    else:
                        raise FileNotFoundError(
                            f"Power output max profile not found for {variable.__class__.__name__} {variable.name}."
                        )
                else:
                    raise FileNotFoundError(
                        f"Power output max profile not found for {variable.__class__.__name__} {variable.name}."
                    )

        else:
            logger.info(f"Reading data for System instance `{system_name}`")
            _, system_instance = System.from_csv(
                filename=dir_structure.data_interim_dir / "systems" / system_name / "attributes.csv",
                scenarios=scenarios,
                data={"dir_str": dir_structure},
            )

        # read in representative days settings
        temporal_settings = TemporalSettings.from_dir(dir_structure.resolve_settings_rep_periods_dir)

        resolve_model = cls(
            temporal_settings=temporal_settings,
            system=system_instance,
            results_settings=results_settings,
            create_operational_groups=create_operational_groups,
            solver_options=solver_options,
            production_simulation_mode=production_simulation_mode,
            save_system_to_json=save_system_to_json,
        )

        return resolve_model

    def export_results_summary(self, output_dir: pathlib.Path, results_reporting: dict):
        self.export_temporal_settings(output_dir=output_dir.parent.joinpath("temporal_settings/"))

        disagg_group_results = results_reporting["disagg_group"]

        slack_cost_summary = pd.DataFrame()
        cost_summary = pd.DataFrame()
        for component in self.system._optimization_construction_order:
            # Pull investment and operational costs for the component
            costs_df = pd.concat(
                {
                    "Annual Total Investment Cost ($)": convert_pyomo_object_to_dataframe(
                        component.formulation_block.annual_total_investment_cost, use_doc_as_column_name=True
                    ).squeeze(axis=1),
                    "Annual Total Operational Cost ($)": convert_pyomo_object_to_dataframe(
                        component.formulation_block.annual_total_operational_cost, use_doc_as_column_name=True
                    ).squeeze(axis=1),
                },
                axis=1,
            )

            # Append slack costs for summary output. If slack investment costs or slack operational costs,
            # don't exist then just append an empty Series.
            block = component.formulation_block
            slack_costs_dict = dict()
            if hasattr(block, "annual_total_slack_investment_cost"):
                slack_costs_dict["Annual Total Slack Investment Cost ($)"] = convert_pyomo_object_to_dataframe(
                    block.annual_total_slack_investment_cost, use_doc_as_column_name=True
                ).squeeze(axis=1)
            else:
                slack_costs_dict["Annual Total Slack Investment Cost ($)"] = pd.Series(
                    index=self.MODELED_YEARS, dtype="object"
                )
            if hasattr(block, "annual_total_slack_operational_cost"):
                slack_costs_dict["Annual Total Slack Operational Cost ($)"] = convert_pyomo_object_to_dataframe(
                    block.annual_total_slack_operational_cost, use_doc_as_column_name=True
                ).squeeze(axis=1)
            else:
                slack_costs_dict["Annual Total Slack Operational Cost ($)"] = pd.Series(
                    index=self.MODELED_YEARS, dtype="object"
                )
            slack_costs_df = pd.concat(slack_costs_dict, axis=1)

            for df in [costs_df, slack_costs_df]:
                df["Component Name"] = component.name
                df["Component Type"] = component.__class__.__name__
                df.set_index(["Component Name", "Component Type", df.index], inplace=True)
                df.rename_axis(index=("Component Name", "Component Type", "Modeled Year"), inplace=True)

                # Insert column for the zone(s) to which this component is linked (if it is linked to a zone)
                if hasattr(component, "zones"):
                    zones = ",".join(map(str, component.zones.keys()))
                else:
                    zones = ""
                df.insert(0, "Zone(s)", zones)

            # Concat component cost_summary with the df for all other components
            cost_summary = pd.concat([cost_summary, costs_df])
            slack_cost_summary = pd.concat([slack_cost_summary, slack_costs_df])

        # Export to csv
        cost_summary.to_csv(output_dir.joinpath("component_cost_summary.csv"))
        slack_cost_summary.to_csv(output_dir.joinpath("component_slack_cost_summary.csv"))

        if disagg_group_results:
            for asset_group in tqdm(
                self.system.asset_groups.values(),
                desc="Updating results to assets linked to asset groups:".rjust(50),
                bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
            ):
                asset_group.update_assets_with_results()

        # Save capacity decisions as asset attributes. These are stored on the system and can be used in a future
        # production simulation run
        for asset in self.system.assets.values():
            asset.save_capacity_expansion_results()

        annual_results = defaultdict(list)
        category_column_orders = dict()
        category_components = dict()
        annual_by_product_results = defaultdict(list)
        for component in tqdm(
            # Order of components list is reversed because of dependencies on zonal price expressions being created
            # prior to the creation of expressions in other components
            list(self.system._optimization_construction_order)[::-1],
            desc="Exporting summary results:".ljust(50),
            bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
        ):
            category = component.results_reporting_category
            annual_summary, annual_by_product_summary = component.export_component_result_summary(
                output_dir=output_dir, results_settings=results_reporting
            )
            annual_results[category].append(annual_summary)
            if not all([isinstance(product, Electricity) for product in self.system.products.values()]):
                # Don't print annual by product summaries if only Electricity products in system
                if len(annual_by_product_summary) > 0:
                    annual_by_product_results[component.results_reporting_category].append(annual_by_product_summary)

            # Check if it's necessary to reorder the summary columns
            if hasattr(component, "annual_results_column_order"):
                # Add correct order of columns
                if category not in category_column_orders:
                    category_column_orders[category] = component.annual_results_column_order
                # Add components in this category
                if category not in category_components.keys():
                    category_components[category] = [component]
                else:
                    category_components[category].append(component)

        logger.info("Exporting annual results summary...")
        for category in annual_results.keys():
            concat_results = [
                x for x in annual_results[category] if isinstance(x, pd.Series) or isinstance(x, pd.DataFrame)
            ]
            if len(concat_results) > 0:
                concat_df = pd.concat(concat_results)

                # Reorder columns if required
                if category in category_column_orders.keys():
                    ordered_columns = self._order_annual_results_summary_columns(
                        components=category_components[category],
                        column_order=category_column_orders[category],
                        annual_results_summary=concat_df,
                        category=category,
                    )
                    # Add an empty column to keep all columns in exact same place
                    for col in ordered_columns:
                        if col not in concat_df.columns:
                            concat_df[col] = None
                    concat_df = concat_df[ordered_columns]

                # Export annual results summaries to CSV
                concat_df.to_csv(output_dir / f"{category}_annual_results_summary.csv", index=True)

        for category in annual_by_product_results.keys():
            concat_results = [
                x
                for x in annual_by_product_results[category]
                if isinstance(x, pd.Series) or isinstance(x, pd.DataFrame)
            ]
            if len(concat_results) > 0:
                concat_df = pd.concat(concat_results)
                concat_df.to_csv(output_dir / f"{category}_annual_results_by_product_summary.csv", index=True)

    def _order_annual_results_summary_columns(
        self, components: list, column_order: list, annual_results_summary: pd.DataFrame, category: str
    ) -> list:
        """The desired order of columns in the component's annual results summary

        Args:
            annual_results: annual results summary dataframe
        """
        ordered_columns = []
        for column in column_order:
            column_added = False
            for component in components:
                field_dict = component.model_fields | component.model_computed_fields
                # Check if column refers to a pyomo component and exists in any of the category's components
                if (
                    hasattr(component.formulation_block, column)
                    and getattr(component.formulation_block, column).doc in annual_results_summary.columns
                ):
                    column_added = True
                    ordered_columns.append(getattr(component.formulation_block, column).doc)
                    break
                # Check if column refers to an attribute and exists in any of the category's components
                elif column in field_dict.keys() and field_dict[column].title in annual_results_summary.columns:
                    column_added = True
                    ordered_columns.append(field_dict[column].title)
                    break
            if not column_added:
                # Add an empty column to keep all columns in exact same place
                ordered_columns.append(f"{column}: no data")
                logger.warning(
                    f"For {category} annual results summary, no annual output data exists for desired output column {column}."
                )
        return ordered_columns

    def export_raw_results(self, dir_structure: DirStructure):
        Parallel()(
            delayed(component.export_formulation_block_raw_results)(
                output_dir=dir_structure.output_resolve_raw_results_dir
            )
            for component in tqdm(
                self.system._optimization_construction_order,
                desc="Exporting raw results:".rjust(50),
                bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
            )
        )
