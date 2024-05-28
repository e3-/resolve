from pydantic import Field

from new_modeling_toolkit import get_units
from new_modeling_toolkit.core import component
from new_modeling_toolkit.core import dir_str
from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.temporal import timeseries as ts


class BiomassResource(component.Component):
    """A biomass resource can be converted to create a candidate fuel."""

    ######################
    # Mapping Attributes #
    ######################
    candidate_fuels: dict[str, linkage.Linkage] = {}

    ######################
    # Attributes         #
    ######################
    name: str
    feedstock_limit_metric_tons: ts.NumericTimeseries = Field(
        default_freq="YS", up_method="interpolate", down_method="annual", units=get_units("feedstock_limit_metric_tons")
    )


if __name__ == "__main__":
    # path to data folder
    data_path = dir_str.data_dir / "interim" / "biomass_resources"
    # instantiate fuel objects
    fuels = BiomassResource.from_dir(data_path)
