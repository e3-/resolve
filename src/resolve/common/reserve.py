from typing import Optional

from pydantic import Field

from resolve import get_units
from resolve.core import component
from resolve.core import dir_str
from resolve.core import linkage
from resolve.core.temporal import timeseries as ts


class Reserve(component.Component):
    class Config:
        validate_assignment = True

    direction: str = ""
    exclusive: bool = True
    load_following_percentage: Optional[float] = None

    requirement: Optional[ts.NumericTimeseries] = Field(
        default_freq="H", up_method="interpolate", down_method="first", units=get_units("requirement")
    )
    _dynamic_requirement: ts.NumericTimeseries
    category: Optional[str] = None

    ######################
    # Mapping Attributes #
    ######################
    # TODO 2023-05-31: This has switched from `plants` to `resources` here but not yet changed in the Resolve formulation
    loads: dict[str, linkage.LoadToReserve] = {}
    resources: dict[str, linkage.Linkage] = {}
    tx_paths: dict[str, linkage.Linkage] = {}
    zones: dict[str, linkage.Linkage] = {}

    #######################################
    # Unserved Reserve Penalty #
    #######################################
    penalty_unserved_reserve: float = Field(
        10000,
        description="Modeled penalty for unserved operating reserves.",
        units=get_units("penalty_unserved_reserve"),
    )  # $10,000 / MW


if __name__ == "__main__":
    r = Reserve(name="load following")
    # print(r)

    r3 = Reserve.from_dir(dir_str.data_dir / "interim" / "reserves")
    print(r3)
