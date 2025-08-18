import enum
import itertools
from typing import Annotated
from typing import ClassVar
from typing import Union

import pandas as pd
from pydantic import Field
from pyomo import environ as pyo

from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.custom_model import ModelType
from new_modeling_toolkit.core.custom_model import units
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.core.temporal.settings import DispatchWindowEdgeEffects
from new_modeling_toolkit.core.temporal.timeseries import NumericTimeseries
from new_modeling_toolkit.system import FuelProductionPlant
from new_modeling_toolkit.system.fuel.fuel_production_plant import FuelProductionPlantGroup
from new_modeling_toolkit.system.generics.process import ChargeProcess


@enum.unique
class StorageDurationConstraint(enum.Enum):
    FIXED = "fixed"
    MINIMUM = "minimum"
    MAXIMUM = "maximum"


# TODO (BKW 10/22/2024): We should probably implement a generic storage class that contains all of the storage logic
#  spread between both the `FuelStorage` and the `StorageResource` classes.
class FuelStorage(FuelProductionPlant):

    SAVE_PATH: ClassVar[str] = "plants/fuel_storage_plants"

    charging_processes: Annotated[
        dict[Union[tuple[str, str], str], ChargeProcess], Metadata(category=FieldCategory.OPERATIONS)
    ] = Field(
        default_factory=dict,
        description="These three-way linkages define the input-output charging relationship on the fuel storage plant.",
    )

    duration: Annotated[
        float, Metadata(category=FieldCategory.OPERATIONS, show_year_headers=False, units=units.hour)
    ] = Field(
        description=(
            "Operational time of the fuel storage at a specified operation level before it runs out of energy [hours]"
        ),
        alias="storage_duration",
        title=f"Duration",
        ge=0,
    )

    duration_constraint: Annotated[StorageDurationConstraint, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        default=StorageDurationConstraint.FIXED,
    )

    ###################
    # Cost Attributes #
    ###################
    annualized_storage_capital_cost: Annotated[
        float, Metadata(units=units.dollar / units.MMBtu_year, category=FieldCategory.BUILD)
    ] = Field(
        default=0.0,
        description="$/MMBtu-yr. For new storage capacity, the annualized fixed cost of investment. "
        "This is an annualized version of an overnight cost that could include financing costs ($/kWh-year).",
        title=f"Storage Levelized Fixed Cost",
    )
    annualized_storage_fixed_om_cost: Annotated[
        ts.NumericTimeseries, Metadata(units=units.dollar / units.MMBtu_year, category=FieldCategory.BUILD)
    ] = Field(
        default_factory=ts.NumericTimeseries.zero,
        description="$/MMBtu-yr. For the planned portion of the resource's storage capacity, "
        "the ongoing fixed O&M cost",
        default_freq="YS",
        up_method="interpolate",
        down_method="mean",
        alias="new_storage_capacity_fixed_om_by_vintage",
        title=f"Storage Fixed O&M Cost",
    )
    variable_cost_input: Annotated[
        ts.NumericTimeseries,
        Metadata(
            category=FieldCategory.OPERATIONS,
            units=units.dollar / units.MMBtu,
            excel_short_title="VO&M In",
        ),
    ] = Field(
        default_factory=ts.NumericTimeseries.zero,
        description="Variable O&M cost per MMBtu generated.",
        default_freq="H",
        up_method="ffill",
        down_method="mean",
        weather_year=True,
        title=f"Variable O&M Cost",
    )

    ##########################
    # Operational Attributes #
    ##########################
    allow_inter_period_sharing: Annotated[bool, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        False,
        description="For fuel storage plants that have chronological energy storage capability, enable inter-period"
        " energy/state-of-charge tracking",
        title=f"Inter-Period SoC",
    )
    min_input_profile: Annotated[
        ts.FractionalTimeseries,
        Metadata(category=FieldCategory.OPERATIONS, units=units.unitless, excel_short_title="Max Input Profile"),
    ] = Field(
        default_factory=ts.FractionalTimeseries.zero,
        description="Fixed shape of storage's (e.g. flat shape for storage resources) min input.",
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
        title=f"Min Input Profile",
    )
    max_input_profile: Annotated[
        ts.FractionalTimeseries,
        Metadata(category=FieldCategory.OPERATIONS, units=units.unitless, excel_short_title="Max Input Profile"),
    ] = Field(
        default_factory=ts.FractionalTimeseries.one,
        description="Fixed shape of storage's (e.g. flat shape for storage resources) max input.",
        default_freq="H",
        up_method="interpolate",
        down_method="mean",
        weather_year=True,
        title=f"Max Input Profile",
    )
    parasitic_loss: Annotated[float, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        0,
        description="Hourly state of charge losses.",
        title="Parasitic Losses",
        ge=0,
        le=1,
    )
    min_state_of_charge: Annotated[float, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        0,
        description="Minimum state of charge at any given time.",
        title=f"Min State of Charge",
    )

    ##################################################
    # Build and Retirement Outputs from Solved Model #
    ##################################################
    """These three attributes are outputs, not inputs. They are initialized to None and are updated to their chosen
    optimal values after the RESOLVE model is solved. The attributes are used to give build and retirement decisions to
    a model run in production simulation mode."""
    operational_storage_capacity: NumericTimeseries | None = Field(
        None, down_method="mean", up_method="ffill", default_freq="YS"
    )
    selected_storage_capacity: float | None = None
    retired_storage_capacity: NumericTimeseries | None = Field(
        None, down_method="mean", up_method="ffill", default_freq="YS"
    )
    cumulative_retired_storage_capacity: ts.NumericTimeseries | None = Field(
        None, down_method="mean", up_method="ffill", default_freq="YS"
    )

    @property
    def planned_storage_capacity(self) -> pd.Series:
        """
        This property is for fuel storage only now.
        """

        return self.planned_capacity.data * self.duration

    @property
    def produced_products(self):
        return {
            process.produced_product.name: process.produced_product for process in self.discharging_processes.values()
        }

    @property
    def stored_products(self):
        return {
            process.produced_product.name: process.produced_product
            for process in self.charging_processes.values()
            if process.produced_product.name == self.primary_product
        }

    @property
    def discharging_processes(self):
        return self.processes

    @property
    def storage_processes(self):
        return self.charging_processes | self.discharging_processes

    @property
    def primary_charging_processes(self):
        return [
            process
            for process in self.charging_processes.values()
            if process.produced_product.name == self.primary_product
        ]

    @property
    def primary_discharging_processes(self):
        return [
            process
            for process in self.discharging_processes.values()
            if process.produced_product.name == self.primary_product
        ]

    @property
    def charging_efficiency(self):
        return self.charging_processes[(self.primary_product, self.primary_product)].conversion_rate

    @property
    def discharging_efficiency(self):
        return self.discharging_processes[(self.primary_product, self.primary_product)].conversion_rate

    def save_capacity_expansion_results(self):
        super().save_capacity_expansion_results()
        self.save_operational_storage_capacity()
        self.save_selected_storage_capacity()
        self.save_retired_storage_capacity()
        self.save_cumulative_retired_storage_capacity()

    def save_operational_storage_capacity(self):
        """Save the resulting operational storage capacity after the RESOLVE model has been solved."""
        model_years = self.formulation_block.operational_storage_capacity.extract_values().keys()
        capacities = self.formulation_block.operational_storage_capacity[:].expr()
        self.operational_storage_capacity = NumericTimeseries(
            name="operational_storage_capacity", data=pd.Series(index=model_years, data=capacities)
        )

    def save_selected_storage_capacity(self):
        """Save the resulting selected storage capacity after the RESOLVE model has been solved."""
        self.selected_storage_capacity = self.formulation_block.selected_storage_capacity.value

    def save_retired_storage_capacity(self):
        model_years = self.formulation_block.retired_storage_capacity.extract_values().keys()
        retirements = list(self.formulation_block.retired_storage_capacity.extract_values().values())
        self.retired_storage_capacity = NumericTimeseries(
            name="retired_storage_capacity", data=pd.Series(index=model_years, data=retirements)
        )

    def save_cumulative_retired_storage_capacity(self):
        """Save the resulting retired storage capacity after the RESOLVE model has been solved."""
        model_years = self.formulation_block.retired_storage_capacity.extract_values().keys()
        cumulative_retirements = list(
            itertools.accumulate(self.formulation_block.retired_storage_capacity.extract_values().values())
        )
        self.cumulative_retired_storage_capacity = ts.NumericTimeseries(
            name="cumulative_retired_storage_capacity", data=pd.Series(index=model_years, data=cumulative_retirements)
        )

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_investment_rules(model=model, construct_costs=construct_costs)

        pyomo_components.update(
            planned_storage_capacity=pyo.Param(
                model.MODELED_YEARS,
                initialize=lambda b, year: self.planned_storage_capacity[year],
                doc=f"Planned Storage Capacity (MMBtu)",
            ),
            selected_storage_capacity=pyo.Var(
                within=pyo.NonNegativeReals,
                doc=f"Selected Storage Capacity (MMBtu)",
            ),
            retired_storage_capacity=pyo.Var(
                model.MODELED_YEARS,
                within=pyo.NonNegativeReals,
                doc=f"Retired Storage Capacity (MMBtu)",
            ),
            operational_storage_capacity=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._operational_storage_capacity,
                doc=f"Operational Storage Capacity (MMBtu)",
            ),
            storage_capacity_duration_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                rule=self._storage_capacity_duration_constraint
            ),
            retired_storage_capacity_max_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                rule=self._retired_storage_capacity_max_constraint
            ),
            storage_physical_lifetime_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                rule=self._storage_physical_lifetime_constraint
            )
        )

        ##########################################
        # Production Simulation Mode Constraints #
        ##########################################
        if model.TYPE == ModelType.RESOLVE and model.production_simulation_mode:
            self.formulation_block.chosen_selected_storage_capacity = pyo.Param(
                initialize=self.selected_storage_capacity
            )
            self.formulation_block.chosen_retired_storage_capacity = pyo.Param(
                model.MODELED_YEARS, initialize=self.retired_storage_capacity.data.loc[list(model.MODELED_YEARS)]
            )
            self.formulation_block.chosen_operational_storage_capacity = pyo.Param(
                model.MODELED_YEARS, initialize=self.operational_storage_capacity.data.loc[list(model.MODELED_YEARS)]
            )
            pyomo_components.update(
                prod_sim_selected_storage_capacity_constraint=pyo.Constraint(
                    rule=self._prod_sim_selected_storage_capacity_constraint
                ),
                prod_sim_retired_storage_capacity_constraint=pyo.Constraint(
                    model.MODELED_YEARS, rule=self._prod_sim_retired_storage_capacity_constraint
                ),
                prod_sim_operational_storage_capacity_constraint=pyo.Constraint(
                    model.MODELED_YEARS, rule=self._prod_sim_operational_storage_capacity_constraint
                ),
            )

        if construct_costs:
            pyomo_components.update(
                annual_storage_capital_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_storage_capital_cost,
                    doc="Annual Storage Capacity Capital Cost ($)",
                ),
                annual_storage_fixed_om_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_storage_fixed_om_cost,
                    doc="Annual Storage Capacity Fixed O&M Cost ($)",
                ),
                annual_total_investment_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_investment_cost,
                    doc="Annual Total Investment Cost ($)",
                ),
            )

        return pyomo_components

    def _construct_operational_rules(
        self, model: ModelTemplate, construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

        INPUTS = pyo.Set(initialize=self.consumed_products.keys())
        OUTPUTS = pyo.Set(initialize=self.produced_products.keys())
        STORED_PRODUCTS = pyo.Set(initialize=self.stored_products.keys())

        pyomo_components.update(
            operation=pyomo_components["operation"],
            charge=pyo.Var(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                within=pyo.NonNegativeReals,
                initialize=0,
                doc=f"Hourly Charge (MMBtu per hour)",
            ),
            storage=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._storage,
                doc=f"Hourly Storage (MMBtu per hour)",
            ),
            charging_consumption=pyo.Expression(
                INPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._charging_consumption,
            ),
            discharging_consumption=pyo.Expression(
                INPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._discharging_consumption,
            ),
            consumption=pyo.Expression(
                INPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._consumption,
                doc=f"Hourly Consumption of Input Product (Product Units per hour)",
            ),
            production=pyo.Expression(
                OUTPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._production,
                doc=f"Hourly Production of Output Product (Product Units per hour)",
            ),
            consumed_product_capture=pyo.Expression(
                INPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._consumed_product_capture,
                doc="Hourly Consumed Product Capture (Product Units per hour)",
            ),
            consumed_product_from_zone=pyo.Expression(
                INPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._consumed_product_from_zone,
                doc="Hourly Consumed Product From Zone (Product Units per hour)",
            ),
            produced_product_to_zone=pyo.Expression(
                OUTPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._produced_product_to_zone,
                doc="Hourly Produced Product To Zone (Product Units per hour)",
            ),
            produced_product_release=pyo.Expression(
                OUTPUTS,
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._produced_product_release,
                doc="Hourly Produced Product Release (Product Units per hour)",
            ),
            scaled_min_output_profile=pyomo_components["scaled_min_output_profile"],
            scaled_max_output_profile=pyomo_components["scaled_max_output_profile"],
            scaled_min_input_profile=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._scaled_min_input_profile,
            ),
            scaled_max_input_profile=pyo.Expression(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._scaled_max_input_profile
            ),
            min_output_constraint=pyomo_components["min_output_constraint"],
            max_output_constraint=pyomo_components["max_output_constraint"],
            min_input_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._min_input_constraint,
            ),
            max_input_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._max_input_constraint,
            ),
            mileage_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._mileage_constraint,
            ),
            soc_intra_period=pyo.Var(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                within=pyo.Reals,
                initialize=0,
                doc=f"SOC Intra Period (MMBtu)",
            ),
            soc_inter_period=pyo.Var(
                model.MODELED_YEARS,
                model.CHRONO_PERIODS,
                within=pyo.NonNegativeReals,
                initialize=0,
            ),
            soc_inter_intra_joint=pyo.Expression(
                model.MODELED_YEARS,
                model.CHRONO_PERIODS_AND_TIMESTAMPS,
                rule=self._soc_inter_intra_joint,
                doc=f"SOC Inter-Intra Join (MMBtu)",
            ),
            simultaneous_charging_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._simultaneous_charging_constraint,
            ),
            soc_inter_intra_max_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.CHRONO_PERIODS_AND_TIMESTAMPS,
                rule=self._soc_inter_intra_max_constraint,
            ),
            soc_inter_intra_min_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.CHRONO_PERIODS_AND_TIMESTAMPS,
                rule=self._soc_inter_intra_min_constraint,
            ),
            soc_intra_tracking_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                rule=self._soc_intra_tracking_constraint,
            ),
            soc_intra_anchoring_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.DISPATCH_WINDOWS,
                rule=self._soc_intra_anchoring_constraint,
            ),
            soc_inter_tracking_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                model.CHRONO_PERIODS,
                rule=self._soc_inter_tracking_constraint,
            )
        )

        if construct_costs:
            pyomo_components.update(
                variable_cost_dispatched=pyomo_components["variable_cost_dispatched"],
                production_tax_credit=pyomo_components["production_tax_credit"],
                annual_variable_cost_dispatched=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_variable_cost_dispatched,
                    doc="Annual Discharging Total Variable Cost ($)",
                ),
                variable_cost_charging=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._variable_cost_charging,
                ),
                annual_variable_cost_charging=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_variable_cost_charging,
                    doc="Annual Charging Input Variable Cost ($)"
                ),
                annual_variable_cost=pyomo_components["annual_variable_cost"],
                annual_production_tax_credit=pyomo_components["annual_production_tax_credit"],
                consumed_commodity_product_cost=pyomo_components["consumed_commodity_product_cost"],
                annual_consumed_commodity_product_cost=pyomo_components["annual_consumed_commodity_product_cost"],
                annual_total_operational_cost=pyomo_components["annual_total_operational_cost"],
            )

        return pyomo_components

    def _construct_output_expressions(self, construct_costs: bool):
        super()._construct_output_expressions(construct_costs)
        model: ModelTemplate = self.formulation_block.model()

        if self.has_operational_rules:
            self.formulation_block.annual_charge = pyo.Expression(
                model.MODELED_YEARS, rule=self._annual_charge, doc=f"Annual Charge (MMBtu)"
            )

            self.formulation_block.annual_storage = pyo.Expression(
                model.MODELED_YEARS,
                rule=self._annual_storage,
                doc=f"Annual Product Storage (MMBtu)",
            )

    def _operational_storage_capacity(self, block, modeled_year):
        if modeled_year >= self.build_year:
            operational_storage_capacity = (
                self.planned_storage_capacity[modeled_year]
                + block.selected_storage_capacity
                - pyo.quicksum(
                    block.retired_storage_capacity[year]
                    for year in block.model().MODELED_YEARS
                    if year <= modeled_year
                )
            )
        else:
            operational_storage_capacity = 0.0

        return operational_storage_capacity

    def _storage_capacity_duration_constraint(self, block, modeled_year):
        """
        Constrains operational storage capacity based on duration:
        If user-defined duration is fixed, power capacity * duration is equal to energy capacity
        If user-defined duration is the minimum allowed, power capacity * duration is less than or equal to energy capacity
        If user-defined duration is the maximum allowed, power capacity * duration is greater than or equal to energy capacity

        """
        duration_requirement = block.operational_capacity[modeled_year] * self.duration
        operational_storage_capacity = block.operational_storage_capacity[modeled_year]
        if self.duration_constraint == StorageDurationConstraint.FIXED:
            return duration_requirement == operational_storage_capacity
        elif self.duration_constraint == StorageDurationConstraint.MINIMUM:
            return duration_requirement <= operational_storage_capacity
        elif self.duration_constraint == StorageDurationConstraint.MAXIMUM:
            return duration_requirement >= operational_storage_capacity
        else:
            raise NotImplementedError(
                f"Duration specification ({self.duration_constraint}) for {self.name} has not been implemented yet."
            )

    def _retired_storage_capacity_max_constraint(self, block, modeled_year):
        """Upper bound on the amount of retired capacity in each year. Retired capacity in a given year cannot
        exceed the operational capacity in the previous year, and capacity cannot be retired before the build year
        of the storage resource."""

        # If the modeled year is earlier than the build year, no capacity can be retired in that year
        if self.build_year > modeled_year:
            return block.retired_storage_capacity[modeled_year] == 0

        # If the resource can't be retired, but it has a physical lifetime, don't allow retirement until the
        #  end of its physical lifetime
        elif (
            not self.can_retire
            and self.physical_lifetime is not None
            and modeled_year < self.build_year.replace(year=self.build_year.year + self.physical_lifetime)
        ):
            constraint = block.retired_storage_capacity[modeled_year] == 0

        # If the resource can't be retired, and it has no specified physical lifetime, don't allow it to retire ever
        elif not self.can_retire and self.physical_lifetime is None:
            constraint = block.retired_storage_capacity[modeled_year] == 0

        # If the resource exists before the first modeled year, only the planned capacity can be retired
        elif (modeled_year == block.model().MODELED_YEARS.first()) or (
            modeled_year == self.build_year
        ):
            constraint = block.retired_storage_capacity[modeled_year] <= self.planned_storage_capacity[modeled_year]

        # Otherwise, the resource cannot retire more capacity than was online in the previous modeled year
        else:
            constraint = (
                block.retired_storage_capacity[modeled_year]
                <= block.operational_storage_capacity[block.model().MODELED_YEARS.prev(modeled_year)]
            )

        return constraint

    def _storage_physical_lifetime_constraint(self, block, modeled_year):
        """The fuel storage energy capacity must be retired after the end of its physical lifetime"""
        if (
            self.physical_lifetime is not None
            and self.build_year.replace(year=self.build_year.year + self.physical_lifetime) <= modeled_year
        ):
            constraint = self.formulation_block.operational_storage_capacity[modeled_year] == 0
        else:
            constraint = pyo.Constraint.Skip

        return constraint

    def _prod_sim_selected_storage_capacity_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """In production simulation mode, retirement decisions are constrained to the retirement decisions of the
        original capacity expansion problem."""
        return block.selected_storage_capacity == block.chosen_selected_storage_capacity

    def _prod_sim_retired_storage_capacity_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """In production simulation mode, retirement decisions are constrained to the retirement decisions of the
        original capacity expansion problem."""
        return block.retired_storage_capacity[modeled_year] == block.chosen_retired_storage_capacity[modeled_year]

    def _prod_sim_operational_storage_capacity_constraint(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """In production simulation mode, operational capacities are constrained to those of the original
        capacity expansion problem."""
        return (
            block.operational_storage_capacity[modeled_year] == block.chosen_operational_storage_capacity[modeled_year]
        )

    def _annual_storage_capital_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Capital costs of storage for the Asset in each year. Capital costs are only incurred for selected new-build
        capacity, not for planned capacity. Capital Costs are not incurred overnight in the build year of the
        Asset, but are incurred annually over the course of its financial lifetime. This term represents the
        costs incurred in a single year, and it is not discounted (i.e. it is not multiplied by the discount
        factor for the relevant model year)."""
        if (
            self.build_year
            <= modeled_year
            < self.build_year.replace(year=self.build_year.year + self.physical_lifetime)
        ):
            # TODO (skramer): should planned capacity incur a capital cost or no?
            storage_investment_cost = self.annualized_storage_capital_cost * block.selected_storage_capacity
        else:
            storage_investment_cost = 0.0

        return storage_investment_cost

    def _annual_storage_fixed_om_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        """Fixed O&M costs of capacity for the Asset in each year. Fixed O&M costs are incurred for both selected
        new-build capacity and for planned capacity. This term represents the costs incurred in a single year, and
        it is not discounted (i.e. it is not multiplied by the discount factor for the relevant model year)."""
        storage_fixed_om_cost = (
            self.annualized_storage_fixed_om_cost.data.at[modeled_year]
            * self.formulation_block.operational_storage_capacity[modeled_year]
        )

        return storage_fixed_om_cost

    def _annual_total_investment_cost(self, block: pyo.Block, modeled_year: pd.Timestamp):
        total_investment_cost = super()._annual_total_investment_cost(block=block, modeled_year=modeled_year)
        total_investment_cost += (
            block.annual_storage_capital_cost[modeled_year] + block.annual_storage_fixed_om_cost[modeled_year]
        )

        return total_investment_cost

    def _scaled_min_input_profile(self, block, modeled_year, dispatch_window, timestamp):
        return block.operational_capacity[modeled_year] * self.min_input_profile.data.at[timestamp]

    def _scaled_max_input_profile(self, block, modeled_year, dispatch_window, timestamp):
        return block.operational_capacity[modeled_year] * self.max_input_profile.data.at[timestamp]

    def _storage(self, block, modeled_year, dispatch_window, timestamp):
        """Storage of primary product by charging processes"""
        return block.charge[modeled_year, dispatch_window, timestamp] * self.charging_efficiency

    def _charging_consumption(self, block, input, modeled_year, dispatch_window, timestamp):
        """Consumption due to storage charging"""
        if input == self.primary_product:
            return block.charge[modeled_year, dispatch_window, timestamp]
        else:
            return sum(
                block.storage[modeled_year, dispatch_window, timestamp] / process.conversion_rate
                for process in self.primary_charging_processes
                if process.consumed_product.name == input
            )

    def _discharging_consumption(self, block, input, modeled_year, dispatch_window, timestamp):
        if input == self.primary_product:
            return 0
        else:
            return sum(
                block.operation[modeled_year, dispatch_window, timestamp] / process.conversion_rate
                for process in self.primary_discharging_processes
                if process.consumed_product.name == input
            )

    def _consumption(self, block, input, modeled_year, dispatch_window, timestamp):
        """Consumption of inputs are calculated based on charging or discharging processes of primary product. Plant
        input capacity and primary product consumption is defined by the charge variable. All other products are
        consumed based on primary product storage or plant operation (which is equal to primary product production)."""
        return (
            block.charging_consumption[input, modeled_year, dispatch_window, timestamp]
            + block.discharging_consumption[input, modeled_year, dispatch_window, timestamp]
        )

    def _production(self, block, output, modeled_year, dispatch_window, timestamp):
        """This formulation assumes that primary product production is equal to plant discharge. All other outputs'
        productions are assumed to be the sum of their contributing processes"""
        if output == self.primary_product:
            return block.operation[modeled_year, dispatch_window, timestamp]
        else:
            return sum(
                block.consumption[process.consumed_product.name, modeled_year, dispatch_window, timestamp]
                * process.conversion_rate
                for process in self.storage_processes.values()
                if process.produced_product.name == output
            )

    def _consumed_product_capture(self, block, input, modeled_year, dispatch_window, timestamp):
        """Consumed product capture of inputs by some capture to serve storage charging or discharging. This capture
        process is assumed to pull in product that exists **externally** to the system. In general, this will be 0,
        unless it is believed that the product is some form of captured atmospheric pollutant."""
        return sum(
            block.charge[modeled_year, dispatch_window, timestamp]
            / process.conversion_rate
            * process.input_capture_rate
            for process in self.primary_charging_processes
            if process.consumed_product.name == input
        ) + sum(
            block.operation[modeled_year, dispatch_window, timestamp]
            / process.conversion_rate
            * process.input_capture_rate
            for process in self.primary_discharging_processes
            if process.consumed_product.name == input
        )

    def _produced_product_to_zone(self, block, output, modeled_year, dispatch_window, timestamp):
        """This represents capture of output product, i.e. injection of output product into the plant's linked zone.
        This typically will equal the value of the production expression, unless it is believed that the output
        product is instead a released atmospheric pollution."""
        if output == self.primary_product:
            return block.operation[modeled_year, dispatch_window, timestamp] * self.primary_process_output_capture_rate
        else:
            return sum(
                block.charging_consumption[process.consumed_product.name, modeled_year, dispatch_window, timestamp]
                * process.conversion_rate
                * process.output_capture_rate
                for process in self.charging_processes.values()
                if process.produced_product.name == output
            ) + sum(
                block.discharging_consumption[process.consumed_product.name, modeled_year, dispatch_window, timestamp]
                * process.conversion_rate
                * process.output_capture_rate
                for process in self.discharging_processes.values()
                if process.produced_product.name == output
            )

    def _min_input_constraint(self, block, modeled_year, dispatch_window, timestamp):
        """Constrain minimum plant charging operation."""
        return (
            block.charge[modeled_year, dispatch_window, timestamp]
            >= block.scaled_min_input_profile[modeled_year, dispatch_window, timestamp]
        )

    def _max_input_constraint(self, block, modeled_year, dispatch_window, timestamp):
        """Constrain maximum plant charging operation."""
        return (
            block.charge[modeled_year, dispatch_window, timestamp]
            <= block.scaled_max_input_profile[modeled_year, dispatch_window, timestamp]
        )

    def _mileage_constraint(self, block, modeled_year, dispatch_window, timestamp):
        """The fuel storage cannot both discharge and consume primary product for the entire duration of a single
        timepoint. Note: this constraint is somewhat imperfect unless max input and output profiles are equal in a
        given timepoint."""
        return block.operation[modeled_year, dispatch_window, timestamp] + block.charge[
            modeled_year, dispatch_window, timestamp
        ] <= block.operational_capacity[modeled_year] * max(
            self.max_input_profile.data.at[timestamp], self.max_output_profile.data.at[timestamp]
        )

    def _simultaneous_charging_constraint(self, block, modeled_year, dispatch_window, timestamp):
        """Limit simultaneous charging & discharging for fuel storage plants to what could be possible in a single
        hour.

        In other words, fuel storage plants can simultaneously charge & discharge as long as the "split" the hour (
        e.g., charging for half the hour and discharging for half the hour)."""
        return (
            block.operation[modeled_year, dispatch_window, timestamp]
            + block.charge[modeled_year, dispatch_window, timestamp]
        ) <= 0.5 * (
            block.scaled_max_output_profile[modeled_year, dispatch_window, timestamp]
            + block.scaled_max_input_profile[modeled_year, dispatch_window, timestamp]
        )

    def _soc_inter_intra_joint(self, block, modeled_year, chrono_period, timestamp):
        """Sums inter- and intra-period SOC. Used to track SOC in fuel storage plants in timepoints."""
        dispatch_window = block.model().chrono_periods_map[chrono_period]
        return (
            block.soc_intra_period[modeled_year, dispatch_window, timestamp]
            + block.soc_inter_period[modeled_year, chrono_period]
        )

    def _soc_inter_intra_max_constraint(self, block, modeled_year, chrono_period, timestamp):
        """SOC cannot exceed storage's total MMBtu capacity divided by discharging efficiency, i.e. the full tank
        size"""
        return (
            block.soc_inter_intra_joint[modeled_year, chrono_period, timestamp]
            <= block.operational_storage_capacity[modeled_year] / self.discharging_efficiency
        )

    def _soc_inter_intra_min_constraint(self, block, modeled_year, chrono_period, timestamp):
        """SOC must be non-negative or constrained by min_state_of_charge"""
        return (
            block.soc_inter_intra_joint[modeled_year, chrono_period, timestamp]
            >= block.operational_storage_capacity[modeled_year] * self.min_state_of_charge
        )

    def apply_parasitic_loss(self, state_of_charge, period_hrs):
        return state_of_charge * (1 - self.parasitic_loss) ** period_hrs

    def _soc_intra_tracking_constraint(self, block, modeled_year, dispatch_window, timestamp):
        """
        Tracks intra-period SOC in fuel storage plants. SOC represents at the status at the beginning of the current
        timepoint. Therefore, SOC[next tp] = SOC[curent tp] - operation[current tp] + charge[current tp] - parasitic
        losses.

        If we are using the default representative/chronological period representation,
        this constraint does not apply for the last timepoint of an intra period:
             1. Any energy left in the last tp is transferred to `Soc_Inter_Period` via `SOC_Inter_Tracking_Constraint`
             2. `Soc_Intra_Period` in the first timepoint of each representative period is anchored to 0 by
                `SOC_Intra_Anchoring_Constraint`

        If either of the following conditions is met, this constraint **does** create a SoC constraint to loop
        the last tp of a rep period to the first tp:
             1. A resource is set to :py:attr:`new_modeling_toolkit.system.fuel_storage.FuelStorage.allow_inter_period_sharing`==False
             2. :py:attr:`new_modeling_toolkit.resolve.model_formulation.ResolveCase.rep_period_method`=="manual"

        """
        if (modeled_year, dispatch_window, timestamp) == (
            modeled_year,
            dispatch_window,
            block.model().last_timepoint_in_dispatch_window[dispatch_window],
        ):
            return pyo.Constraint.Skip

        else:

            charged_mmbtu = (
                block.storage[modeled_year, dispatch_window, timestamp]
                * block.model().timestamp_durations_hours[dispatch_window, timestamp]
            )
            discharged_mmbtu = (
                block.operation[modeled_year, dispatch_window, timestamp]
                * block.model().timestamp_durations_hours[dispatch_window, timestamp]
                / self.discharging_efficiency
            )
            return (
                block.soc_intra_period[
                    modeled_year,
                    block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS.next((dispatch_window, timestamp)),
                ]
                == self.apply_parasitic_loss(
                    state_of_charge=block.soc_intra_period[modeled_year, dispatch_window, timestamp],
                    period_hrs=block.model().timestamp_durations_hours[dispatch_window, timestamp],
                )
                + charged_mmbtu
                - discharged_mmbtu
            )

    def _soc_intra_anchoring_constraint(self, block, modeled_year, dispatch_window):
        """Intra-period SOC is 0 in the first timestamp of every dispatch window when inter-period-sharing is allowed"""
        # If the model is set to loop back around dispatch windows, or if inter-period sharing is enabled in the
        # model but not for this specific resource, loop the SOC tracking around the boundary.
        model: ModelTemplate = block.model()
        first_timestamp = model.first_timepoint_in_dispatch_window[dispatch_window]
        last_timestamp = model.last_timepoint_in_dispatch_window[dispatch_window]
        if model.dispatch_window_edge_effects == DispatchWindowEdgeEffects.LOOPBACK or (
            model.dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
            and not self.allow_inter_period_sharing
        ):
            charged_mmbtu = (
                block.storage[modeled_year, dispatch_window, last_timestamp]
                * model.timestamp_durations_hours[dispatch_window, last_timestamp]
            )
            discharged_mmbtu = (
                block.operation[modeled_year, dispatch_window, last_timestamp]
                * model.timestamp_durations_hours[dispatch_window, last_timestamp]
                / self.discharging_efficiency
            )
            constraint = (
                block.soc_intra_period[modeled_year, dispatch_window, first_timestamp]
                == self.apply_parasitic_loss(
                    state_of_charge=block.soc_intra_period[modeled_year, dispatch_window, last_timestamp],
                    period_hrs=model.timestamp_durations_hours[dispatch_window, last_timestamp],
                )
                + charged_mmbtu
                - discharged_mmbtu
            )
        # If the model is set to allow inter-period sharing and the fuel storage plant is set to allow inter-period
        # sharing, force the initial intra-period SOC to be 0
        elif model.dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING:
            constraint = block.soc_intra_period[modeled_year, dispatch_window, first_timestamp] == 0
        # If the model is set to fix SOC at a specific condition, then force the initial SOC to that condition
        elif model.dispatch_window_edge_effects == DispatchWindowEdgeEffects.FIXED_INITIAL_CONDITION:
            raise NotImplementedError("Fixed initial condition for RECAP is not yet implemented")
            # constraint = (
            #    block.state_of_charge[modeled_year, dispatch_window, first_timestamp]
            #    == self.initial_storage_SOC.at[dispatch_window]
            # )  # TODO (BKW 10/24/2024: Define initial_storage_SOC
        else:
            raise ValueError(f"Unsupported value for DispatchWindowEdgeEffects: {model.dispatch_window_edge_effects}")

        return constraint

    def _soc_inter_tracking_constraint(self, block, modeled_year, chrono_period):
        """
        Inter-period SOC should change depending on final intra-period SOC of previous chronological period.

        NOTE: The definition of "get_next_chrono_period" provides that the inter-period SOC of the final
        chronological period is linked to the inter-period SOC of the first chronological period; hence,
        this constraint also enforces the "annual looping" constraint
        """
        model: ModelTemplate = block.model()
        if not (
            model.dispatch_window_edge_effects == DispatchWindowEdgeEffects.INTER_PERIOD_SHARING
            and self.allow_inter_period_sharing
        ):
            constraint = block.soc_inter_period[modeled_year, chrono_period] == 0
        else:

            # Get next chronological period, current representative period, and final hour
            next_chrono_period = model.CHRONO_PERIODS.nextw(chrono_period)
            dispatch_window = model.chrono_periods_map[chrono_period]
            final_hour = model.last_timepoint_in_dispatch_window[dispatch_window]
            first_hour = model.first_timepoint_in_dispatch_window[dispatch_window]

            # Get charging/discharging in final hour of the chronological period
            charged_mmbtu = block.storage[modeled_year, dispatch_window, final_hour]
            discharged_mmbtu = block.operation[modeled_year, dispatch_window, final_hour] / self.discharging_efficiency

            constraint = (
                block.soc_inter_period[modeled_year, next_chrono_period]
                == self.apply_parasitic_loss(
                    block.soc_inter_period[modeled_year, chrono_period],
                    period_hrs=model.dispatch_window_duration_hours[dispatch_window],
                )
                + self.apply_parasitic_loss(
                    block.soc_intra_period[modeled_year, dispatch_window, final_hour], period_hrs=1
                )
                + charged_mmbtu
                - discharged_mmbtu
                - block.soc_intra_period[modeled_year, dispatch_window, first_hour]
            )

        return constraint

    def _variable_cost_dispatched(self, block, modeled_year, dispatch_window, timestamp):
        """Variable cost incurred by the fuel storage discharging to the fuel network."""
        return super()._variable_cost_dispatched(block, modeled_year, dispatch_window, timestamp)

    def _annual_variable_cost_dispatched(self, block, modeled_year):
        """Annual variable cost incurred by the fuel storage discharging to the fuel network."""
        return super()._annual_variable_cost_dispatched(block, modeled_year)


    def _variable_cost_charging(self, block, modeled_year, dispatch_window, timestamp):
        """The variable cost incurred by the fuel storage charging from the fuel network."""
        return self.variable_cost_input.data.at[timestamp] * block.charge[modeled_year, dispatch_window, timestamp]

    def _annual_variable_cost_charging(self, block, modeled_year):
        """The annual variable cost incurred by the fuel storage charging from the fuel network."""
        model: ModelTemplate = block.model()
        return model.sum_timepoint_component_slice_to_annual(
            block.variable_cost_charging[modeled_year, :, :]
        )

    def _annual_variable_cost(self, block, modeled_year):
        return block.annual_variable_cost_dispatched[modeled_year] + block.annual_variable_cost_charging[modeled_year]

    def _annual_total_operational_cost(self, block, modeled_year):
        """The total annual operational costs of the Plant, including both variable O&M and consumed product costs.
        This term is not discounted (i.e. it is not multiplied by the discount factor for the relevant model year)."""
        return (
            super()._annual_total_operational_cost(block=block, modeled_year=modeled_year)
            + block.annual_variable_cost_charging[modeled_year]
        )

    def _annual_charge(self, block, modeled_year):
        model: ModelTemplate = block.model()
        return model.sum_timepoint_component_slice_to_annual(block.charge[modeled_year, :, :])

    def _annual_storage(self, block, modeled_year):
        model: ModelTemplate = block.model()
        return model.sum_timepoint_component_slice_to_annual(block.storage[modeled_year, :, :])


class FuelStorageGroup(FuelProductionPlantGroup, FuelStorage):
    SAVE_PATH: ClassVar[str] = "plants/fuel_storage_plants/groups"
    _NAME_PREFIX: ClassVar[str] = "fuel_storage_groups"
    _GROUPING_CLASS = FuelStorage

    annualized_storage_capital_cost: ts.NumericTimeseries = Field(
        default_factory=ts.NumericTimeseries.zero, up_method="ffill", down_method="mean", default_freq="YS"
    )
    annualized_storage_fixed_om_cost: ts.NumericTimeseries = Field(
        default_factory=ts.NumericTimeseries.zero, up_method="ffill", down_method="mean", default_freq="YS"
    )

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_investment_rules(model=model, construct_costs=construct_costs)
        pyomo_components.update(
            operational_storage_capacity=pyo.Var(
                model.MODELED_YEARS,
                doc="Operational Storage Capacity (MWh)",
            ),
            group_operational_storage_capacity_constraint=pyo.Constraint(
                model.MODELED_YEARS,
                rule=self._operational_storage_capacity,
            ),
            cumulative_selected_storage_capacity=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._cumulative_selected_storage_capacity,
                doc="Cumulative Selected Storage Capacity (MMBtu)",
            ),
            selected_storage_capacity=pyo.Expression(
                model.MODELED_YEARS, rule=self._selected_storage_capacity, doc="Selected Storage Capacity (MMBtu)"
            ),
            retired_storage_capacity=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._retired_storage_capacity,
                doc="Retired Storage Capacity (MMBtu)",
            ),
            cumulative_retired_storage_capacity=pyo.Expression(
                model.MODELED_YEARS,
                rule=self._cumulative_retired_storage_capacity,
                doc="Cumulative Retired Storage Capacity (MMBtu)",
            ),
        )
        pyomo_components.update(
            annual_total_investment_cost=pyo.Expression(
                model.MODELED_YEARS,
                rule=0,
                doc="Annual Total Investment Cost ($)",
            )
        )
        return pyomo_components

    def _operational_storage_capacity(self, block, modeled_year: pd.Timestamp):
        return (
            pyo.quicksum(
                fuel_storage.formulation_block.operational_storage_capacity[modeled_year]
                for fuel_storage in self.build_assets.values()
            )
            == block.operational_storage_capacity[modeled_year]
        )

    def _cumulative_selected_storage_capacity(self, block, modeled_year: pd.Timestamp):
        """Defines the cumulative capacity built in the current and previous modeled year(s) for all linked Assets."""
        return pyo.quicksum(
            +asset.formulation_block.selected_storage_capacity
            for asset in self.build_assets.values()
            if asset.build_year <= modeled_year
        )

    def _selected_storage_capacity(self, block, modeled_year: pd.Timestamp):
        """Defines the capacity built in each modeled year for all linked Assets."""
        model = block.model()
        sorted_years = sorted(model.MODELED_YEARS)
        year_index = sorted_years.index(modeled_year)
        if year_index == 0:
            return self.formulation_block.cumulative_selected_storage_capacity[modeled_year]
        else:
            prev_modeled_year = sorted_years[year_index - 1]
            return (
                self.formulation_block.cumulative_selected_storage_capacity[modeled_year]
                - self.formulation_block.cumulative_selected_storage_capacity[prev_modeled_year]
            )

    def _retired_storage_capacity(self, block, modeled_year: pd.Timestamp):
        """Defines the retired capacity of the group in each year as the sum of retired capacities of all linked Assets."""
        return pyo.quicksum(
            asset.formulation_block.retired_storage_capacity[modeled_year] for asset in self.build_assets.values()
        )

    def _cumulative_retired_storage_capacity(self, block, modeled_year: pd.Timestamp):
        """Defines the cumulative retired capacity in the current and previous modeled years(s) for all linked Assets."""
        model = block.model()
        sorted_years = sorted(model.MODELED_YEARS)
        year_index = sorted_years.index(modeled_year)
        if year_index == 0:
            return self.formulation_block.retired_storage_capacity[modeled_year]
        else:
            prev_modeled_year = sorted_years[year_index - 1]
            return (
                self.formulation_block.retired_storage_capacity[modeled_year]
                + self.formulation_block.cumulative_retired_storage_capacity[prev_modeled_year]
            )
