import os
import shutil
import sys
from typing import Optional

import pandas as pd
import upath
from loguru import logger

import new_modeling_toolkit.ui
import xlwings as xw
from new_modeling_toolkit.core.utils.util import DirStructure

# Set traceback limit to 0 so that error message is more readable in Excel popup window
sys.tracebacklimit = 0

"""
Save model-specific case settings for RESOLVE.
"""

settings_files_dict = {
    "attributes.csv": {
        "static": [
            {"range": "settings_system", "attributes": ["system"]},
            {"range": "settings_solver_attributes", "attributes": ["solver\..*"]},
        ],
        "timeseries": [],
        "flat": [],
    },
    "scenarios.csv": {"static": [], "timeseries": [], "flat": ["settings_scenarios"]},
    "temporal_settings/attributes.csv": {
        "static": [
            {
                "range": "settings_rep_period_attributes",
                "attributes": [
                    "representative_periods_method",
                    "representative_periods_amount",
                    "representative_periods_duration",
                    "allow_inter_period_dynamics",
                ],
            },
            {
                "range": "settings_financial_attributes",
                "attributes": ["cost_dollar_year", "end_effect_years"],
            },
        ],
        "timeseries": [
            {
                "range": "settings_modeled_year_attributes",
                "attributes": ["modeled_years", "annual_discount_rate", "allow_inter_period_dynamics"],
            },
            # {
            #     "range": "settings_weather_years_to_use",
            #     "attributes": ["weather_years_to_use"],
            # },
        ],
        "flat": [],
    },
    "custom_constraints/constraints_to_load.csv": {
        "static": [],
        "timeseries": [],
        "flat": ["constraints_to_load"],
    },
}


def save_multiple_cases(
    sheet_name: str, wb: Optional[xw.Book] = None, model: str = "resolve", data_folder: Optional[os.PathLike] = None
):
    if wb is None:
        wb = xw.Book.caller()
    sheet = wb.sheets[sheet_name]

    for case in sheet.range("cases_to_save").value:
        if case is not None:
            wb.sheets["RESOLVE Settings"].range("settings_name").value = case
            wb.app.calculate()
            save_RESOLVE_case_settings(sheet_name=sheet_name, wb=wb, data_folder=data_folder)


def save_RESOLVE_case_settings(
    sheet_name: str, wb: Optional[xw.Book] = None, model: str = "resolve", data_folder: Optional[os.PathLike] = None
):
    """Save RESOLVE case settings from Scenario Tool named ranges."""
    # Open workbook and define system worksheet
    if wb is None:
        wb = xw.Book.caller()
    sheet = wb.sheets[sheet_name]

    # Define current working directory and path to settings directory
    if data_folder is None:
        data_folder = upath.UPath(wb.fullname).parent / "data"
    data_folder = upath.UPath(data_folder)

    settings_name = sheet.range("settings_name").value

    settings_dir = data_folder / "settings" / model / settings_name
    settings_dir.mkdir(parents=True, exist_ok=True)

    # Save passthrough files
    passthrough_dir = data_folder / "settings" / "resolve" / settings_name / "passthrough"
    passthrough_dir.mkdir(parents=True, exist_ok=True)

    passthrough_files = wb.sheets["Lists"].range("passthrough_ranges").options(pd.DataFrame, index=False).value
    for _, (named_range, sheet_name) in passthrough_files.iterrows():
        df = wb.sheets[sheet_name].range(named_range).options(pd.DataFrame, index=False).value
        df = df.dropna(axis=1,how='all')
        df.to_csv(passthrough_dir / f"{named_range}.csv", index=False)

    # Save case settings
    for filename, settings in settings_files_dict.items():
        # Create new settings directory if necessary
        (settings_dir / filename).parent.mkdir(parents=True, exist_ok=True)

        wb.app.status_bar = f"{settings_name}: {filename}"

        dfs = []
        for setting in settings["static"]:
            df = sheet.range(setting["range"]).options(pd.DataFrame, chunksize=1_000).value
            df = df.loc[df.index.dropna()].reset_index()
            df["timestamp"] = "None"
            df = df.set_index(["timestamp", "attribute"])
            # Append new dataframe to list
            dfs += [df]

        for setting in settings["timeseries"]:
            df = (
                sheet.range(setting["range"])
                .options(pd.DataFrame, chunksize=1_000)
                .value.melt(ignore_index=False)
                .dropna(subset="value")
                .reset_index()
            )
            df = df.rename(columns={"variable": "attribute"}).set_index(["timestamp", "attribute"])
            # Append new dataframe to list
            dfs += [df]

        for setting in settings["flat"]:
            # TODO: Understand why does this not work for the components_to_consider.csv
            df = sheet.range(setting).options(pd.DataFrame, chunksize=1_000).value
            df = df.loc[df.index.dropna()]
            dfs += [df]

        if dfs:
            attributes = pd.concat(dfs, axis=0)
            attributes.to_csv(settings_dir / filename)

    # Save manual temporal settings
    wb.app.status_bar = f"{settings_name}: manual rep periods"
    if sheet.range("settings_rep_period_method").value == "manual":
        save_manual_temporal_settings(wb=wb, settings_name=settings_name, data_folder=data_folder)

    # Save extras (hydro params and simultaneous flow limits)
    wb.app.status_bar = f"{settings_name}: extras"
    save_extras(wb=wb, settings_name=settings_name, data_folder=data_folder)

    # Save custom constraints
    wb.app.status_bar = f"{settings_name}: custom constraints"
    save_custom_constraints(wb=wb, settings_name=settings_name, data_folder=data_folder)

    wb.app.status_bar = None


def save_extras(settings_name: str, wb: Optional[xw.Book] = None, data_folder: Optional[os.PathLike] = None):
    """Save "extras" data for hydro and simultaneous flow constraints."""
    if wb is None:
        wb = xw.Book.caller()

    # Define current working directory and path to settings directory
    if data_folder is None:
        data_folder = upath.UPath(wb.fullname).parent / "data"
    data_folder = upath.UPath(data_folder)

    extras_dir = data_folder / "settings" / "resolve" / settings_name / "extras"
    extras_dir.mkdir(parents=True, exist_ok=True)

    # Simultaneous flow
    tx_sheets = ["Transmission Paths", "Zones and Transmission"]
    for sheet_name in [sheet.name for sheet in wb.sheets if sheet.name in tx_sheets]:  # nosec
        sheet = wb.sheets[sheet_name]
        df = sheet.range("simultaneous_flow_groups").options(pd.DataFrame, chunksize=1_000).value
        if not df.isnull().values.all():
            df = df.dropna(how="all")
            df.to_csv(extras_dir / "simultaneous_flow_groups.csv")

        df = sheet.range("simultaneous_flow_limits").options(pd.DataFrame, chunksize=1_000).value
        if not df.isnull().values.all():
            df = df.dropna(how="all")
            df.columns = df.columns.astype(int)
            df.to_csv(extras_dir / "simultaneous_flow_limits.csv")

    # HECO
    if "Extras - HECO" in [sheet.name for sheet in wb.sheets]:
        sheet = wb.sheets["Extras - HECO"]
        df = sheet.range("erm_group").options(pd.DataFrame, chunksize=1_000).value
        if not df.isnull().values.any():
            df.to_csv(extras_dir / "erm_group.csv")

        df = sheet.range("erm_params").options(pd.DataFrame, chunksize=1_000).value
        if not df.isnull().values.any():
            df.to_csv(extras_dir / "erm_params.csv")

        df = sheet.range("erm_resource_group_map").options(pd.DataFrame, chunksize=1_000).value
        if not df.isnull().values.any():
            df.to_csv(extras_dir / "erm_resource_group_map.csv")

        df = sheet.range("erm_shapes").options(pd.DataFrame, chunksize=1_000).value
        if not df.isnull().values.any():
            df.to_csv(extras_dir / "erm_shapes.csv")

        df = sheet.range("erm_timepoint_params").options(pd.DataFrame, chunksize=1_000).value
        if not df.isnull().values.any():
            df.to_csv(extras_dir / "erm_timepoint_params.csv")

        df = sheet.range("flexible_params").options(pd.DataFrame, chunksize=1_000).value
        if not df.isnull().values.any():
            df.to_csv(extras_dir / "flexible_params.csv")

        df = sheet.range("freq_resp_adjust_resources").options(pd.DataFrame, chunksize=1_000).value
        if not df.isnull().values.any():
            df.to_csv(extras_dir / "freq_resp_adjust_resources.csv")

        df = sheet.range("freq_resp_contingency_resources").options(pd.DataFrame, chunksize=1_000).value
        if not df.isnull().values.any():
            df.to_csv(extras_dir / "freq_resp_contingency_resources.csv")

        df = sheet.range("resource_storage_paired").options(pd.DataFrame, chunksize=1_000).value
        if not df.isnull().values.any():
            df.to_csv(extras_dir / "resource_storage_paired.csv")

        df = sheet.range("synchronous_condenser_resources").options(pd.DataFrame, chunksize=1_000).value
        if not df.isnull().values.any():
            df.to_csv(extras_dir / "synchronous_condenser_resources.csv")


def save_manual_temporal_settings(
    settings_name: str, wb: Optional[xw.Book] = None, data_folder: Optional[os.PathLike] = None
):
    """Save the four temporal settings files to configure rep periods manually."""
    # Open workbook and define system worksheet
    if wb is None:
        wb = xw.Book.caller()
    sheet = wb.sheets["Temporal Settings"]

    # Define current working directory and path to settings directory
    if data_folder is None:
        data_folder = upath.UPath(wb.fullname).parent / "data"
    data_folder = upath.UPath(data_folder)
    settings_dir = data_folder / "settings" / "resolve" / settings_name

    files = [
        "chrono_periods",
        "map_to_rep_periods",
        "rep_periods",
        "rep_period_weights",
    ]
    for f in files:
        df = sheet.range(f).options(pd.DataFrame, chunksize=1_000).value
        df = df.dropna()
        df.index = df.index.astype(int)
        if f in ["chrono_periods", "rep_periods"]:
            df.columns = df.columns.astype(int)
        df.to_csv(settings_dir / "temporal_settings" / f"{f}.csv")


def save_custom_constraints(
    settings_name: str, wb: Optional[xw.Book] = None, data_folder: Optional[os.PathLike] = None
):
    """Save custom constraint groups"""
    # Open workbook sheet
    if wb is None:
        wb = xw.Book.caller()
    sheet = wb.sheets["Custom Constraints"]

    lhs = sheet.range("custom_constraints_lhs").options(pd.DataFrame, chunksize=1_000).value
    # TODO 2024-09-15: All range conversions should use a chunk size to avoid timeout
    operator_and_rhs = sheet.range("custom_constraints_operator_and_rhs").options(pd.DataFrame, chunksize=1_000).value

    # Define current working directory and path to settings directory
    if data_folder is None:
        data_folder = upath.UPath(wb.fullname).parent / "data"
    data_folder = upath.UPath(data_folder)

    custom_constraints_dir = data_folder / "settings" / "resolve" / settings_name / "custom_constraints"

    if custom_constraints_dir.exists():
        for dir in custom_constraints_dir.iterdir():
            if dir.is_dir():
                try:
                    # `recursive` seems not to work on local paths (but does work for example on S3Paths)
                    dir.rmdir(recursive=True)
                except TypeError:
                    shutil.rmtree(dir.absolute())

    # Save each Custom Constraint Group LHS
    lhs = lhs.groupby(["Custom Constraint Group", "Model Formulation Variable"])
    for cc_group, group in lhs:
        # Unpack tuple name of group
        cc_group, var = cc_group
        wb.app.status_bar = f"{settings_name}: custom constraints: {cc_group}"

        cc_group_dir = custom_constraints_dir / cc_group
        cc_group_dir.mkdir(parents=True, exist_ok=True)

        # Save variable multiplier CSVs
        df = (
            group.drop(["Model Formulation Variable"], axis=1)
            .set_index(["Custom Constraint", "Index 1", "Index 2"])
            .melt(ignore_index=False)
        )
        df.index.names = ["Sum Range ID", "Index 1", "Index 2"]
        df.columns = ["MODEL_YEARS", "Multiplier"]
        df["MODEL_YEARS"] = df["MODEL_YEARS"].astype(int)
        df = df.reset_index()
        df["Sum Range ID"] = df["Sum Range ID"].astype(str) + "." + df["MODEL_YEARS"].astype(str)
        if df["Index 2"].isnull().all():
            df = df.drop(["Index 2"], axis=1)

        df.to_csv(cc_group_dir / f"{var}.csv", index=False)

    # Save operator and targets
    operator_and_rhs = operator_and_rhs.groupby("Custom Constraint Group")
    for cc_group, group in operator_and_rhs:
        df = group.set_index(["Custom Constraint"])

        # Save target
        target = df.drop(["Constraint Operator"], axis=1).melt(ignore_index=False)
        target.index.names = ["Sum Range ID"]
        target.columns = ["MODEL_YEARS", "Target"]
        target["Target"] = target["Target"].replace("", None)
        target = target.dropna(subset=["Target"])
        target["MODEL_YEARS"] = target["MODEL_YEARS"].astype(int)
        target = target.reset_index()
        target["Sum Range ID"] = target["Sum Range ID"].astype(str) + "." + target["MODEL_YEARS"].astype(str)
        target = target.drop(["MODEL_YEARS"], axis=1)

        cc_group_dir = custom_constraints_dir / cc_group
        target.to_csv(cc_group_dir / "target.csv", index=False)

        # Save operator
        operator = pd.DataFrame(
            {col: df["Constraint Operator"].values for col in df.columns[1:]}, index=df.index, columns=df.columns[1:]
        ).melt(ignore_index=False)
        operator.index.names = ["Sum Range ID"]
        operator.columns = ["MODEL_YEARS", "Operator"]
        operator["MODEL_YEARS"] = operator["MODEL_YEARS"].astype(int)
        operator = operator.reset_index()
        operator["Sum Range ID"] = operator["Sum Range ID"].astype(str) + "." + operator["MODEL_YEARS"].astype(str)
        operator = operator.drop(["MODEL_YEARS"], axis=1)

        operator.to_csv(cc_group_dir / "operator.csv", index=False)


def save_custom_timepoint_constraints(
    settings_name: str, wb: Optional[xw.Book] = None, data_folder: Optional[os.PathLike] = None
):
    """Quick-and-dirty copy of ``save_custom_constraints``, essentially removing the ``melt`` step."""
    # Open workbook sheet
    if wb is None:
        wb = xw.Book.caller()
    sheet = wb.sheets["Custom Constraints"]

    lhs = sheet.range("custom_constraints_timepoint_lhs").options(pd.DataFrame, chunksize=1_000).value
    operator_and_rhs = (
        sheet.range("custom_constraints_timepoint_operator_and_rhs").options(pd.DataFrame, chunksize=1_000).value
    )

    # Define current working directory and path to settings directory
    if data_folder is None:
        data_folder = upath.UPath(wb.fullname).parent / "data"
    data_folder = upath.UPath(data_folder)

    custom_constraints_dir = data_folder / "settings" / "resolve" / settings_name / "custom_constraints"

    # Save each Custom Constraint Group LHS
    lhs = lhs.groupby(["Custom Constraint Group", "Model Formulation Variable"])
    for name, group in lhs:
        # Unpack tuple name of group
        cc_group, var = name

        (custom_constraints_dir / cc_group).mkdir(parents=True, exist_ok=True)

        # Save variable multiplier CSVs
        df = group.drop(["Model Formulation Variable"], axis=1).set_index(["Custom Constraint", "Index 1", "Index 2"])
        df.index.names = ["Sum Range ID", "Index 1", "Index 2"]
        df = df.reset_index()
        df[["MODEL_YEARS", "REP_PERIODS", "HOURS"]] = df[["MODEL_YEARS", "REP_PERIODS", "HOURS"]].astype(
            int, errors="ignore"
        )
        if df["Index 2"].isnull().all():
            df = df.drop(["Index 2"], axis=1)

        df.to_csv(custom_constraints_dir / cc_group / f"{var}.csv", index=False)

    # Save operator and targets
    operator_and_rhs = operator_and_rhs.groupby("Custom Constraint Group")
    for name, group in operator_and_rhs:
        df = group.set_index(["Custom Constraint"])

        # Save target
        target = df.iloc[:, -1].to_frame()
        target.index.names = ["Sum Range ID"]
        target.columns = ["Target"]
        target["Target"] = target["Target"].replace("", None)
        target = target.dropna(subset=["Target"])
        target = target.reset_index()

        target.to_csv(custom_constraints_dir / name / "target.csv", index=False)

        # Save operator
        operator = df.iloc[:, -2].to_frame()
        operator.index.names = ["Sum Range ID"]
        operator.columns = ["Operator"]
        operator = operator.reset_index()

        operator.to_csv(custom_constraints_dir / name / "operator.csv", index=False)


def load_RESOLVE_case_settings(
    sheet_name: str, model: str = "resolve", wb: Optional[xw.Book] = None, data_folder: Optional[os.PathLike] = None
):
    """Load RESOLVE case settings and populate Scenario Tool named ranges."""
    # Open workbook and define system worksheet
    if wb is None:
        wb = xw.Book.caller()
    sheet = wb.sheets[sheet_name]

    # Define current working directory and path to settings directory
    if data_folder is None:
        data_folder = upath.UPath(wb.fullname).parent / "data"
    data_folder = upath.UPath(data_folder)

    settings_dir = data_folder / "settings" / model / sheet.range("resolve_case_to_load").value

    # load case settings
    for filename, settings in settings_files_dict.items():
        dfs = pd.read_csv(settings_dir / filename)
        for setting in settings["static"]:
            df = dfs.loc[dfs["attribute"].isin(setting["attributes"])]
            sheet.range(setting["range"]).value = [["attribute", "value"]] + df.iloc[:, 1:].values.tolist()

        for setting in settings["timeseries"]:
            df = (
                dfs.loc[dfs["attribute"].isin(setting["attributes"])]
                .pivot(index="timestamp", columns="attribute", values="value")
                .reset_index()
            )
            df = df[["timestamp", "modeled_years", "annual_discount_rate"]]
            df.insert(1, "", pd.DataFrame([""] * len(df)))
            sheet.range(setting["range"]).value = [df.columns.tolist()] + df.values.tolist()

        for setting in settings["flat"]:
            sheet.range(setting).value = [dfs.columns.tolist()] + dfs.values.tolist()

    # # Load manual temporal settings
    # if sheet.range("settings_rep_period_method").value == "manual":
    #     save_manual_temporal_settings(settings_name=sheet.range("settings_name").value)
    #
    # # load extras (simultaneous flow limits)
    # extras_dir = data_folder / "settings" / "resolve" / sheet.range("resolve_case_to_load").value / "extras"

    # # load custom constraints
    # save_custom_constraints(settings_name=sheet.range("settings_name").value)


def export_scenario_tool_data(*, wb: "xw.Book", data_folder: str, start_dir: Optional[os.PathLike] = None):
    dir_str = DirStructure(data_folder=data_folder, start_dir=start_dir)
    logger.info(f"Saving data to {dir_str.data_dir}")

    if isinstance(wb, str):
        import xlwings as xw

        wb = xw.Book(dir_str.proj_dir / wb)

    wb.app.calculate()

    # update __names__ using the VBA macro assumed to be embedded in the Scenario Tool
    wb.macro("ListNamedRanges")()

    logger.info("Saving component data")
    new_modeling_toolkit.ui.scenario_tool.save_attributes_files(wb=wb, data_folder=dir_str.data_dir, model="resolve")

    logger.info("Saving linkages")
    new_modeling_toolkit.ui.scenario_tool.save_linkages_csv(wb=wb, data_folder=dir_str.data_dir, model="resolve")

    logger.info("Saving system configuration")
    new_modeling_toolkit.ui.scenario_tool.save_system(wb=wb, data_folder=dir_str.data_dir, sheet_name="System")

    logger.info("Saving Resolve case settings")
    save_multiple_cases(sheet_name="RESOLVE Settings", wb=wb, data_folder=dir_str.data_dir, model="resolve")


if __name__ == "__main__":
    # Create mock caller
    curr_dir = upath.UPath(__file__).parent
    xw.Book(
        # "/Users/skramer/code/new-modeling-toolkit/Resolve Scenario Tool - CPUC IRP 2023 PSP - PUBLIC - v1.0.2-hydrogen.xlsm"
        "/Users/rgo/PycharmProjects/kit/Resolve Scenario Tool - 25-26-TPP - v7.xlsm"
    ).set_mock_caller()
    wb = xw.Book.caller()
    # Call functions
    # save_RESOLVE_case_settings(sheet_name=r"RESOLVE Settings", data_folder="/Users/rgo/PycharmProjects/kit/data-tpp/")
