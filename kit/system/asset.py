import enum
import pathlib
from abc import ABC
from abc import abstractmethod

import pyomo.environ as pyo

from kit.core.component import BaseComponent


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


class BaseAssetABC(ABC):
    @abstractmethod
    def construct_investment_rules(self, model: pyo.ConcreteModel):
        """Adds Pyomo components to an already-instantiated Pyomo model.

        Assumes that certain components are also defined on the parent model:
            - MODELED_YEARS
            - DISPATCH_WINDOWS
            - Indexed `blocks`, indexed by all sub-components (e.g., resources)
        """

    @abstractmethod
    def construct_operational_rules(self, model: pyo.ConcreteModel):
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


class BaseAsset(BaseComponent, BaseAssetABC):
    """An Asset is anything with a cost & quantity."""


class BaseAssetGroup(BaseComponent):
    """AssetGroup combines multiple vintages of Assets, since Resolve and Recap treat these differently.

    For Resolve, separate vintages
    For Recap, combine vintages
    """


if __name__ == "__main__":
    BaseAsset.from_csv(filename=pathlib.Path("./data-test/interim/assets/Asset.csv"))
