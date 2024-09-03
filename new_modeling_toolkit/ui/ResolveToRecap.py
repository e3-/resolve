import pathlib

import numpy as np
import pandas as pd
import xlwings as xw


def get_RESOLVE_case_list(sheet_name: str, rng_name: str, model: str = "resolve"):
    """Update RESOLVE case list in reports/ folder."""
    wb = xw.Book.caller()
    folder_path = pathlib.Path(wb.fullname).parent / "reports" / model
    paths = [[p.parts[-1]] for p in folder_path.iterdir() if p.is_dir()]
    wb.sheets[sheet_name].range(rng_name).clear_contents()
    wb.sheets[sheet_name].range(rng_name).value = sorted(paths)


def get_RESOLVE_run_list(sheet_name: str, rng_name: str, case_name: str, model: str = "resolve"):
    """Given RESOLVE case, update run list in reports/casename/ folder."""
    wb = xw.Book.caller()
    folder_path = pathlib.Path(wb.fullname).parent / "reports" / model / case_name
    paths = [[p.parts[-1]] for p in folder_path.iterdir() if p.is_dir()]
    wb.sheets[sheet_name].range(rng_name).clear_contents()
    wb.sheets[sheet_name].range(rng_name).value = sorted(paths)


def load_RESOLVE_results(sheet_name: str, component_sheet_name: str, model: str = "resolve"):
    """Load specific RESOLVE case results from reports/ folder."""
    # Open workbook and get case name to load
    wb = xw.Book.caller()
    sheet = wb.sheets[sheet_name]
    case_name = sheet.range("RtoRcase_name").value
    run_name = sheet.range("RtoRrun_name").value

    # Define current working directory and path to report directory
    curr_dir = pathlib.Path(wb.fullname).parent
    results_dir = curr_dir / "reports" / model / case_name / run_name / "results_summary"

    # Read resource build results
    df_build = pd.read_csv(results_dir / "resource_summary.csv")
    df_build["Model Year"] = pd.to_datetime(df_build["Model Year"]).dt.year
    df_operational_MW = df_build.pivot(index="Resource", columns="Model Year", values="Operational Capacity (MW)")
    df_operational_MWh = df_build.pivot(index="Resource", columns="Model Year", values="Operational Capacity (MWh)")

    # reformat results to be full calendar year
    component_sheet = wb.sheets[component_sheet_name]
    yr_list = component_sheet.range("planned_installed_capacity").value[1]
    df_operational_MW_formatted = df_operational_MW.reindex(
        columns=range(yr_list[0].year, yr_list[-1].year + 1)
    ).fillna(0)
    df_operational_MWh_formatted = df_operational_MWh.reindex(
        columns=range(yr_list[0].year, yr_list[-1].year + 1)
    ).fillna(0)

    # paste results into component sheet
    last_row = component_sheet.range("B8").end("down").row
    component_sheet.range("Resource").value = modify_component_inputs(
        component_sheet,
        rng_name="Resource",
        unused_row_num=last_row - 8,
        modified_value=df_operational_MW_formatted.index.values.tolist(),
    ).reshape(-1, 1)
    component_sheet.range("Resource.scenario").value = modify_component_inputs(
        component_sheet,
        rng_name="Resource.scenario",
        unused_row_num=last_row - 8,
        modified_value=["ResolveBuilds_" + str(case_name) + "_" + str(run_name)] * len(df_operational_MW_formatted),
    ).reshape(-1, 1)
    component_sheet.range("planned_installed_capacity").value = modify_component_inputs(
        component_sheet,
        rng_name="planned_installed_capacity",
        unused_row_num=last_row - 6,
        modified_value=df_operational_MW_formatted.values.tolist(),
    )
    component_sheet.range("planned_storage_capacity").value = modify_component_inputs(
        component_sheet,
        rng_name="planned_storage_capacity",
        unused_row_num=last_row - 6,
        modified_value=df_operational_MWh_formatted.values.tolist(),
    )


def modify_component_inputs(sheet, rng_name: str, unused_row_num: int, modified_value):
    # read in used and blank columns
    rng_value = sheet.range(rng_name).value

    # check if there are enough rows to append new data
    if unused_row_num + len(modified_value) <= len(rng_value):
        # modify with additional rows
        rng_value[unused_row_num : (unused_row_num + len(modified_value))] = modified_value
        # write back to range
        return np.array(rng_value)
    else:
        raise ValueError("Error in loading RESOLVE results: not enough rows to append resource build results.")


if __name__ == "__main__":
    # Create mock caller
    curr_dir = pathlib.Path(__file__).parent
    xw.Book(curr_dir / ".." / ".." / "RECAP-RESOLVE Scenario Tool_20230419_R2R.xlsm").set_mock_caller()
    wb = xw.Book.caller()
    # Call functions
    # load_RESOLVE_results(sheet_name="RESOLVE2RECAP", component_sheet_name="Resources")
    get_RESOLVE_run_list(sheet_name="Lists", rng_name="list_resolve_result_run", case_name="", model="resolve")
