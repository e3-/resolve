import pytest

from new_modeling_toolkit.system.electric.resources.hybrid import HybridSolarResource
from new_modeling_toolkit.system.electric.resources.hybrid import HybridSolarResourceGroup
from new_modeling_toolkit.system.electric.resources.hybrid import HybridStorageResource
from new_modeling_toolkit.system.electric.resources.hybrid import HybridStorageResourceGroup
from new_modeling_toolkit.system.electric.resources.hybrid import HybridVariableResource
from new_modeling_toolkit.system.electric.resources.hybrid import HybridVariableResourceGroup
from new_modeling_toolkit.system.electric.resources.hybrid import HybridWindResource
from new_modeling_toolkit.system.electric.resources.hybrid import HybridWindResourceGroup
from tests.system.electric.resources import test_storage
from tests.system.electric.resources import test_variable
from tests.system.electric.resources.test_storage import TestStorageResourceGroup
from tests.system.electric.resources.test_wind import TestWindResource


class TestHybridVariableResource(test_variable.TestVariableResource):
    _COMPONENT_CLASS = HybridVariableResource
    _COMPONENT_NAME = "HybridVariableResource1"
    _SYSTEM_COMPONENT_DICT_NAME = "hybrid_variable_resources"

    def test_hybrid_variable_linkage(self, make_component_with_block_copy):
        hybrid_variable_resource = make_component_with_block_copy()

        hybrid_linkage = hybrid_variable_resource.hybrid_linkage
        assert hybrid_linkage.name == ("HybridStorageResource1", "HybridVariableResource1")
        assert hybrid_linkage.grid_charging_allowed
        assert hybrid_variable_resource.hybrid_linkage.interconnection_limit_mw is not None


class TestHybridStorageResource(test_storage.TestStorageResource):
    _COMPONENT_CLASS = HybridStorageResource
    _COMPONENT_NAME = "HybridStorageResource1"
    _SYSTEM_COMPONENT_DICT_NAME = "hybrid_storage_resources"

    def test_hybrid_storage_linkage(self, make_component_with_block_copy):
        hybrid_storage_resource = make_component_with_block_copy()

        hybrid_linkage = hybrid_storage_resource.hybrid_linkage
        assert hybrid_linkage.name == ("HybridStorageResource1", "HybridVariableResource1")
        assert hybrid_linkage.grid_charging_allowed
        assert hybrid_storage_resource.hybrid_linkage.interconnection_limit_mw is not None

    def test_hybrid_power_output_interconnection_constraint(self, make_component_with_block_copy, first_index):
        """
        Test the hybrid resource interconnection limit constraint. After assigning values to power output and reserves,
        assert that the constraint holds when within limits and fails when exceeded.
        """
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        modeled_year, dispatch_window, timestamp = first_index

        # Test case within limits
        block.power_output[modeled_year, dispatch_window, timestamp].fix(0.1)
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(0.1)

        reserve_name = "TestRegulationUp"
        block.provide_reserve[reserve_name, modeled_year, dispatch_window, timestamp].fix(0.1)
        paired_block.provide_reserve[reserve_name, modeled_year, dispatch_window, timestamp].fix(0.1)

        # Default interconnection limit is 1.0
        assert (
            block.hybrid_power_output_interconnection_constraint[modeled_year, dispatch_window, timestamp].body() == 0.4
        )
        assert (
            block.hybrid_power_output_interconnection_constraint[modeled_year, dispatch_window, timestamp].upper()
            == 1.0
        )
        assert block.hybrid_power_output_interconnection_constraint[modeled_year, dispatch_window, timestamp].expr()

        # Test case exceeding limits
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(0.71)
        assert (
            block.hybrid_power_output_interconnection_constraint[modeled_year, dispatch_window, timestamp].body()
            == 1.01
        )
        assert not block.hybrid_power_output_interconnection_constraint[modeled_year, dispatch_window, timestamp].expr()

    def test_hybrid_power_output_constraint(self, make_component_with_block_copy, first_index):
        """
        Test the hybrid resource operational capacity constraint. After assigning values to power output and reserves,
        assert that the constraint holds when within limits and fails when exceeded.
        """
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        modeled_year, dispatch_window, timestamp = first_index

        # Set operational capacity first if it's a variable (True for resource groups)
        operational_capacity = paired_block.operational_capacity[modeled_year]
        if hasattr(operational_capacity, "fix"):
            operational_capacity.fix(100)

        # Test case within limits
        block.power_output[modeled_year, dispatch_window, timestamp].fix(40)
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(40)

        reserve_name = "TestRegulationUp"
        block.provide_reserve[reserve_name, modeled_year, dispatch_window, timestamp].fix(10)
        paired_block.provide_reserve[reserve_name, modeled_year, dispatch_window, timestamp].fix(10)

        # Default operational capacity is 100
        assert block.hybrid_power_output_constraint[modeled_year, dispatch_window, timestamp].body() == 0
        assert block.hybrid_power_output_constraint[modeled_year, dispatch_window, timestamp].upper() == 0
        assert block.hybrid_power_output_constraint[modeled_year, dispatch_window, timestamp].expr()

        # Test case exceeding limits
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(50)
        assert block.hybrid_power_output_constraint[modeled_year, dispatch_window, timestamp].body() == 10
        assert not block.hybrid_power_output_constraint[modeled_year, dispatch_window, timestamp].expr()

    def test_hybrid_power_input_constraint(self, make_component_with_block_copy, first_index):

        modeled_year, dispatch_window, timestamp = first_index

        # 1) Test constraint for grid_charging_allowed = True
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        paired_block.operational_capacity[modeled_year] = 1.0

        # Upper limit is 0 b/c operational capacity is a variable and we have to subtract it from both sides
        assert block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].upper() == 0

        # Test case within limits
        block.power_input[modeled_year, dispatch_window, timestamp].fix(1.5)
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(0.5)

        assert block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].body() == 1.5 - 0.5 - 1
        assert block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].expr()

        # Test case exceeding limits
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(0)
        assert block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].body() == 1.5 - 0 - 1
        assert not block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].expr()

        # 2) Test constraint for grid_charging_allowed = False
        resource = make_component_with_block_copy(component_name="HybridStorageResource2")
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Upper limit is 0 b/c grid charging is not allowed
        assert block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].upper() == 0

        # Test case within limits
        block.power_input[modeled_year, dispatch_window, timestamp].fix(1.51)
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(1.51)

        assert block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].body() == 0.0
        assert block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].expr()

        # Test case exceeding limits
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(0)
        assert block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].body() == 1.51
        assert not block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].expr()

        # 3) Test constraint for paired charging constraint active in year = False
        resource = make_component_with_block_copy(component_name="HybridStorageResource3")
        block = resource.formulation_block

        # Check if the constraint is skipped by checking if it's in the block's constraints
        assert (modeled_year, dispatch_window, timestamp) not in block.hybrid_power_input_constraint

    def test_hybrid_power_input_interconnection_constraint(self, make_component_with_block_copy, first_index):

        modeled_year, dispatch_window, timestamp = first_index

        # 1) Test constraint for grid_charging_allowed = True
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Default interconnection limit is 1.0
        assert (
            block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].upper() == 1.0
        )

        # Test case within limits
        block.power_input[modeled_year, dispatch_window, timestamp].fix(1.5)
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(0.5)

        assert (
            block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].body()
            == 1.5 - 0.5
        )
        assert block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].expr()

        # Test case exceeding limits
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(0)
        assert (
            block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].body() == 1.5
        )
        assert not block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].expr()

        # 2) Test constraint for grid_charging_allowed = False
        resource = make_component_with_block_copy(component_name="HybridStorageResource2")
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Default interconnection limit x 0 = 0
        assert (
            block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].upper() == 0
        )

        # Test case within limits
        block.power_input[modeled_year, dispatch_window, timestamp].fix(1.51)
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(1.51)

        assert (
            block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].body() == 0.0
        )
        assert block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].expr()

        # Test case exceeding limits
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(0)
        assert (
            block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].body() == 1.51
        )

        # 3) Test constraint for paired charging constraint active in year = False
        resource = make_component_with_block_copy(component_name="HybridStorageResource3")
        block = resource.formulation_block

        # Check if the constraint is skipped by checking if it's in the block's constraints
        assert (modeled_year, dispatch_window, timestamp) not in block.hybrid_power_input_constraint

    def test_hybrid_pairing_ratio_constraint(self, make_component_with_block_copy, first_index):

        modeled_year, _, _ = first_index

        # 1) Test constraint for pairing_ratio = 1
        resource = make_component_with_block_copy()
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Test case where constraint holds
        block.operational_capacity[modeled_year] = 11
        paired_block.operational_capacity[modeled_year] = 11

        assert block.hybrid_pairing_ratio_constraint[modeled_year].expr()
        assert block.hybrid_pairing_ratio_constraint[modeled_year].body() == 0
        assert block.hybrid_pairing_ratio_constraint[modeled_year].upper() == 0
        assert block.hybrid_pairing_ratio_constraint[modeled_year].lower() == 0

        # Test case where constraint does not hold
        paired_block.operational_capacity[modeled_year] = 55

        assert not block.hybrid_pairing_ratio_constraint[modeled_year].expr()
        assert block.hybrid_pairing_ratio_constraint[modeled_year].body() == 44

        # 2) Test constraint for pairing_ratio = 0.95
        resource = make_component_with_block_copy(component_name="HybridStorageResource2")
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Test case where constraint holds
        block.operational_capacity[modeled_year] = 11
        paired_block.operational_capacity[modeled_year] = 11 * 0.95

        assert block.hybrid_pairing_ratio_constraint[modeled_year].expr()
        assert block.hybrid_pairing_ratio_constraint[modeled_year].body() == 0.0
        assert block.hybrid_pairing_ratio_constraint[modeled_year].upper() == 0.0
        assert block.hybrid_pairing_ratio_constraint[modeled_year].lower() == 0.0

        # Test case where constraint does not hold
        paired_block.operational_capacity[modeled_year] = 55

        assert not block.hybrid_pairing_ratio_constraint[modeled_year].expr()
        assert block.hybrid_pairing_ratio_constraint[modeled_year].body() == 44.55

    def test_erm_hybrid_power_output_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        modeled_year, weather_period, weather_timestamp = first_index_erm

        resource = make_component_with_block_copy_inter_period_sharing()
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Immutable values
        multiplier = resource.hybrid_erm_policy_linkage.multiplier.data.at[weather_timestamp]  # 0.9 from conftest.py
        paired_block.operational_capacity[modeled_year] = 1

        # Test where constraint holds
        block.erm_power_output[modeled_year, weather_period, weather_timestamp].fix(0.1)

        # assert block.erm_hybrid_power_output_operational_capacity_constraint[modeled_year, weather_period, weather_timestamp].expr()
        assert (
            block.erm_hybrid_power_output_constraint[modeled_year, weather_period, weather_timestamp].body()
            == 0.1 + 1 * multiplier - 1
        )
        assert block.erm_hybrid_power_output_constraint[modeled_year, weather_period, weather_timestamp].upper() == 0

        # Test where constraint does not hold
        block.erm_power_output[modeled_year, weather_period, weather_timestamp].fix(0.2)

        assert not block.erm_hybrid_power_output_constraint[modeled_year, weather_period, weather_timestamp].expr()
        assert (
            block.erm_hybrid_power_output_constraint[modeled_year, weather_period, weather_timestamp].body()
            == 0.2 + 1 * multiplier - 1
        )
        assert block.erm_hybrid_power_output_constraint[modeled_year, weather_period, weather_timestamp].upper() == 0

    def test_erm_hybrid_power_output_interconnection_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        modeled_year, weather_period, weather_timestamp = first_index_erm

        resource = make_component_with_block_copy_inter_period_sharing()
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Immutable values
        multiplier = resource.hybrid_erm_policy_linkage.multiplier.data.at[weather_timestamp]  # 0.9 from conftest.py
        interconnection_limit = 1.0

        # Set operational capacity first if it's a variable (True for resource groups)
        paired_block.operational_capacity[modeled_year] = 1

        # Test where constraint holds
        block.erm_power_output[modeled_year, weather_period, weather_timestamp].fix(0.1)

        assert block.erm_hybrid_power_output_interconnection_constraint[
            modeled_year, weather_period, weather_timestamp
        ].expr()
        assert (
            block.erm_hybrid_power_output_interconnection_constraint[
                modeled_year, weather_period, weather_timestamp
            ].body()
            == 0.1 + 1 * multiplier
        )
        assert (
            block.erm_hybrid_power_output_interconnection_constraint[
                modeled_year, weather_period, weather_timestamp
            ].upper()
            == interconnection_limit
        )

        # Test where constraint does not hold
        block.erm_power_output[modeled_year, weather_period, weather_timestamp].fix(0.2)

        assert not block.erm_hybrid_power_output_interconnection_constraint[
            modeled_year, weather_period, weather_timestamp
        ].expr()
        assert (
            block.erm_hybrid_power_output_interconnection_constraint[
                modeled_year, weather_period, weather_timestamp
            ].body()
            == 0.2 + 1 * multiplier
        )
        assert (
            block.erm_hybrid_power_output_interconnection_constraint[
                modeled_year, weather_period, weather_timestamp
            ].upper()
            == interconnection_limit
        )

    def test_erm_hybrid_power_input_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        modeled_year, weather_period, weather_timestamp = first_index_erm

        resource = make_component_with_block_copy_inter_period_sharing()
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Immutable values
        multiplier = resource.hybrid_erm_policy_linkage.multiplier.data.at[weather_timestamp]  # 0.9 from conftest.py
        paired_block.operational_capacity[modeled_year] = 1

        # Test where constraint holds
        block.erm_power_input[modeled_year, weather_period, weather_timestamp].fix(1.9)

        assert (
            block.erm_hybrid_power_input_constraint[modeled_year, weather_period, weather_timestamp].body()
            == 1.9 - 1 * multiplier - 1
        )
        assert block.erm_hybrid_power_input_constraint[modeled_year, weather_period, weather_timestamp].upper() == 0

        # Test where constraint does not hold
        block.erm_power_input[modeled_year, weather_period, weather_timestamp].fix(2.0)

        assert not block.erm_hybrid_power_input_constraint[modeled_year, weather_period, weather_timestamp].expr()
        assert (
            block.erm_hybrid_power_input_constraint[modeled_year, weather_period, weather_timestamp].body()
            == 2.0 - 1 * multiplier - 1
        )
        assert block.erm_hybrid_power_input_constraint[modeled_year, weather_period, weather_timestamp].upper() == 0

    def test_erm_hybrid_power_input_interconnection_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        modeled_year, weather_period, weather_timestamp = first_index_erm

        resource = make_component_with_block_copy_inter_period_sharing()
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Immutable values
        multiplier = resource.hybrid_erm_policy_linkage.multiplier.data.at[weather_timestamp]  # 0.9 from conftest.py
        interconnection_limit = resource.hybrid_linkage.interconnection_limit_mw.data.at[
            modeled_year
        ]  # 1.0 from conftest.py
        paired_block.operational_capacity[modeled_year] = 1

        # Test where constraint holds
        block.erm_power_input[modeled_year, weather_period, weather_timestamp].fix(1.9)

        assert block.erm_hybrid_power_input_interconnection_constraint[
            modeled_year, weather_period, weather_timestamp
        ].expr()
        assert (
            block.erm_hybrid_power_input_interconnection_constraint[
                modeled_year, weather_period, weather_timestamp
            ].body()
            == 1.9 - 1 * multiplier
        )
        assert (
            block.erm_hybrid_power_input_interconnection_constraint[
                modeled_year, weather_period, weather_timestamp
            ].upper()
            == interconnection_limit
        )

        # Test where constraint does not hold
        block.erm_power_input[modeled_year, weather_period, weather_timestamp].fix(2.0)

        assert not block.erm_hybrid_power_input_interconnection_constraint[
            modeled_year, weather_period, weather_timestamp
        ].expr()
        assert (
            block.erm_hybrid_power_input_interconnection_constraint[
                modeled_year, weather_period, weather_timestamp
            ].body()
            == 2.0 - 1 * multiplier
        )
        assert (
            block.erm_hybrid_power_input_interconnection_constraint[
                modeled_year, weather_period, weather_timestamp
            ].upper()
            == interconnection_limit
        )

    @pytest.mark.skip(reason="ERM constraint not yet implemented for Hybrid resources")
    def test_erm_power_output_max_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        raise NotImplementedError  # TODO

    @pytest.mark.skip(reason="ERM constraint not yet implemented for Hybrid resources")
    def test_erm_power_input_max_constraint(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        raise NotImplementedError  # TODO

    @pytest.mark.skip(reason="ERM constraint not yet implemented for Hybrid resources")
    def test_erm_net_power_output(
        self,
        make_component_with_block_copy_inter_period_sharing,
        first_index_erm,
    ):
        raise NotImplementedError  # TODO

    @pytest.mark.skip(reason="ERM constraint not yet implemented for Hybrid resources")
    def test_erm_soc_tracking_constraint(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        raise NotImplementedError  # TODO

    @pytest.mark.skip(reason="ERM constraint not yet implemented for Hybrid resources")
    def test_erm_dispatch_cost(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        raise NotImplementedError  # TODO

    @pytest.mark.skip(reason="ERM constraint not yet implemented for Hybrid resources")
    def test_erm_annual_dispatch_cost(self, make_component_with_block_copy_inter_period_sharing, first_index_erm):
        raise NotImplementedError  # TODO


class TestHybridSolarResource(TestHybridVariableResource):
    _COMPONENT_CLASS = HybridSolarResource
    _COMPONENT_NAME = "HybridSolarResource"
    _SYSTEM_COMPONENT_DICT_NAME = "hybrid_solar_resources"

    def test_hybrid_variable_linkage(self, make_component_with_block_copy):
        hybrid_variable_resource = make_component_with_block_copy()

        hybrid_linkage = hybrid_variable_resource.hybrid_linkage
        assert hybrid_linkage.name == ("HybridStorageResource3", "HybridSolarResource")
        assert hybrid_linkage.grid_charging_allowed
        assert hybrid_variable_resource.hybrid_linkage.interconnection_limit_mw is not None


class TestHybridWindResource(TestHybridVariableResource, TestWindResource):
    _COMPONENT_CLASS = HybridWindResource
    _COMPONENT_NAME = "HybridWindResource"
    _SYSTEM_COMPONENT_DICT_NAME = "hybrid_wind_resources"

    def test_hybrid_variable_linkage(self, make_component_with_block_copy):
        hybrid_variable_resource = make_component_with_block_copy()

        hybrid_linkage = hybrid_variable_resource.hybrid_linkage
        assert hybrid_linkage.name == ("HybridStorageResource4", "HybridWindResource")
        assert hybrid_linkage.grid_charging_allowed
        assert hybrid_variable_resource.hybrid_linkage.interconnection_limit_mw is not None


class TestHybridVariableResourceGroup(test_variable.TestVariableResourceGroup, TestHybridVariableResource):
    _COMPONENT_CLASS = HybridVariableResourceGroup
    _COMPONENT_NAME = "TestHybridVariableResourceGroup1"
    _SYSTEM_COMPONENT_DICT_NAME = "hybrid_variable_resource_groups"

    def test_hybrid_variable_linkage(self, make_group_component_with_block_copy):
        hybrid_variable_resource = make_group_component_with_block_copy()

        hybrid_linkage = hybrid_variable_resource.hybrid_linkage
        assert hybrid_linkage.name == ("TestHybridStorageResourceGroup1", "TestHybridVariableResourceGroup1")
        assert hybrid_linkage.grid_charging_allowed
        assert hybrid_variable_resource.hybrid_linkage.interconnection_limit_mw is not None


class TestHybridSolarResourceGroup(TestHybridVariableResourceGroup, TestHybridSolarResource):
    _COMPONENT_CLASS = HybridSolarResourceGroup
    _COMPONENT_NAME = "TestHybridSolarResourceGroup"
    _SYSTEM_COMPONENT_DICT_NAME = "hybrid_solar_resource_groups"

    def test_hybrid_variable_linkage(self, make_group_component_with_block_copy):
        hybrid_variable_resource = make_group_component_with_block_copy()

        hybrid_linkage = hybrid_variable_resource.hybrid_linkage
        assert hybrid_linkage.name == ("TestHybridStorageResourceGroup3", "TestHybridSolarResourceGroup")
        assert hybrid_linkage.grid_charging_allowed
        assert hybrid_variable_resource.hybrid_linkage.interconnection_limit_mw is not None


class TestHybridWindResourceGroup(TestHybridVariableResourceGroup, TestHybridWindResource):
    _COMPONENT_CLASS = HybridWindResourceGroup
    _COMPONENT_NAME = "TestHybridWindResourceGroup"
    _SYSTEM_COMPONENT_DICT_NAME = "hybrid_wind_resource_groups"

    def test_hybrid_variable_linkage(self, make_group_component_with_block_copy):
        hybrid_variable_resource = make_group_component_with_block_copy()

        hybrid_linkage = hybrid_variable_resource.hybrid_linkage
        assert hybrid_linkage.name == ("TestHybridStorageResourceGroup4", "TestHybridWindResourceGroup")
        assert hybrid_linkage.grid_charging_allowed
        assert hybrid_variable_resource.hybrid_linkage.interconnection_limit_mw is not None


class TestHybridStorageResourceGroup(TestStorageResourceGroup, TestHybridStorageResource):
    _COMPONENT_CLASS = HybridStorageResourceGroup
    _COMPONENT_NAME = "TestHybridStorageResourceGroup1"
    _SYSTEM_COMPONENT_DICT_NAME = "hybrid_storage_resource_groups"

    def test_hybrid_storage_linkage(self, make_group_component_with_block_copy):
        hybrid_storage_resource = make_group_component_with_block_copy()

        hybrid_linkage = hybrid_storage_resource.hybrid_linkage
        assert hybrid_linkage.name == ("TestHybridStorageResourceGroup1", "TestHybridVariableResourceGroup1")
        assert hybrid_linkage.grid_charging_allowed
        assert hybrid_storage_resource.hybrid_linkage.interconnection_limit_mw is not None

    def test_hybrid_power_input_constraint(self, make_group_component_with_block_copy, first_index):

        modeled_year, dispatch_window, timestamp = first_index

        # 1) Test constraint for grid_charging_allowed = True
        resource = make_group_component_with_block_copy()
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        paired_block.operational_capacity[modeled_year] = 1.0

        # Upper limit is 0 b/c operational capacity is a variable and we have to subtract it from both sides
        assert block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].upper() == 0

        # Test case within limits
        block.power_input[modeled_year, dispatch_window, timestamp].fix(1.5)
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(0.5)

        assert block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].body() == 1.5 - 0.5 - 1
        assert block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].expr()

        # Test case exceeding limits
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(0)
        assert block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].body() == 1.5 - 0 - 1
        assert not block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].expr()

        # 2) Test constraint for grid_charging_allowed = False
        resource = make_group_component_with_block_copy(component_name="TestHybridStorageResourceGroup2")
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Upper limit is 0 b/c grid charging is not allowed
        assert block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].upper() == 0

        # Test case within limits
        block.power_input[modeled_year, dispatch_window, timestamp].fix(1.51)
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(1.51)

        assert block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].body() == 0.0
        assert block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].expr()

        # Test case exceeding limits
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(0)
        assert block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].body() == 1.51
        assert not block.hybrid_power_input_constraint[modeled_year, dispatch_window, timestamp].expr()

    def test_hybrid_power_input_interconnection_constraint(self, make_group_component_with_block_copy, first_index):

        modeled_year, dispatch_window, timestamp = first_index

        # 1) Test constraint for grid_charging_allowed = True
        resource = make_group_component_with_block_copy()
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Default interconnection limit is 1.0
        assert (
            block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].upper() == 1.0
        )

        # Test case within limits
        block.power_input[modeled_year, dispatch_window, timestamp].fix(1.5)
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(0.5)

        assert (
            block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].body()
            == 1.5 - 0.5
        )
        assert block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].expr()

        # Test case exceeding limits
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(0)
        assert (
            block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].body() == 1.5
        )
        assert not block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].expr()

        # 2) Test constraint for grid_charging_allowed = False
        resource = make_group_component_with_block_copy(component_name="TestHybridStorageResourceGroup2")
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Default interconnection limit x 0 = 0
        assert (
            block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].upper() == 0
        )

        # Test case within limits
        block.power_input[modeled_year, dispatch_window, timestamp].fix(1.51)
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(1.51)

        assert (
            block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].body() == 0.0
        )
        assert block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].expr()

        # Test case exceeding limits
        paired_block.power_output[modeled_year, dispatch_window, timestamp].fix(0)
        assert (
            block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].body() == 1.51
        )
        assert not block.hybrid_power_input_interconnection_constraint[modeled_year, dispatch_window, timestamp].expr()

    def test_erm_hybrid_power_output_interconnection_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        modeled_year, weather_period, weather_timestamp = first_index_erm

        resource = make_component_with_block_copy_inter_period_sharing()
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Immutable values
        multiplier = resource.hybrid_erm_policy_linkage.multiplier.data.at[
            weather_timestamp
        ]  # 0.8 defined in conftest.py
        interconnection_limit = 1.0

        # Set operational capacity first if it's a variable (True for resource groups)
        paired_block.operational_capacity[modeled_year] = 1

        # Test where constraint holds
        block.erm_power_output[modeled_year, weather_period, weather_timestamp].fix(0.2)

        assert block.erm_hybrid_power_output_interconnection_constraint[
            modeled_year, weather_period, weather_timestamp
        ].expr()
        assert (
            block.erm_hybrid_power_output_interconnection_constraint[
                modeled_year, weather_period, weather_timestamp
            ].body()
            == 0.2 + 1 * multiplier
        )
        assert (
            block.erm_hybrid_power_output_interconnection_constraint[
                modeled_year, weather_period, weather_timestamp
            ].upper()
            == interconnection_limit
        )

        # Test where constraint does not hold
        block.erm_power_output[modeled_year, weather_period, weather_timestamp].fix(0.3)

        assert not block.erm_hybrid_power_output_interconnection_constraint[
            modeled_year, weather_period, weather_timestamp
        ].expr()
        assert (
            block.erm_hybrid_power_output_interconnection_constraint[
                modeled_year, weather_period, weather_timestamp
            ].body()
            == 0.3 + 1 * multiplier
        )
        assert (
            block.erm_hybrid_power_output_interconnection_constraint[
                modeled_year, weather_period, weather_timestamp
            ].upper()
            == interconnection_limit
        )

    def test_erm_hybrid_power_output_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        modeled_year, weather_period, weather_timestamp = first_index_erm

        resource = make_component_with_block_copy_inter_period_sharing()
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Immutable values
        multiplier = resource.hybrid_erm_policy_linkage.multiplier.data.at[
            weather_timestamp
        ]  # 0.8 defined in conftest.py
        paired_block.operational_capacity[modeled_year] = 1

        # Test where constraint holds
        block.erm_power_output[modeled_year, weather_period, weather_timestamp] = 0.2

        # assert block.erm_hybrid_power_output_operational_capacity_constraint[modeled_year, weather_period, weather_timestamp].expr()
        assert (
            block.erm_hybrid_power_output_constraint[modeled_year, weather_period, weather_timestamp].body()
            == 0.2 + 1 * multiplier - 1
        )
        assert block.erm_hybrid_power_output_constraint[modeled_year, weather_period, weather_timestamp].upper() == 0

        # Test where constraint does not hold
        block.erm_power_output[modeled_year, weather_period, weather_timestamp] = 0.3

        assert not block.erm_hybrid_power_output_constraint[modeled_year, weather_period, weather_timestamp].expr()
        assert (
            block.erm_hybrid_power_output_constraint[modeled_year, weather_period, weather_timestamp].body()
            == 0.3 + 1 * multiplier - 1
        )
        assert block.erm_hybrid_power_output_constraint[modeled_year, weather_period, weather_timestamp].upper() == 0

    def test_erm_hybrid_power_input_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        modeled_year, weather_period, weather_timestamp = first_index_erm

        resource = make_component_with_block_copy_inter_period_sharing()
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Immutable values
        multiplier = resource.hybrid_erm_policy_linkage.multiplier.data.at[
            weather_timestamp
        ]  # 0.8 defined in conftest.py
        paired_block.operational_capacity[modeled_year] = 1

        # Test where constraint holds
        block.erm_power_input[modeled_year, weather_period, weather_timestamp].fix(1.8)

        assert (
            block.erm_hybrid_power_input_constraint[modeled_year, weather_period, weather_timestamp].body()
            == 1.8 - 1 * multiplier - 1
        )
        assert block.erm_hybrid_power_input_constraint[modeled_year, weather_period, weather_timestamp].upper() == 0

        # Test where constraint does not hold
        block.erm_power_input[modeled_year, weather_period, weather_timestamp].fix(1.9)

        assert not block.erm_hybrid_power_input_constraint[modeled_year, weather_period, weather_timestamp].expr()
        assert (
            block.erm_hybrid_power_input_constraint[modeled_year, weather_period, weather_timestamp].body()
            == 1.9 - 1 * multiplier - 1
        )
        assert block.erm_hybrid_power_input_constraint[modeled_year, weather_period, weather_timestamp].upper() == 0

    def test_erm_hybrid_power_input_interconnection_constraint(
        self, make_component_with_block_copy_inter_period_sharing, first_index_erm
    ):
        modeled_year, weather_period, weather_timestamp = first_index_erm

        resource = make_component_with_block_copy_inter_period_sharing()
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Immutable values
        multiplier = resource.hybrid_erm_policy_linkage.multiplier.data.at[
            weather_timestamp
        ]  # 0.8 defined in conftest.py
        interconnection_limit = resource.hybrid_linkage.interconnection_limit_mw.data.at[modeled_year]  # 1.0
        paired_block.operational_capacity[modeled_year] = 1

        # Test where constraint holds
        block.erm_power_input[modeled_year, weather_period, weather_timestamp].fix(1.8)

        assert block.erm_hybrid_power_input_interconnection_constraint[
            modeled_year, weather_period, weather_timestamp
        ].expr()
        assert (
            block.erm_hybrid_power_input_interconnection_constraint[
                modeled_year, weather_period, weather_timestamp
            ].body()
            == 1.8 - 1 * multiplier
        )
        assert (
            block.erm_hybrid_power_input_interconnection_constraint[
                modeled_year, weather_period, weather_timestamp
            ].upper()
            == interconnection_limit
        )

        # Test where constraint does not hold
        block.erm_power_input[modeled_year, weather_period, weather_timestamp].fix(1.9)

        assert not block.erm_hybrid_power_input_interconnection_constraint[
            modeled_year, weather_period, weather_timestamp
        ].expr()
        assert (
            block.erm_hybrid_power_input_interconnection_constraint[
                modeled_year, weather_period, weather_timestamp
            ].body()
            == 1.9 - 1 * multiplier
        )
        assert (
            block.erm_hybrid_power_input_interconnection_constraint[
                modeled_year, weather_period, weather_timestamp
            ].upper()
            == interconnection_limit
        )

    def test_hybrid_pairing_ratio_constraint(self, make_group_component_with_block_copy, first_index):

        modeled_year, _, _ = first_index

        # 1) Test constraint for pairing_ratio = 1
        resource = make_group_component_with_block_copy()
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Test case where constraint holds
        block.operational_capacity[modeled_year] = 11
        paired_block.operational_capacity[modeled_year] = 11

        assert block.hybrid_pairing_ratio_constraint[modeled_year].expr()
        assert block.hybrid_pairing_ratio_constraint[modeled_year].body() == 0
        assert block.hybrid_pairing_ratio_constraint[modeled_year].upper() == 0
        assert block.hybrid_pairing_ratio_constraint[modeled_year].lower() == 0

        # Test case where constraint does not hold
        paired_block.operational_capacity[modeled_year] = 55

        assert not block.hybrid_pairing_ratio_constraint[modeled_year].expr()
        assert block.hybrid_pairing_ratio_constraint[modeled_year].body() == 44

        # 2) Test constraint for pairing_ratio = 0.95
        resource = make_group_component_with_block_copy(component_name="TestHybridStorageResourceGroup2")
        block = resource.formulation_block
        paired_block = resource.paired_variable_resource.formulation_block

        # Test case where constraint holds
        block.operational_capacity[modeled_year] = 11
        paired_block.operational_capacity[modeled_year] = 11 * 0.95

        assert block.hybrid_pairing_ratio_constraint[modeled_year].expr()
        assert block.hybrid_pairing_ratio_constraint[modeled_year].body() == 0.0
        assert block.hybrid_pairing_ratio_constraint[modeled_year].upper() == 0.0
        assert block.hybrid_pairing_ratio_constraint[modeled_year].lower() == 0.0

        # Test case where constraint does not hold
        paired_block.operational_capacity[modeled_year] = 55

        assert not block.hybrid_pairing_ratio_constraint[modeled_year].expr()
        assert block.hybrid_pairing_ratio_constraint[modeled_year].body() == 44.55
