from typing import Any

import pandas as pd
import pyomo.environ as pyo
import pytest

import new_modeling_toolkit.core.temporal.timeseries as ts
from new_modeling_toolkit.system.generics.generic_linkages import FromZoneToPlant
from new_modeling_toolkit.system.generics.plant import Plant
from new_modeling_toolkit.system.generics.plant import PlantGroup
from new_modeling_toolkit.system.generics.process import Process
from tests.system.test_asset import TestAsset
from tests.system.test_asset import TestAssetGroup


class TestPlant(TestAsset):
    _COMPONENT_CLASS = Plant
    _COMPONENT_NAME = "Plant1"
    _SYSTEM_COMPONENT_DICT_NAME = "generic_plants"

    primary_product: str = "Product_2"

    def _operational_attributes(self) -> list[str]:
        return [
            "stochastic_outage_rate",
            "mean_time_to_repair",
            "random_seed",
            "primary_product",
            "ramp_up_limit",
            "ramp_down_limit",
            "min_output_profile",
            "max_output_profile",
            "variable_cost"
        ]
    @property
    def operational_attributes(self) -> list[str]:
        return self._operational_attributes()

    def test_operational_attributes(self, make_component_copy):
        assert make_component_copy().operational_attributes == self.operational_attributes

    def test_operational_linkages(self, make_component_copy):
        assert make_component_copy().operational_linkages == [
            "emissions_policies",
            "annual_energy_policies",
            "hourly_energy_policies",
            "zones",
            "input_zones",
            "output_zones",
        ]

    def test_operational_three_way_linkages(self, make_component_copy):
        assert make_component_copy().operational_three_way_linkages == ["processes"]

    def test_check_if_operationally_equal_copy(self, make_component_copy):
        plant = make_component_copy()

        # Test 1: An exact copy of the resource should be equal to the original (no linkages)
        generic_resource_copy = plant.copy(include_linkages=True, update={"name": "plant_copy"})
        assert plant.check_if_operationally_equal(generic_resource_copy)
        assert generic_resource_copy.check_if_operationally_equal(plant)

    @pytest.mark.parametrize(
        "attr_name, new_value",
        [
            ("can_build_new", False),
            ("can_retire", False),
            ("financial_lifetime", 1000),
            ("physical_lifetime", 1000),
        ],
    )
    def test_check_if_operationally_equal_true(self, make_component_copy, attr_name, new_value):
        generic_resource = make_component_copy()

        # Test 2: A modified copy of the resource that only has non-operational attributes edited should still be equal
        #  to the original (no linkages)
        curr_test_copy = generic_resource.copy(include_linkages=True, update={attr_name: new_value})
        assert generic_resource.check_if_operationally_equal(curr_test_copy)
        assert curr_test_copy.check_if_operationally_equal(generic_resource)

    @pytest.mark.parametrize(
        "attr_name, new_value",
        [
            ("stochastic_outage_rate", 0.1),
            ("mean_time_to_repair", 50),
            ("random_seed", 8),
            (
                "max_output_profile",
                ts.FractionalTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-01-01 01:00"]), data=[0.5, 0.4]),
                ),
            ),
            (
                "min_output_profile",
                ts.FractionalTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-01-01 01:00"]), data=[0.5, 0.4]),
                ),
            ),
            (
                "variable_cost",
                ts.NumericTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-01-01 01:00"]), data=[0.5, 0.4]),
                ),
            ),
        ],
    )
    def test_check_if_operationally_equal_false(self, make_component_copy, attr_name, new_value):
        # Test 3: An modified copy of the resource should not be equal to the original
        generic_resource = make_component_copy()
        curr_test_copy = generic_resource.copy(include_linkages=True, update={attr_name: new_value})
        assert not generic_resource.check_if_operationally_equal(curr_test_copy)
        assert not curr_test_copy.check_if_operationally_equal(generic_resource)

    def test_check_if_operationally_equal_linkages(self, make_component_copy, test_zone_1, test_zone_2):
        plant = make_component_copy().copy(include_linkages=False)

        # Test 4a: A copy of the plant with the same linkages should be equal
        zone_1 = test_zone_1.copy()
        plant.input_zones = {
            zone_1.name: FromZoneToPlant(
                name=(plant.name, zone_1.name),
                instance_from=zone_1,
                instance_to=plant,
            )
        }
        plant_copy = plant.copy(include_linkages=True, update={"name": "plant_copy"})
        assert plant.check_if_operationally_equal(plant_copy)
        assert plant_copy.check_if_operationally_equal(plant)

        # Test 4b: A copy of the plant with the different linkages should not be equal
        plant_copy = plant.copy(update={"name": "plant_copy"})
        zone_2 = test_zone_2.copy()
        plant_copy.input_zones = {
            zone_2.name: FromZoneToPlant(
                name=(plant_copy.name, zone_2.name),
                instance_from=zone_2,
                instance_to=plant_copy,
            )
        }
        assert not plant.check_if_operationally_equal(plant_copy)
        assert not plant_copy.check_if_operationally_equal(plant)

    def test_check_if_operationally_equal_three_way_linkages(
        self, make_component_copy, test_product_1, test_product_2, test_product_input2
    ):
        plant = make_component_copy().copy(include_linkages=False)

        # Test 5a: A plant with the same process should be equal
        plant.processes = {
            (test_product_1.name, test_product_2.name): Process(
                name=(plant.name, test_product_1.name, test_product_2.name),
                instance_1=plant,
                instance_2=test_product_1,
                instance_3=test_product_2,
            )
        }
        plant_copy = plant.copy(include_linkages=True, update={"name": "plant_copy"})
        assert plant.check_if_operationally_equal(plant_copy)
        assert plant_copy.check_if_operationally_equal(plant)

        # Test 5b: A plant with a different process should not be equal
        plant_copy.processes = {
            (test_product_2.name, test_product_1.name): Process(
                name=(plant.name, test_product_2.name, test_product_1.name),
                instance_1=plant,
                instance_2=test_product_2,
                instance_3=test_product_1,
            )
        }
        assert not plant.check_if_operationally_equal(plant_copy)
        assert not plant_copy.check_if_operationally_equal(plant)

    @pytest.fixture(scope="class")
    def capacity_unit_string(self):
        return "MWh/h"

    def test_annual_capital_cost(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block

        assert asset.physical_lifetime == 20
        assert asset.annualized_capital_cost == 20
        block.selected_capacity.fix(100)

        for year in [
            pd.Timestamp("2025-01-01 00:00"),
            pd.Timestamp("2030-01-01 00:00"),
            pd.Timestamp("2035-01-01 00:00"),
        ]:
            assert block.annual_capital_cost[year].expr() == 2_000

        assert block.annual_capital_cost[pd.Timestamp("2045-01-01 00:00")].expr() == 0

    def test_annual_fixed_om_cost(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block

        assert asset.annualized_fixed_om_cost.data.at[asset.build_year] == 10
        assert asset.planned_capacity.data.at[asset.build_year] == 100

        block.selected_capacity.fix(50)
        block.retired_capacity.fix(0)
        for year in [
            pd.Timestamp("2025-01-01 00:00"),
            pd.Timestamp("2030-01-01 00:00"),
            pd.Timestamp("2035-01-01 00:00"),
            pd.Timestamp("2045-01-01 00:00"),
        ]:
            assert block.annual_fixed_om_cost[year].expr() == 1_500

        block.selected_capacity.fix(50)
        block.retired_capacity[pd.Timestamp("2035-01-01 00:00")].fix(50)
        for year, expected in [
            (pd.Timestamp("2025-01-01 00:00"), 1_500),
            (pd.Timestamp("2030-01-01 00:00"), 1_500),
            (pd.Timestamp("2035-01-01 00:00"), 1_000),
            (pd.Timestamp("2045-01-01 00:00"), 1_000),
        ]:
            assert block.annual_fixed_om_cost[year].expr() == expected

    def test_annual_total_investment_cost(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block

        assert asset.physical_lifetime == 20
        assert asset.annualized_capital_cost == 20
        assert asset.annualized_fixed_om_cost.data.at[asset.build_year] == 10
        assert asset.planned_capacity.data.at[asset.build_year] == 100

        block.selected_capacity.fix(50)
        block.retired_capacity.fix(0)
        for year, expected in [
            (pd.Timestamp("2025-01-01 00:00"), 2_500),
            (pd.Timestamp("2030-01-01 00:00"), 2_500),
            (pd.Timestamp("2035-01-01 00:00"), 2_500),
            (pd.Timestamp("2045-01-01 00:00"), 1_500),
        ]:
            assert block.annual_total_investment_cost[year].expr() == expected

        block.selected_capacity.fix(50)
        block.retired_capacity[pd.Timestamp("2035-01-01 00:00")].fix(50)
        for year, expected in [
            (pd.Timestamp("2025-01-01 00:00"), 2_500),
            (pd.Timestamp("2030-01-01 00:00"), 2_500),
            (pd.Timestamp("2035-01-01 00:00"), 2_000),
            (pd.Timestamp("2045-01-01 00:00"), 1_000),
        ]:
            assert block.annual_total_investment_cost[year].expr() == expected
    def test_scaled_min_output_profile(self,make_component_with_block_copy,first_index,last_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block

        # selected_capacity and retired capacity are initialized to zero. planned capacity is 100.
        assert plant.min_output_profile.data.at[first_index[-1]] == 0.1
        assert block.operational_capacity[first_index[0]].expr() == 100
        assert block.scaled_min_output_profile[first_index].expr() == 100 * 0.1

        modeled_year = first_index[0]
        block.operational_capacity[modeled_year] = 0
        assert block.scaled_min_output_profile[first_index].expr() == 0

        modeled_year = last_index[0]
        block.operational_capacity[modeled_year] = 20
        assert block.scaled_min_output_profile[last_index].expr() == 20 * 0.1

    def test_scaled_max_output_profile(self, make_component_with_block_copy, first_index, last_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block

        # selected_capacity and retired capacity are initialized to zero. planned capacity is 100.
        assert plant.max_output_profile.data.at[first_index[-1]] == 0.9
        assert block.operational_capacity[first_index[0]].expr() == 100
        assert block.scaled_max_output_profile[first_index].expr() == 100 * 0.9

        modeled_year = first_index[0]
        block.operational_capacity[modeled_year] = 0
        assert block.scaled_max_output_profile[first_index].expr() == 0

        modeled_year = last_index[0]
        block.operational_capacity[modeled_year] = 20
        assert block.scaled_max_output_profile[last_index].expr() == 20 * 0.9

    def test_consumption(self, make_component_with_block_copy, first_index, last_index):
        plant = make_component_with_block_copy()
        plant_block = plant.formulation_block
        input_product, output_product = list(plant.processes.keys())[0]
        process = plant.processes[(input_product, output_product)]

        plant_block.operation[first_index] = 0
        assert plant_block.consumption[input_product, first_index].expr() == 0

        plant_block.operation[last_index] = 100
        assert process.conversion_rate == 0.9
        assert plant_block.consumption[input_product, last_index].expr() == 100 / 0.9

    def test_production(self, make_component_with_block_copy, first_index, last_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block
        assert plant.primary_product == self.primary_product
        assert isinstance(plant.primary_product, str)

        # Process 1: production = operation
        block.operation[first_index] = 10
        assert block.production[plant.primary_product, first_index].expr() == 10

        # Process 2: production = consumption * process conversion rate
        process2 = list(plant.processes.values())[1]
        assert process2.conversion_rate == 0.75
        block.consumption[process2.consumed_product.name, first_index] = 10
        assert block.production[process2.produced_product.name, first_index].expr() == 10 * 0.75

    def test_variable_cost_dispatched(self, make_component_with_block_copy, first_index, last_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block

        block.operation[first_index] = 10
        assert block.variable_cost_dispatched[first_index].expr() == 100

        block.operation[last_index] = 100
        assert block.variable_cost_dispatched[last_index].expr() == 1000

        variable_cost_dispatched = 0
        block.operation[first_index].fix(variable_cost_dispatched)
        assert block.variable_cost_dispatched[first_index].expr() == variable_cost_dispatched

    def test_production_tax_credit(self, make_component_with_block_copy, first_index, last_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block

        assert plant.production_tax_credit == 2

        block.production[self.primary_product, first_index] = 100
        block.production[self.primary_product, last_index] = 200
        assert block.production_tax_credit[first_index].expr() == 200
        assert block.production_tax_credit[last_index].expr() == 400

    def test_annual_variable_cost(self, make_component_with_block_copy, first_index, last_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block

        modeled_year = first_index[0]
        annual_total_variable_cost = 0
        for dispatch_window, timestamp in list(block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS):
            block.variable_cost_dispatched[modeled_year, dispatch_window, timestamp] = 0
            annual_total_variable_cost += (
                block.variable_cost_dispatched[modeled_year, dispatch_window, timestamp].expr()
                * block.model().dispatch_window_weights[dispatch_window]
                * block.model().num_days_per_modeled_year[modeled_year]
                * block.model().timestamp_durations_hours[dispatch_window, timestamp]
            )

        assert block.annual_variable_cost[modeled_year].expr() == annual_total_variable_cost

        modeled_year = last_index[0]
        annual_total_variable_cost = 0
        for dispatch_window, timestamp in list(block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS):
            block.variable_cost_dispatched[modeled_year, dispatch_window, timestamp] = 10
            annual_total_variable_cost += (
                block.variable_cost_dispatched[modeled_year, dispatch_window, timestamp].expr()
                * block.model().dispatch_window_weights[dispatch_window]
                * block.model().num_days_per_modeled_year[modeled_year]
                * block.model().timestamp_durations_hours[dispatch_window, timestamp]
            )

        assert block.annual_variable_cost[modeled_year].expr() == annual_total_variable_cost

    def test_consumed_commodity_product_cost(self, make_component_with_block_copy, first_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        for consumed_product in plant.consumed_products.keys():
            block.consumption[consumed_product, modeled_year, :, :] = 100.0

        assert block.consumed_commodity_product_cost[first_index].expr() == 100.0 * 3.0

    def test_annual_consumed_commodity_product_cost(self, make_component_with_block_copy, first_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        for consumed_product in plant.consumed_products.keys():
            block.consumption[consumed_product, modeled_year, :, :] = 100.0

        assert block.annual_consumed_commodity_product_cost[modeled_year].expr() == 100.0 * 3.0 * 3.0 * 365.0

    def test_annual_total_operational_cost(self, make_component_with_block_copy, first_index, last_index):

        plant = make_component_with_block_copy()
        block = plant.formulation_block
        modeled_year = first_index[0]

        block.annual_variable_cost[modeled_year] = 100
        block.annual_consumed_commodity_product_cost[modeled_year] = 1500
        block.annual_production_tax_credit[modeled_year] = 99
        assert block.annual_total_operational_cost[modeled_year].expr() == 100 + 1500 - 99

        modeled_year2 = last_index[0]
        block.annual_variable_cost[modeled_year2] = 5000
        block.annual_consumed_commodity_product_cost[modeled_year2] = 1000
        block.annual_production_tax_credit[modeled_year2] = 88
        assert block.annual_total_operational_cost[modeled_year2].expr() == 5000 + 1000 - 88

    def test_min_output_constraint(self, make_component_with_block_copy, first_index, last_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block

        assert block.min_output_constraint[first_index].upper() == 0

        block.scaled_min_output_profile[first_index] = 0
        modeled_year, dispatch_window, timestamp = first_index
        block.operation[modeled_year, dispatch_window, timestamp].fix(0)
        assert block.min_output_constraint[first_index].body() == 0
        assert block.min_output_constraint[first_index].expr()

        block.scaled_min_output_profile[first_index] = 10
        block.operation[modeled_year, dispatch_window, timestamp].fix(10)
        assert block.min_output_constraint[first_index].body() == 0
        assert block.min_output_constraint[first_index].expr()

        modeled_year, dispatch_window, timestamp = last_index
        block.operation[modeled_year, dispatch_window, timestamp].fix(1000)
        block.scaled_min_output_profile[last_index] = 10
        assert block.min_output_constraint[last_index].body() == -990
        assert block.min_output_constraint[last_index].expr()

        block.operation[modeled_year, dispatch_window, timestamp].fix(0)
        assert block.min_output_constraint[last_index].body() == 10
        assert not block.min_output_constraint[last_index].expr()


    def test_max_output_constraint(self, make_component_with_block_copy, first_index, last_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block

        assert block.max_output_constraint[first_index].upper() == 0

        block.scaled_max_output_profile[first_index] = 0
        modeled_year, dispatch_window, timestamp = first_index
        block.operation[modeled_year, dispatch_window, timestamp].fix(0)
        assert block.max_output_constraint[first_index].body() == 0
        assert block.max_output_constraint[first_index].expr()

        block.scaled_max_output_profile[first_index] = 100
        block.operation[modeled_year, dispatch_window, timestamp].fix(10)
        assert block.max_output_constraint[first_index].body() == -90
        assert block.max_output_constraint[first_index].expr()

        modeled_year, dispatch_window, timestamp = last_index
        block.operation[modeled_year, dispatch_window, timestamp].fix(1000)
        block.scaled_max_output_profile[last_index] = 10

        assert block.max_output_constraint[last_index].body() == 990
        assert not block.max_output_constraint[last_index].expr()

    def test_results_reporting(self, make_component_with_block_copy, capacity_unit_string):
        plant = make_component_with_block_copy()
        block = plant.formulation_block

        plant._construct_output_expressions(construct_costs=True)

        assert block.operation.doc == f"Hourly Operation ({capacity_unit_string})"
        assert block.consumption.doc == f"Hourly Consumption of Input Product (Product Units per hour)"
        assert block.production.doc == f"Hourly Production of Output Product (Product Units per hour)"
        assert block.consumed_product_capture.doc == "Hourly Consumed Product Capture (Product Units per hour)"
        assert block.consumed_product_from_zone.doc == "Hourly Consumed Product From Zone (Product Units per hour)"
        assert block.produced_product_to_zone.doc == "Hourly Produced Product To Zone (Product Units per hour)"
        assert block.produced_product_release.doc == "Hourly Produced Product Release (Product Units per hour)"
        assert block.annual_variable_cost.doc == "Annual Total Variable Cost ($)"
        assert block.annual_consumed_commodity_product_cost.doc == "Annual Total Consumed Commodity Product Cost ($)"
        assert block.annual_total_operational_cost.doc == "Annual Total Operational Cost ($)"

        assert block.annual_consumption.doc == f"Annual Product Consumption (Product Units)"
        assert block.annual_production.doc == f"Annual Product Production (Product Units)"
        assert block.annual_consumed_product_capture.doc == "Annual Consumed Product Capture (Product Units)"
        assert block.annual_consumed_product_from_zone.doc == "Annual Consumed Product From Zone (Product Units)"
        assert block.annual_produced_product_to_zone.doc == "Annual Produced Product To Zone (Product Units)"
        assert block.annual_produced_product_release.doc == "Annual Produced Product Release (Product Units)"
        assert block.annual_production_tax_credit.doc == "Annual Production Tax Credit ($)"

class TestPlantWithCapture(TestPlant):

    _COMPONENT_NAME = "PlantWithInputOutputCapture"
    _COMPONENT_CLASS = Plant
    _SYSTEM_COMPONENT_DICT_NAME = "generic_plants"

    def test_production(self, make_component_with_block_copy, first_index, last_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block
        assert plant.primary_product == self.primary_product
        assert isinstance(plant.primary_product, str)

        # Process 1: production = operation
        block.operation[first_index] = 10
        assert block.production[plant.primary_product, first_index].expr() == 10

        # Process 2: production = consumption * process conversion rate
        process2 = list(plant.processes.values())[1]
        assert process2.conversion_rate == 1.0
        block.consumption[process2.consumed_product.name, first_index] = 10
        assert block.production[process2.produced_product.name, first_index].expr() == 10 * 1.0

    def test_consumed_commodity_product_cost(self, make_component_with_block_copy, first_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        for consumed_product in plant.consumed_products.keys():
            block.consumption[consumed_product, modeled_year, :, :] = 100.0

        assert block.consumed_commodity_product_cost[first_index].expr() == 0.0

    def test_annual_consumed_commodity_product_cost(self, make_component_with_block_copy, first_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        for consumed_product in plant.consumed_products.keys():
            block.consumption[consumed_product, modeled_year, :, :] = 100.0

        assert block.annual_consumed_commodity_product_cost[modeled_year].expr() == 0.0

    def update_optimization_component(self, block: pyo.Block, component_name: str, index: tuple[Any], value: float):
        try:
            getattr(block, component_name)[index].fix(value)
        except:
            getattr(block, component_name)[index] = value

    def update_optimization_components_by_inputs(
        self,
        block: pyo.Block,
        component_name: str,
        index: tuple[Any],
        value: float,
    ):
        for input in block.INPUTS:
            new_index = (input, *index)
            self.update_optimization_component(block, component_name, new_index, value)

    def update_optimization_components_by_outputs(
        self,
        block: pyo.Block,
        component_name: str,
        index: tuple[Any],
        value: float,
    ):
        for output in block.OUTPUTS:
            new_index = (output, *index)
            self.update_optimization_component(block, component_name, new_index, value)

    def update_consumption(self, block, index, value):
        for input in block.INPUTS:
            block.consumption[input, index] = value

    def update_production(self, block, index, value):
        for output in block.OUTPUTS:
            block.production[output, index] = value

    def test_consumed_product_capture(self, make_component_with_block_copy, first_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block
        self.update_optimization_component(block, "operation", first_index, 0)

        assert all(
            block.consumed_product_capture[consumed_product, first_index].expr()==0
            for consumed_product in block.INPUTS
        )

        self.update_optimization_component(block, "operation", first_index, 100)
        assert all(
            block.consumed_product_capture[consumed_product, first_index].expr()
            == sum(
                100 / process.conversion_rate * process.input_capture_rate
                for process in plant.primary_output_processes
                if process.consumed_product.name == consumed_product
            )
            for consumed_product in block.INPUTS
        )

        assert not all(
            block.consumed_product_capture[consumed_product, first_index].expr()
            == sum(
                1_000_000 / process.conversion_rate * process.input_capture_rate
                for process in plant.primary_output_processes
                if process.consumed_product.name == consumed_product
            )
            for consumed_product in block.INPUTS
        )

    def test_consumed_product_from_zone(self, make_component_with_block_copy, first_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block

        self.update_optimization_components_by_inputs(block, "consumption", first_index, 0)
        self.update_optimization_components_by_inputs(block, "consumed_product_capture", first_index, 0)
        assert all(
            block.consumed_product_from_zone[consumed_product, first_index].expr() == 0
            for consumed_product in block.INPUTS
        )

        self.update_optimization_components_by_inputs(block, "consumption", first_index, 100)
        self.update_optimization_components_by_inputs(block, "consumed_product_capture", first_index, 90)
        assert all(
            block.consumed_product_from_zone[consumed_product, first_index].expr() == 10
            for consumed_product in block.INPUTS
        )

    def test_produced_product_to_zone(self, make_component_with_block_copy, first_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block

        self.update_optimization_component(block, "operation", first_index, 0)
        assert all(
            block.produced_product_to_zone[produced_product, first_index].expr() == 0
            for produced_product in block.OUTPUTS
        )

        self.update_optimization_component(block, "operation", first_index, 100)
        self.update_optimization_components_by_inputs(block, "consumption", first_index, 100)
        for output in block.OUTPUTS:
            if output == plant.primary_product:
                assert (
                    block.produced_product_to_zone[output, first_index].expr()
                    == 100 * plant.primary_process_output_capture_rate
                )
                assert not all(
                    block.produced_product_to_zone[output, first_index].expr() == 100 * process.output_capture_rate
                    for process in plant.primary_output_processes
                )
            else:
                assert block.produced_product_to_zone[output, first_index].expr() == sum(
                    100 * process.conversion_rate * process.output_capture_rate
                    for process in plant.processes.values()
                    if process.produced_product.name == output
                )

    def test_produced_product_release(self, make_component_with_block_copy, first_index):
        plant = make_component_with_block_copy()
        block = plant.formulation_block

        self.update_optimization_components_by_outputs(block, "production", first_index, 0)
        self.update_optimization_components_by_outputs(block, "produced_product_to_zone", first_index, 0)
        assert all(
            block.produced_product_release[produced_product, first_index].expr() == 0
            for produced_product in block.OUTPUTS
        )

        self.update_optimization_components_by_outputs(block, "production", first_index, 100)
        self.update_optimization_components_by_outputs(block, "produced_product_to_zone", first_index, 90)
        assert all(
            block.produced_product_release[produced_product, first_index].expr() == 10
            for produced_product in block.OUTPUTS
        )


class TestPlantGroup(TestAssetGroup, TestPlant):
    _COMPONENT_CLASS = PlantGroup
    _COMPONENT_NAME = "generic_plant_group"
    _SYSTEM_COMPONENT_DICT_NAME = "plant_groups"

    def test_scaled_min_output_profile(self, make_component_with_block_copy, first_index, last_index):
        plant_group = make_component_with_block_copy()
        plants = plant_group.asset_instances
        block = plant_group.formulation_block

        block.operational_capacity[first_index[0]] = 100 * len(plants)
        assert plant_group.min_output_profile.data.at[first_index[-1]] == 0.1
        assert block.scaled_min_output_profile[first_index].expr() == 100 * len(plants) * 0.1

        modeled_year = first_index[0]
        block.operational_capacity[modeled_year] = 0
        assert block.scaled_min_output_profile[first_index].expr() == 0

        modeled_year = last_index[0]
        block.operational_capacity[modeled_year] = 20
        assert block.scaled_min_output_profile[last_index].expr() == 20 * 0.1

    def test_scaled_max_output_profile(self, make_component_with_block_copy, first_index, last_index):
        plant_group = make_component_with_block_copy()
        plants = plant_group.asset_instances
        block = plant_group.formulation_block

        block.operational_capacity[first_index[0]] = 100 * len(plants)
        assert plant_group.max_output_profile.data.at[first_index[-1]] == 0.9
        assert block.scaled_max_output_profile[first_index].expr() == 100 * len(plants) * 0.9

        modeled_year = first_index[0]
        block.operational_capacity[modeled_year] = 0
        assert block.scaled_max_output_profile[first_index].expr() == 0

        modeled_year = last_index[0]
        block.operational_capacity[modeled_year] = 20
        assert block.scaled_max_output_profile[last_index].expr() == 20 * 0.9
