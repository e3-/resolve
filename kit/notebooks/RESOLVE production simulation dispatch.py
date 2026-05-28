# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.15.1
#   kernelspec:
#     display_name: new-modeling-toolkit-dev
#     language: python
#     name: python3
# ---
# %% [markdown]
# ## Import Packages
# %%
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
from plotly.subplots import make_subplots


# %% [markdown]
# ## Create functions for getting dataframes

# %% [markdown]
# # Dispatch plots for RESOLVE 8760 hour simulation


# %%
def get_resource_dispatch_summary(directory, case_folder, case):
    # directory = os.path.dirname(os.getcwd())
    # directory = r"C:\Users\BMahoney\Energy and Environmental Economics, Inc\NY PATHWAYS and NMT 2023+ - Documents\RESOLVE NMT"
    filepath = os.path.join(
        directory, "reports\\resolve\\" + case_folder + "\\" + case + "\\results_summary\\resource_dispatch_summary.csv"
    )
    resource_dispatch_summary = pd.read_csv(filepath)

    # convert Model_Year to datetime
    resource_dispatch_summary["Model Year"] = pd.to_datetime(resource_dispatch_summary["Model Year"]).apply(
        lambda x: x.year
    )
    return resource_dispatch_summary


def get_power_provided_df(resource_dispatch_summary, rep_periods):
    if not isinstance(rep_periods, list):
        rep_periods = [rep_periods]
    power_provided_df = resource_dispatch_summary.loc[
        resource_dispatch_summary.Rep_Period.isin(rep_periods),
        ["Model Year", "Rep_Period", "Hour", "Zone", "Resource", "Provide Power (MW)"],
    ]

    # change hours to hours in list of rep_periods provided
    day = 0
    for rep_period in rep_periods:
        power_provided_df.loc[power_provided_df.Rep_Period == rep_period, "DAY"] = day
        day += 1
    power_provided_df["Hour"] = power_provided_df["Hour"] + (power_provided_df["DAY"] * 24)
    power_provided_df["Hour"] = power_provided_df["Hour"].apply(lambda x: int(x))

    return power_provided_df


def get_load_increased_df(resource_dispatch_summary, rep_periods):
    if not isinstance(rep_periods, list):
        rep_periods = [rep_periods]
    load_increased_df = resource_dispatch_summary.loc[
        resource_dispatch_summary.Rep_Period.isin(rep_periods),
        ["Model Year", "Rep_Period", "Hour", "Zone", "Resource", "Increase Load (MW)"],
    ]

    # change hours to hours in list of rep_periods provided
    day = 0
    for rep_period in rep_periods:
        load_increased_df.loc[load_increased_df.Rep_Period == rep_period, "DAY"] = day
        day += 1
    load_increased_df["Hour"] = load_increased_df["Hour"] + (load_increased_df["DAY"] * 24)
    load_increased_df["Hour"] = load_increased_df["Hour"].apply(lambda x: int(x))

    return load_increased_df


def get_load_summary_df(directory, case_folder, case, rep_periods):
    # pull df
    filepath = os.path.join(
        directory,
        "reports\\resolve\\" + case_folder + "\\" + case + "\\results_summary\\hourly_load_components_summary.csv",
    )
    hourly_load_summary = pd.read_csv(filepath)

    # filter on rep_periods
    if not isinstance(rep_periods, list):
        rep_periods = [rep_periods]
    hourly_load_summary = hourly_load_summary.loc[hourly_load_summary.REP_PERIODS.isin(rep_periods)]

    # change hours to hours in list of rep_periods provided
    day = 0
    for rep_period in rep_periods:
        hourly_load_summary.loc[hourly_load_summary.REP_PERIODS == rep_period, "DAY"] = day
        day += 1
    hourly_load_summary["HOURS"] = hourly_load_summary["HOURS"] + (hourly_load_summary["DAY"] * 24)

    return hourly_load_summary


def sum_zonal_loads(load_summary_df, zones):
    load_summary_df["all_zones"] = 0
    for zone in zones:
        zone_total = zone + "_total"
        load_summary_df[zone_total] = load_summary_df.filter(like=zone, axis=1).sum(axis=1)
        load_summary_df["all_zones"] += load_summary_df[zone_total]

        # rename zone_total back to the name of the zone
        load_summary_df.rename(columns={zone_total: zone}, inplace=True)
    return load_summary_df


def get_hourly_transmission_results_df(directory, case_folder, case, rep_periods):
    hourly_transmission_results_filepath = os.path.join(
        directory, "reports\\resolve\\" + case_folder + "\\" + case + "\\variables\\Transmit_Power_MW.csv"
    )
    hourly_transmission_results_df = pd.read_csv(hourly_transmission_results_filepath)

    transmission_summary_filepath = os.path.join(
        directory, "reports\\resolve\\" + case_folder + "\\" + case + "\\results_summary\\transmission_summary.csv"
    )
    transmission_summary_df = pd.read_csv(transmission_summary_filepath)
    transmission_summary_df = transmission_summary_df[["Transmission Path", "Zone From", "Zone To"]]
    transmission_summary_df.rename(
        columns={"Transmission Path": "TRANSMISSION_LINES", "Zone From": "Zone_From", "Zone To": "Zone_To"},
        inplace=True,
    )

    # join dfs
    hourly_transmission_results_df = hourly_transmission_results_df.merge(
        transmission_summary_df, how="left", on="TRANSMISSION_LINES"
    )

    # filter on rep_periods
    if not isinstance(rep_periods, list):
        rep_periods = [rep_periods]
    hourly_transmission_results_df = hourly_transmission_results_df.loc[
        hourly_transmission_results_df.REP_PERIODS.isin(rep_periods)
    ]

    # change hours to hours in list of rep_periods provided
    day = 0
    for rep_period in rep_periods:
        hourly_transmission_results_df.loc[hourly_transmission_results_df.REP_PERIODS == rep_period, "DAY"] = day
        day += 1
    hourly_transmission_results_df["HOURS"] = hourly_transmission_results_df["HOURS"] + (
        hourly_transmission_results_df["DAY"] * 24
    )
    hourly_transmission_results_df["HOURS"] = hourly_transmission_results_df["HOURS"].apply(lambda x: int(x))

    return hourly_transmission_results_df


def add_imports_to_power_provided_df(power_provided_df, hourly_transmission_results_df):
    # group transmission results by Zone_To
    zonal_hourly_imports_to = hourly_transmission_results_df.groupby(
        by=["MODEL_YEARS", "REP_PERIODS", "HOURS", "Zone_To"], as_index=False
    ).sum(numeric_only=True)
    # remove negative numbers (exports) from imports df
    zonal_hourly_imports_to.loc[zonal_hourly_imports_to["Transmit_Power_MW"] < 0, "Transmit_Power_MW"] = 0
    zonal_hourly_imports_to.rename(columns={"Zone_To": "Zone"}, inplace=True)

    # add negative values to imports for "Zone_From" zone
    zonal_hourly_imports_from = hourly_transmission_results_df.groupby(
        by=["MODEL_YEARS", "REP_PERIODS", "HOURS", "Zone_From"], as_index=False
    ).sum(numeric_only=True)
    # remove positive numbers (exports) from imports df
    zonal_hourly_imports_from.loc[zonal_hourly_imports_from["Transmit_Power_MW"] > 0, "Transmit_Power_MW"] = 0
    zonal_hourly_imports_from["Transmit_Power_MW"] = -zonal_hourly_imports_from["Transmit_Power_MW"]
    zonal_hourly_imports_from.rename(columns={"Zone_From": "Zone"}, inplace=True)

    # combine two dfs into zonal_hourly_imports
    zonal_hourly_imports = pd.concat([zonal_hourly_imports_to, zonal_hourly_imports_from])
    zonal_hourly_imports = zonal_hourly_imports.groupby(
        by=["MODEL_YEARS", "REP_PERIODS", "HOURS", "Zone"], as_index=False
    ).sum(numeric_only=True)

    # # change names of hourly imports columns
    zonal_hourly_imports.rename(
        columns={
            "MODEL_YEARS": "Model Year",
            "REP_PERIODS": "Rep_Period",
            "HOURS": "Hour",
            "Transmit_Power_MW": "Provide Power (MW)",
        },
        inplace=True,
    )

    # # Add column for Resource name
    zonal_hourly_imports["Resource"] = "Imports"

    # # concat two dfs
    power_provided_and_imported = pd.concat([power_provided_df, zonal_hourly_imports], keys=["Generation", "Imports"])

    return power_provided_and_imported


def sum_zonal_hourly_exports(hourly_transmission_results_df):
    # group transmission results by zone_from
    zonal_hourly_exports_from = hourly_transmission_results_df.groupby(
        by=["MODEL_YEARS", "REP_PERIODS", "HOURS", "Zone_From"], as_index=False
    ).sum(numeric_only=True)
    # remove negative numbers (imports) from exports df
    zonal_hourly_exports_from.loc[zonal_hourly_exports_from["Transmit_Power_MW"] < 0, "Transmit_Power_MW"] = 0
    zonal_hourly_exports_from.rename(columns={"Zone_From": "Zone"}, inplace=True)

    # group transmission results by zone_to
    zonal_hourly_exports_to = hourly_transmission_results_df.groupby(
        by=["MODEL_YEARS", "REP_PERIODS", "HOURS", "Zone_To"], as_index=False
    ).sum(numeric_only=True)
    # remove positive numbers (imports) from exports df
    zonal_hourly_exports_to.loc[zonal_hourly_exports_to["Transmit_Power_MW"] > 0, "Transmit_Power_MW"] = 0
    zonal_hourly_exports_to["Transmit_Power_MW"] = -zonal_hourly_exports_to["Transmit_Power_MW"]
    zonal_hourly_exports_to.rename(columns={"Zone_To": "Zone"}, inplace=True)

    # concat zonal_hourly_exports
    zonal_hourly_exports = pd.concat([zonal_hourly_exports_from, zonal_hourly_exports_to])
    zonal_hourly_exports = zonal_hourly_exports.groupby(
        by=["MODEL_YEARS", "REP_PERIODS", "HOURS", "Zone"], as_index=False
    ).sum(numeric_only=True)

    # change name of Transmit_Power_MW
    zonal_hourly_exports.rename(columns={"Transmit_Power_MW": "Exports (MW)"}, inplace=True)

    return zonal_hourly_exports


# %% [markdown]
# ## Create function for creating dispatch plot
#

# %%
# TODO: sum up loads by specifying/sorting hour


def create_dispatch_plot(
    power_provided_df, load_summary_df, load_increased_df, zonal_hourly_exports=None, model_year=2050, zone="all_zones"
):

    # print(power_provided_df.columns)
    # print(load_increased_df.columns)
    # print(load_summary_df.columns)
    # print(zonal_hourly_exports.columns)
    power_provided_df = power_provided_df.loc[power_provided_df["Model Year"] == model_year]
    load_summary_df = load_summary_df.loc[load_summary_df["MODEL_YEARS"] == model_year]
    load_increased_df = load_increased_df.loc[load_increased_df["Model Year"] == model_year]
    zonal_hourly_exports = zonal_hourly_exports.loc[zonal_hourly_exports["MODEL_YEARS"] == model_year]

    # plot generation
    if zone == "all_zones":
        # if looking at all zones, ignore imports
        fig = px.area(power_provided_df, x="Hour", y="Provide Power (MW)", color="Resource")

        # sum charging load by hour
        charging_load = (
            load_increased_df[["Hour", "Increase Load (MW)"]]
            .fillna(0)
            .groupby(by=["Hour"])
            .sum(numeric_only=True)["Increase Load (MW)"]
        )
    else:
        fig = px.area(
            power_provided_df.loc[power_provided_df.Zone == zone], x="Hour", y="Provide Power (MW)", color="Resource"
        )

        # sum charging load by zone and by hour
        load_increased_df = load_increased_df.loc[load_increased_df.Zone == zone]
        charging_load = (
            load_increased_df[["Hour", "Increase Load (MW)"]]
            .fillna(0)
            .groupby(by=["Hour"])
            .sum(numeric_only=True)["Increase Load (MW)"]
        )

    # plot load without battery charging
    fig2 = px.line(load_summary_df, x="HOURS", y=zone)

    # plot load with battery charging
    load_summary_copy = load_summary_df.copy()
    load_summary_copy["Load Including Charging"] = load_summary_df[zone] + charging_load.values
    fig3 = px.line(load_summary_copy, x="HOURS", y="Load Including Charging")

    # plot load with exports
    if zone != "all_zones":
        load_summary_copy["Load Including Charging and Exports"] = (
            load_summary_copy["Load Including Charging"]
            + zonal_hourly_exports.loc[zonal_hourly_exports["Zone"] == zone, "Exports (MW)"].values
        )
        fig4 = px.line(load_summary_copy, x="HOURS", y="Load Including Charging and Exports")

    # add all plots to subfig
    subfig = make_subplots()
    fig2.update_traces(showlegend=True, name="Load")
    fig3.update_traces(showlegend=True, name="Load with charging", line_color="red", patch={"line": {"dash": "dash"}})
    if zone == "all_zones":
        subfig.add_traces(fig.data + fig2.data + fig3.data)
    else:
        fig4.update_traces(
            showlegend=True, name="Load with charging and exports", line_color="green", patch={"line": {"dash": "dash"}}
        )
        subfig.add_traces(fig.data + fig2.data + fig3.data + fig4.data)

    # # todo: make subplots with go.figure
    subfig.show()


# %% [markdown]
# ## Create function for creating dispatch from raw results files


# %%
def dispatch_plot_from_raw_results(directory, case_folder, case, rep_periods, model_year=2050, zone="all_zones"):
    # resource dispatch summary
    resource_dispatch_summary = get_resource_dispatch_summary(directory, case_folder, case)
    # power provided df
    power_provided_df = get_power_provided_df(resource_dispatch_summary, rep_periods)
    # load increased df
    load_increased_df = get_load_increased_df(resource_dispatch_summary, rep_periods)
    # load summary df
    load_summary_df = get_load_summary_df(directory, case_folder, case, rep_periods)
    zones = power_provided_df.Zone.unique()
    load_summary_df = sum_zonal_loads(load_summary_df, zones)

    # add transmission summary only if looking at specific zone
    if zone == "all_zones":
        create_dispatch_plot(power_provided_df, load_summary_df, load_increased_df)
    else:
        hourly_transmission_results_df = get_hourly_transmission_results_df(directory, case_folder, case, rep_periods)
        power_provided_df = add_imports_to_power_provided_df(power_provided_df, hourly_transmission_results_df)
        zonal_hourly_exports = sum_zonal_hourly_exports(hourly_transmission_results_df)
        create_dispatch_plot(power_provided_df, load_summary_df, load_increased_df, zonal_hourly_exports, zone=zone)


# %% [markdown]
# ## Plot test-manual-rep-periods representative day

# %%
# User inputs
# directory = os.path.dirname(os.getcwd())
directory = (
    r"C:\Users\BMahoney\Energy and Environmental Economics, Inc\NY PATHWAYS and NMT 2023+ - Documents\RESOLVE NMT"
)
case_folder = "Ref_noFlex_1119_prodsim"
case = "2023-12-28 21-12-10"
rep_periods = [24]
zone = "NYISO_A"

# create dispatch plot
dispatch_plot_from_raw_results(directory, case_folder, case, rep_periods, zone=zone)

# %%
# User inputs
# directory = os.path.dirname(os.getcwd())
directory = (
    r"C:\Users\BMahoney\Energy and Environmental Economics, Inc\NY PATHWAYS and NMT 2023+ - Documents\RESOLVE NMT"
)
case_folder = "Ref_noFlex_1119_prodsim"
case = "2023-12-11 10-52-10"
rep_periods = [23, 24]
zone = "ISONE"

# create dispatch plot
dispatch_plot_from_raw_results(directory, case_folder, case, rep_periods, zone)

# %%
# User inputs
# directory = os.path.dirname(os.getcwd())
directory = (
    r"C:\Users\BMahoney\Energy and Environmental Economics, Inc\NY PATHWAYS and NMT 2023+ - Documents\RESOLVE NMT"
)
case_folder = "Ref_noFlex_1119_prodsim"
case = "2023-12-11 10-52-10"
rep_periods = np.arange(0, 365).tolist()
zone = "PJM"

# resource dispatch summary
resource_dispatch_summary = get_resource_dispatch_summary(directory, case_folder, case)
# power provided df
power_provided_df = get_power_provided_df(resource_dispatch_summary, rep_periods)
power_provided_df.loc[power_provided_df.Resource == "PJM_Solar_Existing", "Provide Power (MW)"].sum()

# create dispatch plot
# dispatch_plot_from_raw_results(directory, case_folder, case, rep_periods, zone)

# %%
rep_periods = list(np.arange(0, 365))
load_summary = get_load_summary_df(directory, case_folder, case, rep_periods)
load_summary_summed = sum_zonal_loads(load_summary, zones)
plt.plot(load_summary_summed["ISONE"])
np.argmax(load_summary_summed["ISONE"])

# %%
filepath = os.path.join(
    r"C:\Users\BMahoney\Energy and Environmental Economics, Inc\NY PATHWAYS and NMT 2023+ - Documents\RESOLVE NMT\reports\resolve\Ref_noFlex_1119_prodsim\2023-12-11 10-52-10\expressions"
    + "\\Plant_Provide_Power_Capacity_In_Timepoint_MW.csv"
)
provide_power_in_timepoint = pd.read_csv(filepath)
provide_power_in_timepoint.loc[provide_power_in_timepoint.PLANTS_THAT_PROVIDE_POWER == "PJM_Solar_Existing"].sum()


# %% [markdown]
# ## Plot 168 hours over representative week in full production simulation

# %%
# User inputs
case_folder = "test-manual-rep-periods-prod-sim"
case = "2023-11-20 10-54-21"
rep_periods = np.arange(202, 209).tolist()
zone = "zone_1"

dispatch_plot_from_raw_results(case_folder, case, rep_periods, zone)

# %% [markdown]
# ## Dispatch plot for NYSERDA production simulation

# %%
# User inputs
# directory = os.path.dirname(os.getcwd())
directory = (
    r"C:\Users\BMahoney\Energy and Environmental Economics, Inc\NY PATHWAYS and NMT 2023+ - Documents\RESOLVE NMT"
)
case_folder = "Ref_noFlex_1119_prodsim"
case = "2023-12-28 21-12-10"
rep_periods = [308]
zone = "NYISO_A"

# create dispatch plot
dispatch_plot_from_raw_results(directory, case_folder, case, rep_periods, zone)

# %%
# User inputs
# directory = os.path.dirname(os.getcwd())
directory = (
    r"C:\Users\BMahoney\Energy and Environmental Economics, Inc\NY PATHWAYS and NMT 2023+ - Documents\RESOLVE NMT"
)
case_folder = "Ref_noFlex_1119_fullProfiles"
case = "2023-12-28 07-43-05"
rep_periods = [0]
zone = "NYISO_A"

# create dispatch plot
dispatch_plot_from_raw_results(directory, case_folder, case, rep_periods, zone=zone)

# %%
# User inputs
# directory = os.path.dirname(os.getcwd())
directory = (
    r"C:\Users\BMahoney\Energy and Environmental Economics, Inc\NY PATHWAYS and NMT 2023+ - Documents\RESOLVE NMT"
)
case_folder = "Ref_noFlex_1119_prodsim"
case = "2023-12-28 21-12-10"
rep_periods = [308]
zone = "NYISO_A"

# create dispatch plot
dispatch_plot_from_raw_results(directory, case_folder, case, rep_periods, zone=zone)

# %%
