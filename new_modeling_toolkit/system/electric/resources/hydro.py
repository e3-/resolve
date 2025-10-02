from typing import ClassVar

import numpy as np
import pandas as pd
from loguru import logger
from pydantic import model_validator
from pyomo import environ as pyo

from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.system.electric.resources.variable.variable import VariableResource
from new_modeling_toolkit.system.electric.resources.variable.variable import VariableResourceGroup

# Make equality constraints inequality constraints with slack_up and slack_down variables to avoid infeasibilities
BUDGET_SLACK_PENALTY = 50_000_000  # $/MWh

class HydroResource(VariableResource):
    """Resource with storage capacity.

    Adds state-of-charge tracking.

    It feels like BatteryResource could be composed of a GenericResource + Asset (that represents the storage costs),
    but need to think about this more before implementing.
    """

    SAVE_PATH: ClassVar[str] = "resources/hydro"

    ###########
    # Methods #
    ###########

    def revalidate(self):
        super().revalidate()

        # Check that power output max is compatible with budgets if resource is not curtailable
        if not self.curtailable and self.energy_budget_daily is not None:
            if any(
                self.power_output_max.data.groupby(self.power_output_max.data.index.date)
                .mean()
                .lt(self.energy_budget_daily.data)
            ):
                raise ValueError(
                    f"Hydro Resource {self.name} is not curtailable and it has a daily energy budget, but "
                    f"its power output max is not high enough to meet the minimum energy output defined by "
                    f"the budget. Check your Pmax and daily budget inputs."
                )
        if not self.curtailable and self.energy_budget_annual is not None:
            if any(
                self.power_output_max.data.groupby(self.power_output_max.data.index.year)
                .mean()
                .lt(self.energy_budget_annual.data)
            ):
                raise ValueError(
                    f"Hydro Resource {self.name} is not curtailable and it has an annual energy budget, but "
                    f"its power output max is not high enough to meet the minimum energy output defined by "
                    f"the budget. Check your Pmax and daily budget inputs."
                )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @model_validator(mode="after")
    def validate_budget_exists(self) -> "Hydro":
        if (
            self.energy_budget_daily is None
            and self.energy_budget_monthly is None
            and self.energy_budget_annual is None
        ):
            logger.warning(f"Hydro resource {self.name} does not have an energy budget defined.")
        return self

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

        # Redefine budget constraints to equality constraints with slacks if hydro is NOT curtailable
        if not self.curtailable:
            if self.energy_budget_daily is not None:
                pyomo_components.update(
                    daily_budget_slack_up=pyo.Var(
                        model.MODELED_YEARS, model.DAYS, within=pyo.NonNegativeReals, doc="Daily Slack Up"
                    ),
                    daily_budget_slack_down=pyo.Var(
                        model.MODELED_YEARS, model.DAYS, within=pyo.NonNegativeReals, doc="Daily Slack Down"
                    ),
                    daily_budget_slack_cost=pyo.Expression(model.MODELED_YEARS, rule=self._daily_budget_slack_cost),
                    daily_energy_budget_constraint=pyo.Constraint(
                        model.MODELED_YEARS,
                        model.DAYS,
                        rule=self._daily_energy_budget_constraint,
                    ),
                )
            if self.energy_budget_annual is not None:
                pyomo_components.update(
                    annual_budget_slack_up=pyo.Var(
                        model.MODELED_YEARS, within=pyo.NonNegativeReals, doc="Annual Slack Up"
                    ),
                    annual_budget_slack_down=pyo.Var(
                        model.MODELED_YEARS, within=pyo.NonNegativeReals, doc="Annual Slack Down"
                    ),
                    annual_budget_slack_cost=pyo.Expression(model.MODELED_YEARS, rule=self._annual_budget_slack_cost),
                    annual_energy_budget_constraint=pyo.Constraint(
                        model.MODELED_YEARS,
                        model.WEATHER_YEARS,
                        rule=self._annual_energy_budget_constraint,
                    ),
                )
            if self.energy_budget_monthly is not None:
                raise NotImplementedError("Monthly energy budgets are not yet implemented in Resolve.")

            # Only update operational cost and operational slack cost expressions if hydro is not curtailable
            pyomo_components.update(
                annual_total_slack_operational_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_slack_operational_cost,
                    doc="Annual Total Slack Operational Cost ($)",
                ),
                annual_total_operational_cost=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_operational_cost,
                    doc="Annual Total Operational Cost ($)",
                ),
            )
        return pyomo_components

    # TODO: Need separate columns for spilled hydro and other curtailment? Should spilled hydro be based on budget or pmax?
    # def _construct_output_expressions(self, construct_costs: bool):
    #     if self.curtailable:
    #         self.formulation_block.annual_total_scheduled_curtailment.doc = "Spilled Hydro (MWh)"
    #         self.formulation_block.scheduled_curtailment.doc = "Spilled Hydro (MWh)"

    def _daily_budget_slack_cost(self, block, modeled_year):
        # This summation does not weight by dispatch window, but the penalty is arbitrary anyway, so it doesn't matter
        return BUDGET_SLACK_PENALTY * sum(
            block.daily_budget_slack_up[modeled_year, day] + block.daily_budget_slack_down[modeled_year, day]
            for day in block.model().DAYS
        )

    def _daily_energy_budget_constraint(self, block, modeled_year, day):
        """The daily power output of the non-curtailable resource must be equal to its specified daily budget."""
        if self.energy_budget_daily is None or np.isinf(self.energy_budget_daily.data.at[day]):
            constraint = pyo.Constraint.Skip
        elif self.curtailable:
            return super()._daily_energy_budget_constraint(block, modeled_year, day)
        else:
            daily_energy_generation = sum(
                block.power_output[modeled_year, dispatch_window, timestamp]
                for dispatch_window, timestamp in block.model().DAY_TO_TIMESTAMPS_MAPPING[day]
            )
            constraint = (
                daily_energy_generation
                - self.formulation_block.daily_budget_slack_up[modeled_year, day]
                + self.formulation_block.daily_budget_slack_down[modeled_year, day]
                == block.daily_energy_budget_MWh[modeled_year, day]
            )

        return constraint

    def _annual_budget_slack_cost(self, block, modeled_year):
        return BUDGET_SLACK_PENALTY * (
            block.annual_budget_slack_up[modeled_year] + block.annual_budget_slack_down[modeled_year]
        )

    def _annual_energy_budget_constraint(self, block, modeled_year: pd.Timestamp, weather_year: pd.Timestamp):
        """The annual power output of the non-curtailable resource must be equal to its specified annual budget."""
        if self.energy_budget_annual is None or np.isinf(self.energy_budget_annual.data.at[weather_year]):
            constraint = pyo.Constraint.Skip
        elif self.curtailable:
            return super()._annual_energy_budget_constraint(block, modeled_year, weather_year)
        else:
            constraint = (
                block.model().sum_timepoint_component_slice_to_annual(block.power_output[modeled_year, :, :])
                - block.annual_budget_slack_up[modeled_year]
                + block.annual_budget_slack_down[modeled_year]
                == block.annual_energy_budget_MWh[modeled_year, weather_year]
            )

        return constraint

    def _monthly_energy_budget_constraint(self, block, modeled_year, month):
        """The annual power output of the non-curtailable resource must be equal to its specified annual budget."""
        if self.energy_budget_monthly is None or np.isinf(self.energy_budget_monthly.data.at[month]):
            constraint = pyo.Constraint.Skip
        else:
            # TODO: figure out how to add this up appropriately using chrono to rep mapping for RESOLVE
            raise NotImplementedError("Monthly energy budgets are not yet implemented in Resolve.")
            # constraint = (
            #     sum(
            #         block.power_output[modeled_year, dispatch_window, timestamp]
            #         for dispatch_window, timestamp in block.model().MONTH_TO_TIMESTAMPS_MAPPING[month]
            #     )
            #     <= block.monthly_energy_budget_MWh[modeled_year, month] + _PYOMO_BUDGET_TOLERANCE
            # )

        return constraint

    def _annual_total_operational_cost(
        self,
        block,
        modeled_year: pd.Timestamp,
    ):
        """
        Calculate the annual curtailment cost over a given modeled year.
        Args:
            block: The block object associated with the expression
            modeled_year (pd.Timestamp): The timestamp representing the modeled year
        Returns:
            pyo.Expression
        """
        total_operational_cost = super()._annual_total_operational_cost(block, modeled_year)
        if not self.curtailable:
            total_operational_cost += block.annual_total_slack_operational_cost[modeled_year]

        return total_operational_cost

    def _annual_total_slack_operational_cost(self, block, modeled_year: pd.Timestamp):
        """The total annual operational costs of the hydro resource (slack penalty costs). This term is not
        discounted (i.e. it is not multiplied by the discount factor for the relevant model year)."""
        annual_total_slack_operational_cost = 0
        if not self.curtailable:
            if self.energy_budget_daily is not None:
                annual_total_slack_operational_cost += block.daily_budget_slack_cost[modeled_year]
            if self.energy_budget_annual is not None:
                annual_total_slack_operational_cost += block.annual_budget_slack_cost[modeled_year]
            if self.energy_budget_monthly is not None:
                raise NotImplementedError("Monthly energy budgets are not yet implemented in Resolve.")

        return annual_total_slack_operational_cost


class HydroResourceGroup(VariableResourceGroup, HydroResource):
    SAVE_PATH: ClassVar[str] = "resources/hydro/groups"
    _NAME_PREFIX: ClassVar[str] = "hydro_resource_group"
    _GROUPING_CLASS = HydroResource

    def revalidate(self):
        super().revalidate()

        # Check that power output max is compatible with budgets if resource is not curtailable
        if not self.curtailable and self.energy_budget_daily is not None:
            if any(
                self.power_output_max.data.groupby(self.power_output_max.data.index.date)
                .mean()
                .lt(self.energy_budget_daily.data)
            ):
                raise ValueError(
                    f"Hydro Resource Group {self.name} is not curtailable and it has a daily energy budget, but "
                    f"its power output max is not high enough to meet the minimum energy output defined by "
                    f"the budget. Check your Pmax and daily budget inputs."
                )
        if not self.curtailable and self.energy_budget_annual is not None:
            if any(
                self.power_output_max.data.groupby(self.power_output_max.data.index.year)
                .mean()
                .lt(self.energy_budget_annual.data)
            ):
                raise ValueError(
                    f"Hydro Resource Group {self.name} is not curtailable and it has an annual energy budget, but "
                    f"its power output max is not high enough to meet the minimum energy output defined by "
                    f"the budget. Check your Pmax and daily budget inputs."
                )
