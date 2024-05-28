from typing import Optional

import pandas as pd
import pyomo.environ as pyo
from pydantic import confloat
from pydantic import Field

from new_modeling_toolkit.common.asset.plant import Plant
from new_modeling_toolkit.core.temporal import timeseries as ts


class FuelConversionPlant(Plant):
    consumed_candidate_fuel_name: str = Field(
        ..., description="Name of the CandidateFuel that is consumed by the plant"
    )
    produced_candidate_fuel_name: str = Field(
        ..., description="Name of the CandidateFuel that is produced by the plant"
    )

    conversion_efficiency: confloat(ge=0, le=1) = Field(
        ..., description="Conversion efficiency of the plant, MMBtu output / MMBtu input"
    )

    variable_cost: ts.NumericTimeseries = Field(
        ...,
        description="Variable cost of operating the plant in each modeled year, excluding fuel costs, "
        "in $/MMBtu of fuel produced.",
        default_freq="YS",
        up_method="ffill",
        down_method="annual",
    )

    @property
    def consumed_candidate_fuel(self):
        if self.consumed_candidate_fuel_name not in self.candidate_fuels:
            raise KeyError(
                f"The specified consumed_candidate_fuel `{self.consumed_candidate_fuel_name}` could not be found in "
                f"the plant's linked candidate fuels"
            )

        return self.candidate_fuels[self.consumed_candidate_fuel_name]._instance_to

    @property
    def produced_candidate_fuel(self):
        if self.produced_candidate_fuel_name not in self.candidate_fuels:
            raise KeyError(
                f"The specified produced_candidate_fuel `{self.produced_candidate_fuel_name}` could not be found in "
                f"the plant's linked candidate fuels"
            )

        return self.candidate_fuels[self.produced_candidate_fuel_name]._instance_to

    opt_annual_fuel_consumption_by_fuel_mmbtu: Optional[pd.Series] = Field(
        None,
        description="Optimized annual fuel consumption by fuel, in MMBtu.",
    )
    opt_annual_produced_fuel_mmbtu: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized annual fuel production, in MMBtu.",
        up_method=None,
        down_method="annual",
    )
    opt_annual_fuel_cost_dollars: Optional[ts.NumericTimeseries] = Field(
        None,
        description="Optimized annual fuel cost, in dollars.",
        default_freq="YS",
        up_method=None,
        down_method="annual",
    )

    @property
    def opt_annual_fuel_consumption_all_fuels_mmbtu(self) -> ts.NumericTimeseries:
        if self.opt_annual_fuel_consumption_by_fuel_mmbtu is None:
            annual_consumption_all_fuels = None
        else:
            annual_consumption_all_fuels = self.opt_annual_fuel_consumption_by_fuel_mmbtu.groupby(["MODEL_YEARS"]).sum()
            annual_consumption_all_fuels.index = pd.to_datetime(annual_consumption_all_fuels.index, format="%Y")
            annual_consumption_all_fuels = ts.NumericTimeseries(
                name="opt_annual_fuel_consumption_all_fuels_mmbtu", data=annual_consumption_all_fuels
            )

        return annual_consumption_all_fuels

    ############################
    # Optimization Expressions #
    ############################
    def Candidate_Fuel_Production_From_Fuel_Production_Plant_In_Timepoint_MMBTU_H(
        self, model, candidate_fuel: str, model_year: int, rep_period: int, hour: int
    ):
        if candidate_fuel == self.produced_candidate_fuel_name:
            production_in_timepoint_mmbtu = self.conversion_efficiency * sum(
                model.Fuel_Conversion_Plant_Consumption_In_Timepoint_MMBTU[self.name, cf, model_year, rep_period, hour]
                for cf in model.CANDIDATE_FUELS
            )
        else:
            production_in_timepoint_mmbtu = 0.0

        return production_in_timepoint_mmbtu

    def Candidate_Fuel_Production_From_Fuel_Production_Plant_MMBTU(
        self, resolve_case, model_year: int, candidate_fuel: str
    ):
        production_from_electrolyzer_mmbtu = resolve_case.sum_timepoint_to_annual(
            model_year,
            "Candidate_Fuel_Production_From_Fuel_Production_Plant_In_Timepoint_MMBTU_H",
            candidate_fuel,
            self.name,
        )
        return production_from_electrolyzer_mmbtu

    def Fuel_Conversion_Plant_Variable_Cost_In_Timepoint(self, model, model_year, rep_period, hour):
        variable_cost = sum(
            model.Candidate_Fuel_Production_From_Fuel_Production_Plant_In_Timepoint_MMBTU_H[
                candidate_fuel, self.name, model_year, rep_period, hour
            ]
            for candidate_fuel in model.CANDIDATE_FUELS
        ) * self.variable_cost.slice_by_year(year=model_year)

        return variable_cost

    ############################
    # Optimization Constraints #
    ############################

    def Fuel_Conversion_Plant_Consumed_Fuel_Constraint(self, model, candidate_fuel, model_year, rep_period, hour):
        if candidate_fuel != self.consumed_candidate_fuel_name:
            constraint = (
                model.Fuel_Conversion_Plant_Consumption_In_Timepoint_MMBTU[
                    self.name, candidate_fuel, model_year, rep_period, hour
                ]
                == 0
            )
        else:
            constraint = pyo.Constraint.Skip

        return constraint

    def Fuel_Conversion_Plant_Max_Hourly_Production_Constraint(
        self, model, candidate_fuel: str, model_year: int, rep_period: int, hour: int
    ):
        if self.name not in model.CANDIDATE_FUEL_ELECTROFUEL_PLANTS[candidate_fuel]:
            constraint = pyo.Constraint.Skip
        elif candidate_fuel != self.produced_candidate_fuel_name:
            constraint = (
                model.Candidate_Fuel_Production_From_Fuel_Production_Plant_In_Timepoint_MMBTU_H[
                    candidate_fuel, self.name, model_year, rep_period, hour
                ]
                == 0
            )
        else:
            constraint = (
                model.Candidate_Fuel_Production_From_Fuel_Production_Plant_In_Timepoint_MMBTU_H[
                    candidate_fuel, self.name, model_year, rep_period, hour
                ]
                <= model.Operational_Capacity_In_Model_Year[self.name, model_year]
            )

        return constraint
