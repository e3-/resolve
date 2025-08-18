import pytest

from tests.system.electric.resources import test_shed_dr


@pytest.mark.skip(reason=(f"Unit testing for FlexLoadResources is not yet implemented."))
class TestFlexLoadResource(test_shed_dr.TestShedDrResource):
    # TODO: uncomment and edit for RESOLVE refactor
    """
    _COMPONENT_CLASS = FlexLoadResource
    _COMPONENT_NAME = "FlexLoadResource1"
    _SYSTEM_COMPONENT_DICT_NAME = "flex_load_resources"
    """

    @pytest.mark.parametrize(
        "committed_units, committed_capacity",
        [
            (0, 0),
            (1, 50.0),
            (2, 100.0),
        ],
    )
    def test_committed_capacity_mw_power_output(
        self, make_component_with_block_copy, first_index, committed_units, committed_capacity
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block

        resource_block.committed_units_power_output[first_index].fix(committed_units)
        assert resource_block.committed_capacity_mw_power_output[first_index].expr() == committed_capacity

    @pytest.mark.parametrize(
        "committed_units_first, committed_units_next, start_units_next, shutdown_units_next, commitment_tracking_upper, commitment_tracking_lower, commitment_tracking_body, expr",
        [
            (0, 0, 1, 0, 0.0, 0.0, -1.0, False),
            (0, 1, 1, 0, 0.0, 0.0, 0.0, True),
            (0, 0, 1, 1, 0.0, 0.0, 0.0, True),
            (1, 1, 0, 0, 0.0, 0.0, 0.0, True),
            (1, 0, 0, 1, 0.0, 0.0, 0.0, True),
            (1, 1, 1, 1, 0.0, 0.0, 0.0, True),
            (0, 1, 1, 1, 0.0, 0.0, 1.0, False),
        ],
    )
    def test_commitment_power_output_tracking_constraint(
        self,
        make_component_with_block_copy,
        first_index,
        committed_units_first,
        committed_units_next,
        start_units_next,
        shutdown_units_next,
        commitment_tracking_upper,
        commitment_tracking_lower,
        commitment_tracking_body,
        expr,
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index
        next_index = (modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=1))
        resource_block.committed_units_power_output[first_index].fix(committed_units_first)
        resource_block.committed_units_power_output[next_index].fix(committed_units_next)
        resource_block.start_units_power_output[next_index].fix(start_units_next)
        resource_block.shutdown_units_power_output[next_index].fix(shutdown_units_next)
        assert (
            resource_block.commitment_power_output_tracking_constraint[first_index].upper() == commitment_tracking_upper
        )
        assert (
            resource_block.commitment_power_output_tracking_constraint[first_index].lower() == commitment_tracking_lower
        )
        assert (
            resource_block.commitment_power_output_tracking_constraint[first_index].body() == commitment_tracking_body
        )
        assert resource_block.commitment_power_output_tracking_constraint[first_index].expr() == expr

    @pytest.mark.parametrize(
        "committed_units, increase_load_capacity",
        [
            (0, 0),
            (1, 25.0),
            (2, 50.0),
        ],
    )
    def test_power_input_max(
        self, make_component_with_block_copy, first_index, committed_units, increase_load_capacity
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block

        resource_block.committed_units[first_index].fix(committed_units)
        assert resource_block.power_input_max[first_index].expr() == increase_load_capacity

    def test_power_input_max_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        block.committed_units.fix(4)
        modeled_year, dispatch_window_id, timestamp = first_index

        block.operational_capacity[modeled_year] = 200

        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(80.0)
        assert (
            block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].body()
            == -20  # 80 - 0.5 * 200
        )
        assert block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(250.0)
        assert (
            block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].body() == 150
        )  # 250 - 0.5*200
        assert block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert not block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(0.0)
        assert block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].body() == 0 - 0.5 * 200
        assert block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.power_input_max_constraint[modeled_year, dispatch_window_id, timestamp].expr()

    def test_power_input_min_constraint(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        block.committed_units.fix(4)
        modeled_year, dispatch_window_id, timestamp = first_index

        assert resource.planned_capacity == 100
        block.selected_capacity.fix(100)
        block.retired_capacity.fix(0)

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(160.0)
        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(120.0)
        block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window_id, timestamp].fix(30.0)
        assert block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].body() == 0.1 * 200 - 120
        assert block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(30.0)
        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(10.0)
        block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window_id, timestamp].fix(30.0)
        assert block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].body() == 0.1 * 200 - 10
        assert not block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].expr()

        block.power_output[modeled_year, dispatch_window_id, timestamp].fix(0.0)
        block.power_input[modeled_year, dispatch_window_id, timestamp].fix(0.0)
        block.provide_reserve["TestRegulationUp", modeled_year, dispatch_window_id, timestamp].fix(30.0)
        assert block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].upper() == 0
        assert block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].body() == 0.1 * 200 - 0
        assert not block.power_input_min_constraint[modeled_year, dispatch_window_id, timestamp].expr()

    @pytest.mark.parametrize(
        "committed_units, committed_capacity",
        [
            (0, 0),
            (1, 50.0),
            (2, 100.0),
        ],
    )
    def test_committed_capacity_mw_power_output(
        self, make_component_with_block_copy, first_index, committed_units, committed_capacity
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block

        resource_block.committed_units_power_output[first_index].fix(committed_units)
        assert resource_block.committed_capacity_mw_power_output[first_index].expr() == committed_capacity

    @pytest.mark.parametrize(
        "committed_units_first, committed_units_next, start_units_next, shutdown_units_next, commitment_tracking_upper, commitment_tracking_lower, commitment_tracking_body, expr",
        [
            (0, 0, 1, 0, 0.0, 0.0, -1.0, False),
            (0, 1, 1, 0, 0.0, 0.0, 0.0, True),
            (0, 0, 1, 1, 0.0, 0.0, 0.0, True),
            (1, 1, 0, 0, 0.0, 0.0, 0.0, True),
            (1, 0, 0, 1, 0.0, 0.0, 0.0, True),
            (1, 1, 1, 1, 0.0, 0.0, 0.0, True),
            (0, 1, 1, 1, 0.0, 0.0, 1.0, False),
        ],
    )
    def test_commitment_power_output_tracking_constraint(
        self,
        make_component_with_block_copy,
        first_index,
        committed_units_first,
        committed_units_next,
        start_units_next,
        shutdown_units_next,
        commitment_tracking_upper,
        commitment_tracking_lower,
        commitment_tracking_body,
        expr,
    ):
        resource = make_component_with_block_copy()
        resource_block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index
        next_index = (modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=1))
        resource_block.committed_units_power_output[first_index].fix(committed_units_first)
        resource_block.committed_units_power_output[next_index].fix(committed_units_next)
        resource_block.start_units_power_output[next_index].fix(start_units_next)
        resource_block.shutdown_units_power_output[next_index].fix(shutdown_units_next)
        assert (
            resource_block.commitment_power_output_tracking_constraint[first_index].upper() == commitment_tracking_upper
        )
        assert (
            resource_block.commitment_power_output_tracking_constraint[first_index].lower() == commitment_tracking_lower
        )
        assert (
            resource_block.commitment_power_output_tracking_constraint[first_index].body() == commitment_tracking_body
        )
        assert resource_block.commitment_power_output_tracking_constraint[first_index].expr() == expr

    # TODO: re-write these tests for RESOLVE Refactor
    """
    def test_increase_adjacency_constraint(self, resource_block, first_index):
        resource_block = copy.deepcopy(resource_block)
        modeled_year, dispatch_window, timestamp = first_index
        resource_block.start_units.fix(0)
        timestamp = timestamp + pd.DateOffset(hours=5)

        resource_block.committed_units[modeled_year, dispatch_window, timestamp].fix(1)
        assert resource_block.adjacency_constraint[modeled_year, dispatch_window, timestamp].body() == 1
        assert resource_block.adjacency_constraint[modeled_year, dispatch_window, timestamp].upper() == 0
        assert not resource_block.adjacency_constraint[modeled_year, dispatch_window, timestamp].expr()

        resource_block.start_units[modeled_year, dispatch_window, timestamp - pd.DateOffset(hours=2)].fix(1)
        assert resource_block.adjacency_constraint[modeled_year, dispatch_window, timestamp].body() == 0
        assert resource_block.adjacency_constraint[modeled_year, dispatch_window, timestamp].upper() == 0
        assert resource_block.adjacency_constraint[modeled_year, dispatch_window, timestamp].expr()

        resource_block.start_units[modeled_year, dispatch_window, timestamp - pd.DateOffset(hours=3)].fix(1)
        assert resource_block.adjacency_constraint[modeled_year, dispatch_window, timestamp].body() == -1
        assert resource_block.adjacency_constraint[modeled_year, dispatch_window, timestamp].upper() == 0
        assert resource_block.adjacency_constraint[modeled_year, dispatch_window, timestamp].expr()

    def test_energy_balance_committed_units_constraint_pre_consumption(self, resource_block, first_index):
        resource_block = copy.deepcopy(resource_block)
        # initial soc is 0
        resource_block.committed_units[first_index].fix(0)
        resource_block.state_of_charge[first_index].fix(0.5)

        assert not resource_block.energy_balance_committed_units_constraint[first_index].expr()
        assert resource_block.energy_balance_committed_units_constraint[first_index].body() == 0.5
        assert resource_block.energy_balance_committed_units_constraint[first_index].upper() == 0.0

        resource_block.committed_units[first_index].fix(1)
        assert resource_block.energy_balance_committed_units_constraint[first_index].expr()
        assert resource_block.energy_balance_committed_units_constraint[first_index].body() == -1999.5
        assert resource_block.energy_balance_committed_units_constraint[first_index].upper() == 0

    def test_energy_balance_committed_units_constraint_deferred_consumption(
        self, resource_block_deferred_consumption, first_index
    ):
        resource_block = copy.deepcopy(resource_block_deferred_consumption)
        # initial soc is 5
        resource_block.committed_units[first_index].fix(0)
        resource_block.state_of_charge[first_index].fix(5.5)

        assert not resource_block.energy_balance_committed_units_constraint[first_index].expr()
        assert resource_block.energy_balance_committed_units_constraint[first_index].body() == 0.5
        assert resource_block.energy_balance_committed_units_constraint[first_index].upper() == 0.0

        resource_block.committed_units[first_index].fix(1)
        assert resource_block.energy_balance_committed_units_constraint[first_index].expr()
        assert resource_block.energy_balance_committed_units_constraint[first_index].body() == -4.5
        assert resource_block.energy_balance_committed_units_constraint[first_index].upper() == 0

    def test_energy_balance_uncommitted_units_constraint_pre_consumption(self, resource_block, first_index):
        resource_block = copy.deepcopy(resource_block)

        # initial soc is 0
        resource_block.committed_units[first_index].fix(0)
        resource_block.state_of_charge[first_index].fix(0.5)

        assert resource_block.energy_balance_uncommitted_units_constraint[first_index].expr()
        assert resource_block.energy_balance_uncommitted_units_constraint[first_index].body() == 0.5
        assert resource_block.energy_balance_uncommitted_units_constraint[first_index].lower() == 0.0

        resource_block.committed_units[first_index].fix(1)
        assert resource_block.energy_balance_uncommitted_units_constraint[first_index].expr()
        assert resource_block.energy_balance_uncommitted_units_constraint[first_index].body() == 0.5
        assert resource_block.energy_balance_uncommitted_units_constraint[first_index].lower() == 0

    def test_energy_balance_uncommitted_units_constraint_deferred_consumption(
        self, resource_block_deferred_consumption, first_index
    ):
        resource_block = copy.deepcopy(resource_block_deferred_consumption)
        # initial soc is 5
        resource_block.committed_units[first_index].fix(0)
        resource_block.state_of_charge[first_index].fix(0.5)

        assert not resource_block.energy_balance_uncommitted_units_constraint[first_index].expr()
        assert resource_block.energy_balance_uncommitted_units_constraint[first_index].body() == 4.5
        assert resource_block.energy_balance_uncommitted_units_constraint[first_index].upper() == 0.0

        resource_block.committed_units[first_index].fix(1)
        assert resource_block.energy_balance_uncommitted_units_constraint[first_index].expr()
        assert resource_block.energy_balance_uncommitted_units_constraint[first_index].body() == -0.5
        assert resource_block.energy_balance_uncommitted_units_constraint[first_index].upper() == 0.0

    def test_start_and_shutdown_unit_exclusivity_constraint(self, resource_block, first_index):
        resource_block = copy.deepcopy(resource_block)
        resource_block.start_units[first_index].fix(1)
        resource_block.shutdown_units[first_index].fix(1)
        assert not resource_block.start_and_shutdown_unit_exclusivity_constraint[first_index].expr()
        assert resource_block.start_and_shutdown_unit_exclusivity_constraint[first_index].body() == 2.0
        assert resource_block.start_and_shutdown_unit_exclusivity_constraint[first_index].upper() == 1.0

        resource_block.shutdown_units[first_index].fix(0)
        assert resource_block.start_and_shutdown_unit_exclusivity_constraint[first_index].expr()
        assert resource_block.start_and_shutdown_unit_exclusivity_constraint[first_index].body() == 1.0
        assert resource_block.start_and_shutdown_unit_exclusivity_constraint[first_index].upper() == 1.0

    def test_shift_direction_constraint_pre_consumption(self, resource_block, first_index):
        resource_block = copy.deepcopy(resource_block)
        modeled_year, dispatch_window, timestamp = first_index
        first_index = (
            modeled_year,
            dispatch_window,
        )
        resource_block.state_of_charge.fix(0)

        assert resource_block.shift_direction_constraint[first_index].upper() == 0
        assert resource_block.shift_direction_constraint[first_index].expr()
        assert resource_block.shift_direction_constraint[first_index].body() == 0

        resource_block.state_of_charge.fix(1)
        assert not resource_block.shift_direction_constraint[first_index].expr()
        assert resource_block.shift_direction_constraint[first_index].body() == 1

    def test_shift_direction_constraint_deferred_consumption(
        self,
        resource_block_deferred_consumption,
        first_index,
    ):
        modeled_year, dispatch_window, timestamp = first_index
        first_index = (
            modeled_year,
            dispatch_window,
        )

        resource_block = copy.deepcopy(resource_block_deferred_consumption)

        resource_block.state_of_charge.fix(1)
        assert not resource_block.shift_direction_constraint[first_index].expr()
        assert resource_block.shift_direction_constraint[first_index].upper() == 5.0
        assert resource_block.shift_direction_constraint[first_index].lower() == 5.0
        assert resource_block.shift_direction_constraint[first_index].body() == 1

        resource_block.state_of_charge.fix(5)
        assert resource_block.shift_direction_constraint[first_index].expr()
        assert resource_block.shift_direction_constraint[first_index].body() == 5

    def test_first_hour_state_of_charge_tracking(self, resource_block, first_index, last_index):
        resource_block = copy.deepcopy(resource_block)
        modeled_year, dispatch_window, timestamp = first_index
        resource_block.state_of_charge[last_index].fix(2)
        resource_block.power_input[last_index].fix(1)
        resource_block.power_output[last_index].fix(1)
        resource_block.state_of_charge[first_index].fix(0)

        assert not resource_block.first_hour_state_of_charge_tracking[modeled_year, dispatch_window].expr()
        assert (
            resource_block.first_hour_state_of_charge_tracking[modeled_year, dispatch_window].body() == -1.838888888888889
        )

        resource_block.state_of_charge[first_index].fix(1.838888888888889)
        assert resource_block.first_hour_state_of_charge_tracking[modeled_year, dispatch_window].expr()
        assert resource_block.first_hour_state_of_charge_tracking[modeled_year, dispatch_window].body() == 0
        assert resource_block.first_hour_state_of_charge_tracking[modeled_year, dispatch_window].lower() == 0

    def test_dispatch_monthly_annual(self, resource_for_dispatch_tests, test_net_load_for_dispatch):
        net_load = test_net_load_for_dispatch
        resource = copy.deepcopy(resource_for_dispatch_tests)

        # test with all daily, monthly, and annual calls
        resource.validate_assignment = False
        resource.max_daily_calls = None
        resource.max_monthly_calls.data[:] = 2
        resource.max_annual_calls.data.loc[:] = 5
        resource.dispatch(net_load, 2030)
        new_ts = resource.heuristic_provide_power_mw  # test the max in each day does not exceed the daily energy budget
        pp = new_ts[new_ts > 0]
        discharge_eff = resource.discharging_efficiency.data.loc[new_ts > 0]
        il = abs(new_ts[new_ts < 0])
        charge_eff = resource.charging_efficiency.data.loc[new_ts < 0]
        charging_losses = (il * (1 - charge_eff)).sum()
        discharging_losses = ((pp / discharge_eff) - pp).sum()
        assert (pp / discharge_eff).sum() == pytest.approx((il * charge_eff).sum())
        assert -new_ts.sum() == pytest.approx(charging_losses + discharging_losses)
        assert (net_load.loc[pp.index] > 0).all()
        assert (net_load.loc[il.index] < 0).all()
        assert pp.groupby(pp.index.date).sum().max() == pytest.approx(0.83)
        assert pp.sum() == pytest.approx(4.15)

    def test_dispatch_daily_annual(self, resource_for_dispatch_tests, test_net_load_for_dispatch):
        net_load = test_net_load_for_dispatch
        resource = copy.deepcopy(resource_for_dispatch_tests)

        # test with all daily and annual calls
        resource.max_daily_calls.data.loc[:] = 1
        resource.max_monthly_calls = None
        resource.max_annual_calls.data.loc[:] = 5
        resource.dispatch(net_load, 2030)
        new_ts = resource.heuristic_provide_power_mw  # test the max in each day does not exceed the daily energy budget
        pp = new_ts[new_ts > 0]
        discharge_eff = resource.discharging_efficiency.data.loc[new_ts > 0]
        il = abs(new_ts[new_ts < 0])
        charge_eff = resource.charging_efficiency.data.loc[new_ts < 0]
        charging_losses = (il * (1 - charge_eff)).sum()
        discharging_losses = ((pp / discharge_eff) - pp).sum()
        assert (pp / discharge_eff).sum() == pytest.approx((il * charge_eff).sum())
        assert -new_ts.sum() == pytest.approx(charging_losses + discharging_losses)
        assert (net_load.loc[pp.index] > 0).all()
        assert (net_load.loc[il.index] < 0).all()
        assert pp.groupby(pp.index.date).sum().max() == pytest.approx(0.83)
        assert pp.sum() == pytest.approx(4.15)

    def test_dispatch_daily_monthly(self, resource_for_dispatch_tests, test_net_load_for_dispatch):
        net_load = test_net_load_for_dispatch
        resource = copy.deepcopy(resource_for_dispatch_tests)
        # test with all daily, monthly, and annual calls
        resource.max_daily_calls.data.loc[:] = 1
        resource.max_monthly_calls.data.loc[:] = 2
        resource.max_annual_calls = None
        resource.dispatch(net_load, 2030)
        new_ts = resource.heuristic_provide_power_mw  # test the max in each day does not exceed the daily energy budget
        pp = new_ts[new_ts > 0]
        discharge_eff = resource.discharging_efficiency.data.loc[new_ts > 0]
        il = abs(new_ts[new_ts < 0])
        charge_eff = resource.charging_efficiency.data.loc[new_ts < 0]
        charging_losses = (il * (1 - charge_eff)).sum()
        discharging_losses = ((pp / discharge_eff) - pp).sum()
        assert (pp / discharge_eff).sum() == pytest.approx((il * charge_eff).sum())
        assert -new_ts.sum() == pytest.approx(charging_losses + discharging_losses)
        assert (net_load.loc[pp.index] > 0).all()
        assert (net_load.loc[il.index] < 0).all()
        assert pp.groupby(pp.index.date).sum().max() == pytest.approx(0.83)
        assert pp.sum() == pytest.approx(4.98)

    def test_dispatch_daily_only(self, resource_for_dispatch_tests, test_net_load_for_dispatch):
        net_load = test_net_load_for_dispatch
        resource = copy.deepcopy(resource_for_dispatch_tests)

        # test with all daily, monthly, and annual calls
        resource.max_daily_calls.data.loc[:] = 1
        resource.max_monthly_calls = None
        resource.max_annual_calls = None
        resource.dispatch(net_load, 2030)
        new_ts = resource.heuristic_provide_power_mw
        pp = new_ts[new_ts > 0]
        discharge_eff = resource.discharging_efficiency.data.loc[new_ts > 0]
        il = abs(new_ts[new_ts < 0])
        charge_eff = resource.charging_efficiency.data.loc[new_ts < 0]
        charging_losses = (il * (1 - charge_eff)).sum()
        discharging_losses = ((pp / discharge_eff) - pp).sum()
        assert (pp / discharge_eff).sum() == pytest.approx((il * charge_eff).sum())
        assert -new_ts.sum() == pytest.approx(charging_losses + discharging_losses)
        assert (net_load.loc[pp.index] > 0).all()
        assert (net_load.loc[il.index] < 0).all()
        assert pp.groupby(pp.index.date).sum().max() == pytest.approx(0.83)
        assert pp.sum() == pytest.approx(4.98)

    def test_dispatch_monthly_only(self, resource_for_dispatch_tests, test_net_load_for_dispatch):
        net_load = test_net_load_for_dispatch
        resource = copy.deepcopy(resource_for_dispatch_tests)

        # test with all daily, monthly, and annual calls
        resource.max_daily_calls = None
        resource.max_monthly_calls.data.loc[:] = 2
        resource.max_annual_calls = None
        resource.dispatch(net_load, 2030)
        new_ts = resource.heuristic_provide_power_mw  # test the max in each day does not exceed the daily energy budget
        pp = new_ts[new_ts > 0]
        discharge_eff = resource.discharging_efficiency.data.loc[new_ts > 0]
        il = abs(new_ts[new_ts < 0])
        charge_eff = resource.charging_efficiency.data.loc[new_ts < 0]
        charging_losses = (il * (1 - charge_eff)).sum()
        discharging_losses = ((pp / discharge_eff) - pp).sum()
        assert (pp / discharge_eff).sum() == pytest.approx((il * charge_eff).sum())
        assert -new_ts.sum() == pytest.approx(charging_losses + discharging_losses)
        assert (net_load.loc[pp.index] > 0).all()
        assert (net_load.loc[il.index] < 0).all()
        assert pp.groupby(pp.index.date).sum().max() == pytest.approx(0.83)
        assert pp.sum() == pytest.approx(4.98)

    def test_dispatch_annual_only(self, resource_for_dispatch_tests, test_net_load_for_dispatch):
        net_load = test_net_load_for_dispatch
        resource = copy.deepcopy(resource_for_dispatch_tests)

        # test with all daily, monthly, and annual calls
        resource.max_daily_calls = None
        resource.max_monthly_calls = None
        resource.max_annual_calls.data.loc[:] = 5
        resource.dispatch(net_load, 2030)
        new_ts = resource.heuristic_provide_power_mw  # test the max in each day does not exceed the daily energy budget
        pp = new_ts[new_ts > 0]
        assert pp.groupby(pp.index.date).sum().max() == pytest.approx(0.83)
        assert pp.sum() == pytest.approx(4.15)

    def test_dispatch_second_modeled_year(self, resource_for_dispatch_tests, test_net_load_for_dispatch):
        net_load = test_net_load_for_dispatch
        resource = copy.deepcopy(resource_for_dispatch_tests)

        updated_net_load = resource.dispatch(net_load=net_load, modeled_year=2030)
        new_ts = resource.heuristic_provide_power_mw  # test the max in each day does not exceed the daily energy budget
        pp = new_ts[new_ts > 0]
        discharge_eff = resource.discharging_efficiency.data.loc[new_ts > 0]
        il = abs(new_ts[new_ts < 0])
        charge_eff = resource.charging_efficiency.data.loc[new_ts < 0]
        charging_losses = (il * (1 - charge_eff)).sum()
        discharging_losses = ((pp / discharge_eff) - pp).sum()
        assert (pp / discharge_eff).sum() == pytest.approx((il * charge_eff).sum())
        assert round(pp.sum(), 2) == 4.15
        assert round(il.sum(), 2) == 4.85
        assert -(net_load.sum() - updated_net_load.sum()) == pytest.approx(charging_losses + discharging_losses)

    def test_mileage_constraint(
        self,
        resource_for_dispatch_tests,
        single_resource_dispatch_model_generator,
        make_resource_group_copy,
        first_index,
    ):
        resource = copy.deepcopy(resource_for_dispatch_tests)
        resource.power_input_max = ts.FractionalTimeseries(
            name="power_input_max",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-06-21 00:00",
                        "2010-06-21 10:00",
                        "2010-06-21 15:00",
                        "2010-06-21 22:00",
                        "2010-06-21 23:00",
                        "2010-09-21 00:00",
                        "2010-09-21 10:00",
                        "2010-09-21 15:00",
                        "2010-09-21 22:00",
                        "2010-09-21 23:00",
                        "2010-06-22 00:00",
                        "2010-06-22 10:00",
                        "2010-06-22 15:00",
                        "2010-06-22 22:00",
                        "2010-06-22 23:00",
                        "2010-10-21 00:00",
                        "2010-10-21 10:00",
                        "2010-10-21 15:00",
                        "2010-10-21 22:00",
                        "2010-10-21 23:00",
                        "2010-08-21 00:00",
                        "2010-08-21 10:00",
                        "2010-08-21 15:00",
                        "2010-08-21 22:00",
                        "2010-08-21 23:00",
                        "2010-07-21 00:00",
                        "2010-07-21 10:00",
                        "2010-07-21 15:00",
                        "2010-07-21 22:00",
                        "2010-07-21 23:00",
                    ],
                    name="timestamp",
                ),
                data=[
                    0,
                    0,
                    0.85,
                    0,
                    0.85,
                    0,
                    0,
                    0.84,
                    0,
                    0.84,
                    0,
                    0,
                    0.83,
                    0,
                    0.83,
                    0,
                    0,
                    0.82,
                    0,
                    0.82,
                    0,
                    0,
                    0.81,
                    0,
                    0.81,
                    0,
                    0,
                    0.80,
                    0,
                    0.80,
                ],
                name="value",
            ),
        )
        resource.upsample(pd.DatetimeIndex(["2030-01-01", "2030-12-31"]))

        model = single_resource_dispatch_model_generator.get(
            component_dict_name=self._SYSTEM_COMPONENT_DICT_NAME,
            resource=resource,
            resource_group=make_resource_group_copy(),
            perfect_capacity=0,
        )

        resource_block = model.blocks[resource.name]
        modeled_year, dispatch_window, timestamp = first_index
        new_index = (modeled_year, dispatch_window, timestamp + pd.DateOffset(hours=15))

        # both provide power and increase load
        resource_block.power_output[new_index].fix(0.8)
        resource_block.power_input[new_index].fix(0.8)
        assert resource_block.mileage_constraint[new_index].body() == 1.6
        assert resource_block.mileage_constraint[new_index].upper() == pytest.approx(0.80099)
        assert not resource_block.mileage_constraint[new_index].expr()

        # either provide power or increase
        resource_block.power_output[new_index].fix(0)
        assert resource_block.mileage_constraint[new_index].body() == 0.8
        assert resource_block.mileage_constraint[new_index].expr()

        # both but within the limit
        resource_block.power_output[new_index].fix(0.4)
        resource_block.power_input[new_index].fix(0.4)
        assert resource_block.mileage_constraint[new_index].body() == 0.8
        assert resource_block.mileage_constraint[new_index].upper() == pytest.approx(0.80099)
        assert resource_block.mileage_constraint[new_index].expr()

"""
    # @pytest.fixture(scope="class")
    # def resource_block_deferred_consumption(
    #     self, resource_for_dispatch_tests, make_resource_group_copy, single_resource_dispatch_model_generator
    # ):
    #     resource = copy.deepcopy(resource_for_dispatch_tests)
    #     resource.shift_direction = FlexLoadShiftDirection.DEFERRED_CONSUMPTION
    #
    #     model = single_resource_dispatch_model_generator.get(
    #         component_dict_name=self._SYSTEM_COMPONENT_DICT_NAME,
    #         resource=resource,
    #         resource_group=make_resource_group_copy(),
    #         perfect_capacity=0,
    #     )
    #
    #     resource_block = model.blocks[resource.name]
    #     return resource_block
    #
    # @pytest.fixture(scope="class")
    # def resource_for_dispatch_tests(self, make_resource_copy):
    #     resource = make_resource_copy()
    #     resource.capacity_planned = ts.NumericTimeseries(
    #         name="capacity_planned",
    #         data=pd.Series(
    #             index=pd.DatetimeIndex(["2020-01-01", "2030-01-01"], name="timestamp"),
    #             data=[1.0, 1.0],
    #             name="value",
    #         ),
    #     )
    #     resource.power_output_max = ts.FractionalTimeseries(
    #         name="power_output_max",
    #         data=pd.Series(
    #             index=pd.DatetimeIndex(
    #                 [
    #                     "2010-06-21 00:00",
    #                     "2010-06-21 16:00",
    #                     "2010-06-21 21:00",
    #                     "2010-09-21 00:00",
    #                     "2010-09-21 16:00",
    #                     "2010-09-21 21:00",
    #                     "2010-06-22 00:00",
    #                     "2010-06-22 16:00",
    #                     "2010-06-22 21:00",
    #                     "2010-10-21 00:00",
    #                     "2010-10-21 16:00",
    #                     "2010-10-21 21:00",
    #                     "2010-08-21 00:00",
    #                     "2010-08-21 16:00",
    #                     "2010-08-21 21:00",
    #                     "2010-07-21 00:00",
    #                     "2010-07-21 16:00",
    #                     "2010-07-21 21:00",
    #                 ],
    #                 name="timestamp",
    #             ),
    #             data=[0, 0.85, 0, 0, 0.84, 0, 0, 0.83, 0, 0, 0.82, 0, 0, 0.81, 0, 0, 0.80, 0],
    #             name="value",
    #         ),
    #     )
    #     resource.power_output_min = ts.FractionalTimeseries(
    #         name="power_output_min",
    #         data=pd.Series(index=pd.DatetimeIndex(["2010-01-01 00:00"], name="timestamp"), data=0, name="value"),
    #     )
    #     resource.power_input_max = ts.FractionalTimeseries(
    #         name="power_input_max",
    #         data=pd.Series(
    #             index=pd.DatetimeIndex(
    #                 [
    #                     "2010-06-21 00:00",
    #                     "2010-06-21 10:00",
    #                     "2010-06-21 15:00",
    #                     "2010-06-21 22:00",
    #                     "2010-06-21 23:00",
    #                     "2010-09-21 00:00",
    #                     "2010-09-21 10:00",
    #                     "2010-09-21 15:00",
    #                     "2010-09-21 22:00",
    #                     "2010-09-21 23:00",
    #                     "2010-06-22 00:00",
    #                     "2010-06-22 10:00",
    #                     "2010-06-22 15:00",
    #                     "2010-06-22 22:00",
    #                     "2010-06-22 23:00",
    #                     "2010-10-21 00:00",
    #                     "2010-10-21 10:00",
    #                     "2010-10-21 15:00",
    #                     "2010-10-21 22:00",
    #                     "2010-10-21 23:00",
    #                     "2010-08-21 00:00",
    #                     "2010-08-21 10:00",
    #                     "2010-08-21 15:00",
    #                     "2010-08-21 22:00",
    #                     "2010-08-21 23:00",
    #                     "2010-07-21 00:00",
    #                     "2010-07-21 10:00",
    #                     "2010-07-21 15:00",
    #                     "2010-07-21 22:00",
    #                     "2010-07-21 23:00",
    #                 ],
    #                 name="timestamp",
    #             ),
    #             data=[
    #                 0,
    #                 0.85,
    #                 0,
    #                 0.85,
    #                 0,
    #                 0,
    #                 0.84,
    #                 0,
    #                 0.84,
    #                 0,
    #                 0,
    #                 0.83,
    #                 0,
    #                 0.83,
    #                 0,
    #                 0,
    #                 0.82,
    #                 0,
    #                 0.82,
    #                 0,
    #                 0,
    #                 0.81,
    #                 0,
    #                 0.81,
    #                 0,
    #                 0,
    #                 0.80,
    #                 0,
    #                 0.80,
    #                 0,
    #             ],
    #             name="value",
    #         ),
    #     )
    #     resource.outage_profile = ts.FractionalTimeseries(
    #         name="outage_profile",
    #         data=pd.Series(
    #             index=pd.DatetimeIndex(
    #                 ["2010-01-01 00:00", "2010-01-01 01:00", "2010-01-01 02:00", "2010-12-31 23:00"], name="timestamp"
    #             ),
    #             data=[1, 1, 1, 1],
    #             name="value",
    #         ),
    #     )
    #     resource.energy_budget_daily = ts.NumericTimeseries(
    #         name="energy_budget_daily",
    #         data=pd.Series(
    #             index=pd.DatetimeIndex(["2018-01-01 00:00"], name="timestamp"), data=0.83 / 24, name="value"
    #         ),
    #         freq_="D",
    #     )
    #
    #     resource.upsample(pd.DatetimeIndex(["2030-01-01", "2030-12-31"]))
    #     return resource
    #
    # def test_operational_block_time(self, make_resource_copy, dispatch_model_generator):
    #     resource = make_resource_copy()
    #     resource.resample_ts_attributes([2030, 2030], [2010, 2010])
    #     resource.initial_storage_SOC = pd.Series(index=[float(x) for x in range(0, 8761)]).fillna(0)
    #     dispatch_model = dispatch_model_generator.get()
    #     del dispatch_model.blocks_index
    #     dispatch_model.blocks = pyo.Block(["Example_Resource"])
    #     profile_time(resource._construct_operational_rules, dispatch_model)
    #
    # @pytest.mark.parametrize(
    #     "shift_direction, shifted_total",
    #     [
    #         (FlexLoadShiftDirection.PRE_CONSUMPTION, 4.15),
    #         (FlexLoadShiftDirection.DEFERRED_CONSUMPTION, 3.5226),
    #         (FlexLoadShiftDirection.EITHER, 4.15),
    #     ],
    # )
    # def test_dispatch(self, resource_for_dispatch_tests, test_net_load_for_dispatch, shift_direction, shifted_total):
    #     net_load = test_net_load_for_dispatch
    #     resource = copy.deepcopy(resource_for_dispatch_tests)
    #     resource.shift_direction = shift_direction
    #     resource.dispatch(net_load=net_load, modeled_year=2030)
    #     new_ts = resource.heuristic_provide_power_mw
    #     pp = new_ts[new_ts > 0]
    #     discharge_eff = resource.discharging_efficiency.data.loc[new_ts > 0]
    #     il = abs(new_ts[new_ts < 0])
    #     charge_eff = resource.charging_efficiency.data.loc[new_ts < 0]
    #     assert round((pp / discharge_eff).sum(), 2) == round((il * charge_eff).sum(), 2)
    #     assert pp.sum() == pytest.approx(shifted_total)
    #     assert (net_load.loc[pp.index] > 0).all()
    #     assert (net_load.loc[il.index] < 0).all()
    #
    # def test_dispatch_all_negative(self, resource_for_dispatch_tests, test_net_load_for_dispatch):
    #     net_load = test_net_load_for_dispatch.clip(upper=-1)
    #     resource = copy.deepcopy(resource_for_dispatch_tests)
    #     resource.dispatch(net_load=net_load, modeled_year=2030)
    #     new_ts = resource.heuristic_provide_power_mw
    #     pp = new_ts[new_ts > 0]
    #     discharge_eff = resource.discharging_efficiency.data.loc[new_ts > 0]
    #     il = abs(new_ts[new_ts < 0])
    #     charge_eff = resource.charging_efficiency.data.loc[new_ts < 0]
    #     assert (pp / discharge_eff).sum() == (il * charge_eff).sum()
    #     assert new_ts.sum() == 0
    #     assert (net_load.loc[pp.index] > 0).all()
    #     assert (net_load.loc[il.index] < 0).all()
    #
    # def test_dispatch_all_positive(self, resource_for_dispatch_tests, test_net_load_for_dispatch):
    #     net_load = test_net_load_for_dispatch.clip(lower=1)
    #     resource = copy.deepcopy(resource_for_dispatch_tests)
    #     resource.dispatch(net_load=net_load, modeled_year=2030)
    #     new_ts = resource.heuristic_provide_power_mw
    #     pp = new_ts[new_ts > 0]
    #     discharge_eff = resource.discharging_efficiency.data.loc[new_ts > 0]
    #     il = abs(new_ts[new_ts < 0])
    #     charge_eff = resource.charging_efficiency.data.loc[new_ts < 0]
    #     assert (pp / discharge_eff).sum() == (il * charge_eff).sum()
    #     assert new_ts.sum() == 0
    #     assert (net_load.loc[pp.index] > 0).all()
    #     assert (net_load.loc[il.index] < 0).all()
    #
    # def test_dispatch_all_zero(self, resource_for_dispatch_tests, test_net_load_for_dispatch):
    #     net_load = test_net_load_for_dispatch * 0
    #     resource = copy.deepcopy(resource_for_dispatch_tests)
    #     resource.dispatch(net_load=net_load, modeled_year=2030)
    #     new_ts = resource.heuristic_provide_power_mw
    #     pp = new_ts[new_ts > 0]
    #     discharge_eff = resource.discharging_efficiency.data.loc[new_ts > 0]
    #     il = abs(new_ts[new_ts < 0])
    #     charge_eff = resource.charging_efficiency.data.loc[new_ts < 0]
    #     assert (pp / discharge_eff).sum() == (il * charge_eff).sum()
    #     assert new_ts.sum() == 0
    #     assert (net_load.loc[pp.index] > 0).all()
    #     assert (net_load.loc[il.index] < 0).all()
    #
    # def test_dispatch_time_varying_efficiency(self, resource_for_dispatch_tests, test_net_load_for_dispatch):
    #     resource = copy.deepcopy(resource_for_dispatch_tests)
    #     net_load = test_net_load_for_dispatch
    #
    #     resource.charging_efficiency.data.loc[
    #         [
    #             "2030-08-21 08:00:00",
    #             "2030-08-21 09:00:00",
    #             "2030-08-21 10:00:00",
    #             "2030-08-21 11:00:00",
    #             "2030-08-21 12:00:00",
    #             "2030-09-21 08:00:00",
    #             "2030-09-21 09:00:00",
    #             "2030-09-21 10:00:00",
    #             "2030-09-21 11:00:00",
    #             "2030-09-21 12:00:00",
    #             "2030-10-21 08:00:00",
    #             "2030-10-21 09:00:00",
    #             "2030-10-21 10:00:00",
    #             "2030-10-21 11:00:00",
    #             "2030-10-21 12:00:00",
    #         ]
    #     ] = [1.0, 0.5, 0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.8, 0.85, 0.9, 0.85, 0.9, 0.95]
    #
    #     resource.discharging_efficiency.data.loc[
    #         [
    #             "2030-06-21 15:00:00",
    #             "2030-06-21 16:00:00",
    #             "2030-07-21 15:00:00",
    #             "2030-07-21 16:00:00",
    #             "2030-08-21 15:00:00",
    #             "2030-08-21 16:00:00",
    #             "2030-09-21 15:00:00",
    #             "2030-09-21 16:00:00",
    #             "2030-10-21 15:00:00",
    #             "2030-10-21 16:00:00",
    #         ]
    #     ] = [1.0, 0.85, 0.75, 0.75, 0.75, 0.25, 0.85, 0.85, 1.0, 0.75]
    #
    #     resource.dispatch(net_load=net_load, modeled_year=2030)
    #     new_ts = resource.heuristic_provide_power_mw
    #     pp = new_ts[new_ts > 0]
    #     discharge_eff = resource.discharging_efficiency.data.loc[new_ts > 0]
    #     il = abs(new_ts[new_ts < 0])
    #     charge_eff = resource.charging_efficiency.data.loc[new_ts < 0]
    #     charging_losses = (il * (1 - charge_eff)).sum()
    #     discharging_losses = ((pp / discharge_eff) - pp).sum()
    #     assert (
    #         pp.groupby(pp.index.date).sum() <= resource.scaled_daily_energy_budget[2030]["2030-01-01"] + 0.00001
    #     ).all()
    #     assert (pp / discharge_eff).sum() == pytest.approx((il * charge_eff).sum())
    #     assert -new_ts.sum() == pytest.approx(charging_losses + discharging_losses)
    #
    # def test_dispatch_no_call_limit(self, resource_for_dispatch_tests, test_net_load_for_dispatch):
    #     net_load = test_net_load_for_dispatch
    #     resource = copy.deepcopy(resource_for_dispatch_tests)
    #
    #     # test with all daily, monthly, and annual calls
    #     resource.max_daily_calls = None
    #     resource.max_monthly_calls = None
    #     resource.max_annual_calls = None
    #     resource.dispatch(net_load, 2030)
    #     new_ts = resource.heuristic_provide_power_mw
    #     pp = new_ts[new_ts > 0]
    #     discharge_eff = resource.discharging_efficiency.data.loc[new_ts > 0]
    #     il = abs(new_ts[new_ts < 0])
    #     charge_eff = resource.charging_efficiency.data.loc[new_ts < 0]
    #     charging_losses = (il * (1 - charge_eff)).sum()
    #     discharging_losses = ((pp / discharge_eff) - pp).sum()
    #     assert (pp / discharge_eff).sum() == pytest.approx((il * charge_eff).sum())
    #     assert -new_ts.sum() == pytest.approx(charging_losses + discharging_losses)
