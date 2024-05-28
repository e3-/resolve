import re
import shutil
import sys

import pandas as pd
import pyomo.environ as pyo
from loguru import logger
from tqdm import tqdm

from new_modeling_toolkit.core.utils.core_utils import timer
from new_modeling_toolkit.core.utils.pyomo_utils import convert_pyomo_object_to_dataframe
from new_modeling_toolkit.core.utils.util import DirStructure
from new_modeling_toolkit.resolve.model_formulation import ResolveCase

### Custom results reporting functions

### Functions for creating config files and writing out results


def get_object_type_dict(resolve_case: ResolveCase):
    """

    Args:
        resolve_case: new_modeling_toolkit.resolve.ResolveModel

    Returns:

    """

    # Get configuration file directory
    return {
        "Variable": {"object": pyo.Var, "output_dir": resolve_case.dir_structure.outputs_resolve_var_dir},
        "Expression": {"object": pyo.Expression, "output_dir": resolve_case.dir_structure.outputs_resolve_exp_dir},
        "Constraint": {
            "object": pyo.Constraint,
            "output_dir": resolve_case.dir_structure.outputs_resolve_constraint_dir,
        },
        "Parameter": {"object": pyo.Param, "output_dir": resolve_case.dir_structure.outputs_resolve_param_dir},
        "Set": {"object": pyo.Set, "output_dir": resolve_case.dir_structure.outputs_resolve_set_dir},
    }


def _export_temporal_settings(dir_str: DirStructure):
    """Exports the temporal settings used in the model to the results folder.

    This function currently assumes that the TemporalSettings instance has been instantiated and
    `find_representative_periods()` has been run, which writes the requisite representative periods files to
    the RESOLVE case's input settings directory. Therefore, this directory can just be copied to the results folder.

    Args:
        dir_str: the model's DirStructure instance
    """
    # Copy the input attributes.csv file to the results directory
    # Note: this is done for two reasons. First
    shutil.copytree(
        src=dir_str.resolve_settings_rep_periods_dir,
        dst=dir_str.output_resolve_temporal_settings_dir,
        dirs_exist_ok=True,
    )


def _export_scaled_load_components(resolve_case: ResolveCase, raw_results: bool = False):
    """Export individual scaled load components when raw_results is True."""
    if raw_results:
        for load_component in resolve_case.system.loads.values():
            scaled_load_results_folder = (
                resolve_case.dir_structure.output_resolve_temporal_settings_dir / "scaled load components"
            )
            scaled_load_results_folder.mkdir(parents=True, exist_ok=True)
            pd.DataFrame.from_dict(
                {
                    modeled_year: profile.data
                    for modeled_year, profile in load_component.scaled_profile_by_modeled_year.items()
                }
            ).round(3).to_csv(scaled_load_results_folder / f"{load_component.name}.csv", index=True)


@timer
def _export_model_results(resolve_case: ResolveCase, raw_results: bool = False):
    """Loops through ResolveModel components and saves to CSV."""

    # Get object type dictionary
    object_type_dict = get_object_type_dict(resolve_case)

    # Write out "raw" results
    for obj_type in object_type_dict.keys():
        if raw_results:
            components_to_print = list(
                resolve_case.model.component_objects(object_type_dict[obj_type]["object"], active=True)
            )
        else:
            # BAND-AID: Always report some "raw" results
            always_report = {
                "Variable": [
                    resolve_case.model.ELCC_MW,
                    resolve_case.model.Custom_Constraint_Slack_Up,
                    resolve_case.model.Custom_Constraint_Slack_Down,
                    resolve_case.model.Policy_Slack,
                    resolve_case.model.Resource_Potential_Slack,
                    resolve_case.model.SOC_Inter_Period,
                ],
                "Expression": [resolve_case.model.ELCC_Facet_Value],
                "Constraint": [
                    resolve_case.model.Custom_Constraint,
                    resolve_case.model.ELCC_Facet_Constraint_LHS,
                ],
                "Parameter": [],
                "Set": [],
            }
            components_to_print = always_report[obj_type]

        for obj in tqdm(
            components_to_print,
            desc=f"Printing {obj_type} results:".ljust(48),
            bar_format="{l_bar}{bar:30}{r_bar}{bar:-10b}",
        ):
            df = convert_pyomo_object_to_dataframe(obj)
            logger.debug(f"{obj}: {sys.getsizeof(obj)} bytes")

            if df is not None:
                # Write out df
                df.dropna(axis=0, how="all").round(3).sort_index().to_csv(
                    object_type_dict[obj_type]["output_dir"] / f"{obj.name}.csv", index=True
                )
                # For block-based components, save them in a subfolder of the block's name instead of by component type
                if "blocks" in obj.name:
                    block_name = re.search("(?<=\[)(.*?)(?=\])", obj.name).group(1)
                    (resolve_case.dir_structure.output_resolve_dir / "raw" / block_name).mkdir(
                        exist_ok=True, parents=True
                    )

                    component_name = obj.name.split(".")[-1]
                    df.dropna(axis=0, how="all").round(3).sort_index().to_csv(
                        resolve_case.dir_structure.output_resolve_dir / "raw" / block_name / f"{component_name}.csv",
                        index=True,
                    )

    logger.info("***Done outputting model results***")


def export_results(resolve_case: ResolveCase, raw_results: bool = False):
    _export_temporal_settings(dir_str=resolve_case.dir_structure)
    _export_model_results(resolve_case=resolve_case, raw_results=raw_results)
    _export_scaled_load_components(resolve_case=resolve_case, raw_results=raw_results)
