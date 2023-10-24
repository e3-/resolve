from typing import Any
from typing import Optional

import kmedoids
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from loguru import logger
from plotly.subplots import make_subplots
from pydantic import Field
from resolve.core.component import Component
from resolve.core.custom_model import CustomModel
from resolve.core.utils.core_utils import timer
from sklearn.metrics.pairwise import euclidean_distances


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
