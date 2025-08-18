import os
import pathlib
import shutil
import time

import pydantic
from loguru import logger


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


class DirStructure(pydantic.BaseModel):
    """Directory and file structure of the model."""

    code_dir: pathlib.Path = pathlib.Path(__file__).parent.parent.parent
    data_folder: str = "data"
    tool_name: str = "kit"
    start_dir: pathlib.Path | None = None
    proj_dir: pathlib.Path = None

    def __init__(self, **kwargs):
        """Initialize directory structure based on scenario name.
        Naming convention: directories have _dir as suffix, while files don't have this suffix.
        Args:
            common_dir (str): Path to the `common` directory where shared python codes are located
            tool_name (str): specific name of the model.
        """
        super().__init__(**kwargs)

        # Define paths to other directories
        # Project directory/ Root directory
        if self.start_dir is not None:
            self.proj_dir = self.start_dir
        else:
            self.proj_dir = self.code_dir.parent

        # testing code base location
        self.code_test_dir = self.proj_dir / "tests"

        # Data directories
        self.data_dir = self.proj_dir / self.data_folder
        self.data_raw_dir = self.data_dir / "raw"
        self.data_interim_dir = self.data_dir / "interim"
        self.data_settings_dir = self.data_dir / "settings"
        self.data_processed_dir = self.data_dir / "processed"

        # results directory
        self.results_dir = self.proj_dir / "reports"

        # make these directories if they do not already exist
        self.make_directories()

    class Config:
        extra = "allow"

        def __init__(self):
            super().__init__()

    def make_directories(self):
        for path in (vars(self) | self.__pydantic_extra__).values():
            if isinstance(path, pathlib.Path):
                path.mkdir(parents=True, exist_ok=True)

    def make_pathways_dir(self, case_name, log_level: str = "DEBUG"):
        timestamp = time.strftime("%Y-%m-%d-%H-%M-%S")
        self.pathways_dir = self.data_settings_dir / "pathways" / case_name
        self.pathways_case = self.results_dir / "pathways" / f"{case_name}" / f"{timestamp}"

        # add copy of inputs to output file
        shutil.copytree(self.pathways_dir, self.pathways_case)

        logger.add(self.pathways_case / "pathways.log", level=log_level)

        self.make_directories()

    def make_resolve_dir(self, resolve_settings_name: str, timestamp: str = None):
        # resolve temp file location for pyomo
        if timestamp is not None:
            # Check that the passed timestamp adheres to the desired format
            # Note: this will raise a ValueError if the timestamp cannot be converted to a time object using this format
            time.strptime(timestamp, "%Y-%m-%d-%H-%M-%S")
        else:
            timestamp = time.strftime("%Y-%m-%d-%H-%M-%S")
        # Override the timestamp with (cloud-kit) run ID if defined
        timestamp = os.environ.get("E3_KIT_RUN_ID", timestamp)

        # resolve settings file location
        self.resolve_settings_dir = self.data_settings_dir / "resolve" / resolve_settings_name
        self.resolve_settings_rep_periods_dir = self.resolve_settings_dir / "temporal_settings"

        # resolve output file location
        self.output_resolve_dir = self.results_dir / "resolve" / f"{resolve_settings_name}" / f"{timestamp}"
        self.latest_output_resolve_dir = self.results_dir / "resolve" / f"{resolve_settings_name}" / "latest"

        # Log files & LP files

        # Reporting outputs
        self.output_resolve_temporal_settings_dir = self.output_resolve_dir / "temporal_settings"
        self.outputs_results_summary_dir = self.output_resolve_dir / "summary"
        self.output_resolve_raw_results_dir = self.output_resolve_dir / "raw"
        # representative periods output location
        self.output_rep_periods_dir = self.data_processed_dir / "temporal" / resolve_settings_name

        # make these directories if they do not already exist
        self.make_directories()

    def make_reclaim_dir(self, reclaim_config_name):
        # reclaim config name
        timestamp = time.strftime("%Y-%m-%d-%H-%M-%S")
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
        # Get current time for naming results directory
        timestamp = time.strftime("%Y-%m-%d-%H-%M-%S")

        # Override the timestamp with (cloud-kit) run ID if defined
        timestamp = os.environ.get("E3_KIT_RUN_ID", timestamp)

        # Specify settings directory
        self.recap_settings_dir = self.data_settings_dir / "recap"
        self.analysis_dir = self.proj_dir / "analysis"
        # TODO: why do we need these? Maybe change once we get to results viewer updates
        self.analysis_input = self.analysis_dir / "Inputs Checker"
        self.analysis_output = self.analysis_dir / "Results Inspection"

        # [Optional] If case name specified, set up logging/results directory
        if case_name and not skip_creating_results_folder:
            # Specify day draw maps directory
            self.day_draw_dir = self.recap_settings_dir / case_name / "day_draw_map"
            self.day_draw_dir.mkdir(parents=True, exist_ok=True)

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
            data_folder=self.data_folder,
            tool_name=self.tool_name,
            **kwargs,
        )
        return DirStructure(**copy_kwargs)
