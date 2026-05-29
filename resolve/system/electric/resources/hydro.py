from typing import ClassVar

import numpy as np
import pandas as pd
from kit.system.electric.resources.hydro import BaseHydroResource
from kit.system.electric.resources.hydro import BaseHydroResourceGroup
from loguru import logger
from pydantic import model_validator
from pyomo import environ as pyo

from resolve.core.component import LastUpdatedOrderedDict
from resolve.core.model import ModelTemplate
from resolve.system.electric.resources.variable.variable import VariableResource
from resolve.system.electric.resources.variable.variable import VariableResourceGroup

# Make equality constraints inequality constraints with slack_up and slack_down variables to avoid infeasibilities
BUDGET_SLACK_PENALTY = 100_000  # $/MWh


class HydroResource(BaseHydroResource, VariableResource):
    """Hydro electric resource."""

    SAVE_PATH: ClassVar[str] = "resources/hydro"

    ###########
    # Methods #
    ###########

    def revalidate(self):
        """Validate that if a resource is not curtailable and:
        - Has a daily energy budget: its power output max is sufficient to meet the minimum energy output defined by the daily budget.
        - Has an annual energy budget: its power output max is sufficient to meet the minimum energy output defined by the annual budget.
        """
        super().revalidate()

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
                    f"the budget. Check your Pmax and annual budget inputs."
                )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @model_validator(mode="after")
    def validate_budget_exists(self) -> "Hydro":
        """Validate that at least one energy budget is defined for the hydro resource, and log a warning if not."""
        if (
            self.energy_budget_daily is None
            and self.energy_budget_monthly is None
            and self.energy_budget_annual is None
        ):
            logger.warning(
                f"Hydro resource {self.name} does not have an energy budget defined. It will operate with the same "
                f"formulation as a generic VariableResource.If this is intentional, you can ignore this warning. "
                f"Otherwise, consider adding at least one energy budget to the resource."
            )
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
                        model.MODELED_YEARS, model.WEATHER_YEARS, within=pyo.NonNegativeReals, doc="Annual Slack Up"
                    ),
                    annual_budget_slack_down=pyo.Var(
                        model.MODELED_YEARS, model.WEATHER_YEARS, within=pyo.NonNegativeReals, doc="Annual Slack Down"
                    ),
                    annual_budget_slack_total=pyo.Expression(
                        model.MODELED_YEARS,
                        rule=self._annual_budget_slack_total,
                        doc="Total Annual Budget Slack (MWh)",
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
        """Calculate the daily budget slack cost for a given modeled year as the sum of the daily slack up and down variables multiplied by the budget slack penalty."""
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
            daily_energy_generation = pyo.quicksum(
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

    def _annual_budget_slack_total(self, block, modeled_year):
        """Calculate the total annual budget slack for a given modeled year as the sum of the annual slack up and down variables."""
        return pyo.quicksum(
            block.annual_budget_slack_up[modeled_year, weather_year]
            + block.annual_budget_slack_down[modeled_year, weather_year]
            for weather_year in block.model().WEATHER_YEARS
        )

    def _annual_budget_slack_cost(self, block, modeled_year):
        """Calculate the annual budget slack cost for a given modeled year as the sum of the annual slack up and down variables multiplied by the budget slack penalty."""
        return BUDGET_SLACK_PENALTY * block.annual_budget_slack_total[modeled_year]

    def _annual_energy_budget_constraint(self, block, modeled_year: pd.Timestamp, weather_year: pd.Timestamp):
        """The annual power output of the non-curtailable resource must be equal to its specified annual budget."""
        if self.energy_budget_annual is None or np.isinf(self.energy_budget_annual.data.at[weather_year]):
            constraint = pyo.Constraint.Skip
        elif self.curtailable:
            return super()._annual_energy_budget_constraint(block, modeled_year, weather_year)
        else:
            constraint = (
                block.power_output_annual[modeled_year]
                - block.annual_budget_slack_up[modeled_year, weather_year]
                + block.annual_budget_slack_down[modeled_year, weather_year]
                <= block.annual_energy_budget_MWh[modeled_year, weather_year]
            )

        return constraint

    def _monthly_energy_budget_constraint(self, block, modeled_year, month):
        """The monthly power output of the non-curtailable resource must be equal to its specified monthly budget."""
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
        """
        total_operational_cost = super()._annual_total_operational_cost(block, modeled_year)
        if not self.curtailable:
            total_operational_cost += block.annual_total_slack_operational_cost[modeled_year]

        return total_operational_cost

    def _annual_total_slack_operational_cost(self, block, modeled_year: pd.Timestamp):
        """The total annual operational costs of the hydro resource (slack penalty costs)."""
        annual_total_slack_operational_cost = 0
        if not self.curtailable:
            if self.energy_budget_daily is not None:
                annual_total_slack_operational_cost += block.daily_budget_slack_cost[modeled_year]
            if self.energy_budget_annual is not None:
                annual_total_slack_operational_cost += block.annual_budget_slack_cost[modeled_year]
            if self.energy_budget_monthly is not None:
                raise NotImplementedError("Monthly energy budgets are not yet implemented in Resolve.")

        return annual_total_slack_operational_cost


class HydroResourceGroup(BaseHydroResourceGroup, VariableResourceGroup, HydroResource):
    SAVE_PATH: ClassVar[str] = "resources/hydro/groups"
    _NAME_PREFIX: ClassVar[str] = "hydro_resource_group"
    _GROUPING_CLASS = HydroResource

    def revalidate(self):
        """Validate that if the resource group is not curtailable and:

        - Has a daily energy budget: its power output max is sufficient to meet the minimum energy output defined by the daily budget.
        - Has an annual energy budget: its power output max is sufficient to meet the minimum energy output defined by the annual budget.
        """
        super().revalidate()

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
                    f"the budget. Check your Pmax and annual budget inputs."
                )
