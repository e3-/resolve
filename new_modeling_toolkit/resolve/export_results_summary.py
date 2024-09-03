import os
from dataclasses import dataclass
from typing import Dict
from typing import Optional
from typing import Tuple
from typing import Union

import pandas as pd
from loguru import logger

from new_modeling_toolkit.common.temporal import TemporalSettings
from new_modeling_toolkit.core.component import Component
from new_modeling_toolkit.core.utils.core_utils import timer
from new_modeling_toolkit.core.utils.pandas_utils import convert_index_levels_to_datetime
from new_modeling_toolkit.resolve.model_formulation import ResolveCase


# Define mappings between component attribute names and columns in output summary CSV files.
_ASSET_ATTRIBUTE_COLUMN_MAPPING = {
    "Planned Capacity (MW)": "planned_installed_capacity",
    "New Build Capacity (MW)": "opt_operational_new_capacity",
    "Operational Capacity (MW)": "opt_total_operational_capacity",
    "Potential (MW)": "potential",
    "Capital Cost ($)": "opt_annual_installed_cost_dollars",
    "Fixed O&M Cost ($)": "opt_annual_fixed_om_cost_dollars",
}
_ELECTROLYZER_COLUMN_ATTRIBUTE_MAPPING = {
    "Planned Capacity (MW)": "planned_installed_capacity",
    "New Build Capacity (MW)": "opt_operational_new_capacity",
    "Retired Capacity (MW)": "opt_retired_capacity",
    "Operational Capacity (MW)": "opt_total_operational_capacity",
    "Potential (MW)": "potential",
    "Gross Increase Load (MWh)": "opt_annual_increase_load_mwh",
    "Produced Fuel (MMBtu)": "opt_annual_produced_fuel_mmbtu",
    "Capital Cost ($)": "opt_annual_installed_cost_dollars",
    "Fixed O&M Cost ($)": "opt_annual_fixed_om_cost_dollars",
    "Variable Cost ($)": "opt_annual_variable_cost_dollars",
}
_FUEL_CONVERSION_PLANT_ATTRIBUTE_COLUMN_MAPPING = {
    "Planned Capacity (MMBtu/hr)": "planned_installed_capacity",
    "New Build Capacity (MMBtu/hr)": "opt_operational_new_capacity",
    "Retired Capacity (MMBtu/hr)": "opt_retired_capacity",
    "Operational Capacity (MMBtu/hr)": "opt_total_operational_capacity",
    "Potential (MMBtu/hr)": "potential",
    "Input Fuel Consumption (MMBtu)": "opt_annual_fuel_consumption_all_fuels_mmbtu",
    "Produced Fuel (MMBtu)": "opt_annual_produced_fuel_mmbtu",
    "Gross Provide Power (MWh)": "opt_annual_provide_power_mwh",
    "Net Generation (MWh)": "opt_annual_net_generation_mwh",
    "Capital Cost ($)": "opt_annual_installed_cost_dollars",
    "Fixed O&M Cost ($)": "opt_annual_fixed_om_cost_dollars",
    "Variable Cost ($)": "opt_annual_variable_cost_dollars",
    "Fuel Cost ($)": "opt_annual_fuel_cost_dollars",
}
_FUEL_STORAGE_COLUMN_ATTRIBUTE_MAPPING = {
    "Planned Capacity (MMBtu/hr)": "planned_installed_capacity",
    "New Build Capacity (MMBtu/hr)": "opt_operational_new_capacity",
    "Retired Capacity (MMBtu/hr)": "opt_retired_capacity",
    "Operational Capacity (MMBtu/hr)": "opt_total_operational_capacity",
    "Potential (MMBtu/hr)": "potential",
    "Planned Capacity (MMBtu)": "planned_storage_capacity",
    "New Build Capacity (MMBtu)": "opt_operational_new_storage_capacity",
    "Retired Capacity (MMBtu)": "opt_retired_storage_capacity",
    "Operational Capacity (MMBtu)": "opt_total_operational_storage_capacity",
    "Gross Increase Load (MWh)": "opt_annual_increase_load_mwh",
    "Capital Cost ($)": "opt_annual_installed_cost_dollars",
    "Fixed O&M Cost ($)": "opt_annual_fixed_om_cost_dollars",
    "Variable Cost ($)": "opt_annual_variable_cost_dollars",
}
_FUEL_TRANSPORTATION_ATTRIBUTE_COLUMN_MAPPING = {
    "Planned Capacity (MMBtu/hr)": "planned_installed_capacity",
    "New Build Capacity (MMBtu/hr)": "opt_operational_new_capacity",
    "Retired Capacity (MMBtu/hr)": "opt_retired_capacity",
    "Operational Capacity (MMBtu/hr)": "opt_total_operational_capacity",
    "Capital Cost ($)": "opt_annual_installed_cost_dollars",
    "Forward Hurdle Cost ($)": "opt_annual_hurdle_cost_forward_dollars",
    "Reverse Hurdle Cost ($)": "opt_annual_hurdle_cost_reverse_dollars",
    "Gross Forward Flow (MMBtu)": "opt_annual_flow_forward_mmbtu",
    "Gross Reverse Flow (MMBtu)": "opt_annual_flow_reverse_mmbtu",
}
_EMISSIONS_POLICY_TX_PATH_COLUMN_ATTRIBUTE_MAPPING = {
    "Annual Policy Contribution (tonne)": "opt_annual_contribution_by_tx_path"
}
_EMISSIONS_POLICY_RESOURCE_COLUMN_ATTRIBUTE_MAPPING = {
    "Annual Policy Contribution (tonne)": "opt_annual_contribution_by_resource"
}
_ENERGY_POLICY_ATTRIBUTE_COLUMN_MAPPING = {
    "Annual Policy Contribution (MWh)": "opt_annual_contribution_by_resource_mwh"
}
_FUEL_BURN_ATTRIBUTE_COLUMN_MAPPING = {
    "Annual Fuel Consumption (MMBtu)": "opt_annual_fuel_consumption_by_fuel_mmbtu",
}
_POLICY_DUALS_ATTRIBUTE_COLUMN_MAPPING = {
    "Target (Units)": "target",
    "Target Adjustment (Units)": "target_adjustment",
    "Dual Value ($/Unit)": "opt_dual_value_unweighted",
    "Achieved (Units)": "opt_policy_lhs",
}
_PRM_POLICY_RESOURCE_SUMMARY_COLUMN_ATTRIBUTE_MAPPING = {
    "Reliability Capacity (MW)": "opt_resource_reliability_capacity",
    "NQC (MW)": "opt_resource_nqc",
}
_RESOURCE_ATTRIBUTE_COLUMN_MAPPING = {
    "Planned Capacity (MW)": "planned_installed_capacity",
    "New Build Capacity (MW)": "opt_operational_new_capacity",
    "Retired Capacity (MW)": "opt_retired_capacity",
    "Operational Capacity (MW)": "opt_total_operational_capacity",
    "Potential (MW)": "potential",
    "Planned Capacity (MWh)": "planned_storage_capacity",
    "New Build Capacity (MWh)": "opt_operational_new_storage_capacity",
    "Retired Capacity (MWh)": "opt_retired_storage_capacity",
    "Operational Capacity (MWh)": "opt_total_operational_storage_capacity",
    "Gross Increase Load (MWh)": "opt_annual_increase_load_mwh",
    "Gross Provide Power (MWh)": "opt_annual_provide_power_mwh",
    "Net Generation (MWh)": "opt_annual_net_generation_mwh",
    "Curtailed Energy (MWh)": "opt_annual_curtailment_mwh",
    "Number of Starts": "opt_annual_start_units",
    "Number of Shutdowns": "opt_annual_shutdown_units",
    "Capital Cost ($)": "opt_annual_installed_cost_dollars",
    "Fixed O&M Cost ($)": "opt_annual_fixed_om_cost_dollars",
    "Variable Cost ($)": "opt_annual_variable_cost_dollars",
    "Fuel Cost ($)": "opt_annual_fuel_cost_dollars",
    "Curtailment Cost ($)": "opt_annual_curtailment_cost_dollars",
    "Start Cost ($)": "opt_annual_start_cost_dollars",
    "Shutdown Cost ($)": "opt_annual_shutdown_cost_dollars",
}
_RESOURCE_DISPATCH_ATTRIBUTE_COLUMN_MAPPING = {
    "Provide Power (MW)": "opt_provide_power_mw",
    "Increase Load (MW)": "opt_increase_load_mw",
}
_TRANSMISSION_ATTRIBUTE_COLUMN_MAPPING = {
    "Capital Cost ($)": "opt_annual_installed_cost_dollars",
    "Forward Hurdle Cost ($)": "opt_annual_hurdle_cost_forward_dollars",
    "Reverse Hurdle Cost ($)": "opt_annual_hurdle_cost_reverse_dollars",
    "Forward Flow Value (To Zone) ($)": "opt_forward_flow_to_zone_value",
    "Forward Flow Value (From Zone) ($)": "opt_forward_flow_from_zone_value",
    "Reverse Flow Value (To Zone) ($)": "opt_reverse_flow_to_zone_value",
    "Reverse Flow Value (From Zone) ($)": "opt_reverse_flow_from_zone_value",
    "Gross Reverse Flow (MWh)": "opt_annual_transmit_power_reverse_mwh",
    "Gross Forward Flow (MWh)": "opt_annual_transmit_power_forward_mwh",
    "Planned Capacity (MW)": "planned_installed_capacity",
    "New Build Capacity (MW)": "opt_operational_new_capacity",
    "Retired Capacity (MW)": "opt_retired_capacity",
    "Operational Capacity (MW)": "opt_total_operational_capacity",
    "Potential (MW)": "potential",
}
_ZONAL_ATTRIBUTE_COLUMN_MAPPING = {
    "Unserved Energy (MWh)": "opt_annual_unserved_energy_mwh",
    "Overgeneration (MWh)": "opt_annual_overgeneration_mwh",
    "Net Generation (MWh)": "opt_annual_net_generation_mwh",
    "Gross Imports (MWh)": "opt_annual_imports_mwh",
    "Gross Exports (MWh)": "opt_annual_exports_mwh",
    "Net Imports (MWh)": "opt_annual_net_imports_mwh",
    "Input Load (MWh)": "opt_annual_input_load_mwh",
}
_ZONAL_PRICE_ATTRIBUTE_COLUMN_MAPPING = {"Energy Price ($/MWh)": "opt_hourly_energy_price_unweighted_dollars_per_mwh"}


# Define names of output summary CSV files for different component types.
ASSET_SUMMARY_FILENAME = "asset_summary.csv"
ELECTROLYZER_SUMMARY_FILENAME = "electrolyzer_summary.csv"
FUEL_CONVERSION_PLANT_SUMMARY_FILENAME = "fuel_conversion_plant_summary.csv"
FUEL_STORAGE_SUMMARY_FILENAME = "fuel_storage_summary.csv"
FUEL_TRANSPORTATION_SUMMARY_FILENAME = "fuel_transportation_summary.csv"
EMISSIONS_POLICY_RESOURCE_SUMMARY_FILENAME = "emissions_policy_resource_summary.csv"
EMISSIONS_POLICY_TX_PATH_SUMMARY_FILENAME = "emissions_policy_tx_path_summary.csv"
ENERGY_POLICY_SUMMARY_FILENAME = "energy_policy_summary.csv"
POLICY_SUMMARY_FILENAME = "policy_summary.csv"
PRM_POLICY_RESOURCE_SUMMARY_FILENAME = "prm_policy_resource_summary.csv"
RESOURCE_DISPATCH_SUMMARY_FILENAME = "resource_dispatch_summary.csv"
RESOURCE_FUEL_BURN_SUMMARY_FILENAME = "resource_fuel_burn_summary.csv"
RESOURCE_SUMMARY_FILENAME = "resource_summary.csv"
SYSTEM_SUMMARY_FILENAME = "system_summary.csv"
TRANSMISSION_SUMMARY_FILENAME = "transmission_summary.csv"
ZONAL_PRICE_SUMMARY_FILENAME = "zonal_price_summary.csv"
ZONAL_SUMMARY_FILENAME = "zonal_summary.csv"

# Define column names for index columns in output CSV summary files.
ASSET = "Asset"
FUEL_CONVERSION_PLANT = "Fuel Conversion Plant"
FUEL_ZONE = "Fuel Zone"
ELECTROLYZER = "Electrolyzer"
FUEL_STORAGE = "Fuel Storage"
FUEL_TRANSPORTATION = "Fuel Transportation"
FUEL = "Fuel"
MODEL_YEAR = "Model Year"
POLICY = "Policy"
RESOURCE = "Resource"
SYSTEM = "System"
TRANSMISSION_PATH = "Transmission Path"
ZONE = "Zone"
ZONE_FROM = "Zone From"
ZONE_TO = "Zone To"


@dataclass
class FileConfig:
    """Helper class to store data for each output summary CSV file"""

    component_dict: Dict[str, Component]
    column_attribute_mapping: Dict[str, str]
    index_names: Tuple[str, ...]
    attributes_are_timeseries: bool
    add_electric_zone_to_index: bool
    filename: str

    add_fuel_zone_to_index: bool = False
    index_levels_convert_to_datetime: Optional[Union[str, list[str, ...]]] = None


def _create_attribute_df(
    component_dict: Dict[str, Component],
    column_attribute_mapping: Dict[str, str],
    index_names: tuple[str, ...],
    attributes_are_timeseries: bool = True,
    add_electric_zone_to_index: bool = False,
    add_fuel_zone_to_index: bool = False,
) -> pd.DataFrame:
    """Creates a DataFrame by concatenating attributes of Components together column-wise and by concatenating
    Components together row-wise.

    Args:
        component_dict: dictionary containing Component names as keys and Component objects as values
        column_attribute_mapping: dictionary mapping from output column name to Component attribute
        index_names: names for the resulting row index levels
        attributes_are_timeseries: whether or not the attrributes in `column_attribute_mapping` are Timeseries objects
        add_electric_zone_to_index: whether to add the component's linked electric zone as a level in the index
        add_fuel_zone_to_index: whether to add the component's linked fuel zone as a level in the index

    Returns:
        component_data: the DataFrame containing data from the attributes of all Components
    """
    component_dfs = {}
    for component_name, component in component_dict.items():
        curr_component_data = {
            column_name: (
                getattr(component, attribute).data if attributes_are_timeseries else getattr(component, attribute)
            )
            for column_name, attribute in column_attribute_mapping.items()
            if getattr(component, attribute) is not None
        }
        if len(curr_component_data) > 0:
            # Extract the attributes for the current Component
            curr_component_df = pd.concat(curr_component_data, axis=1)

        else:
            curr_component_df = pd.DataFrame(columns=list(column_attribute_mapping.keys()))

        # Append the zone of the Component to the index for output
        component_key = [component_name]
        if add_electric_zone_to_index:
            electric_zone = list(component.zones.keys())[0] if component.zones else None
            component_key.append(electric_zone)
        if add_fuel_zone_to_index:
            fuel_zone = list(component.fuel_zones.keys())[0] if component.fuel_zones else None
            component_key.append(fuel_zone)

        component_dfs[tuple(component_key)] = curr_component_df

    # Combine the data from all Components
    if len(component_dfs) > 0:
        component_data = pd.concat(component_dfs, axis=0)

        # Ensure that all output columns are present, even if the attributes are None for all Components
        component_data = component_data.reindex(
            columns=list(column_attribute_mapping.keys()),
        )

        component_data = component_data.rename_axis(index=index_names)
    else:
        component_data = pd.DataFrame(
            columns=list(column_attribute_mapping.keys()), index=pd.MultiIndex.from_tuples([], names=index_names)
        )

    return component_data


def _reindex_to_modeled_years(df: pd.DataFrame, temporal_settings: TemporalSettings) -> pd.DataFrame:
    """Helper method for reindexing results summary dataframes to only contain years that were modeled in RESOLVE.

    Many Timeseries attributes of System components are resampled to be continuous for all years in between the first
    and last modeled year, but the results summaries should only contain results for the modeled years to avoid
    confusion.

    Args:
        df: data frame to reindex
        temporal_settings: the TemporalSettings for the RESOLVE run

    Returns:
        reindexed_df: the input dataframe with non-modeled years removed
    """
    modeled_years_index = temporal_settings.modeled_years.data.loc[temporal_settings.modeled_years.data].index.rename(
        MODEL_YEAR
    )
    reindexed_df = df.reindex(modeled_years_index, level=MODEL_YEAR)

    return reindexed_df


def _create_temporal_settings_summary(resolve_case: ResolveCase) -> pd.DataFrame:
    temporal_settings_summary = resolve_case.temporal_settings.modeled_year_discount_factor.data.rename(
        "Discount Factor"
    ).to_frame()
    temporal_settings_summary = temporal_settings_summary.rename_axis(MODEL_YEAR)
    temporal_settings_summary.loc[:, "Cost Dollar Year"] = resolve_case.temporal_settings.cost_dollar_year
    temporal_settings_summary.loc[
        temporal_settings_summary.index.max(), "End Effect Years"
    ] = resolve_case.temporal_settings.end_effect_years

    temporal_settings_summary = temporal_settings_summary.rename_axis(MODEL_YEAR)

    return temporal_settings_summary


@timer
def export_all_results_summary(resolve_case: ResolveCase, output_dir: os.PathLike):
    os.makedirs(output_dir, exist_ok=True)

    # Write temporal settings summary
    temporal_settings_summary = _create_temporal_settings_summary(resolve_case)
    temporal_settings_summary.sort_index().to_csv(os.path.join(output_dir, "temporal_settings_summary.csv"))

    # Write system costs summary
    if system_cost_data := {cost: obj.annual_cost.data for cost, obj in resolve_case.system.system_costs.items()}:
        system_costs = pd.concat(system_cost_data, axis=1)
        system_costs.sort_index().to_csv(output_dir / "non_optimized_system_costs_summary.csv", index=True)

    # Hacky exporting of load components
    hourly_loads = resolve_case.hourly_loads
    resolve_case.hourly_loads.index.names = ["MODEL_YEARS", "REP_PERIODS", "HOURS"]
    resolve_case.hourly_loads.round(3).to_csv(output_dir / "hourly_load_components_summary.csv", index=True)

    # Calculate annual load components
    hourly_loads = hourly_loads.reset_index()
    hourly_loads = hourly_loads.merge(
        pd.Series(resolve_case.model.rep_periods_per_model_year.extract_values(), name="rep_periods_per_model_year"),
        left_on="MODEL_YEARS",
        right_index=True,
    )
    hourly_loads = hourly_loads.merge(
        pd.Series(resolve_case.model.rep_period_weight.extract_values(), name="rep_period_weight"),
        left_on="REP_PERIODS",
        right_index=True,
    )
    hourly_loads = hourly_loads.merge(
        pd.Series(resolve_case.temporal_settings.timesteps, name="timesteps"), left_on="HOURS", right_index=True
    )
    hourly_loads = hourly_loads.set_index(["MODEL_YEARS", "REP_PERIODS", "HOURS"])
    for col in hourly_loads.columns:
        if col not in ["rep_periods_per_model_year", "rep_period_weight", "timesteps"]:
            hourly_loads[col] = (
                hourly_loads[col]
                * hourly_loads["rep_periods_per_model_year"]
                * hourly_loads["rep_period_weight"]
                * hourly_loads["timesteps"]
            )
    annual_loads = (
        hourly_loads.groupby(level="MODEL_YEARS")
        .sum()
        .drop(["rep_periods_per_model_year", "rep_period_weight", "timesteps"], axis=1)
    )
    annual_loads.round(3).to_csv(output_dir / "annual_load_components_summary.csv", index=True)

    # Write out each config file
    for config in [
        FileConfig(
            component_dict=resolve_case.system.resources,
            column_attribute_mapping=_RESOURCE_ATTRIBUTE_COLUMN_MAPPING,
            add_electric_zone_to_index=True,
            index_names=(RESOURCE, ZONE, MODEL_YEAR),
            attributes_are_timeseries=True,
            index_levels_convert_to_datetime=None,
            filename=RESOURCE_SUMMARY_FILENAME,
        ),
        FileConfig(
            component_dict=resolve_case.system.resources,
            column_attribute_mapping=_RESOURCE_DISPATCH_ATTRIBUTE_COLUMN_MAPPING,
            attributes_are_timeseries=False,
            add_electric_zone_to_index=True,
            index_names=(RESOURCE, ZONE, MODEL_YEAR, "Rep_Period", "Hour"),
            index_levels_convert_to_datetime=MODEL_YEAR,
            filename=RESOURCE_DISPATCH_SUMMARY_FILENAME,
        ),
        FileConfig(
            component_dict=resolve_case.system.resources,
            column_attribute_mapping=_FUEL_BURN_ATTRIBUTE_COLUMN_MAPPING,
            attributes_are_timeseries=False,
            add_electric_zone_to_index=True,
            index_names=(RESOURCE, ZONE, FUEL, MODEL_YEAR),
            index_levels_convert_to_datetime=MODEL_YEAR,
            filename=RESOURCE_FUEL_BURN_SUMMARY_FILENAME,
        ),
        FileConfig(
            component_dict={
                asset_name: asset
                for asset_name, asset in resolve_case.system.electric_assets.items()
                if (
                    asset_name not in resolve_case.system.resources.keys()
                    and asset_name not in resolve_case.system.tx_paths.keys()
                )
            },
            column_attribute_mapping=_ASSET_ATTRIBUTE_COLUMN_MAPPING,
            attributes_are_timeseries=True,
            add_electric_zone_to_index=False,
            index_names=(ASSET, MODEL_YEAR),
            index_levels_convert_to_datetime=None,
            filename=ASSET_SUMMARY_FILENAME,
        ),
        FileConfig(
            component_dict=resolve_case.system.zones,
            column_attribute_mapping=_ZONAL_ATTRIBUTE_COLUMN_MAPPING,
            attributes_are_timeseries=True,
            add_electric_zone_to_index=False,
            index_names=(ZONE, MODEL_YEAR),
            index_levels_convert_to_datetime=None,
            filename=ZONAL_SUMMARY_FILENAME,
        ),
        FileConfig(
            component_dict=resolve_case.system.zones,
            column_attribute_mapping=_ZONAL_PRICE_ATTRIBUTE_COLUMN_MAPPING,
            attributes_are_timeseries=False,
            add_electric_zone_to_index=False,
            index_names=(ZONE, MODEL_YEAR, "Rep Period", "Hour"),
            index_levels_convert_to_datetime=None,
            filename=ZONAL_PRICE_SUMMARY_FILENAME,
        ),
        FileConfig(
            component_dict=resolve_case.system.tx_paths,
            column_attribute_mapping=_TRANSMISSION_ATTRIBUTE_COLUMN_MAPPING,
            attributes_are_timeseries=True,
            add_electric_zone_to_index=False,
            index_names=(TRANSMISSION_PATH, MODEL_YEAR),
            index_levels_convert_to_datetime=None,
            filename=TRANSMISSION_SUMMARY_FILENAME,
        ),
        FileConfig(
            component_dict=resolve_case.system.policies,
            column_attribute_mapping=_POLICY_DUALS_ATTRIBUTE_COLUMN_MAPPING,
            add_electric_zone_to_index=False,
            index_names=(POLICY, MODEL_YEAR),
            attributes_are_timeseries=True,
            index_levels_convert_to_datetime=None,
            filename=POLICY_SUMMARY_FILENAME,
        ),
        FileConfig(
            component_dict={
                policy_name: policy
                for policy_name, policy in resolve_case.system.policies.items()
                if policy.type == "energy"
            },
            column_attribute_mapping=_ENERGY_POLICY_ATTRIBUTE_COLUMN_MAPPING,
            attributes_are_timeseries=False,
            add_electric_zone_to_index=False,
            index_names=(POLICY, RESOURCE, MODEL_YEAR),
            index_levels_convert_to_datetime=MODEL_YEAR,
            filename=ENERGY_POLICY_SUMMARY_FILENAME,
        ),
        FileConfig(
            component_dict={
                policy_name: policy
                for policy_name, policy in resolve_case.system.policies.items()
                if policy.type == "emissions"
            },
            column_attribute_mapping=_EMISSIONS_POLICY_RESOURCE_COLUMN_ATTRIBUTE_MAPPING,
            attributes_are_timeseries=False,
            add_electric_zone_to_index=False,
            index_names=(POLICY, RESOURCE, MODEL_YEAR),
            index_levels_convert_to_datetime=MODEL_YEAR,
            filename=EMISSIONS_POLICY_RESOURCE_SUMMARY_FILENAME,
        ),
        FileConfig(
            component_dict={
                policy_name: policy
                for policy_name, policy in resolve_case.system.policies.items()
                if policy.type == "emissions"
            },
            column_attribute_mapping=_EMISSIONS_POLICY_TX_PATH_COLUMN_ATTRIBUTE_MAPPING,
            attributes_are_timeseries=False,
            add_electric_zone_to_index=False,
            index_names=(POLICY, TRANSMISSION_PATH, MODEL_YEAR),
            index_levels_convert_to_datetime=MODEL_YEAR,
            filename=EMISSIONS_POLICY_TX_PATH_SUMMARY_FILENAME,
        ),
        FileConfig(
            component_dict={
                policy_name: policy
                for policy_name, policy in resolve_case.system.policies.items()
                if policy.type == "prm"
            },
            column_attribute_mapping=_PRM_POLICY_RESOURCE_SUMMARY_COLUMN_ATTRIBUTE_MAPPING,
            attributes_are_timeseries=False,
            add_electric_zone_to_index=False,
            index_names=(POLICY, RESOURCE, MODEL_YEAR),
            index_levels_convert_to_datetime=MODEL_YEAR,
            filename=PRM_POLICY_RESOURCE_SUMMARY_FILENAME,
        ),
        FileConfig(
            component_dict=resolve_case.system.electrolyzers,
            column_attribute_mapping=_ELECTROLYZER_COLUMN_ATTRIBUTE_MAPPING,
            index_names=(ELECTROLYZER, ZONE, FUEL_ZONE, MODEL_YEAR),
            add_electric_zone_to_index=True,
            add_fuel_zone_to_index=True,
            attributes_are_timeseries=True,
            index_levels_convert_to_datetime=MODEL_YEAR,
            filename=ELECTROLYZER_SUMMARY_FILENAME,
        ),
        FileConfig(
            component_dict=resolve_case.system.fuel_storages,
            column_attribute_mapping=_FUEL_STORAGE_COLUMN_ATTRIBUTE_MAPPING,
            index_names=(FUEL_STORAGE, ZONE, FUEL_ZONE, MODEL_YEAR),
            add_electric_zone_to_index=True,
            add_fuel_zone_to_index=True,
            attributes_are_timeseries=True,
            index_levels_convert_to_datetime=None,
            filename=FUEL_STORAGE_SUMMARY_FILENAME,
        ),
        FileConfig(
            component_dict=resolve_case.system.fuel_transportations,
            column_attribute_mapping=_FUEL_TRANSPORTATION_ATTRIBUTE_COLUMN_MAPPING,
            index_names=(FUEL_TRANSPORTATION, MODEL_YEAR),
            add_electric_zone_to_index=False,
            add_fuel_zone_to_index=False,
            attributes_are_timeseries=True,
            index_levels_convert_to_datetime=None,
            filename=FUEL_TRANSPORTATION_SUMMARY_FILENAME,
        ),
        FileConfig(
            component_dict=resolve_case.system.fuel_conversion_plants,
            column_attribute_mapping=_FUEL_CONVERSION_PLANT_ATTRIBUTE_COLUMN_MAPPING,
            index_names=(FUEL_CONVERSION_PLANT, ZONE, FUEL_ZONE, MODEL_YEAR),
            attributes_are_timeseries=True,
            add_electric_zone_to_index=True,
            add_fuel_zone_to_index=True,
            index_levels_convert_to_datetime=MODEL_YEAR,
            filename=FUEL_CONVERSION_PLANT_SUMMARY_FILENAME,
        ),
    ]:
        # Create the summary dataframe
        logger.info(f"Saving {config.filename}")
        summary_frame = _create_attribute_df(
            component_dict=config.component_dict,
            column_attribute_mapping=config.column_attribute_mapping,
            add_electric_zone_to_index=config.add_electric_zone_to_index,
            add_fuel_zone_to_index=config.add_fuel_zone_to_index,
            index_names=config.index_names,
            attributes_are_timeseries=config.attributes_are_timeseries,
        )

        # Add the "to" and "from" zones for transmission lines to the index for output
        if config.filename == TRANSMISSION_SUMMARY_FILENAME:
            if len(summary_frame) > 0:
                zone_names = pd.DataFrame.from_dict(
                    {
                        tx_path_name: {
                            ZONE_FROM: tx_path.from_zone._instance_from.name,
                            ZONE_TO: tx_path.to_zone._instance_from.name,
                        }
                        for tx_path_name, tx_path in resolve_case.system.tx_paths.items()
                    },
                    orient="index",
                ).rename_axis(index=TRANSMISSION_PATH)

                summary_frame = summary_frame.join(zone_names, on=TRANSMISSION_PATH, how="left")

                summary_frame = summary_frame.set_index([ZONE_FROM, ZONE_TO], append=True).reorder_levels(
                    [TRANSMISSION_PATH, ZONE_FROM, ZONE_TO, MODEL_YEAR]
                )
            else:
                summary_frame.index = pd.MultiIndex.from_tuples(
                    [], names=[TRANSMISSION_PATH, ZONE_FROM, ZONE_TO, MODEL_YEAR]
                )

        # Add the "to" and "from" zones for the fuel transportation component to the index for output
        if config.filename == FUEL_TRANSPORTATION_SUMMARY_FILENAME:
            if len(summary_frame) > 0:
                zone_names = pd.DataFrame.from_dict(
                    {
                        fuel_transportation_name: {
                            ZONE_FROM: fuel_transportation.from_zone._instance_from.name,
                            ZONE_TO: fuel_transportation.to_zone._instance_from.name,
                        }
                        for fuel_transportation_name, fuel_transportation in resolve_case.system.fuel_transportations.items()
                    },
                    orient="index",
                ).rename_axis(index=FUEL_TRANSPORTATION)

                summary_frame = summary_frame.join(zone_names, on=FUEL_TRANSPORTATION, how="left")

                summary_frame = summary_frame.set_index([ZONE_FROM, ZONE_TO], append=True).reorder_levels(
                    [FUEL_TRANSPORTATION, ZONE_FROM, ZONE_TO, MODEL_YEAR]
                )
            else:
                summary_frame.index = pd.MultiIndex.from_tuples(
                    [], names=[FUEL_TRANSPORTATION, ZONE_FROM, ZONE_TO, MODEL_YEAR]
                )

        # Convert index levels to datetime objects, if necessary
        if config.index_levels_convert_to_datetime is not None:
            summary_frame = convert_index_levels_to_datetime(
                summary_frame, levels=config.index_levels_convert_to_datetime, format="%Y"
            )

        # Reindex to ensure all model years are included in the output
        summary_frame = _reindex_to_modeled_years(summary_frame, temporal_settings=resolve_case.temporal_settings)

        # Write the output file
        summary_frame.round(3).sort_index().to_csv(output_dir / config.filename)
