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
# # Profile Adapter Demo
#
# This notebook demonstrates how to use the `profile_adapter.py` module to extract and transform EV (Electric Vehicle) charging profiles from the E3 data library catalog into RESOLVE-compatible CSV format.
#
# ## Overview
#
# The profile adapter provides utilities to:
# - Filter and retrieve EV profile data from data_utils tables
# - Handle multiple filter dimensions (model_year, region_name, scenario_name, vehicle type, etc.)
# - Export profiles in RESOLVE-compatible format (timestamp + value columns)
# - Automatically group and split data into separate CSV files
#
# ## Key Functions
#
# 1. **`get_choices()`** - Identify unique values in low-cardinality columns
# 2. **`get_ev_profile()`** - Retrieve filtered profile data with flexible filter syntax
# 3. **`put_ev_profile()`** - Export DataFrame to RESOLVE CSV format
# 4. **`pull_ev_profiles_to_local()`** - Orchestrate batch extraction and grouping
# 5. **`get_filterable_columns()`** - Identify available filter dimensions
#

# %% [markdown]
# ## Setup and Imports
#
# First, let's import the necessary modules and authenticate with AWS to access the data library.

# %%
import sys
from pathlib import Path

import data_utils as du
import pandas as pd

# Add the data-utils directory to path so we can import profile_adapter
sys.path.insert(0, str(Path.cwd()))

import profile_adapter as pa

# Authenticate with AWS
du.aws_sign_in()

# %% [markdown]
# ## Connect to the Data Catalog
#
# We'll connect to the E3 data library catalog which contains various EV charging profile tables.

# %%
# Connect to the library catalog (production data)
# Use du.Catalog.testing() for testing/development
catalog = du.Catalog.library()

# List all available tables
available_tables = catalog.list_tables()
print(f"Total tables available: {len(available_tables)}")
print("\nSample tables:")
for table in available_tables[:10]:
    print(f"  - {table}")

# %% [markdown]
# ## Explore the EV Profile Table
#
# Let's examine the structure of the EV load shape table to understand what data is available.

# %%
# Get the EV load shape table
table_name = "evlst_library_regional"
table = catalog.get_table(table_name)

print("Table columns:")
print(table.columns)

# %%
# Let's peek at a small sample of the data
sample_df = table.to_pandas(filter=(table.model_year == 2040) & (table.region_name == "CAISO"))
print(f"\nSample data shape: {sample_df.shape}")
sample_df.head(10)

# %% [markdown]
# ## Use Case 1: Understanding Data Dimensions with `get_choices()`
#
# The `get_choices()` function helps us understand what filter options are available by showing unique values in low-cardinality columns (< 10 unique values).
#
# * TODO: connect get_choices to populate UI

# %%
# Get choices from our sample data
choices = pa.get_choices(sample_df)

print("Available filter choices:")
for column, values in choices.items():
    print(f"\n{column}:")
    print(f"  {values}")

# %% [markdown]
# ## Use Case 2: Flexible Filtering with `get_ev_profile()`
#
# The `get_ev_profile()` function provides powerful filtering capabilities:
# - **Equality filters**: `{'region_name': 'CAISO'}`
# - **Range filters**: `{'start_model_year': 2020, 'end_model_year': 2040}`
# - **Combined filters**: Multiple conditions with AND logic
#
# ### Example 2a: Simple Equality Filter

# %%
# Filter for a specific model_year and region_name
filter_config = {
    "model_year": 2040,
    "region_name": "CAISO",
    "scenario_name": "managed",
    "vehicle_type": "ldvs",
    "charger_type": "home_l2",
}

df_2030 = pa.get_ev_profile(catalog, table_name, filter_config)
print(f"Retrieved {len(df_2030)} rows")
print(f"Columns: {df_2030.columns.tolist()}")
df_2030.head()

# %% [markdown]
# ### Example 2b: Range Filters
#
# Use `start_` and `end_` prefixes for range queries.

# %%
# Filter for a range of years
filter_config_range = {
    "start_model_year": 2020,
    "end_model_year": 2060,
    "region_name": "CAISO",
    "vehicle_type": "ldvs",
    "charger_type": "home_l2",
}

df_range = pa.get_ev_profile(catalog, table_name, filter_config_range)

# Check what years we actually got
years_retrieved = df_range["model_year"].unique()
print(f"Years in filtered data: {sorted(years_retrieved)}")
print(f"Total rows: {len(df_range)}")

# Check what scenarios we got
scenarios = df_range["scenario_name"].unique()
print(f"Scenarios: {scenarios}")

# %% [markdown]
# ## Use Case 3: Identifying Filterable Columns
#
# Before extracting profiles, we need to know which columns can be used for filtering. The `get_filterable_columns()` function identifies columns that aren't timestamp or value columns.

# %%
# Describe target table structure
tbl_cfg = {
    "table_name": "evlst_library_regional",
    "timestamp_col": "timestamp",
    "value_col": "kw_per_vehicle",
    "profile_name_stem": "ev_profile",
}

# Identify filterable columns
col_filt_d = pa.get_filterable_columns(tbl_cfg, catalog)
tbl_cfg.update(col_filt_d)

print(f"Filterable columns: {tbl_cfg['filterable_columns']}")

# %% [markdown]
# ## Use Case 4: Exporting a Single Profile with `put_ev_profile()`
#
# The `put_ev_profile()` function exports a DataFrame to CSV in RESOLVE format:
# - Renames timestamp column to "timestamp"
# - Prefixes value column with filename for identification
# - Automatically drops constant columns (single unique value)
# - Warns if extra variable columns exist (potential multi-index)

# %%
# Create a temporary output directory
output_dir = Path.cwd() / "temp_profiles"
output_dir.mkdir(exist_ok=True)

print(f"Output directory: {output_dir}")

# %%
# Export a single profile
# First, get data for one specific combination
single_profile_df = pa.get_ev_profile(
    catalog,
    table_name,
    {
        "model_year": 2040,
        "region_name": "CAISO",
        "scenario_name": "managed",
        "vehicle_type": "ldvs",
        "charger_type": "home_l2",
    },
)

pa.put_ev_profile(
    single_profile_df,
    folder=output_dir,
    filename="ev_2040_caiso_managed_ldvs_home_l2.csv",
    timestamp_col="timestamp",
    value_col="kw_per_vehicle",
)

# Read back the exported file to verify
exported_df = pd.read_csv(output_dir / "ev_2040_caiso_managed_ldvs_home_l2.csv")
print(f"\nExported file columns: {exported_df.columns.tolist()}")
print(f"Exported file shape: {exported_df.shape}")
exported_df.head()

# %% [markdown]
# ### Understanding Column Handling
#
# Notice how the function handles columns:
# - **Constant columns** (model_year, region_name, scenario_name, etc.) are dropped from dataframe (and appear in file name and value column name)
# - **timestamp** is renamed to "timestamp"
# - **kw_per_vehicle** is renamed with filename prefix for identification

# %%
# Check what columns were in the original DataFrame
print("Original columns:", single_profile_df.columns.tolist())
print("\nColumns with unique values:")
for col in single_profile_df.columns:
    n_unique = single_profile_df[col].nunique()
    print(f"  {col}: {n_unique} unique values")

# %% [markdown]
# ## Use Case 5: Batch Export with Automatic Grouping
#
# The `pull_ev_profiles_to_local()` function is the main orchestration function that:
# 1. Uses default table config for EVs
# 2. Retrieves filtered data from the catalog
# 3. Automatically groups by all filterable columns
# 4. Exports one CSV per unique group combination
#
# This is powerful when you want to extract multiple profiles at once (e.g., multiple years and scenarios).
#
# ### Example 5a: Extract Multiple Years for One scenario_name

# %%
# Configure filters - this will get multiple years
filter_cfg_multi_year = {
    "start_model_year": 2020,
    "end_model_year": 2040,
    "region_name": "CAISO",
    "scenario_name": "managed",
    "vehicle_type": "ldvs",
    "charger_type": "home_l2",
}

# Pull profiles - will create separate CSV for each model_year
pa.pull_ev_profiles_to_local(catalog=catalog, profiles_directory=output_dir, filter_cfg=filter_cfg_multi_year)

# %%
# Check what files were created
csv_files = sorted(output_dir.glob("ev_profile_*.csv"))
print(f"Created {len(csv_files)} profile files:\n")
for f in csv_files:
    file_size = f.stat().st_size / 1024  # KB
    print(f"  {f.name} ({file_size:.1f} KB)")

# %% [markdown]
# ### Example 5b: Extract Multiple Scenarios and Years
#
# By leaving out the scenario_name filter, we'll get all available scenarios, resulting in separate CSVs for each (model_year, scenario_name) combination.

# %%
# Configure filters - now without scenario_name filter to get all scenarios
filter_cfg_multi_scenario = {
    "start_model_year": 2030,
    "end_model_year": 2040,
    "region_name": "CAISO",
    "vehicle_type": "ldvs",
    "charger_type": "home_l2",
    # Note: 'scenario_name' is not specified, so all scenarios will be included
}

# Create a separate output directory for this example
output_dir_multi = Path.cwd() / "temp_profiles_multi_scenario"
output_dir_multi.mkdir(exist_ok=True)

pa.pull_ev_profiles_to_local(catalog=catalog, profiles_directory=output_dir_multi, filter_cfg=filter_cfg_multi_scenario)

# %%
# Check the results
csv_files_multi = sorted(output_dir_multi.glob("ev_profile_*.csv"))
print(f"Created {len(csv_files_multi)} profile files:\n")
for f in csv_files_multi:
    print(f"  {f.name}")

# %% [markdown]
# ### Understanding the Grouping Logic
#
# The function groups by all filterable columns that have variation in the data. Let's examine one of the exported files to understand the grouping:

# %%
# Read one of the multi-scenario_name files
if csv_files_multi:
    sample_file = csv_files_multi[0]
    sample_data = pd.read_csv(sample_file)

    print(f"File: {sample_file.name}")
    print(f"Shape: {sample_data.shape}")
    print(f"Columns: {sample_data.columns.tolist()}")
    print("\nFirst few rows:")
    display(sample_data.head())

    # Parse filename to understand grouping
    filename_parts = sample_file.stem.split("_")
    print(f"\nFilename components: {filename_parts}")

# %% [markdown]
# ## Use Case 6: Verifying Profile Quality
#
# After extracting profiles, it's good practice to verify data quality. Let's create some quick quality checks.

# %%
import matplotlib.pyplot as plt

# Read a couple of profiles and visualize
if len(csv_files) >= 2:
    # Read two different years
    df1 = pd.read_csv(csv_files[0])
    df2 = pd.read_csv(csv_files[-1])

    # Convert timestamp to datetime
    df1["timestamp"] = pd.to_datetime(df1["timestamp"])
    df2["timestamp"] = pd.to_datetime(df2["timestamp"])

    # Get value column names (they should have the filename prefix)
    val_col1 = [c for c in df1.columns if c != "timestamp"][0]
    val_col2 = [c for c in df2.columns if c != "timestamp"][0]

    # Plot first week of data
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))

    # Plot first profile
    week1 = df1.head(168)  # First week (24*7)
    ax1.plot(week1["timestamp"], week1[val_col1], linewidth=0.8)
    ax1.set_title(f"Profile: {csv_files[0].name} (First Week)")
    ax1.set_ylabel("kW per Vehicle")
    ax1.grid(True, alpha=0.3)

    # Plot second profile
    week2 = df2.head(168)
    ax2.plot(week2["timestamp"], week2[val_col2], linewidth=0.8, color="orange")
    ax2.set_title(f"Profile: {csv_files[-1].name} (First Week)")
    ax2.set_ylabel("kW per Vehicle")
    ax2.set_xlabel("Timestamp")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.show()

    print(f"\nProfile 1 statistics:")
    print(df1[val_col1].describe())
    print(f"\nProfile 2 statistics:")
    print(df2[val_col2].describe())

# %% [markdown]
# ## Use Case 7: Advanced - Custom Filter Combinations
#
# You can create complex filter combinations by mixing equality and range filters.

# %%
# Example: Get all "managed" scenarios for years 2025-2035, all vehicle types
filter_cfg_advanced = {
    "start_model_year": 2025,
    "end_model_year": 2035,
    "region_name": "CAISO",
    "scenario_name": "managed",  # Only managed charging
    # vehicle_type: not specified - will get all vehicle types
    "charger_type": "home_l2",
}

# First, let's see what we would get
test_df = pa.get_ev_profile(catalog, table_name, filter_cfg_advanced)
choices = pa.get_choices(test_df)

print("Data dimensions that will be grouped:")
for col, vals in choices.items():
    if col not in ["timestamp", "kw_per_vehicle"]:
        print(f"  {col}: {vals}")

print(f"\nThis will create {len(test_df['model_year'].unique()) * len(test_df['vehicle_type'].unique())} CSV files")

# %% [markdown]
# ## Use Case 8: Error Handling
#
# The profile adapter includes robust error handling. Let's demonstrate some common error scenarios and how they're handled.
#
# ### Invalid Column Names

# %%
# Try to filter on a non-existent column
try:
    bad_filter = {"invalid_column": "some_value"}
    pa.get_ev_profile(catalog, table_name, bad_filter)
except AttributeError as e:
    print(f"✓ Caught expected error: {e}")

# %% [markdown]
# ### Missing Required Columns in Export

# %%
# Try to export with wrong column names
try:
    test_df = pd.DataFrame({"col1": [1, 2], "col2": [3, 4]})
    pa.put_ev_profile(test_df, folder=output_dir, filename="test.csv", timestamp_col="nonexistent", value_col="col2")
except AssertionError as e:
    print(f"✓ Caught expected error: {e}")

# %% [markdown]
# ## Summary and Best Practices
#
# ### Key Takeaways
#
# 1. **Use range filters** (`start_`, `end_` prefixes) for flexible model_year ranges (or other numeric columns that may exist)
# 2. **Understand grouping behavior** - one CSV per unique combination of filterable columns
# 3. **Check your filters** - use `get_choices()` to validate available options. This may support UI menuing in future.
# 4. **Verify exports** - spot-check a few files to ensure correct data
#
# ### Common Workflows
#
# **Workflow 1: Extract single profile**
# ```python
# # 1. Configure table
# tbl_cfg = {...}
# tbl_cfg = pa.get_filterable_columns(tbl_cfg, catalog)
#
# # 2. Get specific profile
# table_name = 'evlst_library_regional'
# df = pa.get_ev_profile(catalog, table_name, {'model_year': 2040, 'region_name': 'CAISO', ...})
#
# # 3. Export
# pa.put_ev_profile(df, output_dir, 'profile.csv', 'timestamp', 'kw_per_vehicle')
# ```
#
# **Workflow 2: Batch extract with grouping**
# ```python
# # 1. Define broad filters
# filter_cfg = {'start_model_year': 2020, 'end_model_year': 2050, 'region_name': 'CAISO'}
#
# # 2. Extract all - automatically creates one file per group
# pa.pull_ev_profiles_to_local(catalog, output_dir, filter_cfg)
# ```
#
# ### Performance Tips
#
# - Use specific filters to reduce data retrieved
# - For large date ranges, consider extracting in batches

# %% [markdown]
# ## Cleanup
#
# Let's remove the temporary files we created during this demo.

# %%
import shutil

# Clean up temporary directories
for temp_dir in [output_dir, output_dir_multi]:
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
        print(f"Removed: {temp_dir}")

# %% [markdown]
# ## Next Steps
#
# - Explore other tables in the catalog
# - Adapt the profile_adapter functions for other data types
# - Integrate extracted profiles into RESOLVE modeling workflows
# - Check the unit tests in `tests/test_profile_adapter.py` for more usage examples
#
# For questions or issues, refer to the module docstrings or the comprehensive test suite.
