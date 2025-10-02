import copy

import pandas as pd
import pytest

import new_modeling_toolkit.core.temporal.timeseries as ts
from new_modeling_toolkit.system.electric.load_component import Load
from tests.system.component_test_template import ComponentTestTemplate


class TestLoad(ComponentTestTemplate):
    _COMPONENT_CLASS = Load
    _COMPONENT_NAME = "Load_1"
    _SYSTEM_COMPONENT_DICT_NAME = "loads"

    @pytest.fixture(scope="class")
    def modeled_year_tuple(self, test_temporal_settings):
        return (test_temporal_settings.first_modeled_year, test_temporal_settings.last_modeled_year)

    @pytest.fixture(scope="class")
    def weather_year_tuple(self, test_temporal_settings):
        return (test_temporal_settings.first_weather_year, test_temporal_settings.last_weather_year)

    @pytest.mark.parametrize(
        "scale_by_capacity, scale_by_energy, result_2025, result_2026",
        [
            (False, True, 2190000000, 2920000000),
            (True, False, 2600, 3000),
        ],
    )
    def test_forecast_load(
        self, test_load_1, weather_year_tuple, scale_by_capacity, scale_by_energy, result_2025, result_2026
    ):
        load = test_load_1.copy()
        load.scale_by_energy = scale_by_energy
        load.scale_by_capacity = scale_by_capacity
        load.forecast_load([2025, 2026], weather_year_tuple)
        assert load.model_year_profiles[2025].data.sum() == pytest.approx(result_2025)
        assert load.model_year_profiles[2026].data.sum() == pytest.approx((result_2026 * 0.9))

    @pytest.mark.parametrize(
        "scale_by_capacity, scale_by_energy,custom_scalars, result_2025, result_2026",
        [
            (False, True, [1.2, 1.5], 2190000000 * 1.2, 2920000000 * 1.5),
            (True, False, [1.2, 1.5], 2600, 3000),
        ],
    )
    def test_forecast_load_w_custom_scalars(
        self,
        test_load_1,
        weather_year_tuple,
        scale_by_capacity,
        scale_by_energy,
        custom_scalars,
        result_2025,
        result_2026,
    ):
        load = test_load_1.copy()
        load.scale_by_energy = scale_by_energy
        load.scale_by_capacity = scale_by_capacity
        custom_scalars = pd.Series(
            index=pd.DatetimeIndex(
                [
                    "2025-01-01 00:00",
                    "2026-01-01 00:00",
                ],
                name="timestamp",
            ),
            data=custom_scalars,
        )
        load.forecast_load([2025, 2026], weather_year_tuple, custom_scalars=custom_scalars)
        assert pytest.approx(load.model_year_profiles[2025].data.sum(), rel=1) == result_2025
        assert pytest.approx(load.model_year_profiles[2026].data.sum()) == result_2026 * 0.9

    @pytest.mark.parametrize(
        "to_peak, to_energy, td_losses_adjustment, leap_year, profile_data",
        [
            (False, False, 1.1, False, [1 * 1.1, 2 * 1.1, 3 * 1.1, 2 * 1.1, 1 * 1.1, 1 * 1.1]),
            (False, 3000, 1, False, [600, 1200, 1800, 1200, 600, 600]),
            (3000, False, 1, False, [1200, 2400, 3600, 2400, 1200, 1200]),
            (3000, 3000, 1, False, [1199.80, 2399.93, 3600.07, 2399.93, 1199.79, 1199.79]),
            (3000, 3000, 1, True, [1199.80, 2399.93, 3600.07, 2399.93, 1199.79, 1199.79]),
        ],
    )
    def test_scale_load(self, test_load_1, to_peak, to_energy, td_losses_adjustment, leap_year, profile_data):
        load = test_load_1.copy()
        profile = load.profile
        new_profile = Load.scale_load(
            profile,
            to_peak=to_peak,
            to_energy=to_energy,
            td_losses_adjustment=td_losses_adjustment,
            leap_year=leap_year,
        )
        pd.testing.assert_series_equal(
            new_profile.data,
            pd.Series(index=profile.data.index, data=profile_data),
            check_names=False,
            check_dtype=False,
        )

    @pytest.mark.parametrize(
        "profile_data, sum_before",
        [
            ([2, 3, 5, 3, 4, 3], [10.0 * 365, 12.0 * 365, 20.0 * 365, 30.0 * 365]),
            ([1, 1, 6, 4, 4, 4], [9.6 * 365, 11.52 * 365, 19.2 * 365, 28.8 * 365]),
        ],
    )
    def test_update_load_components(
        self, test_load_1, weather_year_tuple, test_temporal_settings, profile_data, sum_before
    ):
        load = test_load_1.copy()
        load.annual_energy_forecast.data[:] = [10, 11, 12, 20, 30]
        load_profile = ts.NumericTimeseries(
            name="profile",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-06-21 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=profile_data,
                name="value",
            ),
        )

        # setting up test data, `modeled_year_profiles` only exists after calling `forecast_load` or as a direct input
        # load.profile = copy.deepcopy(load_profile)
        load.profile = load_profile
        load.model_year_profiles[2025] = copy.deepcopy(load_profile)
        load.model_year_profiles[2030] = copy.deepcopy(load_profile)
        load.model_year_profiles[2030].data *= 1.2
        load.model_year_profiles[2035] = copy.deepcopy(load_profile)
        load.model_year_profiles[2035].data *= 2
        load.model_year_profiles[2045] = copy.deepcopy(load_profile)
        load.model_year_profiles[2045].data *= 3

        # test profile before scaling
        weighted_sum_before = load._adjusted_hourly_load(test_temporal_settings).groupby(level=0).sum()
        pd.testing.assert_series_equal(
            weighted_sum_before.squeeze(),
            pd.Series(
                index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2035-01-01", "2045-01-01"]), data=sum_before
            ),
            check_exact=False,
            check_names=False,
        )

        load.update_load_components(test_temporal_settings)

        weighted_sum_after = load._adjusted_hourly_load(test_temporal_settings).groupby(level=0).sum()

        pd.testing.assert_series_equal(
            weighted_sum_after.squeeze(),
            pd.Series(
                index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2035-01-01", "2045-01-01"]),
                data=[10.0, 12.0, 20.0, 30.0],
            ),
            check_exact=False,
            check_names=False,
        )

    def test_results_reporting(self, make_component_with_block_copy):
        resource = make_component_with_block_copy()
        resource._construct_output_expressions(construct_costs=True)

        assert resource.formulation_block.load.doc == "Hourly Load (MWh)"
        assert resource.formulation_block.rep_annual_energy.doc == "Representative Annual Energy (MWh)"
        assert resource.formulation_block.annual_energy.doc == "Average Annual Energy (MWh)"
        assert resource.formulation_block.rep_annual_peak.doc == "Representative Annual Peak (MWh)"
        assert resource.formulation_block.annual_peak.doc == "Average Annual Peak (MWh)"

        assert resource.model_fields["scale_by_capacity"].title == "Scale by Median Peak"
        assert resource.model_fields["scale_by_energy"].title == "Scale by Mean Annual Energy"
