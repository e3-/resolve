import copy

import pandas as pd
import pytest

from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.core.temporal import timeseries as ts
from new_modeling_toolkit.system import Asset
from new_modeling_toolkit.system import FuelStorage
from new_modeling_toolkit.system.fuel.fuel_storage import FuelStorageGroup
from new_modeling_toolkit.system.fuel.fuel_storage import StorageDurationConstraint
from tests.system.fuel.test_fuel_production_plant import TestFuelProductionPlant
from tests.system.fuel.test_fuel_production_plant import TestFuelProductionPlantGroup


class TestFuelStorage(TestFuelProductionPlant):
    _COMPONENT_CLASS = FuelStorage
    _COMPONENT_NAME = "FuelStorage1"
    _SYSTEM_COMPONENT_DICT_NAME = "fuel_storage_plants"

    primary_product: str = "CandidateFuel2"
    primary_product_unit: str = "MMBtu"

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
            "variable_cost",
            "duration",
            "duration_constraint",
            "variable_cost_input",
            "allow_inter_period_sharing",
            "min_input_profile",
            "max_input_profile",
            "parasitic_loss",
            "min_state_of_charge"
        ]

    def test_operational_three_way_linkages(self, make_component_copy):
        assert make_component_copy().operational_three_way_linkages == ["processes", "charging_processes"]

    @pytest.fixture(scope="class")
    def make_component_with_block_copy_inter_period_sharing(self, test_model_inter_period_sharing):
        def _make_copy_with_block():
            return copy.deepcopy(
                getattr(test_model_inter_period_sharing.system, self._SYSTEM_COMPONENT_DICT_NAME)[self._COMPONENT_NAME]
            )

        return _make_copy_with_block

    @pytest.mark.parametrize(
        "attr_name, new_value",
        [
            ("can_build_new", False),
            ("can_retire", False),
            # ("financial_lifetime", 1000),
            ("physical_lifetime", 1000),
            # ("potential", 1000),
            # ("planned_capacity", 1000),
            # ("annualized_capital_cost", 1000),
            # ("annualized_fixed_om_cost", 1000),
            # ("annualized_storage_capital_cost", 10),
            # ("annualized_storage_fixed_om_cost", 15),
        ],
    )
    def test_check_if_operationally_equal_true(self, make_component_copy, attr_name, new_value):
        fuel_storage: Asset = make_component_copy()

        curr_test_copy: Asset = fuel_storage.copy(include_linkages=True, update={attr_name: new_value})
        assert fuel_storage.check_if_operationally_equal(curr_test_copy)
        assert curr_test_copy.check_if_operationally_equal(fuel_storage)

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
            ("duration", 12),
            ("duration_constraint", StorageDurationConstraint.MAXIMUM),
            (
                "variable_cost_input",
                ts.NumericTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-01-01 01:00"]), data=[0.5, 0.4]),
                ),
            ),
            (
                "min_input_profile",
                ts.FractionalTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-01-01 01:00"]), data=[0.5, 0.4]),
                ),
            ),
            (
                "max_input_profile",
                ts.FractionalTimeseries(
                    name="other_profile",
                    data=pd.Series(index=pd.DatetimeIndex(["2020-01-01 00:00", "2020-01-01 01:00"]), data=[0.5, 0.4]),
                ),
            ),
            ("parasitic_loss", 0.05),
            ("min_state_of_charge", 0.9),
        ],
    )
    def test_check_if_operationally_equal_false(self, make_component_copy, attr_name, new_value):
        fuel_storage: Asset = make_component_copy()
        curr_test_copy: Asset = fuel_storage.copy(include_linkages=True, update={attr_name: new_value})

        assert not fuel_storage.check_if_operationally_equal(curr_test_copy)
        assert not curr_test_copy.check_if_operationally_equal(fuel_storage)

    # Operational rule testing
    def test_variable_bounds(self, make_component_with_block_copy):
        fuel_storage = make_component_with_block_copy()
        block = fuel_storage.formulation_block

        for index in block.charge:
            assert block.charge[index].lb == 0
            assert block.charge[index].ub is None

        for index in block.soc_intra_period:
            assert block.soc_intra_period[index].lb is None
            assert block.soc_intra_period[index].ub is None

        for index in block.soc_inter_period:
            assert block.soc_inter_period[index].lb == 0
            assert block.soc_inter_period[index].ub is None

    def test_consumption(self, make_component_with_block_copy, first_index, last_index):
        plant: FuelStorage = make_component_with_block_copy()
        plant_block = plant.formulation_block

        # Testing primary product processes
        plant_block.charge[first_index] = 0
        plant_block.operation[first_index] = 0
        assert plant_block.consumption[self.primary_product, first_index].expr() == 0

        plant_block.charge[first_index] = 100
        plant_block.operation[first_index] = 200
        assert plant.charging_efficiency == 0.95
        assert plant_block.consumption[self.primary_product, first_index].expr() == 100

        # Testing other product processes
        input_product = list(plant.discharging_processes.keys())[1][0]
        process = plant.discharging_processes[(input_product, self.primary_product)]
        assert process.conversion_rate == 0.75

        plant_block.charge[last_index] = 0
        plant_block.operation[last_index] = 0
        assert plant_block.consumption[input_product, last_index].expr() == 0

        plant_block.charge[last_index] = 100
        plant_block.operation[last_index] = 200
        assert plant_block.consumption[input_product, last_index].expr() == pytest.approx(200 / 0.75, 10**-6)

    def test_production(self, make_component_with_block_copy, first_index, last_index):
        # TODO: Create secondary production pathway to test the second expression in production if-else
        plant: FuelStorage = make_component_with_block_copy()
        plant_block = plant.formulation_block

        # Testing primary processes
        plant_block.operation[first_index] = 0
        plant_block.consumption[self.primary_product, first_index] = 0
        assert plant_block.production[self.primary_product, first_index].expr() == 0

        plant_block.operation[first_index] = 100
        plant_block.consumption[self.primary_product, first_index] = 200
        assert plant_block.production[self.primary_product, first_index].expr() == 100

        input_product = list(plant.discharging_processes.keys())[1][0]
        plant_block.operation[last_index] = 100
        plant_block.consumption[input_product, last_index] = 200
        assert plant_block.production[self.primary_product, last_index].expr() == 100

    def test_scaled_min_input_profile(self, make_component_with_block_copy):
        input_mins = {
            pd.Timestamp("2025-01-01"): 200 * 0.1,
            pd.Timestamp("2035-01-01"): 100 * 0.1,
        }
        timestamps = [
            pd.Timestamp("2010-06-21 00:00"),
            pd.Timestamp("2010-06-21 01:00"),
            pd.Timestamp("2010-06-21 02:00"),
            pd.Timestamp("2012-02-15 12:00"),
            pd.Timestamp("2012-02-15 13:00"),
            pd.Timestamp("2012-02-15 14:00"),
        ]
        dispatch_windows = [pd.Timestamp(f"{ts.year}-{ts.month}-{ts.day}") for ts in timestamps]

        block = make_component_with_block_copy().formulation_block
        block.operational_capacity[pd.Timestamp("2025-01-01")] = 200
        block.operational_capacity[pd.Timestamp("2035-01-01")] = 100

        for modeled_year, val in input_mins.items():
            for dispatch_window, timestamp in zip(dispatch_windows, timestamps):
                assert block.scaled_min_input_profile[modeled_year, dispatch_window, timestamp].expr() == val

    def test_scaled_max_input_profile(self, make_component_with_block_copy):
        input_maxes = {
            pd.Timestamp("2025-01-01"): 200 * 0.5,
            pd.Timestamp("2035-01-01"): 100 * 0.5,
        }
        timestamps = [
            pd.Timestamp("2010-06-21 00:00"),
            pd.Timestamp("2010-06-21 01:00"),
            pd.Timestamp("2010-06-21 02:00"),
            pd.Timestamp("2012-02-15 12:00"),
            pd.Timestamp("2012-02-15 13:00"),
            pd.Timestamp("2012-02-15 14:00"),
        ]
        dispatch_windows = [pd.Timestamp(f"{ts.year}-{ts.month}-{ts.day}") for ts in timestamps]

        block = make_component_with_block_copy().formulation_block
        block.operational_capacity[pd.Timestamp("2025-01-01")] = 200
        block.operational_capacity[pd.Timestamp("2035-01-01")] = 100

        for modeled_year, val in input_maxes.items():
            for dispatch_window, timestamp in zip(dispatch_windows, timestamps):
                assert block.scaled_max_input_profile[modeled_year, dispatch_window, timestamp].expr() == val

    def test_min_input_constraint(self, make_component_with_block_copy, first_index):
        fuel_storage = make_component_with_block_copy()
        block = fuel_storage.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        block.operational_capacity[modeled_year] = 200

        block.charge[first_index].fix(80.0)
        assert block.min_input_constraint[first_index].body() == 200 * 0.1 - 80.0
        assert block.min_input_constraint[first_index].upper() == 0
        assert block.min_input_constraint[first_index].expr()

        block.charge[first_index].fix(0.0)
        assert block.min_input_constraint[first_index].body() == 200 * 0.1 - 0.0
        assert not block.min_input_constraint[first_index].expr()

        block.charge[first_index].fix(200 * 0.1)
        assert block.min_input_constraint[first_index].body() == 0.0
        assert block.min_input_constraint[first_index].expr()

    def test_max_input_constraint(self, make_component_with_block_copy, first_index):
        fuel_storage = make_component_with_block_copy()
        block = fuel_storage.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        block.operational_capacity[modeled_year] = 200

        block.charge[first_index].fix(120.0)
        assert block.max_input_constraint[first_index].body() == -(200 * 0.5 - 120.0)
        assert block.max_input_constraint[first_index].upper() == 0
        assert not block.max_input_constraint[first_index].expr()

        block.charge[first_index].fix(0.0)
        assert block.max_input_constraint[first_index].body() == -(200 * 0.5 - 0.0)
        assert block.max_input_constraint[first_index].expr()

        block.charge[first_index].fix(200 * 0.5)
        assert block.max_input_constraint[first_index].body() == 0.0
        assert block.max_input_constraint[first_index].expr()

    def test_mileage_constraint(self, make_component_with_block_copy, first_index):
        fuel_storage = make_component_with_block_copy()
        block = fuel_storage.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        block.operational_capacity[modeled_year] = 200

        block.operation[first_index].fix(100)
        block.charge[first_index].fix(50)
        assert block.mileage_constraint[first_index].upper() == 0
        assert block.mileage_constraint[first_index].body() == 100 + 50 - 200 * 0.9
        assert block.mileage_constraint[first_index].expr()

        block.operation[first_index].fix(100)
        block.charge[first_index].fix(150)
        assert block.mileage_constraint[first_index].body() == 100 + 150 - 200 * 0.9
        assert not block.mileage_constraint[first_index].expr()

    def test_simultaneous_charging_constraint(self, make_component_with_block_copy, last_index):
        fuel_storage = make_component_with_block_copy()
        block = fuel_storage.formulation_block
        modeled_year, dispatch_window, timestamp = last_index

        block.operational_capacity[modeled_year] = 100

        block.operation[last_index].fix(50)
        block.charge[last_index].fix(50)
        assert not block.simultaneous_charging_constraint[last_index].expr()

        block.operation[last_index].fix(50)
        block.charge[last_index].fix(20)
        assert block.simultaneous_charging_constraint[last_index].expr()

        block.operation[last_index].fix(20)
        block.charge[last_index].fix(20)
        assert block.simultaneous_charging_constraint[last_index].expr()

    def test_soc_inter_intra_joint(self, make_component_with_block_copy, first_index_storage):

        fuel_storage = make_component_with_block_copy()
        block = fuel_storage.formulation_block
        model: ModelTemplate = block.model()

        modeled_year, chrono_period, timestamp = first_index_storage
        dispatch_window = model.chrono_periods_map[chrono_period]

        block.soc_inter_period[modeled_year, chrono_period].fix(-10)
        block.soc_intra_period[modeled_year, dispatch_window, timestamp].fix(15)
        assert block.soc_inter_intra_joint[modeled_year, chrono_period, timestamp].expr() == 5
        assert not block.soc_inter_intra_joint[modeled_year, chrono_period, timestamp].expr() == 0

    def test_soc_inter_intra_max_constraint(self, make_component_with_block_copy, first_index_storage):

        fuel_storage = make_component_with_block_copy()
        block = fuel_storage.formulation_block
        model: ModelTemplate = block.model()

        modeled_year = first_index_storage[0]

        block.soc_inter_intra_joint[first_index_storage] = 1_000
        block.operational_storage_capacity[modeled_year] = 100 * 100
        assert block.soc_inter_intra_max_constraint[first_index_storage].upper() == 0
        assert block.soc_inter_intra_max_constraint[first_index_storage].body() == pytest.approx(
            1_000 - 100 * 100 / 0.9
        )
        assert block.soc_inter_intra_max_constraint[first_index_storage].expr()

        block.soc_inter_intra_joint[first_index_storage] = 100 * 100 / 0.9
        block.operational_storage_capacity[modeled_year] = 100 * 100
        assert block.soc_inter_intra_max_constraint[first_index_storage].body() == pytest.approx(0.0)
        assert block.soc_inter_intra_max_constraint[first_index_storage].expr()

        block.soc_inter_intra_joint[first_index_storage] = 100 * 101 / 0.9
        block.operational_storage_capacity[modeled_year] = 100 * 100
        assert not block.soc_inter_intra_max_constraint[first_index_storage].expr()

    def test_soc_inter_intra_min_constraint(self, make_component_with_block_copy, first_index_storage):

        fuel_storage = make_component_with_block_copy()
        block = fuel_storage.formulation_block
        model: ModelTemplate = block.model()

        modeled_year = first_index_storage[0]

        block.soc_inter_intra_joint[first_index_storage] = 1_100
        block.operational_storage_capacity[modeled_year] = 100 * 100
        assert block.soc_inter_intra_min_constraint[first_index_storage].upper() == 0
        assert block.soc_inter_intra_min_constraint[first_index_storage].body() == pytest.approx(
            100 * 100 * 0.1 - 1_100
        )
        assert block.soc_inter_intra_min_constraint[first_index_storage].expr()

        block.soc_inter_intra_joint[first_index_storage] = 1_000
        block.operational_storage_capacity[modeled_year] = 100 * 100
        assert block.soc_inter_intra_min_constraint[first_index_storage].body() == pytest.approx(0.0)
        assert block.soc_inter_intra_min_constraint[first_index_storage].expr()

        block.soc_inter_intra_joint[first_index_storage] = 900
        block.operational_storage_capacity[modeled_year] = 100 * 100
        assert not block.soc_inter_intra_min_constraint[first_index_storage].expr()

    def test_soc_intra_tracking_constraint(self, make_component_with_block_copy, first_index):
        fuel_storage = make_component_with_block_copy()
        block = fuel_storage.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        block.charge[modeled_year, dispatch_window, timestamp].fix(40)
        block.operation[modeled_year, dispatch_window, timestamp].fix(30)
        block.soc_intra_period[modeled_year, dispatch_window, timestamp].fix(20)
        block.soc_intra_period[
            modeled_year,
            fuel_storage.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS.next((dispatch_window, timestamp)),
        ].fix(10)

        assert block.soc_intra_tracking_constraint[modeled_year, dispatch_window, timestamp].body() == (
            pytest.approx(10 - (20 + 40 * 0.95 - 30 / 0.9))
        )
        assert block.soc_intra_tracking_constraint[modeled_year, dispatch_window, timestamp].lower() == 0
        assert block.soc_intra_tracking_constraint[modeled_year, dispatch_window, timestamp].upper() == 0
        assert not block.soc_intra_tracking_constraint[modeled_year, dispatch_window, timestamp].expr()

        block.charge[modeled_year, dispatch_window, timestamp].fix(100)
        block.operation[modeled_year, dispatch_window, timestamp].fix(90)
        block.soc_intra_period[modeled_year, dispatch_window, timestamp].fix(200)
        block.soc_intra_period[
            modeled_year,
            fuel_storage.formulation_block.model().DISPATCH_WINDOWS_AND_TIMESTAMPS.next((dispatch_window, timestamp)),
        ].fix(195)

        assert block.soc_intra_tracking_constraint[modeled_year, dispatch_window, timestamp].body() == (
            pytest.approx(0)
        )
        assert block.soc_intra_tracking_constraint[modeled_year, dispatch_window, timestamp].lower() == 0
        assert block.soc_intra_tracking_constraint[modeled_year, dispatch_window, timestamp].upper() == 0
        assert block.soc_intra_tracking_constraint[modeled_year, dispatch_window, timestamp].expr()

    def test_soc_inter_tracking_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_inter_period_sharing
    ):
        fuel_storage = make_component_with_block_copy_inter_period_sharing()
        block = fuel_storage.formulation_block
        model: ModelTemplate = block.model()
        modeled_year, chrono_period, timestamp = first_index_inter_period_sharing
        dispatch_window = model.chrono_periods_map[chrono_period]

        final_hour = model.last_timepoint_in_dispatch_window[dispatch_window]
        block.charge[modeled_year, dispatch_window, timestamp].fix(40)
        block.operation[modeled_year, dispatch_window, timestamp].fix(30)
        block.charge[modeled_year, dispatch_window, final_hour].fix(40)
        block.operation[modeled_year, dispatch_window, final_hour].fix(30)

        block.soc_intra_period[modeled_year, dispatch_window, timestamp].fix(0)
        block.soc_intra_period[modeled_year, dispatch_window, final_hour].fix(0)
        block.soc_inter_period[modeled_year, model.CHRONO_PERIODS.next(chrono_period)].fix(0)
        block.soc_inter_period[modeled_year, chrono_period].fix(0)

        assert block.soc_inter_tracking_constraint[modeled_year, chrono_period].body() == (
            pytest.approx(0 - (0 + 0 + 40 * 0.95 - 30 / 0.9))
        )
        assert not block.soc_inter_tracking_constraint[modeled_year, chrono_period].expr()

    def test_soc_inter_zero_constraint_no_inter_period_sharing(
        self, make_component_with_block_copy, first_index_storage
    ):
        fuel_storage = make_component_with_block_copy()
        block = fuel_storage.formulation_block

        block.soc_inter_period.fix(0)

        for modeled_year in [
            pd.Timestamp("2025-01-01"),
            pd.Timestamp("2030-01-01"),
            pd.Timestamp("2035-01-01"),
            pd.Timestamp("2045-01-01"),
        ]:
            for chrono_period in [pd.Timestamp("2010-06-21"), pd.Timestamp("2012-02-15")]:
                assert block.soc_inter_tracking_constraint[modeled_year, chrono_period].lower() == 0
                assert block.soc_inter_tracking_constraint[modeled_year, chrono_period].upper() == 0
                assert block.soc_inter_tracking_constraint[modeled_year, chrono_period].body() == 0
                assert block.soc_inter_tracking_constraint[modeled_year, chrono_period].expr()

    def test_soc_intra_anchoring_constraint_loopback(self, make_component_with_block_copy, first_index, last_index):
        fuel_storage = make_component_with_block_copy()
        block = fuel_storage.formulation_block
        modeled_year, dispatch_window, _ = first_index

        block.charge[last_index].fix(40)
        block.operation[last_index].fix(30)
        block.soc_intra_period[last_index].fix(20)
        block.soc_intra_period[first_index].fix(10)

        assert block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].body() == (
            pytest.approx(10 - (20 + 40 * 0.95 - 30 / 0.9))
        )
        assert block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].lower() == 0
        assert block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].upper() == 0
        assert not block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].expr()

        block.charge[last_index].fix(100)
        block.operation[last_index].fix(90)
        block.soc_intra_period[last_index].fix(200)
        block.soc_intra_period[first_index].fix(195)

        assert block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].body() == (
            pytest.approx(0)  # 185 - (200 + 0.85 * 100 - 90 / 0.9)
        )
        assert block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].lower() == 0
        assert block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].upper() == 0
        assert block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].expr()

    def test_soc_intra_anchoring_constraint_interperiod(
        self, make_component_with_block_copy_inter_period_sharing, first_index
    ):
        fuel_storage = make_component_with_block_copy_inter_period_sharing()
        block = fuel_storage.formulation_block
        modeled_year, dispatch_window, _ = first_index

        block.soc_intra_period[first_index].fix(10)
        assert block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].body() == 10
        assert block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].lower() == 0
        assert block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].upper() == 0
        assert not block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].expr()

        block.soc_intra_period[first_index].fix(0)
        assert block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].body() == 0
        assert block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].lower() == 0
        assert block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].upper() == 0
        assert block.soc_intra_anchoring_constraint[modeled_year, dispatch_window].expr()

    def test_variable_cost_charging(self, make_component_with_block_copy, first_index):
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        assert resource.variable_cost_input.data.at[timestamp] == 1

        block.operation[first_index].fix(100)
        block.charge[first_index].fix(50)
        assert block.variable_cost_charging[first_index].expr() == 50

    def test_annual_total_operational_cost(self, make_component_with_block_copy):
        resource = make_component_with_block_copy()
        block = resource.formulation_block

        for year in [
            pd.Timestamp("2025-01-01 00:00"),
            pd.Timestamp("2030-01-01 00:00"),
            pd.Timestamp("2035-01-01 00:00"),
            pd.Timestamp("2045-01-01 00:00"),
        ]:
            block.annual_variable_cost[year] = 99
            block.annual_consumed_commodity_product_cost[year] = 155
            block.annual_variable_cost_charging[year] = 88
            block.annual_production_tax_credit[year] = 11
            assert block.annual_total_operational_cost[year].expr() == 99 + 155 + 88 - 11

        assert block.annual_total_operational_cost

    # Investment rule testing
    def test_storage_capacity_duration_constraint_fixed(self, make_component_with_block_copy, first_index):
        storage_resource = make_component_with_block_copy()
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        resource_block.operational_storage_capacity[modeled_year] = 10 * 100
        resource_block.operational_capacity[modeled_year] = 10.0

        assert resource_block.storage_capacity_duration_constraint[modeled_year].expr()

    def test_storage_capacity_duration_constraint_minimum(self, make_custom_component_with_block, first_index):
        storage_resource = make_custom_component_with_block(duration_constraint=StorageDurationConstraint.MINIMUM)
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        resource_block.operational_storage_capacity[modeled_year] = 10 * 100
        resource_block.operational_capacity[modeled_year] = 9

        assert resource_block.storage_capacity_duration_constraint[modeled_year].expr()

    def test_storage_capacity_duration_constraint_maximum(self, make_custom_component_with_block, first_index):
        storage_resource = make_custom_component_with_block(duration_constraint=StorageDurationConstraint.MAXIMUM)
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        resource_block.operational_storage_capacity[modeled_year] = 10 * 100
        resource_block.operational_capacity[modeled_year] = 11.0

        assert resource_block.storage_capacity_duration_constraint[modeled_year].expr()

    def test_retired_storage_capacity_max_constraint_can_retire(self, make_component_with_block_copy, first_index):
        storage_resource = make_component_with_block_copy()
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Tests retireable resources during their physical lifetime
        resource_block.retired_storage_capacity[modeled_year] = 12000.0

        assert not resource_block.retired_storage_capacity_max_constraint[modeled_year].expr()

    def test_retired_storage_capacity_max_constraint_cannot_retire(self, make_custom_component_with_block, first_index):
        storage_resource = make_custom_component_with_block(can_retire=False)
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Tests retireable resources during their physical lifetime
        resource_block.retired_storage_capacity[modeled_year] = 300.0

        assert not resource_block.retired_storage_capacity_max_constraint[modeled_year].expr()

    def test_retired_storage_capacity_max_constraint_cannot_retire_no_lifetime(
        self, make_custom_component_with_block, first_index
    ):
        storage_resource = make_custom_component_with_block(can_retire=False, physical_lifetime=100)
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, timestamp = first_index

        # Tests retireable resources during their physical lifetime
        resource_block.retired_storage_capacity[modeled_year] = 300.0

        assert not resource_block.retired_storage_capacity_max_constraint[modeled_year].expr()

    def test_storage_physical_lifetime_constraint(self, make_component_with_block_copy, last_modeled_year):
        storage_resource = make_component_with_block_copy()
        resource_block = storage_resource.formulation_block
        modeled_year, dispatch_window, timestamp = last_modeled_year

        resource_block.operational_storage_capacity[modeled_year] = 30.0

        assert not resource_block.storage_physical_lifetime_constraint[modeled_year].expr()

    def test_save_operational_storage_capacity(self, make_component_with_block_copy):
        storage_resource = make_component_with_block_copy()
        block = storage_resource.formulation_block
        modeled_years = list(block.model().MODELED_YEARS)

        block.operational_storage_capacity[:] = 10
        storage_resource.save_operational_storage_capacity()

        assert (storage_resource.operational_storage_capacity.data == pd.Series(index=modeled_years, data=10)).all()

    def test_save_selected_storage_capacity(self, make_component_with_block_copy):
        storage_resource = make_component_with_block_copy()
        block = storage_resource.formulation_block

        block.selected_storage_capacity = 10
        storage_resource.save_selected_storage_capacity()

        assert storage_resource.selected_storage_capacity == 10

    def test_save_retired_storage_capacity(self, make_component_with_block_copy):
        storage_resource = make_component_with_block_copy()
        block = storage_resource.formulation_block
        modeled_years = list(block.model().MODELED_YEARS)

        block.retired_storage_capacity[:] = 10
        storage_resource.save_retired_storage_capacity()

        assert (storage_resource.retired_storage_capacity.data == pd.Series(index=modeled_years, data=10)).all()

    def test_save_cumulative_retired_storage_capacity(self, make_component_with_block_copy):
        asset = make_component_with_block_copy()
        block = asset.formulation_block
        modeled_years = list(block.model().MODELED_YEARS)

        block.retired_storage_capacity[:] = 10
        asset.save_cumulative_retired_storage_capacity()

        cumulative_value = 0
        for year in modeled_years:
            cumulative_value += 10
            assert asset.cumulative_retired_storage_capacity.data.at[year] == cumulative_value

    def test_prod_sim_selected_storage_capacity_constraint(self, make_component_with_block_copy_production_simulation):
        # All selected, retired, and operational capacities are set to zero
        storage_resource = make_component_with_block_copy_production_simulation()
        block = storage_resource.formulation_block

        # Constraint is valid
        assert block.prod_sim_selected_storage_capacity_constraint.upper() == 0
        assert block.prod_sim_selected_storage_capacity_constraint.lower() == 0
        block.selected_storage_capacity = 0
        assert block.prod_sim_selected_storage_capacity_constraint.expr()

        # Constraint is violated
        block.selected_storage_capacity = 4
        assert not block.prod_sim_selected_storage_capacity_constraint.expr()

    def test_prod_sim_retired_storage_capacity_constraint(
        self, make_component_with_block_copy_production_simulation, first_index
    ):
        # All selected, retired, and operational capacities are set to zero
        storage_resource = make_component_with_block_copy_production_simulation()
        block = storage_resource.formulation_block
        first_year = first_index[0]

        # Constraint is valid
        assert block.prod_sim_retired_storage_capacity_constraint[first_year].upper() == 0
        assert block.prod_sim_retired_storage_capacity_constraint[first_year].lower() == 0
        block.retired_storage_capacity[first_year] = 0
        assert block.prod_sim_retired_storage_capacity_constraint[first_year].expr()

        # Constraint is violated
        block.retired_storage_capacity[first_year] = 4
        assert not block.prod_sim_retired_storage_capacity_constraint[first_year].expr()

    def test_prod_sim_operational_storage_capacity_constraint(
        self, make_component_with_block_copy_production_simulation, first_index
    ):
        # All selected, retired, and operational capacities are set to zero
        storage_resource = make_component_with_block_copy_production_simulation()
        block = storage_resource.formulation_block
        first_year = first_index[0]

        # Constraint is valid
        assert block.prod_sim_operational_storage_capacity_constraint[first_year].upper() == 0
        assert block.prod_sim_operational_storage_capacity_constraint[first_year].lower() == 0
        block.operational_storage_capacity[first_year] = 0
        assert block.prod_sim_operational_storage_capacity_constraint[first_year].expr()

        # Constraint is violated
        block.operational_storage_capacity[first_year] = 4
        assert not block.prod_sim_operational_storage_capacity_constraint[first_year].expr()

    def test_results_reporting(self, make_component_with_block_copy):
        storage_resource = make_component_with_block_copy()
        block = storage_resource.formulation_block
        storage_resource._construct_output_expressions(construct_costs=True)

        assert block.planned_storage_capacity.doc == f"Planned Storage Capacity ({self.primary_product_unit})"
        assert block.selected_storage_capacity.doc == f"Selected Storage Capacity ({self.primary_product_unit})"
        assert block.retired_storage_capacity.doc == f"Retired Storage Capacity ({self.primary_product_unit})"
        assert block.operational_storage_capacity.doc == f"Operational Storage Capacity ({self.primary_product_unit})"

        assert block.annual_storage_capital_cost.doc == "Annual Storage Capacity Capital Cost ($)"
        assert block.annual_storage_fixed_om_cost.doc == "Annual Storage Capacity Fixed O&M Cost ($)"
        assert block.annual_total_investment_cost.doc == "Annual Total Investment Cost ($)"

        assert block.annual_charge.doc == f"Annual Charge ({self.primary_product_unit})"
        assert block.annual_storage.doc == f"Annual Product Storage ({self.primary_product_unit})"


class TestFuelStorageGroup(TestFuelProductionPlantGroup, TestFuelStorage):
    _COMPONENT_CLASS = FuelStorageGroup
    _COMPONENT_NAME = "fuel_storage_group"
    _SYSTEM_COMPONENT_DICT_NAME = "fuel_storage_groups"

    @pytest.fixture(scope="class")
    def make_component_with_block_copy_inter_period_sharing(
        self, test_model_with_operational_groups_inter_period_sharing
    ):
        def _make_copy_with_block():
            return copy.deepcopy(
                getattr(
                    test_model_with_operational_groups_inter_period_sharing.system, self._SYSTEM_COMPONENT_DICT_NAME
                )[self._COMPONENT_NAME]
            )

        return _make_copy_with_block

    def test_cumulative_selected_storage_capacity(self, make_component_with_block_copy):
        operational_group = make_component_with_block_copy()
        for asset in operational_group.asset_instances.values():
            asset.formulation_block.selected_storage_capacity = 50
        assert (
            operational_group.formulation_block.cumulative_selected_storage_capacity[pd.Timestamp("2025-01-01")].expr()
            == 100
        )
        assert (
            operational_group.formulation_block.cumulative_selected_storage_capacity[pd.Timestamp("2035-01-01")].expr()
            == 100
        )
        for asset in operational_group.asset_instances.values():
            asset.formulation_block.selected_storage_capacity = 25
        assert (
            operational_group.formulation_block.cumulative_selected_storage_capacity[pd.Timestamp("2025-01-01")].expr()
            == 50
        )
        assert (
            operational_group.formulation_block.cumulative_selected_storage_capacity[pd.Timestamp("2035-01-01")].expr()
            == 50
        )

    def test_selected_storage_capacity(self, make_component_with_block_copy):
        operational_group = make_component_with_block_copy()
        for asset in operational_group.asset_instances.values():
            asset.formulation_block.selected_storage_capacity = 50
        assert operational_group.formulation_block.selected_storage_capacity[
            pd.Timestamp("2025-01-01")
        ].expr() == 50 * len(operational_group.asset_instances)
        assert operational_group.formulation_block.selected_storage_capacity[pd.Timestamp("2030-01-01")].expr() == 0

        for ind, asset in enumerate(operational_group.asset_instances.values()):
            if ind == 0:
                asset.formulation_block.selected_storage_capacity = 25
            else:
                asset.formulation_block.selected_storage_capacity = 0
        assert operational_group.formulation_block.selected_storage_capacity[pd.Timestamp("2025-01-01")].expr() == 25
        assert operational_group.formulation_block.selected_storage_capacity[pd.Timestamp("2030-01-01")].expr() == 0

    def test_retired_storage_capacity(self, make_component_with_block_copy):
        operational_group = make_component_with_block_copy()
        block = operational_group.formulation_block
        num_instances = len(operational_group.asset_instances)

        for asset in operational_group.asset_instances.values():
            asset.formulation_block.retired_storage_capacity[pd.Timestamp("2025-01-01")] = 25
        assert block.retired_storage_capacity[pd.Timestamp("2025-01-01")].expr() == 25 * num_instances

        for asset in operational_group.asset_instances.values():
            asset.formulation_block.retired_storage_capacity[pd.Timestamp("2045-01-01")] = 75
        assert block.retired_storage_capacity[pd.Timestamp("2045-01-01")].expr() == 75 * num_instances

    def test_cumulative_retired_storage_capacity(self, make_component_with_block_copy):
        operational_group = make_component_with_block_copy()
        block = operational_group.formulation_block

        block.retired_storage_capacity[pd.Timestamp("2025-01-01")] = 50
        block.retired_storage_capacity[pd.Timestamp("2030-01-01")] = 75
        block.retired_storage_capacity[pd.Timestamp("2035-01-01")] = 100
        block.retired_storage_capacity[pd.Timestamp("2045-01-01")] = 25

        assert block.cumulative_retired_storage_capacity[pd.Timestamp("2025-01-01")].expr() == 50
        assert block.cumulative_retired_storage_capacity[pd.Timestamp("2030-01-01")].expr() == 125
        assert block.cumulative_retired_storage_capacity[pd.Timestamp("2035-01-01")].expr() == 225
        assert block.cumulative_retired_storage_capacity[pd.Timestamp("2045-01-01")].expr() == 250

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_storage_capacity_duration_constraint_fixed(self, make_component_with_block_copy, first_index):
        super().test_storage_capacity_duration_constraint_fixed(make_component_with_block_copy, first_index)

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_storage_capacity_duration_constraint_minimum(self, make_custom_component_with_block, first_index):
        super().test_storage_capacity_duration_constraint_minimum(make_custom_component_with_block, first_index)

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_storage_capacity_duration_constraint_maximum(self, make_custom_component_with_block, first_index):
        super().test_storage_capacity_duration_constraint_maximum(make_custom_component_with_block, first_index)

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_retired_storage_capacity_max_constraint_can_retire(self, make_component_with_block_copy, first_index):
        super().test_retired_storage_capacity_max_constraint_can_retire(make_component_with_block_copy, first_index)

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_retired_storage_capacity_max_constraint_cannot_retire(self, make_custom_component_with_block, first_index):
        super().test_retired_storage_capacity_max_constraint_cannot_retire(
            make_custom_component_with_block, first_index
        )

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_retired_storage_capacity_max_constraint_cannot_retire_no_lifetime(
        self, make_custom_component_with_block, first_index
    ):
        super().test_retired_storage_capacity_max_constraint_cannot_retire_no_lifetime(
            make_custom_component_with_block, first_index
        )

    @pytest.mark.skip(
        reason=(
            "Because the operational group should just represent the sum of the investment decisions of the resources "
            "in that group, it should not have its own investment decision constraints"
        )
    )
    def test_storage_physical_lifetime_constraint(self, make_component_with_block_copy, last_modeled_year):
        super().test_storage_physical_lifetime_constraint(make_component_with_block_copy, last_modeled_year)

    @pytest.mark.skip(reason=("Selected capacities are not saved for AssetGroups."))
    def test_save_selected_storage_capacity(self, make_component_with_block_copy_production_simulation):
        pass

    @pytest.mark.skip(reason=("Operational capacities are not saved for AssetGroups."))
    def test_save_operational_storage_capacity(self, make_component_with_block_copy):
        pass

    @pytest.mark.skip(reason=("Retired capacities are not saved for AssetGroups."))
    def test_save_retired_storage_capacity(self, make_component_with_block_copy):
        pass

    @pytest.mark.skip(reason=("Retired capacities are not saved for AssetGroups."))
    def test_save_cumulative_retired_storage_capacity(self, make_component_with_block_copy):
        pass

    @pytest.mark.skip(reason=("Production Simulation constraints only apply to individual assets, not their groups."))
    def test_prod_sim_selected_storage_capacity_constraint(self, make_component_with_block_copy_production_simulation):
        """Production Simulation constraints only apply to individual assets, not their groups."""
        super().test_prod_sim_selected_storage_capacity_constraint(make_component_with_block_copy_production_simulation)

    @pytest.mark.skip(reason=("Production Simulation constraints only apply to individual assets, not their groups."))
    def test_prod_sim_retired_storage_capacity_constraint(self, make_component_with_block_copy_production_simulation):
        """Production Simulation constraints only apply to individual assets, not their groups."""
        super().test_prod_sim_retired_storage_capacity_constraint(make_component_with_block_copy_production_simulation)

    @pytest.mark.skip(reason=("Production Simulation constraints only apply to individual assets, not their groups."))
    def test_prod_sim_operational_storage_capacity_constraint(
        self, make_component_with_block_copy_production_simulation
    ):
        """Production Simulation constraints only apply to individual assets, not their groups."""
        super().test_prod_sim_operational_storage_capacity_constraint(
            make_component_with_block_copy_production_simulation
        )
