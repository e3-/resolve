from typing import Dict
from typing import Optional

import pandas as pd
from pydantic import Field

from new_modeling_toolkit.core import component
from new_modeling_toolkit.core import linkage
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.utils.core_utils import map_not_none
from new_modeling_toolkit.system.fuel.electrolyzer import Electrolyzer
from new_modeling_toolkit.system.fuel.storage import FuelStorage
from new_modeling_toolkit.system.fuel.transport import FuelTransportation


class FuelZone(component.Component):
    class Config:
        validate_assignment = True

    ######################
    # Mapping Attributes #
    ######################
    fuel_transportations: dict[str, linkage.Linkage] = {}
    electrolyzers: dict[str, linkage.Linkage] = {}
    fuel_storages: dict[str, linkage.Linkage] = {}
    fuel_conversion_plants: dict[str, linkage.Linkage] = {}
    assets: dict[str, linkage.Linkage] = {}
    resources: dict[str, linkage.Linkage] = {}
    plants: dict[str, linkage.Linkage] = {}
    candidate_fuels: dict[str, linkage.Linkage] = {}
    final_fuels: dict[str, linkage.Linkage] = {}

    penalty_overproduction: float = Field(
        2930.83,  # $10,000/MWh converted to $/MMBtu
        description="Modeled penalty for overgeneration.",
    )
    penalty_unserved_energy: float = Field(
        2930.83,  # $10,000/MWh converted to $/MMBtu
        description="Modeled penalty for unserved load.",
    )

    @property
    def fuel_production_plants(self):
        if self.electrolyzers is None and self.fuel_conversion_plants is None:
            fuel_production_plants = None
        else:
            fuel_production_plants = (self.electrolyzers or dict()) | (self.fuel_conversion_plants or dict())

        return fuel_production_plants

    ########################################
    # Optimization Expressions/Constraints #
    ########################################

    def Net_Candidate_Fuel_Imports_In_Timepoint_MMBTU_H(
        self, resolve_case, candidate_fuel, model_year, rep_period, hour
    ):
        """
        Calculates net candidate imports via fuel transportation resources.
        """
        # TODO: Use self.fuel_transportation_from_instances and self.fuel_transportation_to_instances
        imports_exports = 0.0
        if candidate_fuel in self.candidate_fuels.keys():
            for fuel_transportation in resolve_case.model.FUEL_TRANSPORTATIONS:
                if (
                    resolve_case.system.fuel_transportations[fuel_transportation].unique_candidate_fuel
                    == candidate_fuel
                ):
                    if resolve_case.model.fuel_transportation_to[fuel_transportation] == self.name:
                        imports_exports += resolve_case.model.Transmit_Candidate_Fuel_MMBTU_H[
                            fuel_transportation, model_year, rep_period, hour
                        ]
                    elif resolve_case.model.fuel_transportation_from[fuel_transportation] == self.name:
                        imports_exports -= resolve_case.model.Transmit_Candidate_Fuel_MMBTU_H[
                            fuel_transportation, model_year, rep_period, hour
                        ]
        return imports_exports

    def Fuel_Zone_Candidate_Fuel_Production_In_Timepoint_MMBTU_H(
        self, model, candidate_fuel, model_year, rep_period, hour
    ):
        """
        Candidate fuel production by in-zone electrolyzers
        """
        if self.fuel_production_plants is None or len(self.fuel_production_plants) == 0:
            return 0.0
        else:
            return sum(
                model.Candidate_Fuel_Production_From_Fuel_Production_Plant_In_Timepoint_MMBTU_H[
                    candidate_fuel, fuel_production_plant, model_year, rep_period, hour
                ]
                for fuel_production_plant in self.fuel_production_plants.keys()
                if candidate_fuel
                in self.fuel_production_plants[fuel_production_plant]._instance_from.candidate_fuels.keys()
            )

    def Fuel_Zone_Resource_Candidate_Fuel_Consumption_In_Timepoint_MMBTU_H(
        self, model, candidate_fuel, model_year, rep_period, hour
    ):
        """
        Candidate fuel consumption for generation purposes in a given fuel zone.
        """
        consumption = 0.0
        if self.resources is not None:
            for resource in self.resources.keys():
                if candidate_fuel in model.RESOURCE_CANDIDATE_FUELS[resource]:
                    consumption += model.Resource_Fuel_Consumption_In_Timepoint_MMBTU[
                        resource, candidate_fuel, model_year, rep_period, hour
                    ]
        return consumption

    def Fuel_Zone_Candidate_Fuel_Storage_In_Timepoint_MMBTU_H(
        self, model, candidate_fuel, model_year, rep_period, hour, temporal_settings
    ):
        """
        Candidate fuel storage in a given fuel zone.
        """
        storage = 0.0
        if self.fuel_storage_instances is not None:
            for fuel_storage in self.fuel_storage_instances.keys():
                # TODO: (BKW) We will need to make some distinction between candidate fuels stored and candidate fuels used for operations
                if candidate_fuel in self.fuel_storages[fuel_storage]._instance_from.candidate_fuels.keys():
                    storage += model.Fuel_Storage_Charging_MMBtu_per_Hr[fuel_storage, model_year, rep_period, hour]

                    storage -= model.Fuel_Storage_Discharging_MMBtu_per_Hr[fuel_storage, model_year, rep_period, hour]
        return storage

    def Net_Fuel_Zone_Candidate_Fuel_Consumption_In_Timepoint_MMBTU_H(
        self, model, candidate_fuel, model_year, rep_period, hour
    ):
        return (
            model.Fuel_Zone_Resource_Candidate_Fuel_Consumption_In_Timepoint_MMBTU_H[
                self.name, candidate_fuel, model_year, rep_period, hour
            ]
            + model.Fuel_Zone_Candidate_Fuel_Storage_In_Timepoint_MMBTU_H[
                self.name, candidate_fuel, model_year, rep_period, hour
            ]
        )

    def Fuel_Zone_Candidate_Fuel_Constraint(self, model, candidate_fuel, model_year, rep_period, hour):
        """
        Ensures that net hourly inflows of candidate fuels into fuel zone is at least as great as net
        consumption of candidate fuels. Excess candidate fuels inflows will be applied to annual final fuel demands
        in another constraint.
        """

        return (
            model.Fuel_Zone_Candidate_Fuel_Production_In_Timepoint_MMBTU_H[
                self.name, candidate_fuel, model_year, rep_period, hour
            ]
            + model.Net_Candidate_Fuel_Imports_In_Timepoint_MMBTU_H[
                self.name, candidate_fuel, model_year, rep_period, hour
            ]
            + model.Fuel_Zone_Candidate_Fuel_Commodity_Production_In_Timepoint_MMBTU_H[
                self.name, candidate_fuel, model_year, rep_period, hour
            ]
            - model.Unserved_Energy_MMBTU_H[self.name, candidate_fuel, model_year, rep_period, hour]
            + model.Overproduction_MMBTU_H[self.name, candidate_fuel, model_year, rep_period, hour]
            - model.Net_Fuel_Zone_Candidate_Fuel_Consumption_In_Timepoint_MMBTU_H[
                self.name, candidate_fuel, model_year, rep_period, hour
            ]
            - sum(
                model.Fuel_Zone_Candidate_Fuel_Consumption_By_Final_Fuel_Demands_MMBTU_H[
                    self.name, candidate_fuel, final_fuel_demand, model_year, rep_period, hour
                ]
                for final_fuel_demand in model.FINAL_FUEL_DEMANDS
            )
            == 0.0
        )

    def Annual_Fuel_Zone_Candidate_Fuel_Consumption_For_Final_Fuel_Demands_MMBTU(
        self, model, candidate_fuel, model_year
    ):
        return sum(
            model.Annual_Fuel_Zone_Candidate_Fuel_Consumption_By_Final_Fuel_Demands_MMBTU[
                self.name, candidate_fuel, final_fuel_demand, model_year
            ]
            for final_fuel_demand in model.FINAL_FUEL_DEMANDS
            if candidate_fuel in model.FINAL_FUEL_DEMAND_CANDIDATE_FUELS[final_fuel_demand]
        )

    def Annual_Fuel_Zone_Candidate_Fuel_Balance(self, model, candidate_fuel, model_year):
        return (
            model.Annual_Fuel_Zone_Candidate_Fuel_Production_MMBTU[self.name, candidate_fuel, model_year]
            + model.Annual_Net_Candidate_Fuel_Imports_MMBTU[self.name, candidate_fuel, model_year]
            - model.Annual_Net_Fuel_Zone_Candidate_Fuel_Consumption_MMBTU[self.name, candidate_fuel, model_year]
            - model.Annual_Fuel_Zone_Candidate_Fuel_Consumption_For_Final_Fuel_Demands_MMBTU[
                self.name, candidate_fuel, model_year
            ]
            == 0.0
        )

    def Satisfy_Fuel_Zone_Final_Fuel_Hourly_Demands_Constraint(
        self, temporal_settings, model, final_fuel_demand, model_year, rep_period, hour
    ):
        return sum(
            model.Fuel_Zone_Candidate_Fuel_Consumption_By_Final_Fuel_Demands_MMBTU_H[
                self.name, candidate_fuel, final_fuel_demand, model_year, rep_period, hour
            ]
            for candidate_fuel in model.FINAL_FUEL_DEMAND_CANDIDATE_FUELS[final_fuel_demand]
        ) == self.final_fuels[final_fuel_demand]._instance_from.demand.slice_by_timepoint(
            temporal_settings=temporal_settings, model_year=model_year, period=rep_period, hour=hour
        )

    def Satisfy_Fuel_Zone_Final_Fuel_Annual_Demands_Constraint(self, model, final_fuel_demand, model_year):
        """
        Ensures that annual zonal final fuel demands are met by candidate consumption for final fuel demands.
        """
        return sum(
            model.Annual_Fuel_Zone_Candidate_Fuel_Consumption_By_Final_Fuel_Demands_MMBTU[
                self.name, candidate_fuel, final_fuel_demand, model_year
            ]
            for candidate_fuel in model.FINAL_FUEL_DEMAND_CANDIDATE_FUELS[final_fuel_demand]
        ) == self.final_fuels[final_fuel_demand]._instance_from.demand.slice_by_year(model_year)

    ########################
    # Optimization Results #
    ########################
    opt_hourly_fuel_price_unweighted_dollars_per_mmbtu: Optional[pd.Series] = Field(
        None, description="Optimized hourly fuel prices from RESOLVE, in $/MMBTU."
    )

    @property
    def electrolyzer_instances(self) -> Dict[str, Electrolyzer]:
        electrolyzers = (
            {name: linkage._instance_from for name, linkage in self.electrolyzers.items()}
            if self.electrolyzers is not None
            else None
        )
        return electrolyzers

    @property
    def fuel_storage_instances(self) -> Dict[str, FuelStorage]:
        fuel_storages = (
            {name: linkage._instance_from for name, linkage in self.fuel_storages.items()}
            if self.fuel_storages is not None
            else None
        )
        return fuel_storages

    @property
    def fuel_transportation_instances_to_zone(
        self,
    ) -> Dict[str, FuelTransportation]:
        paths_to = (
            {name: linkage._instance_to for name, linkage in self.fuel_transportations.items() if linkage.to_zone}
            if self.fuel_transportations is not None
            else None
        )
        return paths_to

    @property
    def fuel_transportation_instances_from_zone(
        self,
    ) -> Dict[str, FuelTransportation]:
        paths_from = (
            {name: linkage._instance_to for name, linkage in self.fuel_transportations.items() if linkage.from_zone}
            if self.fuel_transportations is not None
            else None
        )
        return paths_from

    @property
    def opt_total_operational_electrolyzer_capacity_mw(self) -> ts.NumericTimeseries:
        operational_capacity = self.sum_attribute_from_components(
            component_dict=self.electrolyzer_instances,
            attribute="opt_total_operational_capacity_mw",
            timeseries=True,
            skip_none=True,
        )
        return operational_capacity

    @property
    def opt_operational_planned_electrolyzer_capacity_mw(self) -> ts.NumericTimeseries:
        operational_capacity = self.sum_attribute_from_components(
            component_dict=self.electrolyzer_instances,
            attribute="opt_operational_planned_capacity_mw",
            timeseries=True,
            skip_none=True,
        )
        return operational_capacity

    @property
    def opt_operational_new_electrolyzer_capacity_mw(self) -> ts.NumericTimeseries:
        operational_capacity = self.sum_attribute_from_components(
            component_dict=self.electrolyzer_instances,
            attribute="opt_operational_new_capacity_mw",
            timeseries=True,
            skip_none=True,
        )
        return operational_capacity

    @property
    def opt_annual_imports_mmbtu(self) -> ts.NumericTimeseries:
        if self.fuel_transportation_instances_to_zone is None and self.fuel_transportation_instances_from_zone is None:
            total_imports = None
        else:
            forward_imports = sum(
                map_not_none(
                    lambda ts: ts.data,
                    [
                        fuel_transportation.opt_annual_flow_forward_mmbtu
                        for fuel_transportation in self.fuel_transportation_instances_to_zone.values()
                    ],
                )
            )
            reverse_imports = sum(
                map_not_none(
                    lambda ts: ts.data,
                    [
                        fuel_transportation.opt_annual_flow_reverse_mmbtu
                        for fuel_transportation in self.fuel_transportation_instances_from_zone.values()
                    ],
                )
            )
            total_imports = forward_imports + reverse_imports

            # Note: total_imports should only be a single value equal to 0 if none of fuel flow paths have
            # optimization results stored in them, so None should be returned instead for consistency.
            if isinstance(total_imports, int) and total_imports == 0:
                total_imports = None
            else:
                total_imports = ts.NumericTimeseries(name="opt_total_annual_imports_mmbtu", data=total_imports)

        return total_imports

    @property
    def opt_annual_exports_mmbtu(self) -> ts.NumericTimeseries:
        if self.fuel_transportation_instances_to_zone is None and self.fuel_transportation_instances_from_zone is None:
            total_exports = None
        else:
            forward_exports = sum(
                map_not_none(
                    lambda ts: ts.data,
                    [
                        fuel_transportation.opt_annual_flow_reverse_mmbtu
                        for fuel_transportation in self.fuel_transportation_instances_to_zone.values()
                    ],
                )
            )
            reverse_exports = sum(
                map_not_none(
                    lambda ts: ts.data,
                    [
                        fuel_transportation.opt_annual_flow_forward_mmbtu
                        for fuel_transportation in self.fuel_transportation_instances_from_zone.values()
                    ],
                )
            )
            total_exports = forward_exports + reverse_exports

            # Note: total_exports should only be a single value equal to 0 if none of fuel flow paths have
            # optimization results stored in them, so None should be returned instead for consistency.
            if isinstance(total_exports, int) and total_exports == 0:
                total_exports = None
            else:
                total_exports = ts.NumericTimeseries(name="opt_total_annual_exports_mmbtu", data=total_exports)

        return total_exports

    @property
    def opt_annual_net_imports_mmbtu(self) -> ts.NumericTimeseries:
        if self.opt_annual_imports_mmbtu is None and self.opt_annual_exports_mmbtu is None:
            net_imports = None
        elif self.opt_annual_exports_mmbtu is None:
            net_imports = ts.NumericTimeseries(
                name="opt_net_annual_imports_mmbtu", data=self.opt_annual_imports_mmbtu.data
            )
        elif self.opt_annual_imports_mmbtu is None:
            net_imports = ts.NumericTimeseries(
                name="opt_net_annual_exports_mmbtu", data=self.opt_annual_exports_mmbtu.data
            )
        else:
            net_imports = ts.NumericTimeseries(
                name="opt_annual_imports_mmbtu",
                data=self.opt_annual_imports_mmbtu.data - self.opt_annual_exports_mmbtu.data,
            )
        return net_imports
