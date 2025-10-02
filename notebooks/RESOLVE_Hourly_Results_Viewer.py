# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.16.2
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---
# %% [markdown]
# # RESOLVE Hourly Dispatch and SOC Viewer
#
# ## Interactive Analysis and Plotting for Hourly- and Chrono-indexed Results
# %%
# Import packages
import datetime
import pathlib

import ipywidgets as widgets
import pandas as pd
from ipyfilechooser import FileChooser
from IPython.display import display
from ipywidgets import Layout
from loguru import logger

from new_modeling_toolkit.resolve.hourly_results_processing import ResolveHourlyResultsViewer as RV

# %% [markdown]
# ### Step 0. Define Excel Results Viewer Named Ranges (for aggregating and plotting hourly resource dispatch)

# %%
"""
These are the names of the named ranges which must be present if you are using an Excel Results Viewer to define aggregation settings (see Step 2).

If you are not aggregating resources and you would like to instead analyze the resource results of all resources individually, you can skip Step 2, but you will not be able to produce hourly dispatch charts.

'hourly_aggregation_settings' is a named range that must include three columns:
    First, the Component names of the resources and resource groups in your case settings which include hourly dispatch results
    Second, the Component Type of these resources, which is the object that these resources are known as in RESOLVE (e.g., StorageResource, StorageResourceGroup, etc.)
    Third, the Build Group to which you would like to aggregate certain resources (e.g., Solar, Natural Gas, etc.)

'build_group_colors' is a named range that must include three columns:
    First, the Build Group column should be the unique set of Build Groups defined in the third column of your hourly_aggregation_settings
    Second, the Chart Order column defines the order in which you want the groups to appear on an hourly dispatch chart, with 1 indicating the group will appear on the bottom of the chart.
    Third, the Color Hex column defines the color that should be applied to each build group. These should be unique.

"""
HOURLY_AGG_SETTINGS_NAMED_RANGE = "hourly_aggregation_settings"
COLOR_SETTINGS_NAMED_RANGE = "build_group_colors"

# %% [markdown]
# ### Step 1. Load Case Results from specified local directory and choose destination directory
# #### The case folder is usually named with a timestamp and it should include a "summary" folder. It must be stored on your local directory.
# #### The destination folder can be any folder in your local directory.

# %%
# Pick where raw results files are stored locally
fc = FileChooser(
    "..",
    title="<b>Select RESOLVE results folder where case results are saved:</b>",
    layout=Layout(width="800px"),
    show_only_dirs=True,
)
fc._show_dialog()
display(fc)

# Select the appropriate Destination folder
dest = FileChooser(
    "..",
    title="<b>Select Destination folder where hourly results should be sent:</b>",
    layout=Layout(width="800px"),
    show_only_dirs=True,
)
dest._show_dialog()
display(dest)

# %%
# Define selected case path and dest path
case_path = fc.selected
dest_path = dest.selected

# Import relevant temporal settings
chrono_periods_map = pd.read_csv(pathlib.Path(case_path) / "temporal_settings/chrono_periods_map.csv")
chrono_periods = [pd.Timestamp(chrono) for chrono in sorted(chrono_periods_map["chrono_period"])]
dispatch_window_weights = pd.read_csv(pathlib.Path(case_path) / "temporal_settings/dispatch_window_weights.csv")
dispatch_window_weights["dispatch_window"] = pd.to_datetime(dispatch_window_weights["dispatch_window"])
weight_map = dispatch_window_weights.set_index("dispatch_window")["weight"]
all_dispatch_windows = sorted(
    [datetime.datetime.strptime(dw, "%Y-%m-%d").date() for dw in chrono_periods_map["dispatch_window"].unique()]
)
all_years = pd.read_csv(pathlib.Path(case_path) / "temporal_settings/modeled_years.csv")
modeled_years = [pd.Timestamp(year_str) for year_str in sorted(all_years.loc[all_years["value"] == True, "timestamp"])]
modeled_years_int = [year.year for year in modeled_years]

# %% [markdown]
# ### Step 2. Are you aggregating resource results according to build groups defined in an Excel Results Viewer?
# #### If so, choose that file here. Note that the Excel workbook must contain a named range for "hourly_aggregation_settings", which assigns each resource to its build group.
# #### If not, and you'd like to analyze hourly results at the individual resource level, skip this step.

# %%
# Select the appropriate Results Viewer. Excel RV must have the named ranges defined above.
rv = FileChooser(
    "..",
    title="<b>If you'd like to aggregate resource results by a defined grouping, select Excel Annual Results Viewer where these are defined in the named ranges. "
    "To get hourly results of individual resources, leave this unselected. </b>",
    layout=Layout(width="800px"),
    filter_pattern="[!~$]*.xls*",
)
rv._show_dialog()
display(rv)

# %%
rv_path = rv.selected
if rv_path is None:
    raise AssertionError("You must select an Excel workbook in the box above.")
rv_groupings = RV.get_range_data_from_excel_rv(rv_path, HOURLY_AGG_SETTINGS_NAMED_RANGE)
color_settings_df = RV.get_range_data_from_excel_rv(rv_path, COLOR_SETTINGS_NAMED_RANGE)

# Throw an error if Build Groups are not the same in hourly_aggregation_settings and build_group_colors
if set(rv_groupings["AnalysisGroupName"].unique()) != set(color_settings_df["AnalysisGroupName"].unique()):
    only_in_rv_groupings = set(rv_groupings["AnalysisGroupName"].unique()) - set(
        color_settings_df["AnalysisGroupName"].unique()
    )
    only_in_color_settings = set(color_settings_df["AnalysisGroupName"].unique()) - set(
        rv_groupings["AnalysisGroupName"].unique()
    )
    logger.warning(
        f"The following mismatch exists bewteen your resource aggregation and color settings. Are you sure your Results Viewer settings are correct?\n"
        f"Only in hourly_aggregation_settings: {only_in_rv_groupings if len(only_in_rv_groupings) > 0 else ''}\n"
        f"Only in build_group_colors: {only_in_color_settings if len(only_in_color_settings) > 0 else ''}"
    )

if color_settings_df is not None:
    ordered_analysis_groups = color_settings_df.sort_values(by="ChartOrder")["AnalysisGroupName"].tolist()
    aggregation_config_df = RV.combine_rv_groupings_and_color_settings(rv_groupings, color_settings_df)
else:
    aggregation_config_df = rv_groupings.copy()
aggregation_config_df.set_index("Component").to_csv(f"{dest_path}/aggregation_config.csv")
print(f"The following table summarizes the aggregation settings defined in the Excel Results Viewer:")
display(aggregation_config_df)

# %% [markdown]
# ### Step 3. Create ResolveResultsViewer instance

# %%
# The default is to grab hourly results for all modeled years, but if you'd like to select only some, you can create a list of integers here.
selected_modeled_years = modeled_years_int.copy()

# create hourly RV object
if "aggregation_config_df" in locals():  # Using provided aggregation settings if Step 2 is performed
    hourly_RV = RV(
        case_results_folder=case_path,
        chrono_date_list=all_dispatch_windows,
        modeled_years=selected_modeled_years,
        aggregation_config_df=aggregation_config_df,
    )
else:  # Using all resource-level hourly results if Step 2 is skipped
    hourly_RV = RV(
        case_results_folder=case_path, chrono_date_list=all_dispatch_windows, modeled_years=selected_modeled_years
    )

# %% [markdown]
# ### Step 4. Export Load Resource Balance for all selected zones to "LRB Hourly Results" folder in defined destination path.
# #### Only run this step if you expect to need to store hourly dispatch results and you haven't saved these results already.

# %%
# Save selected dest_path
dest_path = dest.selected

# Create a label for the question
question = widgets.Label(value="For which zones do you need to export hourly results?")
display(question)
# Create multi-select option for modeled year from a pre-defined list
zones_path = pathlib.Path(case_path) / "summary" / "Zone"
all_zones = [d.name for d in zones_path.iterdir() if d.is_dir()]
zones_selected = [widgets.Checkbox(value=True, description=zone) for zone in all_zones]

# Display year checkboxes
for checkbox in zones_selected:
    display(checkbox)

# %%
# The default is to export hourly results for all modeled years, but if you'd like to select only some, you can create a list of integers here.
export_modeled_years = selected_modeled_years.copy()

# Export results to defined path
zones_for_export = [zone.description for zone in zones_selected if zone.value == True]
hourly_RV.export_lrb_hourly_results(dest_path=dest_path, modeled_years=export_modeled_years, zones=zones_for_export)

# %% [markdown]
# ### Step 5. Representative Day Dispatch Plots
# #### Use the following cells to plot the hourly dispatch of a certain zone over a certain representative day. Results will be saved in your destination folder.
# #### Note: These plots can only be generated if you have selected an Excel Results Viewer workbook with a valid resource aggregation in Step 2.

# %%
if "rv_groupings" not in locals():
    raise AssertionError(
        "Dispatch plots cannot be generated without a valid resource aggregation. Go back to Step 2 and choose your aggregation settings."
    )
if color_settings_df is None:
    raise AssertionError(
        "Dispatch plots can only be created with a valid color assignment for each analysis group. Go back to Step 2 and choose your aggregation settings."
    )

# Choose zone & date range for dispatch plot
# TODO: Allow for multiple zones in dispatch plot
# Create a dropdown widget
zones_path = pathlib.Path(case_path) / "summary" / "Zone"
all_zones = [d.name for d in zones_path.iterdir() if d.is_dir()]
zone_dropdown = widgets.Dropdown(
    options=all_zones,
    value=all_zones[0],  # Default selected value
    description="Select Zone:",
    disabled=False,
)

# Display dropdown in the notebook
print(f"Select your dispatch plot parameters.")
display(zone_dropdown)

year_dropdown = widgets.Dropdown(
    options=selected_modeled_years,
    value=selected_modeled_years[0],  # Default selected value
    description="Select Year:",
    disabled=False,
)
display(year_dropdown)

# Create a description
description = widgets.Label(value="You may choose one dispatch window (DW) to plot.")
display(description)
# Show dropdown of representative dispatch days to plot
day_dropdown = widgets.Dropdown(
    options=all_dispatch_windows,
    value=all_dispatch_windows[0],  # Default selected value
    description="Select DW:",
    disabled=False,
)
display(day_dropdown)

# %%
# TODO: Add aggregation of RESOLVE zones (e.g., all CAISO zones)
if "rv_groupings" not in locals():
    raise AssertionError(
        "Dispatch plots cannot be generated without a valid resource aggregation. Go back to Step 2 and choose your aggregation settings."
    )
if color_settings_df is None:
    raise AssertionError(
        "Dispatch plots can only be created with a valid color assignment for each analysis group. Go back to Step 2 and choose your aggregation settings."
    )

# Save selected parameters
plotting_zone = zone_dropdown.value
plotting_year = int(year_dropdown.value)
plotting_dates = [day_dropdown.value]
title_note = f"Dispatch for {plotting_zone} in Model Year {plotting_year} and Dispatch Window {plotting_dates[0]}"

# Build LRB dataframes
power_provided, imports, load = hourly_RV.get_load_resource_balance(
    zone=plotting_zone, model_years=[plotting_year], date_list=plotting_dates
)

# Build dispatch plot
dispatch_fig = hourly_RV.create_chrono_dispatch_plot(
    power_provided, imports, load, plotting_dates, ordered_analysis_groups, title_note
)

# Default image size is 14x8, but it can be updated here:
dispatch_fig.update_layout(
    width=1400,  # pixels
    height=800,  # pixels
    margin=dict(l=110, r=110, t=80, b=80),  # pixels
)

# Display image
dispatch_fig.show()

# Save dispatch plot as html file
dispatch_plots_path = pathlib.Path(f"{dest_path}/Dispatch Plots")
if not dispatch_plots_path.exists():
    dispatch_plots_path.mkdir(exist_ok=True)
dispatch_fig.write_html(f"{dispatch_plots_path}/{plotting_zone}_{day_dropdown.value}.html")
