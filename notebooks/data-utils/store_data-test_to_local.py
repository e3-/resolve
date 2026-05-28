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
# # Transcribing the RESOLVE data-test profiles to data-utils
# Here we are using a local catalog which writes data to our local disk. Note the `pyiceberg.db` file and `warehouse` directory, this is where the data ends up getting stored!

# %%
import os

import data_utils as du

du.set_local_only()

TABLE_NAME = "test_profile_table"
catalog = du.Catalog.new_local(os.getcwd())
catalog.drop_table(TABLE_NAME, needs_to_exist=False)  # TODO: remove when implemented
catalog

# %% vscode={"languageId": "shellscript"}
from typing import Union
from resolve.system.electric.resources import ResourceType

# ResourceType includes
# GENERIC = "Generic"
# THERMAL = "Thermal"
# THERMAL_UC = "Thermal Unit Commitment"
# HYDRO = "Hydro"
# SHED = "Shed DR"
# SHIFT = "Shift DR"
# STORAGE = "Storage"
# VARIABLE = "Variable"
# SOLAR = "Solar"
# WIND = "Wind"
# HYBRID_STORAGE = "Hybrid Storage"
# HYBRID_VARIABLE = "Hybrid Variable"
# HYBRID_SOLAR = "Hybrid Solar"
# HYBRID_WIND = "Hybrid Wind"

NA_TOKEN = None

# Create mapping dictionary from file names to resource types
# Note: we don't have history and resource types for all files. The files may not be Resources per se.
file_resource_mapping = {
    "AAEE.csv": NA_TOKEN,
    "AAFS.csv": NA_TOKEN,
    "CAISO_Hydro_budget.csv": "Hydro",
    "CAISO_Hydro_pmax.csv": "Hydro",
    "CAISO_Hydro_pmin.csv": "Hydro",
    "CAISO_Solar.csv": "Solar",
    "CAISO_Wind.csv": "Wind",
    "CAISO-agg.csv": NA_TOKEN,
    "Customer_PV.csv": "Solar",
    "erm_solar_multiplier.csv": "Solar",
    "erm_target_mw.csv": NA_TOKEN,
    "erm_wind_multiplier.csv": "Wind",
    "Existing_Solar_reg_up.csv": "Solar",
    "gas_CCGT_FOR_profile.csv": "Thermal",
    "Heating_Demand.csv": NA_TOKEN,
    "In_State_Wind.csv": "Wind",
    "Riverside_Solar.csv": "Solar",
    "ShedDR_group_annual_budget.csv": "Shed DR",
    "upward_reg_mw.csv": NA_TOKEN,
    "Wyoming_Wind.csv": "Wind",
}


def map_resource_type(component_name: str) -> Union[ResourceType, None]:
    """Map component_name (filename) to proper resource_type or None if not found."""

    resource_type = file_resource_mapping.get(component_name)
    if resource_type is NA_TOKEN:
        resource_type = None
    return resource_type


# %% [markdown]
# # Schema
# ## Table with schema suitable for RESOLVE profiles ingested from CSV
#
# To create a table within the database, we need to specify what columns and data types the table should expect, its "Schema". Note that creating a table is not the same as writing data to the table.
#
# **Importantly: Creating a table only needs to happen once, as a "setup" process. Once the table is created, you should not rerun any table creation commands on the catalog**
#
#

# %%
import pandas as pd
import pyarrow as pa

# we define the schema using a dictionary of {col : type}
schema = pa.schema(
    {
        "timestamp": pa.string(),  # could be pa.timestamp() however the test data has inconsistent formatting. Using string to limit scope creep.
        "zone": pa.string(),
        "component_name": pa.string(),
        "resource_type": pa.string(),  # OR
        "column": pa.string(),
        "value": pa.float64(),
    }
)
# For a table written during RESOLVE execution, schema could include LValues such as:
#    _COMPONENT_CLASS = TxPath
#    _COMPONENT_NAME = "TxPath"
# in place of resource_type and component_name.

catalog.create_table(TABLE_NAME, schema=schema, partitioning_columns=["zone", "resource_type"])

table = catalog.get_table(TABLE_NAME)


# %%
def retrieve_data_by_conditions(zone, component_name, t_min=None, t_max=None):

    filt = (table.zone == zone) & (table.component_name == component_name)
    # TODO: manage resource_type==None to use clause  filt &= (table.resource_type is resource_type)
    time_filt = None
    if t_min is not None:
        time_filt = table.timestamp >= t_min
    if t_max is not None:
        time_filt &= table.timestamp <= t_max
    # TODO: min and max timestamp parsing to be robust to different formats. Currently the compare is string-based.
    if time_filt is None:
        pull_df = table.to_pandas(filter=filt)
    else:
        pull_df = table.to_pandas(filter=filt & time_filt)
    return filt, time_filt, pull_df


# %% [markdown]
# # Baseline pytest on data-test folder
# Before running this test, confirm the git controlled CSV file in data-test are un-modified.
# The pytest result is a baseline for the unmodified profile data.

# %%
if False:
    TEST_PATH = os.path.abspath(os.path.join(os.getcwd(), "../../tests/resolve/test_run_opt.py"))
    # # !pytest --collect-only $TEST_PATH -k "test_run_opt_main"
    # !pytest $TEST_PATH -k "test_run_opt_main"  --disable-warnings

# %% [markdown]
# # Ingest all CSVs from `data-test` folder
#
# Report on naming and time format inconsistencies.
#
# Append or upsert into one table that can be filtered by Zone etc.

# %%
# Loop through CSV files in data/data-test
profiles_directory = os.path.abspath(os.path.join(os.getcwd(), "../../data-test/profiles"))

for component_name in os.listdir(profiles_directory):
    if component_name.endswith(".csv"):
        filepath = os.path.join(profiles_directory, component_name)

        try:
            df = pd.read_csv(filepath, dtype={0: str, 1: float})
            colnames = df.columns.tolist()
            time_col = colnames[0]
            value_col = colnames[1]
        except Exception as e:
            print(f"Cannot read {component_name} : {e}")
            continue

        # Melt the dataframe to have columns: timestamp, column, value
        try:
            UNIQUE_COL_NAME = "new_values_for_melting_12345"  # avoid collision with any existing column names
            df_melted = df.melt(id_vars=[time_col], var_name="column", value_name=UNIQUE_COL_NAME)
        except Exception as e:
            print(f"Error melting dataframe {component_name}: {e}")
            continue

        # Add zone and component_name columns
        df_melted["zone"] = "data-test"
        df_melted["component_name"] = component_name
        resource_type = map_resource_type(component_name)
        df_melted["resource_type"] = resource_type

        # Rename new_values to value
        df_melted = df_melted.rename(columns={time_col: "timestamp", UNIQUE_COL_NAME: "value"})

        t_min = df_melted.timestamp.min()
        t_max = df_melted.timestamp.max()

        # Calculate filters
        filt, time_filt, _ = retrieve_data_by_conditions("data-test", component_name, t_min, t_max)

        if True:
            # Upsert to test_profile_table
            table.upsert(df_melted, replace_where=filt & time_filt)
            pull_df = table.to_pandas(filter=filt & time_filt)
            _, _, pull_df = retrieve_data_by_conditions("data-test", component_name, t_min, t_max)
            assert pull_df.shape == df_melted.shape
            action_msg = "Upsert"
        else:
            # Append to test_profile_table
            table.append(df_melted)
            action_msg = "Append"

        print(
            f"{action_msg} {component_name} | {resource_type=} | columns ({time_col}, {value_col}) | index[:3]= {df.iloc[:3,0].tolist()}"
        )


# %%
# Check optional time bounds works
filt, time_filt, pull_df = retrieve_data_by_conditions("data-test", component_name)
# type(filt)

# %% [markdown]
# ## inspect the table
#
# Column names seens in files
#
# Note ' value' and 'value' are distinct columns seen in the wild.

# %%
set(table.to_pandas()["column"])

# %% [markdown]
# column naming by input file

# %%
display(table.to_pandas()[["component_name", "column"]].drop_duplicates())


# %% [markdown]
# Successfully constructed the table

# %%
table.to_pandas().round(3)

# %% [markdown]
# Random sample shows a variety of rows

# %%
table.to_pandas().sample(25).round(3)

# %% [markdown]
# # Filtering

# %% [markdown]
# Basic filtering can be done directly on data-utils columns

# %%
# we can also optimize the amount of data in memory by pre-filtering the data
df_filtered = (
    table.to_pandas(
        filter=(
            table.zone.isin(
                [
                    "data-test",
                ]
            )
        )
        & (table.value > 0)
    )
    .sample(10)
    .round(2)
)
df_filtered

# %%
# TODO: filter such as to find rows with file value that contains "wind" (case insensitive)

# Can we access PyIceberg or PyArrow DSL to implement that filtering without loading the whole table into memory?
# from pyiceberg.expressions import like
type(table.component_name)
# table.scan(row_filter=like(table.component_name, "%wind%")) #.to_pandas()["component_name"].unique()

# %%
table

# %% [markdown]
# # Pull from database, Write CSV files back to `data-test` folder
#
# Reader may use Git to inspect small changes in the CSV files
#

# %%
OUTPUT_FOLDER = os.path.abspath(os.path.join(os.getcwd(), "../../data-test/profiles"))
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
OUTPUT_FOLDER

# %%
import os
import data_utils as du

du.set_local_only()

TABLE_NAME = "test_profile_table"
catalog = du.Catalog.new_local(os.getcwd())
catalog
table = catalog.get_table(TABLE_NAME)


# %%
# Find CSV files from database
files = table.to_pandas().component_name.unique()
files

# %%
import math

for component_name in files:
    # Raw retrieval using known table schema
    df_file_0 = table.to_pandas(filter=(table.component_name == component_name))
    # Beginning to build an interface for retrieval
    _, _, df_file = retrieve_data_by_conditions("data-test", component_name)
    # Checks
    delta_shape = df_file_0.compare(df_file).shape
    # Restore to original CSV format that may have been non-standard
    df_pivot = df_file.pivot(index="timestamp", columns="column", values="value").sort_index().reset_index()
    # Store to CSV
    output_path = os.path.join(OUTPUT_FOLDER, component_name)
    df_pivot.to_csv(output_path, index=False)
    print(
        f"Wrote {output_path} with shape {df_pivot.shape}. Number of differences on save/load: {math.prod(delta_shape)}"
    )

# %% [markdown]
# ## Confirm that test profiles CSV files were written to disk

# %%
# Report CSV files that we have recreated
os.listdir(OUTPUT_FOLDER)

# %%
# Confirms data read/write did not affect file list
assert set(os.listdir(OUTPUT_FOLDER)) == set(files), "Mismatch between expected and recreated files"

# %% [markdown]
# ## Run pytest against profiles from local data-lake instance

# %% [markdown]
# The pytest "test_run_opt_main" uses data-test/profile data.
# Passing tests indicate the data-lake success in load/save of test profile data.

# %%
TEST_PATH = os.path.abspath(os.path.join(os.getcwd(), "../../tests/resolve/test_run_opt.py"))
# # !pytest --collect-only $TEST_PATH -k "test_run_opt_main"
# !pytest $TEST_PATH -k "test_run_opt_main"  --disable-warnings

# %% [markdown]
# These pytest results should match earlier results that read original profile data.

# %%
