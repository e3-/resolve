import copy

import pytest

from new_modeling_toolkit.system import Electricity
from new_modeling_toolkit.system.electric.zone import Zone
from tests.system.component_test_template import ComponentTestTemplate


class TestZone(ComponentTestTemplate):
    _COMPONENT_CLASS = Zone
    _COMPONENT_NAME = "Zone_1"
    _SYSTEM_COMPONENT_DICT_NAME = "zones"

    @pytest.fixture(scope="class")
    def make_component_with_block_copy_zone_2(self, test_model):
        def _make_copy_with_block():
            return copy.deepcopy(getattr(test_model.system, self._SYSTEM_COMPONENT_DICT_NAME)["Zone_2"])

        return _make_copy_with_block

    def test_zonal_resource_provide_power(self, make_component_with_block_copy, first_index, last_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        for name, resource in zone.resource_instances.items():
            if name == "HydroResource1":
                resource.formulation_block.power_output[first_index].fix(100)
            elif name == "ThermalResource1":
                resource.formulation_block.power_output[first_index].fix(50)
            else:
                resource.formulation_block.power_output[first_index].fix(0)

        assert block.zonal_resource_provide_power[first_index].expr() == 150

        for name, resource in zone.resource_instances.items():
            if name == "HydroResource1":
                resource.formulation_block.power_output[last_index].fix(100)
            elif name == "ThermalResource1":
                resource.formulation_block.power_output[last_index].fix(100)
            else:
                resource.formulation_block.power_output[last_index].fix(0)

        assert not block.zonal_resource_provide_power[last_index].expr() == 150

    def test_zonal_plant_provide_power(self, make_component_with_block_copy, first_index, last_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        electric_producers = 0
        for linkage in zone.producing_plants.values():
            plant = linkage.plant
            for product_name, product in plant.produced_products.items():
                if isinstance(product, Electricity):
                    plant.formulation_block.produced_product_to_zone[product_name, first_index].fix(1000)
                    electric_producers += 1

        assert block.zonal_plant_provide_power[first_index].expr() == electric_producers

        electric_producers = 0
        for linkage in zone.producing_plants.values():
            plant = linkage.plant
            for product_name, product in plant.produced_products.items():
                if isinstance(product, Electricity):
                    plant.formulation_block.produced_product_to_zone[product_name, last_index].fix(10_000)
                    electric_producers += 1

        assert block.zonal_plant_provide_power[last_index].expr() == 10 * electric_producers

    def test_zonal_demand_provide_power(self, make_component_with_block_copy, first_index, last_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        electric_producers = 0
        for linkage in zone.producing_demands.values():
            demand = linkage.demand
            if hasattr(demand.formulation_block, "OUTPUTS"):
                for product_name, product in demand.produced_products.items():
                    if isinstance(product, Electricity):
                        demand.formulation_block.produced_product_to_zone[product_name, first_index].fix(1000)
                        electric_producers += 1

        assert block.zonal_demand_provide_power[first_index].expr() == electric_producers

        electric_producers = 0
        for linkage in zone.producing_demands.values():
            demand = linkage.demand
            if hasattr(demand.formulation_block, "OUTPUTS"):
                for product_name, product in demand.produced_products.items():
                    if isinstance(product, Electricity):
                        demand.formulation_block.produced_product_to_zone[product_name, last_index].fix(10_000)
                        electric_producers += 1

        assert block.zonal_demand_provide_power[last_index].expr() == 10 * electric_producers

    def test_zonal_provide_power(self, make_component_with_block_copy, first_index, last_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        block.zonal_resource_provide_power[first_index] = 1_000
        block.zonal_plant_provide_power[first_index] = 13
        block.zonal_demand_provide_power[first_index] = 223

        assert block.zonal_provide_power[first_index].expr() == 1_000 + 13 + 223

    def test_zonal_resource_increase_load(self, make_component_with_block_copy, first_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        for name, resource in zone.resource_instances.items():
            if name == "StorageResource1":
                resource.formulation_block.power_input[first_index].fix(100)

        assert block.zonal_resource_increase_load[first_index].expr() == 100

    def test_zonal_plant_increase_load(self, make_component_with_block_copy, first_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        electric_consumers = 0
        for linkage in zone.consuming_plants.values():
            plant = linkage.plant
            for product_name, product in plant.consumed_products.items():
                if isinstance(product, Electricity):
                    plant.formulation_block.consumed_product_from_zone[product_name, first_index] = 10_000
                    electric_consumers += 1

        assert block.zonal_plant_increase_load[first_index].expr() == 10 * electric_consumers

    def test_zonal_demand_increase_load(self, make_component_with_block_copy, first_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        electric_consumers = 0
        for linkage in zone.consuming_demands.values():
            demand = linkage.demand
            for product_name, product in demand.consumed_products.items():
                if isinstance(product, Electricity):
                    demand.formulation_block.consumed_product_from_zone[product_name, first_index] = 10_000
                    electric_consumers += 1

        assert block.zonal_demand_increase_load[first_index].expr() == 10 * electric_consumers

    def test_zonal_synchronous_condenser_increase_load(self, make_component_with_block_copy, first_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        zone.resource_instances["ThermalUnitCommitmentResource"].formulation_block.committed_capacity[
            first_index
        ] = 10  # addition_to_load = 0
        zone.resource_instances["ThermalUnitCommitmentResource2"].formulation_block.committed_capacity[
            first_index
        ] = 12345  # addition_to_load = 4

        assert block.zonal_synchronous_condenser_increase_load[first_index].expr() == 0 + 4 * 12345

    def test_zonal_increase_load(self, make_component_with_block_copy, first_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        block.zonal_resource_increase_load[first_index] = 340
        block.zonal_plant_increase_load[first_index] = 22
        block.zonal_demand_increase_load[first_index] = 3954
        block.zonal_synchronous_condenser_increase_load[first_index] = 1982

        assert block.zonal_increase_load[first_index].expr() == 340 + 22 + 3954 + 1982

    def test_input_load(self, make_component_with_block_copy, first_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        # first index: check that input load = load 1 + load 2
        modeled_year, dispatch_window, timestamp = first_index
        num_loads = len(zone.loads)
        assert num_loads == 2
        input_load = 0
        for load in zone.load_instances.values():
            input_load += load.get_load(modeled_year.year, timestamp)
        assert block.input_load[modeled_year, dispatch_window, timestamp].expr() == input_load

    def test_zonal_net_imports(self, make_component_with_block_copy, first_index, last_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        # first index: all flows from zone
        for tx_path_from_zone in zone.tx_path_instances_from_zone.values():
            tx_path_from_zone.formulation_block.transmit_power_forward[first_index].fix(100)
            tx_path_from_zone.formulation_block.transmit_power_reverse[first_index].fix(0)
        for tx_path_to_zone in zone.tx_path_instances_to_zone.values():
            tx_path_to_zone.formulation_block.transmit_power_forward[first_index].fix(0)
            tx_path_to_zone.formulation_block.transmit_power_reverse[first_index].fix(100)

        assert block.zonal_net_imports[first_index].expr() == (
            -(len(zone.tx_path_instances_from_zone) * 100) - (len(zone.tx_path_instances_to_zone) * 100)
        )

        # first index: forward flows from zone, forward flows to zone
        for tx_path_from_zone in zone.tx_path_instances_from_zone.values():
            tx_path_from_zone.formulation_block.transmit_power_forward[first_index].fix(100)
            tx_path_from_zone.formulation_block.transmit_power_reverse[first_index].fix(0)
        for tx_path_to_zone in zone.tx_path_instances_to_zone.values():
            tx_path_to_zone.formulation_block.transmit_power_forward[first_index].fix(100)
            tx_path_to_zone.formulation_block.transmit_power_reverse[first_index].fix(0)

        assert block.zonal_net_imports[first_index].expr() == (
            -(len(zone.tx_path_instances_from_zone) * 100) + (len(zone.tx_path_instances_to_zone) * 100)
        )

        # last index: all flows to zone
        for tx_path_from_zone in zone.tx_path_instances_from_zone.values():
            tx_path_from_zone.formulation_block.transmit_power_forward[last_index].fix(0)
            tx_path_from_zone.formulation_block.transmit_power_reverse[last_index].fix(100)
        for tx_path_to_zone in zone.tx_path_instances_to_zone.values():
            tx_path_to_zone.formulation_block.transmit_power_forward[last_index].fix(100)
            tx_path_to_zone.formulation_block.transmit_power_reverse[last_index].fix(0)

        assert block.zonal_net_imports[last_index].expr() == (
            (len(zone.tx_path_instances_from_zone) * 100) + (len(zone.tx_path_instances_to_zone) * 100)
        )

        # last index: reverse flows from zone, reverse flows to zone
        for tx_path_from_zone in zone.tx_path_instances_from_zone.values():
            tx_path_from_zone.formulation_block.transmit_power_forward[last_index].fix(0)
            tx_path_from_zone.formulation_block.transmit_power_reverse[last_index].fix(100)
        for tx_path_to_zone in zone.tx_path_instances_to_zone.values():
            tx_path_to_zone.formulation_block.transmit_power_forward[last_index].fix(0)
            tx_path_to_zone.formulation_block.transmit_power_reverse[last_index].fix(100)

        assert block.zonal_net_imports[last_index].expr() == (
            (len(zone.tx_path_instances_from_zone) * 100) - (len(zone.tx_path_instances_to_zone) * 100)
        )

    def test_zonal_gross_imports(self, make_component_with_block_copy, first_index, last_index):
        zone = make_component_with_block_copy()
        zone._construct_output_expressions(construct_costs=False)
        block = zone.formulation_block

        # first index: all flows from zone
        for tx_path_from_zone in zone.tx_path_instances_from_zone.values():
            tx_path_from_zone.formulation_block.transmit_power_forward[first_index].fix(100)
            tx_path_from_zone.formulation_block.transmit_power_reverse[first_index].fix(0)
        for tx_path_to_zone in zone.tx_path_instances_to_zone.values():
            tx_path_to_zone.formulation_block.transmit_power_forward[first_index].fix(0)
            tx_path_to_zone.formulation_block.transmit_power_reverse[first_index].fix(100)

        assert block.zonal_gross_imports[first_index].expr() == 0

        # first index: forward flows from zone, forward flows to zone
        for tx_path_from_zone in zone.tx_path_instances_from_zone.values():
            tx_path_from_zone.formulation_block.transmit_power_forward[first_index].fix(100)
            tx_path_from_zone.formulation_block.transmit_power_reverse[first_index].fix(0)
        for tx_path_to_zone in zone.tx_path_instances_to_zone.values():
            tx_path_to_zone.formulation_block.transmit_power_forward[first_index].fix(100)
            tx_path_to_zone.formulation_block.transmit_power_reverse[first_index].fix(0)

        assert block.zonal_gross_imports[first_index].expr() == len(zone.tx_path_instances_to_zone) * 100

        # last index: all flows to zone
        for tx_path_from_zone in zone.tx_path_instances_from_zone.values():
            tx_path_from_zone.formulation_block.transmit_power_forward[last_index].fix(0)
            tx_path_from_zone.formulation_block.transmit_power_reverse[last_index].fix(100)
        for tx_path_to_zone in zone.tx_path_instances_to_zone.values():
            tx_path_to_zone.formulation_block.transmit_power_forward[last_index].fix(100)
            tx_path_to_zone.formulation_block.transmit_power_reverse[last_index].fix(0)

        assert block.zonal_gross_imports[last_index].expr() == (
            (len(zone.tx_path_instances_from_zone) * 100) + (len(zone.tx_path_instances_to_zone) * 100)
        )

        # last index: reverse flows from zone, reverse flows to zone
        for tx_path_from_zone in zone.tx_path_instances_from_zone.values():
            tx_path_from_zone.formulation_block.transmit_power_forward[last_index].fix(0)
            tx_path_from_zone.formulation_block.transmit_power_reverse[last_index].fix(100)
        for tx_path_to_zone in zone.tx_path_instances_to_zone.values():
            tx_path_to_zone.formulation_block.transmit_power_forward[last_index].fix(0)
            tx_path_to_zone.formulation_block.transmit_power_reverse[last_index].fix(100)

        assert block.zonal_gross_imports[last_index].expr() == len(zone.tx_path_instances_from_zone) * 100

    def test_zonal_gross_exports(self, make_component_with_block_copy, first_index, last_index):
        zone = make_component_with_block_copy()
        zone._construct_output_expressions(construct_costs=False)
        block = zone.formulation_block

        # first index: all flows from zone
        for tx_path_from_zone in zone.tx_path_instances_from_zone.values():
            tx_path_from_zone.formulation_block.transmit_power_forward[first_index].fix(100)
            tx_path_from_zone.formulation_block.transmit_power_reverse[first_index].fix(0)
        for tx_path_to_zone in zone.tx_path_instances_to_zone.values():
            tx_path_to_zone.formulation_block.transmit_power_forward[first_index].fix(0)
            tx_path_to_zone.formulation_block.transmit_power_reverse[first_index].fix(100)

        assert block.zonal_gross_exports[first_index].expr() == (
            (len(zone.tx_path_instances_from_zone) * 100) + (len(zone.tx_path_instances_to_zone) * 100)
        )

        # first index: forward flows from zone, forward flows to zone
        for tx_path_from_zone in zone.tx_path_instances_from_zone.values():
            tx_path_from_zone.formulation_block.transmit_power_forward[first_index].fix(100)
            tx_path_from_zone.formulation_block.transmit_power_reverse[first_index].fix(0)
        for tx_path_to_zone in zone.tx_path_instances_to_zone.values():
            tx_path_to_zone.formulation_block.transmit_power_forward[first_index].fix(100)
            tx_path_to_zone.formulation_block.transmit_power_reverse[first_index].fix(0)

        assert block.zonal_gross_exports[first_index].expr() == len(zone.tx_path_instances_from_zone) * 100

        # last index: all flows to zone
        for tx_path_from_zone in zone.tx_path_instances_from_zone.values():
            tx_path_from_zone.formulation_block.transmit_power_forward[last_index].fix(0)
            tx_path_from_zone.formulation_block.transmit_power_reverse[last_index].fix(100)
        for tx_path_to_zone in zone.tx_path_instances_to_zone.values():
            tx_path_to_zone.formulation_block.transmit_power_forward[last_index].fix(100)
            tx_path_to_zone.formulation_block.transmit_power_reverse[last_index].fix(0)

        assert block.zonal_gross_exports[last_index].expr() == 0

        # last index: reverse flows from zone, reverse flows to zone
        for tx_path_from_zone in zone.tx_path_instances_from_zone.values():
            tx_path_from_zone.formulation_block.transmit_power_forward[last_index].fix(0)
            tx_path_from_zone.formulation_block.transmit_power_reverse[last_index].fix(100)
        for tx_path_to_zone in zone.tx_path_instances_to_zone.values():
            tx_path_to_zone.formulation_block.transmit_power_forward[last_index].fix(0)
            tx_path_to_zone.formulation_block.transmit_power_reverse[last_index].fix(100)

        assert block.zonal_gross_exports[last_index].expr() == len(zone.tx_path_instances_to_zone) * 100

    def test_zonal_plant_production_by_product(self, make_component_with_block_copy_zone_2, first_index):
        zone = make_component_with_block_copy_zone_2()
        block = zone.formulation_block
        product_name = "Product_2"
        total_num_products = 0

        for producing_plant_linkage in zone.producing_plants.values():
            plant = producing_plant_linkage.plant
            if product_name in plant.produced_products:
                plant.formulation_block.produced_product_to_zone[product_name, first_index] = 100
                total_num_products += 1

            with pytest.raises(KeyError):
                p1 = plant.formulation_block.produced_product_to_zone["not_a_product_name", first_index]
                assert p1 is None

        assert block.zonal_plant_production_by_product[product_name, first_index].expr() == 100 * total_num_products

    def test_zonal_demand_production_by_product(self, make_component_with_block_copy_zone_2, first_index):
        zone = make_component_with_block_copy_zone_2()
        block = zone.formulation_block
        product_name = "Product_2"
        total_num_products = 0

        for producing_demand_linkage in zone.producing_demands.values():
            demand = producing_demand_linkage.demand
            if product_name in demand.produced_products:
                demand.formulation_block.produced_product_to_zone[product_name, first_index] = 100
                total_num_products += 1

        assert block.zonal_demand_production_by_product[product_name, first_index].expr() == 100 * total_num_products

    def test_zonal_production_by_product(self, make_component_with_block_copy_zone_2, first_index):
        zone = make_component_with_block_copy_zone_2()
        block = zone.formulation_block
        product_name = "Product_2"

        block.zonal_plant_production_by_product[product_name, first_index] = 230
        block.zonal_demand_production_by_product[product_name, first_index] = 37

        assert block.zonal_production_by_product[product_name, first_index].expr() == 230 + 37

    def test_zonal_resource_consumption_by_product(self, make_component_with_block_copy, first_index, last_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        product_name = "Product_1"
        resources = 0

        for resource in zone.resource_instances.values():
            if hasattr(resource, "candidate_fuels"):
                if product_name in resource.candidate_fuels.keys():
                    resource.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
                        product_name, first_index
                    ].fix(1_000)
                    resources += 1

        assert block.zonal_resource_consumption_by_product[product_name, first_index].expr() == 0

        product_name = "CandidateFuel1"
        resources = 0
        for resource in zone.resource_instances.values():
            if hasattr(resource, "candidate_fuels"):
                if product_name in resource.candidate_fuels.keys():
                    resource.formulation_block.resource_fuel_consumption_in_timepoint_mmbtu[
                        product_name, first_index
                    ].fix(1_000)
                    resources += 1

        assert block.zonal_resource_consumption_by_product[product_name, first_index].expr() == 1_000 * resources

    def test_zonal_plant_consumption_by_product(self, make_component_with_block_copy, first_index, last_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        product_name = "Product_1"
        total_num_products = 0

        for consuming_plant_linkage in zone.consuming_plants.values():
            plant = consuming_plant_linkage.plant
            if product_name in plant.consumed_products:
                plant.formulation_block.consumed_product_from_zone[product_name, first_index] = 100
                total_num_products += 1

        assert block.zonal_plant_consumption_by_product[product_name, first_index].expr() == 100 * total_num_products

        product_name = "CandidateFuel1"
        total_num_products = 0
        for consuming_plant_linkage in zone.consuming_plants.values():
            plant = consuming_plant_linkage.plant
            if product_name in plant.consumed_products:
                plant.formulation_block.consumed_product_from_zone[product_name, first_index] = 100
                total_num_products += 1

        assert block.zonal_plant_consumption_by_product[product_name, first_index].expr() == 100 * total_num_products

    def test_zonal_demand_consumption_by_product(self, make_component_with_block_copy, first_index, last_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        product_name = "Product_1"
        total_num_products = 0

        for consuming_demand_linkage in zone.consuming_demands.values():
            demand = consuming_demand_linkage.demand
            if product_name in demand.consumed_products:
                demand.formulation_block.consumption[product_name, first_index] = 100
                total_num_products += 1

        assert block.zonal_demand_production_by_product[product_name, first_index].expr() == 100 * total_num_products

        product_name = "CandidateFuel1"
        total_num_products = 0

        for consuming_demand_linkage in zone.consuming_demands.values():
            demand = consuming_demand_linkage.demand
            if product_name in demand.consumed_products:
                demand.formulation_block.consumption[product_name, first_index] = 100
                total_num_products += 1

        assert block.zonal_demand_production_by_product[product_name, first_index].expr() == 100 * total_num_products

    def test_zonal_consumption_by_product(self, make_component_with_block_copy, first_index, last_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block
        product_name = "Product_1"

        block.zonal_resource_consumption_by_product[product_name, first_index] = 1_235
        block.zonal_plant_consumption_by_product[product_name, first_index] = 280
        block.zonal_demand_consumption_by_product[product_name, first_index] = 764

        assert block.zonal_consumption_by_product[product_name, first_index].expr() == 1_235 + 280 + 764

        product_name = "CandidateFuel1"

        block.zonal_resource_consumption_by_product[product_name, last_index] = 1_235
        block.zonal_plant_consumption_by_product[product_name, last_index] = 280
        block.zonal_demand_consumption_by_product[product_name, last_index] = 764

        assert block.zonal_consumption_by_product[product_name, last_index].expr() == 1_235 + 280 + 764

    def test_zonal_sequestration_by_product(self, make_component_with_block_copy, first_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        product_name = "Pollutant1"
        seq_plant_1 = zone.sequestering_plants["Sequestration1"].plant
        seq_plant_1.formulation_block.produced_product_sequestered[product_name, first_index] = 100

        seq_plant_2 = zone.sequestering_plants["Sequestration2"].plant
        seq_plant_2.formulation_block.produced_product_sequestered[product_name, first_index] = 50

        assert block.zonal_sequestration_by_product[product_name, first_index].expr() == 150

    def test_zonal_net_imports_by_product(self, make_component_with_block_copy_zone_2, first_index, last_index):
        zone = make_component_with_block_copy_zone_2()
        block = zone.formulation_block

        for transportation in zone.transportation_instances_from_zone.values():
            transportation.formulation_block.net_transmit_product["Product_2", first_index] = -200

        assert block.zonal_net_imports_by_product["Product_2", first_index].expr() == 200 * 2

    def test_annual_total_operational_cost(self, make_custom_component_with_block, first_index, last_index):
        zone = make_custom_component_with_block(penalty_unserved_energy=15000, penalty_overgen=1000)
        block = zone.formulation_block

        modeled_year = first_index[0]
        total_operational_cost = 0
        for dispatch_window, timestamp in list(block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS):
            block.unserved_energy[modeled_year, dispatch_window, timestamp] = 10.0
            block.overgen[modeled_year, dispatch_window, timestamp] = 1.0

            block.unmet_demand[:, modeled_year, dispatch_window, timestamp] = 5.0
            block.overproduction[:, modeled_year, dispatch_window, timestamp] = 2.0
            total_operational_cost += (
                (
                    15_000
                    * 10.0
                    * block.model().dispatch_window_weights[dispatch_window]
                    * block.model().num_days_per_modeled_year[modeled_year]
                )
                + (
                    1_000
                    * 1.0
                    * block.model().dispatch_window_weights[dispatch_window]
                    * block.model().num_days_per_modeled_year[modeled_year]
                )
                + (
                    10_000
                    * 5.0
                    * block.model().dispatch_window_weights[dispatch_window]
                    * block.model().num_days_per_modeled_year[modeled_year]
                )
                * len(zone.non_electricity_products)
                + (
                    10_000
                    * 2.0
                    * block.model().dispatch_window_weights[dispatch_window]
                    * block.model().num_days_per_modeled_year[modeled_year]
                )
                * len(zone.non_electricity_products)
            )

        assert block.annual_total_operational_cost[modeled_year].expr() == total_operational_cost

    def test_zonal_power_balance_constraint(self, make_component_with_block_copy, first_index, last_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        block.zonal_provide_power[first_index] = 10_000
        block.zonal_increase_load[first_index] = 9_000
        block.input_load[first_index] = 2_000
        block.zonal_net_imports[first_index] = 1_000
        block.overgen[first_index].fix(0)
        block.unserved_energy[first_index].fix(0)

        assert block.zonal_power_balance_constraint[first_index].body() == 0
        assert block.zonal_power_balance_constraint[first_index].lower() == 0
        assert block.zonal_power_balance_constraint[first_index].upper() == 0
        assert block.zonal_power_balance_constraint[first_index].expr()

        block.zonal_provide_power[last_index] = 10
        block.zonal_increase_load[last_index] = 2_300
        block.input_load[last_index] = 1_000
        block.zonal_net_imports[last_index] = 2_000
        block.overgen[last_index].fix(1_500)
        block.unserved_energy[last_index].fix(10_000)

        assert block.zonal_power_balance_constraint[last_index].body() == 10_000 + 2_000 + 10 - 1_500 - 1_000 - 2_300
        assert not block.zonal_power_balance_constraint[last_index].expr()

    def test_zonal_flow_balance_by_product_constraint(self, make_component_with_block_copy, first_index, last_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        product = "Product_1"
        block.zonal_production_by_product[product, first_index] = 10
        block.zonal_net_imports_by_product[product, first_index] = 10
        block.unmet_demand[product, first_index].fix(10)
        block.zonal_consumption_by_product[product, first_index] = 15
        block.overproduction[product, first_index].fix(15)

        assert block.zonal_flow_balance_by_product[product, first_index].body() == 0
        assert block.zonal_flow_balance_by_product[product, first_index].lower() == 0
        assert block.zonal_flow_balance_by_product[product, first_index].upper() == 0
        assert block.zonal_flow_balance_by_product[product, first_index].expr()

        block.overproduction[product, first_index].fix(10)
        assert not block.zonal_flow_balance_by_product[product, first_index].expr()

        # Test that commodity products do not have the zonal flow balance constraint defined
        with pytest.raises(KeyError):
            assert not any(
                block.zonal_flow_balance_by_product[product_name, first_index]
                for product_name, linkage in zone.products.items()
                if linkage.product.commodity
            )

    def test_hourly_energy_prices_weighted(self, make_component_with_block_copy, first_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        for year in block.model().MODELED_YEARS:
            for dispatch_window, timestamp in block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS:
                block.zonal_power_balance_constraint[year, dispatch_window, timestamp].set_suffix_value("dual", 10)

        zone._construct_output_expressions(construct_costs=True)

        for year in block.model().MODELED_YEARS:
            for dispatch_window, timestamp in block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS:
                assert block.hourly_energy_prices_weighted[year, dispatch_window, timestamp].expr() == 10

    def test_hourly_energy_prices_unweighted(self, make_component_with_block_copy, first_index):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        for year in block.model().MODELED_YEARS:
            for dispatch_window, timestamp in block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS:
                block.zonal_power_balance_constraint[year, dispatch_window, timestamp].set_suffix_value("dual", 10)

        zone._construct_output_expressions(construct_costs=True)

        for year in block.model().MODELED_YEARS:
            for dispatch_window, timestamp in block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS:
                assert block.hourly_energy_prices_unweighted[year, dispatch_window, timestamp].expr() == (
                    10
                    / block.model().temporal_settings.modeled_year_discount_factors.data.at[year]
                    / block.model().num_days_per_modeled_year[year]
                    / block.model().temporal_settings.dispatch_window_weights.at[dispatch_window]
                    / block.model().timestamp_durations_hours[dispatch_window, timestamp]
                )

    def test_hourly_energy_prices_per_product_weighted_and_unweighted(
        self, make_component_with_block_copy, first_index
    ):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        for product_linkage in zone.non_electricity_products.values():
            product = product_linkage.instance_to
            product_name = product.name
            if not product.commodity:
                for year in block.model().MODELED_YEARS:
                    for dispatch_window, timestamp in block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS:
                        block.zonal_flow_balance_by_product[
                            product_name, year, dispatch_window, timestamp
                        ].set_suffix_value("dual", 10)

        zone._construct_output_expressions(construct_costs=True)

        for product_linkage in zone.non_electricity_products.values():
            product = product_linkage.instance_to
            product_name = product.name
            for year in block.model().MODELED_YEARS:
                for dispatch_window, timestamp in block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS:
                    if product.commodity:
                        assert (
                            block.hourly_energy_prices_by_product_weighted[
                                product_name, year, dispatch_window, timestamp
                            ].expr()
                            == 3.0
                            * block.model().temporal_settings.modeled_year_discount_factors.data.at[year]
                            * block.model().num_days_per_modeled_year[year]
                            * block.model().temporal_settings.dispatch_window_weights.at[dispatch_window]
                            * block.model().timestamp_durations_hours[dispatch_window, timestamp]
                        )
                        assert (
                            block.hourly_energy_prices_by_product_unweighted[
                                product_name, year, dispatch_window, timestamp
                            ].expr()
                            == 3.0
                        )
                    else:
                        assert (
                            block.hourly_energy_prices_by_product_weighted[
                                product_name, year, dispatch_window, timestamp
                            ].expr()
                            == 10
                        )
                        assert block.hourly_energy_prices_by_product_unweighted[
                            product_name, year, dispatch_window, timestamp
                        ].expr() == (
                            10
                            / block.model().temporal_settings.modeled_year_discount_factors.data.at[year]
                            / block.model().num_days_per_modeled_year[year]
                            / block.model().temporal_settings.dispatch_window_weights.at[dispatch_window]
                            / block.model().timestamp_durations_hours[dispatch_window, timestamp]
                        )

    def test_results_reporting(self, make_component_with_block_copy):
        zone = make_component_with_block_copy()
        block = zone.formulation_block

        for year in block.model().MODELED_YEARS:
            for dispatch_window, timestamp in block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS:
                block.zonal_power_balance_constraint[year, dispatch_window, timestamp].set_suffix_value("dual", 10)

        zone._construct_output_expressions(construct_costs=True)

        assert block.hourly_energy_prices_unweighted.doc == "Hourly Energy Price Unweighted ($/MWh)"
        assert block.hourly_energy_prices_weighted.doc == "Hourly Energy Price Weighted ($/MWh)"

        assert block.annual_unserved_energy.doc == "Annual Unserved Energy (MWh)"
        assert block.annual_overgen.doc == "Annual Overgeneration (MWh)"
        assert block.annual_overproduction.doc == "Annual Overproduction (Product Units)"
        assert block.annual_zonal_production_by_product.doc == "Annual Zonal Production (Product Units)"
        assert block.annual_zonal_consumption_by_product.doc == "Annual Zonal Consumption (Product Units)"
        assert block.annual_zonal_sequestration_by_product.doc == "Annual Zonal Sequestration (Product Units)"
        assert block.annual_zonal_net_imports_by_product.doc == "Annual Zonal Net Imports (Product Units)"
        assert block.annual_zonal_net_release_by_product.doc == "Annual Zonal Net Release (Product Units)"
        assert block.annual_provide_power.doc == "Provide Power (MWh)"
        assert block.annual_input_load.doc == "Input Load (MWh)"
        assert block.annual_increase_load.doc == "Increase Load (MWh)"
        assert block.annual_gross_imports.doc == "Gross Imports (MWh)"
        assert block.annual_gross_exports.doc == "Gross Exports (MWh)"
        assert block.annual_net_imports.doc == "Net Imports (MWh)"
        assert block.curtailment.doc == "Curtailment (MW)"
        assert block.annual_curtailment.doc == "Total Annual Curtailment (MWh)"
