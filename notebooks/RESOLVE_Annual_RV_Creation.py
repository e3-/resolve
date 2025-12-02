#!/usr/bin/env python
# coding: utf-8
# %% [markdown]
# # Export RESOLVE Annual Results to Excel Results Viewer Template
#
# <div class="alert alert-block alert-info">
#     ℹ️ <b>How does this script work?</b><br><br>
#     RESOLVE annual results consist of several CSV summary files. This script copies all of the CSV files of interest into a template Result Viewer workbook, recalculates and then spits out a case-specific Results Viewer to the same directory that holds the template.<br>
#
# Before running the code blocks below please make sure that the template RV Excel file is NOT OPEN!!!!
# </div>
# %%
import pathlib as Path

from ipyfilechooser import FileChooser
from IPython.display import display
from ipywidgets import Layout

from new_modeling_toolkit.resolve.annual_rv_export import AnnualResultsViewerExport

# %% [markdown]
# ## Step 1: Select filepaths for Excel RV Template and your RESOLVE case results directory

# %%
# Select RV Template path
rv_file = FileChooser(
    "..",
    title="<b>Select TEMPLATE Results Viewer:</b>",
    layout=Layout(width="800px"),
    filter_pattern="[!~$]*.xls*",
)
rv_file._show_dialog()
display(rv_file)

# Select RESOLVE Case Results directory
results_folder = FileChooser(
    "..",
    title="<b>Select RESOLVE case results folder:</b>",
    layout=Layout(width="800px"),
    show_only_dirs=True,
)
results_folder._show_dialog()
display(results_folder)

# %% [markdown]
# ## Step 2: Define the Template-expected names for certain policies, ELCC surfaces, and passthrough inputs.
#
# <div class="alert alert-block alert-info">
#     ℹ️ <b>Define name-specific worksheets</b><br><br>
#     Some of the expected worksheet names in your RV template could be dependent on the names of certain components within your system. For example, you could have multiple PRM policies, and the results for each of these ought to be distinguished within the RV workbook.<br>
#
# The widget below allows you to define the worksheet names actually used in your template for different policies, ELCC surfaces, and passthrough inputs. The name on the left is the name of the specific component within RESOLVE, and the text box on the right allows you define the specific sheet name that holds the information for that component in the Results Viewer.<br>
#
# If you do not want to export the results for a particular component, leave that text box blank.
# </div>

# %%
rv_path = Path.Path(rv_file.selected)
results_path = Path.Path(results_folder.selected)
cases_and_timestamps = [(results_path.parent.name, results_path.name)]  # TODO: Expand to multiple cases at once
rv = AnnualResultsViewerExport(rv_path, results_path)


# %%
# Get list of specific components
prm_policies = rv.get_name_specific_component_list("Policy/PlanningReserveMargin")
energy_policies = rv.get_name_specific_component_list("Policy/AnnualEnergyStandard")
emissions_policies = rv.get_name_specific_component_list("Policy/AnnualEmissionsPolicy")
elcc_surfaces = rv.get_name_specific_component_list("ELCCSurface")
erm_policies = rv.get_name_specific_component_list("Policy/EnergyReserveMargin")
passthrough_inputs = rv.get_passthrough_list()

# Prompt user to define sheet names
prm_names = rv.name_specific_sheets("PlanningReserveMargin", prm_policies)
aes_names = rv.name_specific_sheets("AnnualEnergyStandard", energy_policies)
aep_names = rv.name_specific_sheets("AnnualEmissionsPolicy", emissions_policies)
elcc_names = rv.name_specific_sheets("ELCCSurface", elcc_surfaces)
erm_names = rv.name_specific_sheets("EnergyReserveMargin", erm_policies)
passthrough_names = rv.name_specific_sheets("Passthrough", passthrough_inputs)


# %%
prm_mapping = rv.custom_sheet_name_mapping(prm_names, "Policy/PlanningReserveMargin")
aes_mapping = rv.custom_sheet_name_mapping(aes_names, "Policy/AnnualEnergyStandard")
aep_mapping = rv.custom_sheet_name_mapping(aep_names, "Policy/AnnualEmissionsPolicy")
erm_mapping = rv.custom_sheet_name_mapping(erm_names, "Policy/EnergyReserveMargin")
elcc_mapping = rv.custom_sheet_name_mapping(elcc_names, "ELCCSurface")
passthrough_mapping = rv.custom_passthrough_mapping(passthrough_names)


# %% [markdown]
# ## Step 3. If necessary, change any of these options for standard sheet mapping of annual results files. (Usually not required)

# %%
# Users can also edit this list of standard sheet mappings if any of the sheet names deviate from standards.
standard_sheet_names = rv.name_standard_sheets()

# %%
standard_sheet_mapping = rv.standard_sheet_mapping(standard_sheet_names)

# %% [markdown]
# ## Step 4: Generate your new Results Viewer and store it in the same directory as your Template.

# %%
sheet_mapping = (
    standard_sheet_mapping + prm_mapping + aes_mapping + aep_mapping + erm_mapping + elcc_mapping + passthrough_mapping
)
print("Review your full sheet mapping here before starting your RV creation.\n")
sheet_mapping

# %%
macro_enabled = True  # Set to True if your template is a .xlsm or .xlsb file with macros, False if .xlsx without macros
rv.generate_rv(cases_and_timestamps, sheet_mapping, macro_enabled)


# %%
