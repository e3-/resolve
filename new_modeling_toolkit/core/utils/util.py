import pathlib
import shutil
import time

import pandas as pd
from loguru import logger

from new_modeling_toolkit.core.utils.core_utils import timer


class StreamToLogger:
    """Class to help loguru capture all print() from stdout.

    The use-case for this in Pyomo is the `tee=True` feed from the solver.
    Because of this, the logging level is assumed to be DEBUG.
    """

    def __init__(self, level="DEBUG"):
        self._level = level

    def write(self, buffer):
        for line in buffer.rstrip().splitlines():
            logger.opt(depth=1).log(self._level, line.rstrip())

    def flush(self):
        pass


class DirStructure:
    """Directory and file structure of the model."""

    def __init__(
        self,
        code_dir=pathlib.Path(__file__).parent.parent.parent,
        data_folder="data",
        model_name="kit",
        start_dir=None,
    ):
        """Initialize directory structure based on scenario name.
        Naming convention: directories have _dir as suffix, while files don't have this suffix.
        Args:
            common_dir (str): Path to the `common` directory where shared python codes are located
            model_name (str): specific name of the model.
        """
        self._data_folder = data_folder

        self.model_name = model_name
        self.code_dir = code_dir

        # Define paths to various code directories        # resolve code base location
        self.code_resolve_dir = self.code_dir / "resolve"
        # recap code base location
        self.code_recap_dir = self.code_dir / "recap"
        # reclaim code base location
        self.code_reclaim_dir = self.code_dir / "reclaim"
        # visualization code base location
        self.code_visualization_dir = self.code_dir / "visualization"
        # testing code base location
        # TODO: Determine if test directory should be a level up
        self.code_test_dir = self.code_dir / "tests"

        # Define paths to other directories
        # Project directory/ Root directory
        if start_dir is not None:
            self.proj_dir = start_dir
        else:
            self.proj_dir = self.code_dir.parent

        # Data directories
        self.data_dir = self.proj_dir / data_folder
        self.data_raw_dir = self.data_dir / "raw"
        self.data_interim_dir = self.data_dir / "interim"
        self.data_settings_dir = self.data_dir / "settings"
        self.data_processed_dir = self.data_dir / "processed"

        # log directory
        self.logs_dir = self.proj_dir / "logs"

        # results directory
        self.results_dir = self.proj_dir / "reports"

        # make these directories if they do not already exist
        self.make_directories()

    def make_directories(self):
        for path in vars(self).values():
            if isinstance(path, pathlib.Path):
                path.mkdir(parents=True, exist_ok=True)

    def make_simplified_emissions_module_dir(self, simplified_emissions_module_settings_name):
        timestamp = time.strftime("%Y-%m-%d %H-%M-%S")
        self.simplified_emissions_module_settings_dir = (
            self.data_settings_dir / "simplified_emissions_module" / simplified_emissions_module_settings_name
        )
        self.output_simplified_emissions_module_dir = (
            self.results_dir
            / "simplified_emissions_module"
            / f"{simplified_emissions_module_settings_name}"
            / f"{timestamp}"
        )
        self.make_directories()

    def make_resolve_dir(self, resolve_settings_name: str, timestamp: str = None, log_level: str = "INFO"):
        # resolve temp file location for pyomo
        if timestamp is not None:
            # Check that the passed timestamp adheres to the desired format
            # Note: this will raise a ValueError if the timestamp cannot be converted to a time object using this format
            time.strptime(timestamp, "%Y-%m-%d %H-%M-%S")
        else:
            timestamp = time.strftime("%Y-%m-%d %H-%M-%S")

        # resolve settings file location
        self.resolve_settings_dir = self.data_settings_dir / "resolve" / resolve_settings_name
        self.resolve_settings_rep_periods_dir = self.resolve_settings_dir / "temporal_settings"
        self.resolve_settings_custom_constraints_dir = self.resolve_settings_dir / "custom_constraints"
        self.resolve_passthrough_inputs = self.resolve_settings_dir / "passthrough"

        # resolve output file location
        self.output_resolve_dir = self.results_dir / "resolve" / f"{resolve_settings_name}" / f"{timestamp}"

        # Log files & LP files
        logger.add(self.output_resolve_dir / "resolve.log", level=log_level)

        # Reporting outputs
        self.outputs_resolve_var_dir = self.output_resolve_dir / "variables"
        self.outputs_resolve_exp_dir = self.output_resolve_dir / "expressions"
        self.outputs_resolve_constraint_dir = self.output_resolve_dir / "constraints"
        self.outputs_resolve_param_dir = self.output_resolve_dir / "parameters"
        self.outputs_resolve_set_dir = self.output_resolve_dir / "sets"
        self.output_resolve_temporal_settings_dir = self.output_resolve_dir / "temporal_settings"
        self.outputs_results_summary_dir = self.output_resolve_dir / "results_summary"

        # representative periods output location
        self.output_rep_periods_dir = self.data_processed_dir / "temporal" / resolve_settings_name

        # make these directories if they do not already exist
        self.make_directories()

    def make_reclaim_dir(self, reclaim_config_name):
        # reclaim config name
        timestamp = time.strftime("%Y-%m-%d %H-%M-%S")
        self.reclaim_config_name = reclaim_config_name
        self.reclaim_config_dir = self.data_settings_dir / "reclaim" / self.reclaim_config_name

        # Define paths to directories
        self.reclaim_data_dir = self.data_interim_dir / "reclaim" / self.reclaim_config_name  # data/input
        self.reclaim_output_dir = self.data_processed_dir / "reclaim" / self.reclaim_config_name  # nference results
        self.reclaim_logs_dir = (
            self.logs_dir / "reclaim_logs" / self.reclaim_config_name
        )  # training log for tensorboard
        self.reclaim_ckpts_dir = (
            self.logs_dir / "reclaim_ckpts" / self.reclaim_config_name
        )  # checkpoints for accidental pauses
        self.reclaim_models_dir = self.results_dir / "reclaim_models" / self.reclaim_config_name  # trained models
        self.reclaim_diag_dir = self.results_dir / "reclaim_diag" / self.reclaim_config_name  # diagnostics
        self.reclaim_plots_dir = self.reclaim_diag_dir / "plots"  # diagnostic plots

        # Define paths to files
        self.shuffled_indices_path = str(
            self.reclaim_data_dir / "shuffled_indices_{}.npy".format(self.reclaim_config_name)
        )  # Shuffled indices for cross-validation

        # clear all contents in the log directory
        if self.reclaim_logs_dir.exists():
            shutil.rmtree(self.reclaim_logs_dir)

        # make these directories if they do not already exist
        self.make_directories()

    def make_recap_dir(self, case_name=None, log_level="DEBUG", skip_creating_results_folder=False):
        timestamp = time.strftime("%Y-%m-%d %H-%M-%S")

        # Specify settings directory
        self.recap_settings_dir = self.data_settings_dir / "recap"
        self.analysis_dir = self.proj_dir / "analysis"
        self.analysis_input = self.analysis_dir / "Inputs checker"
        self.analysis_output = self.analysis_dir / "Result Inspection"

        # [Optional] If case name specified, set up logging/results directory
        if case_name and not skip_creating_results_folder:
            # Specify results directory
            self.recap_output_dir = self.results_dir / "recap" / case_name / timestamp
            self.recap_output_dir.mkdir(parents=True, exist_ok=True)

            # Log files & LP files
            logger.add(self.recap_output_dir / "recap.log", level=log_level)

        # Make these directories
        if not skip_creating_results_folder:
            self.make_directories()

    def get_valid_results_dirs(self, model: str):
        """Creates a list of all non-empty results folders for the specified model

        Args:
            model: name of the model whose outputs to filter. Should be one of: ["resolve", "reclaim", "recap"]

        Returns:

        """
        results_path = self.results_dir / model

        # Get all RESOLVE results folder names (nested list to make it "tall" instead of "wide"
        paths = ["/".join(p.parts[-3:-1]) for p in results_path.glob("**/results_summary") if any(p.iterdir())]

        return paths

    def make_recap2_dir(self, case_name):
        # Set up RECAP 2.0 directory structure
        self.recap2_dir = self.data_dir.parent / "RECAP-2.0"
        self.recap2_code_dir = self.recap2_dir / "code"
        self.recap2_common_inputs_dir = self.recap2_dir / "common_inputs"
        self.recap2_input_dir = self.recap2_dir / "inputs" / case_name
        self.recap2_results_dir = self.recap2_dir / "results" / case_name

        self.make_directories()

    def copy(self, **kwargs) -> "DirStructure":
        copy_kwargs = dict(
            code_dir=self.code_dir,
            data_folder=self._data_folder,
            model_name=self.model_name,
            **kwargs,
        )
        return DirStructure(**copy_kwargs)


def validate_sales_shares(system_instance):
    # TODO (2022-09-27): Move to Pathways module
    logger.info("Validating sales shares")
    for stock_rollover_subsector in system_instance.stock_rollover_subsectors.keys():
        for sales_share_type in [
            # "sales_share_early_retirement",
            "sales_share_natural_replacements",
            # "sales_share_new_stock_additions",
        ]:
            sales_shares_by_device = pd.DataFrame()
            for device in system_instance.stock_rollover_subsectors[stock_rollover_subsector].devices.keys():
                if getattr(system_instance.devices[device], sales_share_type) is None:
                    continue
                sales_shares_by_device[device] = getattr(system_instance.devices[device], sales_share_type).data

            # if the current sales share type is not specified (for example the new stock additions, which are optional)
            if sales_shares_by_device.empty:
                continue

            sales_shares_summed = sales_shares_by_device.sum(axis=1)
            # check if sum of sales shares is more than 1% different from 100% in any year
            if (((sales_shares_summed - 1).abs() > 0.01) * 1).sum() > 0:
                raise ValueError(
                    "Sales shares for {} do not add up to 100% with tolerance of 1%".format(stock_rollover_subsector)
                )


# def validate_prescribed_fuel_blends(system_instance):
#     print("validating prescribed fuel blends")
#     for sector in system_instance.sectors.keys():
#         tmp = 1
#         system_instance.sectors[sector].sector_candidate_fuel_blending[("Renewable Diesel", "Distillate")]


@timer
def run_non_component_validations(system_instance):
    """
    Run validations on system instance that need to look at the entire instance and not just one component at a time.
    """
    # validate_sales_shares(system_instance)
    # validate_prescribed_fuel_blends(system_instance)
