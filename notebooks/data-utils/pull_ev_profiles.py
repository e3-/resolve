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
# # Pull EV Profiles
#
# This notebook is a workflow to retrieve EV Profiles and put them into your profiles directory.
#
# **Note that these profiles will likely need some additional post-processing to be used in your project.**
#
# ## EV Profiles Documentation
#
# [Methodology & Docs](https://ethreesf.sharepoint.com/:w:/s/Models/EYyglX0MO0xIuoYEWLIrOnUBc8iuxdfMjHC_f6AiaK9aBw?e=y6geJS)
#
# Enumerations shown based on data in Nov 2025
#
# ### Region Name:
#
# ![image.png](attachment:image.png)
#
# **Values:**
#
# - 'CAISO',
# - 'WECC-SW',
# - 'MISO',
# - 'WECC-PNW',
# - 'ERCOT',
# - 'Hawaii',
# - 'SPP',
# - 'PJM',
# - 'SERC',
# - 'NYISO',
# - 'ISONE',
# - 'WECC-RM'
#
# ### Model Year:
#
# Years are differentiated by assumptions on demographics (e.g. share of drivers with access to home and/or work chargers), vehicle characteristics (e.g. range), charger characteristics (e.g. average L2 charger power), and charging network size (e.g. number of public and workplace chargers per vehicle).
#
# **Values:**
#
# - 2025
# - 2040
#
# ### Vehicle type:
#
# We model 3 representative vehicle types: personal LDV, parcel van, and transit bus.
#
#
# **Values:**
#
# - 'transit_bus'
# - 'parcel_van'
# - 'ldvs'
#
# ### Scenario Name:
#
# Managed/Unmanaged – In unmanaged cases, vehicles are responsive to the average cost to charge in a location but are not sensitive to time varying costs to charge in a given location. Drivers will choose to avoid expensive public charging if they can wait to charge for a lower cost at home. They will not, however, response to time-of-use rates faced at home.
#
# In managed cases, customers are responsive to time-varying prices. Additionally, we model a VGI aggregator smoothing out rebound peaks and orchestrating charging during off-peak hours.
#
# **Values:**
#
# - 'managed'
# - 'unmanaged'
#
# ### Charger Type:
#
# What Kind of charger to pull, in most cases this should be 'all'
#
# **Values:**
# - 'all'
# - 'home_l1'
# - 'home_l2'
# - 'work_l2'
# - 'public_l2'
# - 'public_dcfc'
#

# %%
from pathlib import Path

import data_utils as du
import profile_adapter as pa

du.aws_sign_in()
catalog = du.Catalog.library()

# %%
# Configure filters - now without scenario_name filter to get all scenarios
filter_cfg_multi_scenario = {
    "start_model_year": 2030,
    "end_model_year": 2040,
    "region_name": "CAISO",
    "vehicle_type": "ldvs",
    "charger_type": "all",
    # Note: 'scenario_name' is not specified, so all scenario_names will be included
    # "scenario_name" : "managed"
}
# you can redirect this to your profiles directory.
output_dir_multi = Path.cwd() / "ev_profiles_data"
output_dir_multi.mkdir(exist_ok=True)

pa.pull_ev_profiles_to_local(catalog=catalog, profiles_directory=output_dir_multi, filter_cfg=filter_cfg_multi_scenario)

# %%
