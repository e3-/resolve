from __future__ import annotations

import pandas as pd
from loguru import logger
from upath import UPath

from new_modeling_toolkit.core.excel import ScenarioTool


class ResolveScenarioTool(ScenarioTool):

    def export_case(self, *, sheet_name: str = "Resolve Case Setup"):
        app = self.book.app
        app.calculation = "manual"
        app.calculate()
        app.screen_updating = False

        sheet = self.book.sheets[sheet_name]
        data_folder = (
            UPath(self.book.fullname).parent
            / sheet.range(f"Resolve.__DATAFOLDER__").value
            / "settings"
            / "resolve"
            / sheet.range("Resolve.ActiveCaseName").value
        )
        data_folder.mkdir(exist_ok=True, parents=True)
        (data_folder / "temporal_settings").mkdir(exist_ok=True, parents=True)

        # Passthrough Implementation for Non-Opt costs and other components
        if "Passthrough Inputs" in self.book.sheet_names:
            passthrough_dir = data_folder / "passthrough"
            passthrough_dir.mkdir(parents=True, exist_ok=True)

            # These passthrough inputs depend on the following named ranges within the Scenario Tool
            for passthrough_range in ["NonOptimizedCosts", "LoadPolicyInputs", "ELCC_Multipliers"]:
                # These named ranges should have a "Scope" within the "Passthrough Inputs" sheet, not the Workbook
                # But if the Scope is Workbook, we still try to pull the data
                if (
                    passthrough_range in self.book.sheets["Passthrough Inputs"].names
                    or passthrough_range in self.book.names
                ):
                    try:
                        df = (
                            self.book.sheets["Passthrough Inputs"]
                            .range(passthrough_range)
                            .options(pd.DataFrame, index=False)
                            .value
                        )
                        df = df.dropna(axis=1, how="all")
                        df.to_csv(passthrough_dir / f"{passthrough_range}.csv", index=False)
                    except:
                        logger.warning(
                            f"Passthrough input {passthrough_range} could not be loaded successfully. "
                            f"Check the Name Manager within your Scenario Tool to make sure it's referencing"
                            f" the correct range."
                        )

        # attributes.csv
        case_attributes = pd.DataFrame.from_dict(
            {
                "timestamp": [None, None],
                "attribute": ["system", "create_operational_groups"],
                "value": [
                    self.book.sheets["Resolve Case Setup"].range("Resolve.system").value,
                    self.book.sheets["Resolve Case Setup"].range("Resolve.create_operational_groups").value,
                ],
            }
        )

        # Add results_reporting_settings to attributes df
        if "Resolve.results_reporting_settings" in self.book.sheets["Resolve Case Setup"].tables:  # guard clause
            results_reporting_settings = (
                self.book.sheets["Resolve Case Setup"]
                .tables["Resolve.results_reporting_settings"]
                .data_body_range.options(pd.DataFrame, index=0, header=0)
                .value.iloc[:, 1:]
            )
            results_reporting_settings.columns = ["value", "attribute"]
            results_reporting_settings = results_reporting_settings.dropna(subset="attribute")
            results_reporting_settings["timestamp"] = None
            case_attributes = pd.concat([case_attributes, results_reporting_settings], axis=0)

        # Add production simulation settings to attributes df
        if "Resolve.production_simulation_settings" in self.book.sheets["Resolve Case Setup"].tables:  # guard clause
            prod_sim_settings = (
                self.book.sheets["Resolve Case Setup"]
                .tables["Resolve.production_simulation_settings"]
                .data_body_range.options(pd.DataFrame, index=0, header=0)
                .value.iloc[:, 1:]
            )
            prod_sim_settings.columns = ["value", "attribute"]
            prod_sim_settings = prod_sim_settings.dropna(subset="attribute")
            prod_sim_settings["timestamp"] = None
            if prod_sim_settings.shape[0] > 0:
                if prod_sim_settings.loc[prod_sim_settings.attribute == "production_simulation_mode", "value"].values[
                    0
                ]:
                    # concatenate case name and run timestamp to portfolio_build_results_dir attribute
                    portfolio_build_results_dir = (
                        "/".join(
                            prod_sim_settings.loc[
                                prod_sim_settings.attribute.str.contains("portfolio_build_results_dir"), "value"
                            ].values
                        )
                        + "/json"
                    )
                    # TODO: Throw an error if portfolio_build_results_dir does not exist
                    # absolute_filepath = pathlib.Path.cwd().parent.parent.joinpath(portfolio_build_results_dir)
                    # if not pathlib.Path(absolute_filepath).exists():
                    #     raise ValueError(f"Capacity expansion results do not exist at this filepath: {absolute_filepath}.")
                    prod_sim_settings = prod_sim_settings.loc[
                        ~prod_sim_settings.attribute.str.contains("portfolio_build_results_dir")
                    ]
                    prod_sim_settings = pd.concat(
                        [
                            prod_sim_settings,
                            pd.DataFrame(
                                {
                                    "timestamp": [None],
                                    "attribute": ["portfolio_build_results_dir"],
                                    "value": [portfolio_build_results_dir],
                                }
                            ),
                        ],
                        ignore_index=True,
                    )
                else:
                    prod_sim_settings = prod_sim_settings.loc[
                        ~prod_sim_settings.attribute.str.contains("portfolio_build_results_dir")
                    ]

                case_attributes = pd.concat([case_attributes, prod_sim_settings], axis=0)

        # solver_settings.csv
        if "Resolve.SolverSettings" in self.book.sheets["Resolve Case Setup"].tables:  # guard clause
            solver_settings = (
                self.book.sheets["Resolve Case Setup"]
                .tables["Resolve.SolverSettings"]
                .data_body_range.options(pd.DataFrame, index=0, header=0)
                .value.iloc[:, :]
            )
            solver_settings.columns = ["option", "value", "dtype"]
            solver_settings = solver_settings.dropna(subset="value")
            if solver_settings.shape[0] > 0:
                solver_settings["solver"] = self.book.sheets["Resolve Case Setup"].range("Resolve.solver_name").value
                solver_settings.to_csv(data_folder / "solver_settings.csv", index=False)
                case_attributes = pd.concat(
                    [
                        case_attributes,
                        pd.DataFrame(
                            {"timestamp": [None], "attribute": ["solver_settings"], "value": ["solver_settings.csv"]}
                        ),
                    ],
                    ignore_index=True,
                )
        case_attributes.to_csv(data_folder / "attributes.csv", index=False)

        # scenarios.csv
        df = (
            self.book.sheets["Resolve Case Setup"]
            .tables["Resolve.scenarios"]
            .range.options(pd.DataFrame, index=0)
            .value.dropna(how="all")
        )
        df.columns = ["scenarios", "include", "priority"]
        df["priority"] = df["priority"].astype(int)
        df["include"] = df["include"].astype(bool)
        df.to_csv(data_folder / "scenarios.csv", index=False)


        # temporal_settings/attributes.csv
        temporal_settings = (
            self.book.sheets["Resolve Case Setup"]
            .tables["Resolve.TemporalSettings"]
            .data_body_range.options(pd.DataFrame, index=0, header=0)
            .value.iloc[:, 1:]
        )
        temporal_settings.columns = ["value", "attribute"]
        temporal_settings = temporal_settings.dropna(subset="attribute")
        temporal_settings["timestamp"] = None

        modeled_years = (
            self.book.sheets["Resolve Case Setup"]
            .tables["Resolve.TemporalSettings.modeled_years"]
            .range.options(pd.DataFrame)
            .value
        ).fillna(value=False)
        modeled_years.columns = ["modeled_years", "allow_inter_period_dynamics"]
        modeled_years = modeled_years.melt(ignore_index=False).reset_index()
        modeled_years.columns = ["timestamp", "attribute", "value"]
        modeled_years = modeled_years[["timestamp", "attribute", "value"]]

        df = pd.concat([temporal_settings, modeled_years])

        if "Resolve.TemporalSettings.select_weather_years" in self.book.sheets["Resolve Case Setup"].tables:
            select_weather_years = (
                self.book.sheets["Resolve Case Setup"]
                .tables["Resolve.TemporalSettings.select_weather_years"]
                .range.options(pd.DataFrame)
                .value
            ).fillna(value=False)
            select_weather_years.columns = ["weather_years_to_use"]
            select_weather_years = select_weather_years.melt(ignore_index=False).reset_index()
            select_weather_years.columns = ["timestamp", "attribute", "value"]
            select_weather_years = select_weather_years[["timestamp", "attribute", "value"]]

            df = pd.concat([df, select_weather_years])

        df.to_csv(
            data_folder / "temporal_settings" / "attributes.csv",
            index=False,
        )

    def export_cases_to_run(self, *, sheet_name: str = "Resolve Case Setup"):
        sheet = self.book.sheets[sheet_name]

        cases_to_run = (
            sheet.tables["Resolve.CasesToSave"]
            .data_body_range.options(pd.Series, index=False, header=False)
            .value.dropna()
        )

        cases_to_run.name = "cases"
        data_folder = (
            UPath(self.book.fullname).parent / sheet.range(f"Resolve.__DATAFOLDER__").value / "settings" / "resolve"
        )
        data_folder.mkdir(exist_ok=True, parents=True)
        cases_to_run.to_csv(data_folder / "cases_to_run.csv", index=False)

    def export_batch_cases(self, *, sheet_name: str = "Resolve Case Setup"):
        sheet = self.book.sheets[sheet_name]

        cases_to_save = [
            case
            for case in sheet.tables["Resolve.CasesToSave"].data_body_range.options(empty=None).value
            if case is not None
        ]
        for case in cases_to_save:
            sheet.range("Resolve.CaseToRetrieve").value = case
            self.book.macro("Sheet1.RetrieveCaseSettingRange")()
            self.book.app.status_bar = f"Saving case: {case}"
            self.export_case(sheet_name=sheet_name)

        self.export_cases_to_run(sheet_name=sheet_name)

    def export_timeseries_clusters(self, *, sheet_name: str = "Timeseries Clusters"):
        app = self.book.app
        app.calculation = "manual"
        app.screen_updating = False

        sheet = self.book.sheets[sheet_name]

        for ts_cluster in self.book.sheets["Lists"].range("TimeseriesClusters").options(ndim=1).value:
            sheet.range("ActiveTimeseriesCluster").value = ts_cluster
            app.calculate()

            data_folder = (
                UPath(self.book.fullname).parent
                / self.book.sheets["Resolve Case Setup"].range(f"Resolve.__DATAFOLDER__").value
                / "settings"
                / "timeseries"
                / sheet.range("ActiveTimeseriesCluster").value
            )
            data_folder.mkdir(exist_ok=True, parents=True)

            for rng in ["dispatch_windows_map", "chrono_periods_map"]:
                df = (
                    self.book.sheets[sheet_name]
                    .range(f"TimeseriesClusters.{rng}")
                    .options(pd.DataFrame, index=0, chunksize=250)
                    .value
                ).dropna()
                if rng == "dispatch_windows_map":
                    df = self._adjust_dst_timestamps(df)
                app.status_bar = f"Saving timeseries cluster: {ts_cluster} {rng}.csv"
                df.to_csv(data_folder / f"{rng}.csv", index=False)

            app.screen_updating = True

    def _adjust_dst_timestamps(self, df):
        """
        Adjust timestamp in dispatch_windows_map to account for DST transitions, revert back to ST (hours 00:00:00 to 23:00:00)
        - Spring forward: Adjust first 3AM to 2AM
        - Fall back: Adjust subsequent duplicate 1AM times to next integer hour
        """
        if len(df["timestamp"]) != len(df["timestamp"].unique()):
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=False).dt.tz_localize(None)
            df["dispatch_window"] = pd.to_datetime(df["dispatch_window"])

            for dispatch_window in df["dispatch_window"].unique():
                dispatch_window_df = df[df["dispatch_window"] == dispatch_window]
                # Check for duplicated hour timestamps
                if dispatch_window_df.duplicated(subset="timestamp", keep=False).any():
                    idx_3am = dispatch_window_df[dispatch_window_df["timestamp"].dt.hour == 3].index
                    idx_1am = dispatch_window_df[dispatch_window_df["timestamp"].dt.hour == 1].index
                    # TODO: check first if dispatch_window is a DST transition day before updating?
                    # Identify if Spring Forward (duplicate 3AM, adjust first 3AM to 2AM)
                    if len(idx_3am == 2):
                        df.loc[idx_3am[0], "timestamp"] = df.loc[idx_3am[0], "timestamp"].replace(hour=2)
                    # Identify if Fall Back (duplicate 1AM, adjust following timestamps in dispatch_window to next hour)
                    elif len(idx_1am == 2):
                        for idx in range(idx_1am[1], dispatch_window_df.index[-1] + 1):
                            df.loc[idx, "timestamp"] = df.loc[idx, "timestamp"].replace(
                                hour=df.loc[idx, "timestamp"].hour + 1
                            )
                    else:
                        raise ValueError(
                            f"The dispatch_window_map for dispatch_window {dispatch_window.date} has duplicate timestamps."
                        )

        return df

if __name__ == "__main__":
    from new_modeling_toolkit.core.custom_model import ModelType

    wb = ResolveScenarioTool(book="../../RESOLVE_3_Training_User_Interface.xlsm")
    wb.export_system(model=ModelType.RESOLVE)
    wb.export_batch_cases(sheet_name="Resolve Case Setup")
