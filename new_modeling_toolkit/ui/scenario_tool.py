import os
import sys
from importlib import import_module
from typing import Optional

import pandas as pd
import upath
from loguru import logger

import xlwings as xw


# Set traceback limit to 0 so that error message is more readable in Excel popup window
sys.tracebacklimit = 0


# TODO 2023-05-14: Could make this a ScenarioTool class if data handling gets more complex


def check_version(wb: Optional["Book"] = None):
    """Compare Scenario Tool version number (embedded as a named value) to acceptable version range.

    See https://peps.python.org/pep-0440/ for how to specify `COMPATIBILITY_SET` version requirements.
    """
    from packaging import version, specifiers

    if wb is None:
        wb = xw.Book.caller()

    version_number = version.parse(wb.names("VERSION_NUMBER").refers_to[2:-1])
    COMPATIBILITY_SET = specifiers.SpecifierSet("==0.5.*")

    if version_number not in COMPATIBILITY_SET:
        wb.app.alert(
            f"Warning: This Scenario Tool (version {version_number}) may not be fully compatible with current code. "
            "Code will continue but may have hidden surprises."
        )


def save_attributes_files(
    *, model, wb: Optional[xw.Book] = None, data_folder: Optional[os.PathLike] = None, overwrite: bool = True
):
    """Save all component attribute CSV files from Scenario Tool."""
    if wb is None:
        wb = xw.Book.caller()

    check_version(wb=wb)

    # Locate data folder to save to
    if data_folder is None:
        data_folder = upath.UPath(wb.fullname).parent / "data"

    data_folder = upath.UPath(data_folder) / "interim"

    # Locate components & class definitions
    filter = "Resolve-only" if model == "recap" else "Recap-only"
    component_class_sheets = (
        wb.sheets["Lists"].range("component_class_sheets").options(pd.DataFrame, index=False).value.dropna(how="all")
    )
    component_class_sheets.drop(
        component_class_sheets[component_class_sheets["Model(s)"] == filter].index, inplace=True
    )
    component_class_sheets.drop(
        component_class_sheets[component_class_sheets["Model(s)"] == filter].index, inplace=True
    )
    component_class_sheets["Fully-Specified Attributes"] = component_class_sheets["Fully-Specified Attributes"].astype(
        bool
    )

    # Loop through tabs to get data
    sheet_names = [sheet.name for sheet in wb.sheets]

    for (module, component, save_path), sheets_with_component_attrs in sorted(
        component_class_sheets.groupby(["NMT Module", "Component Class", "Save Path"])
    ):
        component_class = import_module(module).__dict__[component]

        # Get data from multiple sheets
        data = pd.DataFrame()
        for _, config in sheets_with_component_attrs.iterrows():
            sheet_name = config["Tab"]
            fully_specified = config["Fully-Specified Attributes"]
            new_style = config["New Style"]
            if sheet_name in sheet_names:
                data = pd.concat(
                    [
                        data,
                        component_class.get_data_from_xlwings(
                            wb=wb,
                            sheet_name=sheet_name,
                            fully_specified=fully_specified,
                            new_style=new_style,
                        ),
                    ]
                )
            else:
                wb.app.status_bar = f"{sheet_name} not found in current Scenario Tool"

        # Save to CSV
        if not data.empty:
            component_class.save_instance_attributes_csvs(
                wb=wb, data=data, save_path=data_folder / f"{save_path}", overwrite=overwrite
            )

    # Clear status bar
    wb.app.status_bar = None


def save_linkages_csv(*, model, wb: Optional["Book"] = None, data_folder: Optional[os.PathLike] = None):
    """Save all component attribute CSV files from Scenario Tool."""
    if wb is None:
        wb = xw.Book.caller()

    check_version(wb=wb)

    # Locate data folder to save to
    if data_folder is None:
        data_folder = upath.UPath(wb.fullname).parent / "data"

    data_folder = upath.UPath(data_folder) / "interim" / "systems" / wb.sheets["System"].range("system_name").value
    data_folder.mkdir(parents=True, exist_ok=True)

    # Loop through linkage pairs in Scenario Tool
    linkages = pd.DataFrame()
    filter = "Resolve-only" if model == "recap" else "Recap-only"
    linkage_sheets = (
        wb.sheets["Lists"].range("linkages_sheets").options(pd.DataFrame, index=False).value.dropna(how="all")
    )
    linkage_sheets.drop(linkage_sheets[linkage_sheets["Model(s)"] == filter].index, inplace=True)
    linkage_sheets = linkage_sheets.itertuples(index=False)

    for (
        model,
        sheet,
        linkage,
        named_range,
        column_type,
        scenario_column,
        other_column_named_range,
        other_column_first,
    ) in linkage_sheets:
        wb.app.status_bar = f"Saving {linkage} from {sheet}"
        if sheet in [sheet_obj.name for sheet_obj in wb.sheets]:
            if column_type == "TupleColumn":
                df = wb.sheets[sheet].range(named_range).options(pd.DataFrame, ndim=2, index=False, header=False).value
                df.columns = [0, 1]
            elif column_type == "BooleanColumn":
                rngs = [
                    wb.sheets[sheet]
                    .range(other_column_named_range)
                    .options(pd.DataFrame, ndim=2, index=False, header=False)
                    .value,
                    wb.sheets[sheet].range(named_range).options(pd.DataFrame, ndim=2, index=False, header=False).value,
                ]
                if not other_column_first:
                    rngs = rngs[::-1]
                df = pd.concat(
                    rngs,
                    axis=1,
                )

                # Rename columns
                df.columns = [0] + wb.sheets[sheet].range(named_range).offset(row_offset=-3).resize(row_size=1).options(
                    ndim=1
                ).value

                # Replace `True` values with name of columns
                df.iloc[:, 1:] = df.iloc[:, 1:].replace(True, pd.Series(df.columns, df.columns))

                df["linkage"] = linkage
            elif column_type == "NameColumn":
                rngs = [
                    wb.sheets[sheet]
                    .range(other_column_named_range)
                    .options(pd.DataFrame, ndim=2, index=False, header=False)
                    .value,
                    wb.sheets[sheet].range(named_range).options(pd.DataFrame, ndim=2, index=False, header=False).value,
                ]
                df = pd.concat(
                    rngs,
                    axis=1,
                )
                df.iloc[:, 1] = df.iloc[:, 1].replace(
                    True, wb.sheets[sheet].range(named_range).offset(row_offset=-3).resize(1, 1).value
                )

                # Rename columns
                df.columns = [0] + ([linkage] * wb.sheets[sheet].range(named_range).shape[1])

            else:
                wb.app.status_bar = f"{linkage} linkages on {sheet} in Scenario Tool not recognized"

            # Add linkage name
            if not df.empty:
                df["linkage"] = linkage

                # Get all scenario tags (or return a index-length list of None)
                scenario: list = (
                    wb.sheets[sheet].range(f"{scenario_column}").value
                    if scenario_column is not None
                    else [None] * len(df)
                )
                df["scenario"] = scenario

                # Drop stray rows and melt
                df = df.melt(id_vars=[0, "linkage", "scenario"]).dropna(subset=0).drop(columns=["variable"])

                if other_column_first is True or other_column_first is None:
                    df = df.rename(columns={0: "component_from", "value": "component_to"})
                elif other_column_first is False:
                    df = df.rename(columns={0: "component_to", "value": "component_from"})

                # Combine dataframes
                linkages = pd.concat([linkages, df], ignore_index=True, axis=0)

    # Remove `False` or `None` values in `component_to`
    linkages = linkages[linkages["component_to"] != False].dropna(subset="component_to")

    linkages = (
        linkages.dropna(subset=["component_from"]).drop_duplicates().to_csv(data_folder / "linkages.csv", index=False)
    )

    wb.app.status_bar = None


def save_system(sheet_name: str, wb: Optional["Book"] = None, data_folder: Optional[os.PathLike] = None):
    # Open workbook and define system worksheet
    if wb is None:
        wb = xw.Book.caller()

    check_version(wb=wb)
    sheet = wb.sheets[sheet_name]

    # Locate data folder to save to
    if data_folder is None:
        data_folder = upath.UPath(wb.fullname).parent / "data"

    data_folder = upath.UPath(data_folder) / "interim"

    # Get system name / directory
    system_dir = data_folder / "systems" / sheet.range("system_name").value
    system_dir.mkdir(parents=True, exist_ok=True)

    # Get components data from worksheet
    df_components = (
        wb.sheets["System"]
        .range("components_data_range")
        .expand("down")
        .expand("right")
        .options(pd.DataFrame, expand="table")
        .value
    ).dropna(how="all")

    # Save to components.csv and linkages.csv
    df_components.to_csv(system_dir / "components.csv")

    # Save attributes.csv
    pd.DataFrame(columns=["timestamp", "attribute", "value"]).to_csv(system_dir / "attributes.csv", index=False)

    # Clear status bar
    wb.app.status_bar = None


def get_system_folders(
    sheet_name: str, rng_name: str, wb: Optional[xw.Book] = None, data_folder: Optional[os.PathLike] = None
):
    """Get the name of all saved systems."""
    if wb is None:
        wb = xw.Book.caller()

    check_version(wb=wb)

    # Locate data folder to save to
    if data_folder is None:
        data_folder = upath.UPath(wb.fullname).parent / "data"

    data_folder = upath.UPath(data_folder) / "interim"

    folder_path = data_folder / "systems"
    paths = [[p.parts[-1]] for p in folder_path.iterdir() if p.is_dir()]
    # Write to Results Viewer range
    wb.sheets[sheet_name].range(rng_name).clear_contents()
    wb.sheets[sheet_name].range(rng_name).value = sorted(paths)

    # Clear status bar
    wb.app.status_bar = None


def load_system(sheet_name: str, wb: Optional["Book"] = None, data_folder: Optional[os.PathLike] = None):
    # Open workbook and define system worksheet
    if wb is None:
        wb = xw.Book.caller()

    check_version(wb=wb)
    sheet = wb.sheets[sheet_name]

    # Locate data folder to save to
    if data_folder is None:
        data_folder = upath.UPath(wb.fullname).parent / "data"

    data_folder = upath.UPath(data_folder)
    system_dir = data_folder / "interim" / "systems" / str(sheet.range("system_to_load").value)

    # Load existing system component and linkages
    df_components = pd.read_csv(system_dir / "components.csv")

    # Populate data into UI
    sheet.range("component_types").clear_contents()
    sheet.range("component_names").clear_contents()

    sheet.range("component_types").value = df_components["component"].values.reshape(-1, 1)
    sheet.range("component_names").value = df_components["instance"].values.reshape(-1, 1)

    # Load System attributes
    # sheet.range("System.scenario").clear_contents()
    # sheet.range("System.scenario").value = df_attributes["scenario"].unique().reshape(-1, 1)
    # for att in df_attributes["attribute"].unique():
    #     dt_att = df_attributes.loc[df_attributes["attribute"] == att].pivot(
    #         index="scenario", columns="timestamp", values="value"
    #     )
    #     columns = list(sheet.range(att).value[:2])
    #     sheet.range(att).clear_contents()
    #     sheet.range(att).value = columns + list(dt_att.values)

    # Clear status bar
    wb.app.status_bar = None


def get_valid_case_folders(
    sheet_name: str,
    rng_name: str,
    model_name: str,
    wb: Optional[xw.Book] = None,
    data_folder: Optional[os.PathLike] = None,
):
    """Get the name of all non-empty folders.
    TODO 2022-06-05: This function is very similar to results_viewers.get_valid_results_folders. Can be combined
    """
    if wb is None:
        wb = xw.Book.caller()

    check_version(wb=wb)
    # Locate data folder to save to
    if data_folder is None:
        data_folder = upath.UPath(wb.fullname).parent / "data"

    data_folder = upath.UPath(data_folder)

    folder_path = data_folder / "settings" / model_name
    # nested list to make it "tall" instead of "wide"
    paths = [[p.parts[-1]] for p in folder_path.iterdir() if p.is_dir()]
    # Write to Results Viewer range
    wb.sheets[sheet_name].range(rng_name).clear_contents()
    wb.sheets[sheet_name].range(rng_name).value = sorted(paths)


def update_cases_to_run(
    sheet_name: str,
    rng_name: str,
    model_name: str,
    wb: Optional[xw.Book] = None,
    data_folder: Optional[os.PathLike] = None,
):
    """Save selected cases to cases_to_run.csv file."""
    if wb is None:
        wb = xw.Book.caller()

    check_version(wb=wb)
    # Locate data folder to save to
    if data_folder is None:
        data_folder = upath.UPath(wb.fullname).parent / "data"

    data_folder = upath.UPath(data_folder)

    folder_path = data_folder / "settings" / model_name

    cases_to_run = wb.sheets[sheet_name].range(rng_name).options(pd.DataFrame, index=False).value.dropna()
    cases_to_run.to_csv(folder_path / "cases_to_run.csv", index=False)

    # Clear status bar
    wb.app.status_bar = None


def regroup_columns_by_modeled_years(*, wb: Optional["Book"] = None):
    """Regroup columns based on active modeled years by checking the contents of the second row of the named range."""
    from sys import platform

    if wb is None:
        wb = xw.Book.caller()
    # Get active modeled years
    modeled_years = wb.sheets["RESOLVE Settings"].range("settings_modeled_year_attributes").options(pd.DataFrame).value

    # Always keep first and last years
    modeled_years.iloc[[0, -1], 1] = True

    # Regroup modeled year-indexed named ranges
    for sheet in wb.sheets:
        if named_ranges := {
            name.name
            for name in wb.names
            if "$" in name.refers_to  # Should be a cell address
            and name.refers_to.split("!")[0][1:].replace("'", "") == sheet.name  # Named range on current sheet
            and "_FilterDatabase" not in name.name  # Some "hidden" names on sheets
        }:
            for named_range in named_ranges:
                headers = sheet.range(named_range).offset(row_offset=1).resize(row_size=1)

                # For now, assume # of columns exactly matched # of modeled years on Resolve Settings tab
                if len(modeled_years) == len(headers.columns):
                    wb.app.status_bar = f"Regrouping columns on {sheet.name}: {named_range}"

                    # Ungroup columns
                    try:
                        if platform in ["win32", "cygwin"]:
                            sheet.api.Columns(
                                f"${headers.address.split('$')[1]}:${headers.address.split('$')[3]}"
                            ).Ungroup()
                        elif platform == "darwin":
                            sheet.api.columns[
                                f"${headers.address.split('$')[1]}:${headers.address.split('$')[3]}"
                            ].ungroup()
                        else:
                            logger.exception(
                                "It seems like you're running on Linux. Running the Excel UIs on Linux is not supported."
                            )
                    except:
                        logger.debug(f"Couldn't ungroup {named_range}")

                    # Group columns

                    for cell in headers:
                        if cell.value in modeled_years[modeled_years["modeled_years"] == False].index:
                            if platform in ["win32", "cygwin"]:
                                sheet.api.Columns(
                                    f"${cell.address.split('$')[1]}:${cell.address.split('$')[1]}"
                                ).Group()
                            elif platform == "darwin":
                                sheet.api.columns[
                                    f"${cell.address.split('$')[1]}:${cell.address.split('$')[1]}"
                                ].group()
                            else:
                                logger.exception(
                                    "It seems like you're running on Linux. Running the Excel UIs on Linux is not supported."
                                )


def run_mock_pathways(wb: Optional[xw.Book] = None):
    """Run the Pathways UI to print out inputs (for testing)."""

    if wb is None:
        curr_dir = upath.UPath(__file__).parent
        xw.Book(curr_dir / ".." / ".." / ".." / "pathways" / "Pathways Scenario Tool.xlsb").set_mock_caller()
        wb = xw.Book.caller()

    # Automatically populate Pathways UI interpreter path
    from sys import platform

    if platform in ["win32", "cygwin"]:
        wb.sheets["xlwings.conf"].range("B1").value = sys.executable
    elif platform == "darwin":
        wb.sheets["xlwings.conf"].range("B2").value = sys.executable
    else:
        logger.exception("It seems like you're running on Linux. Running the Excel UIs on Linux is not supported.")

    # Save files
    save_simplified_emissions_module_case_settings(sheet_name="PATHWAYS Case Settings")
    save_attributes_files(wb=wb)
    save_system(sheet_name="System")


def run_mock_resolve():
    curr_dir = upath.UPath(__file__).parent
    xw.Book(curr_dir / ".." / ".." / "RECAP-RESOLVE Scenario Tool_20230202.xlsm").set_mock_caller()
    wb = xw.Book.caller()

    # Automatically populate UI interpreter path
    # if sys.platform in ["win32", "cygwin"]:
    #     wb.sheets["xlwings.conf"].range("B1").value = sys.executable
    # elif sys.platform == "darwin":
    #     wb.sheets["xlwings.conf"].range("B2").value = sys.executable
    # else:
    #     print("It seems like you're running on Linux. Running the Excel UIs on Linux is not supported.")

    # Call functions
    # save_attributes_files(wb=wb)
    # save_system(sheet_name="System")
    load_system(sheet_name="System")


if __name__ == "__main__":
    curr_dir = upath.UPath(__file__).parent
    xw.Book(
        str(
            (
                upath.UPath("../..") / "/Users/rgo/PycharmProjects/kit/Resolve Scenario Tool - 25-26-TPP - v7.xlsm"
            ).absolute()
        )
    ).set_mock_caller()
    wb = xw.Book.caller()

    # regroup_columns_by_modeled_years(wb=wb)
    list_named_ranges = wb.macro("ListNamedRanges")
    list_named_ranges()
    save_attributes_files(model="resolve", wb=wb, data_folder=upath.UPath("../../data-tpp").absolute())
    # save_linkages_csv(model="resolve", wb=wb, data_folder=upath.UPath("../../data-cpuc-test").absolute())
    # save_system(sheet_name="System", wb=wb, data_folder=upath.UPath("../../data-cpuc-test").absolute())
