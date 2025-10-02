from new_modeling_toolkit.system.electric.tx_path import TxPath
from new_modeling_toolkit.system.electric.tx_path import TxPathGroup
from tests.system import test_asset


class TestTxPath(test_asset.TestAsset):
    _COMPONENT_CLASS = TxPath
    _COMPONENT_NAME = "TxPath"
    _SYSTEM_COMPONENT_DICT_NAME = "tx_paths"

    def test_transmission_max_flow_constraint(self, make_component_with_block_copy, first_index, last_index):
        tx_path = make_component_with_block_copy()
        block = tx_path.formulation_block
        planned_capacity = tx_path.planned_capacity.data.at[first_index[0]]

        # check first index: body = upper bound
        modeled_year, dispatch_window, timestamp = first_index
        forward_rating_profile = tx_path.forward_rating_profile.data.at[timestamp]
        power_flow_forward = 200
        power_flow_reverse = 0
        net_power_flow = power_flow_forward - power_flow_reverse
        capacity_selected = 100
        capacity_retired = 0
        block.transmit_power_forward[first_index].fix(power_flow_forward)
        block.transmit_power_reverse[first_index].fix(power_flow_reverse)
        block.selected_capacity.fix(capacity_selected)
        block.retired_capacity[modeled_year].fix(capacity_retired)
        assert (
            block.transmission_max_flow_constraint[first_index].body()
            == net_power_flow - (planned_capacity + capacity_selected - capacity_retired) * forward_rating_profile
        )  # body = 0
        assert block.transmission_max_flow_constraint[first_index].upper() == 0
        assert block.transmission_max_flow_constraint[first_index].expr()

        # check first index: body < upper bound
        power_flow_forward = 100
        capacity_selected = 100
        capacity_retired = 0
        block.transmit_power_forward[first_index].fix(power_flow_forward)
        block.transmit_power_reverse[first_index].fix(power_flow_reverse)
        block.selected_capacity.fix(capacity_selected)
        block.retired_capacity[modeled_year].fix(capacity_retired)
        assert (
            block.transmission_max_flow_constraint[first_index].body()
            == power_flow_forward - (planned_capacity + capacity_selected - capacity_retired) * forward_rating_profile
        )  # body < 0
        assert block.transmission_max_flow_constraint[first_index].upper() == 0
        assert block.transmission_max_flow_constraint[first_index].expr()

        # check last index: body > upper bound
        modeled_year, dispatch_window, timestamp = last_index
        forward_rating_profile = tx_path.forward_rating_profile.data.at[timestamp]
        power_flow_forward = 200
        capacity_selected = 200
        capacity_retired = 200
        block.transmit_power_forward[last_index].fix(power_flow_forward)
        block.transmit_power_reverse[last_index].fix(power_flow_reverse)
        block.selected_capacity.fix(capacity_selected)
        block.retired_capacity[modeled_year].fix(capacity_retired)
        assert (
            block.transmission_max_flow_constraint[last_index].body()
            == power_flow_forward - (planned_capacity + capacity_selected - capacity_retired) * forward_rating_profile
        )  # body > 0
        assert block.transmission_max_flow_constraint[last_index].upper() == 0
        assert not block.transmission_max_flow_constraint[last_index].expr()

    def test_transmission_min_flow_constraint(self, make_component_with_block_copy, first_index, last_index):
        tx_path = make_component_with_block_copy()
        block = tx_path.formulation_block
        planned_capacity = tx_path.planned_capacity.data.at[first_index[0]]

        # check first index: body = upper bound
        modeled_year, dispatch_window, timestamp = first_index
        reverse_rating_profile = tx_path.forward_rating_profile.data.at[timestamp]
        power_flow_reverse = 200
        capacity_selected = 100
        capacity_retired = 0
        block.transmit_power_reverse[first_index].fix(power_flow_reverse)
        block.selected_capacity.fix(capacity_selected)
        block.retired_capacity[modeled_year].fix(capacity_retired)
        assert (
            block.transmission_min_flow_constraint[first_index].body()
            == power_flow_reverse - (planned_capacity + capacity_selected - capacity_retired) * reverse_rating_profile
        )  # body = 0
        assert block.transmission_min_flow_constraint[first_index].upper() == 0
        assert block.transmission_min_flow_constraint[first_index].expr()

        # check first index: body < upper bound
        power_flow_reverse = 200
        capacity_selected = 200
        capacity_retired = 0
        block.transmit_power_reverse[first_index].fix(power_flow_reverse)
        block.selected_capacity.fix(capacity_selected)
        block.retired_capacity[modeled_year].fix(capacity_retired)
        assert (
            block.transmission_min_flow_constraint[first_index].body()
            == power_flow_reverse - (planned_capacity + capacity_selected - capacity_retired) * reverse_rating_profile
        )  # body < 0
        assert block.transmission_min_flow_constraint[first_index].upper() == 0
        assert block.transmission_min_flow_constraint[first_index].expr()

        # check last index: body > upper bound
        modeled_year, dispatch_window, timestamp = last_index
        reverse_rating_profile = tx_path.forward_rating_profile.data.at[timestamp]
        power_flow_reverse = 200
        capacity_selected = 200
        capacity_retired = 200
        block.transmit_power_reverse[last_index].fix(power_flow_reverse)
        block.selected_capacity.fix(capacity_selected)
        block.retired_capacity[modeled_year].fix(capacity_retired)
        assert (
            block.transmission_min_flow_constraint[last_index].body()
            == power_flow_reverse - (planned_capacity + capacity_selected - capacity_retired) * reverse_rating_profile
        )  # body > 0
        assert block.transmission_min_flow_constraint[last_index].upper() == 0
        assert not block.transmission_min_flow_constraint[last_index].expr()

    def test_transmission_mileage_constraint(self, make_component_with_block_copy, first_index, last_index):
        tx_path = make_component_with_block_copy()
        block = tx_path.formulation_block
        planned_capacity = tx_path.planned_capacity.data.at[first_index[0]]

        # first index: body = upper bound
        modeled_year, dispatch_window, timestamp = first_index
        forward_rating_profile = tx_path.forward_rating_profile.data.at[timestamp]
        reverse_rating_profile = tx_path.reverse_rating_profile.data.at[timestamp]
        power_flow_forward = 0
        power_flow_reverse = 200
        capacity_selected = 100
        capacity_retired = 0
        block.transmit_power_forward[first_index].fix(power_flow_forward)
        block.transmit_power_reverse[first_index].fix(power_flow_reverse)
        block.selected_capacity.fix(capacity_selected)
        block.retired_capacity[modeled_year].fix(capacity_retired)
        assert block.transmission_mileage_constraint[first_index].body() == power_flow_forward + power_flow_reverse - (
            (planned_capacity + capacity_selected - capacity_retired)
            * max(forward_rating_profile, reverse_rating_profile)
        )
        assert block.transmission_mileage_constraint[first_index].upper() == 0
        assert block.transmission_mileage_constraint[first_index].expr()

        # first index: body < upper bound
        modeled_year, dispatch_window, timestamp = first_index
        forward_rating_profile = tx_path.forward_rating_profile.data.at[timestamp]
        reverse_rating_profile = tx_path.reverse_rating_profile.data.at[timestamp]
        power_flow_forward = 100
        power_flow_reverse = 0
        capacity_selected = 100
        capacity_retired = 0
        block.transmit_power_forward[first_index].fix(power_flow_forward)
        block.transmit_power_reverse[first_index].fix(power_flow_reverse)
        block.selected_capacity.fix(capacity_selected)
        block.retired_capacity[modeled_year].fix(capacity_retired)
        assert block.transmission_mileage_constraint[first_index].body() == power_flow_forward + power_flow_reverse - (
            (planned_capacity + capacity_selected - capacity_retired)
            * max(forward_rating_profile, reverse_rating_profile)
        )
        assert block.transmission_mileage_constraint[first_index].upper() == 0
        assert block.transmission_mileage_constraint[first_index].expr()

        # last index: body > upper bound
        modeled_year, dispatch_window, timestamp = last_index
        forward_rating_profile = tx_path.forward_rating_profile.data.at[timestamp]
        reverse_rating_profile = tx_path.reverse_rating_profile.data.at[timestamp]
        power_flow_forward = 100
        power_flow_reverse = 200
        capacity_selected = 100
        capacity_retired = 0
        block.transmit_power_forward[last_index].fix(power_flow_forward)
        block.transmit_power_reverse[last_index].fix(power_flow_reverse)
        block.selected_capacity.fix(capacity_selected)
        block.retired_capacity[modeled_year].fix(capacity_retired)
        assert block.transmission_mileage_constraint[last_index].body() == power_flow_forward + power_flow_reverse - (
            (planned_capacity + capacity_selected - capacity_retired)
            * max(forward_rating_profile, reverse_rating_profile)
        )
        assert block.transmission_mileage_constraint[last_index].upper() == 0
        assert not block.transmission_mileage_constraint[last_index].expr()

    def test_annual_total_operational_cost(self, make_component_with_block_copy, first_index, last_index):
        tx_path = make_component_with_block_copy()
        block = tx_path.formulation_block

        # first model year: all forward flows
        modeled_year = first_index[0]
        total_operational_cost = 0
        for dispatch_window, timestamp in list(block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS):
            block.transmit_power_forward[modeled_year, dispatch_window, timestamp].fix(200)
            block.transmit_power_reverse[modeled_year, dispatch_window, timestamp].fix(0)
            total_operational_cost += (
                block.tx_hurdle_cost_forward[modeled_year, dispatch_window, timestamp].expr()
                * block.model().dispatch_window_weights[dispatch_window]
                * block.model().num_days_per_modeled_year[modeled_year]
            )

        assert block.annual_total_operational_cost[modeled_year].expr() == total_operational_cost

        # last model year: some forward flows, some reverse flows
        modeled_year = last_index[0]
        total_operational_cost = 0
        counter = 0
        for dispatch_window, timestamp in list(block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS):
            if counter % 2 == 0:
                block.transmit_power_forward[modeled_year, dispatch_window, timestamp].fix(200)
                block.transmit_power_reverse[modeled_year, dispatch_window, timestamp].fix(0)
            else:
                block.transmit_power_forward[modeled_year, dispatch_window, timestamp].fix(0)
                block.transmit_power_reverse[modeled_year, dispatch_window, timestamp].fix(300)
            total_operational_cost += (
                block.tx_hurdle_cost_forward[modeled_year, dispatch_window, timestamp].expr()
                * block.model().dispatch_window_weights[dispatch_window]
                * block.model().num_days_per_modeled_year[modeled_year]
            ) + (
                block.tx_hurdle_cost_reverse[modeled_year, dispatch_window, timestamp].expr()
                * block.model().dispatch_window_weights[dispatch_window]
                * block.model().num_days_per_modeled_year[modeled_year]
            )
            counter += 1

        assert block.annual_total_operational_cost[modeled_year].expr() == total_operational_cost

    def test_results_reporting(self, make_component_with_block_copy):
        tx_path = make_component_with_block_copy()
        block = tx_path.formulation_block

        tx_path._construct_output_expressions(construct_costs=True)

        assert block.to_zone.doc == "Zone To"
        assert block.from_zone.doc == "Zone From"
        assert block.max_forward_capacity.doc == "Max Forward Capacity (MW)"
        assert block.max_reverse_capacity.doc == "Max Reverse Capacity (MW)"
        assert block.annual_gross_forward_flow.doc == "Gross Forward Flow (MWh)"
        assert block.annual_gross_reverse_flow.doc == "Gross Reverse Flow (MWh)"
        assert block.annual_net_forward_flow.doc == "Net Forward Flow (MWh)"
        assert block.annual_forward_hurdle_cost.doc == "Forward Hurdle Cost ($)"
        assert block.annual_reverse_hurdle_cost.doc == "Reverse Hurdle Cost ($)"

        if hasattr(tx_path.to_zone.instance_from.formulation_block, "hourly_energy_prices_weighted"):
            assert block.annual_forward_flow_value_to_zone.doc == "Forward Flow Value (To Zone) ($)"
            assert block.annual_reverse_flow_value_to_zone.doc == "Reverse Flow Value (To Zone) ($)"

        if hasattr(tx_path.from_zone.instance_from.formulation_block, "hourly_energy_prices_weighted"):
            assert block.annual_forward_flow_value_from_zone.doc == "Forward Flow Value (From Zone) ($)"
            assert block.annual_reverse_flow_value_from_zone.doc == "Reverse Flow Value (From Zone) ($)"


class TestTxPathGroup(test_asset.TestAssetGroup, TestTxPath):
    _COMPONENT_CLASS = TxPathGroup
    _COMPONENT_NAME = "tx_path_group_0"
    _SYSTEM_COMPONENT_DICT_NAME = "tx_path_groups"

    def test_transmission_max_flow_constraint(self, make_component_with_block_copy, first_index, last_index):
        tx_path_group = make_component_with_block_copy()
        block = tx_path_group.formulation_block
        planned_capacity = tx_path_group.planned_capacity.data.at[first_index[0]]

        # check first index: body = upper bound
        modeled_year, dispatch_window, timestamp = first_index
        forward_rating_profile = tx_path_group.forward_rating_profile.data.at[timestamp]
        power_flow_forward = 200
        power_flow_reverse = 0
        net_power_flow = power_flow_forward - power_flow_reverse
        capacity_selected = 100
        capacity_retired = 0
        block.transmit_power_forward[first_index].fix(power_flow_forward)
        block.transmit_power_reverse[first_index].fix(power_flow_reverse)
        block.operational_capacity[modeled_year].fix(planned_capacity + capacity_selected - capacity_retired)
        assert (
            block.transmission_max_flow_constraint[first_index].body()
            == net_power_flow - (planned_capacity + capacity_selected - capacity_retired) * forward_rating_profile
        )  # body = 0
        assert block.transmission_max_flow_constraint[first_index].upper() == 0
        assert block.transmission_max_flow_constraint[first_index].expr()

        # check first index: body < upper bound
        power_flow_forward = 100
        capacity_selected = 100
        capacity_retired = 0
        block.transmit_power_forward[first_index].fix(power_flow_forward)
        block.transmit_power_reverse[first_index].fix(power_flow_reverse)
        block.operational_capacity[modeled_year].fix(planned_capacity + capacity_selected - capacity_retired)
        assert (
            block.transmission_max_flow_constraint[first_index].body()
            == power_flow_forward - (planned_capacity + capacity_selected - capacity_retired) * forward_rating_profile
        )  # body < 0
        assert block.transmission_max_flow_constraint[first_index].upper() == 0
        assert block.transmission_max_flow_constraint[first_index].expr()

        # check last index: body > upper bound
        modeled_year, dispatch_window, timestamp = last_index
        forward_rating_profile = tx_path_group.forward_rating_profile.data.at[timestamp]
        power_flow_forward = 200
        capacity_selected = 200
        capacity_retired = 200
        block.transmit_power_forward[last_index].fix(power_flow_forward)
        block.transmit_power_reverse[last_index].fix(power_flow_reverse)
        block.operational_capacity[modeled_year].fix(planned_capacity + capacity_selected - capacity_retired)
        assert (
            block.transmission_max_flow_constraint[last_index].body()
            == power_flow_forward - (planned_capacity + capacity_selected - capacity_retired) * forward_rating_profile
        )  # body = 100
        assert block.transmission_max_flow_constraint[last_index].upper() == 0
        assert not block.transmission_max_flow_constraint[last_index].expr()

    def test_transmission_min_flow_constraint(self, make_component_with_block_copy, first_index, last_index):
        tx_path = make_component_with_block_copy()
        block = tx_path.formulation_block
        planned_capacity = tx_path.planned_capacity.data.at[first_index[0]]

        # check first index: body = upper bound
        modeled_year, dispatch_window, timestamp = first_index
        reverse_rating_profile = tx_path.forward_rating_profile.data.at[timestamp]
        power_flow_reverse = 200
        capacity_selected = 100
        capacity_retired = 0
        block.transmit_power_reverse[first_index].fix(power_flow_reverse)
        block.operational_capacity.fix(planned_capacity + capacity_selected - capacity_retired)
        assert (
            block.transmission_min_flow_constraint[first_index].body()
            == power_flow_reverse - (planned_capacity + capacity_selected - capacity_retired) * reverse_rating_profile
        )  # body = 0
        assert block.transmission_min_flow_constraint[first_index].upper() == 0
        assert block.transmission_min_flow_constraint[first_index].expr()

        # check first index: body < upper bound
        power_flow_reverse = 200
        capacity_selected = 200
        capacity_retired = 0
        block.transmit_power_reverse[first_index].fix(power_flow_reverse)
        block.operational_capacity.fix(planned_capacity + capacity_selected - capacity_retired)
        assert (
            block.transmission_min_flow_constraint[first_index].body()
            == power_flow_reverse - (planned_capacity + capacity_selected - capacity_retired) * reverse_rating_profile
        )  # body < 0
        assert block.transmission_min_flow_constraint[first_index].upper() == 0
        assert block.transmission_min_flow_constraint[first_index].expr()

        # check last index: body > upper bound
        modeled_year, dispatch_window, timestamp = last_index
        reverse_rating_profile = tx_path.forward_rating_profile.data.at[timestamp]
        power_flow_reverse = 200
        capacity_selected = 200
        capacity_retired = 200
        block.transmit_power_reverse[last_index].fix(power_flow_reverse)
        block.operational_capacity.fix(planned_capacity + capacity_selected - capacity_retired)
        assert (
            block.transmission_min_flow_constraint[last_index].body()
            == power_flow_reverse - (planned_capacity + capacity_selected - capacity_retired) * reverse_rating_profile
        )  # body > 0
        assert block.transmission_min_flow_constraint[last_index].upper() == 0
        assert not block.transmission_min_flow_constraint[last_index].expr()

    def test_transmission_mileage_constraint(self, make_component_with_block_copy, first_index, last_index):
        tx_path = make_component_with_block_copy()
        block = tx_path.formulation_block
        planned_capacity = tx_path.planned_capacity.data.at[first_index[0]]

        # first index: body = upper bound
        modeled_year, dispatch_window, timestamp = first_index
        forward_rating_profile = tx_path.forward_rating_profile.data.at[timestamp]
        reverse_rating_profile = tx_path.reverse_rating_profile.data.at[timestamp]
        power_flow_forward = 0
        power_flow_reverse = 200
        capacity_selected = 100
        capacity_retired = 0
        block.transmit_power_forward[first_index].fix(power_flow_forward)
        block.transmit_power_reverse[first_index].fix(power_flow_reverse)
        block.operational_capacity.fix(planned_capacity + capacity_selected - capacity_retired)
        assert block.transmission_mileage_constraint[first_index].body() == power_flow_forward + power_flow_reverse - (
            (planned_capacity + capacity_selected - capacity_retired)
            * max(forward_rating_profile, reverse_rating_profile)
        )
        assert block.transmission_mileage_constraint[first_index].upper() == 0
        assert block.transmission_mileage_constraint[first_index].expr()

        # first index: body < upper bound
        modeled_year, dispatch_window, timestamp = first_index
        forward_rating_profile = tx_path.forward_rating_profile.data.at[timestamp]
        reverse_rating_profile = tx_path.reverse_rating_profile.data.at[timestamp]
        power_flow_forward = 100
        power_flow_reverse = 0
        capacity_selected = 100
        capacity_retired = 0
        block.transmit_power_forward[first_index].fix(power_flow_forward)
        block.transmit_power_reverse[first_index].fix(power_flow_reverse)
        block.operational_capacity.fix(planned_capacity + capacity_selected - capacity_retired)
        assert block.transmission_mileage_constraint[first_index].body() == power_flow_forward + power_flow_reverse - (
            (planned_capacity + capacity_selected - capacity_retired)
            * max(forward_rating_profile, reverse_rating_profile)
        )
        assert block.transmission_mileage_constraint[first_index].upper() == 0
        assert block.transmission_mileage_constraint[first_index].expr()

        # last index: body > upper bound
        modeled_year, dispatch_window, timestamp = last_index
        forward_rating_profile = tx_path.forward_rating_profile.data.at[timestamp]
        reverse_rating_profile = tx_path.reverse_rating_profile.data.at[timestamp]
        power_flow_forward = 100
        power_flow_reverse = 200
        capacity_selected = 100
        capacity_retired = 0
        block.transmit_power_forward[last_index].fix(power_flow_forward)
        block.transmit_power_reverse[last_index].fix(power_flow_reverse)
        block.operational_capacity.fix(planned_capacity + capacity_selected - capacity_retired)
        assert block.transmission_mileage_constraint[last_index].body() == power_flow_forward + power_flow_reverse - (
            (planned_capacity + capacity_selected - capacity_retired)
            * max(forward_rating_profile, reverse_rating_profile)
        )
        assert block.transmission_mileage_constraint[last_index].upper() == 0
        assert not block.transmission_mileage_constraint[last_index].expr()
