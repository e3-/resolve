import pandas as pd
import pytest

import new_modeling_toolkit.core.temporal.timeseries as ts
from new_modeling_toolkit.system.policy import AnnualEmissionsPolicy
from new_modeling_toolkit.system.policy import AnnualEnergyStandard
from new_modeling_toolkit.system.policy import EnergyReserveMargin
from new_modeling_toolkit.system.policy import HourlyEnergyStandard
from new_modeling_toolkit.system.policy import PlanningReserveMargin
from tests.system.component_test_template import ComponentTestTemplate


# TODO: Update results reporting unit tests for policy
class TestAnnualEnergyStandard(ComponentTestTemplate):
    _COMPONENT_CLASS = AnnualEnergyStandard
    _COMPONENT_NAME = "TestRPS"
    _SYSTEM_COMPONENT_DICT_NAME = "annual_energy_policies"

    def test_results_reporting(self, make_component_with_block_copy):
        policy = make_component_with_block_copy()

        # Assign placeholder values to the dual values of the policy constraint
        for year, value in [
            (pd.Timestamp("2025-01-01"), 10),
            (pd.Timestamp("2030-01-01"), 20),
            (pd.Timestamp("2035-01-01"), 30),
            (pd.Timestamp("2045-01-01"), 40),
        ]:
            policy.formulation_block.policy_constraint[year].set_suffix_value("dual", value)

        policy._construct_output_expressions(construct_costs=True)
        block = policy.formulation_block

        assert policy.model_fields["target"].title == "Annual Target (Units)"
        assert policy.model_fields["target_adjustment"].title == "Annual Target Adjustment (Units)"
        assert block.policy_slack_up.doc == "Policy Slack Up (Units)"
        assert block.policy_slack_down.doc == "Policy Slack Down (Units)"
        assert block.policy_slack_cost.doc == "Policy Slack Cost ($)"
        assert block.policy_lhs.doc == "Achieved (Units)"
        assert block.annual_total_operational_cost.doc == "Annual Total Operational Cost ($)"

        assert block.energy_policy_annual_contribution_by_resource.doc == "Annual Policy Contribution (MWh)"
        assert block.policy_shadow_price.doc == "Unweighted Dual Value ($/Unit)"

    def test_policy_constraint(self, make_component_with_block_copy, first_index, last_index):
        policy = make_component_with_block_copy()
        rps_block = policy.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Test 1
        rps_block.policy_lhs[modeled_year] = 10000
        rps_block.policy_slack_up[modeled_year].fix(0)
        rps_block.policy_slack_down[modeled_year].fix(1000)

        assert rps_block.policy_constraint[modeled_year].body() == 11000
        assert rps_block.policy_constraint[modeled_year].lower() == 11000

        assert rps_block.policy_constraint[modeled_year].expr()

        # Test 2
        modeled_year, dispatch_window, timestamp = last_index
        rps_block.policy_lhs[modeled_year] = 10000
        rps_block.policy_slack_up[modeled_year].fix(0)
        rps_block.policy_slack_down[modeled_year].fix(500)

        assert rps_block.policy_constraint[modeled_year].body() == 10500
        assert rps_block.policy_constraint[modeled_year].lower() == 11000

        assert not rps_block.policy_constraint[modeled_year].expr()

    def test_policy_lhs(self, make_component_with_block_copy, first_index):
        policy = make_component_with_block_copy()
        rps_block = policy.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        policy.resources["SolarResource1"].instance_from.formulation_block.power_output_annual[modeled_year] = 100

        # thermal contributions from clean fuel burn
        policy.resources["ThermalResource1"].instance_from.formulation_block.annual_power_output_by_fuel[
            "CandidateFuel1", modeled_year
        ] = 100  # rps eligible fuel
        policy.resources["ThermalResource1"].instance_from.formulation_block.annual_power_output_by_fuel[
            "CandidateFuel2", modeled_year
        ] = 200  # NOT rps eligible fuel
        policy.resources["ThermalUnitCommitmentResource"].instance_from.formulation_block.annual_power_output_by_fuel[
            "CandidateFuel1", modeled_year
        ] = 500  # rps eligible fuel
        policy.resources["ThermalUnitCommitmentResource"].instance_from.formulation_block.annual_power_output_by_fuel[
            "CandidateFuel2", modeled_year
        ] = 700  # NOT rps eligible fuel

        assert rps_block.policy_lhs[modeled_year].expr() == 100 + 100 + 500

    def test_annual_total_operational_cost_target(self, make_component_with_block_copy, first_index):
        policy = make_component_with_block_copy()
        rps_block = policy.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        rps_block.policy_slack_up[modeled_year].fix(0)
        rps_block.policy_slack_down[modeled_year].fix(1000)

        assert rps_block.annual_total_operational_cost[modeled_year].expr() == 100_000_000 * 1000

    def test_policy_slack_cost(self, make_component_with_block_copy, first_index):
        policy = make_component_with_block_copy()
        rps_block = policy.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        rps_block.policy_slack_up[modeled_year].fix(10)
        rps_block.policy_slack_down[modeled_year].fix(20)

        assert rps_block.policy_slack_cost[modeled_year].expr() == 30 * 100_000_000

    def test_annual_total_operational_cost_no_penalty_defined(self, make_component_with_block_copy, first_index):
        policy = make_component_with_block_copy()
        rps_block = policy.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        rps_block.policy_slack_up[modeled_year].fix(0)
        rps_block.policy_slack_down[modeled_year].fix(1000)

        assert rps_block.annual_total_operational_cost[modeled_year].expr() == 100_000_000 * 1000

    def test_annual_total_operational_cost_penalty_defined(self, make_component_with_block_copy, first_index):
        policy = make_component_with_block_copy()
        rps_block = policy.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        rps_block.policy_slack_up[modeled_year].fix(0)
        rps_block.policy_slack_down[modeled_year].fix(1000)

        assert rps_block.annual_total_operational_cost[modeled_year].expr() == 1000 * 100_000_000

    def test_annual_total_operational_cost_price(self, make_custom_component_with_block, first_index):
        policy = make_custom_component_with_block(
            target=None,
            price=ts.NumericTimeseries(
                name="TestRPS:price",
                data=pd.Series(
                    index=pd.DatetimeIndex(
                        [
                            "2025-01-01 00:00:00",
                            "2030-01-01 00:00:00",
                        ],
                        name="timestamp",
                    ),
                    data=3,
                    name="price",
                ),
            ),
        )
        rps_block = policy.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        rps_block.policy_slack_up.fix(0)
        rps_block.policy_slack_down.fix(0)
        rps_block.policy_lhs[modeled_year] = 50

        assert rps_block.annual_total_operational_cost[modeled_year].expr() == 150

        rps_block.policy_slack_up.fix(10)
        rps_block.policy_slack_down.fix(45)
        rps_block.policy_lhs[modeled_year] = 50

        assert rps_block.annual_total_operational_cost[modeled_year].expr() == 150 + 55 * 100_000_000


class TestAnnualEmissionsPolicy(ComponentTestTemplate):
    _COMPONENT_CLASS = AnnualEmissionsPolicy
    _COMPONENT_NAME = "TestGHG"
    _SYSTEM_COMPONENT_DICT_NAME = "emissions_policies"

    def test_results_reporting(self, make_component_with_block_copy):
        policy = make_component_with_block_copy()
        block = policy.formulation_block

        # Assign placeholder values to the duel values of the policy constraint
        for year, value in [
            (pd.Timestamp("2025-01-01"), 10),
            (pd.Timestamp("2030-01-01"), 10),
            (pd.Timestamp("2035-01-01"), 10),
            (pd.Timestamp("2045-01-01"), 10),
        ]:
            block.policy_constraint[year].set_suffix_value("dual", value)

        policy._construct_output_expressions(construct_costs=True)

        assert policy.model_fields["target"].title == "Annual Target (Units)"
        assert policy.model_fields["target_adjustment"].title == "Annual Target Adjustment (Units)"
        assert block.policy_slack_up.doc == "Policy Slack Up (Units)"
        assert block.policy_slack_down.doc == "Policy Slack Down (Units)"
        assert block.policy_slack_cost.doc == "Policy Slack Cost ($)"
        assert block.policy_lhs.doc == "Achieved (Units)"
        assert block.annual_total_operational_cost.doc == "Annual Total Operational Cost ($)"
        assert block.annual_resource_emissions_in_policy.doc == "Annual Resource Policy Contribution (tonne)"
        assert block.annual_transmission_emissions_in_policy.doc == "Annual Transmission Policy Contribution (tonne)"
        assert (
            block.annual_negative_emissions_technology_emissions_in_policy.doc
            == "Annual Negative Emissions Technology Policy Contribution (tonne)"
        )
        assert block.annual_plant_emissions_in_policy.doc == "Annual Plant Policy Contribution (tonne)"
        assert block.annual_demand_emissions_in_policy.doc == "Annual Demand Policy Contribution (tonne)"
        assert (
            block.annual_transportation_emissions_in_policy.doc == "Annual Transportation Policy Contribution (tonne)"
        )
        assert block.policy_shadow_price.doc == "Unweighted Dual Value ($/Unit)"

    def update_resources_for_tests(self, resource_with_multiplier, resource_without_multiplier):
        """
        Hard code values to the thermal resources
        """
        first_year = pd.Timestamp("2025-01-01 00:00:00")

        resource_with_multiplier.formulation_block.power_output.fix(20)

        resource_without_multiplier.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
            "CandidateFuel1",
            first_year,
            :,
            :,
        ].fix(100)
        resource_without_multiplier.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
            "CandidateFuel2",
            first_year,
            :,
            :,
        ].fix(60)

        return resource_with_multiplier, resource_without_multiplier

    def update_tx_paths_for_tests(self, tx_path_with_multiplier, tx_path_without_multiplier):
        """
        Hard code values to the tx_paths
        """
        first_year = pd.Timestamp("2025-01-01 00:00:00")

        tx_path_with_multiplier.formulation_block.transmit_power_forward[first_year, :, :].fix(100)
        tx_path_with_multiplier.formulation_block.transmit_power_reverse[first_year, :, :].fix(10)

        tx_path_without_multiplier.formulation_block.transmit_power_forward[first_year, :, :].fix(120)
        tx_path_without_multiplier.formulation_block.transmit_power_reverse[first_year, :, :].fix(40)

        return tx_path_with_multiplier, tx_path_without_multiplier

    def update_transportations_for_tests(self, transp_with_multiplier, transp_without_multiplier):
        """
        Hard code values to the transportations
        """
        first_year = pd.Timestamp("2025-01-01 00:00:00")

        for product_linkage in transp_with_multiplier.products.values():
            product = product_linkage.instance_from
            transp_with_multiplier.formulation_block.transmit_product_forward[product.name, first_year, :, :] = 5
            transp_with_multiplier.formulation_block.transmit_product_reverse[product.name, first_year, :, :] = 6

        for product_linkage in transp_without_multiplier.products.values():
            product = product_linkage.instance_from
            transp_without_multiplier.formulation_block.transmit_product_forward[product.name, first_year, :, :] = 7
            transp_without_multiplier.formulation_block.transmit_product_reverse[product.name, first_year, :, :] = 8

        return transp_with_multiplier, transp_without_multiplier

    def test_annual_resource_emissions_in_policy(
        self,
        make_component_with_block_copy,
    ):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        policy = make_component_with_block_copy()
        block = policy.formulation_block

        resource_with_multiplier = policy.resources["ThermalResource2"].instance_from
        resource_without_multiplier = policy.resources["ThermalResource1"].instance_from

        resource_with_multiplier, resource_without_multiplier = self.update_resources_for_tests(
            resource_with_multiplier, resource_without_multiplier
        )

        # test for resource with multiplier
        assert block.annual_resource_emissions_in_policy["ThermalResource2", first_year].expr() == pytest.approx(
            ((20 * 3 * 0.6 + 20 * 3 * 0.4) * 365) * 0.5
        )

        # test for resource without multiplier
        assert block.annual_resource_emissions_in_policy["ThermalResource1", first_year].expr() == pytest.approx(
            ((100 * 3 * 0.6 + 100 * 3 * 0.4) * 365) * 0.1 + ((60 * 3 * 0.6 + 60 * 3 * 0.4) * 365) * 0.25
        )

    def test_annual_transmission_emissions_in_policy(
        self,
        make_component_with_block_copy,
    ):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        policy = make_component_with_block_copy()
        block = policy.formulation_block

        tx_path_with_multiplier = policy.tx_paths["TxPath"].instance_from
        tx_path_without_multiplier = policy.tx_paths["TxPath2"].instance_from

        tx_path_with_multiplier, tx_path_without_multiplier = self.update_tx_paths_for_tests(
            tx_path_with_multiplier, tx_path_without_multiplier
        )

        # test for tx_path with multiplier
        assert block.annual_transmission_emissions_in_policy["TxPath", first_year].expr() == pytest.approx(
            ((100 * 3 * 0.6 + 100 * 3 * 0.4) * 365) + ((10 * 3 * 0.6 + 10 * 3 * 0.4) * 365)
        )

        # test for tx_path without multiplier
        assert block.annual_transmission_emissions_in_policy["TxPath2", first_year].expr() == pytest.approx(
            5 * ((120 * 3 * 0.6 + 120 * 3 * 0.4) * 365) + 2 * ((40 * 3 * 0.6 + 40 * 3 * 0.4) * 365)
        )

    def test_annual_plant_emissions_in_policy(
        self,
        make_component_with_block_copy,
    ):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        policy = make_component_with_block_copy()
        block = policy.formulation_block

        plant = policy.plants["Plant1"].instance_from

        for product in plant.produced_products.values():
            if product.name in policy.pollutants.keys():
                plant.formulation_block.produced_product_release[product.name, first_year, :, :] = 15

        for product in plant.consumed_products.values():
            if product.name in policy.pollutants.keys():
                plant.formulation_block.consumed_product_capture[product.name, first_year, :, :] = 1

        assert block.annual_plant_emissions_in_policy["Plant1", first_year].expr() == pytest.approx(
            ((15 * 0.6 * 365) * 3 + (15 * 0.4 * 365) * 3) * 20 - ((1 * 0.6 * 365) * 3 + (1 * 0.4 * 365) * 3) * 20
        )

    def test_annual_net_emissions_in_policy(
        self,
        make_component_with_block_copy,
    ):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        policy = make_component_with_block_copy()
        block = policy.formulation_block

        net = policy.negative_emissions_technologies["NegativeEmissionsTechnology1"].instance_from

        for product in net.produced_products.values():
            if product.name in policy.pollutants.keys():
                net.formulation_block.produced_product_release[product.name, first_year, :, :] = 1

        for product in net.consumed_products.values():
            if product.name in policy.pollutants.keys():
                net.formulation_block.consumed_product_capture[product.name, first_year, :, :] = 15

        assert block.annual_negative_emissions_technology_emissions_in_policy[
            "NegativeEmissionsTechnology1", first_year
        ].expr() == pytest.approx(
            ((1 * 0.6 * 365) * 3 + (1 * 0.4 * 365) * 3) * 20 - ((15 * 0.6 * 365) * 3 + (15 * 0.4 * 365) * 3) * 20
        )

    def test_annual_demand_emissions_in_policy(
        self,
        make_component_with_block_copy,
    ):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        policy = make_component_with_block_copy()
        block = policy.formulation_block

        demand = policy.demands["GenericEnergyDemand2"].instance_from

        for product in demand.produced_products.values():
            if product.name in policy.pollutants.keys():
                demand.formulation_block.produced_product_release[product.name, first_year, :, :] = 10

        assert block.annual_demand_emissions_in_policy["GenericEnergyDemand2", first_year].expr() == pytest.approx(
            ((10 * 0.6 * 365) * 3 + (10 * 0.4 * 365) * 3) * 20
        )

    def test_annual_transportation_emissions_in_policy(
        self,
        make_component_with_block_copy,
    ):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        policy = make_component_with_block_copy()
        block = policy.formulation_block

        transp_with_multiplier = policy.transportations["Transportation_1"].instance_from
        transp_without_multiplier = policy.transportations["Transportation_2"].instance_from

        transp_with_multiplier, transp_without_multiplier = self.update_transportations_for_tests(
            transp_with_multiplier, transp_without_multiplier
        )

        assert block.annual_transportation_emissions_in_policy["Transportation_1", first_year].expr() == pytest.approx(
            2 * (((5 * 0.6 * 365) * 3 + (5 * 0.4 * 365) * 3) * 1.5 + ((6 * 0.6 * 365) * 3 + (6 * 0.4 * 365) * 3) * 1.5)
        )

        assert block.annual_transportation_emissions_in_policy["Transportation_2", first_year].expr() == pytest.approx(
            2 * (((7 * 0.6 * 365) * 3 + (7 * 0.4 * 365) * 3) * 5 + ((8 * 0.6 * 365) * 3 + (8 * 0.4 * 365) * 3) * 2)
        )

    def test_policy_lhs(
        self,
        make_component_with_block_copy,
    ):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        policy = make_component_with_block_copy()
        block = policy.formulation_block

        resource_with_multiplier = policy.resources["ThermalResource2"].instance_from
        resource_without_multiplier = policy.resources["ThermalResource1"].instance_from
        resource_with_multiplier, resource_without_multiplier = self.update_resources_for_tests(
            resource_with_multiplier, resource_without_multiplier
        )
        resource_emissions = (
            ((20 * 3 * 0.6 + 20 * 3 * 0.4) * 365) * 0.5
            + ((100 * 3 * 0.6 + 100 * 3 * 0.4) * 365) * 0.1
            + ((60 * 3 * 0.6 + 60 * 3 * 0.4) * 365) * 0.25
        )

        tx_path_with_multiplier = policy.tx_paths["TxPath"].instance_from
        tx_path_without_multiplier = policy.tx_paths["TxPath2"].instance_from
        tx_path_with_multiplier, tx_path_without_multiplier = self.update_tx_paths_for_tests(
            tx_path_with_multiplier, tx_path_without_multiplier
        )
        tx_emissions = (
            ((100 * 3 * 0.6 + 100 * 3 * 0.4) * 365)
            + ((10 * 3 * 0.6 + 10 * 3 * 0.4) * 365)
            + 5 * ((120 * 3 * 0.6 + 120 * 3 * 0.4) * 365)
            + 2 * ((40 * 3 * 0.6 + 40 * 3 * 0.4) * 365)
        )

        plant = policy.plants["Plant1"].instance_from
        for product in plant.produced_products.values():
            if product.name in policy.pollutants.keys():
                plant.formulation_block.produced_product_release[product.name, first_year, :, :] = 15
        plant_emissions = ((15 * 0.6 * 365) * 3 + (15 * 0.4 * 365) * 3) * 20

        seq_plant = policy.plants["Sequestration1"].instance_from
        for product in seq_plant.produced_products.values():
            if product.name in policy.pollutants.keys():
                seq_plant.formulation_block.produced_product_release[product.name, first_year, :, :] = 0.5
        seq_plant_emissions = ((0.5 * 0.6 * 365) * 3 + (0.5 * 0.4 * 365) * 3) * 20

        net = policy.negative_emissions_technologies["NegativeEmissionsTechnology1"].instance_from
        for product in net.consumed_products.values():
            if product.name in policy.pollutants.keys():
                net.formulation_block.consumed_product_capture[product.name, first_year, :, :] = 2
        net_emissions = -((2 * 0.6 * 365) * 3 + (2 * 0.4 * 365) * 3) * 20

        demand = policy.demands["GenericEnergyDemand2"].instance_from
        for product in demand.produced_products.values():
            if product.name in policy.pollutants.keys():
                demand.formulation_block.produced_product_release[product.name, first_year, :, :] = 10
        demand_emissions = ((10 * 0.6 * 365) * 3 + (10 * 0.4 * 365) * 3) * 20

        transp_with_multiplier = policy.transportations["Transportation_1"].instance_from
        transp_without_multiplier = policy.transportations["Transportation_2"].instance_from
        transp_with_multiplier, transp_without_multiplier = self.update_transportations_for_tests(
            transp_with_multiplier, transp_without_multiplier
        )
        transportation_emissions = 2 * 1.5 * (
            ((5 * 0.6 * 365) * 3 + (5 * 0.4 * 365) * 3) + ((6 * 0.6 * 365) * 3 + (6 * 0.4 * 365) * 3)
        ) + 2 * (((7 * 0.6 * 365) * 3 + (7 * 0.4 * 365) * 3) * 5 + ((8 * 0.6 * 365) * 3 + (8 * 0.4 * 365) * 3) * 2)

        assert block.policy_lhs[first_year].expr() == pytest.approx(
            resource_emissions
            + tx_emissions
            + plant_emissions
            + seq_plant_emissions
            + net_emissions
            + demand_emissions
            + transportation_emissions
        )

    def test_policy_slack_cost(self, make_component_with_block_copy):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        policy = make_component_with_block_copy()
        block = policy.formulation_block

        block.policy_slack_up[first_year].fix(100)
        block.policy_slack_down[first_year].fix(60)

        assert block.policy_slack_cost[first_year].expr() == pytest.approx(160 * 100_000_000)

    def test_annual_total_operational_cost(
        self,
        make_custom_component_with_block,
    ):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        policy = make_custom_component_with_block(
            slack_penalty=10000,
            target=None,
            price=ts.NumericTimeseries(
                name="price",
                data=pd.Series(
                    index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2045-01-01", "2050-01-01"]),
                    data=8.0,
                    name="values",
                ),
            ),
        )
        block = policy.formulation_block
        block.policy_lhs[first_year] = 100
        block.policy_slack_cost[first_year] = 555

        assert block.annual_total_operational_cost[first_year].expr() == pytest.approx(8 * 100 + 555)

    def test_annual_total_operational_cost_for_no_price(self, make_component_with_block_copy):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        policy = make_component_with_block_copy()
        block = policy.formulation_block
        block.policy_slack_cost[first_year] = 555

        assert block.annual_total_operational_cost[first_year].expr() == pytest.approx(555)

    def test_policy_constraint(
        self,
        make_component_with_block_copy,
    ):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        second_year = pd.Timestamp("2030-01-01 00:00:00")
        policy = make_component_with_block_copy()
        block = policy.formulation_block

        block.policy_lhs[first_year] = 1
        block.policy_slack_up[first_year] = 10
        block.policy_slack_down[first_year] = 3

        assert block.policy_constraint[first_year].body() == pytest.approx(-6.0)
        assert block.policy_constraint[first_year].upper() == pytest.approx(4.0)
        assert block.policy_constraint[first_year].expr()

        block.policy_lhs[second_year] = 100
        block.policy_slack_up[second_year] = 20
        block.policy_slack_down[second_year] = 10

        assert block.policy_constraint[second_year].body() == pytest.approx(90.0)
        assert block.policy_constraint[second_year].upper() == pytest.approx(4.0)
        assert not block.policy_constraint[second_year].expr()


class Test_HourlyCES(ComponentTestTemplate):

    _COMPONENT_CLASS = HourlyEnergyStandard
    _COMPONENT_NAME = "Test_HourlyCES"
    _SYSTEM_COMPONENT_DICT_NAME = "hourly_energy_policies"

    def test_results_reporting(self, make_component_with_block_copy):
        policy = make_component_with_block_copy()
        policy._construct_output_expressions(construct_costs=True)
        block = policy.formulation_block

        assert block.target.doc == "Target w Adjustment"
        assert block.policy_slack.doc == "Slack"
        assert block.policy_slack_cost.doc == "Policy Slack Cost ($)"
        assert block.policy_lhs.doc == "Achieved (Units)"
        assert block.annual_total_operational_cost.doc == "Annual Total Operational Cost ($)"

        assert block.resource_contribution.doc == "Hourly Policy Contribution (MWh)"
        assert block.policy_shadow_price.doc == "Unweighted Dual Value ($/Unit)"

    def test_policy_constraint(self, make_component_with_block_copy, first_index, last_index):
        policy = make_component_with_block_copy()
        policy_block = policy.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Test 1
        policy_block.policy_lhs[first_index] = 900
        policy_block.policy_slack[first_index].fix(100)
        policy_block.target[first_index] = 1000

        assert policy_block.policy_constraint[first_index].body() == 0
        assert policy_block.policy_constraint[first_index].upper() == 0

        assert policy_block.policy_constraint[first_index].expr()

        # Test 2
        modeled_year, dispatch_window, timestamp = last_index
        policy_block.policy_lhs[last_index] = 900
        policy_block.policy_slack[last_index].fix(50)
        policy_block.target[last_index] = 1000

        assert policy_block.policy_constraint[last_index].body() == 50
        assert policy_block.policy_constraint[last_index].upper() == 0

        assert not policy_block.policy_constraint[last_index].expr()

    def test_policy_lhs(self, make_component_with_block_copy, first_index):
        policy = make_component_with_block_copy()
        policy_block = policy.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        policy.resources["SolarResource1"].instance_from.formulation_block.power_output[first_index] = 100

        assert policy_block.policy_lhs[first_index].expr() == 100

    def test_policy_slack_cost(self, make_component_with_block_copy, first_index):
        policy = make_component_with_block_copy()
        policy_block = policy.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        for d, t in policy_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS:
            policy_block.policy_slack[modeled_year, d, t].fix(10)

        assert policy_block.policy_slack_cost[modeled_year].expr() == 10950


class TestEnergyReserveMargin(ComponentTestTemplate):
    _COMPONENT_CLASS = EnergyReserveMargin
    _COMPONENT_NAME = "TestERM"
    _SYSTEM_COMPONENT_DICT_NAME = "erm_policies"

    def test_results_reporting(self, make_component_with_block_copy):
        policy = make_component_with_block_copy()
        policy._construct_output_expressions(construct_costs=True)
        block = policy.formulation_block

        assert block.policy_slack.doc == "Slack (MW)"
        assert block.policy_slack_cost.doc == "Policy Slack Cost ($)"
        assert block.policy_lhs.doc == "Achieved (MW)"
        assert block.annual_total_slack_investment_cost.doc == "Annual Total Slack Investment Cost ($)"
        assert block.annual_total_investment_cost.doc == "Annual Total Investment Cost ($)"

        assert block.storage_resource_contribution.doc == "Hourly Storage Contribution (MW)"
        assert block.other_resource_contribution.doc == "Hourly Contribution from other resources (MW)"
        assert block.policy_shadow_price.doc == "Unweighted Dual Value ($/Unit)"

    def test_storage_resource_contribution(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        policy = make_component_with_block_copy_inter_period_sharing()
        block = policy.formulation_block

        modeled_year, weather_period, weather_timestamp = first_index_erm

        storage = policy.resources["StorageResource1"].instance_from
        storage.formulation_block.erm_net_power_output[modeled_year, weather_period, weather_timestamp] = 55

        # storage_linkage.multiplier = 0.9
        assert (
            block.storage_resource_contribution[
                "StorageResource1", modeled_year, weather_period, weather_timestamp
            ].expr()
            == 55 * 0.9
        )

    def test_shed_dr_resource_contribution(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        # with energy_budget_annual:
        policy = make_component_with_block_copy_inter_period_sharing()
        block = policy.formulation_block

        modeled_year, weather_period, weather_timestamp = first_index_erm

        shed_dr_resource = policy.resources["ShedDRResource"].instance_from
        shed_dr_resource.formulation_block.erm_power_output[modeled_year, weather_period, weather_timestamp] = 55

        # shed_dr_linkage.multiplier = 0.9
        assert (
            block.shed_dr_resource_contribution[
                "ShedDRResource", modeled_year, weather_period, weather_timestamp
            ].expr()
            == 55 * 0.9
        )

        # without energy_budget_annual:
        shed_dr_no_energy_budget = policy.resources["ShedDRResourceNoEnergyBudget"].instance_from
        shed_dr_no_energy_budget.formulation_block.erm_power_output[modeled_year, weather_period, weather_timestamp] = (
            50.0
        )
        assert (
            block.shed_dr_resource_contribution[
                "ShedDRResourceNoEnergyBudget", modeled_year, weather_period, weather_timestamp
            ].expr()
            == 0.9 * 50.0
        )

    def test_other_resource_contribution(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        policy = make_component_with_block_copy_inter_period_sharing()
        block = policy.formulation_block

        modeled_year, weather_period, timestamp = first_index_erm

        resource_linkage = policy.resources["SolarResource1"]
        resource = resource_linkage.instance_from
        resource.formulation_block.operational_capacity[modeled_year] = 12

        # resource_linkage.multiplier = 0.5
        assert (
            block.other_resource_contribution["SolarResource1", modeled_year, weather_period, timestamp].expr()
            == 12 * 0.5
        )

    def test_tx_path_contribution(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        modeled_year, weather_period, weather_timestamp = first_index_erm
        policy = make_component_with_block_copy_inter_period_sharing()
        block = policy.formulation_block
        tx_linkage = policy.tx_paths["TxPath"]
        tx_path = tx_linkage.instance_from
        tx_path.formulation_block.operational_capacity[modeled_year] = 50.0

        assert block.tx_path_contribution["TxPath", modeled_year, weather_period, weather_timestamp].expr() == 45.0

    def test_generic_asset_contribution(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        modeled_year, weather_period, weather_timestamp = first_index_erm
        policy = make_component_with_block_copy_inter_period_sharing()
        block = policy.formulation_block
        generic_asset_linkage = policy.assets_["GenericAsset1"]
        generic_asset = generic_asset_linkage.instance_from
        generic_asset.formulation_block.operational_capacity[modeled_year] = 50.0

        assert (
            block.generic_asset_contribution["GenericAsset1", modeled_year, weather_period, weather_timestamp].expr()
            == 45.0
        )

    def test_policy_lhs(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        policy = make_component_with_block_copy_inter_period_sharing()
        block = policy.formulation_block

        modeled_year, weather_period, weather_timestamp = first_index_erm

        block.storage_resource_contribution["StorageResource1", modeled_year, weather_period, weather_timestamp] = 11
        block.other_resource_contribution["SolarResource1", modeled_year, weather_period, weather_timestamp] = 22
        block.shed_dr_resource_contribution["ShedDRResource", modeled_year, weather_period, weather_timestamp] = 33
        block.shed_dr_resource_contribution[
            "ShedDRResourceNoEnergyBudget", modeled_year, weather_period, weather_timestamp
        ] = 0.0
        block.tx_path_contribution["TxPath", modeled_year, weather_period, weather_timestamp] = 44
        block.generic_asset_contribution["GenericAsset1", modeled_year, weather_period, weather_timestamp] = 55
        block.storage_resource_contribution[
            "HybridStorageResource1", modeled_year, weather_period, weather_timestamp
        ] = 66
        block.other_resource_contribution[
            "HybridVariableResource1", modeled_year, weather_period, weather_timestamp
        ] = 77

        assert block.policy_lhs[modeled_year, weather_period, weather_timestamp].expr() == pytest.approx(
            11 + 22 + 33 + 44 + 55 + 66 + 77
        )

    def test_policy_constraint(
        self,
        make_component_with_block_copy_inter_period_sharing,
        first_index_erm,
        last_index_erm,
    ):
        policy = make_component_with_block_copy_inter_period_sharing()
        block = policy.formulation_block

        modeled_year, weather_period, weather_timestamp = first_index_erm
        last_modeled_year, _, _ = last_index_erm

        block.policy_lhs[:, weather_period, weather_timestamp] = 5
        block.policy_slack[:, weather_period, weather_timestamp] = 1

        # First year: constraint holds
        # policy_target_adjusted = 2.2
        assert block.policy_constraint[modeled_year, weather_period, weather_timestamp].body() == pytest.approx(6)
        assert block.policy_constraint[modeled_year, weather_period, weather_timestamp].lower() == pytest.approx(2.2)
        assert block.policy_constraint[modeled_year, weather_period, weather_timestamp].expr()

        # Second year: constraint does not hold
        # policy_target_adjusted = 8.8
        assert block.policy_constraint[last_modeled_year, weather_period, weather_timestamp].body() == pytest.approx(6)
        assert block.policy_constraint[last_modeled_year, weather_period, weather_timestamp].lower() == pytest.approx(
            8.8
        )
        assert not block.policy_constraint[last_modeled_year, weather_period, weather_timestamp].expr()

        # test annual slack costs
        first_modeled_year = pd.Timestamp("2025-01-01")
        second_modeled_year = pd.Timestamp("2030-01-01")
        block.policy_slack[first_modeled_year, :, :] = 1.5
        block.policy_slack[second_modeled_year, :, :] = 2.5
        num_days_per_year = block.model().num_days_per_modeled_year[first_modeled_year]
        assert block.policy_slack_cost[first_modeled_year].expr() == 100_000_000 * 24 * num_days_per_year * 1.5
        assert (
            block.annual_total_slack_investment_cost[first_modeled_year].expr()
            == 100_000_000 * 24 * num_days_per_year * 1.5
        )
        assert (
            block.annual_total_investment_cost[first_modeled_year].expr() == 100_000_000 * 24 * num_days_per_year * 1.5
        )

        assert block.policy_slack_cost[second_modeled_year].expr() == 100_000_000 * 24 * num_days_per_year * 2.5
        assert (
            block.annual_total_slack_investment_cost[second_modeled_year].expr()
            == 100_000_000 * 24 * num_days_per_year * 2.5
        )
        assert (
            block.annual_total_investment_cost[second_modeled_year].expr() == 100_000_000 * 24 * num_days_per_year * 2.5
        )


class TestPlanningReserveMargin(ComponentTestTemplate):
    _COMPONENT_CLASS = PlanningReserveMargin
    _COMPONENT_NAME = "TestPRM"
    _SYSTEM_COMPONENT_DICT_NAME = "prm_policies"

    def test_NQC_lhs(
        self,
        make_component_with_block_copy,
    ):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        policy = make_component_with_block_copy()
        block = policy.formulation_block
        expected_NQC_lhs = 0
        for _asset in policy.assets:
            asset = policy.assets[_asset].instance_from
            if policy.assets[_asset].multiplier is not None:
                NQC_multiplier = policy.assets[_asset].multiplier.data.at[first_year]
                asset.formulation_block.reliability_capacity[policy.name, first_year] = 100.0
                expected_NQC_lhs += NQC_multiplier * 100.0
        assert block.NQC_lhs[first_year].expr() == pytest.approx(expected_NQC_lhs)

    def test_ELCC_lhs(
        self,
        make_component_with_block_copy,
    ):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        policy = make_component_with_block_copy()
        block = policy.formulation_block

        elcc_surface = policy.elcc_surfaces["TestELCCSurface"].instance_from
        elcc_surface.formulation_block.ELCC_MW[first_year].fix(100.0)

        assert block.ELCC_lhs[first_year].expr() == 100.0

    def test_policy_lhs(
        self,
        make_component_with_block_copy,
    ):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        policy = make_component_with_block_copy()
        block = policy.formulation_block

        block.NQC_lhs[first_year] = 95.0
        block.ELCC_lhs[first_year] = 50.0

        assert block.policy_lhs[first_year].expr() == pytest.approx(145.0)

    def test_policy_slack_cost(self, make_component_with_block_copy, first_index):
        policy = make_component_with_block_copy()
        policy_block = policy.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        policy_block.policy_slack_up[modeled_year].fix(10)
        policy_block.policy_slack_down[modeled_year].fix(0)

        assert policy_block.policy_slack_cost[modeled_year].expr() == 10 * 100_000_000

    def test_total_policy_cost_in_modeled_year(self, make_component_with_block_copy, first_index):
        policy = make_component_with_block_copy()
        policy_block = policy.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # PRM policy has no price
        assert policy.price is None
        policy_block.policy_slack_cost[modeled_year] = 100.0
        assert policy_block.annual_total_operational_cost[modeled_year].expr() == 0.0
        assert policy_block.annual_total_investment_cost[modeled_year].expr() == 100.0

    def test_policy_constraint(
        self,
        make_component_with_block_copy,
    ):
        first_year = pd.Timestamp("2025-01-01 00:00:00")
        second_year = pd.Timestamp("2030-01-01 00:00:00")
        policy = make_component_with_block_copy()
        block = policy.formulation_block

        # First year: constraint holds
        block.policy_lhs[first_year] = 1000
        block.policy_slack_up[first_year] = 10
        block.policy_slack_down[first_year] = 30

        assert block.policy_constraint[first_year].lower() == 990.0
        assert block.policy_constraint[first_year].body() == pytest.approx(1020.0)
        assert block.policy_constraint[first_year].expr()

        # Second year: constraint does not hold
        block.policy_lhs[second_year] = 1000
        block.policy_slack_up[second_year] = 30
        block.policy_slack_down[second_year] = 10

        assert block.policy_constraint[second_year].lower() == 990.0
        assert block.policy_constraint[second_year].body() == pytest.approx(980.0)
        assert not block.policy_constraint[second_year].expr()

    def test_results_reporting(self, make_component_with_block_copy, first_index):
        policy = make_component_with_block_copy()
        policy._construct_output_expressions(construct_costs=True)
        block = policy.formulation_block

        assert block.policy_shadow_price.doc == "Unweighted Dual Value ($/Unit)"
        assert policy.model_fields["target"].title == "Annual Target (Units)"
        assert policy.model_fields["target_adjustment"].title == "Annual Target Adjustment (Units)"
        assert block.policy_slack_cost.doc == "Policy Slack Cost ($)"
        assert block.policy_lhs.doc == "Achieved (Units)"
        assert block.annual_total_investment_cost.doc == "Annual Total Investment Cost ($)"
        assert block.policy_slack_up.doc == "Policy Slack Up (Units)"
        assert block.policy_slack_down.doc == "Policy Slack Down (Units)"
        assert block.NQC_lhs.doc == "NQC Reliable Capacity (MW)"
        assert block.ELCC_lhs.doc == "ELCC Reliable Capacity (MW)"
        assert block.policy_cost_without_slack.doc == "Policy Cost Without Slack ($)"
