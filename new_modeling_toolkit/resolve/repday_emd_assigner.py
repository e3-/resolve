import datetime
import itertools
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

import numpy as np
import ot
import pandas as pd
import plotly.express as px
from loguru import logger
from plotly.graph_objs import Figure
from plotly.subplots import make_subplots

__all__ = ["RepdayToDayofyearEmdAssigner"]


# Module for representative day assignment to
# approximate netload over one vintage year using Earth Mover Distance (EMD).


class RepdayToDayofyearEmdAssigner:
    """
    Optimize representative day assignment using Earth Mover Distance (EMD).

    Representative days (repdays) are a small set of weather dates D that are used to proxy an entire hourly history of some quantity of interest over multiple weather years.
    Here the quantity of interest is netload, and `profile netload` refers to the hourly scalar netload for all weather years (e.g., 23 years).
    Selection of representative days is out of scope; we assume that the representative days are provided as input.
    The `dispatched netload` is a (derived) single year of hourly netload to stand for netload in a specific vintage year, and as a reasonable approximation across all weather years.
    On each date of the dispatch netload (1..365) there is chosen a representative day (from D), and netload from that weather date is appended into the dispatch.

    The optimization computes a mapping from day of the year to representative day, that is M : 1..365 -> D.
    The optimization finds a choice of M, such that the dispatched netload is as close as possible to the profile netload across all weather years.
    (The 1-year dispatch is repeated across weather years to construct the comparison.)

    LIMITATION: Leap years are not handled in this implementation.

    When a repday is chosen that is far in the year from the day that it is proxying, there are concerns about the validity of the proxy.
    The class includes a mechanism to prevent this by limiting the day-of-year difference to 45 days.

    The settings for one optimization consist of a specific choice for each of the following:
    - vintage year
    - EMD cost metric (e.g., cityblock, euclidean, sqeuclidean)
    - whether to force integer representative day weights
    - penalty for day-of-year differences
    - day-of-year difference limit
    - window length of rep segment  [this mechanism* is not used in the current implementation]

    Window mechanism* anticipates needing to evaluate mappings M on the basis of their multi-day properties, not fully implemented here.

    Repday inputs include associated weights that represent their proportion in the entire year, and the optimization respects these weights in mapping M.
    Analysts can choose to force the weights to be integers, in which case M is one-to-one.
    If the weights are not forced to be integers, M is one-to-many, and the weights are allowed to be fractional.
    For example, on day-of-year 355, M(355) = {D1, D2} with weights {0.7, 0.3} means that on day 355 of the dispatch netload, D1 netload should be appended with probability 0.7 and D2 netload should be appended with probability 0.3.

    The class provides for arrays of settings, so that multiple optimizations can be run and compared.

    Args:
        write_dir: Directory to write output files.
        repday_path: Path to CSV file containing representative day information.
        netload_input_files: List of CSV files with hourly netload data for each vintage year.
        units_str: String representing the units of netload (e.g., "MW").
        one_case: If True, use a single set of hyperparameters for analysis. If False, search over multiple settings.

    Attributes:
        emd_cost_metrics: List of distance metrics to use for EMD.
        force_int_repweights_choices: Whether to force integer representative day weights.
        day_difference_penalties: Penalties for day-of-year differences.
        dayofyear_difference_limits: Maximum allowed day-of-year difference.
        window_days: Duration of repday mapped segments.
        data: Aligned netload data.
        repday_df: Representative day dataframe.
    """

    def __init__(
        self,
        write_dir: Union[str, Path],
        repday_path: Union[str, Path],
        netload_input_files: List[Union[str, Path]],
        units_str: str,
        one_case: bool = True,
    ) -> None:
        self.write_dir = Path(write_dir)
        self.netload_input_files = netload_input_files
        self.repday_path = Path(repday_path)
        self.units_str = units_str
        self.one_case = one_case

        if self.one_case:
            # Settings used for CPUC analysis in May 2025.
            self.emd_cost_metrics = ["cityblock"]
            self.force_int_repweights_choices = [True]
            self.day_difference_penalties = [0.5]
            self.dayofyear_difference_limits = [30]
            self.window_days = 1
        else:
            # Search over different hyperparameters settings.
            # emd_cost_metrics can be "cityblock", "euclidean", "sqeuclidean" , cityblock corresponds to MAE
            self.emd_cost_metrics = [
                "cityblock",
            ]
            self.force_int_repweights_choices = [True, False]
            self.day_difference_penalties = [0.0, 0.5]
            # Disengage (0.0) or engage (any float > 0.0) dayofyear_difference_limit
            self.dayofyear_difference_limits = [30, 45]
            self.window_days = 1
        self.data = self.align_netload_data()
        self.repday_df = self.get_repday_df()

    def align_netload_data(self) -> pd.DataFrame:
        """
        Ingest and align netload data from CSV files for processing.

        Returns:
            pd.DataFrame: Aligned netload data with columns for weather year, vintage year, month, date, hour, and netload.
        """
        data_frames = []

        for case, info in self.netload_input_files.items():
            file_path = Path(info["fpath"])
            raw_data = pd.read_csv(file_path)
            raw_data["timestamp"] = pd.to_datetime(pd.DatetimeIndex(raw_data["timestamp"]))
            raw_data["weather_year"] = raw_data["timestamp"].dt.year
            raw_data["vintage_year"] = int(info["output_year"])
            raw_data["month"] = raw_data["timestamp"].dt.month
            raw_data["date"] = raw_data["timestamp"].dt.date
            raw_data["hour"] = raw_data["timestamp"].dt.hour
            raw_data.rename(columns={info["target_variable"]: "netload"}, inplace=True)
            data_frames.append(raw_data[["weather_year", "vintage_year", "month", "date", "hour", "netload"]])

        data = pd.concat(data_frames, ignore_index=True)
        data.sort_values(by=["date", "hour", "vintage_year"], inplace=True)
        d0 = data["date"].iloc[0]
        data["window_idx"] = pd.TimedeltaIndex(data["date"] - d0).days % self.window_days
        data["window_idx"] = data["window_idx"].astype("int")
        return data

    @staticmethod
    def generate_heatmap(matrix: np.ndarray, repdays: List[datetime.date], title: str) -> Figure:
        """
        Generate and return a heatmap for the given matrix.

        Args:
            matrix: The cost matrix.
            repdays: List of representative days (dates).
            title: Title of the heatmap.

        Returns:
            Figure: Plotly Figure object.
        """
        # Convert repdays to day-of-year and sort
        repdays_labels = [
            f"({date.timetuple().tm_yday:03d}) " + date.strftime("%Y-%m-%d") + " " for date in repdays
        ]  # Format as text labels

        # Create a DataFrame for the heatmap
        df = pd.DataFrame(matrix, index=repdays_labels, columns=range(1, matrix.shape[1] + 1))
        df.sort_index(inplace=True)

        # Generate heatmap
        fig = px.imshow(
            df,
            labels=dict(x="Day of Year", y="Repday", color="Cost"),
            title=title,
            x=df.columns,
            y=df.index,
            color_continuous_scale="Viridis",
        )
        # Set font sizes for title and axes
        fig.update_layout(
            title_font_size=22,
            xaxis_title_font_size=18,
            yaxis_title_font_size=18,
            font=dict(size=14),
        )
        return fig

    @staticmethod
    def generate_heatmap_with_marginals(matrix: np.ndarray, repdays: List[datetime.date], title: str) -> Figure:
        """
        Generate and return a heatmap for the given matrix with marginal sums on top and right.

        Args:
            matrix: The cost matrix.
            repdays: List of representative days (dates).
            title: Title of the heatmap.

        Returns:
            Figure: Plotly Figure object with heatmap and marginals.
        """
        # Prepare labels
        repdays_labels = [f"({date.timetuple().tm_yday:03d}) " + date.strftime("%Y-%m-%d") + " " for date in repdays]
        df = pd.DataFrame(matrix, index=repdays_labels, columns=range(1, matrix.shape[1] + 1))
        df.sort_index(inplace=True, ascending=False)

        df0 = df.copy() / df.sum().sum() * matrix.shape[1]  # Normalize the matrix to sum to 1 per column (i.e. 365)
        # Marginals
        row_sums = df0.sum(axis=1)
        col_sums = df0.sum(axis=0)

        # Create subplots: 2 rows, 2 cols, shared axes
        fig = make_subplots(
            rows=2,
            cols=2,
            column_widths=[0.85, 0.15],
            row_heights=[0.15, 0.85],
            shared_xaxes=True,
            shared_yaxes=True,
            horizontal_spacing=0.02,
            vertical_spacing=0.02,
            specs=[[{"type": "xy"}, {"type": "xy"}], [{"type": "heatmap"}, {"type": "xy"}]],
        )

        # Top marginal (column sums)
        fig.add_trace(
            px.bar(x=df0.columns, y=col_sums, labels={"x": "Day of Year", "y": "Weight"}).data[0], row=1, col=1
        )

        # Right marginal (row sums)
        fig.add_trace(
            px.bar(y=df0.index, x=row_sums, orientation="h", labels={"y": "Repday", "x": "Weight"}).data[0],
            row=2,
            col=2,
        )

        # Heatmap
        heatmap = px.imshow(
            df0, labels=dict(x="Day of Year", y="Repday", color="Cost"), color_continuous_scale="Viridis"
        ).data[0]
        fig.add_trace(heatmap, row=2, col=1)

        # Hide unused subplot (top-right)
        fig.update_xaxes(visible=False, row=1, col=2)
        fig.update_yaxes(visible=False, row=1, col=2)

        # Layout adjustments
        fig.update_layout(
            title=title,
            title_font_size=22,
            xaxis2_title="Sum1",
            yaxis1_title="Weight",
            font=dict(size=14),
            showlegend=False,
        )
        # Hide axes for marginals
        fig.update_xaxes(showticklabels=False, row=1, col=1)
        fig.update_xaxes(showticklabels=False, row=2, col=2)
        fig.update_yaxes(showticklabels=False, row=2, col=2)
        fig.update_yaxes(showticklabels=False, row=1, col=1)
        # Set axes titles for main heatmap
        fig.update_xaxes(title_text="Day of Year", row=2, col=1)
        fig.update_yaxes(title_text="Repday", row=2, col=1)
        return fig

    def get_repday_df(self, max_repdays: int = 100) -> pd.DataFrame:
        """
        Load representative day information from a CSV file.

        Rep day information consists of a list of representative days and their corresponding weights.
        The weights express the target proportion each date should be present in an assignment.

        Returns:
            pd.DataFrame: DataFrame with representative day information and weights.
        """

        try:
            sample_day_df = pd.read_csv(
                self.repday_path,
                parse_dates=[
                    "Rep Days",
                ],
                dayfirst=False,
            )
            sample_day_df = sample_day_df[["Weights", "Rep Days"]].dropna(how="any", axis=0)
            logger.info("Reading pre-calculated repday weights.")
        except ValueError:
            logger.info("Calculating repday weights from repday file.")
            df = pd.read_csv(self.repday_path)
            if {"chrono_period", "dispatch_window"}.issubset(set(df.columns)):
                chrono_per_col = "chrono_period"
                dispatch_window_col = "dispatch_window"
                dayfirst = False
            elif {"Rep Period", "Chrono Period"}.issubset(set(df.columns)):
                chrono_per_col = "Chrono Period"
                dispatch_window_col = "Rep Period"
                dayfirst = False
            sample_day_df = pd.read_csv(self.repday_path, parse_dates=[dispatch_window_col], dayfirst=dayfirst)[
                [dispatch_window_col, chrono_per_col]
            ]
            sample_day_df = sample_day_df.sort_values(by=[chrono_per_col, dispatch_window_col]).drop_duplicates(
                subset=[chrono_per_col, dispatch_window_col]
            )
            df = sample_day_df.groupby(dispatch_window_col).count()
            df["Weights"] = df[chrono_per_col] / df[chrono_per_col].sum()
            sample_day_df = df.sort_index().reset_index()[["Weights", dispatch_window_col]]
            sample_day_df.rename(columns={dispatch_window_col: "Rep Days"}, inplace=True)
        num_rep_days = sample_day_df.shape[0]
        if num_rep_days > max_repdays:
            logger.warning(
                f"Number of rep days ({num_rep_days}) exceeds max_repdays ({max_repdays}). Check the repday input file: {self.repday_path}"
            )

        return sample_day_df

    def get_dayofyear_repday_maps(
        self, vintage_years: Optional[List[int]] = None
    ) -> List[Dict[Tuple[str, bool, float, int], Dict[str, Any]]]:
        """
        Run the representative day assignment for a set of vintage years.

        Args:
            vintage_years: List of vintage years to process. If None, uses all available.

        Returns:
            List of assignment results for each vintage year.
        """
        vintage_years = vintage_years or self.data["vintage_year"].unique()
        vintage_years = sorted(vintage_years)

        result_list = []
        for vintage_year in vintage_years:
            logger.info(f"Beginning day assignment for vintage year {vintage_year}")
            results_dict, error_report_df = self.optimize_repday_distribution(self.repday_df, vintage_year)
            result_list.append(results_dict)

        return result_list

    def optimize_repday_distribution(
        self, repday_df: pd.DataFrame, vintage_year: int
    ) -> Tuple[Dict[Tuple[str, bool, float, int], Dict[str, Any]], pd.DataFrame]:
        """
        Solve representative day assignment using EMD for various cost metrics and day-difference penalties.

        Args:
            repday_df: Representative day DataFrame.
            vintage_year: The vintage year to process.

        Returns:
            Tuple of:
                - Dictionary of results keyed by (cost_metric, force_integer_repweights, dayofyear_difference_penalty, dayofyear_difference_limit).
                - DataFrame summarizing error reports.
        """

        vy_netload_doy_by_wyh, rep_netload_repdate_by_h = self.align_profile_and_rep_netload(repday_df, vintage_year)
        complete_wys = vy_netload_doy_by_wyh.columns.get_level_values("weather_year").unique()
        num_weather_years = len(complete_wys)

        rep_netload_repdate_by_wyh = pd.concat((rep_netload_repdate_by_h for _ in range(num_weather_years)), axis=1)

        total_days = vy_netload_doy_by_wyh.shape[0]
        rep_wt_df = (
            pd.DataFrame(index=rep_netload_repdate_by_wyh.index).join(
                repday_df[["Weights", "Rep Days"]].rename(columns={"Rep Days": "date"}).set_index("date")
            )
            * total_days
        )

        results_dict = {}
        error_reports = []

        for force_integer_repweights in self.force_int_repweights_choices:
            P_data = rep_netload_repdate_by_wyh.to_numpy()
            P_wts_df = rep_wt_df / rep_wt_df.sum(axis=0)
            Q_data = vy_netload_doy_by_wyh.to_numpy()
            Q_wts_df = pd.DataFrame(index=vy_netload_doy_by_wyh.index, data={"Weights": 1.0})
            Q_wts = (Q_wts_df / Q_wts_df.sum()).to_numpy()

            if force_integer_repweights:
                P_wts_df = self.force_int_total(P_wts_df, int(rep_wt_df.iloc[:, 0].sum(axis=0).round()))
            P_wts_df /= P_wts_df.sum(axis=0)
            P_wts = P_wts_df.to_numpy()

            # Flattened loop using itertools.product for all combinations
            for cost_metric, dayofyear_difference_penalty, dayofyear_difference_limit in itertools.product(
                self.emd_cost_metrics, self.day_difference_penalties, self.dayofyear_difference_limits
            ):

                logger.info(
                    f"\nOptimizing rep day assignment using Earth Mover Distance (EMD, Wasserstein-1). \nSettings:\n  {vintage_year=}\n  {dayofyear_difference_penalty=}\n  {dayofyear_difference_limit=}\n  {num_weather_years=}\n  {repday_df.shape=}\n  {P_data.shape=}\n  {Q_data.shape=}"
                )

                cost_matrix = ot.dist(P_data, Q_data, metric=cost_metric)
                cost_matrix /= P_data.shape[1]  # Converts cityblock to MAE, euclidean to RMSE, sqeuclidean to MSE
                cost_scale = cost_matrix.ravel().max()
                large_dayofyear_difference_mask = self.get_day_angle_mask(
                    dayofyear_difference_limit, vy_netload_doy_by_wyh, rep_netload_repdate_by_wyh
                )

                cost_matrix_with_penalty = (
                    cost_matrix + dayofyear_difference_penalty * cost_scale * large_dayofyear_difference_mask
                )
                solver_em_dist_value, em_plan = ot.emd2(
                    P_wts.ravel(),
                    Q_wts.ravel(),
                    cost_matrix_with_penalty,
                    return_matrix=True,
                )
                em_transportplan_G = em_plan["G"]
                penalized_em_distance_value = (em_transportplan_G * cost_matrix_with_penalty).ravel().sum()
                # Distance A: penalized_em_distance_value is a valid EM distance w.r.t a penalizing two-factor cost metric
                assert np.isclose(
                    solver_em_dist_value, penalized_em_distance_value
                ), "Solver EMD value does not match explicit re-calculation of transport plan value."
                em_distance_value = (em_transportplan_G * cost_matrix).ravel().sum()
                # Distance B: em_distance_value is a valid EM distance w.r.t the specified cost metric selected by the user
                # When asserting probabilistic bounds arising from EMD when using plan G, the inequality should refer to distance B, not A.
                logger.info(
                    f"OT solution has {cost_metric}-EMD= {em_distance_value:.4f} ({self.units_str}) (and penalized-{cost_metric}-EMD= {penalized_em_distance_value:.4f})."
                )

                day_difference_penalty_str = str(int(round(100 * dayofyear_difference_penalty))) + "pc"
                case_name_detail = f"{vintage_year}_metric_{cost_metric}_penalty_{day_difference_penalty_str}_{int(dayofyear_difference_limit)}d_forceint_{force_integer_repweights}"
                # Generate heatmaps
                fig_cost_matrix_with_penalty = self.generate_heatmap(
                    cost_matrix_with_penalty,
                    rep_netload_repdate_by_h.index,
                    "Cost+Penalty to assign Repday to Day of Year, Heatmap",
                )
                # Save the heatmap as an HTML file
                plot_path = self.write_dir / (f"cost_matrix_with_penalty_heatmap_{case_name_detail}.html")
                fig_cost_matrix_with_penalty.write_html(plot_path)

                fig1 = self.generate_heatmap(
                    cost_matrix, rep_netload_repdate_by_h.index, "Cost to assign Repday to Day of Year, Heatmap"
                )
                # Save the heatmap as an HTML file
                plot_path = self.write_dir / (f"cost_matrix_heatmap_{case_name_detail}.html")
                fig1.write_html(plot_path)

                fig_ot_marginals = self.generate_heatmap_with_marginals(
                    em_transportplan_G,
                    rep_netload_repdate_by_h.index,
                    f"Transport Plan for OT solution with {cost_metric}-EMD= {em_distance_value:.4f} ({self.units_str})",
                )
                # Save the heatmap as an HTML file
                plot_path = self.write_dir / (f"transport_plan_{case_name_detail}.html")
                fig_ot_marginals.write_html(plot_path)

                em_transportplan_G_df = pd.DataFrame(em_transportplan_G, index=P_wts_df.index, columns=Q_wts_df.index)
                em_transportplan_G_df = em_transportplan_G_df.fillna(0)
                em_transportplan_G_df = em_transportplan_G_df.clip(lower=0)
                em_transportplan_G_df = em_transportplan_G_df.div(em_transportplan_G_df.sum(axis=0), axis=1)
                em_transportplan_G_df = em_transportplan_G_df.round(4)

                df = (em_transportplan_G_df > 0).sum(axis=0).value_counts()
                df.index.name = "#repdays assigned"
                df.name = "count daysofyear"
                assignment_count_histogram = df.to_frame()
                num_repday_probs = assignment_count_histogram.index.max()
                logger.info(f"EMD solution has up to {num_repday_probs} repdays for some daysofyear.")
                logger.info(f"\nReport on EMD solution:  assignment_count_histogram=\n  {assignment_count_histogram}")

                map_doy_repday_pr_df0 = em_transportplan_G_df.apply(
                    lambda x: [
                        *zip(
                            x.nlargest(num_repday_probs).index.strftime("%Y-%m-%d").tolist(),
                            x.nlargest(num_repday_probs).tolist(),
                        )
                    ],
                    axis=0,
                ).T

                map_doy_repdays = map_doy_repday_pr_df0.applymap(lambda x: x[0]).add_prefix("repday_")
                map_doy_probs = map_doy_repday_pr_df0.applymap(lambda x: x[1]).add_prefix("prob_")
                map_doy_repday_pr_df = pd.concat(
                    (
                        pd.DataFrame(index=map_doy_repday_pr_df0.index, data={"vintage_year": vintage_year}),
                        map_doy_repdays,
                        map_doy_probs,
                    ),
                    axis=1,
                )

                dayofyear0 = map_doy_repday_pr_df.index.to_numpy()
                rep_doy_df = pd.DataFrame(index=map_doy_repday_pr_df.index)
                for repday_col in map_doy_repday_pr_df.filter(like="repday_").columns:
                    doy = pd.DatetimeIndex(map_doy_repday_pr_df[repday_col]).dayofyear.to_numpy()
                    day_diff = (doy - dayofyear0) % 365
                    day_diff = np.minimum(day_diff, 365 - day_diff)
                    rep_doy_df[repday_col + "_daydelta"] = day_diff

                logger.info(
                    f"\nWith {force_integer_repweights=}, {dayofyear_difference_penalty=}, {dayofyear_difference_limit=} \nresults in {num_repday_probs=} and dayofyear deltas distributed as:\n{rep_doy_df.describe().astype(int)=}"
                )

                p_df0 = map_doy_repday_pr_df.drop(columns=["vintage_year"])
                repday_sample_df_list = []
                for weather_year in complete_wys:
                    r_cols = p_df0.filter(like="repday_").columns.to_numpy()
                    p_cols = p_df0.filter(like="prob_").columns.to_numpy()

                    repdays = p_df0.apply(
                        lambda row: np.random.choice(
                            row.loc[r_cols].to_numpy(), p=row.loc[p_cols].astype(float).to_numpy()
                        ),
                        axis=1,
                    )
                    repday_sample_df0 = pd.DataFrame(
                        index=repdays.index, data={"weather_year": weather_year, "date": repdays}
                    )
                    repday_sample_df_list.append(repday_sample_df0.copy())
                repday_sample_df = pd.concat(repday_sample_df_list, axis=0, ignore_index=False)

                repday_sample_df = repday_sample_df.set_index("weather_year", append=True)
                repday_sample_df.index = repday_sample_df.index.swaplevel()
                repday_sample_df.sort_index(inplace=True)
                repday_sample_df["date"] = pd.DatetimeIndex(repday_sample_df["date"])
                rep_netload_repdate_by_h.index = pd.DatetimeIndex(rep_netload_repdate_by_h.index)
                dispatched_netload_df = repday_sample_df.join(
                    rep_netload_repdate_by_h["netload"], on="date", rsuffix="_repday"
                )
                dispatched_netload_df0 = dispatched_netload_df.drop(columns="date")
                profile_netload_df = vy_netload_doy_by_wyh["netload"].stack("weather_year")
                profile_netload_df.index = profile_netload_df.index.swaplevel()
                profile_netload_df.sort_index(inplace=True)
                error_report_df0 = self.error_aggregation_report(
                    profile_netload_df,
                    dispatched_netload_df0,
                    {
                        "cost_metric": cost_metric,
                        "force_integer_repweights": force_integer_repweights,
                        "dayofyear_difference_penalty": dayofyear_difference_penalty,
                        "dayofyear_difference_limit": dayofyear_difference_limit,
                    },
                )
                error_reports.append(error_report_df0)
                # avg_day_peak = error_report_df0
                avg_day_peak_valley = (
                    error_report_df0.set_index(["aggregation", "statistic"])
                    .round(8)
                    .loc["all_weather_days", "mean"][["profile_day_peak", "profile_day_valley"]]
                )
                overall_mae = (profile_netload_df - dispatched_netload_df0).abs().mean().mean().round(8)
                logger.info(f"MAE of dispatched netload vs profile netload = {overall_mae} ({self.units_str})")

                dispatched_netload_vy = dispatched_netload_df0.groupby("dayofyear").mean()
                dispatched_netload_vy.columns = profile_netload_df.columns
                dispatched_netload_vy = dispatched_netload_vy.stack("hour").to_frame(
                    name=f"Netload ({self.units_str}) {vintage_year}"
                )
                dispatched_netload_vy.sort_index(inplace=True)
                profile_netload_df = profile_netload_df.stack("hour").unstack("weather_year")
                profile_netload_df.sort_index(inplace=True)

                dispatched_vs_profile_netload_df = pd.concat(
                    (dispatched_netload_vy, profile_netload_df.add_prefix("wy-")), axis=1
                )

                net_load_col = dispatched_vs_profile_netload_df.filter(like="Netload").columns[0]
                wy_maes = [
                    (dispatched_vs_profile_netload_df[net_load_col] - dispatched_vs_profile_netload_df[wy]).abs().mean()
                    for wy in dispatched_vs_profile_netload_df.filter(like="wy-")
                ]

                avg_wy_maes = sum(wy_maes) / len(wy_maes)
                logger.info(f"MAE (2) of dispatched netload vs profile netload = {avg_wy_maes:.4f} ({self.units_str})")

                fig = self.visualize_netload_discrepancy(vintage_year, dispatched_vs_profile_netload_df)
                result_tuple = {
                    "map_doy_repday_pr_df": map_doy_repday_pr_df,
                    "em_distance_value": em_distance_value,
                    "penalized_em_distance_value": penalized_em_distance_value,
                    "wy_maes": dict(zip(dispatched_vs_profile_netload_df.filter(like="wy-").columns, wy_maes)),
                    "avg_wy_maes": avg_wy_maes,
                    "profile_day_peak_avg": avg_day_peak_valley["profile_day_peak"],
                    "profile_day_valley_avg": avg_day_peak_valley["profile_day_valley"],
                    "error_report_df": error_report_df0,
                    "dispatched_netload_df": dispatched_netload_df,
                    "profile_netload_df": profile_netload_df,
                    "dispatched_vs_profile_netload_df": dispatched_vs_profile_netload_df,
                    "fig_netload_discrepancy": fig,
                    "fig_cost_matrix_with_penalty": fig_cost_matrix_with_penalty,
                    "fig_ot_marginals": fig_ot_marginals,
                }
                results_dict[
                    (cost_metric, force_integer_repweights, dayofyear_difference_penalty, dayofyear_difference_limit)
                ] = result_tuple

                fpath_map = self.write_dir / (f"emd_repday_map_vy_{case_name_detail}.csv")
                map_doy_repday_pr_df.to_csv(fpath_map, float_format="%.4f")
                logger.info(
                    f"Rep day mapping for vintage year {vintage_year}, cost_metric {cost_metric}, and penalty {dayofyear_difference_penalty}_{int(dayofyear_difference_limit)}days saved to \n    file:///{str(fpath_map).replace(' ', '%20')}"
                )
                ddoy_ser = pd.Series(
                    index=map_doy_repday_pr_df.index,
                    data=(pd.DatetimeIndex(map_doy_repday_pr_df["repday_0"]).dayofyear - map_doy_repday_pr_df.index),
                )
                ddoffset_abs = np.minimum(365 - ddoy_ser, ddoy_ser)
                day_offset_compliance = (ddoffset_abs <= dayofyear_difference_limit).value_counts()
                day_offset_compliance.name = "day_difference_compliance"
                results_dict[
                    (cost_metric, force_integer_repweights, dayofyear_difference_penalty, dayofyear_difference_limit)
                ].update({day_offset_compliance.name: int(day_offset_compliance.loc[True])})

                fpath_compliance = self.write_dir / (f"day_offset_compliance_vy_{case_name_detail}.csv")
                day_offset_compliance.to_csv(fpath_compliance, index=True)
                logger.info(
                    f"Day offset compliance for vintage year {vintage_year}, cost_metric {cost_metric}, and penalty {dayofyear_difference_penalty}_{int(dayofyear_difference_limit)}days saved to \n    file:///{str(fpath_compliance).replace(' ', '%20')}"
                )

                fpath_dispatched = self.write_dir / (f"dispatched_vs_profile_netload_vy_{case_name_detail}.csv")
                dispatched_vs_profile_netload_df.to_csv(fpath_dispatched, float_format="%.4f", index=True)
                logger.info(
                    f"Trace comparison for vintage year {vintage_year}, cost_metric {cost_metric}, and penalty {dayofyear_difference_penalty}_{int(dayofyear_difference_limit)}days saved to \n    file:///{str(fpath_dispatched).replace(' ', '%20')}"
                )

                plot_path = self.write_dir / (f"dispatched_vs_profile_netload_vy_{case_name_detail}.html")
                fig.write_html(plot_path)
                logger.info(
                    f"Plot for vintage year {vintage_year}, cost_metric {cost_metric}, and penalty {dayofyear_difference_penalty}_{int(dayofyear_difference_limit)}days saved to \n    file:///{str(plot_path).replace(' ', '%20')}"
                )
            # ...existing code...
        error_report_df = pd.concat(error_reports, axis=0, ignore_index=True)
        fpath = self.write_dir / f"emd_repday_error_report_vintage_{vintage_year}.csv"
        error_report_df.to_csv(fpath, float_format="%.4f", index=False)

        return results_dict, error_report_df

    def get_day_angle_mask(
        self,
        dayofyear_difference_limit: int,
        profile_netload_doy_by_wyh: pd.DataFrame,
        rep_netload_repdate_by_wyh: pd.DataFrame,
    ) -> np.ndarray:
        """
        Create a mask indicating inadmissible combinations of representative days and days of year.

        Args:
            dayofyear_difference_limit: Maximum allowed day-of-year difference.
            profile_netload_doy_by_wyh: Profile netload by day of year and weather year for a specific vintage year.
            rep_netload_repdate_by_wyh: Netload by representative day.

        Returns:
            np.ndarray: 2D mask array (1 for inadmissible, 0 for admissible).
        """
        two_pi = 2 * 3.14159
        p_doy = pd.DatetimeIndex(rep_netload_repdate_by_wyh.index).dayofyear.to_numpy().reshape((-1, 1)) / 365 * two_pi
        q_doy = profile_netload_doy_by_wyh.index.to_numpy().reshape((-1, 1)) / 365 * two_pi
        angle_delta = abs(p_doy - q_doy.T) % two_pi
        angle_delta = np.minimum(angle_delta, (two_pi - angle_delta))
        angle_days = angle_delta / two_pi * 365
        angle_mask = np.where(angle_days > dayofyear_difference_limit, 1, 0)
        return angle_mask

    def align_profile_and_rep_netload(
        self, sample_day_df: pd.DataFrame, vintage_year: int
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Align profile netload data with representative day data for a specific vintage year.

        Args:
            sample_day_df (pd.DataFrame): Representative day DataFrame.
            vintage_year (int): The vintage year to process.

        Returns:
            Tuple of:
                - Profile netload: 1 row per day of year, one column for each (hour of day, weather year) pair.
                - Representative day netload: 1 row per repday, one column for every hour of day (24).
        """
        self.data["dayofyear"] = pd.DatetimeIndex(self.data["date"]).dayofyear
        data1 = self.data.loc[
            self.data["vintage_year"] == vintage_year, ["dayofyear", "weather_year", "hour", "netload"]
        ].set_index(["dayofyear", "weather_year", "hour"])
        data1 = data1.sort_index()
        data1 = data1.loc[(slice(1, 365),), :]  # suppress leap years
        s = data1.index.to_series().groupby("weather_year").count()
        complete_wys = s.index[s == 8760]  # proceed with complete weather years only
        data1 = data1.loc[(slice(None), complete_wys), :]
        profile_netload_dayofyear_by_wyh = data1.unstack(["weather_year", "hour"])
        profile_netload_dayofyear_by_wyh.sort_index(inplace=True)

        data2 = self.data.loc[
            self.data["vintage_year"] == vintage_year, ["date", "dayofyear", "weather_year", "hour", "netload"]
        ]
        data3 = data2.loc[data2["date"].isin(pd.DatetimeIndex(sample_day_df["Rep Days"]).date), :]

        rep_netload_repdate_by_h = data3[["date", "hour", "netload"]].set_index(["date", "hour"]).sort_index()
        rep_netload_repdate_by_h = rep_netload_repdate_by_h.unstack(["hour"]).sort_index()
        return profile_netload_dayofyear_by_wyh, rep_netload_repdate_by_h

    def visualize_netload_discrepancy(
        self, vintage_year: int, dispatched_vs_profile_netload_df: pd.DataFrame
    ) -> Figure:
        """
        Visualize dispatched vs. profile netload data for a specific vintage year.

        Args:
            vintage_year: The vintage year to visualize.
            dispatched_vs_profile_netload_df: DataFrame with dispatched and profile netload data.

        Returns:
            Figure: Plotly Figure object showing the comparison.
        """
        idx = pd.TimedeltaIndex(
            (dispatched_vs_profile_netload_df.index.get_level_values("dayofyear") - 1) * 24
            + dispatched_vs_profile_netload_df.index.get_level_values("hour"),
            unit="hour",
        ) + pd.Timestamp(vintage_year, 1, 1)
        dispatched_vs_profile_netload_df.index = idx
        dispatched_vs_profile_netload_df.index.name = "datetime"

        wy_columns = [col for col in dispatched_vs_profile_netload_df.columns if col.startswith("wy-")]
        dispatched_vs_profile_netload_df["25th Percentile"] = dispatched_vs_profile_netload_df[wy_columns].quantile(
            0.25, axis=1
        )
        dispatched_vs_profile_netload_df["50th Percentile"] = dispatched_vs_profile_netload_df[wy_columns].quantile(
            0.50, axis=1
        )
        dispatched_vs_profile_netload_df["75th Percentile"] = dispatched_vs_profile_netload_df[wy_columns].quantile(
            0.75, axis=1
        )
        units = self.units_str if self.units_str else "units"
        fig = px.line(
            labels={"value": f"Netload ({units})", "datetime": "Datetime"}, title="Dispatched vs Profile Netload"
        )

        fig.add_scatter(
            x=dispatched_vs_profile_netload_df.index,
            y=dispatched_vs_profile_netload_df[f"Netload ({units}) {int(vintage_year)}"],
            mode="lines",
            name=f"Dispatched Netload ({units}) {int(vintage_year)}",
            line=dict(width=3, color="black"),
        )

        fig.add_scatter(
            x=dispatched_vs_profile_netload_df.index,
            y=dispatched_vs_profile_netload_df["75th Percentile"],
            mode="lines",
            name="wy- 75th Percentile",
            opacity=0.5,
            line=dict(width=1.5, color="green"),
        )
        fig.add_scatter(
            x=dispatched_vs_profile_netload_df.index,
            y=dispatched_vs_profile_netload_df["50th Percentile"],
            mode="lines",
            name="wy- 50th Percentile",
            opacity=0.5,
            line=dict(width=1.5, color="red"),
        )
        fig.add_scatter(
            x=dispatched_vs_profile_netload_df.index,
            y=dispatched_vs_profile_netload_df["25th Percentile"],
            mode="lines",
            name="wy- 25th Percentile",
            opacity=0.5,
            line=dict(width=1.5, color="green"),
        )

        for col in wy_columns:
            fig.add_scatter(
                x=dispatched_vs_profile_netload_df.index,
                y=dispatched_vs_profile_netload_df[col],
                mode="lines",
                name=col,
                line=dict(width=1, color="orange"),
                opacity=0.4,
            )

        fig.update_layout(yaxis_title_text=f"Netload ({units})")
        fig.for_each_trace(lambda trace: trace.update(legendgroup=trace.name))
        return fig

    def force_int_total(self, wt_df: pd.DataFrame, total: int) -> pd.DataFrame:
        """
        Scale a DataFrame of weights to integer values summing to a specified total.

        Args:
            wt_df: DataFrame of weights.
            total: Desired integer sum.

        Returns:
            pd.DataFrame: Adjusted DataFrame with integer weights.
        """
        total = int(total)
        wt_df0 = total * wt_df / wt_df.sum()
        wt_df = wt_df0.round(0).astype(int)
        total0 = wt_df.iloc[:, 0].sum()
        delta = int(total - total0)
        step = 1 if delta > 0 else -1
        while delta != 0:
            idx = (step * (wt_df0 - wt_df)).idxmax()
            wt_df.loc[idx] += step
            delta -= step

        assert (
            wt_df.iloc[:, 0].sum() == total
        ), f"Sum of series {wt_df.iloc[:, 0].sum()=} does not equal {total} after adjustment."
        assert wt_df.iloc[:, 0].min() >= 0, f"Series has negative values after adjustment: {wt_df}"
        logger.info(f"{pd.concat((wt_df, wt_df0), axis=1)=}")
        return wt_df

    def error_aggregation_report(
        self, profile_netload_df: pd.DataFrame, dispatched_netload_df: pd.DataFrame, params: Dict[str, Any]
    ) -> pd.DataFrame:
        """
        Calculate error statistics between dispatched and profile netload data across all weather years.

        Reports on various statistics (mean, peak, valley, positive/negative means) for different aggregations.

        Args:
            profile_netload_df: Profile netload data.
            dispatched_netload_df: Dispatched (simulated) netload data.
            params: Parameters describing the run.

        Returns:
            pd.DataFrame: Aggregated error report.
        """
        res = dispatched_netload_df - profile_netload_df
        res = res.reset_index()
        chrono_date = pd.DatetimeIndex(res["weather_year"].astype(str) + "-01-01") + pd.TimedeltaIndex(
            res["dayofyear"] - 1, unit="D"
        )
        month = pd.DatetimeIndex(chrono_date).month
        res["month"] = month
        res.set_index(["weather_year", "dayofyear", "month"], inplace=True)
        prf = profile_netload_df.reset_index()
        prf["month"] = month
        prf.set_index(["weather_year", "dayofyear", "month"], inplace=True)

        day_mean = lambda row: row.mean()
        day_peak = lambda row: row.max()
        day_valley = lambda row: row.min()
        day_pos_mean = lambda row: row[row > 0].sum() / row.size
        day_neg_mean = lambda row: row[row < 0].sum() / row.size
        cols = ["day_mean", "day_peak", "day_valley", "day_pos_mean", "day_neg_mean"]
        prf_df = prf.agg([day_mean, day_peak, day_valley, day_pos_mean, day_neg_mean], axis=1)
        prf_df.columns = cols
        res_df = res.agg([day_mean, day_peak, day_valley, day_pos_mean, day_neg_mean], axis=1)
        res_df.columns = cols

        res_all = res_df.describe()
        res_all.loc["mad", :] = res_df.abs().mean()
        prf_all = prf_df.describe()
        prf_all.loc["mad", :] = prf_df.abs().mean()
        res_wy = res_df.groupby("weather_year").mean().describe()
        res_wy.loc["mad", :] = res_df.groupby("weather_year").mean().abs().mean()
        prf_wy = prf_df.groupby("weather_year").mean().describe()
        prf_wy.loc["mad", :] = prf_df.groupby("weather_year").mean().abs().mean()
        res_m = res_df.groupby("month").mean().describe()
        res_m.loc["mad", :] = res_df.groupby("month").mean().abs().mean()
        prf_m = prf_df.groupby("month").mean().describe()
        prf_m.loc["mad", :] = prf_df.groupby("month").mean().abs().mean()

        res_all1 = pd.concat(
            (
                pd.DataFrame(index=res_all.index, data=params),
                pd.DataFrame(index=res_all.index, data={"aggregation": "all_weather_days", "data_source": "residuals"}),
                res_all,
            ),
            axis=1,
        )
        prf_all1 = pd.concat(
            (
                pd.DataFrame(index=prf_all.index, data=params),
                pd.DataFrame(index=prf_all.index, data={"aggregation": "all_weather_days", "data_source": "profile"}),
                prf_all,
            ),
            axis=1,
        )

        res_wy1 = pd.concat(
            (
                pd.DataFrame(index=res_wy.index, data=params),
                pd.DataFrame(index=res_wy.index, data={"aggregation": "weather_year", "data_source": "residuals"}),
                res_wy,
            ),
            axis=1,
        )
        prf_wy1 = pd.concat(
            (
                pd.DataFrame(index=prf_wy.index, data=params),
                pd.DataFrame(index=prf_wy.index, data={"aggregation": "weather_year", "data_source": "profile"}),
                prf_wy,
            ),
            axis=1,
        )

        res_m1 = pd.concat(
            (
                pd.DataFrame(index=res_m.index, data=params),
                pd.DataFrame(index=res_m.index, data={"aggregation": "month", "data_source": "residuals"}),
                res_m,
            ),
            axis=1,
        )
        prf_m1 = pd.concat(
            (
                pd.DataFrame(index=prf_m.index, data=params),
                pd.DataFrame(index=prf_m.index, data={"aggregation": "month", "data_source": "profile"}),
                prf_m,
            ),
            axis=1,
        )

        result = pd.concat((res_all1, prf_all1, res_wy1, prf_wy1, res_m1, prf_m1), axis=0)
        result = result.reset_index().rename(columns={"index": "statistic"})
        result = result.set_index(
            [
                "cost_metric",
                "force_integer_repweights",
                "dayofyear_difference_penalty",
                "dayofyear_difference_limit",
                "aggregation",
                "data_source",
                "statistic",
            ],
            append=False,
        )
        result = result.unstack("data_source")
        result.columns = result.columns.swaplevel()
        result.columns = ["_".join(map(str, col)).strip() for col in result.columns.values]

        result = result.reset_index()

        return result


# tests/resolve/test_repday_emd_assigner.py
