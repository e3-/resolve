from typing import Dict
from typing import Optional

import pandas as pd
from pydantic import Field

from new_modeling_toolkit import get_units
from new_modeling_toolkit.common.asset.plant import Resource
from new_modeling_toolkit.common.load_component import Load
from new_modeling_toolkit.core import component
from new_modeling_toolkit.core import dir_str
from new_modeling_toolkit.core.linkage import Linkage
from new_modeling_toolkit.core.temporal.timeseries import NumericTimeseries
from new_modeling_toolkit.core.utils.core_utils import map_not_none


class Zone(component.Component):
    """This class defines a zone object and its methods."""

    class Config:
        validate_assignment = True

    ######################
    # Mapping Attributes #
    ######################
    biomass_resources: dict[str, Linkage] = {}
    candidate_fuels: dict[str, Linkage] = {}
    electrolyzers: dict[str, Linkage] = {}
    energy_demand_subsectors: dict[str, Linkage] = {}
    final_fuel_demands: dict[str, Linkage] = {}
    fuel_conversion_plants: dict[str, Linkage] = {}
    fuel_resources: dict[str, Linkage] = {}
    fuel_storages: dict[str, Linkage] = {}
    loads: dict[str, Linkage] = {}
    non_energy_subsectors: dict[str, Linkage] = {}
    parent_zones: dict[str, Linkage] = {}
    reserves: dict[str, Linkage] = {}
    resources: dict[str, Linkage] = {}
    stock_rollover_subsectors: dict[str, Linkage] = {}
    subzones: dict[str, Linkage] = {}
    tx_paths: dict[str, Linkage] = {}

    #######################################
    # Overgen / Unserved Energy Penalties #
    #######################################
    penalty_overgen: float = Field(
        10000, description="Modeled penalty for overgeneration.", units=get_units("penalty_overgen")
    )
    penalty_unserved_energy: float = Field(
        10000, description="Modeled penalty for unserved load.", units=get_units("penalty_unserved_energy")
    )

    ########################
    # Optimization Results #
    ########################
    # opt_hourly_energy_price_dollars_per_mwh: Optional[pd.Series] = Field(
    #     None, description="Optimized hourly energy prices from RESOLVE, in $/MWh."
    # )
    opt_hourly_energy_price_unweighted_dollars_per_mwh: Optional[pd.Series] = Field(
        None, description="Optimized hourly energy prices from RESOLVE, in $/MWh."
    )
    opt_annual_unserved_energy_mwh: Optional[NumericTimeseries] = Field(
        None,
        description="Optimized annual unserved energy, in MWh.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_annual_overgeneration_mwh: Optional[NumericTimeseries] = Field(
        None,
        description="Optimized annual overgeneration, in MWh.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )
    opt_annual_input_load_mwh: Optional[NumericTimeseries] = Field(
        None,
        description="Annual zonal input load, in MWh.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )

    @property
    def resource_instances(self) -> Dict[str, Resource]:
        resources = (
            {name: linkage._instance_from for name, linkage in self.resources.items()}
            if self.resources is not None
            else None
        )

        return resources

    @property
    def load_instances(self) -> Dict[str, Load]:
        loads = (
            {name: linkage._instance_from for name, linkage in self.loads.items()} if self.loads is not None else None
        )

        return loads

    @property
    def tx_path_instances_to_zone(self) -> Dict:
        paths_to = (
            {name: linkage._instance_to for name, linkage in self.tx_paths.items() if linkage.to_zone}
            if self.tx_paths is not None
            else None
        )

        return paths_to

    @property
    def tx_path_instances_from_zone(self) -> Dict:
        paths_from = (
            {name: linkage._instance_to for name, linkage in self.tx_paths.items() if linkage.from_zone}
            if self.tx_paths is not None
            else None
        )

        return paths_from

    @property
    def opt_total_operational_capacity_mw(self) -> NumericTimeseries:
        result = self.sum_attribute_from_components(
            component_dict=self.resource_instances,
            attribute="opt_total_operational_capacity_mw",
            timeseries=True,
            skip_none=True,
        )

        return result

    @property
    def opt_operational_planned_capacity_mw(self) -> NumericTimeseries:
        operational_planned_capacity = self.sum_attribute_from_components(
            component_dict=self.resource_instances,
            attribute="opt_operational_planned_capacity_mw",
            timeseries=True,
            skip_none=True,
        )

        return operational_planned_capacity

    @property
    def opt_operational_new_capacity_mw(self) -> NumericTimeseries:
        operational_new_capacity = self.sum_attribute_from_components(
            component_dict=self.resource_instances,
            attribute="opt_operational_new_capacity_mw",
            timeseries=True,
            skip_none=True,
        )

        return operational_new_capacity

    @property
    def opt_annual_net_generation_mwh(self) -> NumericTimeseries:
        net_generation = self.sum_attribute_from_components(
            component_dict=self.resource_instances,
            attribute="opt_annual_net_generation_mwh",
            timeseries=True,
            skip_none=True,
        )

        return net_generation

    @property
    def opt_annual_imports_mwh(self):
        if self.tx_path_instances_to_zone is None and self.tx_path_instances_from_zone is None:
            total_imports = None
        else:
            forward_imports = sum(
                map_not_none(
                    lambda ts: ts.data,
                    [
                        tx_path.opt_annual_transmit_power_forward_mwh
                        for tx_path in self.tx_path_instances_to_zone.values()
                    ],
                )
            )
            reverse_imports = sum(
                map_not_none(
                    lambda ts: ts.data,
                    [
                        tx_path.opt_annual_transmit_power_reverse_mwh
                        for tx_path in self.tx_path_instances_from_zone.values()
                    ],
                )
            )
            total_imports = forward_imports + reverse_imports

            # Note: total_imports should only be a single value equal to 0 if none of the Tx paths have optimization
            #   results stored in them, so None should be returned instead for consistency.
            if isinstance(total_imports, int) and total_imports == 0:
                total_imports = None
            else:
                total_imports = NumericTimeseries(name="opt_total_annual_imports_mwh", data=total_imports)

        return total_imports

    @property
    def opt_annual_exports_mwh(self):
        if self.tx_path_instances_to_zone is None and self.tx_path_instances_from_zone is None:
            total_exports = None
        else:
            reverse_exports = sum(
                map_not_none(
                    lambda ts: ts.data,
                    [
                        tx_path.opt_annual_transmit_power_reverse_mwh
                        for tx_path in self.tx_path_instances_to_zone.values()
                    ],
                )
            )
            forward_exports = sum(
                map_not_none(
                    lambda ts: ts.data,
                    [
                        tx_path.opt_annual_transmit_power_forward_mwh
                        for tx_path in self.tx_path_instances_from_zone.values()
                    ],
                )
            )
            total_exports = forward_exports + reverse_exports

            # Note: total_exports should only be a single value equal to 0 if none of the Tx paths have optimization
            #   results stored in them, so None should be returned instead for consistency.
            if isinstance(total_exports, int) and total_exports == 0:
                total_exports = None
            else:
                total_exports = NumericTimeseries(
                    name="opt_total_annual_exports_mwh",
                    data=total_exports,
                )

        return total_exports

    @property
    def opt_annual_net_imports_mwh(self):
        if self.opt_annual_imports_mwh is None and self.opt_annual_exports_mwh is None:
            net_imports = None
        elif self.opt_annual_exports_mwh is None:
            net_imports = NumericTimeseries(name="opt_net_annual_imports_mwh", data=self.opt_annual_imports_mwh.data)
        elif self.opt_annual_imports_mwh is None:
            net_imports = NumericTimeseries(name="opt_net_annual_imports_mwh", data=self.opt_annual_exports_mwh.data)
        else:
            net_imports = NumericTimeseries(
                name="opt_net_annual_imports_mwh",
                data=self.opt_annual_imports_mwh.data - self.opt_annual_exports_mwh.data,
            )

        return net_imports

    # TODO (2022-04-16): Make this a property or generally more dynamic
    def get_aggregated_load(self, temporal_settings, model_year: int, period: int, hour: int) -> float:
        """
        Queries aggregated load in zone at given timepoint
        """
        if self.load_instances is not None:
            return sum(
                load.get_load(temporal_settings, model_year, period, hour) for load in self.load_instances.values()
            )
        else:
            return 0

    def get_aggregated_load_profile(self, model_year):
        """
        Queries aggregated load profile in zone
        """
        agg_load_profile = 0
        for inst in self.loads.keys():
            agg_load_profile += self.loads[inst]._instance_from.scaled_profile_by_modeled_year[model_year].data
        return agg_load_profile


if __name__ == "__main__":
    test_zone = Zone(name="Test zone")
    print(f"From test object: {test_zone}")

    test_zone_csv = Zone.from_dir(data_path=dir_str.data_dir / "interim" / "zones")
    print(f"From csv file: {test_zone_csv}")

    test_zone = Zone(loads={"load_1": Load()})
