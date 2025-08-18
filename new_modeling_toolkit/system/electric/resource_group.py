import enum
from typing import ClassVar
from typing import Optional
from typing import Union

import numpy as np
import pandas as pd
import pydantic
import scipy.stats
from loguru import logger

from new_modeling_toolkit.core import component
from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.utils.core_utils import cantor_pairing_function


def _get_daily_mean(
    hour_profile: Union[pd.Series, pd.DataFrame],
    start: Optional[Union[str, pd.Timestamp]] = None,
    end: Optional[Union[str, pd.Timestamp]] = None,
):
    """
    Args:
        start (pd.timestamp, optional): start date
        end (pd.timestamp, optional): end date
    Returns: daily_mean: DataFrame with daily average load/generation indexed by date
    """
    daily_mean = pd.DataFrame(hour_profile.resample("D").mean())
    if start is not None:
        daily_mean = daily_mean.loc[start:]
    if end is not None:
        daily_mean = daily_mean.loc[:end]
    daily_mean["dayofyear"] = daily_mean.index.dayofyear

    return daily_mean


def _get_candidate_days(daily_profile: pd.DataFrame, dayofyear: int, daysbefore: int, daysafter: int):
    """
    get a slice of -daysbefore to +daysafter days relative to the specified dayofyear, not considering weekday matching for now
    Args:
        daily_profile DataFrame with at least a dayofyear column
    Returns:
        DataFrame with average load/generation for all days within the slice, indexed by date
    """
    dayofyear_start = dayofyear - daysbefore
    dayofyear_end = dayofyear + daysafter
    if dayofyear_start < 1:
        dayofyear_start1 = 365 + dayofyear_start  # ignoring leapyear effects for now
        dayofyear_end1 = 365
        dayofyear_start = 1
    elif dayofyear_end > 365:
        dayofyear_start1 = 1
        dayofyear_end1 = dayofyear_end - 365
    else:
        dayofyear_start1 = dayofyear_start
        dayofyear_end1 = dayofyear_end

    pool = daily_profile.loc[
        ((daily_profile["dayofyear"] >= dayofyear_start) & (daily_profile["dayofyear"] <= dayofyear_end))
        | ((daily_profile["dayofyear"] >= dayofyear_start1) & (daily_profile["dayofyear"] <= dayofyear_end1))
    ]

    return pool


@enum.unique
class ResourceGroupCategory(enum.Enum):
    DEMAND_RESPONSE = "dr"
    FIRM = "firm"
    FLEXIBLE_LOAD = "flexible_load"
    GENERIC = "generic"
    HYBRID_STORAGE = "hybrid_storage"
    HYDRO = "hydro"
    STORAGE = "storage"
    THERMAL = "thermal"
    VARIABLE = "variable"
    HYBRID_VARIABLE = "hybrid_variable"


class ResourceGroup(component.Component):
    SAVE_PATH: ClassVar[str] = "resource_groups"
    ### LINKAGES ###

    resources: dict[str, linkage.Linkage] = {}
    flexible_resources: dict[str, linkage.Linkage] = {}
    hydro_resources: dict[str, linkage.Linkage] = {}
    shed_dr_resources: dict[str, linkage.Linkage] = {}
    storage_resources: dict[str, linkage.Linkage] = {}
    variable_resources: dict[str, linkage.Linkage] = {}
    hybrid_variable_resources: dict[str, linkage.Linkage] = {}
    thermal_resources: dict[str, linkage.Linkage] = {}

    ### ATTRIBUTES ###

    # Required for upsampling of resource data in recap.monte_carlo_draw / defining operating constraints in recap.dispatch_model
    category: Optional[ResourceGroupCategory] = pydantic.Field(
        None,
        description="[RECAP only]. string. Category of all resources in the group. Must be linked to a ResourceGroup. Used to upsample resources and simulate outages in RECAP.",
    )

    # Used for day draw maps
    random_seed: Optional[float] = pydantic.Field(None, description="Random seed used for outage simulation in RECAP.")

    # Used to determine how to upsample profiles with fixed annual shapes
    fixed_annual_shape: Optional[bool] = pydantic.Field(
        False,
        description="[RECAP only]. TRUE/FALSE. boolean. Whether or not resources in this group have a fixed annual shape. Typically used when you do not want a resource to got through RECAP's day draw algorithm.",
    )

    # TODO: validate that only ONE or fewer of the above upsampling options is true (validator)

    def get_aggregated_generation_profile(self, model_year) -> pd.Series:
        agg_gen = 0
        for resource in self.resource_dict.values():
            generation_profile = resource.capacity_planned.slice_by_year(model_year) * resource.power_output_max.data
            agg_gen += generation_profile
        agg_gen.name = 0
        return agg_gen

    @property
    def resource_dict(self):
        if self.resources:
            return {resource: self.resources[resource].instance_from for resource in self.resources}
        elif self.thermal_resources:
            return {resource: self.thermal_resources[resource].instance_from for resource in self.thermal_resources}
        elif self.variable_resources:
            return {resource: self.variable_resources[resource].instance_from for resource in self.variable_resources}
        elif self.hybrid_variable_resources:
            return {
                resource: self.hybrid_variable_resources[resource].instance_from
                for resource in self.hybrid_variable_resources
            }
        elif self.hydro_resources:
            return {resource: self.hydro_resources[resource].instance_from for resource in self.hydro_resources}
        elif self.flexible_resources:
            return {resource: self.flexible_resources[resource].instance_from for resource in self.flexible_resources}
        elif self.shed_dr_resources:
            return {resource: self.shed_dr_resources[resource].instance_from for resource in self.shed_dr_resources}
        else:
            return {}

    def get_start_and_end_date(self):
        """
        Get the start and end date for the overlapping section of profiles for the group
        Returns:
            (start_date, end_date): start_date and end_date (Timestamp) for the group of profiles
        """
        n_matches = 0
        for resource in self.resources:
            profile_start = self.resource_dict[resource].power_output_max.data.index[0]
            profile_end = self.resource_dict[resource].power_output_max.data.index[-1]
            logger.debug(f"Profile length for {self.name} resource {resource}: {profile_start} to {profile_end}")
            if n_matches == 0:
                output = (profile_start, profile_end)
                n_matches += 1
            else:
                start = max(output[0], profile_start)
                end = min(output[1], profile_end)
                output = (start, end)
        self.start_and_end_date = output

    ##############################################
    # Create day draw map for variable_resources #
    ##############################################
    # This function does renewable day matching to define self.day_draw_map
    # (map between historical weather/load days and days in renewables records of weather-dependent resource groups)

    def _construct_pool_gen_load(self, dayofyear, daysbefore, daysafter):
        """
        Args:
            daysbefore(int): days before to include in slice
            daysafter(int): days after to include in slice
        Returns:
            {group: DataFrame}: dict, with key of group; value as daily load/gen dataframe,
            sliced for days that are within 'daysbefore' and 'daysafter' of the specified dayofyear
        """
        group_pool = _get_candidate_days(
            self.daily_load_by_group, dayofyear, daysbefore, daysafter
        ).copy()  # copy so we won't change original df

        group_pool = group_pool.rename(columns={"value": "load"})
        group_pool["gen"] = (group_pool.index.to_series()).map(self.daily_gen_by_group[0])
        # todo RL clarify about column name
        group_pool["prev_day_gen"] = (group_pool.index.to_series() + pd.DateOffset(days=-1)).map(
            self.daily_gen_by_group[0]
        )
        # there will be no previous day gen for the first day, so take the average of previous day gen of the whole slice
        group_pool.loc[pd.isnull(group_pool["prev_day_gen"]), "prev_day_gen"] = group_pool["prev_day_gen"].mean()

        return group_pool

    def draw_days_by_group(self, load_calendar, model_year, day_window_variable_draws, draw_random_seed):
        """
        Randomly draw the days for resource groups with a category of "variable".
        Default probability function is normal multivariate
        Returns:
            dict {(i,group): day}: i is the datetimeindex of the full load profile,
                                   group is the variable profile group,
                                   and day is a datetime.datetime representing the random day draw for that variable profile group
        """

        draw_group = {}

        # Iterate over each day in the full daily calendar (e.g. 70 years of average daily load)
        logger.info(f"Upsampling generation profiles for group {self.name}")
        self.get_start_and_end_date()
        overlap_start_end_date_by_group = (
            max(load_calendar.index[0], self.start_and_end_date[0]),
            min(load_calendar.index[-1], self.start_and_end_date[1]),
        )
        logger.info(
            f"Overlap period between load and {self.name}:"
            f" {overlap_start_end_date_by_group[0]} to {overlap_start_end_date_by_group[1]}"
        )
        assert overlap_start_end_date_by_group[0] < overlap_start_end_date_by_group[1], (
            f"Resource group `{self.name}` start and end dates "
            f"`{self.start_and_end_date[0]}` - "
            f"`{self.start_and_end_date[1]}` "
            f"do not overlap with load profile start and end dates `{load_calendar.index[0]}` - `{load_calendar.index[1]}`"
        )

        logger.debug("Calculating daily load profile...")
        daily_load = _get_daily_mean(load_calendar)
        # Rename column "load"
        daily_load = daily_load.rename(columns={daily_load.columns[0]: "load"})
        # Get average daily load for profile group, trimmed for common calendar (e.g. solar: 1998-2005, wind: 2005-2012)
        self.daily_load_by_group = daily_load.loc[
            overlap_start_end_date_by_group[0] : overlap_start_end_date_by_group[1]
        ]
        logger.debug("Calculating daily generation profile for resource groups...")
        self.daily_gen_by_group = _get_daily_mean(
            self.get_aggregated_generation_profile(model_year),
            overlap_start_end_date_by_group[0],
            overlap_start_end_date_by_group[1],
        )

        # Get candidate pool settings
        day_slice_window = day_window_variable_draws
        daysbefore = round(day_slice_window / 2.0, 0)
        daysafter = round(day_slice_window / 2.0, 0)

        # Pre-compute candidate pools for each day of the year
        candidate_pools_by_dayofyear = {}
        covariance_by_dayofyear_by_group = {}

        logger.debug("Constructing candidate day pools for draw and calculating covariance of load/gen in pools")
        for dayofyear in daily_load["dayofyear"].unique():
            # Save candidate pools for all groups
            candidate_pool = self._construct_pool_gen_load(dayofyear, daysbefore, daysafter)
            candidate_pools_by_dayofyear[dayofyear] = candidate_pool
            # Precompute covariance matrices for each group's candidate pool and each day of year
            covariance_by_dayofyear_by_group[dayofyear] = {}
            load_cmp, group_cmp = candidate_pool["load"].values, candidate_pool["prev_day_gen"].values
            covariance = np.cov(np.vstack((load_cmp, group_cmp)))
            covariance_by_dayofyear_by_group[dayofyear] = covariance

        logger.debug(f"Creating day draw maps for group {self.name}")
        counter = 0
        np.random.seed(
            cantor_pairing_function(draw_random_seed, int(self.random_seed))
        )  # set the random number seed. First seed is MC draw seed, second seed is the seed of the group
        for i, row in daily_load.iterrows():  # Full weather / load record length
            dayofyear = row["dayofyear"]  # int
            load_ref = row["load"]
            candidate_pool = candidate_pools_by_dayofyear[dayofyear]  # Done
            if counter < 1:  # first iteration
                prev_day_gen = np.random.choice(candidate_pool["prev_day_gen"].values)
            load_cmp, group_cmp = candidate_pool["load"].values, candidate_pool["prev_day_gen"].values
            covariance = covariance_by_dayofyear_by_group[dayofyear]
            # Calculate probability of each day in the group slice, based on deviation from load and prev_day_gen
            likelihood = scipy.stats.multivariate_normal.pdf(
                list(zip(load_cmp, group_cmp)), mean=[load_ref, prev_day_gen], cov=covariance, allow_singular=True
            )
            pmf_group = np.array(likelihood) / np.sum(likelihood)
            day = np.random.choice(candidate_pool.index.values, p=pmf_group)

            # Update the previous day's generation data for the next iteration
            prev_day_gen = self.daily_gen_by_group[0].loc[day]

            draw_group[(i, self.name)] = day
            counter += 1

        idx = pd.MultiIndex.from_tuples(draw_group.keys())
        df_draw_group = pd.DataFrame(list(draw_group.values()), index=idx, columns=["day"]).unstack(fill_value=0)["day"]

        self.day_draw_map = df_draw_group
