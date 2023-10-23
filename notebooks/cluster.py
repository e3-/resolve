# ---
# jupyter:
#   jupytext:
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

import kmedoids
import numpy
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from loguru import logger
from plotly.subplots import make_subplots
from resolve.common.load_component import Load
from sklearn.metrics.pairwise import euclidean_distances

# %%
logger.remove()
# Set stdout logging level
logger.add(sys.__stdout__, level="INFO")
logger.add(sys.stderr, level="INFO")

# %%
from resolve.core.utils.util import DirStructure
from resolve.common import system
import pandas as pd

case = "8_22_Resources_Hydrogen_25MMT"

dir_str = DirStructure(data_folder=r"data")
dir_str.make_resolve_dir(resolve_settings_name=case)

scenarios = pd.read_csv(dir_str.resolve_settings_dir / "scenarios.csv")["scenarios"].tolist()

_, system = system.System.from_csv(
    filename=dir_str.data_interim_dir / "systems" / "test-08-25-hydrogen" / "attributes.csv",
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
from typing import Any, Optional
from resolve.core.component import Component
from resolve.core.custom_model import CustomModel
import numpy as np
from loguru import logger
from pydantic import Field
from resolve.core.utils.core_utils import timer


class Clusterer(CustomModel):
    components_to_consider: list[tuple[Component, float, str]]
    weather_years_to_use: list[int]
    rep_period_length: str = Field(
        "1D",
        description='See https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#offset-aliases for valid options (though special offsets like "business days" will likely not work).',
    )

    # Intermediate things
    chrono_periods: Optional[pd.DataFrame] = None
    distance_matrix: Optional[np.ndarray] = None
    clustered_dates: Optional[pd.DataFrame] = None
    rmse: Optional[pd.DataFrame] = None
    medoid_results: Any = None

    # Attributes to pass to kmedoids package
    clusters: int
    random_state: int = 1730482

    def _pivot_chrono_periods(self):
        self.chrono_periods = pd.concat(
            [
                pd.pivot_table(
                    multiplier * getattr(component, attr).data.to_frame(),
                    index=getattr(component, attr).data.index.date,
                    columns=getattr(component, attr).data.index.hour,
                )
                for component, multiplier, attr in self.components_to_consider
            ],
            axis=1,
        )
        self.chrono_periods.index = pd.to_datetime(self.chrono_periods.index)

        if len(self.weather_years_to_use) > 0:
            self.chrono_periods = self.chrono_periods.loc[
                np.isin(self.chrono_periods.index.year, self.weather_years_to_use)
            ]

        self.chrono_periods = self.chrono_periods.dropna(how="any").T.reset_index(drop=True).T

    @timer
    def get_clusters(self):
        self._pivot_chrono_periods()

        self.distance_matrix = euclidean_distances(self.chrono_periods)

        # Add this to attrs above
        self.medoid_results = kmedoids.fasterpam(
            self.distance_matrix, medoids=self.clusters, random_state=self.random_state, n_cpu=4
        )

        # Map chrono and rep periods
        medoids = pd.Series(self.medoid_results.medoids).map(self.chrono_periods.reset_index()["index"])

        clustered_dates = pd.Series(self.medoid_results.labels, index=self.chrono_periods.index).map(medoids)
        clustered_dates.index = pd.to_datetime(clustered_dates.index, infer_datetime_format=True)
        clustered_dates = pd.to_datetime(clustered_dates, infer_datetime_format=True)

        # Create a new DateTimeIndex that has all the hours
        hourly_timestamps = pd.date_range(
            start=clustered_dates.index[0],
            end=clustered_dates.index[-1] + pd.tseries.frequencies.to_offset(self.rep_period_length),
            freq="1H",
            inclusive="left",
        )

        clustered_dates = pd.Series(hourly_timestamps, index=hourly_timestamps).map(clustered_dates).ffill()
        clustered_dates = clustered_dates + pd.to_timedelta(clustered_dates.index.hour, unit="H")

        self.clustered_dates = clustered_dates

        return self.clustered_dates

    @timer
    def calculate_rmse(self):
        """Calculate RMSE for every component included in Clusterer."""
        rmse: dict = {}
        for component, _, attr in self.components_to_consider:
            profiles_for_plotting = pd.concat(
                [getattr(component, attr).data, self.clustered_dates.map(getattr(component, attr).data)], axis=1
            )
            profiles_for_plotting.columns = ["original", "clustered"]

            rmse[component.name] = (
                (
                    (profiles_for_plotting["original"] - profiles_for_plotting["clustered"])
                    / profiles_for_plotting["original"].max()
                )
                ** 2
            ).mean() ** 0.5

        rmse["total"] = sum(
            multiplier * rmse[component.name] for component, multiplier, _ in self.components_to_consider
        )

        self.rmse = pd.Series(rmse)

    @timer
    def compare_clustered_timeseries(self):
        """Create a plotly figure with comparison metrics between original and clustered timeseries.

        TODO: Can add more components than just the ones that were used to cluster on to do this comparison
        TODO: This won't work out of the box with modeled year timeseries.
        """
        f = open("clustering_results.html", "w")
        f.close()
        # print(components_to_consider)
        with open("clustering_results.html", "a") as f:
            for component, _, attr in self.components_to_consider:
                profiles_for_plotting = pd.concat(
                    [getattr(component, attr).data, self.clustered_dates.map(getattr(component, attr).data)], axis=1
                )
                profiles_for_plotting.columns = ["original", "clustered"]

                fig = make_subplots(
                    rows=2,
                    cols=3,
                    specs=[
                        [{"colspan": 2, "type": "xy"}, None, {"rowspan": 2, "type": "table"}],
                        [{"type": "xy"}, {"type": "xy"}, None],
                    ],
                    column_widths=[0.35, 0.35, 0.3],
                )

                # Chronological
                fig.add_traces(
                    [
                        go.Scatter(
                            x=profiles_for_plotting.index,
                            y=profiles_for_plotting["original"] / profiles_for_plotting["original"].max(),
                            marker_color="rgb(3, 78, 110)",
                            opacity=0.75,
                            name="original",
                            showlegend=False,
                        ),
                        go.Scatter(
                            x=profiles_for_plotting.index,
                            y=profiles_for_plotting["clustered"] / profiles_for_plotting["original"].max(),
                            marker_color="rgb(255, 135, 0)",
                            name="clustered",
                            opacity=0.75,
                            showlegend=False,
                        ),
                    ],
                    rows=1,
                    cols=1,
                )

                # Duration curve
                fig.add_traces(
                    [
                        go.Scatter(
                            x=profiles_for_plotting.reset_index().index,
                            y=profiles_for_plotting["original"].sort_values(ascending=False)
                            / profiles_for_plotting["original"].max(),
                            marker_color="rgb(3, 78, 110)",
                            opacity=0.75,
                            name="original",
                            showlegend=False,
                        ),
                        go.Scatter(
                            x=profiles_for_plotting.reset_index().index,
                            y=profiles_for_plotting["clustered"].sort_values(ascending=False)
                            / profiles_for_plotting["original"].max(),
                            marker_color="rgb(255, 135, 0)",
                            name="clustered",
                            opacity=0.75,
                            showlegend=False,
                        ),
                    ],
                    rows=2,
                    cols=1,
                )

                # Histogram
                fig.add_traces(
                    [
                        go.Histogram(
                            x=profiles_for_plotting["original"],
                            marker_color="rgb(3, 78, 110)",
                            opacity=0.75,
                            histnorm="probability density",
                            name="Original",
                        ),
                        go.Histogram(
                            x=profiles_for_plotting["clustered"],
                            marker_color="rgb(255, 135, 0)",
                            opacity=0.75,
                            histnorm="probability density",
                            name="Clustered",
                        ),
                    ],
                    rows=2,
                    cols=2,
                )

                # Summary stats table
                annual_metrics = profiles_for_plotting.groupby(profiles_for_plotting.index.year)

                fig.add_trace(
                    go.Table(
                        header=dict(
                            values=[
                                ("", ""),
                                ("<b>Peak</b>", "Original"),
                                ("<b>Peak</b>", "Clustered"),
                                ("<b>Mean</b>", "Original"),
                                ("<b>Mean</b>", "Clustered"),
                            ],
                            font=dict(size=12),
                        ),
                        cells=dict(
                            values=[
                                annual_metrics.max().index,
                                annual_metrics.max()["original"],
                                annual_metrics.max()["clustered"],
                                annual_metrics.mean()["original"],
                                annual_metrics.mean()["clustered"],
                            ],
                            font=dict(size=12),
                            format=[None, ",.5r", ",.5r", ",.5r", ",.5r"],
                        ),
                    ),
                    row=1,
                    col=3,
                )

                fig.update_layout(
                    height=5 * 144,
                    width=12.32 * 144,
                    barmode="overlay",
                    title=dict(
                        text=f"<b>{component.name}.</b>{attr}",
                        x=0.04,
                        y=0.96,
                    ),
                )
                logger.info(f"Saving timeseries comparison to: {component.name}.{attr}")
                f.write(
                    fig.to_html(
                        f"{component.name}-{attr}.html",
                        full_html=False,
                        include_plotlyjs="cdn",
                    ),
                )
            fig.show()
        f.close()


# %%
c = Clusterer(
    name="test",
    components_to_consider=[
        (system.loads["CAISO Baseline"], 3, "profile"),
    ],
    weather_years_to_use=[],
    rep_period_length="1D",
    clusters=36,
)

c.get_clusters()
# c.compare_clustered_timeseries()
c.calculate_rmse()

# %%
# c.compare_clustered_timeseries()

# %%
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

# %%
net_load_profile = gross_load.copy(deep=True)
for cmp, multiplier, attr in net_load_components:
    net_load_profile = net_load_profile - multiplier * getattr(cmp, attr).data

# %%
from resolve.common.load_component import Load
from resolve.core.temporal.timeseries import NumericTimeseries

net_load = Load(
    name="net load", profile=NumericTimeseries(name="net load profile", data=net_load_profile), profile_model_years=None
)

# %%
months = net_load.copy(deep=True)
months.name = "months"
months.profile.data.iloc[:] = months.profile.data.index.month
months.profile.data

# %%
# TODO: To use zonal load instead of each load component (which would also magically make modeled-year timeseries work), seems like we could feed in a zone component to considerand use `get_load()` or something

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
    # weather_years_to_use=[],
    weather_years_to_use=[2007, 2008, 2009],
    rep_period_length="1D",
    clusters=6,
)

# %%
c.get_clusters()
c.calculate_rmse()
c.rmse

# %%
x = {
    component.name: pd.pivot_table(
        multiplier * getattr(component, attr).data.to_frame(),
        index=getattr(component, attr).data.index.date,
        columns=getattr(component, attr).data.index.hour,
    )
    for component, multiplier, attr in c.components_to_consider
}

# %%
for cmp, y in x.items():
    print(y.index[0], y.index[-1], cmp)

# %%
pd.Series(c.medoid_results.labels).describe()

# %%
c.clustered_dates

# %%
c.clustered_dates.to_csv("clustered_dates.csv", index=True)

# %%
c.chrono_periods

# %%
from pathlib import Path

output_dir = Path(f"./{c.clusters}_{'_'.join(map(str, [min(c.weather_years_to_use), max(c.weather_years_to_use)]))}/")
output_dir.mkdir(exist_ok=True)

# %%
chrono_periods = pd.DataFrame(
    data={
        i: pd.date_range(start=chrono_period, periods=24, freq="H")
        for i, chrono_period in enumerate(c.chrono_periods.index)
    }
).T
chrono_periods = chrono_periods.rename_axis(index="period")
chrono_periods.to_csv(output_dir.joinpath("chrono_periods.csv"))
chrono_periods

# %%
c.chrono_periods

# %%
c.clustered_dates.resample("D").first().index.difference(c.chrono_periods.index)

# %%
map_to_rep_periods = c.clustered_dates.resample("D").first().reset_index()
map_to_rep_periods.columns = ["Chrono Period", "Rep Period"]
# chrono_period_to_period_id_map = (
#     map_to_rep_periods.rename_axis(index="period_id").reset_index().set_index("Chrono Period").loc[:, "period_id"]
# )
# map_to_rep_periods.loc[:, "Representative Period"] = map_to_rep_periods["Rep Period"].map(
#     chrono_period_to_period_id_map.to_dict()
# )
# map_to_rep_periods = (
#     map_to_rep_periods.rename_axis(index="Chronological Period").loc[:, "Representative Period"].to_frame()
# )
# map_to_rep_periods.to_csv(output_dir.joinpath("map_to_rep_periods.csv"))
map_to_rep_periods

# %%
rep_periods = chrono_periods.loc[sorted(map_to_rep_periods.squeeze().unique())]
rep_periods.to_csv(output_dir.joinpath("rep_periods.csv"))
rep_periods

# %%
rep_period_weights = map_to_rep_periods.squeeze().value_counts() / map_to_rep_periods.squeeze().value_counts().sum()
rep_period_weights = rep_period_weights.sort_index()
rep_period_weights = rep_period_weights.rename_axis(index="Representative Period").rename("Weight").to_frame()
rep_period_weights.to_csv(output_dir.joinpath("rep_period_weights.csv"))
rep_period_weights

# %%
c.compare_clustered_timeseries()

# %%
df = c.clustered_dates.resample("D").first().reset_index()
df.columns = ["Chrono Period", "Rep Period"]
df.to_csv("map_to_chrono_periods.csv", index=True)

# %%
df

# %%
n_colors = 365
colors = px.colors.sample_colorscale("IceFire", [n / (n_colors - 1) for n in range(n_colors)])
colors = pd.Series(colors, index=range(0, 365))
colors = colors.to_frame(name="colors")
colors = pd.concat([colors] * 23, axis=0, ignore_index=True)
colors.index = pd.date_range(start="1/1/1998", freq="D", end="12/31/2020")[:-6]
colors

df = pd.merge(df, colors, left_on="Chrono Period", right_index=True)
df["Month"] = df["Rep Period"].dt.month
df["Day"] = df["Rep Period"].dt.day
df = df.sort_values(["Month", "Day"])

# %%
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

# %%

# %%
