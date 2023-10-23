import os
from typing import Any
from typing import Optional

from pydantic import Field

from resolve.core import component
from resolve.core import linkage
from resolve.core.temporal import timeseries as ts


class ELCCSurface(component.Component):
    facets: dict = {}
    assets: dict[str, linkage.Linkage] = {}
    # TODO 2023-05-31: Switched to `assets` but not implemented in the Resolve formulation eyt
    policies: dict[str, linkage.Linkage] = {}

    @classmethod
    def from_csv(cls, data_path: os.PathLike, **kwargs) -> dict[Any, "ELCCSurface"]:
        # TODO 2022-04-16: Currently the `from_dir` call is a bit hacky due to quick fix for #214
        facet_dict = ELCCFacets.from_dir(data_path.parent / data_path.stem, **kwargs)
        return {data_path.stem: cls(name=data_path.stem, facets=facet_dict, **kwargs)}

    def revalidate(self):
        for asset_linkage in self.assets.values():
            if asset_linkage.elcc_axis_index is None:
                raise ValueError(
                    f"`AssetToELCC Linkage between Asset `{asset_linkage._instance_from.name}` and ELCCSurface "
                    f"`{self.name}` has no `elcc_axis_index` defined."
                )


class ELCCFacets(component.Component):
    """A single ELCC facet, representing a plane equation.

    axis_0 is the intercept
    axis_1 and axis_2 are the "slopes"
    """

    # TODO: Add more axis
    axis_0: Optional[ts.NumericTimeseries] = Field(None, default_freq="YS", up_method="ffill", down_method="first")
    axis_1: Optional[ts.NumericTimeseries] = Field(None, default_freq="YS", up_method="ffill", down_method="first")
    axis_2: Optional[ts.NumericTimeseries] = Field(None, default_freq="YS", up_method="ffill", down_method="first")
    axis_3: Optional[ts.NumericTimeseries] = Field(None, default_freq="YS", up_method="ffill", down_method="first")
