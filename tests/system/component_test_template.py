import copy
from typing import Type

import pytest

from new_modeling_toolkit.core.component import Component
from new_modeling_toolkit.core.model import ModelTemplate


class ComponentTestTemplate:
    _COMPONENT_CLASS: Type[Component]  # The type of Asset to be instantiated in tests
    _SYSTEM_COMPONENT_DICT_NAME: str  # The name of the attribute dictionary on System that this Asset lives in
    _COMPONENT_NAME: str  # The name of the Asset that is being tested in the example System instance

    @pytest.fixture(scope="class")
    def make_component_copy(self, test_system):
        def _make_copy():
            return getattr(test_system, self._SYSTEM_COMPONENT_DICT_NAME)[self._COMPONENT_NAME].copy(
                include_linkages=True
            )

        return _make_copy

    @pytest.fixture(scope="class")
    def make_component_with_block_copy(self, test_model):
        def _make_copy_with_block(component_name=None):
            if not component_name:
                return copy.deepcopy(getattr(test_model.system, self._SYSTEM_COMPONENT_DICT_NAME)[self._COMPONENT_NAME])
            else:
                return copy.deepcopy(getattr(test_model.system, self._SYSTEM_COMPONENT_DICT_NAME)[component_name])

        return _make_copy_with_block

    @pytest.fixture(scope="class")
    def make_custom_component_with_block(self, test_system, test_temporal_settings):
        def _make_custom_asset(**kwargs):
            system_copy = test_system.copy()
            asset = getattr(system_copy, self._SYSTEM_COMPONENT_DICT_NAME)[self._COMPONENT_NAME]
            for key, value in kwargs.items():
                setattr(asset, key, value)

            # Resample the timeseries attributes of the System to ensure data is interpolated and extrapolated correctly
            #  to cover all required model years and weather years
            modeled_years = test_temporal_settings.modeled_years.data.loc[
                test_temporal_settings.modeled_years.data.values
            ].index
            system_copy.resample_ts_attributes(
                modeled_years=(min(modeled_years).year, max(modeled_years).year),
                weather_years=(
                    min(test_temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
                    max(test_temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
                ),
            )

            # Construct the model
            model = ModelTemplate(
                system=system_copy,
                temporal_settings=test_temporal_settings,
                construct_investment_rules=True,
                construct_operational_rules=True,
                construct_costs=True,
            )

            return asset

        return _make_custom_asset

    @pytest.fixture(scope="class")
    def make_group_component_with_block_copy(self, test_model_with_operational_groups):
        def _make_copy_with_block(component_name=None):
            if not component_name:
                return copy.deepcopy(
                    getattr(test_model_with_operational_groups.system, self._SYSTEM_COMPONENT_DICT_NAME)[
                        self._COMPONENT_NAME
                    ]
                )
            else:
                return copy.deepcopy(
                    getattr(test_model_with_operational_groups.system, self._SYSTEM_COMPONENT_DICT_NAME)[component_name]
                )

        return _make_copy_with_block

    @pytest.fixture(scope="class")
    def make_component_with_block_copy_inter_period_sharing(self, test_model_inter_period_sharing):
        def _make_copy_with_block():
            return copy.deepcopy(
                getattr(test_model_inter_period_sharing.system, self._SYSTEM_COMPONENT_DICT_NAME)[self._COMPONENT_NAME]
            )

        return _make_copy_with_block

    @pytest.fixture(scope="class")
    def make_component_with_block_copy_production_simulation(self, test_model_production_simulation_mode):
        def _make_copy_with_block():
            return copy.deepcopy(
                getattr(test_model_production_simulation_mode.system, self._SYSTEM_COMPONENT_DICT_NAME)[
                    self._COMPONENT_NAME
                ]
            )

        return _make_copy_with_block

    @pytest.fixture(scope="class")
    def first_index(self, test_model):
        """Fixture that returns an example index for the dispatch model, for use in testing."""
        modeled_year = test_model.MODELED_YEARS.first()
        dispatch_window, timestamp = test_model.DISPATCH_WINDOWS_AND_TIMESTAMPS.first()

        return modeled_year, dispatch_window, timestamp

    @pytest.fixture(scope="class")
    def first_index_storage(self, test_model):
        """Fixture that returns an example index for the dispatch model, for use in testing."""
        modeled_year = test_model.MODELED_YEARS.first()
        chrono_period, timestamp = test_model.CHRONO_PERIODS_AND_TIMESTAMPS.first()

        return modeled_year, chrono_period, timestamp

    @pytest.fixture(scope="class")
    def first_index_inter_period_sharing(self, test_model_inter_period_sharing):
        """Fixture that returns an example index for the dispatch model, for use in testing."""
        modeled_year = test_model_inter_period_sharing.MODELED_YEARS.first()
        chrono_period, timestamp = test_model_inter_period_sharing.CHRONO_PERIODS_AND_TIMESTAMPS.first()

        return modeled_year, chrono_period, timestamp

    @pytest.fixture(scope="class")
    def first_index_erm(self, test_model_inter_period_sharing):
        """Fixture that returns an example index for the dispatch model with ERM policy, for use in testing."""
        modeled_year = test_model_inter_period_sharing.MODELED_YEARS.first()
        chrono_period, chrono_timestamp = test_model_inter_period_sharing.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS.first()

        return modeled_year, chrono_period, chrono_timestamp

    @pytest.fixture(scope="class")
    def last_index(self, test_model):
        """Fixture that returns an example index for the dispatch model, for use in testing."""
        modeled_year = test_model.MODELED_YEARS.first()
        dispatch_window, timestamp = test_model.DISPATCH_WINDOWS_AND_TIMESTAMPS.first()
        last_tp = test_model.TIMESTAMPS_IN_DISPATCH_WINDOWS[dispatch_window].prevw(timestamp)

        return modeled_year, dispatch_window, last_tp

    @pytest.fixture(scope="class")
    def last_modeled_year(self, test_model):
        """Fixture that returns an index in the last model year, for use in testing"""
        modeled_year = test_model.MODELED_YEARS.last()
        dispatch_window, timestamp = test_model.DISPATCH_WINDOWS_AND_TIMESTAMPS.last()

        return modeled_year, dispatch_window, timestamp

    @pytest.fixture(scope="class")
    def last_index_erm(self, test_model_inter_period_sharing):
        """Fixture that returns an example index for the dispatch model with ERM policy, for use in testing."""
        modeled_year = test_model_inter_period_sharing.MODELED_YEARS.last()
        chrono_period, chrono_timestamp = test_model_inter_period_sharing.WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS.last()

        return modeled_year, chrono_period, chrono_timestamp
