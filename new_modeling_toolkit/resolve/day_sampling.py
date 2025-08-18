import copy
import glob
import io
import os
import pathlib
from itertools import product
from typing import Any
from typing import Optional

import ipywidgets as widgets
import kmedoids
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import scipy
import seaborn as sns
from IPython.display import clear_output
from IPython.display import display
from loguru import logger
from plotly.subplots import make_subplots
from pydantic import Field
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import euclidean_distances

from new_modeling_toolkit.core.custom_model import CustomModel
from new_modeling_toolkit.core.utils.core_utils import timer
from new_modeling_toolkit.core.utils.util import DirStructure
from new_modeling_toolkit.system import System


class DaySamplingClusterer(CustomModel):
    grid_combo: dict[str, float]
    components_to_cluster: list[tuple[str, float]]
    components_to_plot: dict[str, list[tuple[str, float]]]
    weather_years_to_use: list[int]
    rep_period_length: str = Field(
        "1D",
        description='See https://pandas.pydata.org/pandas-docs/stable/user_guide/timeseries.html#offset-aliases for valid options (though special offsets like "business days" will likely not work).',
    )
    dict_profiles: dict[str, pd.DataFrame | pd.Series]

    # Intermediate attribute
    chrono_periods: Optional[pd.DataFrame] = None
    distance_matrix: Optional[np.ndarray] = None
    clustered_dates: Optional[pd.DataFrame | pd.Series] = None
    clustered_dates_force: Optional[pd.DataFrame | pd.Series] = None
    rmse: Optional[dict] = None
    medoids: Any = None
    medoid_results: Any = None
    dfCorrelation: Any = None
    sil: Any = None
    # Attributes to pass to kmedoids package
    clusters: int
    random_state: int

    # Results and file path
    prof_raw: Optional[pd.DataFrame | pd.Series] = None
    prof_cluster: Optional[pd.DataFrame | pd.Series] = None
    prof_8760_cluster: Optional[pd.DataFrame | pd.Series] = None
    results_folder_name: str = None

    def _pivot_chrono_periods(self):
        # chrono_periods is a dataframe with daily index and columns for every variable/hour combo in the 24-hour day
        self.chrono_periods = pd.concat(
            [
                pd.pivot_table(
                    multiplier
                    * (
                        # normalize the component time series before multiplying so differences in profiles' scale don't override multipliers' effect
                        (self.dict_profiles[component] - self.dict_profiles[component].mean())
                        / self.dict_profiles[component].std(ddof=0)
                    ).to_frame(),
                    index=self.dict_profiles[component].index.date,
                    columns=self.dict_profiles[component].index.hour,
                )
                for component, multiplier in self.components_to_cluster
            ],
            axis=1,
        )

        self.chrono_periods.index = pd.to_datetime(self.chrono_periods.index)

        if len(self.weather_years_to_use) > 0:  # filter for specific weather years to use in the clustering, if desired
            self.chrono_periods = self.chrono_periods.loc[
                np.isin(self.chrono_periods.index.year, self.weather_years_to_use)
            ]

        self.chrono_periods = self.chrono_periods.dropna(how="any").T.reset_index(drop=True).T

    @timer
    def get_clusters(self):
        self._pivot_chrono_periods()

        # calculate distance matrix used in the clustering
        # distances are based on each day's (X variables)*(24 hours) features
        self.distance_matrix = euclidean_distances(self.chrono_periods)

        self.medoid_results = kmedoids.fasterpam(
            self.distance_matrix, medoids=self.clusters, random_state=self.random_state, n_cpu=4
        )

        # Map chrono and rep periods
        self.medoids = pd.Series(self.medoid_results.medoids).map(
            self.chrono_periods.reset_index()["index"]
        )  # retrieves list of periods selected as medoids

        clustered_dates = pd.Series(self.medoid_results.labels, index=self.chrono_periods.index).map(
            self.medoids
        )  # for each day in the time horizon (chrono_periods.index), add a column showing which medoid it was labeled to
        clustered_dates.index = pd.to_datetime(clustered_dates.index, infer_datetime_format=True)
        clustered_dates = pd.to_datetime(clustered_dates, infer_datetime_format=True)

        # Create a new DateTimeIndex that has all the hours
        hourly_timestamps = pd.date_range(
            start=clustered_dates.index[0],
            end=clustered_dates.index[-1] + pd.tseries.frequencies.to_offset(self.rep_period_length),
            freq="1H",
            inclusive="left",
        )

        # remove leap days
        # hourly_timestamps = hourly_timestamps[~((hourly_timestamps.month == 2) & (hourly_timestamps.day == 29))]

        clustered_dates = (
            pd.Series(hourly_timestamps, index=hourly_timestamps).map(clustered_dates).ffill()
        )  # this step results in some days that had NaNs originally being mapped to the same medoids as the previous point
        self.clustered_dates = clustered_dates + pd.to_timedelta(clustered_dates.index.hour, unit="H")

        self.sil = silhouette_score(
            self.distance_matrix, self.medoid_results.labels
        )  # potentially not useful metric depending on the shape of the data (more challenging in higher dimensions

    def calculate_rmse(self):
        """Calculate RMSE for every component included in Clusterer."""
        rmse: dict = {}
        for cat in self.components_to_plot.keys():
            if len(self.components_to_plot[cat]) != 0:
                for component, _ in self.components_to_plot[cat]:
                    profiles_for_plotting = pd.concat(
                        [self.dict_profiles[component], self.clustered_dates.map(self.dict_profiles[component])], axis=1
                    )
                    profiles_for_plotting.columns = ["original", "clustered"]

                    rmse[component] = (
                        (
                            (profiles_for_plotting["original"] - profiles_for_plotting["clustered"])
                            / profiles_for_plotting["original"].max()
                        )
                        ** 2
                    ).mean() ** 0.5
        rmse["all input components"] = sum(
            multiplier * rmse[component] for component, multiplier in self.components_to_cluster
        )
        self.rmse = rmse

    def output_df_rmse(self):
        # Combine weights and RMSE for specific grid combo in df
        df_weights = pd.DataFrame(self.grid_combo, index=[0]).add_suffix("_weight")
        df_rmse = pd.DataFrame(self.rmse, index=[0]).add_suffix("_RMSE")
        df_grid_combo = pd.concat([df_weights, df_rmse], axis=1)

        # Add cluster number as first column
        df_clusters = pd.DataFrame({"cluster_number": [self.clusters]})

        return pd.concat([df_clusters, df_grid_combo], axis=1)

    @timer
    def collect_cluster_results(self):
        """
        Collect data and save in dataframe for plotting.
        No return value.
        """
        # Raw data input for all components
        self.prof_raw = pd.DataFrame(
            (
                np.array(
                    [
                        self.dict_profiles[component].values
                        for component in [re[0] for k, v in self.components_to_plot.items() for re in v]
                    ]
                )
            ).T,
            columns=[component for component in [re[0] for k, v in self.components_to_plot.items() for re in v]],
            index=self.dict_profiles[self.components_to_cluster[0][0]].index,  # workaround
        )

        self.prof_raw["month"] = self.prof_raw.index.month
        self.prof_raw["year"] = self.prof_raw.index.year
        self.prof_raw["day"] = self.prof_raw.index.date

        # Selected representative days profile
        self.prof_cluster = self.prof_raw.loc[self.clustered_dates.unique()]

        # Reconstructed 8760 profiles from representative days
        self.prof_8760_cluster = pd.DataFrame(
            np.array(
                [
                    self.clustered_dates.map(self.dict_profiles[component]).values
                    for component in [re[0] for k, v in self.components_to_plot.items() for re in v]
                ]
            ).T,
            columns=[component for component in [re[0] for k, v in self.components_to_plot.items() for re in v]],
            index=pd.to_datetime(self.clustered_dates.index),
        )

        self.prof_8760_cluster["month"] = self.prof_8760_cluster.index.month
        self.prof_8760_cluster["year"] = self.prof_8760_cluster.index.year
        self.prof_8760_cluster["day"] = self.prof_8760_cluster.index.date

    #         print('Raw and cluster-reconstituted profiles collected.')

    ## Results saving and visuals
    def save_cluster_csvs(self):
        """
        Get chrono and dispatch window mapping and save to local.
        """
        df = self.clustered_dates.resample("D").first().reset_index()
        df.columns = ["chrono_period", "dispatch_window"]
        df.to_csv(self.results_folder_name + "/map_to_chrono_periods.csv", index=True)

        # Save chrono and dispatch window
        clustered_dates_format = self.clustered_dates.to_frame()
        clustered_dates_format["dispatch_window"] = clustered_dates_format.resample("D").first()
        clustered_dates_format = clustered_dates_format.fillna(method="ffill")
        clustered_dates_format.columns = ["timestamp", "dispatch_window"]
        clustered_dates_format["include"] = True
        # clustered_dates_format["weight"] = True

        clustered_dates_format = clustered_dates_format.loc[clustered_dates_format["timestamp"].unique(), :]
        clustered_dates_format.to_csv(self.results_folder_name + "/dispatch_windows.csv", index=False)

        map_to_rep_periods = clustered_dates_format.resample("D").first().reset_index()
        map_to_rep_periods = clustered_dates_format.reset_index()
        map_to_rep_periods.columns = ["index", "chrono_period", "dispatch_window", "include"]  # , "weight"]
        map_to_rep_periods.to_csv(self.results_folder_name + "/chrono_periods.csv", index=False)

    #         print(f'Timeseries csvs saved to {self.results_folder_name}.')

    @timer
    def force_rep_days(
        self, extreme_dates, number_of_closest_days
    ):  # extreme_day_indices is position of extreme day in c.clustered_dates -- double check correct day is being selected, e.g. by calling c._compare_daily_peak_load_ranges()
        new_distance = pd.DataFrame(self.distance_matrix, index=self.chrono_periods.index)
        new_distance.index = pd.to_datetime(new_distance.index)

        # find list of closest days
        for extreme_date in extreme_dates:
            closest_days_indices = np.argsort(new_distance.loc[extreme_date].values)[
                0 : number_of_closest_days + 1
            ]  # includes the point itself (distance 0) + n others
            closest_days_dates = self.chrono_periods.index[closest_days_indices]
            logger.info(f"{extreme_date} mapped to {closest_days_dates}")

            # for each in list of closest days, reassign clustered_dates value to extreme_date
            mask = self.clustered_dates.index.normalize().isin(closest_days_dates)  # list of dates to reassign
            self.clustered_dates_force = self.clustered_dates.loc[:]
            self.clustered_dates_force.loc[mask] = pd.to_datetime(extreme_date) + pd.to_timedelta(
                self.clustered_dates_force.loc[mask].index.hour, unit="h"
            )

            # save results again
        df = self.clustered_dates_force.resample("D").first().reset_index()
        df.columns = ["chrono_period", "dispatch_window"]
        df.to_csv(self.results_folder_name + "/map_to_chrono_periods_extreme.csv", index=True)

        # Save chrono and dispatch window
        clustered_dates_format = self.clustered_dates_force.to_frame()
        clustered_dates_format["dispatch_window"] = clustered_dates_format.resample("D").first()
        clustered_dates_format = clustered_dates_format.fillna(method="ffill")
        clustered_dates_format.columns = ["timestamp", "dispatch_window"]
        clustered_dates_format["include"] = True
        # clustered_dates_format["weight"] = True

        clustered_dates_format = clustered_dates_format.loc[clustered_dates_format["timestamp"].unique(), :]
        clustered_dates_format.to_csv(self.results_folder_name + "/dispatch_windows_extreme.csv", index=False)

        map_to_rep_periods = clustered_dates_format.resample("D").first().reset_index()
        map_to_rep_periods = clustered_dates_format.reset_index()
        map_to_rep_periods.columns = ["index", "chrono_period", "dispatch_window", "include"]  # , "weight"]
        map_to_rep_periods.to_csv(self.results_folder_name + "/chrono_periods_extreme.csv", index=False)

    def create_plots(self):
        """Create and save visuals for screening clustering performance"""

        # Direct hourly results comparison between raw and rep-day profiles
        self._compare_clustered_timeseries()

        # Joint distribution charts
        for ld in self.components_to_plot["load"]:
            for re in ["Total_solar", "Total_wind", "Total_LBW", "Total_OSW"]:
                if re in self.prof_raw.columns:
                    self._show_joint_distribution(re, ld[0])

        # # Hydro: check rep-day constituted budget and compare with historical annual availability
        # if "hydro" in self.components_to_plot.keys():
        #     self._check_hydro_budget()

        # Hourly profile shapes for all data in selected months, with rep days overlaid
        self._show_repday_shape([6, 7, 8, 9], "summer")
        self._show_repday_shape([11, 12, 1, 2], "winter")

        # Calendar check: show what months, days, week/weekends the rep days are taken from the full dataset
        self._show_repday_distribution()

        # Peak load box plots to compare rep day peaks to full dataset
        self._compare_daily_peak_load_ranges()

    @timer
    def _compare_clustered_timeseries(self):
        """Create a plotly figure with comparison metrics between original and clustered timeseries and save local.
        TODO: Can add more components than just the ones that were used to cluster on to do this comparison
        TODO: This won't work out of the box with modeled year timeseries.
        """
        with open(self.results_folder_name + "/compare_clustered_ts.html", "a") as f:
            for component, _ in self.components_to_cluster:
                profiles_for_plotting = pd.concat(
                    [self.dict_profiles[component], self.clustered_dates.map(self.dict_profiles[component])], axis=1
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
                        text=f"<b>{component}",
                        x=0.04,
                        y=0.96,
                    ),
                )
                #                 logger.info(f"Saving timeseries comparison to: {component}")
                f.write(
                    fig.to_html(
                        f"{component}new.html",
                        full_html=False,
                        include_plotlyjs="cdn",
                    ),
                )
        #             fig.show()

        f.close()

    def _show_rep_days_8760(self, n_colors=365):
        colors = px.colors.sample_colorscale("IceFire", [n / (n_colors - 1) for n in range(n_colors)])
        colors = pd.Series(colors, index=range(0, 365))
        colors = colors.to_frame(name="colors")
        colors = pd.concat([colors] * 23, axis=0, ignore_index=True)
        colors.index = pd.date_range(start="1/1/1998", freq="D", end="12/31/2020")[
            :-6
        ]  # RL: correct slicing to -6 here

        df = self.clustered_dates.resample("D").first().reset_index()
        df.columns = ["chrono_period", "dispatch_window"]
        df = pd.merge(df, colors, left_on="chrono_period", right_index=True)
        df["Month"] = df["dispatch_window"].dt.month
        df["Day"] = df["dispatch_window"].dt.day
        df = df.sort_values(["Month", "Day"])

        fig = go.Figure(
            data=go.Scatter(
                y=df["chrono_period"],
                x=df["dispatch_window"].dt.strftime("%m/%d/%Y"),
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
            yaxis=dict(
                autorange="reversed", title="<b>Original Date</b>", tickformat="%m/%d/%Y", showgrid=True, dtick="M12"
            ),
            height=12 * 144,
            width=6 * 144,
            margin=dict(
                l=120,
                b=160,
            ),
            font=dict(size=10),
        )
        #         fig.show()
        fig.write_html(self.results_folder_name + "/rep-periods.html")

    def _show_joint_distribution(self, resource_name, load_name):
        """
        Create a joint distribution plot of selected renewable and load.
        """
        f_path = self.results_folder_name + "/Resource-Load Joint Distribution"
        os.makedirs(f_path, exist_ok=True)

        df = pd.concat(
            [
                pd.DataFrame(
                    {
                        "Type": "Original",
                        "RE": self.prof_raw[resource_name].values,
                        "Load": self.prof_raw[load_name].values,
                    }
                ),
                pd.DataFrame(
                    {
                        "Type": "Cluster",
                        "RE": self.prof_8760_cluster[resource_name].values,
                        "Load": self.prof_8760_cluster[load_name].values,
                    }
                ),
            ]
        ).reset_index()

        alpha_map = {"Original": 0.01, "Cluster": 1}

        jointplot = sns.JointGrid()

        for t_type, alpha in alpha_map.items():
            subset = df[df["Type"] == t_type]
            jointplot.ax_joint.scatter(subset["RE"], subset["Load"], alpha=alpha, label=t_type)
        jointplot.ax_joint.legend(loc="best", title="Type")
        jointplot.ax_joint.set_xlabel(resource_name)
        jointplot.ax_joint.set_ylabel(load_name)
        plt.close(jointplot.fig)
        jointplot.fig.savefig(f_path + "/" + resource_name + "_" + load_name + "_joint_distri.png", bbox_inches="tight")

    def _show_repday_location(self):
        """
        Normalized distribution of raw data + location of selected days
        """
        df_raw_byday = self.prof_raw.groupby(["day"]).mean()
        df_cluster_byday = self.prof_cluster.groupby(["day"]).mean()

        f_path = self.results_folder_name + "/Rep Day Location"
        os.makedirs(f_path, exist_ok=True)

        for comp in self.prof_raw.columns:
            if comp not in ["month", "day", "year"]:
                fig, ax = plt.subplots(1, 1, figsize=[14, 3])
                count, bins, ignored = plt.hist(
                    df_raw_byday[comp].values, bins=50, alpha=0.7, color="#FAA0A0", edgecolor="black"
                )

                for clust in df_cluster_byday[comp].items():
                    plt.axvline(clust[1], color="grey", linestyle="--")
                    plt.text(clust[1], count.max() * 1.1, clust[0], color="grey", ha="center", fontsize=8, rotation=90)

                plt.title(f"Raw data vs. representative day: {comp}", loc="left", pad=60)
                plt.xlabel("Daily Average Value")
                plt.ylabel("Frequency")

                fig.tight_layout()
                fig.savefig(f_path + f"/Rep_day_location_{comp}.png")
                plt.close()

    def _show_repday_distribution(self):
        f_path = self.results_folder_name + "/Rep Day Distribution"
        os.makedirs(f_path, exist_ok=True)
        df_daily = self.prof_cluster.resample("D").first().dropna()
        df_daily["day_of_week"] = df_daily.index.dayofweek  # 0 = Monday, 6 = Sunday
        df_daily["month"] = df_daily.index.month  # 1 = January, 12 = December
        df_daily["year"] = df_daily.index.year

        # Create a 3x1 subplot
        fig, axes = plt.subplots(3, 1, figsize=(8, 12))

        day_of_week_counts = df_daily["day_of_week"].value_counts().reindex(range(7), fill_value=0).sort_index()
        day_of_week_counts.plot(kind="bar", ax=axes[0], color="skyblue", edgecolor="black")

        axes[0].set_title("Day of the Week")
        axes[0].set_xticklabels(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        axes[0].set_ylabel("Count")

        # Plot the histogram of the month
        month_counts = df_daily["month"].value_counts().reindex(range(1, 13), fill_value=0).sort_index()

        month_counts.plot(kind="bar", ax=axes[1], color="salmon", edgecolor="black")
        axes[1].set_title("Month of the Year")
        axes[1].set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
        axes[1].set_ylabel("Count")

        # Plot the histogram of the year
        year_counts = df_daily["year"].value_counts().reindex(df_daily["year"].unique(), fill_value=0).sort_index()
        year_counts.plot(kind="bar", ax=axes[2], color="lightgreen", edgecolor="black")
        axes[2].set_title("Year")
        axes[2].set_ylabel("Count")

        # Adjust layout
        plt.tight_layout()
        fig.savefig(f_path + f"/Rep_day_distribution.png")
        plt.close()

    def _show_daily_CF_range(self):
        """
        Range of daily CF (mostly for resources) by month in raw data vs reconstructed 8760.
        """
        f_path = self.results_folder_name + "/CF Range Comparison"
        os.makedirs(f_path, exist_ok=True)

        df_CF_month_raw = self.prof_raw.groupby(["month", "year"]).mean(numeric_only=True).reset_index()
        df_CF_month_min_raw = df_CF_month_raw.groupby(["month"]).min()
        df_CF_month_max_raw = df_CF_month_raw.groupby(["month"]).max()
        df_CF_month_mean_raw = df_CF_month_raw.groupby(["month"]).mean()

        df_CF_month_cluster = self.prof_8760_cluster.groupby(["month", "year"]).mean(numeric_only=True).reset_index()
        df_CF_month_min_cluster = df_CF_month_cluster.groupby(["month"]).min()
        df_CF_month_max_cluster = df_CF_month_cluster.groupby(["month"]).max()
        df_CF_month_mean_cluster = df_CF_month_cluster.groupby(["month"]).mean()

        for comp in self.prof_raw.columns:
            if comp not in ["month", "day", "year"]:
                fig, ax = plt.subplots(1, 1, figsize=[12, 4])
                mon = np.arange(12)
                wid = 0.25

                plt.bar(
                    mon - wid / 2,
                    df_CF_month_max_raw[comp].values - df_CF_month_min_raw[comp].values,
                    bottom=df_CF_month_min_raw[comp].values,
                    width=wid,
                    color="#FAA0A0",
                    alpha=0.8,
                )
                plt.plot(mon - wid / 2, df_CF_month_mean_raw[comp].values, "_k", lw=15)

                plt.bar(
                    mon + wid / 2,
                    df_CF_month_max_cluster[comp].values - df_CF_month_min_cluster[comp].values,
                    bottom=df_CF_month_min_cluster[comp].values,
                    width=wid,
                    color="grey",
                    alpha=0.8,
                )
                plt.plot(mon + wid / 2, df_CF_month_mean_cluster[comp].values, "_k", lw=15)

                ax.spines["top"].set_visible(False)
                ax.spines["right"].set_visible(False)
                ax.spines["bottom"].set_color("grey")
                ax.spines["left"].set_color("grey")
                ax.set_xlabel("Month", fontsize=12)
                ax.set_ylabel("Capacity Factor (%)", fontsize=12)
                ax.yaxis.set_major_formatter(mtick.PercentFormatter(1.0))
                ax.xaxis.set_major_formatter(mtick.StrMethodFormatter("{x:,.0f}"))
                ax.set_xticks(np.arange(0, 12, 1))
                ax.set_yticks(np.arange(0, 1.1, 0.1))
                ax.set_xlim(-0.5, 12)
                ax.set_ylim(df_CF_month_min_raw[comp].min() * 0.9, df_CF_month_max_raw[comp].max() * 1.1)
                ax.tick_params(labelsize=10)
                # ax.grid(axis='y', c = 'grey', alpha = 0.2)

                plt.title(f"Raw data vs. 8760 from representative days range of daily CF by month: {comp}", loc="left")
                plt.rcParams["font.family"] = "Arial"
                plt.legend(["", "", "Original", "Clustered"])

                fig.tight_layout()
                fig.savefig(f_path + f"/Daily_CF_range_{comp}.png")
                plt.close()

    def _compare_daily_peak_load_ranges(self):
        from matplotlib.lines import Line2D

        fig, ax = plt.subplots(figsize=[12, 4])
        sample_day_peaks = []
        all_clustered_day_peaks = []
        for i in (
            self.clustered_dates.resample("D").first().value_counts().index
        ):  # list of clustered days as timestamp objects
            sample_day_peaks.append(self.prof_raw[self.prof_raw.index.date == i.date()].Total_load.max())
            represented_days = self.clustered_dates[self.clustered_dates == i].index.date
            self.prof_raw["dt-date"] = self.prof_raw.index.date
            represented_days_loads = self.prof_raw[self.prof_raw["dt-date"].isin(represented_days)].Total_load
            represented_days_peak_values = represented_days_loads.resample("D").max().dropna()
            all_clustered_day_peaks.append(represented_days_peak_values.tolist())

        x = range(1, len(self.clustered_dates.resample("D").first().value_counts().index) + 1)
        scatter_plot = ax.scatter(x, sample_day_peaks, label="Rep day peak")
        ax.boxplot(all_clustered_day_peaks, positions=x, showfliers=False)

        boxplot_line = Line2D(
            [0], [0], color="black", linewidth=1, linestyle="-", label="Range of peaks for actual days"
        )

        plt.ylabel("Regional peak gross load (MW)")
        plt.xlabel("Rep day")

        handles = [scatter_plot, boxplot_line]
        plt.legend(handles=handles, loc="center left", bbox_to_anchor=(1, 0.5))

        plt.title("Rep day peaks vs Peaks for days represented")
        ax.set_xticklabels(
            self.clustered_dates.resample("D").first().value_counts().index.strftime("%m-%d-%Y"), rotation=90
        )
        f_path = self.results_folder_name + "/Daily Peak Loads"
        os.makedirs(f_path, exist_ok=True)
        fig.tight_layout()
        plt.savefig(f_path + f"/peak_load_ranges.png", bbox_inches="tight")
        plt.close()

    def _show_scaled_CF_comparison(self, resource_name):
        f_path = self.results_folder_name + "/Scaled CF Comparison"
        os.makedirs(f_path, exist_ok=True)

        def test_profile_scaling(scalar, profile, target_cf: float):
            test_profile = copy.deepcopy(profile)
            sampled_cf = test_profile.mean()
            return sampled_cf - target_cf

        # Iterate using Newton method
        scalar = scipy.optimize.newton(
            test_profile_scaling,
            0,
            args=(self.prof_8760_cluster[resource_name].values, self.prof_raw[resource_name].mean()),
            tol=0.004,
            maxiter=10,
            disp=False,
        )
        # Get final profile & CF
        scaled_profile = (self.prof_raw[resource_name] * (1 + scalar)).clip(upper=self.prof_raw[resource_name].max())
        # scaled_profile.to_csv(f_path + f'/test_{resource_name}.csv')

        fig = go.Figure()
        hour = np.arange(0, 288)
        df = pd.DataFrame(
            {"Original": self.prof_raw[resource_name].values, "Rescaled Cluster": scaled_profile.values},
            index=self.prof_raw[resource_name].index,
        )
        df["month"] = df.index.month
        df["hour"] = df.index.hour
        for l in ["Original", "Rescaled Cluster"]:
            fig.add_trace(go.Scatter(x=hour, y=df[l].values, mode="lines", name=l))
        for x, m in zip(
            list(np.arange(0, 288, 24)),
            ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"],
        ):
            fig.add_vline(
                x=x,
                line_dash="dot",
                line_color="grey",
                annotation_text=m,
                annotation_position="top",
                annotation_font_size=16,
            )
        fig.update_layout(
            title_text="Month-Hour Shape",
            xaxis_title="Hour",
            height=450,
            width=900,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font={"family": "Arial", "size": 12},
            showlegend=True,
        )
        fig.write_html(f_path + f"/Month-Hour CF comp_{resource_name}.html")

    def _show_annual_peak_loads(self):
        """
        Range of total gross peak loads in raw data vs reconstructed 8760.
        """

        f_path = self.results_folder_name + "/Peak Loads Comparisons"
        os.makedirs(f_path, exist_ok=True)

        df_annual_peak_raw = self.prof_raw.groupby("year").max(numeric_only=True).reset_index()
        df_annual_peak_cluster = self.prof_8760_cluster.groupby("year").max(numeric_only=True).reset_index()
        fig, ax = plt.subplots(1, 1, figsize=[12, 4])
        width = 0.4
        ax.bar(
            [i - width / 2 for i in range(0, len(df_annual_peak_raw))],
            sorted(df_annual_peak_raw["Total_Load"]),
            alpha=0.5,
            width=width,
        )
        ax.bar(
            [i + width / 2 for i in range(0, len(df_annual_peak_cluster))],
            sorted(df_annual_peak_cluster["Total_Load"]),
            alpha=0.5,
            width=width,
        )
        plt.legend(["Raw", "Clustered"])
        plt.xlabel("Years (ascending)")
        plt.ylabel("Total Annual Peak (MW)")
        fig.tight_layout()
        fig.savefig(f_path + f"/annual_peak_loads.png")

    def _show_repday_shape(self, month_list, season_name):
        """
        For selected month (season), show the range of actual daily shape in raw data vs what we have in representative days
        """
        df_raw_month = self.prof_raw.loc[self.prof_raw["month"].isin(month_list)]
        df_cluster_month = self.prof_cluster.loc[self.prof_cluster["month"].isin(month_list)]

        f_path = self.results_folder_name + "/Rep Day Shape Comparison"
        os.makedirs(f_path, exist_ok=True)

        for comp in self.prof_raw.columns:
            if comp not in ["month", "day", "year"]:
                fig = go.Figure()
                hour = np.arange(0, 24)
                i = 0
                for day in np.unique(df_raw_month.day):
                    i += 1
                    dt_day = df_raw_month.loc[day.strftime("%Y-%m-%d")]
                    fig.add_trace(
                        go.Scatter(
                            mode="lines",
                            x=hour,
                            y=dt_day[comp].values,
                            opacity=0.05,
                            name="Original",
                            text=day.strftime("%Y-%m-%d"),
                            hoverinfo="text",
                            marker_color="#FAA0A0",
                            showlegend=(i == 1),
                        )
                    )

                i = 0
                for day in np.unique(df_cluster_month.day):
                    i += 1
                    dt_day = df_cluster_month.loc[day.strftime("%Y-%m-%d")]
                    fig.add_trace(
                        go.Scatter(
                            mode="lines",
                            x=hour,
                            y=dt_day[comp].values,
                            opacity=0.7,
                            name="Clustered",
                            text=day.strftime("%Y-%m-%d"),
                            hoverinfo="text",
                            marker_color="grey",
                            showlegend=(i == 1),
                        )
                    )

                fig.update_layout(
                    title_text=f"Raw data vs. representative day daily shape in month {month_list[0]}-{month_list[-1]}: {comp}",
                    xaxis_title="Hour",
                    xaxis=dict(
                        tickmode="array",
                        tickvals=[0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22],
                    ),
                    # yaxis_range=[0, 1],
                    # yaxis=dict(tickformat=".0%"),
                    height=300,
                    width=1000,
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font={"family": "Arial", "size": 12},
                )

                fig.update_xaxes(showline=True, linewidth=1, linecolor="black", ticks="outside")
                fig.update_yaxes(showline=True, linewidth=1, linecolor="black", ticks="outside")

                fig.write_html(f_path + f"/Daily_shape_comp_{comp}_{season_name}.html")

    def _check_hydro_budget(self):
        # UPDATE
        # this function needs a lot of checks
        f_path = self.results_folder_name + "/Hydro Budget Check"
        os.makedirs(f_path, exist_ok=True)

        annual_avg_budget = {}
        self.dict_profiles["Total_solar"] = sum(
            self.weighting_portfolio.loc[comp].values * self.dict_profiles[comp] for comp in self.solar_component
        )

        total_hydro_magnitude = sum([self.weighting_portfolio.loc[comp].values for comp in self.hydro_components])
        component = "Total_Hydro_Normalized"

        annual_avg_budget[component + " Cluster"] = []
        annual_avg_budget[component + " Original"] = []

        monthly_profile_original = (
            self.dict_profiles[component].resample("M").mean()
        )  # this is hourly "average daily budget"
        monthly_profile_clustered = self.clustered_dates.map(self.dict_profiles[component]).resample("M").mean()

        profiles_for_plotting = pd.concat([monthly_profile_original, monthly_profile_clustered], axis=1)
        profiles_for_plotting.columns = ["original", "clustered"]
        profiles_for_plotting["year"] = profiles_for_plotting.index.year
        profiles_for_plotting["month"] = profiles_for_plotting.index.month

        # plot 1: reconstituted all 23 years
        df_budget_byyr = profiles_for_plotting.groupby(["year"]).mean(numeric_only=True).reset_index()
        byyr_min = df_budget_byyr.groupby(["year"]).min()
        byyr_max = df_budget_byyr.groupby(["year"]).max()
        fig, ax = plt.subplots(1, 1, figsize=[12, 4])
        yr = profiles_for_plotting["year"].unique()
        plt.scatter(
            yr,
            (df_budget_byyr["clustered"].values - df_budget_byyr["original"].values)
            / df_budget_byyr["original"].values,
            color="red",
            marker="o",
        )
        plt.hlines(xmin=min(yr), xmax=max(yr), y=0, color="grey", linestyle="--")

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color("grey")
        ax.spines["left"].set_color("grey")
        ax.set_xlabel("Weather Year", fontsize=12)
        ax.set_ylabel("Average Monthly Budget (Clustered - original, %)", fontsize=12)
        ax.tick_params(labelsize=10)

        plt.title(f"8760 from rep days minus Raw data: difference in average monthly budget: {component}", loc="left")
        plt.rcParams["font.family"] = "Arial"
        fig.savefig(f_path + f"/Hydro_budget_{component}_weather_year_comparison.png")
        plt.close()

        annual_avg_budget[component + " Cluster"].append(monthly_profile_clustered.mean())
        annual_avg_budget[component + " Original"].append(monthly_profile_original.mean())

        # plot 2: final 8760 average
        rep_days_mean = pd.DataFrame(
            self.dict_profiles[component].loc[self.clustered_dates.unique()].resample("D").mean().dropna()
        )
        rep_days_mean.columns = ["Daily mean"]
        rep_days_mean["Month"] = rep_days_mean.index.month

        df_budget_bymon = profiles_for_plotting.groupby(["month"]).mean(numeric_only=True).reset_index()
        df_budget_bymon_min = profiles_for_plotting.groupby(["month"]).min(numeric_only=True).reset_index()
        df_budget_bymon_max = profiles_for_plotting.groupby(["month"]).max(numeric_only=True).reset_index()
        fig, ax = plt.subplots(1, 1, figsize=[12, 4])
        mon = profiles_for_plotting["month"].unique()
        wid = 0.25

        plt.bar(
            mon,
            (df_budget_bymon_max["original"].values - df_budget_bymon_min["original"].values)
            * 24
            * total_hydro_magnitude,
            bottom=df_budget_bymon_min["original"].values * 24 * total_hydro_magnitude,
            width=wid,
            color="#FAA0A0",
            alpha=0.8,
        )
        plt.plot(mon, df_budget_bymon["clustered"].values * 24 * total_hydro_magnitude, "^r", lw=50)
        plt.scatter(
            rep_days_mean["Month"].values,
            rep_days_mean["Daily mean"].values * 24 * total_hydro_magnitude,
            s=None,
            c=None,
            marker="_",
        )  # c=rep_days_mean['Daily mean'].values

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_color("grey")
        ax.spines["left"].set_color("grey")
        ax.set_xlabel("Month", fontsize=12)
        ax.set_ylabel("Average Daily Budget (MWh)", fontsize=12)
        ax.tick_params(labelsize=10)

        plt.title(f"Historical Monthly Budget vs Reconstituted Sample Days: {component}", loc="left")
        plt.rcParams["font.family"] = "Arial"

        fig.tight_layout()
        fig.savefig(f_path + f"/Hydro_budget_{component}_bymon.png")
        plt.close()

        pd.DataFrame(annual_avg_budget).to_csv(f_path + f"/Hydro_average_daily_budget_bymon.csv")


class DaySamplingSystem:
    """
    System for day sampling with support for grid search, extreme day selection, and resource profile handling.
    """

    clusters: dict[str, DaySamplingClusterer] = {}

    def __init__(
        self,
        dir_str: DirStructure,
        case_name: str = None,
        system_name: str = None,
    ):
        self.dir_str = dir_str
        self.inputs_dir = dir_str.data_settings_dir.joinpath("resolve")
        self.system_dir = dir_str.data_interim_dir.joinpath("systems")
        self.case_name = case_name
        self.system_name = system_name

    def input_selection(self):
        """
        Select a case and system for clustering analysis.
        A case represent selected scenario tags;
        A system represent underlying resource, load, and zone definitions.
        """
        case_list = [pathlib.Path(d).name for d in glob.glob(str(self.inputs_dir / "*")) if pathlib.Path(d).is_dir()]
        system_list = [pathlib.Path(d).name for d in glob.glob(str(self.system_dir / "*")) if pathlib.Path(d).is_dir()]

        case_selector = widgets.Dropdown(
            options=case_list,
            description="Select a case:",
            style={"description_width": "initial"},
            layout={"width": "50%"},
            rows=min(len(case_list), 10),
        )
        sys_selector = widgets.Dropdown(
            options=system_list,
            description="Select a system:",
            tooltip="testttttt",
            style={"description_width": "initial"},
            layout={"width": "50%"},
        )
        yr_selector = widgets.BoundedFloatText(
            value=2035,
            min=2020,
            max=2070,
            step=5,
            description="Select target year:",
            style={"description_width": "initial"},
            layout={"width": "50%"},
            disabled=False,
        )
        start_weather_selector = widgets.BoundedFloatText(
            value=2015,
            min=1950,
            max=2070,
            step=1,
            description="Specify start weather year:",
            style={"description_width": "initial"},
            layout={"width": "50%"},
        )
        end_weather_selector = widgets.BoundedFloatText(
            value=2019,
            min=1950,
            max=2070,
            step=1,
            description="Specify end weather year:",
            style={"description_width": "initial"},
            layout={"width": "50%"},
        )

        label = widgets.HTML(
            """
            <b style="color:#034E6E;">Note:</b><br>
            <span style="color:#034E6E;">
                • A <b>case</b> specifies the scenario tags to be included.<br>
                • A <b>system</b> defines the underlying components, such as resources and load profiles.<br>
                • <b>Target year</b> is relevant for (1) if you want to assign initial weights to resources before sampling (see more details in the "load_resource_weights" section below) and (2) scaling load profiles to selected year. <br>
                • <i>All zones included in the case will be considered. If you want to focus on a single zone and its associated resources and load, be sure to define a case that includes only that zone</i>
            </span>
            """
        )
        butt = widgets.Button(description="Save Selection")
        outt = widgets.Output()

        def _collect_case_name(a):
            with outt:
                clear_output()
                self.case_name = case_selector.value
                self.system_name = sys_selector.value
                self.model_year = int(yr_selector.value)
                self.weather_years = (int(start_weather_selector.value), int(end_weather_selector.value))
                print("Input Selection Saved")

                outputs_dir = self.dir_str.results_dir.joinpath(f"day_sampling/{self.system_name}")
                os.makedirs(outputs_dir, exist_ok=True)
                self.outputs_dir = outputs_dir

        butt.on_click(_collect_case_name)
        display(
            widgets.VBox(
                [
                    label,
                    case_selector,
                    sys_selector,
                    yr_selector,
                    start_weather_selector,
                    end_weather_selector,
                    butt,
                    outt,
                ]
            )
        )

    def load_prep_data(self):
        """
        Relies on system constructing functions here to access all information from a kit system.
        """
        self.resolve_settings_dir = self.inputs_dir / self.case_name
        self.scenarios = pd.read_csv(self.resolve_settings_dir / "scenarios.csv")["scenarios"].tolist()

        _, system_instance = System.from_csv(
            filename=self.system_dir / self.system_name / "attributes.csv",
            scenarios=self.scenarios,
            data={"dir_str": self.dir_str, "model_name": "resolve"},
        )
        setattr(self, "system", system_instance)
        self.wind_component = list(self.system.wind_resources.keys()) + [
            k for k, v in self.system.wind_resource_groups.items() if v.aggregate_operations
        ]
        self.solar_component = list(self.system.solar_resources.keys()) + [
            k for k, v in self.system.solar_resource_groups.items() if v.aggregate_operations
        ]
        self.hydro_component = list(self.system.hydro_resources.keys()) + [
            k for k, v in self.system.hydro_resource_groups.items() if v.aggregate_operations
        ]
        self.load_component = list(self.system.loads.keys())

        print("Day Sampling System uploaded")
        if self.wind_component:
            print(f"Wind Resources: {self.wind_component}")
        if self.solar_component:
            print(f"Solar Resources: {self.solar_component}")
        if self.hydro_component:
            print(f"Hydro Resources: {self.hydro_component}")
        if self.load_component:
            print(f"Loads: {self.load_component}")

    def _upload_portfolio_csv(self, path):
        df_group = pd.read_csv(io.BytesIO(path))[["Resource", "Modeled Year", "Weight"]]
        df_group["Modeled Year"] = pd.to_datetime(df_group["Modeled Year"]).dt.year
        df_group["Modeled Year"] = df_group["Modeled Year"].astype("Int64")
        df_group = df_group[df_group["Modeled Year"] == self.model_year].drop(columns=["Modeled Year"])
        df_group = df_group.reset_index(drop=True).set_index("Resource")
        self.weighting_portfolio = df_group

        print("Weighting portfolio for target year uploaded.")
        pd.set_option("display.max_rows", len(self.weighting_portfolio))
        display(self.weighting_portfolio)

    def _create_ones_weighting(self):
        ind = self.wind_component + self.solar_component + self.hydro_component
        df = pd.DataFrame(np.ones(len(ind)), index=ind)
        df.columns = ["Operational Capacity (MW)"]
        df.index.name = "Resource"
        self.weighting_portfolio = df

    def load_resource_weights(self):
        label = widgets.HTML(
            """
            <span style="color:#034E6E; font-family: Arial, sans-serif; font-size: 14px;">
                Upload a <b>pre-determined resource weighting matrix</b> if you wish to provide initial weighting to selected resources. <br>
                File must be a .csv with columns "Resource", "Modeled Year", and "Weight".<br>
                Modeled Year should include target year specified in input_selection above.<br>
                E.g., For CPUC IRP, resources with higher capacity in target year are treated as of “higher priority”. <br>

                <i>❗ If left unchecked, all components will be assigned an initial weight of 1.</i><br>
                <i>❗ This only applies to resource components. Load components will be scaled by peak/energy forecasts only.</i>
            </span>
            """
        )
        select = widgets.Checkbox(description="Load matrix?", disabled=False, indent=False)
        butt = widgets.Button(description="Save Selection")
        outt = widgets.Output()

        def _set_portfolio(a):
            with outt:
                clear_output()
                if select.value == True:
                    clear_output()
                    w_portfolio = widgets.FileUpload(multiple=False)

                    def _upload_portfolio(b):
                        uploaded = w_portfolio.value[0].content
                        self._upload_portfolio_csv(uploaded)

                    w_portfolio.observe(_upload_portfolio, names="value")
                    display(w_portfolio)
                else:
                    clear_output()
                    self._create_ones_weighting()
                    print("All resources have initial weighting of one.")

        butt.on_click(_set_portfolio)
        display(widgets.VBox([label, select, butt, outt]))

    def _create_combined_profile(self):
        ## calculate total wind, solar, hydro generation for plotting purpose later
        self.dict_profiles["Total_solar"] = sum(
            self.weighting_portfolio.loc[comp].values * self.dict_profiles[comp] for comp in self.solar_component
        )
        self.dict_profiles["Total_wind"] = sum(
            self.weighting_portfolio.loc[comp].values * self.dict_profiles[comp] for comp in self.wind_component
        )
        if self.hydro_component:
            self.dict_profiles["Total_hydro"] = sum(
                self.weighting_portfolio.loc[comp].values * self.dict_profiles[comp] for comp in self.hydro_component
            )
        self.dict_profiles["Total_RE"] = self.dict_profiles["Total_solar"] + self.dict_profiles["Total_wind"]
        self.dict_profiles["Total_load"] = sum(self.dict_profiles[key] for key in self.load_component)
        ## calculate net loads
        self.dict_profiles["Net_Load"] = self.dict_profiles["Total_load"] - self.dict_profiles["Total_RE"]

    def load_profiles_input(self):
        """
        Load the profiles and construct an accessible dictionary based on defined system.
        """
        self.dict_profiles = {}

        if self.wind_component + self.solar_component:
            logger.info(f"Loading renewable profiles...")
        else:
            logger.info(f"No renewable profiles to load")
        for re in self.wind_component + self.solar_component:
            resource = self.system.resources.get(re) or self.system.resource_groups.get(re)
            resource.resample_ts_attributes(
                modeled_years=(self.model_year, self.model_year),
                weather_years=self.weather_years,
                resample_weather_year_attributes=False,
            )
            if resource:
                self.dict_profiles[re] = resource.power_output_max.data
            else:
                try:
                    path = self.dir_str.data_interim_dir.joinpath("custom_profiles")
                    df = pd.read_csv(path + f"{re}.csv", index_col=0, parse_date=True).squeeze("columns")
                except FileNotFoundError:
                    logger.info(
                        f"{re} is in initial portfolio but not part of selected system. No profiles defined in data/custom_profiles folder"
                    )

        if self.hydro_component:
            logger.info(f"Loading hydro profiles...")
        else:
            logger.info(f"No hydro profiles to load")
        for re in self.hydro_component:
            resource = self.system.resources.get(re) or self.system.resource_groups.get(re)
            resource.resample_ts_attributes(
                modeled_years=(self.model_year, self.model_year),
                weather_years=self.weather_years,
            )
            if resource:
                energy_budget_profile = (
                    resource.energy_budget_daily or resource.energy_budget_monthly or resource.energy_budget_annual
                ).data
                energy_budget_hourly = energy_budget_profile.resample("H").ffill()
                self.dict_profiles[re] = energy_budget_hourly
            else:
                try:
                    path = self.dir_str.data_interim_dir.joinpath("custom_profiles")
                    df = pd.read_csv(path + f"{re}.csv", index_col=0, parse_date=True).squeeze("columns")
                except FileNotFoundError:
                    logger.info(
                        f"{re} is in initial portfolio but not part of selected system. No profiles defined in data/custom_profiles folder"
                    )

        if self.load_component:
            logger.info(f"Loading load profiles...")
        else:
            logger.info(f"No load profiles to load")
        for ld in self.load_component:
            if ld in self.system.loads.keys():
                load = self.system.loads[ld]
                load.resample_ts_attributes(
                    modeled_years=(self.model_year, self.model_year),
                    weather_years=self.weather_years,
                )
                load.forecast_load(
                    modeled_years=(self.model_year, self.model_year),
                    weather_years=self.weather_years,
                )
                self.dict_profiles[ld] = load.model_year_profiles[self.model_year].data
            else:
                try:
                    path = self.dir_str.data_interim_dir.joinpath("custom_profiles")
                    df = pd.read_csv(path + f"{ld}.csv", index_col=0, parse_date=True).squeeze("columns")
                except FileNotFoundError:
                    logger.info(
                        f"{ld} is in initial portfolio but not part of selected system. No profiles defined in data/custom_profiles folder"
                    )

        # Truncate profile to be only overlapped periods:
        logger.info(f"Truncating profiles to use only overlapped weather year data ...")
        common_index = set(self.dict_profiles[next(iter(self.dict_profiles))].index)
        for series in self.dict_profiles.values():
            common_index &= set(series.index)
        common_index = pd.DatetimeIndex(sorted(common_index))
        if len(common_index) != 0:
            for key in self.dict_profiles:
                self.dict_profiles[key] = self.dict_profiles[key].loc[common_index]
            logger.info(
                f" -- Used overlapping profile from: {common_index[0]} to {common_index[-1]}, with length equal to {len(common_index)}"
            )
        else:
            logger.info(f"-- No overlapped periods in profiles, double check your input!")

        # Apply initial weights on load
        logger.info(f"Applying initial weights on components ...")
        self.weighting_load = pd.DataFrame(
            [
                {
                    "Load": key,
                    "Med Peak (MW)": self.dict_profiles[key].groupby(self.dict_profiles[key].index.year).max().median(),
                }
                for key in self.load_component
            ]
        )

        ## apply initial weights on resources and create combined profile (e.g. total solar)
        self._create_combined_profile()
        logger.info(f"\nAll profiles loaded.")

    def check_correlation(self):
        # create output folder first if not exist yet
        path = self.outputs_dir.joinpath("Correlation check")
        if not os.path.exists(path):
            os.mkdir(path)

        logger.info(f"Calculating correlation and saving heatmaps saved to folder: {path}")
        for attr in ["wind", "solar", "hydro", "load"]:
            correlation_components = getattr(self, attr + "_component")
            # get a list of components by category
            dict_temp = {}
            for component in correlation_components:
                dict_temp[component] = self.dict_profiles[component]

            # calculate correlation df
            dfCorrelation = pd.DataFrame.from_dict(dict_temp)
            correlation_matrix = dfCorrelation.corr()
            setattr(self, attr + "_correlation", correlation_matrix)

            # produce heat map
            if correlation_components:
                self._plot_corr_heatmap(correlation_matrix, attr, path)

    def _plot_corr_heatmap(self, correlation_matrix, attr, path):
        text = np.round(correlation_matrix.values, 2).astype(str)
        heatmap = go.Figure(
            data=go.Heatmap(
                z=correlation_matrix.values,
                x=correlation_matrix.columns,
                y=correlation_matrix.columns,
                colorscale="Greens",
                colorbar=dict(title="Correlation Coefficient"),
                text=text,
                texttemplate="%{text}",
            )
        )

        heatmap.update_layout(
            title=f"Correlation Heatmap - {attr}", xaxis=dict(title="Variables"), yaxis=dict(title="Variables")
        )
        heatmap.show()
        heatmap.write_html(path / f"{attr}_correlation.html")

    def remove_redundant_component(self):
        """
        Define a threshold above which you would remove certain components since it's highly correlated with other components in the system.
        """
        label = widgets.HTML(
            """
            <div style="color: #034E6E; font-family: Arial; line-height: 1.6; font-size: 14px;">
                Note that you can set threshold at 1 to retain all features in the catetory. <br>
            </div>
            """
        )
        wind_th_selector = widgets.BoundedFloatText(
            value=0.9,
            min=0,
            max=1,
            step=0.05,
            description="Wind components: ",
            disabled=False,
            style={"description_width": "initial"},
            layout={"width": "50%"},
        )
        solar_th_selector = widgets.BoundedFloatText(
            value=0.9,
            min=0,
            max=1,
            step=0.05,
            description="Solar components: ",
            disabled=False,
            style={"description_width": "initial"},
            layout={"width": "50%"},
        )
        hydro_th_selector = widgets.BoundedFloatText(
            value=0.9,
            min=0,
            max=1,
            step=0.05,
            description="Hydro components: ",
            disabled=False,
            style={"description_width": "initial"},
            layout={"width": "50%"},
        )
        load_th_selector = widgets.BoundedFloatText(
            value=0.9,
            min=0,
            max=1,
            step=0.05,
            description="Load components: ",
            disabled=False,
            style={"description_width": "initial"},
            layout={"width": "50%"},
        )

        butt = widgets.Button(
            description="Save threshold definition", style={"description_width": "initial"}, layout={"width": "50%"}
        )
        outt = widgets.Output()

        def _apply_threshold(a):
            with outt:
                clear_output()
                # do this one category at a time
                self.consolidated_input = pd.concat(
                    [
                        self.weighting_load.reset_index()
                        .drop(columns=["index"])
                        .set_axis(["Component", "Size"], axis=1),
                        self.weighting_portfolio.reset_index().set_axis(["Component", "Size"], axis=1),
                    ]
                ).set_index("Component")
                #
                # for attr in ['wind', 'solar', 'hydro', 'load']:
                #     component_correlation = getattr(self, attr + '_correlation', None)
                #     component_th_selector = getattr(self, attr + '_th_selector', None)
                #     if component_correlation:
                #         self._consolidate_features(component_correlation, component_th_selector.value, attr)

                self._consolidate_features(self.wind_correlation, wind_th_selector.value, "wind")
                self._consolidate_features(self.solar_correlation, solar_th_selector.value, "solar")
                self._consolidate_features(self.hydro_correlation, hydro_th_selector.value, "hydro")
                self._consolidate_features(self.load_correlation, load_th_selector.value, "load")
                # keep final features where there are profiles
                # TODO: revisit this logic later
                self.consolidated_input = self.consolidated_input.loc[
                    self.consolidated_input.index.intersection(list(self.dict_profiles.keys()))
                ]

        butt.on_click(_apply_threshold)
        display(
            widgets.VBox([label, wind_th_selector, solar_th_selector, hydro_th_selector, load_th_selector, butt, outt])
        )

    def _consolidate_features(self, df_corr, threshold, attr):
        # Calculate the correlation matrix

        if threshold == 1:
            print(f"Keep all components for {attr} components give threshold = 1.")
            print("-" * 20)
            setattr(self, f"{attr}_to_consider", getattr(self, f"{attr}_component", []))
            return

        features_to_drop = set()
        for i in range(len(df_corr.columns)):
            for j in range(i):
                if abs(df_corr.iloc[i, j]) > threshold:
                    feature1 = df_corr.columns[i]
                    feature2 = df_corr.columns[j]
                    magnitude1 = self.consolidated_input.loc[feature1].values
                    magnitude2 = self.consolidated_input.loc[feature2].values

                    # Keep the feature with the higher operational magnitude
                    if magnitude1 > magnitude2:
                        features_to_drop.add(feature2)
                        self.consolidated_input.loc[feature1] += magnitude2
                    else:
                        features_to_drop.add(feature1)
                        self.consolidated_input.loc[feature2] += magnitude1

        remaining_features = [feature for feature in df_corr.columns if feature not in features_to_drop]
        setattr(self, f"{attr}_to_consider", remaining_features)

        self.consolidated_input = self.consolidated_input.drop(list(features_to_drop))

        drop_sorted = sorted(features_to_drop)
        remain_sorted = sorted(remaining_features)
        drop_str = ", ".join(drop_sorted) if drop_sorted else "(none)"
        remain_str = ", ".join(remain_sorted) if remain_sorted else "(none)"

        print(f"Features to drop for {attr} components:")
        print(f"  - {drop_str}")
        print(f"Remaining features for {attr} components:")
        print(f"  - {remain_str}")
        print("-" * 20)

    def design_clustering_param(self):
        tab_contents = ["# of Rep days", "Include Hydro Input?", "Weather year to use", "OSW vs. LBW?"]
        children = [
            widgets.VBox(
                [
                    widgets.HTML(
                        """
                    <div style="color: #034E6E; font-family: Arial; line-height: 1.6; font-size: 14px;">
                        Select the # of rep days you'd like to select.<br>
                        • You can specify any amount between 10 to 365 days in the box.<br><br>
                    </div>
                    """
                    ),
                    widgets.BoundedFloatText(
                        value=36,
                        min=10,
                        max=365,
                        step=1,
                        description="Input number of representative days:",
                        style={"description_width": "initial"},
                        layout={"width": "75%"},
                        disabled=False,
                        indent=False,
                    ),
                ]
            ),
            widgets.VBox(
                [
                    widgets.HTML(
                        """
                    <div style="color: #034E6E; font-family: Arial; line-height: 1.6; font-size: 14px;">
                        Whether to include hydro in the representative day selection process depends on the specific needs of your project.<br>
                        By checking this box, the clustering algorithm will account for hydro performance, which may interfere with the selection of representative renewable days.</div>
                    """
                    ),
                    widgets.Checkbox(
                        value=False,
                        description="Click to include Hydro in clustering process",
                        style={"description_width": "initial"},
                        layout={"width": "75%"},
                        disabled=False,
                        indent=False,
                    ),
                ]
            ),
            widgets.VBox(
                [
                    widgets.HTML(
                        """
                    <div style="color: #034E6E; font-family: Arial; line-height: 1.6; font-size: 14px;">
                        We generally default to include all weather year data in selection, but you can also zoom into a couple weather years specified in this box.<br></div>
                    """
                    ),
                    widgets.Text(
                        value="",
                        description="Specify weather year to cluster on (otherwise leave as blank):",
                        placeholder="Enter years separated by comma (e.g., 2015, 2018, 2020)",
                        style={"description_width": "initial"},
                        layout={"width": "75%"},
                        disabled=False,
                    ),
                ]
            ),
            widgets.VBox(
                [
                    widgets.HTML(
                        """
                    <div style="color: #034E6E; font-family: Arial; line-height: 1.6; font-size: 14px;">
                        In the case when onshore and offshore wind generation is very different in the region, specify the offshore wind resources in the list so that clusterer can calculate error metrics for them seperately.<br></div>
                    """
                    ),
                    widgets.SelectMultiple(
                        options=self.wind_to_consider,
                        description="Specify OSW resources: ",
                        style={"description_width": "initial"},
                        layout={"width": "75%"},
                    ),
                ]
            ),
        ]
        tab = widgets.Tab(style={"description_width": "initial"}, layout={"width": "100%"})
        tab.children = children
        tab.titles = tab_contents

        butt = widgets.Button(description="Save Selection")
        outt = widgets.Output()

        def _collect_input(a):
            with outt:
                clear_output()
                print("Clustering parameters saved")
                self.rep_days = int(tab.children[0].children[1].value)
                print(f"  - Number of representative days: {self.rep_days}")
                if tab.children[1].children[1].value:
                    self.hydro_flag = True
                    print("  - Hydro resources included")
                else:
                    self.hydro_flag = False
                    dropped_hydro = [hy for hy in self.hydro_component if hy in self.consolidated_input.index]
                    self.hydro_to_consider = list(set(self.hydro_to_consider) - set(dropped_hydro))
                    self.consolidated_input = self.consolidated_input.drop(dropped_hydro)
                    print("  - No Hydro resources included")
                if tab.children[2].children[1].value == "":
                    self.weather_years_to_use = []
                    print("  - All weather years included")
                else:
                    self.weather_years_to_use = [int(x) for x in tab.children[2].children[1].value.split(",")]
                    print(f"  - Only weather years {self.weather_years_to_use} included")
                if len(tab.children[3].children[1].value) > 0:
                    self.OSW_to_consider = list(tab.children[3].children[1].value)
                    self.LBW_to_consider = list(set(self.wind_to_consider) - set(self.OSW_to_consider))
                    self.dict_profiles["Total_LBW"] = sum(
                        self.weighting_portfolio.loc[comp].values * self.dict_profiles[comp]
                        for comp in self.LBW_to_consider
                    )
                    self.dict_profiles["Total_OSW"] = sum(
                        self.weighting_portfolio.loc[comp].values * self.dict_profiles[comp]
                        for comp in self.OSW_to_consider
                    )
                    print(f"  - LBW resources specified as {self.LBW_to_consider}")
                    print(f"  - OS resources specified as {self.OSW_to_consider}")
                else:
                    self.OSW_to_consider = []
                    self.LBW_to_consider = []
                    print("  - No offshore wind resources specified")

        butt.on_click(_collect_input)
        display(widgets.VBox([tab, butt, outt]))

    def _build_weight_selector(self, label):
        return widgets.Text(
            value="",
            placeholder="Enter a list of weights w/o space (e.g., 1,3,6,9,15,20)",
            description=f"{label}: ",
            disabled=False,
            style={"description_width": "initial"},
            layout={"width": "50%"},
        )

    def set_grid_search_range(self):
        self._set_weight_ui(mode="grid_search")

    def set_extreme_days_weights(self):
        self._set_weight_ui(mode="extreme_days")

    def _set_weight_ui(self, mode):
        is_grid_search = mode == "grid_search"
        desc_html = {
            "grid_search": """
                <span style="color:#034E6E; font-family: Arial, sans-serif; font-size: 14px;">
                    This is where you specify <b>a range of weights by resource category</b> to influence the behavior of the clustering process.<br>
                    <i>Note: This is different from the initial weights assigned to individual resources...</i>
                </span>
            """,
            "extreme_days": """
                <span style="color:#034E6E; font-family: Arial, sans-serif; font-size: 14px;">
                    This is where you specify the (range of) weights by resource category <b>to include extreme days.</b> <br>
                    <i>Note: You can only input weights for which you <b>already ran the grid search step</b> for above.</i>
                </span>
            """,
        }

        label = widgets.HTML(desc_html[mode])
        selectors = {
            "OSW": self._build_weight_selector("OSW"),
            "LBW": self._build_weight_selector("LBW"),
            "wind": self._build_weight_selector("Wind"),
            "solar": self._build_weight_selector("Solar"),
            "hydro": self._build_weight_selector("Hydro"),
            "load": self._build_weight_selector("Load"),
        }

        # Build which components to show
        keys_to_show = []
        if len(self.OSW_to_consider) > 0:
            keys_to_show += ["OSW", "LBW"]
        else:
            keys_to_show += ["wind"]

        keys_to_show += ["solar"]
        if self.hydro_flag:
            keys_to_show += ["hydro"]
        keys_to_show += ["load"]

        selectors_list = [selectors[k] for k in keys_to_show]

        butt = widgets.Button(
            description=(
                "Save list of weights (by component) for grid searching..."
                if is_grid_search
                else "Save list of weights (by component) for extreme day selection..."
            ),
            style={"description_width": "initial"},
            layout={"width": "50%"},
        )
        outt = widgets.Output()

        display(widgets.VBox([label, *selectors_list, butt, outt]))

        def _apply_weights(_):
            with outt:
                clear_output()
                target_dict = {}

                if any(selectors[k].value == "" for k in keys_to_show):
                    raise ValueError("At least one weight value must be specified for each category.")

                for k in selectors:
                    if k in keys_to_show:
                        try:
                            target_dict[k] = [float(x) for x in selectors[k].value.split(",")]
                        except ValueError:
                            raise ValueError(f"Invalid entry in {k}: must be comma-separated integers.")
                        print(f"  - {k}: {target_dict[k]}")
                    else:
                        target_dict[k] = []

                if is_grid_search:
                    self.grid_search_weight_dict = target_dict
                else:
                    # Validate that weights are subset of weights in grid search
                    for key in target_dict:
                        if not set(target_dict[key]).issubset(self.grid_search_weight_dict[key]):
                            raise ValueError(f"Weights must have already run through the grid search.")
                    self.extreme_days_weight_dict = target_dict

                print("Weights saved for", "grid search" if is_grid_search else "extreme days")

        butt.on_click(_apply_weights)

    def run_grid_search(self):

        # Get grid search parameter ranges
        keys = list(self.grid_search_weight_dict.keys())  # e.g., ['solar', 'wind', 'load', etc.]
        values = list(self.grid_search_weight_dict.values())
        values = [v if v else [0] for v in values]  # default to 0 if list is empty
        grid_combos = [dict(zip(keys, combo)) for combo in product(*values)]  # list of all parameter combinations

        # Initialize results dataframe for all grid_combos
        df_rmse_search = pd.DataFrame()

        for grid_combo in grid_combos:
            df_rmse_search = pd.concat(
                [
                    df_rmse_search,
                    self._run_single_grid_combo_results(grid_combo),
                ],
                ignore_index=True,
            )

        # Save all RMSE grid combo results to csv
        df_rmse_search.to_csv(str(self.outputs_dir) + "/rmse_for_all_combo.csv")
        logger.info(f"RMSE results saved in: reports/day_sampling/{self.system.name}/rmse_for_all_combo.csv")

    def _run_single_grid_combo_results(self, grid_combo: dict[str, float]):
        grid_combo_name = "-".join(f"{k}_{v}" for k, v in grid_combo.items())

        nonzero_weights = ", ".join(f"{k}: {v}" for k, v in grid_combo.items() if v != 0)
        logger.info(f"Running grid search for {nonzero_weights}")

        # Create results directory
        results_path = str(self.outputs_dir) + "/" + grid_combo_name + f"_{self.rep_days}_repperiods"
        os.makedirs(results_path, exist_ok=True)

        # Get components for DaySamplingClusterer inputs
        components_to_cluster, components_to_plot = self._get_cluster_components(grid_combo)

        # Initiate clustering engine
        cluster = DaySamplingClusterer(
            name=grid_combo_name,
            grid_combo=grid_combo,
            components_to_cluster=components_to_cluster,
            components_to_plot=components_to_plot,
            weather_years_to_use=self.weather_years_to_use,
            rep_period_length="1D",  # daily clustering
            clusters=self.rep_days,
            dict_profiles=self.dict_profiles,
            results_folder_name=results_path,
            random_state=1730482,
        )

        # Run and output results
        df_single_grid_combo_rmse = self._run_and_extract_cluster(cluster)

        self.clusters[grid_combo_name] = cluster

        logger.info(
            f"Results saved in folder: Day Sampling Analysis/{self.system.name}/{grid_combo_name}/_{self.rep_days}_repperiods/"
        )
        return df_single_grid_combo_rmse

    def _get_cluster_components(self, grid_combo: dict[str, float]):
        weighted_components = self.consolidated_input.copy(deep=True)
        components_to_cluster = []
        components_to_plot = {}

        # Apply category weights
        for cat in ["LBW", "OSW", "wind", "hydro", "solar", "load"]:
            components = getattr(self, f"{cat}_to_consider", [])
            if len(components) != 0:
                weighted_components.loc[components] *= grid_combo[cat]
                total_cat = [(f"Total_{cat}", weighted_components.loc[components].sum())]
                components_to_cluster += list(weighted_components.loc[components].itertuples(index=True, name=None))
                components_to_plot[cat] = (
                    list(weighted_components.loc[components].itertuples(index=True, name=None)) + total_cat
                )
        # Additional components to plot
        components_to_plot = {**components_to_plot, "Other": [("Total_RE", 1), ("Net_Load", 1)]}

        return components_to_cluster, components_to_plot

    def _run_and_extract_cluster(self, cluster: DaySamplingClusterer):
        # Spinning up clusters
        cluster.get_clusters()
        # Collect rep day results
        cluster.collect_cluster_results()
        # Save dispatch window, chrono periods mapping to csvs
        cluster.save_cluster_csvs()
        # Calculate RMSE stats and save
        cluster.calculate_rmse()
        # Create and save plots for screening clustering performance if specified
        cluster.create_plots()

        return cluster.output_df_rmse()

    def set_extreme_days_param(self):
        # saves self.extreme_dates: list[str] and self.num_extreme_days: int
        date_selector = widgets.Text(
            value="",
            placeholder="e.g., 2020-01-01, 2021-02-18",
            description="Extreme Dates:",
            style={"description_width": "initial"},
            layout={"width": "80%"},
        )
        num_extreme_selector = widgets.BoundedIntText(
            value=1,
            min=1,
            max=self.rep_days,
            step=1,
            description="Num Extreme Days:",
            style={"description_width": "initial"},
            layout={"width": "40%"},
        )
        butt = widgets.Button(
            description="Save Selection",
            style={"description_width": "initial"},
            layout={"width": "40%"},
        )
        outt = widgets.Output()
        display(widgets.VBox([date_selector, num_extreme_selector, butt, outt]))

        def _apply_selection(_):
            with outt:
                clear_output()
                # Parse date list input
                try:
                    extreme_dates = [x.strip() for x in date_selector.value.split(",") if x.strip()]
                    self.extreme_dates = extreme_dates
                    print(f"Saved extreme days list: {self.extreme_dates}")
                except ValueError:
                    print("⚠️ Error: Invalid date format. Use YYYY-MM-DD, comma-separated.")
                    return

                # Save number of extreme days
                self.num_extreme_days = num_extreme_selector.value
                print(f"Saved number of extreme days: {self.num_extreme_days}")

        butt.on_click(_apply_selection)

    def force_extreme_days(self):
        # Get grid search parameter ranges
        keys = list(self.extreme_days_weight_dict.keys())  # e.g., ['solar', 'wind', 'load', etc.]
        values = list(self.extreme_days_weight_dict.values())
        values = [v if v else [0] for v in values]  # default to 0 if list is empty
        grid_combos = [dict(zip(keys, combo)) for combo in product(*values)]  # list of all parameter combinations

        for grid_combo in grid_combos:
            grid_combo_name = "-".join(f"{k}_{v}" for k, v in grid_combo.items())

            nonzero_weights = ", ".join(f"{k}: {v}" for k, v in grid_combo.items() if v != 0)
            logger.info(f"Manually including extreme dates for weights = {nonzero_weights}")

            c = self.clusters[grid_combo_name]
            c.force_rep_days(self.extreme_dates, self.num_extreme_days)
