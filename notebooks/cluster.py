# ---
# jupyter:
#   jupytext:
#     custom_cell_magics: kql
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.15.1
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---
# %%
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from loguru import logger
from resolve.common import system
from resolve.common.load_component import Load
from resolve.core.temporal.cluster import Clusterer
from resolve.core.temporal.timeseries import NumericTimeseries
from resolve.core.utils.util import DirStructure

logger.remove()
# Set stdout logging level
logger.add(sys.__stdout__, level="INFO")
logger.add(sys.stderr, level="INFO")
logger.disable("resolve")

# %%
# Case to use for clustering
case = "Core_25MMT"

# %%
dir_str = DirStructure(data_folder=r"data")
dir_str.make_resolve_dir(resolve_settings_name=case)

scenarios = pd.read_csv(dir_str.resolve_settings_dir / "scenarios.csv")["scenarios"].tolist()
system_name = pd.read_csv(dir_str.resolve_settings_dir / "attributes.csv", index_col="attribute").loc["system", "value"]

_, system = system.System.from_csv(
    filename=dir_str.data_interim_dir / "systems" / system_name / "attributes.csv",
    scenarios=scenarios,
    data={"dir_str": dir_str, "model_name": "resolve"},
)

# %%
hourly_timestamps = pd.date_range(
    start="1/1/1998",
    end="12/31/2020 23:00",
    freq="1H",
    inclusive="left",
)
system.resources["CAISO_Hydro"].daily_budget.data = pd.Series(
    system.resources["CAISO_Hydro"].daily_budget.data, index=hourly_timestamps
).ffill()

# %%
# Add net load as a timeseries to consider for clustering fit
net_load_components = [
    (system.resources["Arizona_Solar"], 0, "provide_power_potential_profile"),
    (system.resources["Baja_California_Wind"], 0, "provide_power_potential_profile"),
    (system.resources["CAISO_Solar"], 16000, "provide_power_potential_profile"),
    (system.resources["CAISO_Wind"], 6700, "provide_power_potential_profile"),
    (system.resources["Cape_Mendocino_Offshore_Wind"], 0, "provide_power_potential_profile"),
    (system.resources["Central_Valley_North_Los_Banos_Wind"], 200, "provide_power_potential_profile"),
    (system.resources["Del_Norte_Offshore_Wind"], 0, "provide_power_potential_profile"),
    # (system.resources["Diablo_Canyon_Offshore_Wind"], 1000, "provide_power_potential_profile"),
    (system.resources["Distributed_Solar"], 0, "provide_power_potential_profile"),
    (system.resources["Greater_Imperial_Solar"], 0, "provide_power_potential_profile"),
    (system.resources["Greater_Imperial_Wind"], 0, "provide_power_potential_profile"),
    (system.resources["Greater_Kramer_Solar"], 5000, "provide_power_potential_profile"),
    (system.resources["Greater_LA_Solar"], 0, "provide_power_potential_profile"),
    (system.resources["Humboldt_Bay_Offshore_Wind"], 1000, "provide_power_potential_profile"),
    (system.resources["Idaho_Wind"], 0, "provide_power_potential_profile"),
    (system.resources["Morro_Bay_Offshore_Wind"], 1000, "provide_power_potential_profile"),
    (system.resources["New_Mexico_Wind"], 0, "provide_power_potential_profile"),
    (system.resources["Northern_California_Solar"], 0, "provide_power_potential_profile"),
    (system.resources["Northern_California_Wind"], 1000, "provide_power_potential_profile"),
    (system.resources["Riverside_Solar"], 25000, "provide_power_potential_profile"),
    (system.resources["Solano_Wind"], 25, "provide_power_potential_profile"),
    (system.resources["Southern_NV_Eldorado_Solar"], 8000, "provide_power_potential_profile"),
    (system.resources["Southern_NV_Eldorado_Wind"], 500, "provide_power_potential_profile"),
    (system.resources["Southern_PGAE_Solar"], 23000, "provide_power_potential_profile"),
    (system.resources["Tehachapi_Solar"], 6000, "provide_power_potential_profile"),
    (system.resources["Tehachapi_Wind"], 300, "provide_power_potential_profile"),
    (system.resources["Utah_Wind"], 0, "provide_power_potential_profile"),
    (system.resources["Wyoming_Wind"], 1500, "provide_power_potential_profile"),
]

gross_load = system.loads["CAISO Baseline"].profile.data.copy(deep=True)
gross_load = gross_load * 55000 / gross_load.groupby(gross_load.index.year).max().median()


net_load_profile = gross_load.copy(deep=True)
for cmp, multiplier, attr in net_load_components:
    net_load_profile = net_load_profile - multiplier * getattr(cmp, attr).data

net_load = Load(
    name="net load", profile=NumericTimeseries(name="net load profile", data=net_load_profile), profile_model_years=None
)

# %%
# Add months as a timeseries to consider for clustering fit

months = net_load.copy(deep=True)
months.name = "months"
months.profile.data.iloc[:] = months.profile.data.index.month
months.profile.data

# %%
# Initialize timeseries clusterer
c = Clusterer(
    name="test",
    components_to_consider=[
        (months, 20, "profile"),
        (
            system.loads["CAISO Baseline"],
            10
            / system.loads["CAISO Baseline"]
            .profile.data.groupby(system.loads["CAISO Baseline"].profile.data)
            .max()
            .median(),
            "profile",
        ),
        (net_load, 5 / net_load.profile.data.groupby(net_load.profile.data).max().median(), "profile"),
        (system.resources["Arizona_Solar"], 1, "provide_power_potential_profile"),
        (system.resources["Baja_California_Wind"], 10, "provide_power_potential_profile"),
        (system.resources["CAISO_Hydro"], 40, "daily_budget"),
        (system.resources["CAISO_Solar"], 1, "provide_power_potential_profile"),
        (system.resources["CAISO_Wind"], 20, "provide_power_potential_profile"),
        (system.resources["Cape_Mendocino_Offshore_Wind"], 20, "provide_power_potential_profile"),
        (system.resources["Central_Valley_North_Los_Banos_Wind"], 20, "provide_power_potential_profile"),
        (system.resources["Del_Norte_Offshore_Wind"], 20, "provide_power_potential_profile"),
        # (system.resources["Diablo_Canyon_Offshore_Wind"], 20, "provide_power_potential_profile"),
        (system.resources["Distributed_Solar"], 1, "provide_power_potential_profile"),
        (system.resources["Greater_Imperial_Solar"], 1, "provide_power_potential_profile"),
        (system.resources["Greater_Imperial_Wind"], 20, "provide_power_potential_profile"),
        (system.resources["Greater_Kramer_Solar"], 1, "provide_power_potential_profile"),
        (system.resources["Greater_LA_Solar"], 1, "provide_power_potential_profile"),
        (system.resources["Humboldt_Bay_Offshore_Wind"], 20, "provide_power_potential_profile"),
        (system.resources["Idaho_Wind"], 20, "provide_power_potential_profile"),
        (system.resources["Morro_Bay_Offshore_Wind"], 20, "provide_power_potential_profile"),
        (system.resources["New_Mexico_Wind"], 20, "provide_power_potential_profile"),
        (system.resources["Northern_California_Solar"], 1, "provide_power_potential_profile"),
        (system.resources["Northern_California_Wind"], 20, "provide_power_potential_profile"),
        (system.resources["Riverside_Solar"], 1, "provide_power_potential_profile"),
        (system.resources["Solano_Wind"], 20, "provide_power_potential_profile"),
        (system.resources["Southern_NV_Eldorado_Solar"], 1, "provide_power_potential_profile"),
        (system.resources["Southern_NV_Eldorado_Wind"], 20, "provide_power_potential_profile"),
        (system.resources["Southern_PGAE_Solar"], 1, "provide_power_potential_profile"),
        (system.resources["Tehachapi_Solar"], 1, "provide_power_potential_profile"),
        (system.resources["Tehachapi_Wind"], 20, "provide_power_potential_profile"),
        (system.resources["Utah_Wind"], 20, "provide_power_potential_profile"),
        (system.resources["Wyoming_Wind"], 20, "provide_power_potential_profile"),
    ],
    weather_years_to_use=[],  # Use all weather years of data in the timeseries data
    rep_period_length="1D",
    clusters=36,
)

# %%
# Run timeseries clustering
c.get_clusters()
c.calculate_rmse()
c.rmse

# %%
# Save CSV files needed for inputs
chrono_periods = pd.DataFrame(
    data={
        i: pd.date_range(start=chrono_period, periods=24, freq="H")
        for i, chrono_period in enumerate(c.chrono_periods.index)
    }
).T
chrono_periods = chrono_periods.rename_axis(index="period")
chrono_periods.to_csv("chrono_periods.csv")

map_to_rep_periods = c.clustered_dates.resample("D").first().reset_index()
map_to_rep_periods.columns = ["Chrono Period", "Rep Period"]

rep_periods = chrono_periods.loc[chrono_periods[0].isin(sorted(map_to_rep_periods["Rep Period"].unique()))]
rep_periods.to_csv("rep_periods.csv")

map_to_rep_periods = map_to_rep_periods.replace(chrono_periods[[0]].reset_index().set_index(0).squeeze(axis=1))
map_to_rep_periods.to_csv("map_to_rep_periods.csv", index=False)

rep_period_weights = map_to_rep_periods.groupby(["Rep Period"]).count() / len(map_to_rep_periods)
rep_period_weights = rep_period_weights.sort_index().squeeze(axis=1)
rep_period_weights.index = (
    rep_period_weights.index.to_frame()
    .replace(chrono_periods[[0]].reset_index().set_index(0).squeeze(axis=1))
    .squeeze(axis=1)
)
rep_period_weights = rep_period_weights.rename_axis(index="Representative Period").rename("Weight").to_frame()
rep_period_weights.to_csv("rep_period_weights.csv")

# %% [markdown]
# ## (Optional) Plot Clustering Results

# %%
# Creating the timeseries cluster comparison can be quite slow for cases with long timeseries (e.g., 23 weather years in CPUC IRP cases)
c.compare_clustered_timeseries()

# %%
# Plot mapping of representative periods to original chronological period

n_colors = 365
colors = px.colors.sample_colorscale("IceFire", [n / (n_colors - 1) for n in range(n_colors)])
colors = pd.Series(colors, index=range(0, 365))
colors = colors.to_frame(name="colors")
colors = pd.concat([colors] * 23, axis=0, ignore_index=True)
colors.index = pd.date_range(start="1/1/1998", freq="D", end="12/31/2020")[:-6]

df = pd.merge(df, colors, left_on="Chrono Period", right_index=True)
df["Month"] = df["Rep Period"].dt.month
df["Day"] = df["Rep Period"].dt.day
df = df.sort_values(["Month", "Day"])

fig = go.Figure(
    data=go.Scatter(
        y=df["Chrono Period"],
        x=df["Rep Period"].dt.strftime("%m/%d/%Y"),
        mode="markers",
        marker=dict(
            size=6,
            color=df["colors"],
        ),
    )
)

fig.update_layout(
    xaxis=dict(
        # autorange="reversed",
        type="category",
        dtick=1,
        title="<b>Sampled Operational Days</b>",
    ),
    yaxis=dict(autorange="reversed", title="<b>Original Date</b>", tickformat="%m/%d/%Y", showgrid=True, dtick="M12"),
    height=12 * 144,
    width=6 * 144,
    margin=dict(
        l=120,
        b=160,
    ),
    font=dict(size=10),
)
fig.show()
# fig.write_image(f"rep-periods.svg")
fig.write_html("rep-periods.html")
