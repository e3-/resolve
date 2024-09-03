import enum
import pathlib
from abc import ABC
from abc import abstractmethod
from typing import Optional
from typing import Union

import pyomo.environ as pyo
from pydantic import confloat
from pydantic import Field

from new_modeling_toolkit.core.component import Component
from new_modeling_toolkit.core.linkage import Linkage
from new_modeling_toolkit.core.temporal import timeseries as ts


@enum.unique
class AssetCategory(enum.Enum):
    THERMAL = "thermal"
    FIRM = "firm"
    VARIABLE = "variable"
    HYDRO = "hydro"
    STORAGE = "storage"
    DEMAND_RESPONSE = "dr"
    HYBRID_STORAGE = "hybrid_storage"
    FLEXIBLE_LOAD = "flexible_load"


# TODO 2023-04-23: Need a "factory" method to create the right child class based on the resource category


class AssetABC(ABC):
    @abstractmethod
    def construct_investment_block(self, model: pyo.ConcreteModel):
        """Adds Pyomo components to an already-instantiated Pyomo model.

        Assumes that certain components are also defined on the parent model:
            - MODELED_YEARS
            - DISPATCH_WINDOWS
            - Indexed `blocks`, indexed by all sub-components (e.g., resources)
        """

    @abstractmethod
    def construct_operational_block(self, model: pyo.ConcreteModel):
        """Adds Pyomo components to an already-instantiated Pyomo model.

        Assumes that certain components are also defined on the parent model:
            - MODELED_YEARS
            - DISPATCH_WINDOWS
            - Indexed `blocks`, indexed by all sub-components (e.g., resources)
        """

    # @abstractmethod
    # def export_results(self):
    #     pass
    #
    # @abstractmethod
    # def _upsample(self):
    #     pass
    #
    # @property
    # @abstractmethod
    # def scaled_availability_profile(self):
    #     pass

    # @abstractmethod
    # def retrieve_block(self):
    #     pass


class Asset(Component, AssetABC):
    """An Asset is anything with a cost & quantity."""

    class Config:
        validate_assignment = True

    ############
    # Linkages #
    ############
    elcc_surfaces: dict[str, Linkage] = {}
    outage_distributions: dict[str, Linkage] = {}
    policies: dict[str, Linkage] = {}
    zones: dict[str, Linkage] = {}

    #################################
    # Build & Retirement Attributes #
    #################################

    vintage: Optional[Union[None, int, str]] = None
    lifetime_physical: Optional[int] = None

    # planned_start_date
    # planned_retirement_date

    unit_size: Optional[ts.NumericTimeseries] = Field(
        default_factory=ts.Timeseries.zero,
        description="Nameplate MW capacity of the asset. Applies to both directions of power transfer.",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
    )

    can_build_new: bool = Field(
        False,
        description="Whether resource can be expanded (for now only linear capacity expansion).",
    )

    can_retire: bool = Field(
        False,
        description="Whether resource can be retired. By default, resources cannot be retired.",
    )

    capacity_planned: ts.NumericTimeseries = Field(
        default_factory=ts.Timeseries.zero,
        description="Nameplate MW capacity of the asset. Applies to both directions of power transfer.",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
        alias="planned_installed_capacity",
    )
    # TODO 2023-04-30: Maybe timeseries fields should have a "assume_timestamp_is" attribute for now to retain backward compatibility for whether the timestamp column is weather year, model year, or vintage

    ###################
    # Cost Attributes #
    ###################
    lifetime_financial: Optional[int] = None

    cost_fixed_om: ts.NumericTimeseries = Field(
        default_factory=ts.Timeseries.zero,
        description="For new power output capacity, the ongoing fixed O&M of each vintage ($/kW-year). ",
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
        alias="new_capacity_fixed_om_by_vintage",
    )

    # TODO (2023-04-30): Warn that we're going back to EXCLUDING fixed O&M
    cost_investment: ts.NumericTimeseries = Field(
        default_factory=ts.Timeseries.zero,
        description="For new power output capacity, the total annualized fixed cost of investment INCLUDING FOM. "
        "This is an annualized version of an overnight cost that could include financing costs ($/kW-year).",
        default_freq="YS",
        up_method="interpolate",
        down_method="annual",
    )
    # TODO (2023-04-30): Create a property that's the all-in fixed cost investment + fixed O&M to preserve some old behavior

    ##########################
    # Operational Attributes #
    ##########################
    # TODO (2023-04-30): Create a way to read hierarchical tranches of data, in Component
    ramp_rate: confloat(gt=0.0) = Field(
        1.0,
        description="Single-hour ramp rate (% of rating/hour). When used in conjunction with the other ramp rate limits (2-4 hour), a resource's dispatch will be constrained by all applicable ramp rate limits on a rolling basis.",
    )

    td_losses_adjustment: confloat(ge=1.0) = Field(
        1.0,
        description="T&D loss adjustment to gross up to system-level loads. For example, a DER may be able to serve "
        "8% more load (i.e., 1.08) than an equivalent bulk system resource due to T&D losses.",
    )

    ##########################
    # Reliability Attributes #
    ##########################

    stochastic_outage_rate: Optional[confloat(ge=0.0)] = Field(
        None,
        description="Stochastic forced outage rate",
    )

    mean_time_to_repair: Optional[confloat(ge=0.0)] = Field(None, description="Mean time to repair")

    random_seed: Optional[float] = Field(None, description="Random seed")

    ###########
    # Methods #
    ###########

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def outage_distribution(self):
        if self.outage_distributions is None or len(self.outage_distributions) == 0:
            outage_distribution = None
        else:
            outage_dist_name = list(self.outage_distributions.keys())[0]
            outage_distribution = self.outage_distributions[outage_dist_name]._instance_to

        return outage_distribution

    # fmt: off
    def construct_investment_block(self, model: pyo.ConcreteModel):
        """"""
        # Switching to "standard" Python naming conventions (i.e., no capitalization)
        block = model.blocks[self.name]
        block.capacity_selected = pyo.Var(within=pyo.NonNegativeReals)
        block.capacity_retired = pyo.Var(model.MODELED_YEARS, within=pyo.NonNegativeReals)
        block.capacity_operational = pyo.Expression(
            model.MODELED_YEARS,
            rule=lambda block, modeled_year:
                self.capacity_planned.data[modeled_year] + block.capacity_selected - block.capacity_retired[modeled_year]
        )

        block.investment_costs = pyo.Expression(
            model.MODELED_YEARS,
            rule=lambda block, modeled_year:
                block.capacity_selected * self.cost_investment.data[modeled_year] * 10**3
        )

        block.operational_costs = pyo.Expression(
            model.MODELED_YEARS,
            rule=lambda block, modeled_year:
                block.capacity_operational[modeled_year] * self.cost_fixed_om.data[modeled_year] * 10**3
        )

    def construct_operational_block(self, model: pyo.ConcreteModel):
        # TODO 5-11-2023: move into a different block
        pass
    # fmt: on

    # @classmethod
    # def from_csv(cls, **kwargs):


class AssetGroup(Component):
    """AssetGroup combines multiple vintages of Assets, since Resolve and Recap treat these differently.

    For Resolve, separate vintages
    For Recap, combine vintages
    """

    assets: list[Asset]

    min_cumulative_new_build: ts.NumericTimeseries = Field(
        default_factory=ts.Timeseries.zero,
        description="Forced-in new build capacity across active vintages.",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
    )
    min_op_capacity: ts.NumericTimeseries = Field(
        default_factory=ts.Timeseries.zero,
        description="Minimum operational capacity in a given modeled year.",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
    )
    potential: ts.NumericTimeseries = Field(
        default_factory=ts.Timeseries.infinity,
        description="Maximum operational capacity in a given modeled year.",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
    )


if __name__ == "__main__":
    Asset.from_csv(filename=pathlib.Path("./data-test/interim/assets/Asset.csv"))
