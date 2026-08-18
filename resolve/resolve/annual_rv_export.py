import os
import sys

import ipywidgets as widgets
import numpy as np
import pandas as pd
import xlwings as xw
from IPython.display import display


class AnnualResultsViewerExport:

    def __init__(self, rv_path: str, results_path: str):
        """
        Initialize the AnnualResultsViewerExport class.
        Args:
            rv_path (str): Path to the RV template file.
            results_path (str): Path to the results directory.
        """
        self.rv_path = rv_path
        self.results_path = results_path

    ##### Some helper functions for use in the jupyter notebook #####
    def get_name_specific_component_list(self, component_path: str) -> list:
        """
        Get a list of component names for a specific component type.
        Args:
            component_path (str): Path to the component type directory.
        Returns:
            list: List of component names (str).
        """
        try:
            comp_list = [s.name for s in (self.results_path / "summary" / component_path).iterdir() if s.is_dir()]
        except FileNotFoundError:
            component_type = component_path.rsplit("/", 1)[-1]
            print(f"No components of type {component_type} in this case.")
            comp_list = []
        return comp_list

    def get_passthrough_list(self) -> list:
        """
        Get a list of custom passthrough input names.
        Returns:
            list: List of passthrough input names (str).
        """
        try:
            passthrough_list = [
                f.name.replace(".csv", "") for f in (self.results_path / "passthrough").iterdir() if f.is_file()
            ]
            passthrough_list = [p for p in passthrough_list if p != "linkages" and p != "scenarios"]
        except FileNotFoundError:
            print(f"No custom passthrough inputs in this case.")
            passthrough_list = []
        return passthrough_list

    @staticmethod
    def name_specific_sheets(component_type: str, component_list: str) -> dict:
        """
        Create widgets for naming sheets for each component.
        Args:
            component_type (str): Type of the component.
            component_list (list): List of component names.
        Returns:
            dict or None: Dictionary of widgets for each component, or None if list is empty.
        """
        if len(component_list) == 0:
            return None

        # Add hourly and hourly by resource names for ERM policies (only component which shows non-annual results)
        if "EnergyReserveMargin" in component_type:
            hourly_erm_list = []
            for component in component_list:
                hourly_erm_list.append(f"{component}_Hourly")
                hourly_erm_list.append(f"{component}_Hourly_by_Resource")
            component_list = hourly_erm_list

        # create text boxes for each subdir
        max_len = max((len(s) for s in component_list), default=10)
        label_width = f"{min(max_len + 2, 60)}ch"  # make the label area wide enough based on the longest name

        label = widgets.HTML(value=f"<b>{component_type}:</b>")
        display(label)

        text_boxes = {
            name: widgets.Text(
                description=name,
                value=name.replace("_", " ") + " Summary",  # default value = key with underscores removed "Summary"
                placeholder="Leave blank to not use these results",
                style={"description_width": label_width},
                layout=widgets.Layout(width="700px"),  # overall widget width (optional)
            )
            for name in component_list
        }

        # display the widgets
        for tb in text_boxes.values():
            display(tb)

        return text_boxes

    @staticmethod
    def custom_sheet_name_mapping(names: dict, component_type: str) -> list:
        """
        Map custom sheet names to result file paths for components.
        Args:
            names (dict): Dictionary of widgets for each component.
            component_type (str): Type of the component.
        Returns:
            list: List of tuples (file path, sheet name).
        """
        if names is None:
            return []
        path_prefix = f"summary/{component_type}/"
        component_sheet_map = {}
        for c, sheet_name in names.items():
            if len(sheet_name.value) == 0:
                continue  # Skip if sheet name is not given
            if "Policy/" in component_type and "EnergyReserveMargin" not in component_type:
                path_suffix = f"{c}/{c}_annual_results_by_component.csv"
            elif "EnergyReserveMargin" in component_type:
                if "Hourly_by_Resource" in c:
                    original_component_name = c.replace("_Hourly_by_Resource", "")
                    path_suffix = (
                        f"{original_component_name}/{original_component_name}_multi_index_weather_timestamp_results.csv"
                    )
                else:
                    original_component_name = c.replace("_Hourly", "")
                    path_suffix = f"{original_component_name}/{original_component_name}_weather_timestamp_results.csv"
            elif component_type == "ELCCSurface":
                path_suffix = f"{c}/ELCC Facet Value for Policy.csv"
            component_sheet_map[path_prefix + path_suffix] = sheet_name.value
        name_specific_mapping = [(k, v) for k, v in component_sheet_map.items()]
        return name_specific_mapping

    @staticmethod
    def name_standard_sheets() -> dict:
        """
        Creates and displays a set of text box widgets for mapping standard sheet names to their corresponding summary names.
        The function initializes a mapping between internal sheet names and their display names, then generates
        a text box widget for each mapping using ipywidgets. Each widget allows the user to customize the mapping,
        with a placeholder indicating that leaving the box blank will exclude the results. The widgets are displayed
        in the notebook, and a dictionary of the widgets keyed by the internal sheet names is returned.
        Returns:
            dict: A dictionary where keys are internal sheet names and values are ipywidgets.Text objects for user input.
        """

        text_box_map = {
            "TxPath Annual Results": "Transmission Summary",
            "TxPathGroup Annual Results": "Transmission Group Summary",
            "Zone Annual Results": "Zonal Summary",
            "ResourceGroup Annual Results": "Resource Group Summary",
            "Resource Annual Results": "Resource Summary",
            "ResourceGroup by Product Annual Results": "RG by Product Summary",
            "Resource by Product Annual Results": "Resource by Product Summary",
            "Load Annual Results": "Load Summary",
            "Component Cost Summary": "Component Cost Summary",
            "Component Slack Cost Summary": "Slack Cost Summary",
            "CandidateFuel Annual Results": "Candidate Fuel Summary",
            "Asset Annual Results": "Asset Summary",
            "TxConstraint Annual Results": "Tx Constraint Summary",
            "AssetGroup Annual Results": "Asset Group Summary",
            "Policy Annual Results": "Policy Summary",
            "ELCCSurface Annual Results": "ELCC_MW",
            "Linkages Passthrough": "linkages",
            "Discount Factors": "Discount Factor",
            "Fuel Plant Annual Results": "Plant Summary",
            "Fuel Plant by Product Annual Results": "Plant by Product Summary",
            "Fuel PlantGroup Annual Results": "Plant Group Summary",
            "Fuel PlantGroup by Product Annual Results": "Plant Group by Product Summary",
        }

        # create text boxes for each standard sheet
        max_len = max((len(s) for s in text_box_map.keys()), default=10)
        label_width = f"{min(max_len + 2, 60)}ch"  # make the label area wide enough based on the longest name

        label = widgets.HTML(value=f"<b>Standard Sheet Mapping:</b>")
        display(label)

        text_boxes = {
            key: widgets.Text(
                description=key,
                value=value,  # default value = key with underscores removed "Summary"
                placeholder="Leave blank to not use these results",
                style={"description_width": label_width},
                layout=widgets.Layout(width="700px"),  # overall widget width (optional)
            )
            for key, value in text_box_map.items()
        }

        # display the widgets
        for tb in text_boxes.values():
            display(tb)

        return text_boxes

    @staticmethod
    def standard_sheet_mapping(names: dict) -> list:
        """
        Map standard sheet names to result file paths.
        Args:
            names (dict): Dictionary of widgets for each standard sheet.
        Returns:
            list: List of tuples (file path, sheet name).
        """
        standard_sheet_files = {
            "TxPath Annual Results": "summary/TxPath_annual_results_summary.csv",
            "TxPathGroup Annual Results": "summary/TxPathGroup_annual_results_summary.csv",
            "Zone Annual Results": "summary/Zone_annual_results_summary.csv",
            "ResourceGroup Annual Results": "summary/ResourceGroup_annual_results_summary.csv",
            "Resource Annual Results": "summary/Resource_annual_results_summary.csv",
            "ResourceGroup by Product Annual Results": "summary/ResourceGroup_annual_results_by_product_summary.csv",
            "Resource by Product Annual Results": "summary/Resource_annual_results_by_product_summary.csv",
            "Load Annual Results": "summary/Load_annual_results_summary.csv",
            "Component Cost Summary": "summary/component_cost_summary.csv",
            "Component Slack Cost Summary": "summary/component_slack_cost_summary.csv",
            "CandidateFuel Annual Results": "summary/CandidateFuel_annual_results_summary.csv",
            "Asset Annual Results": "summary/Asset_annual_results_summary.csv",
            "TxConstraint Annual Results": "summary/CaisoTxConstraint_annual_results_summary.csv",
            "AssetGroup Annual Results": "summary/AssetGroup_annual_results_summary.csv",
            "Policy Annual Results": "summary/Policy_annual_results_summary.csv",
            "ELCCSurface Annual Results": "summary/ELCCSurface_annual_results_summary.csv",
            "Linkages Passthrough": "passthrough/linkages.csv",
            "Discount Factors": "temporal_settings/modeled_year_discount_factors.csv",
            "Fuel Plant Annual Results": "summary/Plant_annual_results_summary.csv",
            "Fuel Plant by Product Annual Results": "summary/Plant_annual_results_by_product_summary.csv",
            "Fuel PlantGroup Annual Results": "summary/PlantGroup_annual_results_summary.csv",
            "Fuel PlantGroup by Product Annual Results": "summary/PlantGroup_annual_results_by_product_summary.csv",
        }
        if names is None:  # This shouldn't happen, but just in case
            return []
        standard_sheet_map = {}
        for key, sheet_name in names.items():
            if len(sheet_name.value) == 0:
                continue  # Skip if sheet name is not given
            path = standard_sheet_files[key]
            standard_sheet_map[path] = sheet_name.value
        standard_mapping = [(k, v) for k, v in standard_sheet_map.items()]
        return standard_mapping

    @staticmethod
    def custom_passthrough_mapping(names: dict) -> list:
        """
        Map custom passthrough sheet names to passthrough file paths.
        Args:
            names (dict): Dictionary of widgets for each passthrough input.
        Returns:
            list: List of tuples (file path, sheet name).
        """
        if names is None:
            return []
        path_prefix = f"passthrough/"
        passthrough_map = {}
        for p, sheet_name in names.items():
            if len(sheet_name.value) == 0:
                continue  # Skip if sheet name is not given
            path_suffix = f"{p}.csv"
            passthrough_map[path_prefix + path_suffix] = sheet_name.value
        passthrough_mapping = [(k, v) for k, v in passthrough_map.items()]
        return passthrough_mapping

    def generate_rv(self, cases_and_timestamps: list, sheet_mapping: list, macro_enabled: bool = True) -> None:
        """
        Generate Results Viewer Excel files for given cases and timestamps.
        Args:
            cases_and_timestamps (list): List of tuples (case, timestamp).
            sheet_mapping (list): List of tuples (summary filename, target sheet name).
            macro_enabled (bool): Whether to save as a macro-enabled Excel file (.xlsb or .xlsm).
        Returns:
            None
        """
        if macro_enabled:
            if ".xlsb" in str(self.rv_path):
                new_rv = "Resolve RV - {} - {}.xlsb"
            else:
                new_rv = "Resolve RV - {} - {}.xlsm"
        else:
            new_rv = "Resolve RV - {} - {}.xlsx"
        rv_target_dir = self.rv_path.parent  # Print new RV to directory that holds the template

        for case, timestamp in cases_and_timestamps:
            # If the RV already exists, skip to the next iteration
            if os.path.exists(os.path.join(rv_target_dir, new_rv.format(case, timestamp))):
                print(
                    f"Result Viewer Already Exists for {case} {timestamp}. \n"
                    f"Save it as a copy under a different name to generate a new version."
                )
                if len(cases_and_timestamps) == 1:
                    return
                continue

            # Once confirmed that the RV does not exist, start loading raw results
            wb = xw.Book(self.rv_path)
            print(f"Starting RV Creation for {case} {timestamp}")
            for summary_filename, target_sheet_name in sheet_mapping:
                if target_sheet_name not in [sheet.name for sheet in wb.sheets]:
                    print(
                        f"Target sheet {target_sheet_name} does not exist in your template. \n"
                        f"Skipping this sheet for now. If you need it, interrupt this code block and check your mapping "
                        f"above to make sure each sheet name exists in the template. Then re-run this block."
                    )
                    print()
                    continue

                wb.app.status_bar = f"Loading {summary_filename}"
                # Disable Excel features temporarily for better performance
                wb.app.screen_updating = False
                wb.app.calculation = "manual"

                df = pd.DataFrame()
                try:
                    df = pd.concat([df, pd.read_csv(self.results_path / summary_filename)], ignore_index=True)
                except FileNotFoundError:
                    # If the file doesn't exist, print a warning and skip
                    print(
                        f"File {summary_filename} does not exist for {case} {timestamp}. Replacing {target_sheet_name} with blank sheet."
                    )
                    print()
                    wb.sheets[target_sheet_name].api.AutoFilterMode = False
                    wb.sheets[target_sheet_name].clear()
                    continue

                # Guard clause for very large files
                if len(df) > 1e6:
                    print("File has more than 1 million rows, which may cause Excel to crash. Skipping this file.")
                    print()
                    wb.sheets[target_sheet_name].api.AutoFilterMode = False
                    wb.sheets[target_sheet_name].clear()
                    continue

                # Replace inf and -inf values with strings before copying to Excel
                df.replace(np.inf, "inf", inplace=True)
                df.replace(-np.inf, "-inf", inplace=True)

                print(f"Copying data to {target_sheet_name}")
                wb.sheets[target_sheet_name].api.AutoFilterMode = False
                wb.sheets[target_sheet_name].clear()

                # Copy with chunks to avoid memory issues
                # macOS = slower AppleEvent communication → smaller chunks
                # Windows = fast COM → larger chunks OK
                if sys.platform == "darwin":
                    chunk_size = 5_000
                else:
                    chunk_size = 50_000
                wb.sheets[target_sheet_name].range("A1").options(index=False, chunksize=chunk_size).value = [
                    df.columns.tolist()
                ] + df.values.tolist()
                print(f"Done with {target_sheet_name}")
                print()

            print(f"Done reading and copying results files for {case} {timestamp}")
            wb.sheets["Dashboard"].range("active_case").value = f"{case}_{timestamp}"
            wb.app.status_bar = f"Finished loading {case} {timestamp}"

            wb.save(path=os.path.join(rv_target_dir, new_rv.format(case, timestamp)))
            print("New Results Viewer saved!")

        return wb.close()
