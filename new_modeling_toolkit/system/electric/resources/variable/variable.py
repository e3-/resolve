import copy
import pathlib
from typing import Annotated
from typing import ClassVar

import pandas as pd
import pyomo.environ as pyo
import scipy.optimize
from loguru import logger
from pydantic import Field

import new_modeling_toolkit.core.temporal.timeseries as ts
from new_modeling_toolkit.core.component import LastUpdatedOrderedDict
from new_modeling_toolkit.core.custom_model import FieldCategory
from new_modeling_toolkit.core.custom_model import Metadata
from new_modeling_toolkit.core.temporal.settings import TemporalSettings
from new_modeling_toolkit.core.utils.core_utils import timer
from new_modeling_toolkit.system.electric.resources.generic import GenericResource
from new_modeling_toolkit.system.electric.resources.generic import GenericResourceGroup


class VariableResource(GenericResource):
    SAVE_PATH: ClassVar[str] = "resources/variable"

    ###################
    # Cost Attributes #
    ###################
    curtailment_cost: Annotated[ts.NumericTimeseries, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        default_factory=ts.NumericTimeseries.zero,
        description="$/MWh. float. Cost of curtailment - the exogeneously assumed cost"
        "at which different contract zones would be willing to curtail their"
        "variable renewable generation",
        default_freq="H",
        up_method="ffill",
        down_method="mean",
    )

    ##########################
    # Operational Attributes #
    ##########################
    curtailable: Annotated[bool, Metadata(category=FieldCategory.OPERATIONS)] = Field(
        True,
        description="TRUE/FALSE. boolean.  Whether resource's power output can be curtailed relative to "
        ":py:attr:`new_modeling_toolkit.common.resource.Resource.potential_provide_power_profile`.",
    )

    ###########
    # Methods #
    ###########
    @classmethod
    def scale_resource_profile(cls, profile: ts.Timeseries, scalar: float) -> ts.Timeseries:
        """
        Update input timeseries given scalar
        """
        profile.data = (profile.data * scalar).clip(upper=1.0)
        return profile

    # todo: move this to generic?
    def get_sampled_profile_cf(self, profile: ts.Timeseries, temporal_settings: TemporalSettings) -> float:
        """
        Return capacity factor of given profile based on dispatch windows weights
        """
        return pd.concat(
            [
                temporal_settings.subset_timeseries_by_dispatch_windows(profile.data, modeled_year)
                for modeled_year in temporal_settings.modeled_year_list
            ]
        ).squeeze().sum() / (8760 * len(temporal_settings.modeled_year_list))

    @timer
    def update_resource_profiles(self, temporal_settings: TemporalSettings, rescaled_profile_dir: pathlib.Path):
        """Really hacky adjustment to make sure sampled CF matches original (un-sampled) CF."""
        logger.debug(f"Re-scaling {self.name} resource profile")

        # If re-scaled profile already exists
        if (rescaled_profile_dir / f"{self.name}.csv").exists():
            self.power_output_max.data = pd.read_csv(
                rescaled_profile_dir / f"{self.name}.csv", parse_dates=True, infer_datetime_format=True, index_col=0
            ).squeeze(axis=1)
            self.power_output_max._data_dict = None

            logger.info(
                f"Reading {self.__class__} re-scaled profile from {(rescaled_profile_dir / f'{self.name}.csv')}"
            )
        else:

            # Get sampled CF
            original_sampled_cf = self.get_sampled_profile_cf(self.power_output_max, temporal_settings)
            # Calculate target CF
            target_cf = self.power_output_max.data.mean()

            def test_profile_scaling(scalar, profile: ts.Timeseries, target_cf: float):
                test_profile = copy.deepcopy(profile)

                test_profile = self.scale_resource_profile(profile=test_profile, scalar=scalar)

                sampled_cf = self.get_sampled_profile_cf(test_profile, temporal_settings)

                return sampled_cf - target_cf

            # Iterate using Newton method
            scalar = scipy.optimize.newton(
                test_profile_scaling,
                0,
                args=(self.power_output_max, target_cf),
                tol=0.004,
                maxiter=10,
                disp=False,
            )

            # Get final profile & CF
            self.power_output_max = self.scale_resource_profile(profile=self.power_output_max, scalar=scalar)
            final_cf = self.get_sampled_profile_cf(self.power_output_max, temporal_settings)

            # Save CSV to speed up subsequent runs
            sampled_scaled_profile = self.power_output_max.data.loc[
                self.power_output_max.data.index.isin(
                    [timestamp for _, timestamp in temporal_settings.dispatch_windows_and_timestamps]
                )
            ]
            sampled_scaled_profile.to_csv(rescaled_profile_dir / f"{self.name}.csv", index=True)

            logger.debug(
                f"Adjusted {self.name} sampled profile capacity factor from {original_sampled_cf:.2%} to {final_cf:.2%} (target of {target_cf:.2%})"
            )

    def _construct_investment_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        return super()._construct_investment_rules(model=model, construct_costs=construct_costs)

    def _construct_operational_rules(
        self, model: "ModelTemplate", construct_costs: bool
    ) -> LastUpdatedOrderedDict[str, pyo.Component]:
        pyomo_components = super()._construct_operational_rules(model=model, construct_costs=construct_costs)

        if self.curtailable:
            pyomo_components.update(
                scheduled_curtailment=pyo.Expression(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._scheduled_curtailment,
                    doc="Curtailed Energy (MWh)",
                ),
                annual_total_scheduled_curtailment=pyo.Expression(
                    model.MODELED_YEARS,
                    rule=self._annual_total_scheduled_curtailment,
                    doc="Annual Curtailed Energy (MWh)",
                ),
            )
            if construct_costs:
                pyomo_components.update(
                    resource_curtailment_cost_in_timepoint=pyo.Expression(
                        model.MODELED_YEARS,
                        model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                        rule=self._resource_curtailment_cost_in_timepoint,
                        doc="Curtailment Cost ($)",
                    ),
                    annual_total_curtailment_cost=pyo.Expression(
                        model.MODELED_YEARS, rule=self._annual_total_curtailment_cost, doc="Annual Curtailment Cost ($)"
                    ),
                    # Note: annual total operational cost only needs to be updated if the resource is curtailable,
                    #  so this can go within both if-statements
                    annual_total_operational_cost=pyo.Expression(
                        model.MODELED_YEARS,
                        rule=self._annual_total_operational_cost,
                        doc="Annual Total Operational Cost ($)",
                    ),
                )

        if not self.curtailable and self.energy_budget_daily is None:
            # TODO (2021-10-07): What happens in this constraint if `provide_power_potential_profile` is None but `curtailable` is False
            pyomo_components.update(
                provide_power_curtailment_constraint=pyo.Constraint(
                    model.MODELED_YEARS,
                    model.DISPATCH_WINDOWS_AND_TIMESTAMPS,
                    rule=self._provide_power_curtailment_constraint,
                )
            )

        return pyomo_components

    def _scheduled_curtailment(
        self,
        block,
        modeled_year: pd.Timestamp,
        dispatch_window,
        timestamp: pd.Timestamp,
    ):
        """
        The resource's scheduled curtailment is calculated as the difference between the power_output_max profile and
        the actual power_output
        Args:
            block: The block object associated with the expression
            modeled_year (pd.Timestamp): The timestamp representing the modeled year
            dispatch_window (pd.Timestamp): The timestamp representing the dispatch window
            timestamp (pd.Timestamp): The timestamp for which the constraint is being evaluated
        Returns:
            pyo.Expression
        """
        return (
            self.formulation_block.power_output_max[modeled_year, dispatch_window, timestamp]
            - self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
        )

    def _annual_total_scheduled_curtailment(
        self,
        block,
        modeled_year: pd.Timestamp,
    ):
        """
        Calculate the resource's total annual scheduled curtailment
        Args:
            block: The block object associated with the expression
            modeled_year (pd.Timestamp): The timestamp representing the modeled year
        Returns:
            pyo.Expression
        """
        return self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.scheduled_curtailment[modeled_year, :, :]
        )

    def _resource_curtailment_cost_in_timepoint(
        self,
        block,
        modeled_year: pd.Timestamp,
        dispatch_window,
        timestamp: pd.Timestamp,
    ):
        """
        The resource's curtailment cost is calculated as the scheduled curtailment multiplied by the curtailment cost
        Args:
            block: The block object associated with the expression
            modeled_year (pd.Timestamp): The timestamp representing the modeled year
            dispatch_window (pd.Timestamp): The timestamp representing the dispatch window
            timestamp (pd.Timestamp): The timestamp for which the constraint is being evaluated
        Returns:
            pyo.Expression
        """
        return (
            self.formulation_block.scheduled_curtailment[modeled_year, dispatch_window, timestamp]
            * self.curtailment_cost.data.at[modeled_year]
        )

    def _annual_total_curtailment_cost(
        self,
        block,
        modeled_year: pd.Timestamp,
    ):
        """
        Calculate the resource's total annual curtailment cost
        Args:
            block: The block object associated with the expression
            modeled_year (pd.Timestamp): The timestamp representing the modeled year
        Returns:
            pyo.Expression
        """
        return self.formulation_block.model().sum_timepoint_component_slice_to_annual(
            self.formulation_block.resource_curtailment_cost_in_timepoint[modeled_year, :, :]
        )

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
        if self.curtailable:
            total_operational_cost = (
                total_operational_cost + self.formulation_block.annual_total_curtailment_cost[modeled_year]
            )

        return total_operational_cost

    def _provide_power_curtailment_constraint(
        self,
        block,
        modeled_year: pd.Timestamp,
        dispatch_window,
        timestamp: pd.Timestamp,
    ):
        """For non-curtailable resources, for ``Provide_Power_MW`` to be equal to ``provide_power_potential_profile``.

        Notes:
            - This is only "scheduled" hourly curtailment
            - The current formulation does not include any "subhourly" curtailment due to subhourly reserves
            - The model may have numerical issues if the ``provide_power_potential_profile`` is very small
        """
        return (
            self.formulation_block.power_output[modeled_year, dispatch_window, timestamp]
            == self.formulation_block.power_output_max[modeled_year, dispatch_window, timestamp]
        )


class VariableResourceGroup(GenericResourceGroup, VariableResource):
    SAVE_PATH: ClassVar[str] = "resources/variable/groups"
    _NAME_PREFIX: ClassVar[str] = "variable_resource_group"
    _GROUPING_CLASS = VariableResource
