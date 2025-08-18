from typing import Optional

from pydantic import Field

from new_modeling_toolkit.core import component
from new_modeling_toolkit.core import dir_str
from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.custom_model import get_units
from new_modeling_toolkit.core.temporal import timeseries as ts


class BuildingShellType(component.Component):
    """
    A building shell type is one type of building shell, for example a residential new construction reference shell or a residential retrofit efficient 1 shell. Each building shell type is mapped
    to one and only one building shell subsector through a linkage.
    """

    ######################
    # Mapping Attributes #
    ######################

    building_shell_subsectors: dict[str, linkage.Linkage] = {}

    ######################
    # Attributes #
    ######################

    # attributes that will be set during stock rollover calculations
    out_stocks: Optional[ts.NumericTimeseries] = Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units("out_stocks")
    )
    out_sales: Optional[ts.NumericTimeseries] = Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units("out_sales")
    )

    out_overnight_capital_cost: Optional[ts.NumericTimeseries] = Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units("out_capital_cost")
    )

    out_levelized_capital_cost: Optional[ts.NumericTimeseries] = Field(
        None, default_freq="YS", up_method="interpolate", down_method="annual", units=get_units("out_capital_cost")
    )

    def revalidate(self):
        if len(self.building_shell_subsectors.keys()) > 1:
            raise ValueError(
                "Building shell type {} is linked to more than one building shell subsector".format(self.name)
            )


if __name__ == "__main__":
    # path to data folder
    data_path = dir_str.data_dir / "interim" / "building_shell_types"
    building_shell_types = BuildingShellType.from_dir(data_path)
    print("building shell type testing complete!")
