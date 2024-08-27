import re
from typing import Optional

import numpy as np
import pandas as pd
import scipy.spatial
from loguru import logger
from pydantic import conint
from pydantic import Field
from pydantic import root_validator
from pydantic import validator
from sklearn.cluster import AffinityPropagation

from new_modeling_toolkit.common import load_component
from new_modeling_toolkit.common.asset.plant import resource
from new_modeling_toolkit.common.system import System
from new_modeling_toolkit.core import component
from new_modeling_toolkit.core.custom_model import convert_str_float_to_int
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.utils import util

STEPS_MAX = 100
SEED = 0


class Clusterer(object):
    """
    TODO: switch this to pydantic with Typehint
    A class that handles all data and action needed within the timeseries clustering process
    """

    def __init__(self, temporal_settings: "TemporalSettings", data: pd.DataFrame):
        """
        Args:
            temporal_settings:  A settings file including information relevant to clustering
            data: pd.DataFrame. profiles that are already arranged into chronological periods.
        """
        self.method = temporal_settings.representative_periods_method
        self.num_clusters = temporal_settings.representative_periods_amount
        self.norm_order = temporal_settings.norm_order

        self.data = data

        if self.method != "manual":
            # compute distance matrix
            self._get_dist()
            self.all_data_names = self.data.index.tolist()

            # cluster defining attributes
            self.medioids = []
            self.cluster_map = pd.Series(index=self.all_data_names, dtype=int)
            self.weights = pd.Series(index=self.medioids, dtype=float)

            # initialize the medioids selection
            self._init_medioids(init_method="heuristics")

        # commence clustering algorithm
        getattr(self, self.method)(temporal_settings=temporal_settings)

    def _get_dist(self):
        """
        Given data, calculate the pair wise euclidean distance.
        Returns:

        """
        dist = scipy.spatial.distance_matrix(self.data, self.data, self.norm_order)
        self.dist = pd.DataFrame(dist, index=self.data.index, columns=self.data.index)

    def _init_medioids(self, init_method="heuristics"):
        """
        Simple methods for initializating the medioids location
        Args:
            init_method:str.

        Returns:
        """
        if init_method == "heuristics":
            medioids_idx = self.dist.sum().argsort()[: self.num_clusters]
        elif init_method == "random":
            np.random.seed(SEED)
            medioids_idx = np.random.choice(len(self.data), size=self.num_clusters, replace=False)

        self.medioids = np.sort(medioids_idx)

    def _get_mapping_and_weight(self):
        """
        Given medioids and distance matrix, find the appropriate cluster map and weights. Each data point is mapped
        to its closest cluster centroid. The weight of each cluster is its fraction of the amount of all points.
        Returns:

        """
        self.cluster_map = self.dist[self.medioids].idxmin(axis=1)
        self.weights = pd.Series(index=self.medioids, dtype=float)
        for m in self.medioids:
            self.weights.loc[m] = (self.cluster_map == m).sum() / len(self.cluster_map)

    def k_medioids(self, temporal_settings: "TemporalSettings"):
        """Implementation of the k_medioids method with the PAM algorithm.https://en.wikipedia.org/wiki/K-medioids
        Returns:
        """

        # Choosing initial medioids greedily.
        # Reference: https://scikit-learn-extra.readthedocs.io/en/stable/generated/sklearn_extra.cluster.KMedoids.html
        medioids = self.medioids
        non_medioids = list(set(self.all_data_names) - set(self.medioids))
        total_dist = self.dist[medioids].min(axis=1).sum()

        # iterate the k-medioids method until convergence
        for step_count in range(STEPS_MAX):
            logger.info("k-medioids step {} of max {} steps".format(step_count, STEPS_MAX))

            # consider every (medioid, non-medioid pair):
            alt_total_dist = pd.Series(index=pd.MultiIndex.from_product([medioids, non_medioids]), dtype=float)
            for m in medioids:
                for n in non_medioids:
                    # calculate alternative total distance
                    alt_medioids = list((set(medioids) - set([m])) | set([n]))
                    alt_total_dist[(m, n)] = self.dist[alt_medioids].min(axis=0).sum()

            # check for convergence
            if alt_total_dist.min() < total_dist:
                m, n = alt_total_dist.idxmin()
                # avoid cyclical non convergence
                medioids = np.sort(list((set(medioids) - set([m])) | set([n])))
                non_medioids = list(set(self.all_data_names) - set(medioids))
                total_dist = alt_total_dist[(m, n)]
            else:
                logger.info("K-medioids Converged after {} steps".format(step_count))
                break

        # final assignment after convergence
        self.medioids = medioids
        self._get_mapping_and_weight()

    def manual(self, temporal_settings: "TemporalSettings"):
        """
        For manually defined rep periods and their mapping. In order for this to work,
        please provide all files listed in $temporal_settings.rep_periods_def_files$ except for load_components.
        Returns:
        """
        self.medioids = temporal_settings.rep_periods.index.sort_values()
        self.cluster_map = temporal_settings.map_to_rep_periods.sort_index()
        self.weights = temporal_settings.rep_period_weights

    def assign_rep_periods(self, temporal_settings: "TemporalSettings"):
        """
        When the representative periods are already pre-determined, Skip medioid finding and directly
        create a mapping. To use this functionality, please provide rep_periods.csv and components_to_consider.csv
        according to the format of the output.
        """
        self.medioids = temporal_settings.rep_periods.index.sort_values()
        if self.num_clusters != len(self.medioids):
            logger.warning("Inconsistent definition of rep periods amount between rep_periods.csv and attributes.csv")

        self._get_mapping_and_weight()

    def affinity_propagation(self, temporal_settings: "TemporalSettings"):
        """
        affinity propagation (AP) is a clustering algorithm based on the concept of "message passing" between
        data points. For more information, refer to https://en.wikipedia.org/wiki/Affinity_propagation
        """
        clustering = AffinityPropagation(random_state=SEED).fit(self.data)
        self.medioids = pd.Series(clustering.cluster_centers_indices_)
        self.cluster_map = self.medioids[clustering.labels_].reset_index(drop=True)
        for m in self.medioids:
            self.weights.loc[m] = (self.cluster_map == m).sum() / len(self.cluster_map)


class TemporalSettings(component.Component):
    """
    Given a list of coincident timeseries, this class includes methods that cut these timeseries into equal length
    periods (most commonly days). Among those periods, pick out the ones that is most capable of representing or
    reconstructing the original timeseries. This is a crucial step in reducing the temporal complexity of the
    capacity expansion optimization.
    """

    dir_str: util.DirStructure

    # TODO (2022-01-29): Review that all these attributes work as-expected
    modeled_years: ts.BooleanTimeseries = Field(None, default_freq="YS", down_method="annual")

    weather_years_to_use: ts.BooleanTimeseries = Field(None, default_freq="YS", down_method="annual")

    # Discount factor attributes
    annual_discount_rate: Optional[ts.NumericTimeseries] = Field(
        None, default_freq="YS", up_method="ffill", down_method="annual", description="Annual real discount rate."
    )
    cost_dollar_year: Optional[conint(ge=1900)] = None
    end_effect_years: Optional[conint(ge=0)] = None
    modeled_year_discount_factor: Optional[ts.NumericTimeseries] = Field(None, default_freq="YS", down_method="annual")
    discount_rate: Optional[ts.NumericTimeseries] = Field(None, default_freq="YS", down_method="annual")

    # Convert strings that look like floats to integers for integer fields
    _convert_int = validator(
        "cost_dollar_year", "end_effect_years", "representative_periods_amount", allow_reuse=True, pre=True
    )(convert_str_float_to_int)

    def __hash__(self):
        """Define a hash ID for temporal settings so that we can find generation profiles that have already been re-scaled."""

        def string_to_int(s):
            """Python's hash() function doesn't return the same hash for the same string, but it does for other datatypes.
            https://stackoverflow.com/a/2511232/7397542
            """
            ord3 = lambda x: "%.3d" % ord(x)
            return int("".join(map(ord3, s)))

        return hash(
            (
                tuple(sorted(self.modeled_years.data[self.modeled_years.data == True].index.year)),
                tuple(sorted(self.weather_years_to_use.data[self.weather_years_to_use.data == True].index.year))
                if self.weather_years_to_use is not None
                else 0,
                self.representative_periods_amount,
                string_to_int(self.representative_periods_duration),
                tuple(self.rep_periods.iloc[:, 0].values),
            )
        )

    @validator("annual_discount_rate")
    def validate_annual_discount_rate(cls, annual_discount_rate):
        """Validate that discount rates are just the percentage portion and not (1 + discount rate) or 1 / (1 + discount rate)."""
        if (annual_discount_rate.data >= 1).any():
            raise ValueError("It seems like you entered discount rates as (1 + discount rate)")
        elif (annual_discount_rate.data >= 0.8).any():
            raise ValueError("It seems like you entered discount rates as 1 / (1 + discount rate)")
        return annual_discount_rate

    @root_validator
    def validate_or_calculate_discount_factor(cls, values):
        """Validate that required attributes to calculate RESOLVE discount factors are available.

        There are two options:
            #. Use ``annual_discount_rate``, ``cost_dollar_year``, and ``end_effect_years`` to calculate ``discount_factor``
            #. Validate that ``modeled_year_discount_factor`` is passed and none of the other attributes

        If ``discount_factor`` is being calculated endogenously by the code, the calculation works as follows:
            #. Set up DataFrame for calculations spanning from ``cost_dollar_year`` through (``modeled_year_end`` + ``end_effect_years``)
            #. Drop any years before first ``modeled_year_start``
            #. Convert annual discount rate to compounding discount rate for full modeling horizon, with 100% being ``cost_dollar_year``
            #. Add modeled years
            #. Sum up end effect years
            #. Count years between modeled years
            #. Weight compounding discount rate by ``start_year_weight`` and ``end_year_weight``
            #. Sum ``start_year_weight`` and ``end_year_weight`` for each modeled year using ``df.groupby``
            #. Convert to Timeseries object

        """
        # Warn that ``discount_rate`` is deprecated
        if values["discount_rate"]:
            logger.warning(
                "The `discount_rate` attribute is deprecated and will replaced by `modeled_year_discount_factor` or "
                "can be endogenously calculated by passing [`discount_rate`, `cost_dollar_year`, `end_effect_years`]"
            )
            values["modeled_year_discount_factor"] = values["discount_rate"]
        msg = (
            "Discount factors for modeled years can be specified either using "
            "`modeled_year_discount_factor` alone or endogenously calculated "
            "using the combination of [`discount_rate`, `cost_dollar_year`, `end_effect_years`]"
        )

        # If values for `discount_factor` are provided, make sure the others are not
        if values["modeled_year_discount_factor"]:
            assert all(values[v] is None for v in ["annual_discount_rate", "cost_dollar_year", "end_effect_years"]), msg
        else:
            assert all(
                values[v] is not None for v in ["annual_discount_rate", "cost_dollar_year", "end_effect_years"]
            ), msg

            # 1. Set up DataFrame for calculations spanning from ``cost_dollar_year`` through (``modeled_year_end`` + ``end_effect_years``)
            modeled_year_start = values["modeled_years"].data[values["modeled_years"].data == True].index.min()
            modeled_year_end = values["modeled_years"].data[values["modeled_years"].data == True].index.max()
            df = pd.DataFrame(
                index=pd.date_range(
                    start=f"1/1/{values['cost_dollar_year']}",
                    end=f"1/1/{modeled_year_end.year + values['end_effect_years'] - 1}",
                    freq="YS",
                )
            )

            # 2. Drop any years before first ``modeled_year_start``
            df = df[df.index >= min(modeled_year_start, pd.Timestamp(f"1/1/{values['cost_dollar_year']}"))]

            # 3. Convert annual discount rate to compounding discount rate for full modeling horizon, with 100% being ``cost_dollar_year``
            df["compounding_discount_rate"] = (1.0 + values["annual_discount_rate"].data) ** -1
            df["compounding_discount_rate"] = df["compounding_discount_rate"].fillna(method="ffill")
            df.loc[f"1/1/{values['cost_dollar_year']}", "compounding_discount_rate"] = 1
            df["compounding_discount_rate"] = df["compounding_discount_rate"].cumprod()
            df = df[df.index >= modeled_year_start]

            # 4. Add modeled years
            df["modeled_years"] = values["modeled_years"].data
            df["modeled_years"] = df["modeled_years"].fillna(False)

            # 5. Sum up end effect years
            df.loc[modeled_year_end, "compounding_discount_rate"] = df.loc[
                df.index >= modeled_year_end, "compounding_discount_rate"
            ].sum()
            df = df[df.index <= modeled_year_end]

            # 6. Count years between modeled years
            counter = 0
            start_year = modeled_year_start
            for index, row in df.iterrows():
                if row["modeled_years"]:
                    counter = 0
                    start_year = index
                df.loc[index, "end_year_weight"] = counter
                df.loc[index, "start_year"] = start_year
                # Increment counter
                counter += 1

            counter = 1
            end_year = pd.to_datetime(f"1/1/{modeled_year_end.year + 1}")
            for index, row in df[::-1].iterrows():
                df.loc[index, "start_year_weight"] = counter
                df.loc[index, "end_year"] = end_year
                # Increment counter
                counter += 1
                if row["modeled_years"]:
                    end_year = index
                    counter = 1

            df["num_years_between_modeled"] = df["end_year"].dt.year - df["start_year"].dt.year

            # 7. Weight compounding discount rate by ``start_year_weight`` and ``end_year_weight``

            df["end_year_weight"] = (
                df["end_year_weight"] / df["num_years_between_modeled"] * df["compounding_discount_rate"]
            )
            df["start_year_weight"] = (
                df["start_year_weight"] / df["num_years_between_modeled"] * df["compounding_discount_rate"]
            )

            # 8. Sum ``start_year_weight`` and ``end_year_weight`` for each modeled year using ``df.groupby``
            discount_factor = (
                pd.concat(
                    [
                        df.groupby("start_year")["start_year_weight"].sum(),
                        df.groupby("end_year")["end_year_weight"].sum(),
                    ],
                    axis=1,
                )
                .fillna(0)
                .sum(axis=1)
            )
            discount_factor = discount_factor[values["modeled_years"].data[values["modeled_years"].data == True].index]

            # 9. Convert to Timeseries object
            values["modeled_year_discount_factor"] = ts.NumericTimeseries(
                name="modeled_year_discount_factor", data=discount_factor
            )

        return values

    # temporal_granularity: float = 1

    representative_periods_amount: int = Field(12, description="number of representative periods")
    representative_periods_duration: str = Field(
        "1D",
        description=" Duration of each representative period. Must be comprehensible by the pd.Timedelta function.",
    )
    representative_periods_method: str = Field(
        "k medioids",
        description="The method for this downsampling. K-medioids, manual, and find-mapping has been implemented so far",
    )

    norm_order: Optional[int] = Field(
        2,
        description="Relates to the dissimilarity metrics. What order of the minkowsky norm we shall use for the "
        "dissimilarity characterization. 1 is using manhattan distance while 2 is euclidean distance. "
        "Only present when peridods are found rather than prescribed.",
    )

    allow_inter_period_dynamics: ts.BooleanTimeseries = Field(
        ...,
        description="boolean value that determines whether this resolve model consider inter period dynamics. "
        "Namely there are three types of inter period dynamics: SOC tracking, ramping constraint, and adjacency rule",
        default_freq="YS",
        down_method="annual",
    )

    # various files that are used to define the rep periods
    rep_periods_def_files = [
        "rep_periods",
        "chrono_periods",
        "components_to_consider",
        "map_to_rep_periods",
        "rep_period_weights",
    ]

    available_files: Optional[list] = Field(
        [],
        description="list of files that are available and read in out of all the files in $rep_periods_df_files$",
    )

    components_to_consider: Optional[pd.Series] = Field(
        None,
        description="list of components whose profiles are considered in the representative period finding process."
        "Only present when are found rather than prescribed. ",
    )

    rep_periods: Optional[pd.DataFrame] = Field(
        None,
        description="A pd DataFrame that is shaped M by N and filled with pd.Timestamp. Each role records the timestamp "
        "comprising a single rep periods, which is N hours/steps long, and totaling M of them, The index"
        " is each periods location in the chronoligcal sequence",
    )
    chrono_periods: Optional[pd.DataFrame] = Field(
        None,
        description="A pd DataFrame that is shaped M by N and filled with pd.Timestamp. Each role records the timestamp "
        "comprising a single chronological periods, which is N hours/steps long, and totaling M of them"
        "The entirety of this table should represent all weather years under consideration",
    )
    map_to_rep_periods: Optional[pd.Series] = Field(
        None,
        description="A pd series listing the membership of each chronological period to its representative period",
    )
    rep_period_weights: Optional[pd.Series] = Field(
        None,
        description="A pd series listing the weight of each representative periods",
    )

    @validator("representative_periods_method", pre=True)
    def validate_rep_period_method(cls, rep_period_method):
        # define parsing dictionary which gets turned into regex patterns
        parsing_dict = {"-": "_", " ": "_", "medoid": "medioid", "representative": "rep"}
        parsing_dict = dict((re.escape(k), v) for k, v in parsing_dict.items())
        pattern = re.compile("|".join(parsing_dict.keys()))

        # do string replacement based on patterns
        rep_period_method = pattern.sub(lambda m: parsing_dict[re.escape(m.group(0))], rep_period_method)
        rep_period_method = rep_period_method.lower()
        available_methods = ["k_medioids", "assign_rep_periods", "manual", "affinity_propagation"]

        if rep_period_method in available_methods:
            return rep_period_method
        else:
            raise ValueError(
                "RESOLVE model clustering method attribute 'rep_period_method' must be one of {}. Instead the method "
                "was:{}".format(available_methods, rep_period_method)
            )

    @validator("representative_periods_duration")
    def validate_rep_duration(cls, duration):
        # confirm that the provided period duration is a multitude of hour
        if (pd.Timedelta(duration) % pd.Timedelta("1H")).seconds >= 1e-4:
            raise ValueError("Representative Period duration must be multiples of a whole hour")
        else:
            return duration

    def _read_in_addl_temp_files(self):
        for filename in self.rep_periods_def_files:
            filepath = self.attr_path.parent / (filename + ".csv")
            if filepath.exists():
                value = pd.read_csv(filepath, index_col=0).squeeze("columns")
                # translate some information to datetime type
                if filename in ["chrono_periods", "rep_periods"]:
                    value = value[value.columns].apply(pd.to_datetime)
                    value.columns = value.columns.astype(int)

                # set as attribute
                setattr(self, filename, value)
                self.available_files.append(filename)

    def _validate_method_availability(self):
        req_files = {
            "manual": set(self.rep_periods_def_files) - set(["components_to_consider"]),
            "assign_rep_periods": set(
                [
                    "components_to_consider",
                    "rep_periods",
                ]
            ),
            "k_medioids": set(["components_to_consider"]),
            "affinity_propagation": set(["components_to_consider"]),
        }
        method = self.representative_periods_method
        method_req_files = req_files[method]  # files required by the current method
        avail_files = set(self.available_files)  # files available in the folder

        # prompt user about what files are available and what is required
        avail_and_req_files = method_req_files & avail_files
        req_but_unavail_files = method_req_files - avail_files
        avail_but_not_req = avail_files - method_req_files

        if len(avail_and_req_files) > 0:
            logger.info("{} required by {} method and read in".format(avail_and_req_files, method))
        if len(req_but_unavail_files) > 0:
            logger.error(
                "{} required by {} method yet non-existent. Clustering failed".format(req_but_unavail_files, method)
            )
        if len(avail_but_not_req) > 0:
            logger.info("{} not required by {} method and overwritten".format(avail_but_not_req, method))

    def _collect_profiles(self, system):
        """
        Collect profiles from the components provided
        Args:
            components_w_profiles: list of components. A list of components we will extract profiles from.

        Returns:
            all_profiles: pd.Dataframe. A dataframe of the profiles collected. Timestamp in index, and component
            name in columns
        """

        # initialize a container to hold the profile from each component
        all_profiles = pd.DataFrame()
        # Sometimes there are empty rows
        self.components_to_consider = self.components_to_consider.dropna(how="all")

        # collect components instances based on the csv file
        for comp_id in self.components_to_consider.index:
            component_type = self.components_to_consider.loc[comp_id, "component_type"].lower() + "s"
            comp = getattr(system, component_type)[self.components_to_consider.loc[comp_id, "name"]]

            # only gather profiles from resources or loads
            if type(comp) == load_component.Load:
                profile = comp.profile.data
            elif type(comp) == resource.Resource:
                profile = comp.provide_power_potential_profile.data
            else:
                raise TypeError("Only the profiles of load and resource can be considered!")

            # warning when the frequency of the profile is not hourly
            # TODO: restore this check
            if pd.infer_freq(profile.index) != "H":
                logger.warning(comp.name + " is not using hourly frequency!")

            # collect profiles
            all_profiles[comp.name] = profile

        # drop incomplete lines, warn the user if there's not even a year
        all_profiles = all_profiles.dropna()

        if self.weather_years_to_use is not None:
            all_profiles = all_profiles[
                all_profiles.index.year.isin(
                    self.weather_years_to_use.data[self.weather_years_to_use.data == True].index.year
                )
            ]

        if (all_profiles.index[-1] - all_profiles.index[0]) < pd.Timedelta("365D"):
            logger.warning("there's less than a year of coincident data. Not recommended")

        return all_profiles

    def _pivot_profiles_into_periods(self, profiles):
        """
        Prior to this, each column in profiles represent a timeseries. After the pivoting, each column only contains
        the profile at a specific hour.
        Args:
            profiles: pd.Dataframe with timestamp on index and profile name on column, and profiles as values

        Returns: pivoted profiles where period index is on the index, profile name and hours on the columns

        """
        # represent period duration and number of periods as integer
        period_duration = pd.Timedelta(self.representative_periods_duration) // pd.Timedelta("1H")
        num_chrono_periods = profiles.shape[0] // period_duration

        # initialization
        profile_names = profiles.columns
        profiles_pivoted = pd.DataFrame(
            index=np.arange(num_chrono_periods).astype("int"),
            columns=pd.MultiIndex.from_product([profile_names, np.arange(period_duration)]),
        )
        self.chrono_periods = pd.DataFrame(index=profiles_pivoted.index)

        # loop thru each profile, and pivot them into periods
        # TODO 2022-09-01: This is very slow for long period_duration
        for h in range(period_duration):
            for p in profile_names:
                value_of_hour = profiles[p].iloc[h::period_duration][:num_chrono_periods]
                profiles_pivoted[(p, h)] = value_of_hour.values

            # Generate period index and hour index for the long timeseries
            # Previous operation should guarantee value of hour all have the same length
            self.chrono_periods[h] = value_of_hour.index

        return profiles_pivoted

    def _accept_clustering_result(self, cluster_result):
        """

        Args:
            cluster_result: Clusterer. an array of indices for the representative periods (medioids).
            cluster_map: pd.Series. a mapping between the original periods in index and the representative periods
            in data column.

        Returns:
        """

        # Store the clustering result as attributes of the TemporalSettings instance.
        self.rep_periods = self.chrono_periods.loc[cluster_result.medioids]
        self.map_to_rep_periods = cluster_result.cluster_map
        self.rep_period_weights = cluster_result.weights
        self.representative_periods_amount = len(self.rep_periods)

    def set_timesteps(self):
        """
        generate timesteps for temporal.timesteps dataframe

        """
        # not tested
        if not hasattr(self, "rep_periods"):
            logger.error(f"attempted to create timesteps, but rep_periods doesn't exist yet!")
            return

        try:
            # assumes each period has the same timesteps
            firstPeriod = self.rep_periods.iloc[0].tolist()
            # print ("firstPeriod = ",firstPeriod)
            timestepList = [(firstPeriod[1] - firstPeriod[0]).total_seconds() / 3600.0]
            # print ("timesteplist = ", timestepList)
            for i in range(1, len(firstPeriod) - 1):
                timestepList.append((firstPeriod[i + 1] - firstPeriod[i]).total_seconds() / 3600.0)
            timestepList.append(1.0)
            self.timesteps = pd.Series(timestepList)
        except:
            logger.error(f"attempted to create timesteps, but an error occured")

        return None

    def find_representative_periods(self, system):
        logger.debug(f"Reading in available input files for finding representative periods")
        self._read_in_addl_temp_files()

        logger.debug(f"Finding representative periods via {self.representative_periods_method}")
        self._validate_method_availability()

        # Collect coincidental profiles from the provided list of components. Pivot into given lengths of periods
        cluster_result = None
        if self.representative_periods_method != "manual":
            profiles = self._collect_profiles(system)

            # merge the current profile with the others
            if "weight" in self.components_to_consider.columns:  # backward compatibility
                weighted_profiles = self.components_to_consider["weight"].values * profiles
            else:
                weighted_profiles = profiles.copy()

            profiles_pivoted = self._pivot_profiles_into_periods(weighted_profiles)

            # Conduct clustering with the given representative periods method
            cluster_result = Clusterer(self, profiles_pivoted)
            # Transfer the result into the current temporal settings instance
            self._accept_clustering_result(cluster_result)

        else:
            profiles = weighted_profiles = None

        self.output(profiles=profiles, weighted_profiles=weighted_profiles)

        self.set_timesteps()

        return cluster_result

    # used in run_opt.py to output rep periods and rep period mapping
    def output(self, profiles=None, weighted_profiles=None):
        if profiles is not None:
            (self.dir_str.output_resolve_dir / "temporal_settings").mkdir(parents=True, exist_ok=True)

            profiles.to_csv(self.dir_str.output_resolve_dir / "temporal_settings" / "profiles.csv")
            weighted_profiles.to_csv(self.dir_str.output_resolve_dir / "temporal_settings" / "weighted_profiles.csv")

        """Output timeseries clustering data (if not in `manual` mode)."""
        for attr in self.rep_periods_def_files:
            if getattr(self, attr) is not None:
                getattr(self, attr).to_csv(self.attr_path.parent / (attr + ".csv"))

        if self.annual_discount_rate is not None:
            self.annual_discount_rate.data.to_csv(self.attr_path.parent / "annual_discount_rate.csv")

        self.modeled_year_discount_factor.data.to_csv(self.attr_path.parent / "modeled_year_discount_factor.csv")


if __name__ == "__main__":
    dir_str = util.DirStructure()
    settings_dir = "20220724_full_run_48p_xc_AP"
    dir_str.make_resolve_dir(settings_dir)

    scenarios = pd.read_csv(dir_str.resolve_settings_dir / "scenarios.csv")["scenarios"].tolist()

    _, system_instance = System.from_csv(
        filename=dir_str.data_interim_dir / "systems" / "CPUC IRP System Topology" / "attributes.csv",
        scenarios=scenarios,
        data={"dir_str": dir_str},
    )
    _, temporal_settings = TemporalSettings.from_csv(
        dir_str.data_settings_dir / "resolve" / settings_dir / "temporal_settings" / "attributes.csv",
        data={"dir_str": dir_str},
    )
    cluster_result = temporal_settings.find_representative_periods(system_instance)
    temporal_settings.output()
