import contextlib
import importlib
import pathlib
import shutil
import sys
import traceback
from typing import Optional

import pandas as pd
import typer
from loguru import logger
from pyomo.common.tempfiles import TempfileManager

from new_modeling_toolkit import __version__
from new_modeling_toolkit.core import stream
from new_modeling_toolkit.core.utils.util import DirStructure
from new_modeling_toolkit.resolve.model_formulation import ResolveModel


def get_objective_function_value(instance, output_dir: pathlib.Path):
    """Save the objective function value.

    Args:
        instance (pyo.ConcreteModel): Filled abstract model instance to solve.
        scenario_results_directory ([type]): Scenario results directory to write to.
    """
    logger.info("Objective function value is: {:,.2f}".format(instance.Total_Cost()))
    with open(output_dir / "objective_function_value.txt", "w") as writer:
        writer.write(f"Objective function value is: {str(instance.Total_Cost())}")


def _run_case(
    dir_str: DirStructure,
    extras: Optional[str],
    solver_name: str,
    log_level: str,
    symbolic_solver_labels: bool,
):
    # Create ConcreteModel and link to system
    resolve_model = ResolveModel.from_case_dir(dir_structure=dir_str)

    # TODO (2022-02-22): This should be restricted to only "approved" extras
    if extras is not None and extras.strip():
        plugin_modules = importlib.import_module(f"new_modeling_toolkit.resolve.extras.{extras.strip()}")
        resolve_model = plugin_modules.main(resolve_model, dir_str)

    # Solve the model
    # Wrap `solve()` in this redirect so that it gets saved to logging file
    with contextlib.redirect_stdout(stream):
        resolve_model.solve(
            output_dir=dir_str.output_resolve_dir,
            solver_name=solver_name,
            keep_model_files=log_level == "DEBUG",
            symbolic_solver_labels=symbolic_solver_labels,
        )

    for policy in resolve_model.system.hourly_energy_policies.values():
        policy.check_constraint_violations(resolve_model)

    # Write results
    logger.info("Processing results...")
    resolve_model.export_results_summary(
        output_dir=dir_str.outputs_results_summary_dir, results_reporting=resolve_model.results_reporting_settings
    )
    if resolve_model.results_reporting_settings["report_raw"]:
        resolve_model.export_raw_results(dir_structure=dir_str)

    # Output objective function
    get_objective_function_value(resolve_model, dir_str.output_resolve_dir)

    # Save system and components to json files
    if resolve_model.save_system_to_json:
        resolve_model.system.custom_model_dump_json(
            dir_str.output_resolve_dir,
            exclude_from_all_components=set(),
        )

    return resolve_model


def main(
    resolve_settings_name: Optional[str] = typer.Argument(
        None,
        help="Name of a RESOLVE case (under ./data/settings/resolve). If `None`, will run all cases listed in ./data/settings/resolve/cases_to_run.csv",
    ),
    data_folder: str = typer.Option(
        "data", help="Name of data folder, which is assumed to be in the same folder as `new_modeling_toolkit` folder."
    ),
    solver_name: str = typer.Option(
        "appsi_highs",
        help="Name of the solver to use. See Pyomo documentation for solver names.",
    ),
    symbolic_solver_labels: bool = typer.Option(False, help="use symbolic solver labels"),
    log_json: bool = typer.Option(False, help="Serialize logging information as JSON"),
    log_level: str = typer.Option(
        "INFO",
        help="Any Python logging level: [DEBUG, INFO, WARNING, ERROR, CRITICAL]. "
        "Choosing DEBUG will also enable Pyomo `tee=True` and `symbolic_solver_labels` options.",
    ),
    extras: Optional[str] = typer.Option(
        None, help="Enables a RESOLVE 'extras' module, which contains project-specific add-on constraints."
    ),
    return_cases: bool = typer.Option(
        False, help="Whether or not to return a list of the completed cases when finished."
    ),
    raise_on_error: bool = typer.Option(
        True,
        help="Whether or not to raise an exception if one occurs during running of cases. Note that if you are running "
        "multiple cases, any cases subsequent to the raised exception will not run.",
    ),
) -> Optional[list[ResolveModel]]:
    logger.info(f"Resolve version: {__version__}")

    # Write input arguments to log
    logger.info(f"Logging input arguments...")
    logger.info(f"log_level = {log_level}")
    logger.info(f"solver_name = {solver_name}")
    logger.info(f"log_json = {log_json}")
    logger.info(f"symbolic_solver_labels = {symbolic_solver_labels}")

    # Create folder for the specific resolve run
    dir_str = DirStructure(data_folder=data_folder)
    if resolve_settings_name:
        cases_to_run = [resolve_settings_name]
    else:
        cases_to_run = pd.read_csv(dir_str.data_settings_dir / "resolve" / "cases_to_run.csv").iloc[:, 0].to_list()

    resolve_cases = []
    for resolve_settings_name in cases_to_run:
        logger.info(f"Loading Resolve case: {resolve_settings_name}")
        # Remove default loguru logger to stderr
        logger.remove()
        # Set stdout logging level
        logger.add(sys.__stdout__, level=log_level, serialize=log_json)

        # Make folders
        dir_str.make_resolve_dir(resolve_settings_name=resolve_settings_name)
        logger.add(dir_str.output_resolve_dir / "resolve.log", level=log_level)
        TempfileManager.tempdir = dir_str.output_resolve_dir

        if raise_on_error:
            resolve_model = _run_case(
                dir_str=dir_str,
                extras=extras,
                solver_name=solver_name,
                log_level=log_level,
                symbolic_solver_labels=symbolic_solver_labels,
            )
            if return_cases:
                resolve_cases.append(resolve_model)

        else:
            try:
                resolve_model = _run_case(
                    dir_str=dir_str,
                    extras=extras,
                    solver_name=solver_name,
                    log_level=log_level,
                    symbolic_solver_labels=symbolic_solver_labels,
                )

                if return_cases:
                    resolve_cases.append(resolve_model)

            except Exception as e:
                logger.error(f"Case {resolve_settings_name} failed. See error traceback below:")
                logger.error(traceback.format_exc())

        settings_passthrough_dir = dir_str.resolve_settings_dir / "passthrough"
        if not (settings_passthrough_dir).exists():
            settings_passthrough_dir.mkdir(exist_ok=True, parents=True)

        # case settings
        temporal_settings_from = dir_str.resolve_settings_dir / "temporal_settings" / "attributes.csv"
        if temporal_settings_from.exists():
            temporal_settings_to_dir = settings_passthrough_dir / "temporal_settings"
            temporal_settings_to_dir.mkdir(exist_ok=True, parents=True)
            temporal_settings_to = temporal_settings_to_dir / "attributes.csv"
            logger.debug(f"About to copy from {temporal_settings_from} to {temporal_settings_to}")
            shutil.copy2(temporal_settings_from, temporal_settings_to)
        else:
            logger.info(f"Can not copy {temporal_settings_from} to passthrough directory, as it doesn't exist.")

        # linkages (from system directory)
        linkages_from = dir_str.data_interim_dir / "systems" / resolve_model.system.name / "linkages.csv"
        if linkages_from.exists():
            linkages_to = settings_passthrough_dir / "linkages.csv"
            logger.debug(f"About to copy from {linkages_from} to {linkages_to}")
            shutil.copy2(linkages_from, linkages_to)
        else:
            logger.info(f"Can not copy {linkages_from} to passthrough directory, as it doesn't exist.")

        # scenarios.csv
        scenarios_from = dir_str.resolve_settings_dir / "scenarios.csv"
        if scenarios_from.exists():
            scenarios_to = settings_passthrough_dir / "scenarios.csv"
            logger.debug(f"About to copy from {scenarios_from} to {scenarios_to}")
            shutil.copy2(scenarios_from, scenarios_to)
        else:
            logger.info(f"Can not copy {scenarios_from} to passthrough directory, as it doesn't exist.")

        logger.debug(f"Passthrough dir for this run: {dir_str.output_resolve_dir / 'passthrough'}")
        shutil.copytree(
            settings_passthrough_dir,
            dir_str.output_resolve_dir / "passthrough",
            dirs_exist_ok=True,
        )

        # Copy the latest output to the 'latest' directory:
        if dir_str.latest_output_resolve_dir.exists():
            shutil.rmtree(dir_str.latest_output_resolve_dir, ignore_errors=True)
        shutil.copytree(dir_str.output_resolve_dir, dir_str.latest_output_resolve_dir)

        logger.info("Done.")

    return resolve_cases if return_cases else None


if __name__ == "__main__":
    from rich.traceback import install

    install()

    try:
        typer.run(main)
    except ImportError:
        main()
