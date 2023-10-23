import pyomo.environ as pyo

from resolve.core.utils.pyomo_utils import mark_pyomo_component
from resolve.resolve.extras import cpuc_irp
from resolve.resolve.model_formulation import ResolveCase

def main(resolve_model: ResolveCase) -> ResolveCase:
    resolve_model = cpuc_irp.main(resolve_model)

    @mark_pyomo_component
    @resolve_model.model.Constraint(resolve_model.model.MODEL_YEARS_AND_CHRONO_PERIODS, resolve_model.model.HOURS)
    def Fuel_Storage_Min_SOC_Constraint(model, model_year, chrono_period, hour):
        """The total amount of fuel stored in all fuel storage resources should be greater than or equal to the amount
        required to run all hydrogen-burning resources at Pmax for 300 hours."""

        if "Hydrogen" not in resolve_model.system.candidate_fuels:
            return pyo.Constraint.Skip
        else:
            # Calculate the fuel required to run all operational hydrogen-burning units at Pmax for 300 hours
            required_fuel = 0.0
            for resource_name in resolve_model.system.candidate_fuels["Hydrogen"].resources.keys():
                required_fuel += (
                    300
                    * resolve_model._get(resolve_model.system.resources[resource_name].fuel_burn_slope)
                    * model.Operational_Capacity_In_Model_Year[resource_name, model_year]
                )

            total_stored_fuel = sum(
                model.Fuel_Storage_SOC_Inter_Intra_Joint[fuel_storage, model_year, chrono_period, hour]
                for fuel_storage in model.FUEL_STORAGES
            )

            # Set the aggregate stored fuel across all storage resources to be greater than the requirement
            constraint = total_stored_fuel >= required_fuel

            return constraint

    @mark_pyomo_component
    @resolve_model.model.Constraint(resolve_model.model.MODEL_YEARS)
    def Fuel_Storage_Min_Pmax_Constraint(model, model_year):
        """The nameplate"""
        if "Hydrogen" not in resolve_model.system.candidate_fuels:
            return pyo.Constraint.Skip
        else:
            # Calculate the fuel required to run all operational hydrogen-burning units at Pmax in any given hour
            required_fuel = 0.0
            for resource_name in resolve_model.system.candidate_fuels["Hydrogen"].resources.keys():
                required_fuel += (
                    +resolve_model._get(resolve_model.system.resources[resource_name].fuel_burn_slope)
                    * model.Operational_Capacity_In_Model_Year[resource_name, model_year]
                )

            total_instantaneous_discharge_capacity = sum(
                model.Operational_Capacity_In_Model_Year[fuel_storage, model_year]
                for fuel_storage in model.FUEL_STORAGES
            )

            constraint = total_instantaneous_discharge_capacity >= required_fuel

            return constraint

    @mark_pyomo_component
    @resolve_model.model.Constraint(resolve_model.model.FUEL_ZONES, resolve_model.model.MODEL_YEARS)
    def Hydrogen_Min_Annual_Production_Constraint(model, fuel_zone, model_year):
        if "Hydrogen" not in resolve_model.system.candidate_fuels:
            return pyo.Constraint.Skip
        else:
            # Calculate the fuel required to run all operational hydrogen-burning units at Pmax for 300 hours
            required_fuel = 0.0
            for resource_name in resolve_model.system.candidate_fuels["Hydrogen"].resources.keys():
                required_fuel += (
                    300
                    * resolve_model._get(resolve_model.system.resources[resource_name].fuel_burn_slope)
                    * model.Operational_Capacity_In_Model_Year[resource_name, model_year]
                )

            constraint = (
                model.Annual_Fuel_Zone_Candidate_Fuel_Production_MMBTU[fuel_zone, "Hydrogen", model_year]
                >= required_fuel
            )

            return constraint

    return resolve_model
