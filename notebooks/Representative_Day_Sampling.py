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
# # Import packages
# %%
import sys

from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO")

from new_modeling_toolkit.core.utils.util import DirStructure
from new_modeling_toolkit.resolve.day_sampling import DaySamplingSystem

# %% [markdown]
# -----------------------

# %% [markdown]
# # Overal Rep Day Selection Workflow
#
# ![img.svg](img/daysample_workflow.svg)

# %% [markdown]
# # <font color=#034E6E>Set up Input System needed for Rep Day Selection</font>

# %% [markdown]
# ### <font color=#AF2200>**First specify the case and system you want to operate on.**</font>

# %%
# Specify data folder in which System and case settings are saved

data_folder = "data"
dir_str = DirStructure(data_folder=data_folder)
DaySampSys = DaySamplingSystem(dir_str)

DaySampSys.input_selection()

# %% [markdown]
# ### <font color=#AF2200>**Construct the system and load profiles.**</font>

# %%
# Load system and components data

DaySampSys.load_prep_data()

# %%
# Load initial weights assigned to specific resources

DaySampSys.load_resource_weights()

# %%
# Load and prepare profiles input

DaySampSys.load_profiles_input()

# %% [markdown]
# ### <font color=#AF2200>**Remove correlated profiles to reduce cluster solution space.**</font>
#
# This is a pre-processing step aimed at **reducing cluster problem size** by only including profiles that are more distinct and informative to day sampling process.
#
# ![img.svg](img/daysample_input_profile_check.svg)
#
#
# Note that the choice of threshold, whether more stringent or relaxed, directly affects the number of profiles retained for clustering.
# > For example, solar resources often exhibit similar diurnal generation patterns, leading to high correlation among profiles. In such cases, using a higher threshold can be appropriate. As a reference, the CPUC IRP applies a 90% threshold for both wind and solar.

# %%
# Step 1. Calculate Correlation Matrix

DaySampSys.check_correlation()

# %%
# Step 2 + 3: Design Threshold and Remove Redundant Features

DaySampSys.remove_redundant_component()

# %% [markdown]
# ### <font color=#AF2200>**Other clustering parameter specification.**</font>

# %%
# Specify clustering parameters

DaySampSys.design_clustering_param()

# %% [markdown]
# ### <font color=#AF2200>**Grid searching for weights that “optimize” cluster performance.**</font>
#
# This step implemeted a grid searching process to **automate search from a range of weights** and find a few set of clusters that’s identified as “optimal” in the sense that it minimizes clustering error.
#
# >It is intended to **zoom into top X set of weights** that could bring generic error metrics down, instead of finding the one “best” sample day selection.
#
# ❗ After specifying the range of weight, run the loop below to create different set of cluster results and visuals. You can use these charts as additional screening to closely evaluate the quality of reconstituted 8760 profiles. Some screening criteria include:
#
# ![img.svg](img/daysample_screening_criteria.svg)

# %%
# Specify range of weights for grid search

DaySampSys.set_grid_search_range()

# %% [markdown]
# #### <font color=#034E6E>**Actual Grid Search Loop**</font>
#
# Loop through grid search parameter combinations and generate clustering results + visuals
#

# %%
# Run grid search with range of weights

DaySampSys.run_grid_search()

# %% [markdown]
# --------------------------

# %% [markdown]
# ## Optional: Force a Higher Weight for Extreme Days
#
# Representative period selection aims to find the best **"average" day** to summarize a much longer timeframe of data. However, sometimes we want to **_manually include extreme days_** to cover a broader range of challenging load and renewable patterns.
#
# <span style="color:#FFAF00;"><strong>In this section, you can specify a list of days you consider "challenging."</strong></span> The clustering algorithm will then be directed to assign the closest <span style="color:#FFAF00;"><strong>X number of days</strong></span> in the chronological periods to be represented by each challenging day.
#
# > <i>For example, suppose <span style="color:#034E6E;"><strong>"2016-02-02"</strong></span> is identified as a challenging day with high load and low renewable output, but it was not selected by the clusterer as a representative period. You can assign the closest <span style="color:#034E6E;"><strong>2 to 3 days</strong></span> (roughly 1-in-10 in a 20-year weather dataset) in the chronological periods to be represented by this challenging day. This way, you introduce more difficult scenarios into the RESOLVE simulations.</i>
#
# > <span style="color:#034E6E;"><strong>Tip:</strong></span> The number of days and how many closest days to assign is an <em>art</em> — it depends on how many challenging situations you want to include in your model.

# %% [markdown]
# #### Make sure you have already run the grid search above before this step
#
# ⚠️ You will still need to rely on the same Day Sampling System for this process.
#
# 👉 If you have determined the final set of weights, put in the lists above.
#
# > <u>To compare original chorno periods mapping before and after the process</u>, check out:
# > ```ruby
# > weights_combo = "OSW_0-LBW_0-wind_1.0-solar_1.0-hydro_1.0-load_1.0"
# > c = DaySampSys.clusters[weights_combo]
# > c.clustered_dates # for raw results
# > c.clustered_dates_force # for extreme version results
# > ```

# %%
DaySampSys.set_extreme_days_param()

# %%
DaySampSys.set_extreme_days_weights()

# %%
DaySampSys.force_extreme_days()

# %%
