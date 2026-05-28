# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py
#     text_representation:
#       extension: .py
#       format_name: light
#       format_version: '1.5'
#       jupytext_version: 1.14.7
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---
# # RECAP Analytical Tool
#
# This dashboard is designed to assist RECAP 3.0 modelers to conduct basic QA/QC or inspection on:
# - RECAP Case Inputs
# - ELCC Statistics
# - Dispatch Results
#
# Modeler can use this dashbord to exucute efficient anlysis and answer frequently-asked questions on dispatch output.
#
# > Remember to <u>clear all cell outputs</u> each time after using the analytical tool such that large dataset and the chart outputs won't remain and clutter up your workspace. ♻️
# >
# > It's recommended to start fresh with a clean notebook each time to make your work more organized.
# + code_folding=[0]
# Import Packages
import sys

import ipywidgets as widgets
from loguru import logger

from kit.core.utils.util import DirStructure
from kit.recap.recap_analyzer import CaseComparison
from kit.recap.recap_analyzer import InputChecks
from kit.recap.recap_analyzer import ProfileChecker
from kit.recap.recap_analyzer import ResultsViewer

logger.remove()
logger.add(sys.stdout, level="WARNING")
# -


# # <font color=#034E6E>Case Input Checker</font>
#
# > Use this section to check and compare case inputs, including ***Resource Portfolio***, ***Load Components***, and various ***case settings***.


# ### <font color=#AF2200>Step 0. Specify Case Names and Load Case Inputs</font>

# <font color=#034E6E>**First load all case options in the `recap/settings` folder.**</font>
#
# > You will then need to select cases to compare from the two <font color=#EF3B03>**options**</font> below.

dir_str = DirStructure()
case_checker = InputChecks(dir_str)

# <font color=#008A37>**Option 1**</font><font color=#034E6E>: **Select from the dropdown for specific case input comparison.**</font>
# > You can compare multiple cases by press `ctrl` then click on case names in the dropdown list.

# + code_folding=[]
case_checker.case_selection()
# -

# <font color=#008A37>**Option 2**</font><font color=#034E6E>: **Load case list from local.**</font>
# > You can upload a list of case names in a csv file for comparison
# > <br>
# > <br>
# >❗ <font color='red'>**Note**</font>: <u>the csv file should have one column and one column only: `case name`.</u>

case_checker.case_selection_from_local()

# <font color=#034E6E>**Now load the selected cases.**</font>

# + code_folding=[]
case_checker.load_case_object()
# -

# ### <font color=#AF2200>Checker # 1. Compare Case Inputs</font>

# <div class="alert alert-block alert-info" markdown = 1>
#
# In this block, you can compare **input settings** for <u>multiple</u> cases, including:
#
# - Resource portfolio / Resource group
# - Load component scaling
# - case settings / scnearios
# </div>
#
# > You can download csv files and find them under `"analysis/Inputs checker/"` subfolder.

# + code_folding=[]
case_checker.create_case_comparison()
# -

# ### <font color=#AF2200>Checker # 2. Visualize Resource Portfolio(s)</font>

# <div class="alert alert-block alert-info" markdown = 1>
#
# In this block, you can visualize the resource portfolio modeled in each case.
# </div>

# <font color=#034E6E>**Load a customized `resource group` from local to map each resource to a specific group.**</font>
#
# > ❗ <font color='red'>**Note**</font>: <u>The csv file should have at least two columns: `resource` and `dispatch_group`.</u>
# > - *`resource` column should contain the full list of generating resources in the system.*
# > - *`dispatch_group` column is the mapping between **resource** and its **dispatch group**.*
#     |    |        |        |      |      |    |    |      |        |     |   |         |
#     | -------------------------------- |--------|--------|------|------|----|----|------|--------|-----|---|---------|
#     | **Finite list of dispatch group:**    |Thermal |Nuclear |Other |Solar |LBW |OSW |Hydro |Storage |LDES |DR |FlexLoad |
#

case_checker.upload_customized_resource_group()

case_checker.show_resource_portfolio()

# ### <font color=#AF2200>Checker # 3. <font color='grey'>*(Optional)*</font> Check Marginal Resource / ELCC surfaces</font>

# <div class="alert alert-block alert-info" markdown = 1>
#
# In this block, you can choose <u>one case</u> and checking **ELCC input**, if any. This include:
#
# - Marginal ELCC resource
# - Incremental / Decremental ELCC resources
# - ELCC Surface inputs
# </div>

# <font color=#034E6E>**Select a case.**</font>

# + code_folding=[]
ELCC_case = widgets.Dropdown(options=case_checker.case_to_compare)
ELCC_case
# -

# <font color=#034E6E>**Load ELCC inputs.**</font>

# + code_folding=[]
case_checker.show_ELCC_input(ELCC_case)
# -

# -------------------------------

# # <font color=#034E6E>NMT Input Profiles Checker</font>
#
# > Use this section to check the profile quality and view shapes of the data in `data/profiles` folder.

# ### <font color=#AF2200>Step 0. Aggregate input profiles</font>
#
# > ❗ <font color='red'>**Note**</font>: <u>Only **hourly** timeseries profiles will be aggregated here. Profiles in monthly / daily frequency like hydro budget data will be excluded in the checker here.</u>
#
# > ⚠️ **This process can take a relatively long time** depending on the size / quantity of profiles to be aggregated.

# +
dir_str = DirStructure()
ProjectProfiles = ProfileChecker(dir_str)

ProjectProfiles.get_agg_profile_input()
ProjectProfiles.agg_profile.head(5)
# -

# ### <font color=#AF2200>Get data summary</font>

#
# <div class="alert alert-block alert-info" markdown = 1>
#
# In this block, you can check some basic information about the profiles, including `Data Start`, `Data End`, `Cap Factor`, etc.
#
# You can also check the quality of profile by looking at `Missing Data Input?`, ` # of Consecutive Zeros`, etc
# </div>

ProjectProfiles.get_data_summary()

# <font color=#034E6E>**Check low quality data input when possible.**</font>

ProjectProfiles.print_low_quality_data()

# ### <font color=#AF2200>Profile visuals</font>

# <div class="alert alert-block alert-info" markdown = 1>
#
# In this block, you can look at the **raw shape** of each hourly timeseries profile.
#
# You can also check out the **month-hour shape** as a quick sense check.
# </div>
#
# ⚠️ It <u>takes time</u> to render the chart especially when the aggregated profile contains over several timeseries data input. It also correspondingly requires <u>memory</u> to display all the data.

ProjectProfiles.show_profile_shape()

# <font color=#034E6E>**Check data distribution of specific timeseries input.**</font>

ProjectProfiles.show_specific_ts_distribution()

# -------------------------------

# # <font color=#034E6E>Case Result Viewer</font>
#
# > Use this section to compare different metrics of several cases, including:
#     > - Tuned / untuned system reliability characterization;
#     > - System capacity short;
#     > - System portfolio ELCC and TRN;
#     > - System PRM results
#     > - ...
#
# > If you wish to deep dive into one specific case and understand the resource-load dynamics, go to <font color=#034E6E>**Individual Case Deep-Dive**</font> Section.

# ### <font color=#AF2200>Step 0. Select cases to compare</font>

# <font color=#034E6E>**First load all case options in the `reports/recap` folder.**</font>
#
# > You will then need to select cases to compare from the two <font color=#008A37>**options**</font> below.

dir_str = DirStructure()
cases_comp = CaseComparison(dir_str)

# <font color=#008A37>**Option 1**</font><font color=#034E6E>**: Select cases to compare in the dropdown list.**</font>
#
# > ❗ <font color='red'>**Note**</font>: <u>This option defaults to the ***latest*** run for selected cases.</u>
#
# <!-- <font color=#008A37>**Option 1**</font><font color=#034E6E>: **Select from the dropdown for specific case input comparison.**</font>
# > You can compare multiple cases by press `ctrl` then click on case names in the dropdown list. -->

cases_comp.case_selection()

# <font color=#008A37>**Option 2**</font><font color=#034E6E>**: Load a csv file from local to read in list of case names and run choices.**</font>
#
# > ❗ <font color='red'>**Note**</font>: <u>the csv file should have two columns and two columns only: `case name` and `run name`.</u>

cases_comp.case_selection_from_local()

# <font color=#034E6E>**Now Load all selected cases.**</font>
#
# > 👉 This section is for comparing metrics only, so defaul to **not** loading detailed dispatch results.

cases_comp.load_case_to_compare()

# ### <font color=#AF2200>Multiple case results comparison</font>

# <div class="alert alert-block alert-info" markdown = 1>
# In this block, you can compare metrics from multiple cases, including:
#
# - Tuned / Untuned system reliability metrics;
# - Total Resource Need and Portfolio ELCC;
# - ...
# </div>

comparison = cases_comp.compare_case_metrics()

# -------------------------------

# # <font color=#034E6E>Individual Case Deep-Dive</font>

# ### <font color=#AF2200>Step 0. Specify One Case Name and Load Specific Run Outputs</font>

# <font color=#034E6E markdown = 1>**Load case and run options and select.**</font>

# +
dir_str = DirStructure()
RECAP_RESULTS_DIR = dir_str.results_dir.joinpath("recap")

case_analysis = ResultsViewer(result_folder=RECAP_RESULTS_DIR)
case_analysis.case_selection()
# -

# <font color=#034E6E>**Load selected case results.**</font>
#
# > 💭 **Tip:** <u>You can toggle `load_disp_result` to be `False` to stop loading dispatch data for saving space / time.</u> However, you won't be able to check any dispatch-related analysis.

case_analysis.read_case_data(load_disp_result=True)


case_analysis.untuned_disp.loc[("MC_draw_1_0", "12-25-1983"), "duke_HVAC"]

print((case_analysis.untuned_disp["duke_HVAC"] > 0).sum())

# ### <font color=#AF2200>Deep Dive # 1. View System Reliability Metrics 🔎</font>

# <div class="alert alert-block alert-info" markdown = 1>
# In this section, you can characterize the reliability situation of a system by checking:
#
# - **Reliability Metrics** (LOLE, LOLH, LOLP, and EUE)
#     - LOLE...
#     - EUE...
#     - LOLH/LOLP...
# - **Total Resource Need (TRN) and portfolio ELCC**
#     - ...
#
# </div>

case_analysis.get_metrics_result()
display(case_analysis.metrics)

# ### <font color=#AF2200>Deep Dive # 2. View ELCC Results and Produce ELCC Curves 📉</font>

# <div class="alert alert-block alert-info" markdown = 1>
# In this section, you can check out the ELCC results for the case when possible.
#
# </div>

case_analysis.get_ELCC_results()
case_analysis.show_ELCC_results()

# ### <font color=#AF2200>Deep Dive # 3. Month-Hour Loss-of-Load Heat Map 🔥</font>

# <div class="alert alert-block alert-info" markdown = 1>
# In this section, you can :
#
# - ...
#
# </div>

case_analysis.show_heat_map()

# ### <font color=#AF2200>Deep Dive # 4. Outage Events Analysis 📊</font>

# <div class="alert alert-block alert-info" markdown = 1>
# In this section, you can :
#
# - ...
#
# </div>

case_analysis.show_lol_stats()

# ### <font color=#AF2200>Deep Dive # 5. LOL Day Daily EUE Pattern 〽️</font>

# <div class="alert alert-block alert-info" markdown = 1>
# In this section, you can :
#
# - ...
#
# </div>

case_analysis.show_lol_date_EUE()

# df = pd.read_parquet(r"Z:\DOE_CC_RECAP\kit\reports\recap\20231116_Duke_test_case_2030_optimized_flex_loads\2023-11-18 18-52-15\untuned_dispatch_results.gzip")
# df[df.duke_HVAC > 0]
case_analysis.untuned_disp[case_analysis.untuned_disp["duke_HVAC"] > 0]  # .index.get_level_values(

# ### <font color=#AF2200>Deep Dive # 6.  Dispatch Plot 🕛</font>

# <div class="alert alert-block alert-info" markdown = 1>
# In this section, you can :
#
# - ...
#
# </div>

# <font color=#034E6E>**Load the `resource portfolio` from local to categorize resource by dispatch group.**</font>
#
# > ❗ <font color='red'>**Note**</font>: <u>The csv file should have at least two columns: `resource` and `dispatch_group`.</u>
# > - *`resource` column should contain the full list of generating resources in the system.*
# > - *`dispatch_group` column is the mapping between **resource** and its **dispatch group**.*
#     |    |        |        |      |      |    |    |      |        |     |   |         |
#     | -------------------------------- |--------|--------|------|------|----|----|------|--------|-----|---|---------|
#     | **Finite list of dispatch group:**    |Thermal |Nuclear |Other |Solar |LBW |OSW |Hydro |Storage |LDES |DR |FlexLoad |
#

case_analysis.upload_resource_group()

# <font color=#034E6E>**Print a list of LOL-days in the selected system to guide which periods to zoom in for dispatch plot.**</font>
#
# > 💭 **Tip:** The LOL-day list is sorted by level of **unserved energy in the day**, from the highest to lowest day.

lol_days = case_analysis.show_lol_day_list()

lol_days

# <font color=#034E6E>**Now produce dispatch plots.**</font>

case_analysis.show_dispatch_days()

# ### <font color=#AF2200>Deep Dive # 7. <font color='grey'>*(Optional)*</font> Uncertainty Analysis </font>

# <div class="alert alert-block alert-info" markdown = 1>
# In this section, you can :
#
# - ...
#
# </div>

case_analysis.show_results_uncertainty()

# <font color=#034E6E>**Show tuned LOLE / EUE with incremental perfect capacity.**</font>
#
# > ❗ <font color='red'>**Note**</font>: <u>This only applies to ***tuned*** system.</u>

case_analysis.draw_tuned_PCAP()
