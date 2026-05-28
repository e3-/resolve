# -*- coding: utf-8 -*-
# ---
# jupyter:
#   jupytext:
#     custom_cell_magics: kql
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.15.1
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% [markdown]
# ## Resolve on `ethree.cloud`
#
# For more instruction, see: https://e3-encyclopedia.readthedocs-hosted.com/en/latest/cloud/resolve.html
#
# ![ethree-cloud-sequence.svg](ethree-cloud-sequence.svg)
# %%
import pathlib
from subprocess import run  # nosec

import joblib
import pandas as pd
import sys
import upath
import xlwings as xw
from tqdm import tqdm

try:
    from ipyfilechooser import FileChooser
except ModuleNotFoundError:
    print("Installing ipyfilechooser...")
    # %pip install ipyfilechooser -q

from ipywidgets import Checkbox, Dropdown, Layout

from kit.cli import Context
from kit.cli import get_run_number
from kit.cli import submit_workflow
from kit.resolve.results_viewers import summary_sheet_mapping
from kit.resolve.scenario_tool import export_scenario_tool_data

# %% [markdown]
# #### 1. Log into AWS & Argo

# %%
#fmt: off
if sys.platform=="win32":
    argo_check = !argo-workflows version
else:
    argo_check = !argo version
kubectl_check = !kubectl version
aws_check = !aws --version
#fmt: on

errs = ["not found", "not recognized"]

msgs = ["argo-workflows", "aws-cli", "kubectl"]
for i, check in enumerate([argo_check, aws_check, kubectl_check]):
    if any(err in "; ".join(check).lower() for err in errs):
        print(f"It seems like you do not have the {msgs[i]} CLI installed. Please see one-time setup instructions.")
    else:
        print(f"Seems like the {msgs[i]} CLI is installed correctly")

# %% [markdown]
# <div class="alert alert-block alert-warning">
#     ⚠️ <b> One-Time <code>ethree.cloud</code> Setup</b><br><br>
#     If you have not previously configured <code>aws-cli</code> and <code>kubectl</code> for this Resolve project, see <b><a href="https://e3-encyclopedia.readthedocs-hosted.com/en/latest/cloud/resolve.html">the one-time <code>ethree.cloud</code> setup instructions</a></b>.
# </div>

# %%
# !aws sso login

# %% [markdown]
# #### 2. Select & Open Scenario Tool

# %%
st = FileChooser(
    "..",
    title="<b>Select Scenario Tool to Use:</b>",
    layout=Layout(width="800px"),
    filter_pattern="[!~$]*.xls*",
)
st._show_dialog()
display(st)

# %%
wb = xw.Book(upath.UPath(st.selected))

# %% [markdown]
# #### 3. Get Run ID, Upload Data to S3 & Kick Off Run

# %%
# Pick where files are stored locally
fc = FileChooser(
    "..",
    title="<b>Select Folder to Save Local Data:</b>",
    layout=Layout(width="800px"),
    show_only_dirs=True,
)
fc._show_dialog()
display(fc)

# %%
# Get Run ID & upload data to S3
ctx = Context.load()
ctx.configure_run(get_run_number(ctx))
run_id = ctx.run

local_data_folder = pathlib.Path(fc.selected) / run_id

# Make `DATA_FOLDER_PATH` ST match what's in `.nmt.config.json`
data_folder = str(local_data_folder / ctx.data)
wb.sheets["Cover & Configuration"].range("DATA_FOLDER_PATH").value = data_folder
wb.app.calculate()

# Make `cases_to_save` match `cases_to_run` in ST
cases_to_run = (
    wb.sheets["RESOLVE Settings"]
    .range("cases_to_run")
    .options(pd.Series, header=True, index=0)
    .value.dropna()
    .unique()
    .tolist()
)
wb.sheets["RESOLVE Settings"].range("cases_to_save").value = None
wb.sheets["RESOLVE Settings"].range("cases_to_save").options(transpose=True).value = cases_to_run

print(f"Run ID: {run_id}")
print(f"Local data will be saved to: {local_data_folder / ctx.data}")

# %%
nmt_start_dir = upath.UPath(f"s3://e3x-cpuc-irp-data/runs/{run_id}/inputs/")
nmt_start_dir.mkdir(exist_ok=True, parents=True)

print(f"Saving input data locally for {run_id}")
export_scenario_tool_data(wb=wb, data_folder=ctx.data, start_dir=local_data_folder)
print(f"Pushing input data to S3 for {run_id}")
run(["aws", "s3", "sync", f"{local_data_folder}", f"{nmt_start_dir}"])
# export_scenario_tool_data(wb=wb, data_folder=ctx.data, start_dir=nmt_start_dir)

# %%
# Kick of cases in the cloud
submit_workflow(
    ctx=ctx,
    cases=cases_to_run,
    solver="gurobi",
    raw_results=True,
    extras="cpuc_irp",
)
print(f"See run logs on Datadog: https://app.datadoghq.com/logs?query=service%3Anmt%20e3x.run%3A{run_id}")

# %% [markdown]
# <div class="alert alert-block alert-info">
#     ℹ️ <b>You can also see workflow progress on Argo</b><br><br>
#     To see workflow progress on Argo, run the following command in a <b>separate</b> shell window (e.g., Command Prompt): <code>kubectl port-forward -n cpuc-irp svc/argo-workflows-server 2746</code><br>
#     Then, go to <b><a href="http://localhost:2746/">this link</a></b>.
# </div>

# %% [markdown]
# #### 4. Retrieve Results from Run

# %%
run_id_results_to_pull = Dropdown(
    options=[p.parts[-1] for p in upath.UPath("s3://e3x-cpuc-irp-data/runs/").iterdir()],
    value=run_id if "run_id" in globals() else None,
    description='Run ID (if different than currently active run ID above):',
    style= {'description_width': 'auto'},
    layout=Layout(width="auto"),
)
raw_results = Checkbox(
    value=False,
    description="Include Raw Results",
    indent=False,
    layout=Layout(width="auto"),
)
overwrite = Checkbox(
    value=False,
    description=f"Overwrite Local Files",
    indent=False,
    layout=Layout(width="auto"),
)

display(run_id_results_to_pull, raw_results, overwrite)

# %%
reports_dir = upath.UPath(f"s3://e3x-cpuc-irp-data/runs/{run_id_results_to_pull.value}/outputs/reports/resolve")
results_files = [f for f, _ in summary_sheet_mapping]

def get_results_files(
    *,
    local_dir: pathlib.Path = pathlib.Path(".."),
    case: str,
    raw_results: bool = False,
    overwrite: bool = False,
):
    for timestamp in case.iterdir():
        local_folder = local_dir / f"reports/resolve/{case.stem}/{timestamp.stem}"
        local_folder.mkdir(exist_ok=True, parents=True)

        if raw_results:
            run(["aws", "s3", "sync", f"{reports_dir}", f"{local_dir / 'reports/resolve'}"])

        for name in tqdm(results_files, desc=f"{case.parts[-5]}: {case.stem}".ljust(72)):
            filename = timestamp / name
            (local_folder / name).parent.mkdir(exist_ok=True, parents=True)

            copy_file = overwrite == True or (filename.exists() and not (local_folder / name).exists())
            if copy_file:
                df = pd.read_csv(filename)
                df.to_csv(local_folder / name, index=False)

_ = joblib.Parallel(n_jobs=8, prefer="processes")(
    joblib.delayed(get_results_files)(
        case=case,
        local_dir=upath.UPath(fc.selected) / f"{run_id_results_to_pull.value}",
        raw_results=raw_results.value,
        overwrite=overwrite.value,
    )
    for case in reports_dir.iterdir()
)

# %% [markdown]
# -----
#
# #### **`Optional`** Make a Local Copy of the Entire S3 Folder (Inputs, Profiles & Reports)
#
# This can help with easier `diff`-ing of input data for cross-run QA/QC.

# %%
run(["aws", "s3", "sync", f"{nmt_start_dir}", f"{local_data_folder}"])  # nosec

# %% [markdown]
# #### **`Optional`** Finding Data on AWS Console
#
# If you're unsure if your run inputs & reports are saved, go to the AWS console using the URL in the next cell.

# %%
uri = f"https://s3.console.aws.amazon.com/s3/buckets/e3x-cpuc-irp-data?region=us-west-2&prefix=runs/{run_id}/"
print(f"All run data can be found on the AWS console here: {uri}")

# %%
uri = f"https://s3.console.aws.amazon.com/s3/buckets/e3x-cpuc-irp-data?region=us-west-2&prefix=inputs/data/profiles/"
print(f"All profiles can be found on the AWS console here: {uri}")
