#!/usr/bin/env python
import csv
import json
import os
import pathlib
import shlex
import subprocess  # nosec
import sys
from datetime import datetime

import pandas as pd
import typer
import upath
from loguru import logger as log

from new_modeling_toolkit.resolve.run_opt import main as resolve

app = typer.Typer()
app.command(name="resolve", help="Run NMT:RESOLVE model (original)")(resolve)


DEFAULT_CONFIG_FILE = pathlib.Path(__file__).parents[2] / ".nmt.config.json"


class Context:
    DEFAULTS = {}

    def __init__(self, **kwargs):
        self.timestamp = datetime.utcnow()
        self.__config = dict(Context.DEFAULTS, **kwargs)
        if "extras" not in self.__config:
            self.__config["extras"] = None

        self.bucket = f"e3x-{self.project}-data"

        self.inputs_uri = f"s3://{self.bucket}/inputs"
        self.outputs_uri = f"s3://{self.bucket}/outputs"

        self.user = os.getlogin().lower()

        self.run_prefix = f"{self.user}-"
        self.runs_uri = f"s3://{self.bucket}/runs"

    def __getattr__(self, attr):
        try:
            return self.__config[attr]
        except KeyError:
            pass

        raise AttributeError(f"Context has no attribute '{attr}'")

    def __persistent_attr(self):
        return {k: v for k, v in self.__config.items() if Context.DEFAULTS.get(k) != v}

    @classmethod
    def load(cls, filename: os.PathLike[str] = DEFAULT_CONFIG_FILE):

        if pathlib.Path(filename).suffix in [".xlsm", ".xlsx", ".xlsb"]:
            import xlwings as xw

            with xw.App() as app:
                wb = xw.Book(upath.UPath(filename))
                return cls(
                    project=wb.sheets["RESOLVE Settings"].range("__PROJECTNAME__").value,
                    data=wb.sheets["RESOLVE Settings"].range("DATA_FOLDER_NAME").value,
                )
        else:
            with open(filename, "r") as cf:
                return cls(**json.load(cf))

    def save(self, filename: str = DEFAULT_CONFIG_FILE):
        with open(filename, "w") as cf:
            json.dump(self.__persistent_attr(), cf)

    def configure_run(self, number: str):
        self.run = f"{self.run_prefix}{number}"

    def load_cases(self):
        return list(
            pd.read_csv(upath.UPath(f"s3://{self.bucket}/inputs/{self.data}/settings/resolve/cases_to_run.csv"))
            .squeeze(axis=1)
            .values
        )


def get_run_number(ctx: Context):
    date = ctx.timestamp.strftime("%Y%m%d")
    proc = subprocess.run(
        [
            "aws",
            "s3",
            "ls",
            f"{ctx.runs_uri}/{ctx.run_prefix}{date}.",
        ],
        stdout=-1,
        stderr=2,
        text=True,
    )
    if proc.returncode == 0:
        entries = proc.stdout.strip().split("\n")
        numbers = list(map(lambda x: x.rsplit(".")[-1].strip("/"), entries))
        number = max(map(lambda x: int(x) if len(x) > 0 else 0, numbers)) + 1

        return f"{date}.{number}"
    return f"{date}.1"


def s3_sync(src: str, dst: str):
    subprocess.run(["aws", "s3", "sync", "--no-progress", src, dst], check=True)


def sync_inputs(ctx: Context):
    src = f"{ctx.data}/"
    dst = f"{ctx.inputs_uri}/{ctx.data}/"

    log.info("Syncing INPUTS: {0} -> {1}", src, dst)
    s3_sync(src, dst)


def sync_outputs(ctx: Context):
    src = f"{ctx.outputs_uri}/reports/"
    dst = "reports/"

    log.info("Syncing OUTPUTS: {0} -> {1}", src, dst)
    s3_sync(src, dst)


def submit_workflow(ctx: Context, solver: str, raw_results: bool, extras: bool, cases: list[str]):
    cases_param = shlex.quote(json.dumps(cases))
    args = [
        "argo",
        "submit",
        "--name",
        ctx.run.replace(".", "-"),
        "--from",
        f"workflowtemplate/resolve",
        "--namespace",
        f"{ctx.project}",
        "--parameter",
        f"owner={ctx.user}",
        "--parameter",
        f"run={ctx.run}",
        "--parameter",
        f"data={ctx.data}",
        "--parameter",
        f"solver={solver}",
        "--parameter",
        f"raw={'true' if (raw_results if raw_results is not None else ctx.raw_results) else 'false'}",
        "--parameter",
        f"cases={json.dumps(cases)}",
    ]

    extras = extras or ctx.extras
    if extras is not None:
        args.extend(["--parameter", f"extras={extras}"])

    env_with_argo = os.environ.copy()
    sep = ";" if sys.platform == "win32" else ":"
    env_with_argo["PATH"] = f"{pathlib.Path(__file__).absolute().parents[1] / 'bin'}{sep}{env_with_argo['PATH']}"

    log.info(
        "Submitting NMT RESOLVE run: {project}: {run}: {cases}", project=ctx.project, run=ctx.run, cases=cases_param
    )
    if sys.platform == "win32":
        subprocess.run(args, shell=True, env=env_with_argo)
    else:
        subprocess.run(args, check=True, env=env_with_argo)


@app.command(help="Initialize NMT project")
def init(
    project: str = typer.Argument(..., help="Project name"),
    scenario_tool: str = typer.Option(None, "--scenario-tool", "-st", help="File path to project Scenario Tool"),
    data: str = typer.Option("data", help="Path to project data folder."),
    solver: str = typer.Option("gurobi", help="Solver to use (appsi_highs, gurobi)"),
    raw_results: bool = typer.Option(True, help="Report all Pyomo model components directly"),
    extras: str = typer.Option("cpuc_irp", help="Enables a 'extras' module (RESOLVE)"),
):
    if scenario_tool is not None:
        # Configure Scenario Tool
        import xlwings as xw

        with xw.App() as app:
            wb = xw.Book(upath.UPath(scenario_tool))
            wb.sheets["RESOLVE Settings"].range("__PROJECTNAME__").value = project
            wb.sheets["xlwings.conf"].range("__INTERPRETERPATH__").value = sys.executable
    else:
        Context(project=project, data=data, solver=solver, raw_results=raw_results, extras=extras).save()


@app.command(help="Submit NMT:RESOLVE model run")
def submit(
    cases: list[str] = typer.Argument(None, help="List of CASEs to run"),
    scenario_tool: str = typer.Option(None, "--scenario-tool", "-st", help="File path to project Scenario Tool"),
    solver: str = typer.Option("gurobi", help="Solver to use (cbc, gurobi)"),
    raw_results: bool = typer.Option(True, help="Report all Pyomo model components directly"),
    extras: str = typer.Option(None, help="Enables a 'extras' module (RESOLVE)"),
    upload_inputs: bool = typer.Option(False, help="Upload inputs before submitting model run"),
):
    if scenario_tool is not None:
        ctx = Context.load(filename=scenario_tool)
    else:
        ctx = Context.load()
    if cases is None or len(cases) == 0:
        cases = ctx.load_cases()
    if solver is None:
        solver = ctx.solver
    ctx.configure_run(get_run_number(ctx))

    log.info("Preparing NMT:RESOLVE run: {project}: {run}", project=ctx.project, run=ctx.run)

    if upload_inputs:
        sync_inputs(ctx)
    submit_workflow(ctx, solver, raw_results, extras, cases)

    return ctx.run


@app.command(help="Run NMT:RESOLVE model locally")
def run(
    cases: list[str] = typer.Argument(None, help="List of CASEs to run"),
    solver: str = typer.Option("gurobi", help="Solver to use (cbc, gurobi)"),
    raw_results: bool = typer.Option(True, help="Report all Pyomo model components directly"),
    extras: str = typer.Option(None, help="Enables a 'extras' module (RESOLVE)"),
):
    ctx = Context.load()
    if cases is None or len(cases) == 0:
        cases = ctx.load_cases()
    if solver is None:
        solver = ctx.solver

    for case in cases:
        resolve(
            resolve_settings_name=case,
            data_folder=ctx.data,
            solver_name=solver,
            log_json=False,
            log_level="INFO",
            raw_results=raw_results or ctx.raw_results or False,
            extras=extras or ctx.extras,
            return_cases=False,
        )


@app.command(help="Upload INPUTS of the model run")
def upload_inputs():
    sync_inputs(Context.load())


def main():
    app()


if __name__ == "__main__":
    main()
