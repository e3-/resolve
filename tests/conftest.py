import copy
import re

import pandas as pd
import pyomo.environ as pyo
import pytest

import new_modeling_toolkit.core.temporal.timeseries as ts
from new_modeling_toolkit.core.component import Component
from new_modeling_toolkit.core.custom_constraint import CustomConstraintLHS
from new_modeling_toolkit.core.custom_constraint import CustomConstraintRHS
from new_modeling_toolkit.core.linkage import AllToPolicy
from new_modeling_toolkit.core.linkage import AnnualEnergyStandardContribution
from new_modeling_toolkit.core.linkage import AssetToAssetGroup
from new_modeling_toolkit.core.linkage import AssetToELCC
from new_modeling_toolkit.core.linkage import AssetToZone
from new_modeling_toolkit.core.linkage import CandidateFuelToResource
from new_modeling_toolkit.core.linkage import ELCCFacetToSurface
from new_modeling_toolkit.core.linkage import ERMContribution
from new_modeling_toolkit.core.linkage import HybridStorageResourceToHybridVariableResource
from new_modeling_toolkit.core.linkage import LoadToReserve
from new_modeling_toolkit.core.linkage import LoadToZone
from new_modeling_toolkit.core.linkage import ReserveToZone
from new_modeling_toolkit.core.linkage import ResourceToReserve
from new_modeling_toolkit.core.linkage import ResourceToZone
from new_modeling_toolkit.core.linkage import ZoneToTransmissionPath
from new_modeling_toolkit.core.model import ModelTemplate
from new_modeling_toolkit.core.temporal.settings import DispatchWindowEdgeEffects
from new_modeling_toolkit.core.temporal.settings import TemporalSettings
from new_modeling_toolkit.core.three_way_linkage import CustomConstraintLinkage
from new_modeling_toolkit.core.utils.pyomo_utils import convert_pyomo_object_to_dataframe
from new_modeling_toolkit.core.utils.util import DirStructure
from new_modeling_toolkit.resolve.model_formulation import ResolveModel
from new_modeling_toolkit.system import GenericResourceGroup
from new_modeling_toolkit.system import Pollutant
from new_modeling_toolkit.system import System
from new_modeling_toolkit.system.asset import Asset
from new_modeling_toolkit.system.asset import AssetGroup
from new_modeling_toolkit.system.electric.elcc import ELCCFacet
from new_modeling_toolkit.system.electric.elcc import ELCCSurface
from new_modeling_toolkit.system.electric.load_component import Load
from new_modeling_toolkit.system.electric.reserve import Reserve
from new_modeling_toolkit.system.electric.reserve import ReserveDirection
from new_modeling_toolkit.system.electric.resources import GenericResource
from new_modeling_toolkit.system.electric.resources import ThermalResource
from new_modeling_toolkit.system.electric.resources.hybrid import HybridSolarResource
from new_modeling_toolkit.system.electric.resources.hybrid import HybridSolarResourceGroup
from new_modeling_toolkit.system.electric.resources.hybrid import HybridStorageResource
from new_modeling_toolkit.system.electric.resources.hybrid import HybridStorageResourceGroup
from new_modeling_toolkit.system.electric.resources.hybrid import HybridVariableResource
from new_modeling_toolkit.system.electric.resources.hybrid import HybridVariableResourceGroup
from new_modeling_toolkit.system.electric.resources.hybrid import HybridWindResource
from new_modeling_toolkit.system.electric.resources.hybrid import HybridWindResourceGroup
from new_modeling_toolkit.system.electric.resources.hydro import HydroResource
from new_modeling_toolkit.system.electric.resources.hydro import HydroResourceGroup
from new_modeling_toolkit.system.electric.resources.shed_dr import ShedDrResource
from new_modeling_toolkit.system.electric.resources.storage import StorageDurationConstraint
from new_modeling_toolkit.system.electric.resources.storage import StorageResource
from new_modeling_toolkit.system.electric.resources.storage import StorageResourceGroup
from new_modeling_toolkit.system.electric.resources.thermal import ThermalResourceGroup
from new_modeling_toolkit.system.electric.resources.thermal import ThermalUnitCommitmentResource
from new_modeling_toolkit.system.electric.resources.variable.solar import SolarResource
from new_modeling_toolkit.system.electric.resources.variable.solar import SolarResourceGroup
from new_modeling_toolkit.system.electric.resources.variable.wind import WindResource
from new_modeling_toolkit.system.electric.resources.variable.wind import WindResourceGroup
from new_modeling_toolkit.system.electric.tx_path import TxPath
from new_modeling_toolkit.system.electric.tx_path import TxPathGroup
from new_modeling_toolkit.system.electric.zone import Zone
from new_modeling_toolkit.system.fuel.candidate_fuel import CandidateFuel
from new_modeling_toolkit.system.fuel.electrolyzer import Electrolyzer
from new_modeling_toolkit.system.fuel.electrolyzer import ElectrolyzerGroup
from new_modeling_toolkit.system.fuel.fuel_production_plant import FuelProductionPlant
from new_modeling_toolkit.system.fuel.fuel_production_plant import FuelProductionPlantGroup
from new_modeling_toolkit.system.fuel.fuel_storage import FuelStorage
from new_modeling_toolkit.system.fuel.fuel_storage import FuelStorageGroup
from new_modeling_toolkit.system.generics.demand import Demand
from new_modeling_toolkit.system.generics.energy import _EnergyCarrier
from new_modeling_toolkit.system.generics.energy import Electricity
from new_modeling_toolkit.system.generics.energy import EnergyDemand
from new_modeling_toolkit.system.generics.generic_linkages import DemandToProduct
from new_modeling_toolkit.system.generics.generic_linkages import FromZoneToDemand
from new_modeling_toolkit.system.generics.generic_linkages import FromZoneToFuelProductionPlant
from new_modeling_toolkit.system.generics.generic_linkages import FromZoneToFuelStorage
from new_modeling_toolkit.system.generics.generic_linkages import FromZoneToPlant
from new_modeling_toolkit.system.generics.generic_linkages import FromZoneToTransportation
from new_modeling_toolkit.system.generics.generic_linkages import ProductToTransportation
from new_modeling_toolkit.system.generics.generic_linkages import ToZoneToDemand
from new_modeling_toolkit.system.generics.generic_linkages import ToZoneToFuelProductionPlant
from new_modeling_toolkit.system.generics.generic_linkages import ToZoneToFuelStorage
from new_modeling_toolkit.system.generics.generic_linkages import ToZoneToPlant
from new_modeling_toolkit.system.generics.generic_linkages import ToZoneToTransportation
from new_modeling_toolkit.system.generics.generic_linkages import ZoneToProduct
from new_modeling_toolkit.system.generics.plant import Plant
from new_modeling_toolkit.system.generics.plant import PlantGroup
from new_modeling_toolkit.system.generics.process import ChargeProcess
from new_modeling_toolkit.system.generics.process import Process
from new_modeling_toolkit.system.generics.process import SequestrationProcess
from new_modeling_toolkit.system.generics.product import Product
from new_modeling_toolkit.system.generics.transportation import Transportation
from new_modeling_toolkit.system.policy import AnnualEmissionsPolicy
from new_modeling_toolkit.system.policy import AnnualEnergyStandard
from new_modeling_toolkit.system.policy import EnergyReserveMargin
from new_modeling_toolkit.system.policy import HourlyEnergyStandard
from new_modeling_toolkit.system.policy import PlanningReserveMargin
from new_modeling_toolkit.system.pollution.negative_emissions_technology import NegativeEmissionsTechnology
from new_modeling_toolkit.system.pollution.negative_emissions_technology import NegativeEmissionsTechnologyGroup
from new_modeling_toolkit.system.pollution.sequestration import Sequestration
from new_modeling_toolkit.system.pollution.sequestration import SequestrationGroup

collect_ignore = [
    "resolve/test_run_opt.py",
    "system/test_system.py",
    "system/electric/resources/test_unit_commitment.py",
    "system/electric/resources/test_variable.py",
]

#########################
### Helpful functions ###
#########################

_TEST_CASE_NAME = "RECAP_test"


def return_non_zero_df(dispatch_model, resource, component):
    df = convert_pyomo_object_to_dataframe(getattr(dispatch_model.blocks[resource], component))
    df.index = df.index.get_level_values(-1)
    df = df[df.values != 0]
    return df


def print_outputs(dispatch_model):
    for component in pyo.Var, pyo.Expression, pyo.Constraint, pyo.Param:
        components_to_print = list(dispatch_model.component_objects(component, active=True))
        for cp in components_to_print:
            df = convert_pyomo_object_to_dataframe(cp)
            df.to_csv(f"{cp.name}.csv")


@pytest.fixture(scope="session")
def dir_structure():
    dir_str = DirStructure(data_folder="data-test")

    return dir_str


@pytest.fixture(scope="session")
def test_temporal_settings(dir_structure):
    temporal_settings = TemporalSettings.from_dir(
        dir_structure.data_settings_dir / "resolve" / "unit-test-temporal-settings" / "temporal_settings"
    )

    return temporal_settings


@pytest.fixture(scope="session")
def test_results_settings():
    results_settings = {}
    for setting in ["report_raw", "report_hourly", "report_chrono", "disagg_group"]:
        results_settings[setting] = False
    return results_settings


@pytest.fixture(scope="session")
def test_temporal_settings_full_day(dir_structure):
    temporal_settings = TemporalSettings.from_dir(
        dir_structure.data_settings_dir / "resolve" / "unit-test-temporal-settings-full-day" / "temporal_settings"
    )

    return temporal_settings


@pytest.fixture(scope="session")
def test_excel_api():
    from new_modeling_toolkit.core.utils.xlwings import ExcelApiCalls

    return ExcelApiCalls()


@pytest.fixture(scope="session")
def test_model_template(test_excel_api):
    if test_excel_api.platform in ["Darwin", "Windows"]:
        from new_modeling_toolkit.core.excel import ScenarioTool

        return ScenarioTool(book="../E3 Model Template.xlsm")


@pytest.fixture(scope="session")
def test_component():
    return Component(name="Component1")


@pytest.fixture(scope="session")
def test_product_1():
    return Product(name="Product_1", unit="MMBtu")


@pytest.fixture(scope="session")
def test_product_2():
    return Product(name="Product_2", unit="MWh")


@pytest.fixture(scope="session")
def test_commodity_product_1():
    return Product(
        name="CommodityProduct1",
        unit="tonne",
        commodity=True,
        price_per_unit=ts.NumericTimeseries(
            name="price_per_unit",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2025-06-21 01:00",
                        "2025-06-21 02:00",
                        "2025-02-15 12:00",
                        "2025-02-15 13:00",
                        "2025-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=3.0,
                name="value",
            ),
        ),
        availability=ts.NumericTimeseries(
            name="availability",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[100_000, 100_000, 150_000, 150_000],
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_energy_carrier_input():
    return _EnergyCarrier(name="GenericEnergyCarrier1", unit="MMBtu")


@pytest.fixture(scope="session")
def test_energy_carrier_commodity():
    return _EnergyCarrier(
        name="CommodityEnergyCarrier",
        unit="MMBtu",
        commodity=True,
        price_per_unit=ts.NumericTimeseries(
            name="price_per_unit",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2025-06-21 01:00",
                        "2025-06-21 02:00",
                        "2025-02-15 12:00",
                        "2025-02-15 13:00",
                        "2025-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=3.0,
                name="value",
            ),
        ),
        availability=ts.NumericTimeseries(
            name="availability",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[100_000, 100_000, 150_000, 150_000],
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_electricity():
    return Electricity(
        name="Electricity",
    )


@pytest.fixture(scope="session")
def test_product_input2():
    return Product(name="Input2", unit="MMBtu")


@pytest.fixture(scope="session")
def test_product_output2():
    return Product(name="Output2", unit="tonne")


@pytest.fixture(scope="session")
def test_product_3():
    return Product(name="Product_3", unit="tonne")


@pytest.fixture(scope="session")
def test_product_4():
    return Product(name="Product_4", unit="MWh")


@pytest.fixture(scope="session")
def test_pollutant_1():
    return Pollutant(name="Pollutant1", GWP=20)


@pytest.fixture(scope="session")
def test_commodity_product_1():
    return Product(
        name="CommodityProduct1",
        unit="tonne",
        commodity=True,
        price_per_unit=ts.NumericTimeseries(
            name="price_per_unit",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2025-06-21 01:00",
                        "2025-06-21 02:00",
                        "2025-02-15 12:00",
                        "2025-02-15 13:00",
                        "2025-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=3.0,
                name="value",
            ),
        ),
        availability=ts.NumericTimeseries(
            name="availability",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[100_000, 100_000, 150_000, 150_000],
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_asset(test_component: Component):
    return Asset(
        name="GenericAsset1",
        build_year="2025-01-01",
        financial_lifetime=20,
        physical_lifetime=20,
        can_build_new=True,
        can_retire=True,
        potential=300,
        planned_capacity=ts.NumericTimeseries(
            name="planned_capacity",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    ["2025-01-01"],
                    name="timestamp",
                ),
                data=100.0,
                name="value",
            ),
        ),
        annualized_capital_cost=20.0,
        annualized_fixed_om_cost=ts.NumericTimeseries(
            name="annualized_fixed_om_cost",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    ["2025-01-01 00:00:00"],
                    name="timestamp",
                ),
                data=10.0,
            ),
        ),
        min_operational_capacity=ts.NumericTimeseries(
            name="min_cumulative_new_build",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00:00",
                        "2030-01-01 00:00:00",
                        "2035-01-01 00:00:00",
                        "2045-01-01 00:00:00",
                    ],
                    name="timestamp",
                ),
                data=[100.0, 200.0, 200.0, 300.0],
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_generic_resource(test_asset: Asset):
    init_kwargs = test_asset.model_dump()
    init_kwargs.update(
        name="GenericResource1",
        random_seed=1,
        power_output_max=ts.FractionalTimeseries(
            name="power_output_max",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=[1.0, 0.8, 0.5, 0.5, 0.3, 0.7],
                name="value",
            ),
            weather_year=True,
        ),
        power_output_min=ts.FractionalTimeseries(
            name="power_output_min",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=0.10,
                name="value",
            ),
            weather_year=True,
        ),
        outage_profile=ts.FractionalTimeseries(
            name="outage_profile",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=[1.0, 0.0, 0.5, 1.0, 1.0, 1.0],
                name="value",
            ),
        ),
        variable_cost_power_output=ts.NumericTimeseries(
            name="variable_cost_power_output",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=[5.0, 2.5, 6.0, -10.0, 1.0, 3.0],
                name="value",
            ),
            weather_year=True,
        ),
        production_tax_credit=2,
        ptc_term=10,
        energy_budget_daily=ts.FractionalTimeseries(
            name="energy_budget_daily",
            data=pd.Series(
                index=pd.DatetimeIndex(["2010-06-21", "2012-02-15"], name="timestamp"),
                data=[1000 / (400 * 24), 1100 / (400 * 24)],
            ),
            freq_="D",
        ),
        # TODO: test this after implementation
        # energy_budget_monthly=ts.FractionalTimeseries(
        #     name="energy_budget_monthly",
        #     data=pd.Series(
        #         index=pd.DatetimeIndex(["2010-06-01", "2012-02-01"], name="timestamp"),
        #         data=[2000.0 / (400 * 24 * 30), 2500.0 / (400 * 24 * 29)],
        #     ),
        #     freq_="M",
        # ),
        energy_budget_annual=ts.FractionalTimeseries(
            name="energy_budget_annual",
            data=pd.Series(
                index=pd.DatetimeIndex(["2010-01-01", "2012-01-01"], name="timestamp"),
                data=[3000.0 / (400 * 8760), 4000.0 / (400 * 8760)],
            ),
            freq_="YS",
        ),
        ramp_rate_1_hour=0.2,
        ramp_rate_2_hour=0.4,
        ramp_rate_4_hour=0.8,
        allow_inter_period_sharing=True,
    )

    return GenericResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_thermal_resource(test_generic_resource: GenericResource):
    init_kwargs = test_generic_resource.model_dump()
    init_kwargs.update(
        name="ThermalResource1",
        average_heat_rate=2.0,
    )

    return ThermalResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_thermal_resource_2(test_thermal_resource: ThermalResource):
    init_kwargs = test_thermal_resource.model_dump()
    init_kwargs.update(
        name="ThermalResource2",
    )

    return ThermalResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_candidate_fuel_1():
    return CandidateFuel(
        name="CandidateFuel1",
        fuel_is_commodity_bool=True,
        fuel_price_per_mmbtu=ts.NumericTimeseries(
            name="fuel_price_per_mmbtu",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2025-06-21 01:00",
                        "2025-06-21 02:00",
                        "2025-02-15 12:00",
                        "2025-02-15 13:00",
                        "2025-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=3.0,
                name="value",
            ),
        ),
        availability=ts.NumericTimeseries(
            name="availability",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[100_000, 100_000, 150_000, 150_000],
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_candidate_fuel_2():
    return CandidateFuel(
        name="CandidateFuel2",
        fuel_is_commodity_bool=False,
    )


@pytest.fixture(scope="session")
def test_solar_resource(test_generic_resource: GenericResource):
    init_kwargs = test_generic_resource.model_dump()
    init_kwargs.update(
        name="SolarResource1",
        curtailable=True,
        curtailment_cost=ts.NumericTimeseries(
            name="curtailment_cost",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[3.0, 2.0, 1.0, 0.0],
                name="value",
            ),
        ),
    )

    return SolarResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_wind_resource(test_solar_resource: SolarResource):
    init_kwargs = test_solar_resource.model_dump()
    init_kwargs.update(
        name="WindResource1",
        curtailable=True,
        curtailment_cost=ts.NumericTimeseries(
            name="curtailment_cost",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[3.0, 2.0, 1.0, 0.0],
                name="value",
            ),
        ),
    )

    return WindResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_hybrid_variable_resource(test_solar_resource: SolarResource):
    init_kwargs = test_solar_resource.model_dump()
    init_kwargs.update(name="HybridVariableResource1")
    return HybridVariableResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_hybrid_variable_resource_2(test_hybrid_variable_resource: HybridVariableResource):
    init_kwargs = test_hybrid_variable_resource.model_dump()
    init_kwargs.update(name="HybridVariableResource2")
    return HybridVariableResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_hybrid_solar_resource(test_hybrid_variable_resource: HybridVariableResource):
    init_kwargs = test_hybrid_variable_resource.model_dump()
    init_kwargs.update(name="HybridSolarResource")
    return HybridSolarResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_hybrid_wind_resource(test_wind_resource: WindResource):
    init_kwargs = test_wind_resource.model_dump()
    init_kwargs.update(name="HybridWindResource")
    return HybridWindResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_hybrid_storage_resource(test_storage_resource: StorageResource):
    init_kwargs = test_storage_resource.model_dump()
    init_kwargs.update(name="HybridStorageResource1")
    return HybridStorageResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_hybrid_storage_resource_2(test_hybrid_storage_resource: HybridStorageResource):
    init_kwargs = test_hybrid_storage_resource.model_dump()
    init_kwargs.update(name="HybridStorageResource2")
    return HybridStorageResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_hybrid_storage_resource_3(test_hybrid_storage_resource: HybridStorageResource):
    init_kwargs = test_hybrid_storage_resource.model_dump()
    init_kwargs.update(name="HybridStorageResource3")
    return HybridStorageResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_hybrid_storage_resource_4(test_hybrid_storage_resource: HybridStorageResource):
    init_kwargs = test_hybrid_storage_resource.model_dump()
    init_kwargs.update(name="HybridStorageResource4")
    return HybridStorageResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_hydro_resource(test_solar_resource):
    init_kwargs = test_solar_resource.model_dump()
    init_kwargs.update(name="HydroResource1")
    return HydroResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_thermal_unit_commitment_resource(test_generic_resource: GenericResource):
    init_kwargs = test_generic_resource.model_dump()
    init_kwargs.update(
        name="ThermalUnitCommitmentResource",
        unit_commitment_mode="integer",
        planned_capacity=ts.NumericTimeseries(
            name="planned_capacity",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    ["2025-01-01"],
                    name="timestamp",
                ),
                data=100.0,
                name="value",
            ),
        ),
        unit_size=50,
        max_call_duration=4,
        min_stable_level=0.5,
        min_up_time=3,
        min_down_time=3,
        start_cost=5,
        shutdown_cost=10,
        allow_inter_period_sharing=True,
        marginal_heat_rate=1,
        fuel_burn_intercept=1,
        start_fuel_use=2,
        ramp_rate_1_hour=0.4,
        ramp_rate_2_hour=None,
        ramp_rate_3_hour=None,
        ramp_rate_4_hour=None,
    )
    return ThermalUnitCommitmentResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_thermal_unit_commitment_resource_2(test_thermal_unit_commitment_resource):
    # Resource to test synchronous condenser addition to zonal load
    init_kwargs = test_thermal_unit_commitment_resource.model_dump()
    init_kwargs.update(
        name="ThermalUnitCommitmentResource2",
        addition_to_load=4,
    )
    return ThermalUnitCommitmentResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_shed_dr_resource(test_thermal_unit_commitment_resource: ThermalResource):
    init_kwargs = test_thermal_unit_commitment_resource.model_dump()
    init_kwargs.update(
        name="ShedDRResource",
        max_annual_calls=ts.NumericTimeseries(
            name="max_annual_calls",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=365,
                name="value",
            ),
        ),
        max_monthly_calls=None,
        max_daily_calls=ts.NumericTimeseries(
            name="max_daily_calls",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=1,
                name="value",
            ),
        ),
        max_call_duration=3,
        energy_budget_annual=ts.FractionalTimeseries(
            name="energy_budget_annual",
            data=pd.Series(
                index=pd.DatetimeIndex(["2010-01-01", "2012-01-01"], name="timestamp"),
                data=[3000.0 / (400 * 8760), 4000.0 / (400 * 8760)],
            ),
            freq_="YS",
        ),
    )
    return ShedDrResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_shed_dr_resource_no_energy_budget(test_thermal_unit_commitment_resource: ThermalResource):
    init_kwargs = test_thermal_unit_commitment_resource.model_dump()
    init_kwargs.update(
        name="ShedDRResourceNoEnergyBudget",
        max_annual_calls=ts.NumericTimeseries(
            name="max_annual_calls",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=365,
                name="value",
            ),
        ),
        max_monthly_calls=None,
        max_daily_calls=ts.NumericTimeseries(
            name="max_daily_calls",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=1,
                name="value",
            ),
        ),
        max_call_duration=3,
    )
    del init_kwargs["energy_budget_annual"]
    return ShedDrResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_fuel_storage(test_plant):
    init_kwargs = test_plant.model_dump()
    init_kwargs.update(
        primary_product="CandidateFuel2",
        name="FuelStorage1",
        duration=100.0,
        allow_inter_period_sharing=True,
        min_state_of_charge=0.1,
        max_input_profile=ts.FractionalTimeseries(
            name="max_input_profile",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=0.5,
                name="value",
            ),
            weather_year=True,
        ),
        min_input_profile=ts.FractionalTimeseries(
            name="min_input_profile",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=0.1,
                name="value",
            ),
            weather_year=True,
        ),
        variable_cost_input=ts.NumericTimeseries(
            name="variable_cost_input",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=1.0,
                name="value",
            ),
            weather_year=True,
        ),
    )
    return FuelStorage(**init_kwargs)


@pytest.fixture(scope="session")
def test_storage_resource(test_generic_resource: GenericResource):
    init_kwargs = test_generic_resource.model_dump()
    init_kwargs.update(
        name="StorageResource1",
        duration=4.0,
        duration_constraint=StorageDurationConstraint.FIXED,
        allow_inter_period_sharing=True,
        power_input_max=ts.FractionalTimeseries(
            name="power_input_max",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=0.5,
                name="value",
            ),
            weather_year=True,
        ),
        power_input_min=ts.FractionalTimeseries(
            name="power_input_max",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=0.1,
                name="value",
            ),
            weather_year=True,
        ),
        charging_efficiency=ts.FractionalTimeseries(
            name="charging_efficiency",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=0.85,
                name="value",
            ),
        ),
        discharging_efficiency=ts.FractionalTimeseries(
            name="discharging_efficiency",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=0.9,
                name="value",
            ),
        ),
        variable_cost_power_input=ts.NumericTimeseries(
            name="variable_cost_power_input",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=1.0,
                name="value",
            ),
            weather_year=True,
        ),
    )
    return StorageResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_storage_resource_2(test_generic_resource: GenericResource):
    init_kwargs = test_generic_resource.model_dump()
    init_kwargs.update(
        name="StorageResource2",
        duration=4.0,
        allow_inter_period_sharing=True,
        charging_efficiency=ts.FractionalTimeseries(
            name="charging_efficiency",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=0.85,
                name="value",
            ),
        ),
        discharging_efficiency=ts.FractionalTimeseries(
            name="discharging_efficiency",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=0.9,
                name="value",
            ),
        ),
    )
    return StorageResource(**init_kwargs)


@pytest.fixture(scope="session")
def test_reserve_up():
    return Reserve(
        name="TestRegulationUp",
        direction=ReserveDirection.UP,
        exclusive=True,
        load_following_percentage=None,
        requirement=ts.NumericTimeseries(
            name="TestRegulationUp:requirement",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2025-06-21 01:00",
                        "2025-06-21 02:00",
                        "2025-02-15 12:00",
                        "2025-02-15 13:00",
                        "2025-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=10.0,
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_reserve_down():
    return Reserve(
        name="TestRegulationDown",
        direction=ReserveDirection.DOWN,
        exclusive=True,
        load_following_percentage=None,
        requirement=ts.NumericTimeseries(
            name="TestRegulationUp:requirement",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2025-06-21 01:00",
                        "2025-06-21 02:00",
                        "2025-02-15 12:00",
                        "2025-02-15 13:00",
                        "2025-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=10.0,
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_rps():
    return AnnualEnergyStandard(
        name="TestRPS",
        target_basis="sales",
        target_units="relative",
        target=ts.NumericTimeseries(
            name="TestRPS:target",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00:00",
                        "2030-01-01 00:00:00",
                    ],
                    name="timestamp",
                ),
                data=11000,
                name="target",
            ),
        ),
        target_adjustment=ts.NumericTimeseries(
            name="TestRPS:target_adj",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00:00",
                        "2030-01-01 00:00:00",
                    ],
                    name="timestamp",
                ),
                data=0.0,
                name="target_adjustment",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_hourly_ces():
    return HourlyEnergyStandard(
        name="Test_HourlyCES",
        target_basis="sales",
        target_units="relative",
        target=ts.NumericTimeseries(
            name="TestHourlyCES:target",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00:00",
                        "2030-01-01 00:00:00",
                    ],
                    name="timestamp",
                ),
                data=1000,
                name="target",
            ),
        ),
        target_adjustment=ts.NumericTimeseries(
            name="TestHourlyCES:target_adj",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00:00",
                        "2030-01-01 00:00:00",
                    ],
                    name="timestamp",
                ),
                data=0.0,
                name="target_adjustment",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_erm():
    return EnergyReserveMargin(
        name="TestERM",
        # target_basis=,
        target_units="absolute",
        target=ts.NumericTimeseries(
            name="TestERM:target",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00:00",
                        "2030-01-01 00:00:00",
                        "2035-01-01 00:00:00",
                        "2045-01-01 00:00:00",
                    ],
                    name="timestamp",
                ),
                data=[2, 4, 6, 8],
                name="target",
            ),
        ),
        target_adjustment=ts.NumericTimeseries(
            name="TestERM:target_adj",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00:00",
                        "2030-01-01 00:00:00",
                        "2035-01-01 00:00:00",
                        "2045-01-01 00:00:00",
                    ],
                    name="timestamp",
                ),
                data=[0.2, 0.4, 0.6, 0.8],
                name="target_adjustment",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_custom_constraint_lhs():
    return CustomConstraintLHS(
        name="TestLHSProvideReserves",
        pyomo_component_name="provide_reserve",
        additional_index="TestRegulationUp",
        modeled_year_multiplier=ts.NumericTimeseries(
            name="modeled_year_multiplier",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2030-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[0.25, 1.5],
                name="value",
            ),
        ),
        weather_year_hourly_multiplier=ts.NumericTimeseries(
            name="modeled_year_multiplier",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=[0.8, 0.9, 1.0, 1.1, 1.2, 1.3],
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_custom_constraint_lhs_annual():
    return CustomConstraintLHS(
        name="TestLHSOperationalCapacity",
        pyomo_component_name="operational_capacity",
        modeled_year_multiplier=ts.NumericTimeseries(
            name="modeled_year_multiplier",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2030-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[0.5, 0.75],
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_custom_constraint_rhs():
    return CustomConstraintRHS(
        name="TestRHSHourly",
        constraint_operator="==",
        annual_target=ts.NumericTimeseries(
            name="modeled_year_multiplier",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2030-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[5, 0],
                name="value",
            ),
        ),
        weather_year_hourly_target=ts.NumericTimeseries(
            name="modeled_year_multiplier",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=[0.8, 0.9, 1.0, 1.1, 1.2, 1.3],
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_custom_constraint_rhs_annual():
    return CustomConstraintRHS(
        name="TestRHSAnnual",
        constraint_operator="==",
        annual_target=ts.NumericTimeseries(
            name="modeled_year_multiplier",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2030-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[5, 0],
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_zone_1():
    return Zone(name="Zone_1")


@pytest.fixture(scope="session")
def test_zone_2():
    return Zone(name="Zone_2")


@pytest.fixture(scope="session")
def test_zone_3():
    return Zone(name="Zone_3")


@pytest.fixture(scope="session")
def test_transportation_1(test_asset: Asset):
    init_kwargs = test_asset.model_dump()
    init_kwargs.update(
        name="Transportation_1",
    )
    return Transportation(**init_kwargs)


@pytest.fixture(scope="session")
def test_transportation_2(test_asset: Asset):
    init_kwargs = test_asset.model_dump()
    init_kwargs.update(
        name="Transportation_2",
    )
    return Transportation(**init_kwargs)


@pytest.fixture(scope="session")
def test_plant(test_asset: Asset):
    init_kwargs = test_asset.model_dump()
    init_kwargs.update(
        primary_product="Product_2",
        name="Plant1",
        min_output_profile=ts.FractionalTimeseries(
            name="minimum output profile",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=0.1,
                name="value",
            ),
        ),
        max_output_profile=ts.FractionalTimeseries(
            name="maximum output profile",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=0.9,
                name="value",
            ),
        ),
        variable_cost=ts.NumericTimeseries(
            name="Variable O&M cost per MWh generated.",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=10,
                name="value",
            ),
        ),
        production_tax_credit=2,
        ptc_term=10,
    )
    return Plant(**init_kwargs)


@pytest.fixture(scope="session")
def test_plant_with_input_output_capture(test_plant):
    init_kwargs = test_plant.model_dump()
    init_kwargs.update(name="PlantWithInputOutputCapture")
    return Plant(**init_kwargs)


@pytest.fixture(scope="session")
def test_fuel_production_plant(test_plant: Plant):
    init_kwargs = test_plant.model_dump()
    init_kwargs.update(
        primary_product="CandidateFuel2",
        name="FuelProductionPlant1",
    )
    return FuelProductionPlant(**init_kwargs)


@pytest.fixture(scope="session")
def test_negative_emissions_technology(test_plant, test_pollutant_1):
    init_kwargs = test_plant.model_dump()
    init_kwargs.update(
        primary_product=test_pollutant_1.name,
        name="NegativeEmissionsTechnology1",
    )
    return NegativeEmissionsTechnology(**init_kwargs)


@pytest.fixture(scope="session")
def test_sequestration(test_negative_emissions_technology):
    init_kwargs = test_negative_emissions_technology.model_dump()
    init_kwargs.update(
        name="Sequestration1",
    )
    return Sequestration(**init_kwargs)


@pytest.fixture(scope="session")
def test_sequestration_2(test_sequestration):
    init_kwargs = test_sequestration.model_dump()
    init_kwargs.update(
        name="Sequestration2",
    )
    return Sequestration(**init_kwargs)


@pytest.fixture(scope="session")
def test_electrolyzer(test_fuel_production_plant: FuelProductionPlant):
    init_kwargs = test_fuel_production_plant.model_dump()
    init_kwargs.update(name="Electrolyzer1")
    return Electrolyzer(**init_kwargs)


@pytest.fixture(scope="session")
def test_tx_path(test_asset: Asset):
    init_kwargs = test_asset.model_dump()
    init_kwargs.update(
        name="TxPath",
        forward_rating_profile=ts.FractionalTimeseries(
            name="forward_rating_profile",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=1.0,
                name="value",
            ),
        ),
        reverse_rating_profile=ts.FractionalTimeseries(
            name="reverse_rating_profile",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=1.0,
                name="value",
            ),
        ),
        hurdle_rate_forward_direction=ts.NumericTimeseries(
            name="hurdle_rate_forward_direction",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=4.0,
                name="value",
            ),
        ),
        hurdle_rate_reverse_direction=ts.NumericTimeseries(
            name="hurdle_rate_reverse_direction",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=5.0,
                name="value",
            ),
        ),
    )

    return TxPath(**init_kwargs)


@pytest.fixture(scope="session")
def test_tx_path_2(test_tx_path: TxPath):
    init_kwargs = test_tx_path.model_dump()
    init_kwargs.update(
        name="TxPath2",
    )

    return TxPath(**init_kwargs)


@pytest.fixture(scope="session")
def test_generic_demand_1():
    return Demand(
        name="GenericDemand1",
        annual_energy_forecast=ts.NumericTimeseries(
            name="annual_energy_forecast",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[3000000.0 * 365, 4000000.0 * 365, 4000000.0 * 365, 4000000.0 * 365, 4000000.0 * 365],
                name="value",
            ),
        ),
        annual_peak_forecast=ts.NumericTimeseries(
            name="annual_peak_forecast",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[650.0, 750.0, 750.0, 750.0, 750.0],
                name="value",
            ),
        ),
        td_losses_adjustment=ts.NumericTimeseries(
            name="td_losses_adjustment",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[1, 0.9, 1, 1, 1],
                name="value",
            ),
        ),
        scale_by_capacity=False,
        scale_by_energy=True,
        profile=ts.NumericTimeseries(
            name="profile",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=[1, 2, 3, 2, 1, 1],
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_generic_demand_2():
    return Demand(
        name="GenericDemand2",
        annual_energy_forecast=ts.NumericTimeseries(
            name="annual_energy_forecast",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[3000000.0 * 365, 4000000.0 * 365, 4000000.0 * 365, 4000000.0 * 365, 4000000.0 * 365],
                name="value",
            ),
        ),
        annual_peak_forecast=ts.NumericTimeseries(
            name="annual_peak_forecast",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[650.0, 750.0, 750.0, 750.0, 750.0],
                name="value",
            ),
        ),
        td_losses_adjustment=ts.NumericTimeseries(
            name="td_losses_adjustment",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[1, 0.9, 1, 1, 1],
                name="value",
            ),
        ),
        scale_by_capacity=False,
        scale_by_energy=True,
        profile=ts.NumericTimeseries(
            name="profile",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=[1, 2, 3, 2, 1, 1],
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_generic_energy_demand_1():
    return EnergyDemand(
        name="GenericEnergyDemand1",
        annual_energy_forecast=ts.NumericTimeseries(
            name="annual_energy_forecast",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[3000000.0 * 365, 4000000.0 * 365, 4000000.0 * 365, 4000000.0 * 365, 4000000.0 * 365],
                name="value",
            ),
        ),
        annual_peak_forecast=ts.NumericTimeseries(
            name="annual_peak_forecast",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[650.0, 750.0, 750.0, 750.0, 750.0],
                name="value",
            ),
        ),
        td_losses_adjustment=ts.NumericTimeseries(
            name="td_losses_adjustment",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[1, 0.9, 1, 1, 1],
                name="value",
            ),
        ),
        scale_by_capacity=False,
        scale_by_energy=True,
        profile=ts.NumericTimeseries(
            name="profile",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=[1, 2, 3, 2, 1, 1],
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_generic_energy_demand_2(test_generic_energy_demand_1):
    init_kwargs = test_generic_energy_demand_1.model_dump()
    init_kwargs.update(name="GenericEnergyDemand2")
    return EnergyDemand(**init_kwargs)


@pytest.fixture(scope="session")
def test_load_1():
    return Load(
        name="Load_1",
        annual_energy_forecast=ts.NumericTimeseries(
            name="annual_energy_forecast",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[3000000.0 * 365, 4000000.0 * 365, 4000000.0 * 365, 4000000.0 * 365, 4000000.0 * 365],
                name="value",
            ),
        ),
        annual_peak_forecast=ts.NumericTimeseries(
            name="annual_peak_forecast",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[650.0, 750.0, 750.0, 750.0, 750.0],
                name="value",
            ),
        ),
        td_losses_adjustment=ts.NumericTimeseries(
            name="td_losses_adjustment",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[1, 0.9, 1, 1, 1],
                name="value",
            ),
        ),
        scale_by_capacity=False,
        scale_by_energy=True,
        profile=ts.NumericTimeseries(
            name="profile",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=[1, 2, 3, 2, 1, 1],
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_EV_load_1():
    return Load(
        name="EV_Load_1",
        annual_energy_forecast=ts.NumericTimeseries(
            name="annual_energy_forecast",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[300.0, 400.0, 400.0, 400.0, 400.0],
                name="value",
            ),
        ),
        annual_peak_forecast=ts.NumericTimeseries(
            name="annual_peak_forecast",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[6.5, 7.5, 7.5, 7.5, 7.5],
                name="value",
            ),
        ),
        td_losses_adjustment=ts.NumericTimeseries(
            name="td_losses_adjustment",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[1, 0.9, 1, 1, 1],
                name="value",
            ),
        ),
        scale_by_capacity=False,
        scale_by_energy=True,
        profile=ts.NumericTimeseries(
            name="profile",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=[1, 2, 3, 2, 1, 1],
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_load_2():
    return Load(
        name="Load_2",
        annual_energy_forecast=ts.NumericTimeseries(
            name="annual_energy_forecast",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[300000.0 * 365, 400000.0 * 365, 400000.0 * 365, 400000.0 * 365, 400000.0 * 365],
                name="value",
            ),
        ),
        annual_peak_forecast=ts.NumericTimeseries(
            name="annual_peak_forecast",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[65.0, 75.0, 75.0, 75.0, 75.0],
                name="value",
            ),
        ),
        td_losses_adjustment=ts.NumericTimeseries(
            name="td_losses_adjustment",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00",
                        "2026-01-01 00:00",
                        "2030-01-01 00:00",
                        "2035-01-01 00:00",
                        "2045-01-01 00:00",
                    ],
                    name="timestamp",
                ),
                data=[1, 0.9, 1, 1, 1],
                name="value",
            ),
        ),
        scale_by_capacity=False,
        scale_by_energy=True,
        profile=ts.NumericTimeseries(
            name="profile",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2010-01-01 00:00",
                        "2010-06-21 01:00",
                        "2010-06-21 02:00",
                        "2012-02-15 12:00",
                        "2012-02-15 13:00",
                        "2012-02-15 14:00",
                    ],
                    name="timestamp",
                ),
                data=[1, 2, 3, 2, 1, 1],
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_ghg_policy():
    return AnnualEmissionsPolicy(
        name="TestGHG",
        target=ts.NumericTimeseries(
            name="target",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00:00",
                        "2030-01-01 00:00:00",
                        "2035-01-01 00:00:00",
                        "2045-01-01 00:00:00",
                    ],
                    name="timestamp",
                ),
                data=3,
                name="value",
            ),
        ),
        target_adjustment=ts.NumericTimeseries(
            name="target_adjustment",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00:00",
                        "2030-01-01 00:00:00",
                        "2035-01-01 00:00:00",
                        "2045-01-01 00:00:00",
                    ],
                    name="timestamp",
                ),
                data=1,
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_prm_policy():
    return PlanningReserveMargin(
        name="TestPRM",
        target_units="absolute",
        target=ts.NumericTimeseries(
            name="target",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00:00",
                        "2030-01-01 00:00:00",
                        "2035-01-01 00:00:00",
                        "2045-01-01 00:00:00",
                    ],
                    name="timestamp",
                ),
                data=1000,
                name="value",
            ),
        ),
        target_adjustment=ts.NumericTimeseries(
            name="target_adjustment",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00:00",
                        "2030-01-01 00:00:00",
                        "2035-01-01 00:00:00",
                        "2045-01-01 00:00:00",
                    ],
                    name="timestamp",
                ),
                data=-10,
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_elcc_facet():
    return ELCCFacet(
        name="test_elcc_facet",
        axis_0=ts.NumericTimeseries(
            name="axis_0",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00:00",
                        "2030-01-01 00:00:00",
                        "2035-01-01 00:00:00",
                        "2045-01-01 00:00:00",
                    ],
                    name="timestamp",
                ),
                data=[0.0, 0.0, 5.0, 5.0],
                name="value",
            ),
        ),
        axis_1=ts.NumericTimeseries(
            name="axis_1",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00:00",
                        "2030-01-01 00:00:00",
                        "2035-01-01 00:00:00",
                        "2045-01-01 00:00:00",
                    ],
                    name="timestamp",
                ),
                data=[20.0, 15.0, 10.0, 5.0],
                name="value",
            ),
        ),
    )


@pytest.fixture(scope="session")
def test_elcc_surface():
    return ELCCSurface(name="TestELCCSurface")


@pytest.fixture(scope="session")
def test_asset_group():
    return AssetGroup(
        name="AssetGroup1",
        potential=ts.NumericTimeseries(
            name="potential",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00:00",
                        "2030-01-01 00:00:00",
                        "2035-01-01 00:00:00",
                        "2045-01-01 00:00:00",
                    ],
                    name="timestamp",
                ),
                data=[600.0, 700.0, 800.0, 900.0],
            ),
        ),
        cumulative_potential=ts.NumericTimeseries(
            name="cumulative_potential",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00:00",
                        "2030-01-01 00:00:00",
                        "2035-01-01 00:00:00",
                        "2045-01-01 00:00:00",
                    ],
                    name="timestamp",
                ),
                data=[600.0, 700.0, 800.0, 900.0],
            ),
        ),
        min_cumulative_new_build=ts.NumericTimeseries(
            name="min_cumulative_new_build",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00:00",
                        "2030-01-01 00:00:00",
                        "2035-01-01 00:00:00",
                        "2045-01-01 00:00:00",
                    ],
                    name="timestamp",
                ),
                data=[100.0, 150.0, 200.0, 250.0],
            ),
        ),
        min_operational_capacity=ts.NumericTimeseries(
            name="min_operational_capacity",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    [
                        "2025-01-01 00:00:00",
                        "2030-01-01 00:00:00",
                        "2035-01-01 00:00:00",
                        "2045-01-01 00:00:00",
                    ],
                    name="timestamp",
                ),
                data=[200.0, 300.0, 400.0, 500.0],
            ),
        ),
        annualized_capital_cost=ts.NumericTimeseries(
            name="annualized_capital_cost",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    ["2025-01-01 00:00:00"],
                    name="timestamp",
                ),
                data=20.0,
            ),
        ),
        annualized_fixed_om_cost=ts.NumericTimeseries(
            name="annualized_fixed_om_cost",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    ["2025-01-01 00:00:00"],
                    name="timestamp",
                ),
                data=10.0,
            ),
        ),
    )

@pytest.fixture(scope="session")
def test_tx_path_group(test_asset_group, test_tx_path):
    init_kwargs = test_asset_group.model_dump(
        include={
            "build_year",
            "potential",
            "cumulative_potential",
            "min_cumulative_new_build",
            "min_operational_capacity",
            "annualized_capital_cost",
            "annualized_fixed_om_cost",
        }
    )
    init_kwargs.update(name="tx_path_group_0", aggregate_operations=True)
    for attr_name, attr_value in test_tx_path.model_dump().items():
        if attr_name not in init_kwargs:
            init_kwargs[attr_name] = attr_value

    return TxPathGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_generic_resource_group(test_asset_group, test_generic_resource):
    init_kwargs = test_asset_group.model_dump(
        include={
            "build_year",
            "potential",
            "cumulative_potential",
            "min_cumulative_new_build",
            "min_operational_capacity",
            "annualized_capital_cost",
            "annualized_fixed_om_cost",
        }
    )
    init_kwargs.update(
        test_generic_resource.model_dump(
            include={
                "random_seed",
                "stochastic_outage_rate",
                "mean_time_to_repair",
                "variable_cost_power_output",
                "variable_cost_power_input",
                "power_output_min",
                "power_output_max",
                "power_input_max",
                "power_input_min",
                "outage_profile",
                "energy_budget_daily",
                "energy_budget_monthly",
                "energy_budget_annual",
                "ramp_rate_1_hour",
                "ramp_rate_2_hour",
                "ramp_rate_3_hour",
                "ramp_rate_4_hour",
                "allow_inter_period_sharing",
            }
        )
    )
    init_kwargs.update(name="generic_resource_group_0", aggregate_operations=True)
    for attr_name, attr_value in test_generic_resource.model_dump().items():
        if attr_name not in init_kwargs:
            init_kwargs[attr_name] = attr_value

    return GenericResourceGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_thermal_resource_group(test_generic_resource_group, test_thermal_resource):
    init_kwargs = test_generic_resource_group.model_dump()
    init_kwargs.update(name="thermal_resource_group_0")
    for attr_name, attr_value in test_thermal_resource.model_dump().items():
        if attr_name not in init_kwargs:
            init_kwargs[attr_name] = attr_value

    return ThermalResourceGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_solar_resource_group(test_generic_resource_group, test_solar_resource):
    init_kwargs = test_generic_resource_group.model_dump()
    init_kwargs.update(name="solar_resource_group_0")
    for attr_name, attr_value in test_solar_resource.model_dump().items():
        if attr_name not in init_kwargs:
            init_kwargs[attr_name] = attr_value

    return SolarResourceGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_wind_resource_group(test_generic_resource_group, test_wind_resource):
    init_kwargs = test_generic_resource_group.model_dump()
    init_kwargs.update(name="wind_resource_group_0")
    for attr_name, attr_value in test_wind_resource.model_dump().items():
        if attr_name not in init_kwargs:
            init_kwargs[attr_name] = attr_value

    return WindResourceGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_hybrid_variable_resource_group(test_generic_resource_group, test_hybrid_variable_resource):
    init_kwargs = test_generic_resource_group.model_dump()
    init_kwargs.update(name="TestHybridVariableResourceGroup1")
    for attr_name, attr_value in test_hybrid_variable_resource.model_dump().items():
        if attr_name not in init_kwargs:
            init_kwargs[attr_name] = attr_value
    return HybridVariableResourceGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_hybrid_variable_resource_group_2(test_hybrid_variable_resource_group):
    init_kwargs = test_hybrid_variable_resource_group.model_dump()
    init_kwargs.update(name="TestHybridVariableResourceGroup2")
    return HybridVariableResourceGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_hybrid_solar_resource_group(test_hybrid_variable_resource_group):
    init_kwargs = test_hybrid_variable_resource_group.model_dump()
    init_kwargs.update(name="TestHybridSolarResourceGroup")
    return HybridSolarResourceGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_hybrid_wind_resource_group(test_wind_resource_group, test_hybrid_wind_resource):
    init_kwargs = test_wind_resource_group.model_dump()
    init_kwargs.update(name="TestHybridWindResourceGroup")
    for attr_name, attr_value in test_hybrid_wind_resource.model_dump().items():
        if attr_name not in init_kwargs:
            init_kwargs[attr_name] = attr_value
    return HybridWindResourceGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_hybrid_storage_resource_group(test_storage_resource_group, test_hybrid_storage_resource):
    init_kwargs = test_storage_resource_group.model_dump()
    init_kwargs.update(name="TestHybridStorageResourceGroup1")
    for attr_name, attr_value in test_hybrid_storage_resource.model_dump().items():
        if attr_name not in init_kwargs:
            init_kwargs[attr_name] = attr_value
    return HybridStorageResourceGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_hybrid_storage_resource_group_2(test_hybrid_storage_resource_group):
    init_kwargs = test_hybrid_storage_resource_group.model_dump()
    init_kwargs.update(name="TestHybridStorageResourceGroup2")
    return HybridStorageResourceGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_hybrid_storage_resource_group_3(test_hybrid_storage_resource_group):
    init_kwargs = test_hybrid_storage_resource_group.model_dump()
    init_kwargs.update(name="TestHybridStorageResourceGroup3")
    return HybridStorageResourceGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_hybrid_storage_resource_group_4(test_hybrid_storage_resource_group):
    init_kwargs = test_hybrid_storage_resource_group.model_dump()
    init_kwargs.update(name="TestHybridStorageResourceGroup4")
    return HybridStorageResourceGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_hydro_resource_group(test_solar_resource_group, test_hydro_resource):
    init_kwargs = test_solar_resource_group.model_dump()
    init_kwargs.update(name="hydro_resource_group_0")
    for attr_name, attr_value in test_hydro_resource.model_dump().items():
        if attr_name not in init_kwargs:
            init_kwargs.update(attr_name=attr_value)

    return HydroResourceGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_storage_resource_group(test_generic_resource_group, test_storage_resource):
    init_kwargs = test_generic_resource_group.model_dump()
    init_kwargs.update(
        name="storage_resource_group_0",
        annualized_storage_capital_cost=ts.NumericTimeseries(
            name="annualized_storage_capital_cost",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    ["2025-01-01 00:00:00"],
                    name="timestamp",
                ),
                data=0.0,
            ),
        ),
        annualized_storage_fixed_om_cost=ts.NumericTimeseries(
            name="annualized_storage_fixed_om_cost",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    ["2025-01-01 00:00:00"],
                    name="timestamp",
                ),
                data=0.0,
            ),
        ),
    )
    for attr_name, attr_value in test_storage_resource.model_dump().items():
        if attr_name not in init_kwargs:
            init_kwargs[attr_name] = attr_value

    return StorageResourceGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_plant_group(test_asset_group, test_plant):
    init_kwargs = test_asset_group.model_dump(
        include={
            "build_year",
            "potential",
            "cumulative_potential",
            "min_cumulative_new_build",
            "min_operational_capacity",
            "annualized_capital_cost",
            "annualized_fixed_om_cost",
        }
    )
    init_kwargs.update(
        test_plant.model_dump(
            include={
                "random_seed",
                "stochastic_outage_rate",
                "mean_time_to_repair",
                "primary_product" "ramp_up_limit",
                "ramp_down_limit",
                "min_output_profile",
                "max_output_profile",
                "variable_cost",
            }
        )
    )
    init_kwargs.update(name="generic_plant_group", aggregate_operations=True)
    for attr_name, attr_value in test_plant.model_dump().items():
        if attr_name not in init_kwargs:
            init_kwargs[attr_name] = attr_value

    return PlantGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_fuel_production_plant_group(test_plant_group, test_fuel_production_plant):
    init_kwargs = test_plant_group.model_dump()
    init_kwargs.update(name="fuel_production_plant_group", primary_product="CandidateFuel2")
    for attr_name, attr_value in test_fuel_production_plant.model_dump().items():
        if attr_name not in init_kwargs:
            init_kwargs[attr_name] = attr_value

    return FuelProductionPlantGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_electrolyzer_group(test_fuel_production_plant_group, test_electrolyzer):
    init_kwargs = test_fuel_production_plant_group.model_dump()
    init_kwargs.update(name="electrolyzer_group", primary_product="CandidateFuel2")
    for attr_name, attr_value in test_electrolyzer.model_dump().items():
        if attr_name not in init_kwargs:
            init_kwargs[attr_name] = attr_value

    return ElectrolyzerGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_fuel_storage_group(test_fuel_production_plant_group, test_fuel_storage):
    init_kwargs = test_fuel_production_plant_group.model_dump()
    init_kwargs.update(
        name="fuel_storage_group",
        annualized_storage_capital_cost=ts.NumericTimeseries(
            name="annualized_storage_capital_cost",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    ["2025-01-01 00:00:00"],
                    name="timestamp",
                ),
                data=0.0,
            ),
        ),
        annualized_storage_fixed_om_cost=ts.NumericTimeseries(
            name="annualized_storage_fixed_om_cost",
            data=pd.Series(
                index=pd.DatetimeIndex(
                    ["2025-01-01 00:00:00"],
                    name="timestamp",
                ),
                data=0.0,
            ),
        ),
    )
    for attr_name, attr_value in test_fuel_storage.model_dump().items():
        if attr_name not in init_kwargs:
            init_kwargs[attr_name] = attr_value

    return FuelStorageGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_negative_emissions_technology_group(test_plant_group, test_negative_emissions_technology):
    init_kwargs = test_plant_group.model_dump()
    init_kwargs.update(name="negative_emissions_technology_group", primary_product="Pollutant1")
    for attr_name, attr_value in test_negative_emissions_technology.model_dump().items():
        if attr_name not in init_kwargs:
            init_kwargs[attr_name] = attr_value

    return NegativeEmissionsTechnologyGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_sequestration_group(test_plant_group, test_sequestration):
    init_kwargs = test_plant_group.model_dump()
    init_kwargs.update(name="sequestration_group", primary_product="Pollutant1")
    for attr_name, attr_value in test_sequestration.model_dump().items():
        if attr_name not in init_kwargs:
            init_kwargs[attr_name] = attr_value

    return SequestrationGroup(**init_kwargs)


@pytest.fixture(scope="session")
def test_system(
    dir_structure: DirStructure,
    test_asset,
    test_generic_resource,
    test_hydro_resource,
    test_thermal_resource,
    test_thermal_resource_2,
    test_solar_resource,
    test_wind_resource,
    test_storage_resource,
    test_storage_resource_2,
    test_hybrid_variable_resource,
    test_hybrid_storage_resource,
    test_hybrid_variable_resource_2,
    test_hybrid_storage_resource_2,
    test_hybrid_solar_resource,
    test_hybrid_storage_resource_3,
    test_hybrid_wind_resource,
    test_hybrid_storage_resource_4,
    test_thermal_unit_commitment_resource,
    test_thermal_unit_commitment_resource_2,
    test_shed_dr_resource,
    test_shed_dr_resource_no_energy_budget,
    test_reserve_up,
    test_reserve_down,
    test_zone_1,
    test_zone_2,
    test_zone_3,
    test_transportation_1,
    test_transportation_2,
    test_tx_path,
    test_generic_demand_1,
    test_generic_demand_2,
    test_generic_energy_demand_1,
    test_generic_energy_demand_2,
    test_plant,
    test_plant_with_input_output_capture,
    test_fuel_storage,
    test_fuel_production_plant,
    test_electrolyzer,
    test_negative_emissions_technology,
    test_sequestration,
    test_sequestration_2,
    test_product_1,
    test_product_2,
    test_product_3,
    test_product_4,
    test_product_input2,
    test_product_output2,
    test_commodity_product_1,
    test_energy_carrier_input,
    test_electricity,
    test_energy_carrier_commodity,
    test_pollutant_1,
    test_tx_path_2,
    test_load_1,
    test_EV_load_1,
    test_load_2,
    test_rps,
    test_ghg_policy,
    test_hourly_ces,
    test_prm_policy,
    test_elcc_surface,
    test_elcc_facet,
    test_candidate_fuel_1,
    test_candidate_fuel_2,
    test_custom_constraint_lhs,
    test_custom_constraint_rhs,
    test_custom_constraint_rhs_annual,
    test_custom_constraint_lhs_annual,
    test_erm,
):
    test_asset = test_asset.copy()
    test_generic_resource = test_generic_resource.copy()
    test_hydro_resource = test_hydro_resource.copy()
    test_thermal_resource = test_thermal_resource.copy()
    test_thermal_resource_2 = test_thermal_resource_2.copy()
    test_solar_resource = test_solar_resource.copy()
    test_wind_resource = test_wind_resource.copy()
    test_storage_resource = test_storage_resource.copy()
    test_storage_resource_2 = test_storage_resource_2.copy()
    test_hybrid_variable_resource = test_hybrid_variable_resource.copy()
    test_hybrid_storage_resource = test_hybrid_storage_resource.copy()
    test_hybrid_variable_resource_2 = test_hybrid_variable_resource_2.copy()
    test_hybrid_storage_resource_2 = test_hybrid_storage_resource_2.copy()
    test_hybrid_solar_resource = test_hybrid_solar_resource.copy()
    test_hybrid_storage_resource_3 = test_hybrid_storage_resource_3.copy()
    test_hybrid_wind_resource = test_hybrid_wind_resource.copy()
    test_hybrid_storage_resource_4 = test_hybrid_storage_resource_4.copy()
    test_thermal_unit_commitment_resource = test_thermal_unit_commitment_resource.copy()
    test_thermal_unit_commitment_resource_2 = test_thermal_unit_commitment_resource_2.copy()
    test_reserve_up = test_reserve_up.copy()
    test_reserve_down = test_reserve_down.copy()
    test_zone_1 = test_zone_1.copy()
    test_zone_2 = test_zone_2.copy()
    test_zone_3 = test_zone_3.copy()
    test_transportation_1 = test_transportation_1.copy()
    test_transportation_2 = test_transportation_2.copy()
    test_plant = test_plant.copy()
    test_plant_with_input_output_capture = test_plant_with_input_output_capture.copy()
    test_fuel_storage = test_fuel_storage.copy()
    test_fuel_production_plant = test_fuel_production_plant.copy()
    test_electrolyzer = test_electrolyzer.copy()
    test_negative_emissions_technology = test_negative_emissions_technology.copy()
    test_sequestration = test_sequestration.copy()
    test_sequestration_2 = test_sequestration_2.copy()
    test_generic_demand_1 = test_generic_demand_1.copy()
    test_generic_demand_2 = test_generic_demand_2.copy()
    test_product_1 = test_product_1.copy()
    test_product_2 = test_product_2.copy()
    test_product_3 = test_product_3.copy()
    test_product_4 = test_product_4.copy()
    test_generic_energy_demand_1 = test_generic_energy_demand_1.copy()
    test_generic_energy_demand_2 = test_generic_energy_demand_2.copy()
    test_product_input2 = test_product_input2.copy()
    test_product_output2 = test_product_output2.copy()
    test_commodity_product_1 = test_commodity_product_1.copy()
    test_energy_carrier_input = test_energy_carrier_input.copy()
    test_electricity = test_electricity.copy()
    test_energy_carrier_commodity = test_energy_carrier_commodity.copy()
    test_pollutant_1 = test_pollutant_1.copy()
    test_tx_path = test_tx_path.copy()
    test_tx_path_2 = test_tx_path_2.copy()
    test_load_1 = test_load_1.copy()
    test_EV_load_1 = test_EV_load_1.copy()
    test_load_2 = test_load_2.copy()
    test_rps = test_rps.copy()
    test_ghg_policy = test_ghg_policy.copy()
    test_hourly_ces = test_hourly_ces.copy()
    test_prm_policy = test_prm_policy.copy()
    test_elcc_surface = test_elcc_surface.copy()
    test_candidate_fuel_1 = test_candidate_fuel_1.copy()
    test_candidate_fuel_2 = test_candidate_fuel_2.copy()
    test_custom_constraint_rhs = test_custom_constraint_rhs.copy()
    test_custom_constraint_rhs_annual = test_custom_constraint_rhs_annual.copy()
    test_custom_constraint_lhs = test_custom_constraint_lhs.copy()
    test_custom_constraint_lhs_annual = test_custom_constraint_lhs_annual.copy()
    test_erm = test_erm.copy()

    system = System(
        name="test_system",
        dir_str=dir_structure,
        assets={
            test_asset.name: test_asset,
            test_generic_resource.name: test_generic_resource,
            test_thermal_resource.name: test_thermal_resource,
            test_thermal_resource_2.name: test_thermal_resource_2,
            test_solar_resource.name: test_solar_resource,
            test_wind_resource.name: test_wind_resource,
            test_hydro_resource.name: test_hydro_resource,
            test_storage_resource.name: test_storage_resource,
            test_storage_resource_2.name: test_storage_resource_2,
            test_hybrid_variable_resource.name: test_hybrid_variable_resource,
            test_hybrid_storage_resource.name: test_hybrid_storage_resource,
            test_hybrid_variable_resource_2.name: test_hybrid_variable_resource_2,
            test_hybrid_storage_resource_2.name: test_hybrid_storage_resource_2,
            test_hybrid_solar_resource.name: test_hybrid_solar_resource,
            test_hybrid_storage_resource_3.name: test_hybrid_storage_resource_3,
            test_hybrid_wind_resource.name: test_hybrid_wind_resource,
            test_hybrid_storage_resource_4.name: test_hybrid_storage_resource_4,
            test_thermal_unit_commitment_resource.name: test_thermal_unit_commitment_resource,
            test_thermal_unit_commitment_resource_2.name: test_thermal_unit_commitment_resource_2,
            test_shed_dr_resource.name: test_shed_dr_resource,
            test_shed_dr_resource_no_energy_budget.name: test_shed_dr_resource_no_energy_budget,
            test_tx_path.name: test_tx_path,
            test_tx_path_2.name: test_tx_path_2,
            test_transportation_1.name: test_transportation_1,
            test_transportation_2.name: test_transportation_2,
            test_plant.name: test_plant,
            test_plant_with_input_output_capture.name: test_plant_with_input_output_capture,
            test_fuel_storage.name: test_fuel_storage,
            test_fuel_production_plant.name: test_fuel_production_plant,
            test_electrolyzer.name: test_electrolyzer,
            test_negative_emissions_technology.name: test_negative_emissions_technology,
            test_sequestration.name: test_sequestration,
            test_sequestration_2.name: test_sequestration_2,
        },
        reserves={test_reserve_up.name: test_reserve_up, test_reserve_down.name: test_reserve_down},
        annual_energy_policies={test_rps.name: test_rps},
        emissions_policies={test_ghg_policy.name: test_ghg_policy},
        prm_policies={test_prm_policy.name: test_prm_policy},
        elcc_surfaces={test_elcc_surface.name: test_elcc_surface},
        elcc_facets={test_elcc_facet.name: test_elcc_facet},
        hourly_energy_policies={test_hourly_ces.name: test_hourly_ces},
        erm_policies={test_erm.name: test_erm},
        zones={
            test_zone_1.name: test_zone_1,
            test_zone_2.name: test_zone_2,
            test_zone_3.name: test_zone_3,
        },
        products={
            test_candidate_fuel_1.name: test_candidate_fuel_1,
            test_candidate_fuel_2.name: test_candidate_fuel_2,
            test_product_1.name: test_product_1,
            test_product_2.name: test_product_2,
            test_product_3.name: test_product_3,
            test_product_4.name: test_product_4,
            test_product_input2.name: test_product_input2,
            test_product_output2.name: test_product_output2,
            test_commodity_product_1.name: test_commodity_product_1,
            test_energy_carrier_input.name: test_energy_carrier_input,
            test_energy_carrier_commodity.name: test_energy_carrier_commodity,
            test_electricity.name: test_electricity,
            test_pollutant_1.name: test_pollutant_1,
        },
        demands={
            test_generic_energy_demand_1.name: test_generic_energy_demand_1,
            test_generic_energy_demand_2.name: test_generic_energy_demand_2,
            test_generic_demand_1.name: test_generic_demand_1,
            test_generic_demand_2.name: test_generic_demand_2,
        },
        loads={
            test_load_1.name: test_load_1,
            test_EV_load_1.name: test_EV_load_1,
            test_load_2.name: test_load_2,
        },
        custom_constraints_rhs={
            test_custom_constraint_rhs.name: test_custom_constraint_rhs,
            test_custom_constraint_rhs_annual.name: test_custom_constraint_rhs_annual,
        },
        custom_constraints_lhs={
            test_custom_constraint_lhs.name: test_custom_constraint_lhs,
            test_custom_constraint_lhs_annual.name: test_custom_constraint_lhs_annual,
        },
        linkages={
            "AssetToZone": [
                AssetToZone(
                    name=(test_asset.name, test_zone_1.name),
                    instance_from=test_asset,
                    instance_to=test_zone_1,
                ),
            ],
            "AssetToELCC": [
                AssetToELCC(
                    name=(test_solar_resource.name, test_elcc_surface.name),
                    instance_from=test_solar_resource,
                    instance_to=test_elcc_surface,
                    elcc_axis_index=1,
                    elcc_axis_multiplier=0.25,
                ),
                AssetToELCC(
                    name=(test_storage_resource_2.name, test_elcc_surface.name),
                    instance_from=test_storage_resource_2,
                    instance_to=test_elcc_surface,
                    elcc_axis_index=1,
                    elcc_axis_multiplier=0.15,
                ),
            ],
            "ELCCFacetToSurface": [
                ELCCFacetToSurface(
                    name=(test_elcc_facet.name, test_elcc_surface.name),
                    instance_from=test_elcc_facet,
                    instance_to=test_elcc_surface,
                ),
            ],
            "HybridStorageResourceToHybridVariableResource": [
                HybridStorageResourceToHybridVariableResource(
                    name=(test_hybrid_storage_resource.name, test_hybrid_variable_resource.name),
                    instance_from=test_hybrid_storage_resource,
                    instance_to=test_hybrid_variable_resource,
                    grid_charging_allowed=True,
                    interconnection_limit_mw=ts.NumericTimeseries(
                        name="interconnection_limit_mw",
                        data=pd.Series(
                            index=pd.DatetimeIndex(
                                [
                                    "2025-01-01 00:00",
                                    "2030-01-01 00:00",
                                    "2035-01-01 00:00",
                                    "2045-01-01 00:00",
                                ],
                                name="timestamp",
                            ),
                            data=[1, 2, 3, 4],
                            name="value",
                        ),
                    ),
                    pairing_ratio=1,
                ),
                HybridStorageResourceToHybridVariableResource(
                    name=(test_hybrid_storage_resource_2.name, test_hybrid_variable_resource_2.name),
                    instance_from=test_hybrid_storage_resource_2,
                    instance_to=test_hybrid_variable_resource_2,
                    grid_charging_allowed=False,
                    interconnection_limit_mw=ts.NumericTimeseries(
                        name="interconnection_limit_mw",
                        data=pd.Series(
                            index=pd.DatetimeIndex(
                                [
                                    "2025-01-01 00:00",
                                    "2030-01-01 00:00",
                                    "2035-01-01 00:00",
                                    "2045-01-01 00:00",
                                ],
                                name="timestamp",
                            ),
                            data=[1, 2, 3, 4],
                            name="value",
                        ),
                    ),
                    pairing_ratio=0.95,
                ),
                HybridStorageResourceToHybridVariableResource(
                    name=(test_hybrid_storage_resource_3.name, test_hybrid_solar_resource.name),
                    instance_from=test_hybrid_storage_resource_3,
                    instance_to=test_hybrid_solar_resource,
                    grid_charging_allowed=True,
                    interconnection_limit_mw=ts.NumericTimeseries(
                        name="interconnection_limit_mw",
                        data=pd.Series(
                            index=pd.DatetimeIndex(
                                [
                                    "2025-01-01 00:00",
                                    "2030-01-01 00:00",
                                    "2035-01-01 00:00",
                                    "2045-01-01 00:00",
                                ],
                                name="timestamp",
                            ),
                            data=[1, 2, 3, 4],
                            name="value",
                        ),
                    ),
                    pairing_ratio=1,
                    paired_charging_constraint_active_in_year=ts.NumericTimeseries(
                        name="paired_charging_constraint_active_in_year",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2025-01-01 00:00"]),
                            data=[0],
                        ),
                    ),
                ),
                HybridStorageResourceToHybridVariableResource(
                    name=(test_hybrid_storage_resource_4.name, test_hybrid_wind_resource.name),
                    instance_from=test_hybrid_storage_resource_4,
                    instance_to=test_hybrid_wind_resource,
                    grid_charging_allowed=True,
                    interconnection_limit_mw=ts.NumericTimeseries(
                        name="interconnection_limit_mw",
                        data=pd.Series(
                            index=pd.DatetimeIndex(
                                [
                                    "2025-01-01 00:00",
                                    "2030-01-01 00:00",
                                    "2035-01-01 00:00",
                                    "2045-01-01 00:00",
                                ],
                                name="timestamp",
                            ),
                            data=[1, 2, 3, 4],
                            name="value",
                        ),
                    ),
                    pairing_ratio=1,
                ),
            ],
            "ResourceToZone": [
                ResourceToZone(
                    name=(test_hydro_resource.name, test_zone_1.name),
                    instance_from=test_hydro_resource,
                    instance_to=test_zone_1,
                ),
                ResourceToZone(
                    name=(test_generic_resource.name, test_zone_1.name),
                    instance_from=test_generic_resource,
                    instance_to=test_zone_1,
                ),
                ResourceToZone(
                    name=(test_thermal_resource.name, test_zone_1.name),
                    instance_from=test_thermal_resource,
                    instance_to=test_zone_1,
                ),
                ResourceToZone(
                    name=(test_solar_resource.name, test_zone_1.name),
                    instance_from=test_solar_resource,
                    instance_to=test_zone_1,
                ),
                ResourceToZone(
                    name=(test_storage_resource.name, test_zone_1.name),
                    instance_from=test_storage_resource,
                    instance_to=test_zone_1,
                ),
                ResourceToZone(
                    name=(test_thermal_unit_commitment_resource.name, test_zone_1.name),
                    instance_from=test_thermal_unit_commitment_resource,
                    instance_to=test_zone_1,
                ),
                ResourceToZone(
                    name=(test_thermal_unit_commitment_resource_2.name, test_zone_1.name),
                    instance_from=test_thermal_unit_commitment_resource_2,
                    instance_to=test_zone_1,
                ),
                ResourceToZone(
                    name=(test_shed_dr_resource.name, test_zone_1.name),
                    instance_from=test_shed_dr_resource,
                    instance_to=test_zone_1,
                ),
            ],
            "ResourceToReserve": [
                ResourceToReserve(
                    name=(test_hydro_resource.name, test_reserve_up.name),
                    instance_from=test_hydro_resource,
                    instance_to=test_reserve_up,
                ),
                ResourceToReserve(
                    name=(test_generic_resource.name, test_reserve_up.name),
                    instance_from=test_generic_resource,
                    instance_to=test_reserve_up,
                ),
                ResourceToReserve(
                    name=(test_thermal_resource.name, test_reserve_up.name),
                    instance_from=test_thermal_resource,
                    instance_to=test_reserve_up,
                ),
                ResourceToReserve(
                    name=(test_thermal_unit_commitment_resource.name, test_reserve_up.name),
                    instance_from=test_thermal_unit_commitment_resource,
                    instance_to=test_reserve_up,
                ),
                ResourceToReserve(
                    name=(test_solar_resource.name, test_reserve_up.name),
                    instance_from=test_solar_resource,
                    instance_to=test_reserve_up,
                    incremental_requirement_hourly_scalar=ts.NumericTimeseries(
                        name="incremental_requirement_hourly_scalar",
                        data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=0.9),
                    ),
                ),
                ResourceToReserve(
                    name=(test_wind_resource.name, test_reserve_up.name),
                    instance_from=test_wind_resource,
                    instance_to=test_reserve_up,
                ),
                ResourceToReserve(
                    name=(test_storage_resource.name, test_reserve_up.name),
                    instance_from=test_storage_resource,
                    instance_to=test_reserve_up,
                ),
                ResourceToReserve(
                    name=(test_hybrid_variable_resource.name, test_reserve_up.name),
                    instance_from=test_hybrid_variable_resource,
                    instance_to=test_reserve_up,
                ),
                ResourceToReserve(
                    name=(test_hybrid_solar_resource.name, test_reserve_up.name),
                    instance_from=test_hybrid_solar_resource,
                    instance_to=test_reserve_up,
                ),
                ResourceToReserve(
                    name=(test_hybrid_wind_resource.name, test_reserve_up.name),
                    instance_from=test_hybrid_wind_resource,
                    instance_to=test_reserve_up,
                ),
                ResourceToReserve(
                    name=(test_hybrid_storage_resource.name, test_reserve_up.name),
                    instance_from=test_hybrid_storage_resource,
                    instance_to=test_reserve_up,
                ),
                ResourceToReserve(
                    name=(test_shed_dr_resource.name, test_reserve_up.name),
                    instance_from=test_shed_dr_resource,
                    instance_to=test_reserve_up,
                ),
                ResourceToReserve(
                    name=(test_hydro_resource.name, test_reserve_down.name),
                    instance_from=test_hydro_resource,
                    instance_to=test_reserve_down,
                ),
                ResourceToReserve(
                    name=(test_generic_resource.name, test_reserve_down.name),
                    instance_from=test_generic_resource,
                    instance_to=test_reserve_down,
                ),
                ResourceToReserve(
                    name=(test_thermal_resource.name, test_reserve_down.name),
                    instance_from=test_thermal_resource,
                    instance_to=test_reserve_down,
                ),
                ResourceToReserve(
                    name=(test_thermal_unit_commitment_resource.name, test_reserve_down.name),
                    instance_from=test_thermal_unit_commitment_resource,
                    instance_to=test_reserve_down,
                ),
                ResourceToReserve(
                    name=(test_solar_resource.name, test_reserve_down.name),
                    instance_from=test_solar_resource,
                    instance_to=test_reserve_down,
                ),
                ResourceToReserve(
                    name=(test_wind_resource.name, test_reserve_down.name),
                    instance_from=test_wind_resource,
                    instance_to=test_reserve_down,
                ),
                ResourceToReserve(
                    name=(test_storage_resource.name, test_reserve_down.name),
                    instance_from=test_storage_resource,
                    instance_to=test_reserve_down,
                ),
                ResourceToReserve(
                    name=(test_hybrid_variable_resource.name, test_reserve_down.name),
                    instance_from=test_hybrid_variable_resource,
                    instance_to=test_reserve_down,
                ),
                ResourceToReserve(
                    name=(test_hybrid_solar_resource.name, test_reserve_down.name),
                    instance_from=test_hybrid_solar_resource,
                    instance_to=test_reserve_down,
                ),
                ResourceToReserve(
                    name=(test_hybrid_wind_resource.name, test_reserve_down.name),
                    instance_from=test_hybrid_wind_resource,
                    instance_to=test_reserve_down,
                ),
                ResourceToReserve(
                    name=(test_hybrid_storage_resource.name, test_reserve_down.name),
                    instance_from=test_hybrid_storage_resource,
                    instance_to=test_reserve_down,
                ),
                ResourceToReserve(
                    name=(test_shed_dr_resource.name, test_reserve_down.name),
                    instance_from=test_shed_dr_resource,
                    instance_to=test_reserve_down,
                ),
            ],
            "ZoneToTransmissionPath": [
                ZoneToTransmissionPath(
                    name=(test_zone_1.name, test_tx_path.name),
                    instance_from=test_zone_1,
                    instance_to=test_tx_path,
                    from_zone=True,
                ),
                ZoneToTransmissionPath(
                    name=(test_zone_2.name, test_tx_path.name),
                    instance_from=test_zone_2,
                    instance_to=test_tx_path,
                    to_zone=True,
                ),
                ZoneToTransmissionPath(
                    name=(test_zone_1.name, test_tx_path_2.name),
                    instance_from=test_zone_1,
                    instance_to=test_tx_path_2,
                    from_zone=True,
                ),
                ZoneToTransmissionPath(
                    name=(test_zone_2.name, test_tx_path_2.name),
                    instance_from=test_zone_2,
                    instance_to=test_tx_path_2,
                    to_zone=True,
                ),
            ],
            "LoadToZone": [
                LoadToZone(
                    name=(test_load_1.name, test_zone_1.name),
                    instance_from=test_load_1,
                    instance_to=test_zone_1,
                ),
                LoadToZone(
                    name=(test_load_2.name, test_zone_2.name),
                    instance_from=test_load_2,
                    instance_to=test_zone_2,
                ),
                LoadToZone(
                    name=(test_EV_load_1.name, test_zone_1.name),
                    instance_from=test_EV_load_1,
                    instance_to=test_zone_1,
                ),
            ],
            "LoadToReserve": [
                LoadToReserve(
                    name=(test_load_2.name, test_reserve_up.name),
                    instance_from=test_load_2,
                    instance_to=test_reserve_up,
                    incremental_requirement_hourly_scalar=ts.FractionalTimeseries(
                        name="incremental_requirement_hourly_scalar",
                        data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=0.9),
                    ),
                )
            ],
            "ReserveToZone": [
                ReserveToZone(
                    name=(test_reserve_up.name, test_zone_1.name),
                    instance_from=test_reserve_up,
                    instance_to=test_zone_1,
                    incremental_requirement_hourly_scalar=ts.FractionalTimeseries(
                        name="incremental_requirement_hourly_scalar",
                        data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=0.9),
                    ),
                )
            ],
            "CandidateFuelToResource": [
                CandidateFuelToResource(
                    name=(test_candidate_fuel_1.name, test_thermal_resource.name),
                    instance_from=test_candidate_fuel_1,
                    instance_to=test_thermal_resource,
                ),
                CandidateFuelToResource(
                    name=(test_candidate_fuel_2.name, test_thermal_resource.name),
                    instance_from=test_candidate_fuel_2,
                    instance_to=test_thermal_resource,
                ),
                CandidateFuelToResource(
                    name=(test_candidate_fuel_1.name, test_thermal_unit_commitment_resource.name),
                    instance_from=test_candidate_fuel_1,
                    instance_to=test_thermal_unit_commitment_resource,
                ),
                CandidateFuelToResource(
                    name=(test_candidate_fuel_2.name, test_thermal_unit_commitment_resource.name),
                    instance_from=test_candidate_fuel_2,
                    instance_to=test_thermal_unit_commitment_resource,
                ),
                CandidateFuelToResource(
                    name=(test_candidate_fuel_2.name, test_thermal_unit_commitment_resource_2.name),
                    instance_from=test_candidate_fuel_2,
                    instance_to=test_thermal_unit_commitment_resource_2,
                ),
                CandidateFuelToResource(
                    name=(test_candidate_fuel_1.name, test_thermal_resource_2.name),
                    instance_from=test_candidate_fuel_1,
                    instance_to=test_thermal_resource_2,
                ),
            ],
            "ERMContribution": [
                ERMContribution(
                    name=(test_solar_resource.name, test_erm.name),
                    instance_from=test_solar_resource,
                    instance_to=test_erm,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2010-01-01 00:00"]),
                            data=0.5,
                        ),
                        weather_year=True,
                    ),
                ),
                ERMContribution(
                    name=(test_storage_resource.name, test_erm.name),
                    instance_from=test_storage_resource,
                    instance_to=test_erm,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2010-01-01 00:00"]),
                            data=0.9,
                        ),
                        weather_year=True,
                    ),
                ),
                ERMContribution(
                    name=(test_hybrid_storage_resource.name, test_erm.name),
                    instance_from=test_hybrid_storage_resource,
                    instance_to=test_erm,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2010-01-01 00:00"]),
                            data=0.9,
                        ),
                        weather_year=True,
                    ),
                ),
                ERMContribution(
                    name=(test_hybrid_variable_resource.name, test_erm.name),
                    instance_from=test_hybrid_variable_resource,
                    instance_to=test_erm,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2010-01-01 00:00"]),
                            data=0.8,
                        ),
                        weather_year=True,
                    ),
                ),
                ERMContribution(
                    name=(test_shed_dr_resource.name, test_erm.name),
                    instance_from=test_shed_dr_resource,
                    instance_to=test_erm,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2010-01-01 00:00"]),
                            data=0.9,
                        ),
                        weather_year=True,
                    ),
                ),
                ERMContribution(
                    name=(test_shed_dr_resource_no_energy_budget.name, test_erm.name),
                    instance_from=test_shed_dr_resource_no_energy_budget,
                    instance_to=test_erm,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2010-01-01 00:00"]),
                            data=0.9,
                        ),
                        weather_year=True,
                    ),
                ),
                ERMContribution(
                    name=(test_tx_path.name, test_erm.name),
                    instance_from=test_tx_path,
                    instance_to=test_erm,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2010-01-01 00:00"]),
                            data=0.9,
                        ),
                        weather_year=True,
                    ),
                ),
                ERMContribution(
                    name=(test_asset.name, test_erm.name),
                    instance_from=test_asset,
                    instance_to=test_erm,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2010-01-01 00:00"]),
                            data=0.9,
                        ),
                        weather_year=True,
                    ),
                ),
            ],
            "AllToPolicy": [
                AllToPolicy(
                    name=(test_solar_resource.name, test_rps.name),
                    instance_from=test_solar_resource,
                    instance_to=test_rps,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[1.0, 1.0]),
                    ),
                ),
                AnnualEnergyStandardContribution(
                    name=(test_candidate_fuel_1.name, test_rps.name),
                    instance_from=test_candidate_fuel_1,
                    instance_to=test_rps,
                    multiplier=None,
                ),
                AnnualEnergyStandardContribution(
                    name=(test_thermal_resource.name, test_rps.name),
                    instance_from=test_thermal_resource,
                    instance_to=test_rps,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[1.0, 1.0]),
                    ),
                ),
                AnnualEnergyStandardContribution(
                    name=(test_thermal_unit_commitment_resource.name, test_rps.name),
                    instance_from=test_thermal_unit_commitment_resource,
                    instance_to=test_rps,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[1.0, 1.0]),
                    ),
                ),
                AllToPolicy(
                    name=(test_thermal_resource.name, test_prm_policy.name),
                    instance_from=test_thermal_resource,
                    instance_to=test_prm_policy,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[0.95, 0.95]),
                    ),
                ),
                AllToPolicy(
                    name=(test_asset.name, test_prm_policy.name),
                    instance_from=test_asset,
                    instance_to=test_prm_policy,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[0.95, 0.95]),
                    ),
                ),
                AllToPolicy(
                    name=(test_solar_resource.name, test_prm_policy.name),
                    instance_from=test_solar_resource,
                    instance_to=test_prm_policy,
                    multiplier=None,
                ),
                AllToPolicy(
                    name=(test_storage_resource.name, test_prm_policy.name),
                    instance_from=test_storage_resource,
                    instance_to=test_prm_policy,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[0.95, 0.95]),
                    ),
                    fully_deliverable=False,
                ),
                AllToPolicy(
                    name=(test_storage_resource_2.name, test_prm_policy.name),
                    instance_from=test_storage_resource_2,
                    instance_to=test_prm_policy,
                    multiplier=None,
                    fully_deliverable=False,
                ),
                AllToPolicy(
                    name=(test_elcc_surface.name, test_prm_policy.name),
                    instance_from=test_elcc_surface,
                    instance_to=test_prm_policy,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[0.95, 0.95]),
                    ),
                ),
                AllToPolicy(
                    name=(test_thermal_resource.name, test_ghg_policy.name),
                    instance_from=test_thermal_resource,
                    instance_to=test_ghg_policy,
                    multiplier=None,
                ),
                AllToPolicy(
                    name=(test_thermal_resource_2.name, test_ghg_policy.name),
                    instance_from=test_thermal_resource_2,
                    instance_to=test_ghg_policy,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2045-01-01", "2050-01-01"]),
                            data=0.5,
                            name="values",
                        ),
                    ),
                ),
                AllToPolicy(
                    name=(test_candidate_fuel_1.name, test_ghg_policy.name),
                    instance_from=test_candidate_fuel_1,
                    instance_to=test_ghg_policy,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2045-01-01", "2050-01-01"]),
                            data=0.1,
                            name="values",
                        ),
                    ),
                ),
                AllToPolicy(
                    name=(test_candidate_fuel_1.name, test_ghg_policy.name),
                    instance_from=test_candidate_fuel_1,
                    instance_to=test_ghg_policy,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2045-01-01", "2050-01-01"]),
                            data=0.25,
                            name="values",
                        ),
                    ),
                ),
                AllToPolicy(
                    name=(test_tx_path.name, test_ghg_policy.name),
                    instance_from=test_tx_path,
                    instance_to=test_ghg_policy,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2045-01-01", "2050-01-01"]),
                            data=1.0,
                            name="values",
                        ),
                    ),
                ),
                AllToPolicy(
                    name=(test_tx_path_2.name, test_ghg_policy.name),
                    instance_from=test_tx_path_2,
                    instance_to=test_ghg_policy,
                    multiplier=None,
                    forward_dir_multiplier=ts.NumericTimeseries(
                        name="forward_dir_multiplier",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2045-01-01", "2050-01-01"]),
                            data=5.0,
                            name="values",
                        ),
                    ),
                    reverse_dir_multiplier=ts.NumericTimeseries(
                        name="reverse_dir_multiplier",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2045-01-01", "2050-01-01"]),
                            data=2.0,
                            name="values",
                        ),
                    ),
                ),
                AllToPolicy(
                    name=(test_pollutant_1.name, test_ghg_policy.name),
                    instance_from=test_pollutant_1,
                    instance_to=test_ghg_policy,
                ),
                AllToPolicy(
                    name=(test_plant.name, test_ghg_policy.name),
                    instance_from=test_plant,
                    instance_to=test_ghg_policy,
                ),
                AllToPolicy(
                    name=(test_sequestration.name, test_ghg_policy.name),
                    instance_from=test_sequestration,
                    instance_to=test_ghg_policy,
                ),
                AllToPolicy(
                    name=(test_negative_emissions_technology.name, test_ghg_policy.name),
                    instance_from=test_negative_emissions_technology,
                    instance_to=test_ghg_policy,
                ),
                AllToPolicy(
                    name=(test_generic_energy_demand_2.name, test_ghg_policy.name),
                    instance_from=test_generic_energy_demand_2,
                    instance_to=test_ghg_policy,
                ),
                AllToPolicy(
                    name=(test_transportation_1.name, test_ghg_policy.name),
                    instance_from=test_transportation_1,
                    instance_to=test_ghg_policy,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2045-01-01", "2050-01-01"]),
                            data=1.5,
                            name="values",
                        ),
                    ),
                ),
                AllToPolicy(
                    name=(test_transportation_2.name, test_ghg_policy.name),
                    instance_from=test_transportation_2,
                    instance_to=test_ghg_policy,
                    multiplier=None,
                    forward_dir_multiplier=ts.NumericTimeseries(
                        name="forward_dir_multiplier",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2045-01-01", "2050-01-01"]),
                            data=5.0,
                            name="values",
                        ),
                    ),
                    reverse_dir_multiplier=ts.NumericTimeseries(
                        name="reverse_dir_multiplier",
                        data=pd.Series(
                            index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2045-01-01", "2050-01-01"]),
                            data=2.0,
                            name="values",
                        ),
                    ),
                ),
                AllToPolicy(
                    name=(test_solar_resource.name, test_hourly_ces.name),
                    instance_from=test_solar_resource,
                    instance_to=test_hourly_ces,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[1.0, 1.0]),
                    ),
                ),
                AllToPolicy(
                    name=(test_load_1.name, test_hourly_ces.name),
                    instance_from=test_load_1,
                    instance_to=test_hourly_ces,
                    multiplier=ts.NumericTimeseries(
                        name="multiplier",
                        data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[1.0, 1.0]),
                    ),
                ),
            ],
            "DemandToProduct": [
                DemandToProduct(
                    name=(test_generic_demand_2.name, test_commodity_product_1.name),
                    instance_from=test_generic_demand_2,
                    instance_to=test_commodity_product_1,
                ),
            ],
            "ProductToTransportation": [
                ProductToTransportation(
                    name=(test_product_2.name, test_transportation_1.name),
                    instance_from=test_product_2,
                    instance_to=test_transportation_1,
                    hurdle_rate_forward_direction=ts.NumericTimeseries(
                        name="hurdle_rate_forward_direction",
                        data=pd.Series(
                            index=pd.DatetimeIndex(
                                [
                                    "2025-01-01 00:00",
                                    "2030-01-01 00:00",
                                    "2035-01-01 00:00",
                                    "2045-01-01 00:00",
                                ],
                                name="timestamp",
                            ),
                            data=4.0,
                            name="value",
                        ),
                    ),
                    hurdle_rate_reverse_direction=ts.NumericTimeseries(
                        name="hurdle_rate_forward_direction",
                        data=pd.Series(
                            index=pd.DatetimeIndex(
                                [
                                    "2025-01-01 00:00",
                                    "2030-01-01 00:00",
                                    "2035-01-01 00:00",
                                    "2045-01-01 00:00",
                                ],
                                name="timestamp",
                            ),
                            data=2.0,
                            name="value",
                        ),
                    ),
                ),
                ProductToTransportation(
                    name=(test_product_4.name, test_transportation_1.name),
                    instance_from=test_product_4,
                    instance_to=test_transportation_1,
                    hurdle_rate_forward_direction=ts.NumericTimeseries(
                        name="hurdle_rate_forward_direction",
                        data=pd.Series(
                            index=pd.DatetimeIndex(
                                [
                                    "2025-01-01 00:00",
                                    "2030-01-01 00:00",
                                    "2035-01-01 00:00",
                                    "2045-01-01 00:00",
                                ],
                                name="timestamp",
                            ),
                            data=4.0,
                            name="value",
                        ),
                    ),
                    hurdle_rate_reverse_direction=ts.NumericTimeseries(
                        name="hurdle_rate_forward_direction",
                        data=pd.Series(
                            index=pd.DatetimeIndex(
                                [
                                    "2025-01-01 00:00",
                                    "2030-01-01 00:00",
                                    "2035-01-01 00:00",
                                    "2045-01-01 00:00",
                                ],
                                name="timestamp",
                            ),
                            data=2.0,
                            name="value",
                        ),
                    ),
                ),
                ProductToTransportation(
                    name=(test_product_2.name, test_transportation_2.name),
                    instance_from=test_product_2,
                    instance_to=test_transportation_2,
                    hurdle_rate_forward_direction=ts.NumericTimeseries(
                        name="hurdle_rate_forward_direction",
                        data=pd.Series(
                            index=pd.DatetimeIndex(
                                [
                                    "2025-01-01 00:00",
                                    "2030-01-01 00:00",
                                    "2035-01-01 00:00",
                                    "2045-01-01 00:00",
                                ],
                                name="timestamp",
                            ),
                            data=4.0,
                            name="value",
                        ),
                    ),
                    hurdle_rate_reverse_direction=ts.NumericTimeseries(
                        name="hurdle_rate_forward_direction",
                        data=pd.Series(
                            index=pd.DatetimeIndex(
                                [
                                    "2025-01-01 00:00",
                                    "2030-01-01 00:00",
                                    "2035-01-01 00:00",
                                    "2045-01-01 00:00",
                                ],
                                name="timestamp",
                            ),
                            data=2.0,
                            name="value",
                        ),
                    ),
                ),
                ProductToTransportation(
                    name=(test_product_4.name, test_transportation_2.name),
                    instance_from=test_product_4,
                    instance_to=test_transportation_2,
                    hurdle_rate_forward_direction=ts.NumericTimeseries(
                        name="hurdle_rate_forward_direction",
                        data=pd.Series(
                            index=pd.DatetimeIndex(
                                [
                                    "2025-01-01 00:00",
                                    "2030-01-01 00:00",
                                    "2035-01-01 00:00",
                                    "2045-01-01 00:00",
                                ],
                                name="timestamp",
                            ),
                            data=4.0,
                            name="value",
                        ),
                    ),
                    hurdle_rate_reverse_direction=ts.NumericTimeseries(
                        name="hurdle_rate_forward_direction",
                        data=pd.Series(
                            index=pd.DatetimeIndex(
                                [
                                    "2025-01-01 00:00",
                                    "2030-01-01 00:00",
                                    "2035-01-01 00:00",
                                    "2045-01-01 00:00",
                                ],
                                name="timestamp",
                            ),
                            data=2.0,
                            name="value",
                        ),
                    ),
                ),
            ],
            "ZoneToProduct": [
                ZoneToProduct(
                    name=(test_zone_1.name, test_pollutant_1.name),
                    instance_from=test_zone_1,
                    instance_to=test_pollutant_1,
                ),
                ZoneToProduct(
                    name=(test_zone_1.name, test_product_1.name),
                    instance_from=test_zone_1,
                    instance_to=test_product_1,
                ),
                ZoneToProduct(
                    name=(test_zone_1.name, test_product_2.name),
                    instance_from=test_zone_1,
                    instance_to=test_product_2,
                ),
                ZoneToProduct(
                    name=(test_zone_1.name, test_product_3.name),
                    instance_from=test_zone_1,
                    instance_to=test_product_3,
                ),
                ZoneToProduct(
                    name=(test_zone_2.name, test_product_1.name),
                    instance_from=test_zone_2,
                    instance_to=test_product_1,
                ),
                ZoneToProduct(
                    name=(test_zone_2.name, test_product_2.name),
                    instance_from=test_zone_2,
                    instance_to=test_product_2,
                ),
                ZoneToProduct(
                    name=(test_zone_2.name, test_product_3.name),
                    instance_from=test_zone_2,
                    instance_to=test_product_3,
                ),
                ZoneToProduct(
                    name=(test_zone_1.name, test_commodity_product_1.name),
                    instance_from=test_zone_1,
                    instance_to=test_commodity_product_1,
                ),
                ZoneToProduct(
                    name=(test_zone_2.name, test_commodity_product_1.name),
                    instance_from=test_zone_2,
                    instance_to=test_commodity_product_1,
                ),
                ZoneToProduct(
                    name=(test_zone_3.name, test_product_2.name),
                    instance_from=test_zone_3,
                    instance_to=test_product_2,
                ),
                ZoneToProduct(
                    name=(test_zone_3.name, test_product_4.name),
                    instance_from=test_zone_3,
                    instance_to=test_product_4,
                ),
                ZoneToProduct(
                    name=(test_zone_1.name, test_product_input2.name),
                    instance_from=test_zone_1,
                    instance_to=test_product_input2,
                ),
                ZoneToProduct(
                    name=(test_zone_2.name, test_product_output2.name),
                    instance_from=test_zone_2,
                    instance_to=test_product_output2,
                ),
                ZoneToProduct(
                    name=(test_zone_1.name, test_energy_carrier_input.name),
                    instance_from=test_zone_1,
                    instance_to=test_energy_carrier_input,
                ),
                ZoneToProduct(
                    name=(test_zone_2.name, test_candidate_fuel_1.name),
                    instance_from=test_zone_2,
                    instance_to=test_candidate_fuel_1,
                ),
                ZoneToProduct(
                    name=(test_zone_1.name, test_candidate_fuel_1.name),
                    instance_from=test_zone_1,
                    instance_to=test_candidate_fuel_1,
                ),
                ZoneToProduct(
                    name=(test_zone_1.name, test_electricity.name),
                    instance_from=test_zone_1,
                    instance_to=test_electricity,
                ),
                ZoneToProduct(
                    name=(test_zone_2.name, test_candidate_fuel_2.name),
                    instance_from=test_zone_2,
                    instance_to=test_candidate_fuel_2,
                ),
                ZoneToProduct(
                    name=(test_zone_2.name, test_pollutant_1.name),
                    instance_from=test_zone_2,
                    instance_to=test_pollutant_1,
                ),
            ],
            "FromZoneToDemand": [
                FromZoneToDemand(
                    name=(test_zone_1.name, test_generic_demand_1.name),
                    instance_from=test_zone_1,
                    instance_to=test_generic_demand_1,
                ),
                FromZoneToDemand(
                    name=(test_zone_3.name, test_generic_demand_2.name),
                    instance_from=test_zone_3,
                    instance_to=test_generic_demand_2,
                ),
            ],
            "ToZoneToDemand": [
                ToZoneToDemand(
                    name=(test_zone_2.name, test_generic_demand_1.name),
                    instance_from=test_zone_1,
                    instance_to=test_generic_demand_1,
                ),
            ],
            "FromZoneToPlant": [
                FromZoneToPlant(
                    name=(test_zone_1.name, test_plant_with_input_output_capture.name),
                    instance_from=test_zone_1,
                    instance_to=test_plant_with_input_output_capture,
                ),
                FromZoneToPlant(
                    name=(test_zone_1.name, test_negative_emissions_technology.name),
                    instance_from=test_zone_1,
                    instance_to=test_negative_emissions_technology,
                ),
                FromZoneToPlant(
                    name=(test_zone_1.name, test_sequestration.name),
                    instance_from=test_zone_1,
                    instance_to=test_sequestration,
                ),
                FromZoneToPlant(
                    name=(test_zone_1.name, test_sequestration_2.name),
                    instance_from=test_zone_1,
                    instance_to=test_sequestration_2,
                ),
                FromZoneToPlant(
                    name=(test_zone_1.name, test_plant.name),
                    instance_from=test_zone_1,
                    instance_to=test_plant,
                ),
            ],
            "ToZoneToPlant": [
                ToZoneToPlant(
                    name=(test_zone_1.name, test_plant_with_input_output_capture.name),
                    instance_from=test_zone_1,
                    instance_to=test_plant_with_input_output_capture,
                ),
                ToZoneToPlant(
                    name=(test_zone_1.name, test_negative_emissions_technology.name),
                    instance_from=test_zone_1,
                    instance_to=test_negative_emissions_technology,
                ),
                ToZoneToPlant(
                    name=(test_zone_1.name, test_sequestration.name),
                    instance_from=test_zone_1,
                    instance_to=test_sequestration,
                ),
                ToZoneToPlant(
                    name=(test_zone_1.name, test_sequestration_2.name),
                    instance_from=test_zone_1,
                    instance_to=test_sequestration_2,
                ),
                ToZoneToPlant(
                    name=(test_zone_2.name, test_plant.name),
                    instance_from=test_zone_2,
                    instance_to=test_plant,
                ),
            ],
            "FromZoneToTransportation": [
                FromZoneToTransportation(
                    name=(test_zone_2.name, test_transportation_1.name),
                    instance_from=test_zone_2,
                    instance_to=test_transportation_1,
                ),
                FromZoneToTransportation(
                    name=(test_zone_2.name, test_transportation_2.name),
                    instance_from=test_zone_2,
                    instance_to=test_transportation_2,
                ),
            ],
            "ToZoneToTransportation": [
                ToZoneToTransportation(
                    name=(test_zone_3.name, test_transportation_1.name),
                    instance_from=test_zone_3,
                    instance_to=test_transportation_1,
                ),
                ToZoneToTransportation(
                    name=(test_zone_3.name, test_transportation_2.name),
                    instance_from=test_zone_3,
                    instance_to=test_transportation_2,
                ),
            ],
            "FromZoneToFuelProductionPlant": [
                FromZoneToFuelProductionPlant(
                    name=(test_zone_1.name, test_fuel_production_plant.name),
                    instance_from=test_zone_1,
                    instance_to=test_fuel_production_plant,
                ),
                FromZoneToFuelProductionPlant(
                    name=(test_zone_1.name, test_electrolyzer.name),
                    instance_from=test_zone_1,
                    instance_to=test_electrolyzer,
                ),
            ],
            "ToZoneToFuelProductionPlant": [
                ToZoneToFuelProductionPlant(
                    name=(test_zone_2.name, test_fuel_production_plant.name),
                    instance_from=test_zone_2,
                    instance_to=test_fuel_production_plant,
                ),
                ToZoneToFuelProductionPlant(
                    name=(test_zone_2.name, test_electrolyzer.name),
                    instance_from=test_zone_2,
                    instance_to=test_electrolyzer,
                ),
            ],
            "ToZoneToFuelStorage": [
                ToZoneToFuelStorage(
                    name=(test_zone_2.name, test_fuel_storage.name),
                    instance_from=test_zone_2,
                    instance_to=test_fuel_storage,
                ),
            ],
            "FromZoneToFuelStorage": [
                FromZoneToFuelStorage(
                    name=(test_zone_2.name, test_fuel_storage.name),
                    instance_from=test_zone_2,
                    instance_to=test_fuel_storage,
                ),
            ],
        },
        three_way_linkages={
            "CustomConstraintLinkage": [
                CustomConstraintLinkage(
                    name=(test_custom_constraint_rhs.name, test_custom_constraint_lhs.name, test_hydro_resource.name),
                    instance_1=test_custom_constraint_rhs,
                    instance_2=test_custom_constraint_lhs,
                    instance_3=test_hydro_resource,
                ),
                CustomConstraintLinkage(
                    name=(test_custom_constraint_rhs.name, test_custom_constraint_lhs.name, test_thermal_resource.name),
                    instance_1=test_custom_constraint_rhs,
                    instance_2=test_custom_constraint_lhs,
                    instance_3=test_thermal_resource,
                ),
                CustomConstraintLinkage(
                    name=(
                        test_custom_constraint_rhs.name,
                        test_custom_constraint_lhs_annual.name,
                        test_thermal_resource.name,
                    ),
                    instance_1=test_custom_constraint_rhs,
                    instance_2=test_custom_constraint_lhs_annual,
                    instance_3=test_thermal_resource,
                ),
                CustomConstraintLinkage(
                    name=(
                        test_custom_constraint_rhs_annual.name,
                        test_custom_constraint_lhs_annual.name,
                        test_hydro_resource.name,
                    ),
                    instance_1=test_custom_constraint_rhs_annual,
                    instance_2=test_custom_constraint_lhs_annual,
                    instance_3=test_hydro_resource,
                ),
                CustomConstraintLinkage(
                    name=(
                        test_custom_constraint_rhs_annual.name,
                        test_custom_constraint_lhs_annual.name,
                        test_thermal_resource.name,
                    ),
                    instance_1=test_custom_constraint_rhs_annual,
                    instance_2=test_custom_constraint_lhs_annual,
                    instance_3=test_thermal_resource,
                ),
            ],
            "ChargeProcess": [
                ChargeProcess(
                    name=(test_fuel_storage.name, test_candidate_fuel_2.name, test_candidate_fuel_2.name),
                    instance_1=test_fuel_storage,
                    instance_2=test_candidate_fuel_2,
                    instance_3=test_candidate_fuel_2,
                    conversion_rate=0.95,
                )
            ],
            "SequestrationProcess": [
                SequestrationProcess(
                    name=(test_sequestration.name, test_pollutant_1.name, test_pollutant_1.name),
                    instance_1=test_sequestration,
                    instance_2=test_pollutant_1,
                    instance_3=test_pollutant_1,
                    conversion_rate=0.9,
                    output_capture_rate=0.1,
                    sequestration_rate=0.8,
                ),
                SequestrationProcess(
                    name=(test_sequestration_2.name, test_pollutant_1.name, test_pollutant_1.name),
                    instance_1=test_sequestration_2,
                    instance_2=test_pollutant_1,
                    instance_3=test_pollutant_1,
                    conversion_rate=0.9,
                ),
            ],
            "Process": [
                Process(
                    name=(test_plant_with_input_output_capture.name, test_product_2.name, test_product_2.name),
                    instance_1=test_plant_with_input_output_capture,
                    instance_2=test_product_2,
                    instance_3=test_product_2,
                    conversion_rate=0.9,
                    input_capture_rate=1.0,
                    output_capture_rate=0.95,
                ),
                Process(
                    name=(test_plant_with_input_output_capture.name, test_product_1.name, test_product_2.name),
                    instance_1=test_plant_with_input_output_capture,
                    instance_2=test_product_1,
                    instance_3=test_product_2,
                    conversion_rate=1,
                    input_capture_rate=0,
                    output_capture_rate=1.0,
                ),
                Process(
                    name=(test_negative_emissions_technology.name, test_pollutant_1.name, test_pollutant_1.name),
                    instance_1=test_negative_emissions_technology,
                    instance_2=test_pollutant_1,
                    instance_3=test_pollutant_1,
                    conversion_rate=0.9,
                    input_capture_rate=1.0,
                    output_capture_rate=1.0,
                ),
                Process(
                    name=(test_fuel_storage.name, test_candidate_fuel_2.name, test_candidate_fuel_2.name),
                    instance_1=test_fuel_storage,
                    instance_2=test_candidate_fuel_2,
                    instance_3=test_candidate_fuel_2,
                    conversion_rate=0.9,
                ),
                Process(
                    name=(test_fuel_storage.name, test_candidate_fuel_1.name, test_candidate_fuel_2.name),
                    instance_1=test_fuel_storage,
                    instance_2=test_candidate_fuel_1,
                    instance_3=test_candidate_fuel_2,
                    conversion_rate=0.75,
                ),
                Process(
                    name=(test_plant.name, test_product_1.name, test_product_2.name),
                    instance_1=test_plant,
                    instance_2=test_product_1,
                    instance_3=test_product_2,
                    conversion_rate=0.9,
                ),
                Process(
                    name=(test_fuel_production_plant.name, test_commodity_product_1.name, test_candidate_fuel_2.name),
                    instance_1=test_fuel_production_plant,
                    instance_2=test_commodity_product_1,
                    instance_3=test_candidate_fuel_2,
                    conversion_rate=0.9,
                ),
                Process(
                    name=(test_plant.name, test_product_input2.name, test_product_output2.name),
                    instance_1=test_plant,
                    instance_2=test_product_input2,
                    instance_3=test_product_output2,
                    conversion_rate=0.75,
                ),
                Process(
                    name=(test_fuel_production_plant.name, test_product_input2.name, test_product_output2.name),
                    instance_1=test_fuel_production_plant,
                    instance_2=test_product_input2,
                    instance_3=test_product_output2,
                    conversion_rate=0.75,
                ),
                Process(
                    name=(test_fuel_production_plant.name, test_product_input2.name, test_candidate_fuel_2.name),
                    instance_1=test_fuel_production_plant,
                    instance_2=test_product_input2,
                    instance_3=test_candidate_fuel_2,
                    conversion_rate=1000,
                ),
                Process(
                    name=(test_plant.name, test_commodity_product_1.name, test_product_2.name),
                    instance_1=test_plant,
                    instance_2=test_commodity_product_1,
                    instance_3=test_product_2,
                    conversion_rate=0.001,
                ),
                Process(
                    name=(test_generic_demand_1.name, test_product_3.name, test_product_2.name),
                    instance_1=test_generic_demand_1,
                    instance_2=test_product_3,
                    instance_3=test_product_2,
                    output_capture_rate=0.5,
                ),
                Process(
                    name=(test_generic_energy_demand_1.name, test_energy_carrier_input.name, test_electricity.name),
                    instance_1=test_generic_energy_demand_1,
                    instance_2=test_energy_carrier_input,
                    instance_3=test_electricity,
                ),
                Process(
                    name=(
                        test_generic_energy_demand_1.name,
                        test_energy_carrier_input.name,
                        test_energy_carrier_commodity.name,
                    ),
                    instance_1=test_generic_energy_demand_1,
                    instance_2=test_energy_carrier_input,
                    instance_3=test_energy_carrier_commodity,
                ),
                Process(
                    name=(test_plant.name, test_energy_carrier_input.name, test_candidate_fuel_2.name),
                    instance_1=test_plant,
                    instance_2=test_energy_carrier_input,
                    instance_3=test_candidate_fuel_2,
                ),
                Process(
                    name=(test_electrolyzer.name, test_electricity.name, test_candidate_fuel_2.name),
                    instance_1=test_electrolyzer,
                    instance_2=test_electricity,
                    instance_3=test_candidate_fuel_2,
                    conversion_rate=0.9,
                ),
                Process(
                    name=(test_plant.name, test_electricity.name, test_pollutant_1.name),
                    instance_1=test_plant,
                    instance_2=test_electricity,
                    instance_3=test_pollutant_1,
                    conversion_rate=0.9,
                ),
                Process(
                    name=(test_plant.name, test_pollutant_1.name, test_candidate_fuel_1.name),
                    instance_1=test_plant,
                    instance_2=test_pollutant_1,
                    instance_3=test_candidate_fuel_2,
                ),
                Process(
                    name=(test_generic_energy_demand_2.name, test_electricity.name, test_pollutant_1.name),
                    instance_1=test_generic_energy_demand_2,
                    instance_2=test_electricity,
                    instance_3=test_pollutant_1,
                    conversion_rate=0.9,
                ),
                Process(
                    name=(test_plant.name, test_product_input2.name, test_product_2.name),
                    instance_1=test_plant,
                    instance_2=test_product_input2,
                    instance_3=test_product_2,
                    conversion_rate=0.85,
                ),
                Process(
                    name=(test_plant.name, test_energy_carrier_input.name, test_product_2.name),
                    instance_1=test_plant,
                    instance_2=test_energy_carrier_input,
                    instance_3=test_product_2,
                    conversion_rate=0.1,
                ),
                Process(
                    name=(test_plant.name, test_electricity.name, test_product_2.name),
                    instance_1=test_plant,
                    instance_2=test_electricity,
                    instance_3=test_product_2,
                    conversion_rate=1000,
                ),
                Process(
                    name=(test_plant.name, test_pollutant_1.name, test_product_2.name),
                    instance_1=test_plant,
                    instance_2=test_pollutant_1,
                    instance_3=test_product_2,
                    conversion_rate=1000,
                ),
            ],
        },
    )

    return system


@pytest.fixture(scope="session")
def test_system_with_operational_groups(
    dir_structure: DirStructure,
    test_asset,
    test_asset_group,
    test_tx_path_group,
    test_generic_resource,
    test_generic_resource_group,
    test_hydro_resource,
    test_hydro_resource_group,
    test_thermal_resource,
    test_thermal_resource_2,
    test_thermal_resource_group,
    test_solar_resource,
    test_solar_resource_group,
    test_wind_resource,
    test_wind_resource_group,
    test_storage_resource,
    test_storage_resource_2,
    test_storage_resource_group,
    test_hybrid_variable_resource,
    test_hybrid_variable_resource_group,
    test_hybrid_variable_resource_2,
    test_hybrid_variable_resource_group_2,
    test_hybrid_solar_resource,
    test_hybrid_solar_resource_group,
    test_hybrid_wind_resource,
    test_hybrid_wind_resource_group,
    test_hybrid_storage_resource,
    test_hybrid_storage_resource_group,
    test_hybrid_storage_resource_2,
    test_hybrid_storage_resource_group_2,
    test_hybrid_storage_resource_3,
    test_hybrid_storage_resource_group_3,
    test_hybrid_storage_resource_4,
    test_hybrid_storage_resource_group_4,
    test_thermal_unit_commitment_resource,
    test_plant_group,
    test_plant,
    test_fuel_production_plant_group,
    test_fuel_production_plant,
    test_electrolyzer,
    test_electrolyzer_group,
    test_fuel_storage,
    test_fuel_storage_group,
    test_negative_emissions_technology,
    test_negative_emissions_technology_group,
    test_sequestration,
    test_sequestration_group,
    test_product_1,
    test_product_2,
    test_product_input2,
    test_product_output2,
    test_commodity_product_1,
    test_pollutant_1,
    test_electricity,
    test_shed_dr_resource,
    test_reserve_up,
    test_reserve_down,
    test_zone_1,
    test_zone_2,
    test_tx_path,
    test_tx_path_2,
    test_load_1,
    test_EV_load_1,
    test_load_2,
    test_rps,
    test_ghg_policy,
    test_hourly_ces,
    test_prm_policy,
    test_elcc_surface,
    test_elcc_facet,
    test_candidate_fuel_1,
    test_candidate_fuel_2,
    test_erm,
):
    test_asset = test_asset.copy()
    test_generic_resource = test_generic_resource.copy()
    test_generic_resource_group = test_generic_resource_group.copy()
    test_tx_path_group = test_tx_path_group.copy()
    test_hydro_resource = test_hydro_resource.copy()
    test_hydro_resource_group = test_hydro_resource_group.copy()
    test_thermal_resource = test_thermal_resource.copy()
    test_thermal_resource_2 = test_thermal_resource_2.copy()
    test_thermal_resource_group = test_thermal_resource_group.copy()
    test_solar_resource = test_solar_resource.copy()
    test_solar_resource_group = test_solar_resource_group.copy()
    test_wind_resource = test_wind_resource.copy()
    test_wind_resource_group = test_wind_resource_group.copy()
    test_storage_resource = test_storage_resource.copy()
    test_storage_resource_2 = test_storage_resource_2.copy()
    test_storage_resource_group = test_storage_resource_group.copy()
    test_hybrid_variable_resource = test_hybrid_variable_resource.copy()
    test_hybrid_variable_resource_group = test_hybrid_variable_resource_group.copy()
    test_hybrid_variable_resource_2 = test_hybrid_variable_resource_2.copy()
    test_hybrid_variable_resource_group_2 = test_hybrid_variable_resource_group_2.copy()
    test_hybrid_solar_resource = test_hybrid_solar_resource.copy()
    test_hybrid_solar_resource_group = test_hybrid_solar_resource_group.copy()
    test_hybrid_wind_resource = test_hybrid_wind_resource.copy()
    test_hybrid_wind_resource_group = test_hybrid_wind_resource_group.copy()
    test_hybrid_storage_resource = test_hybrid_storage_resource.copy()
    test_hybrid_storage_resource_group = test_hybrid_storage_resource_group.copy()
    test_hybrid_storage_resource_2 = test_hybrid_storage_resource_2.copy()
    test_hybrid_storage_resource_group_2 = test_hybrid_storage_resource_group_2.copy()
    test_hybrid_storage_resource_3 = test_hybrid_storage_resource_3.copy()
    test_hybrid_storage_resource_group_3 = test_hybrid_storage_resource_group_3.copy()
    test_hybrid_storage_resource_4 = test_hybrid_storage_resource_4.copy()
    test_hybrid_storage_resource_group_4 = test_hybrid_storage_resource_group_4.copy()
    test_thermal_unit_commitment_resource = test_thermal_unit_commitment_resource.copy()
    test_plant = test_plant.copy()
    test_plant_group = test_plant_group.copy()
    test_fuel_production_plant = test_fuel_production_plant.copy()
    test_fuel_production_plant_group = test_fuel_production_plant_group.copy()
    test_electrolyzer = test_electrolyzer.copy()
    test_electrolyzer_group = test_electrolyzer_group.copy()
    test_fuel_storage = test_fuel_storage.copy()
    test_fuel_storage_group = test_fuel_storage_group.copy()
    test_sequestration = test_sequestration.copy()
    test_sequestration_group = test_sequestration_group.copy()
    test_product_1 = test_product_1.copy()
    test_product_2 = test_product_2.copy()
    test_product_input2 = test_product_input2.copy()
    test_product_output2 = test_product_output2.copy()
    test_commodity_product_1 = test_commodity_product_1.copy()
    test_pollutant_1 = test_pollutant_1.copy()
    test_electricity = test_electricity.copy()
    test_reserve_up = test_reserve_up.copy()
    test_reserve_down = test_reserve_down.copy()
    test_zone_1 = test_zone_1.copy()
    test_zone_2 = test_zone_2.copy()
    test_tx_path = test_tx_path.copy()
    test_tx_path_2 = test_tx_path_2.copy()
    test_load_1 = test_load_1.copy()
    test_EV_load_1 = test_EV_load_1.copy()
    test_load_2 = test_load_2.copy()
    test_rps = test_rps.copy()
    test_ghg_policy = test_ghg_policy.copy()
    test_hourly_ces = test_hourly_ces.copy()
    test_prm_policy = test_prm_policy.copy()
    test_elcc_surface = test_elcc_surface.copy()
    test_elcc_facet = test_elcc_facet.copy()
    test_candidate_fuel_1 = test_candidate_fuel_1.copy()
    test_candidate_fuel_2 = test_candidate_fuel_2.copy()
    test_erm = test_erm.copy()

    # Create a dictionary of components for the system, including placeholder copies of certain resources
    #  to use in operational grouping
    # Note: some linkages have been modified relative to the baseline test system so that the resource groups are linked
    #  to other components, rather than individual resources
    components = dict(
        assets={
            test_asset.name: test_asset,
            f"{test_asset.name}_copy": test_asset.copy(update={"name": f"{test_asset.name}_copy"}),
            test_generic_resource.name: test_generic_resource,
            f"{test_generic_resource.name}_copy": test_generic_resource.copy(
                update={"name": f"{test_generic_resource.name}_copy"}
            ),
            test_thermal_resource.name: test_thermal_resource,
            test_thermal_resource_2.name: test_thermal_resource_2,
            f"{test_thermal_resource.name}_copy": test_thermal_resource.copy(
                update={"name": f"{test_thermal_resource.name}_copy"}
            ),
            test_solar_resource.name: test_solar_resource,
            f"{test_solar_resource.name}_copy": test_solar_resource.copy(
                update={"name": f"{test_solar_resource.name}_copy"}
            ),
            test_wind_resource.name: test_wind_resource,
            f"{test_wind_resource.name}_copy": test_wind_resource.copy(
                update={"name": f"{test_wind_resource.name}_copy"}
            ),
            test_hydro_resource.name: test_hydro_resource,
            f"{test_hydro_resource.name}_copy": test_hydro_resource.copy(
                update={"name": f"{test_hydro_resource.name}_copy"}
            ),
            test_storage_resource.name: test_storage_resource,
            test_storage_resource_2.name: test_storage_resource_2,
            f"{test_storage_resource.name}_copy": test_storage_resource.copy(
                update={"name": f"{test_storage_resource.name}_copy"}
            ),
            test_shed_dr_resource.name: test_shed_dr_resource,
            test_hybrid_variable_resource.name: test_hybrid_variable_resource.copy(),
            f"{test_hybrid_variable_resource.name}_copy": test_hybrid_variable_resource.copy(
                update={"name": f"{test_hybrid_variable_resource.name}_copy"}
            ),
            test_hybrid_variable_resource_2.name: test_hybrid_variable_resource_2.copy(),
            f"{test_hybrid_variable_resource_2.name}_copy": test_hybrid_variable_resource_2.copy(
                update={"name": f"{test_hybrid_variable_resource_2.name}_copy"}
            ),
            test_hybrid_solar_resource.name: test_hybrid_solar_resource.copy(),
            f"{test_hybrid_solar_resource.name}_copy": test_hybrid_solar_resource.copy(
                update={"name": f"{test_hybrid_solar_resource.name}_copy"}
            ),
            test_hybrid_wind_resource.name: test_hybrid_wind_resource.copy(),
            f"{test_hybrid_wind_resource.name}_copy": test_hybrid_wind_resource.copy(
                update={"name": f"{test_hybrid_wind_resource.name}_copy"}
            ),
            test_hybrid_storage_resource.name: test_hybrid_storage_resource.copy(),
            f"{test_hybrid_storage_resource.name}_copy": test_hybrid_storage_resource.copy(
                update={"name": f"{test_hybrid_storage_resource.name}_copy"}
            ),
            test_hybrid_storage_resource_2.name: test_hybrid_storage_resource_2.copy(),
            f"{test_hybrid_storage_resource_2.name}_copy": test_hybrid_storage_resource_2.copy(
                update={"name": f"{test_hybrid_storage_resource_2.name}_copy"}
            ),
            test_hybrid_storage_resource_3.name: test_hybrid_storage_resource_3.copy(),
            f"{test_hybrid_storage_resource_3.name}_copy": test_hybrid_storage_resource_3.copy(
                update={"name": f"{test_hybrid_storage_resource_3.name}_copy"}
            ),
            test_hybrid_storage_resource_4.name: test_hybrid_storage_resource_4.copy(),
            f"{test_hybrid_storage_resource_4.name}_copy": test_hybrid_storage_resource_4.copy(
                update={"name": f"{test_hybrid_storage_resource_4.name}_copy"}
            ),
            test_thermal_unit_commitment_resource.name: test_thermal_unit_commitment_resource,
            test_tx_path.name: test_tx_path,
            f"{test_tx_path.name}_copy": test_tx_path.copy(update={"name": f"{test_tx_path.name}_copy"}),
            test_tx_path_2.name: test_tx_path_2,
            test_plant.name: test_plant,
            f"{test_plant.name}_copy": test_plant.copy(update={"name": f"{test_plant.name}_copy"}),
            test_fuel_production_plant.name: test_fuel_production_plant,
            f"{test_fuel_production_plant.name}_copy": test_fuel_production_plant.copy(
                update={"name": f"{test_fuel_production_plant.name}_copy"}
            ),
            test_electrolyzer.name: test_electrolyzer,
            f"{test_electrolyzer.name}_copy": test_electrolyzer.copy(update={"name": f"{test_electrolyzer.name}_copy"}),
            test_fuel_storage.name: test_fuel_storage,
            f"{test_fuel_storage.name}_copy": test_fuel_storage.copy(update={"name": f"{test_fuel_storage.name}_copy"}),
            test_negative_emissions_technology.name: test_negative_emissions_technology,
            f"{test_negative_emissions_technology.name}_copy": test_negative_emissions_technology.copy(
                update={"name": f"{test_negative_emissions_technology.name}_copy"}
            ),
            test_sequestration.name: test_sequestration,
            f"{test_sequestration.name}_copy": test_sequestration.copy(
                update={"name": f"{test_sequestration.name}_copy"}
            ),
        },
        asset_groups={
            test_asset_group.name: test_asset_group,
            test_tx_path_group.name: test_tx_path_group,
            test_generic_resource_group.name: test_generic_resource_group,
            test_solar_resource_group.name: test_solar_resource_group,
            test_wind_resource_group.name: test_wind_resource_group,
            test_thermal_resource_group.name: test_thermal_resource_group,
            test_hydro_resource_group.name: test_hydro_resource_group,
            test_storage_resource_group.name: test_storage_resource_group,
            test_hybrid_variable_resource_group.name: test_hybrid_variable_resource_group.copy(),
            test_hybrid_variable_resource_group_2.name: test_hybrid_variable_resource_group_2.copy(),
            test_hybrid_solar_resource_group.name: test_hybrid_solar_resource_group.copy(),
            test_hybrid_wind_resource_group.name: test_hybrid_wind_resource_group.copy(),
            test_hybrid_storage_resource_group.name: test_hybrid_storage_resource_group.copy(),
            test_hybrid_storage_resource_group_2.name: test_hybrid_storage_resource_group_2.copy(),
            test_hybrid_storage_resource_group_3.name: test_hybrid_storage_resource_group_3.copy(),
            test_hybrid_storage_resource_group_4.name: test_hybrid_storage_resource_group_4.copy(),
            test_plant_group.name: test_plant_group,
            test_fuel_production_plant_group.name: test_fuel_production_plant_group,
            test_electrolyzer_group.name: test_electrolyzer_group,
            test_fuel_storage_group.name: test_fuel_storage_group,
            test_negative_emissions_technology_group.name: test_negative_emissions_technology_group,
            test_sequestration_group.name: test_sequestration_group,
        },
        reserves={test_reserve_up.name: test_reserve_up, test_reserve_down.name: test_reserve_down},
        annual_energy_policies={test_rps.name: test_rps},
        emissions_policies={test_ghg_policy.name: test_ghg_policy},
        prm_policies={test_prm_policy.name: test_prm_policy},
        elcc_surfaces={test_elcc_surface.name: test_elcc_surface},
        elcc_facets={test_elcc_facet.name: test_elcc_facet},
        hourly_energy_policies={test_hourly_ces.name: test_hourly_ces},
        erm_policies={test_erm.name: test_erm},
        products={
            test_candidate_fuel_1.name: test_candidate_fuel_1,
            test_candidate_fuel_2.name: test_candidate_fuel_2,
            test_product_1.name: test_product_1,
            test_product_2.name: test_product_2,
            test_product_input2.name: test_product_input2,
            test_product_output2.name: test_product_output2,
            test_commodity_product_1.name: test_commodity_product_1,
            test_pollutant_1.name: test_pollutant_1,
            test_electricity.name: test_electricity,
        },
        zones={
            test_zone_1.name: test_zone_1,
            test_zone_2.name: test_zone_2,
        },
        loads={
            test_load_1.name: test_load_1,
            test_EV_load_1.name: test_EV_load_1,
            test_load_2.name: test_load_2,
        },
    )
    linkages = {
        "AssetToZone": [
            AssetToZone(
                name=(test_asset.name, test_zone_1.name),
                instance_from=test_asset,
                instance_to=test_zone_1,
            ),
        ],
        "AssetToELCC": [
            AssetToELCC(
                name=(test_solar_resource.name, test_elcc_surface.name),
                instance_from=test_solar_resource,
                instance_to=test_elcc_surface,
                elcc_axis_index=1.0,
                elcc_axis_multiplier=0.25,
            ),
            AssetToELCC(
                name=(test_storage_resource_2.name, test_elcc_surface.name),
                instance_from=test_storage_resource_2,
                instance_to=test_elcc_surface,
                elcc_axis_index=1.0,
                elcc_axis_multiplier=0.15,
            ),
        ],
        "ELCCFacetToSurface": [
            ELCCFacetToSurface(
                name=(test_elcc_facet.name, test_elcc_surface.name),
                instance_from=test_elcc_facet,
                instance_to=test_elcc_surface,
            ),
        ],
        "ResourceToZone": [
            ResourceToZone(
                name=(test_hydro_resource_group.name, test_zone_1.name),
                instance_from=test_hydro_resource_group,
                instance_to=test_zone_1,
            ),
            ResourceToZone(
                name=(test_generic_resource_group.name, test_zone_1.name),
                instance_from=test_generic_resource_group,
                instance_to=test_zone_1,
            ),
            ResourceToZone(
                name=(test_thermal_resource_group.name, test_zone_1.name),
                instance_from=test_thermal_resource_group,
                instance_to=test_zone_1,
            ),
            ResourceToZone(
                name=(test_solar_resource_group.name, test_zone_1.name),
                instance_from=test_solar_resource_group,
                instance_to=test_zone_1,
            ),
            ResourceToZone(
                name=(test_wind_resource_group.name, test_zone_1.name),
                instance_from=test_wind_resource_group,
                instance_to=test_zone_1,
            ),
            ResourceToZone(
                name=(test_storage_resource_group.name, test_zone_1.name),
                instance_from=test_storage_resource_group,
                instance_to=test_zone_1,
            ),
            ResourceToZone(
                name=(test_hybrid_variable_resource_group.name, test_zone_1.name),
                instance_from=test_hybrid_variable_resource_group,
                instance_to=test_zone_1,
            ),
            ResourceToZone(
                name=(test_hybrid_variable_resource_group_2.name, test_zone_1.name),
                instance_from=test_hybrid_variable_resource_group_2,
                instance_to=test_zone_1,
            ),
            ResourceToZone(
                name=(test_hybrid_solar_resource_group.name, test_zone_1.name),
                instance_from=test_hybrid_solar_resource_group,
                instance_to=test_zone_1,
            ),
            ResourceToZone(
                name=(test_hybrid_wind_resource_group.name, test_zone_1.name),
                instance_from=test_hybrid_wind_resource_group,
                instance_to=test_zone_1,
            ),
            ResourceToZone(
                name=(test_hybrid_storage_resource_group.name, test_zone_1.name),
                instance_from=test_hybrid_storage_resource_group,
                instance_to=test_zone_1,
            ),
            ResourceToZone(
                name=(test_hybrid_storage_resource_group_2.name, test_zone_1.name),
                instance_from=test_hybrid_storage_resource_group_2,
                instance_to=test_zone_1,
            ),
            ResourceToZone(
                name=(test_hybrid_storage_resource_group_3.name, test_zone_1.name),
                instance_from=test_hybrid_storage_resource_group_3,
                instance_to=test_zone_1,
            ),
            ResourceToZone(
                name=(test_hybrid_storage_resource_group_4.name, test_zone_1.name),
                instance_from=test_hybrid_storage_resource_group_4,
                instance_to=test_zone_1,
            ),
            ResourceToZone(
                name=(test_thermal_unit_commitment_resource.name, test_zone_1.name),
                instance_from=test_thermal_unit_commitment_resource,
                instance_to=test_zone_1,
            ),
            ResourceToZone(
                name=(test_shed_dr_resource.name, test_zone_1.name),
                instance_from=test_shed_dr_resource,
                instance_to=test_zone_1,
            ),
        ],
        "ResourceToReserve": [
            ResourceToReserve(
                name=(test_hydro_resource_group.name, test_reserve_up.name),
                instance_from=test_hydro_resource_group,
                instance_to=test_reserve_up,
            ),
            ResourceToReserve(
                name=(test_generic_resource_group.name, test_reserve_up.name),
                instance_from=test_generic_resource_group,
                instance_to=test_reserve_up,
            ),
            ResourceToReserve(
                name=(test_thermal_resource_group.name, test_reserve_up.name),
                instance_from=test_thermal_resource_group,
                instance_to=test_reserve_up,
            ),
            ResourceToReserve(
                name=(test_thermal_unit_commitment_resource.name, test_reserve_up.name),
                instance_from=test_thermal_unit_commitment_resource,
                instance_to=test_reserve_up,
            ),
            ResourceToReserve(
                name=(test_solar_resource_group.name, test_reserve_up.name),
                instance_from=test_solar_resource_group,
                instance_to=test_reserve_up,
            ),
            ResourceToReserve(
                name=(test_wind_resource_group.name, test_reserve_up.name),
                instance_from=test_wind_resource_group,
                instance_to=test_reserve_up,
            ),
            ResourceToReserve(
                name=(test_storage_resource_group.name, test_reserve_up.name),
                instance_from=test_storage_resource_group,
                instance_to=test_reserve_up,
            ),
            ResourceToReserve(
                name=(test_hybrid_variable_resource_group.name, test_reserve_up.name),
                instance_from=test_hybrid_variable_resource_group,
                instance_to=test_reserve_up,
            ),
            ResourceToReserve(
                name=(test_hybrid_solar_resource_group.name, test_reserve_up.name),
                instance_from=test_hybrid_solar_resource_group,
                instance_to=test_reserve_up,
            ),
            ResourceToReserve(
                name=(test_hybrid_wind_resource_group.name, test_reserve_up.name),
                instance_from=test_hybrid_wind_resource_group,
                instance_to=test_reserve_up,
            ),
            ResourceToReserve(
                name=(test_hybrid_storage_resource_group.name, test_reserve_up.name),
                instance_from=test_hybrid_storage_resource_group,
                instance_to=test_reserve_up,
            ),
            ResourceToReserve(
                name=(test_shed_dr_resource.name, test_reserve_up.name),
                instance_from=test_shed_dr_resource,
                instance_to=test_reserve_up,
            ),
            ResourceToReserve(
                name=(test_hydro_resource_group.name, test_reserve_down.name),
                instance_from=test_hydro_resource_group,
                instance_to=test_reserve_down,
            ),
            ResourceToReserve(
                name=(test_generic_resource_group.name, test_reserve_down.name),
                instance_from=test_generic_resource_group,
                instance_to=test_reserve_down,
            ),
            ResourceToReserve(
                name=(test_thermal_resource_group.name, test_reserve_down.name),
                instance_from=test_thermal_resource_group,
                instance_to=test_reserve_down,
            ),
            ResourceToReserve(
                name=(test_thermal_unit_commitment_resource.name, test_reserve_down.name),
                instance_from=test_thermal_unit_commitment_resource,
                instance_to=test_reserve_down,
            ),
            ResourceToReserve(
                name=(test_solar_resource_group.name, test_reserve_down.name),
                instance_from=test_solar_resource_group,
                instance_to=test_reserve_down,
            ),
            ResourceToReserve(
                name=(test_wind_resource_group.name, test_reserve_down.name),
                instance_from=test_wind_resource_group,
                instance_to=test_reserve_down,
            ),
            ResourceToReserve(
                name=(test_storage_resource_group.name, test_reserve_down.name),
                instance_from=test_storage_resource_group,
                instance_to=test_reserve_down,
            ),
            ResourceToReserve(
                name=(test_shed_dr_resource.name, test_reserve_down.name),
                instance_from=test_shed_dr_resource,
                instance_to=test_reserve_down,
            ),
            ResourceToReserve(
                name=(test_hybrid_variable_resource_group.name, test_reserve_down.name),
                instance_from=test_hybrid_variable_resource_group,
                instance_to=test_reserve_down,
            ),
            ResourceToReserve(
                name=(test_hybrid_solar_resource_group.name, test_reserve_down.name),
                instance_from=test_hybrid_solar_resource_group,
                instance_to=test_reserve_down,
            ),
            ResourceToReserve(
                name=(test_hybrid_wind_resource_group.name, test_reserve_down.name),
                instance_from=test_hybrid_wind_resource_group,
                instance_to=test_reserve_down,
            ),
            ResourceToReserve(
                name=(test_hybrid_storage_resource_group.name, test_reserve_down.name),
                instance_from=test_hybrid_storage_resource_group,
                instance_to=test_reserve_down,
            ),
        ],
        "ZoneToTransmissionPath": [
            ZoneToTransmissionPath(
                name=(test_zone_1.name, test_tx_path.name),
                instance_from=test_zone_1,
                instance_to=test_tx_path,
                from_zone=True,
            ),
            ZoneToTransmissionPath(
                name=(test_zone_2.name, test_tx_path.name),
                instance_from=test_zone_2,
                instance_to=test_tx_path,
                to_zone=True,
            ),
            ZoneToTransmissionPath(
                name=(test_zone_1.name, test_tx_path_group.name),
                instance_from=test_zone_1,
                instance_to=test_tx_path_group,
                from_zone=True,
            ),
            ZoneToTransmissionPath(
                name=(test_zone_2.name, test_tx_path_group.name),
                instance_from=test_zone_2,
                instance_to=test_tx_path_group,
                to_zone=True,
            ),
            ZoneToTransmissionPath(
                name=(test_zone_1.name, test_tx_path_2.name),
                instance_from=test_zone_1,
                instance_to=test_tx_path_2,
                from_zone=True,
            ),
            ZoneToTransmissionPath(
                name=(test_zone_2.name, test_tx_path_2.name),
                instance_from=test_zone_2,
                instance_to=test_tx_path_2,
                to_zone=True,
            ),
        ],
        "LoadToZone": [
            LoadToZone(
                name=(test_load_1.name, test_zone_1.name),
                instance_from=test_load_1,
                instance_to=test_zone_1,
            ),
            LoadToZone(
                name=(test_load_2.name, test_zone_2.name),
                instance_from=test_load_2,
                instance_to=test_zone_2,
            ),
            LoadToZone(
                name=(test_EV_load_1.name, test_zone_1.name),
                instance_from=test_EV_load_1,
                instance_to=test_zone_1,
            ),
        ],
        "CandidateFuelToResource": [
            CandidateFuelToResource(
                name=(test_candidate_fuel_1.name, test_thermal_resource_group.name),
                instance_from=test_candidate_fuel_1,
                instance_to=test_thermal_resource_group,
            ),
            CandidateFuelToResource(
                name=(test_candidate_fuel_2.name, test_thermal_resource_group.name),
                instance_from=test_candidate_fuel_2,
                instance_to=test_thermal_resource_group,
            ),
            CandidateFuelToResource(
                name=(test_candidate_fuel_1.name, test_thermal_unit_commitment_resource.name),
                instance_from=test_candidate_fuel_1,
                instance_to=test_thermal_unit_commitment_resource,
            ),
            CandidateFuelToResource(
                name=(test_candidate_fuel_2.name, test_thermal_unit_commitment_resource.name),
                instance_from=test_candidate_fuel_2,
                instance_to=test_thermal_unit_commitment_resource,
            ),
            CandidateFuelToResource(
                name=(test_candidate_fuel_1.name, test_thermal_resource_2.name),
                instance_from=test_candidate_fuel_1,
                instance_to=test_thermal_resource_2,
            ),
        ],
        "HybridStorageResourceToHybridVariableResource": [
            HybridStorageResourceToHybridVariableResource(
                name=(test_hybrid_storage_resource.name, test_hybrid_variable_resource.name),
                instance_from=test_hybrid_storage_resource,
                instance_to=test_hybrid_variable_resource,
                grid_charging_allowed=True,
                interconnection_limit_mw=ts.NumericTimeseries(
                    name="interconnection_limit_mw",
                    data=pd.Series(
                        index=pd.DatetimeIndex(
                            [
                                "2025-01-01 00:00",
                                "2030-01-01 00:00",
                                "2035-01-01 00:00",
                                "2045-01-01 00:00",
                            ],
                            name="timestamp",
                        ),
                        data=[1, 2, 3, 4],
                        name="value",
                    ),
                ),
                pairing_ratio=1,
            ),
            HybridStorageResourceToHybridVariableResource(
                name=(test_hybrid_storage_resource_2.name, test_hybrid_variable_resource_2.name),
                instance_from=test_hybrid_storage_resource_2,
                instance_to=test_hybrid_variable_resource_2,
                grid_charging_allowed=False,
                interconnection_limit_mw=ts.NumericTimeseries(
                    name="interconnection_limit_mw",
                    data=pd.Series(
                        index=pd.DatetimeIndex(
                            [
                                "2025-01-01 00:00",
                                "2030-01-01 00:00",
                                "2035-01-01 00:00",
                                "2045-01-01 00:00",
                            ],
                            name="timestamp",
                        ),
                        data=[1, 2, 3, 4],
                        name="value",
                    ),
                ),
                pairing_ratio=0.95,
            ),
            HybridStorageResourceToHybridVariableResource(
                name=(test_hybrid_storage_resource_3.name, test_hybrid_solar_resource.name),
                instance_from=test_hybrid_storage_resource_3,
                instance_to=test_hybrid_solar_resource,
                grid_charging_allowed=True,
                interconnection_limit_mw=ts.NumericTimeseries(
                    name="interconnection_limit_mw",
                    data=pd.Series(
                        index=pd.DatetimeIndex(
                            [
                                "2025-01-01 00:00",
                                "2030-01-01 00:00",
                                "2035-01-01 00:00",
                                "2045-01-01 00:00",
                            ],
                            name="timestamp",
                        ),
                        data=[1, 2, 3, 4],
                        name="value",
                    ),
                ),
                pairing_ratio=1,
                paired_charging_constraint_active_in_year=ts.NumericTimeseries(
                    name="paired_charging_constraint_active_in_year",
                    data=pd.Series(
                        index=pd.DatetimeIndex(["2025-01-01 00:00"]),
                        data=[0],
                    ),
                ),
            ),
            HybridStorageResourceToHybridVariableResource(
                name=(test_hybrid_storage_resource_4.name, test_hybrid_wind_resource.name),
                instance_from=test_hybrid_storage_resource_4,
                instance_to=test_hybrid_wind_resource,
                grid_charging_allowed=True,
                interconnection_limit_mw=ts.NumericTimeseries(
                    name="interconnection_limit_mw",
                    data=pd.Series(
                        index=pd.DatetimeIndex(
                            [
                                "2025-01-01 00:00",
                                "2030-01-01 00:00",
                                "2035-01-01 00:00",
                                "2045-01-01 00:00",
                            ],
                            name="timestamp",
                        ),
                        data=[1, 2, 3, 4],
                        name="value",
                    ),
                ),
                pairing_ratio=1,
            ),
            HybridStorageResourceToHybridVariableResource(
                name=(test_hybrid_storage_resource_group.name, test_hybrid_variable_resource_group.name),
                instance_from=test_hybrid_storage_resource_group,
                instance_to=test_hybrid_variable_resource_group,
                grid_charging_allowed=True,
                interconnection_limit_mw=ts.NumericTimeseries(
                    name="interconnection_limit_mw",
                    data=pd.Series(
                        index=pd.DatetimeIndex(
                            [
                                "2025-01-01 00:00",
                                "2030-01-01 00:00",
                                "2035-01-01 00:00",
                                "2045-01-01 00:00",
                            ],
                            name="timestamp",
                        ),
                        data=[1, 2, 3, 4],
                        name="value",
                    ),
                ),
                pairing_ratio=1,
            ),
            HybridStorageResourceToHybridVariableResource(
                name=(test_hybrid_storage_resource_group_2.name, test_hybrid_variable_resource_group_2.name),
                instance_from=test_hybrid_storage_resource_group_2,
                instance_to=test_hybrid_variable_resource_group_2,
                grid_charging_allowed=False,
                interconnection_limit_mw=ts.NumericTimeseries(
                    name="interconnection_limit_mw",
                    data=pd.Series(
                        index=pd.DatetimeIndex(
                            [
                                "2025-01-01 00:00",
                                "2030-01-01 00:00",
                                "2035-01-01 00:00",
                                "2045-01-01 00:00",
                            ],
                            name="timestamp",
                        ),
                        data=[1, 2, 3, 4],
                        name="value",
                    ),
                ),
                pairing_ratio=0.95,
            ),
            HybridStorageResourceToHybridVariableResource(
                name=(test_hybrid_storage_resource_group_3.name, test_hybrid_solar_resource_group.name),
                instance_from=test_hybrid_storage_resource_group_3,
                instance_to=test_hybrid_solar_resource_group,
                grid_charging_allowed=True,
                interconnection_limit_mw=ts.NumericTimeseries(
                    name="interconnection_limit_mw",
                    data=pd.Series(
                        index=pd.DatetimeIndex(
                            [
                                "2025-01-01 00:00",
                                "2030-01-01 00:00",
                                "2035-01-01 00:00",
                                "2045-01-01 00:00",
                            ],
                            name="timestamp",
                        ),
                        data=[1, 2, 3, 4],
                        name="value",
                    ),
                ),
                pairing_ratio=1,
            ),
            HybridStorageResourceToHybridVariableResource(
                name=(test_hybrid_storage_resource_group_4.name, test_hybrid_wind_resource_group.name),
                instance_from=test_hybrid_storage_resource_group_4,
                instance_to=test_hybrid_wind_resource_group,
                grid_charging_allowed=True,
                interconnection_limit_mw=ts.NumericTimeseries(
                    name="interconnection_limit_mw",
                    data=pd.Series(
                        index=pd.DatetimeIndex(
                            [
                                "2025-01-01 00:00",
                                "2030-01-01 00:00",
                                "2035-01-01 00:00",
                                "2045-01-01 00:00",
                            ],
                            name="timestamp",
                        ),
                        data=[1, 2, 3, 4],
                        name="value",
                    ),
                ),
                pairing_ratio=1,
            ),
        ],
        "ERMContribution": [
            ERMContribution(
                name=(test_solar_resource_group.name, test_erm.name),
                instance_from=test_solar_resource_group,
                instance_to=test_erm,
                multiplier=ts.NumericTimeseries(
                    name="multiplier",
                    data=pd.Series(
                        index=pd.DatetimeIndex(["2010-01-01 00:00"]),
                        data=0.5,
                    ),
                    weather_year=True,
                ),
            ),
            ERMContribution(
                name=(test_storage_resource_group.name, test_erm.name),
                instance_from=test_storage_resource_group,
                instance_to=test_erm,
                multiplier=ts.NumericTimeseries(
                    name="multiplier",
                    data=pd.Series(
                        index=pd.DatetimeIndex(["2010-01-01 00:00"]),
                        data=0.9,
                    ),
                    weather_year=True,
                ),
            ),
            ERMContribution(
                name=(test_hybrid_variable_resource_group.name, test_erm.name),
                instance_from=test_hybrid_variable_resource,
                instance_to=test_erm,
                multiplier=ts.NumericTimeseries(
                    name="multiplier",
                    data=pd.Series(
                        index=pd.DatetimeIndex(["2010-01-01 00:00"]),
                        data=0.9,
                    ),
                    weather_year=True,
                ),
            ),
            ERMContribution(
                name=(test_hybrid_storage_resource_group.name, test_erm.name),
                instance_from=test_hybrid_storage_resource,
                instance_to=test_erm,
                multiplier=ts.NumericTimeseries(
                    name="multiplier",
                    data=pd.Series(
                        index=pd.DatetimeIndex(["2010-01-01 00:00"]),
                        data=0.8,
                    ),
                    weather_year=True,
                ),
            ),
        ],
        "AllToPolicy": [
            AllToPolicy(
                name=(test_solar_resource_group.name, test_rps.name),
                instance_from=test_solar_resource_group,
                instance_to=test_rps,
                multiplier=ts.NumericTimeseries(
                    name="multiplier",
                    data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[1.0, 1.0]),
                ),
            ),
            AllToPolicy(
                name=(test_wind_resource_group.name, test_rps.name),
                instance_from=test_wind_resource_group,
                instance_to=test_rps,
                multiplier=ts.NumericTimeseries(
                    name="multiplier",
                    data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[1.0, 1.0]),
                ),
            ),
            AllToPolicy(
                name=(test_thermal_resource_group.name, test_prm_policy.name),
                instance_from=test_thermal_resource_group,
                instance_to=test_prm_policy,
                multiplier=ts.NumericTimeseries(
                    name="multiplier",
                    data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[0.95, 0.95]),
                ),
            ),
            AllToPolicy(
                name=(test_asset.name, test_prm_policy.name),
                instance_from=test_asset,
                instance_to=test_prm_policy,
                multiplier=ts.NumericTimeseries(
                    name="multiplier",
                    data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[0.95, 0.95]),
                ),
            ),
            AllToPolicy(
                name=(test_solar_resource.name, test_prm_policy.name),
                instance_from=test_solar_resource,
                instance_to=test_prm_policy,
                multiplier=None,
            ),
            AllToPolicy(
                name=(test_storage_resource_group.name, test_prm_policy.name),
                instance_from=test_storage_resource_group,
                instance_to=test_prm_policy,
                multiplier=ts.NumericTimeseries(
                    name="multiplier",
                    data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[0.95, 0.95]),
                ),
                fully_deliverable=False,
            ),
            AllToPolicy(
                name=(test_storage_resource_2.name, test_prm_policy.name),
                instance_from=test_storage_resource_2,
                instance_to=test_prm_policy,
                multiplier=None,
                fully_deliverable=False,
            ),
            AllToPolicy(
                name=(test_elcc_surface.name, test_prm_policy.name),
                instance_from=test_elcc_surface,
                instance_to=test_prm_policy,
                multiplier=ts.NumericTimeseries(
                    name="multiplier",
                    data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[0.95, 0.95]),
                ),
            ),
            AllToPolicy(
                name=(test_thermal_resource_group.name, test_ghg_policy.name),
                instance_from=test_thermal_resource_group,
                instance_to=test_ghg_policy,
                multiplier=None,
            ),
            AllToPolicy(
                name=(test_thermal_resource_2.name, test_ghg_policy.name),
                instance_from=test_thermal_resource_2,
                instance_to=test_ghg_policy,
                multiplier=ts.NumericTimeseries(
                    name="multiplier",
                    data=pd.Series(
                        index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2045-01-01", "2050-01-01"]),
                        data=0.5,
                        name="values",
                    ),
                ),
            ),
            AllToPolicy(
                name=(test_candidate_fuel_1.name, test_ghg_policy.name),
                instance_from=test_candidate_fuel_1,
                instance_to=test_ghg_policy,
                multiplier=ts.NumericTimeseries(
                    name="multiplier",
                    data=pd.Series(
                        index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2045-01-01", "2050-01-01"]),
                        data=0.1,
                        name="values",
                    ),
                ),
            ),
            AllToPolicy(
                name=(test_candidate_fuel_1.name, test_ghg_policy.name),
                instance_from=test_candidate_fuel_1,
                instance_to=test_ghg_policy,
                multiplier=ts.NumericTimeseries(
                    name="multiplier",
                    data=pd.Series(
                        index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2045-01-01", "2050-01-01"]),
                        data=0.25,
                        name="values",
                    ),
                ),
            ),
            AllToPolicy(
                name=(test_tx_path.name, test_ghg_policy.name),
                instance_from=test_tx_path,
                instance_to=test_ghg_policy,
                multiplier=ts.NumericTimeseries(
                    name="multiplier",
                    data=pd.Series(
                        index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2045-01-01", "2050-01-01"]),
                        data=1.0,
                        name="values",
                    ),
                ),
            ),
            AllToPolicy(
                name=(test_tx_path_2.name, test_ghg_policy.name),
                instance_from=test_tx_path_2,
                instance_to=test_ghg_policy,
                multiplier=None,
                forward_dir_multiplier=ts.NumericTimeseries(
                    name="forward_dir_multiplier",
                    data=pd.Series(
                        index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2045-01-01", "2050-01-01"]),
                        data=5.0,
                        name="values",
                    ),
                ),
                reverse_dir_multiplier=ts.NumericTimeseries(
                    name="reverse_dir_multiplier",
                    data=pd.Series(
                        index=pd.DatetimeIndex(["2025-01-01", "2030-01-01", "2045-01-01", "2050-01-01"]),
                        data=2.0,
                        name="values",
                    ),
                ),
            ),
            AllToPolicy(
                name=(test_solar_resource_group.name, test_hourly_ces.name),
                instance_from=test_solar_resource_group,
                instance_to=test_hourly_ces,
                multiplier=ts.NumericTimeseries(
                    name="multiplier",
                    data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[1.0, 1.0]),
                ),
            ),
            AllToPolicy(
                name=(test_wind_resource_group.name, test_hourly_ces.name),
                instance_from=test_wind_resource_group,
                instance_to=test_hourly_ces,
                multiplier=ts.NumericTimeseries(
                    name="multiplier",
                    data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[1.0, 1.0]),
                ),
            ),
            AllToPolicy(
                name=(test_load_1.name, test_hourly_ces.name),
                instance_from=test_load_1,
                instance_to=test_hourly_ces,
                multiplier=ts.NumericTimeseries(
                    name="multiplier",
                    data=pd.Series(index=pd.DatetimeIndex(["2025-01-01", "2030-01-01"]), data=[1.0, 1.0]),
                ),
            ),
        ],
        "ZoneToProduct": [
            ZoneToProduct(
                name=(test_zone_1.name, test_product_1.name),
                instance_from=test_zone_1,
                instance_to=test_product_1,
            ),
            ZoneToProduct(
                name=(test_zone_1.name, test_product_2.name),
                instance_from=test_zone_1,
                instance_to=test_product_2,
            ),
            ZoneToProduct(
                name=(test_zone_1.name, test_commodity_product_1.name),
                instance_from=test_zone_1,
                instance_to=test_commodity_product_1,
            ),
            ZoneToProduct(
                name=(test_zone_2.name, test_commodity_product_1.name),
                instance_from=test_zone_2,
                instance_to=test_commodity_product_1,
            ),
            ZoneToProduct(
                name=(test_zone_1.name, test_product_input2.name),
                instance_from=test_zone_1,
                instance_to=test_product_input2,
            ),
            ZoneToProduct(
                name=(test_zone_2.name, test_product_output2.name),
                instance_from=test_zone_2,
                instance_to=test_product_output2,
            ),
            ZoneToProduct(
                name=(test_zone_2.name, test_candidate_fuel_1.name),
                instance_from=test_zone_2,
                instance_to=test_candidate_fuel_1,
            ),
            ZoneToProduct(
                name=(test_zone_1.name, test_candidate_fuel_1.name),
                instance_from=test_zone_1,
                instance_to=test_candidate_fuel_1,
            ),
            ZoneToProduct(
                name=(test_zone_1.name, test_electricity.name),
                instance_from=test_zone_1,
                instance_to=test_electricity,
            ),
            ZoneToProduct(
                name=(test_zone_2.name, test_candidate_fuel_2.name),
                instance_from=test_zone_2,
                instance_to=test_candidate_fuel_2,
            ),
            ZoneToProduct(
                name=(test_zone_2.name, test_pollutant_1.name),
                instance_from=test_zone_2,
                instance_to=test_pollutant_1,
            ),
            ZoneToProduct(
                name=(test_zone_1.name, test_pollutant_1.name),
                instance_from=test_zone_1,
                instance_to=test_pollutant_1,
            ),
        ],
        "FromZoneToPlant": [
            FromZoneToPlant(
                name=(test_zone_1.name, test_plant_group.name),
                instance_from=test_zone_1,
                instance_to=test_plant_group,
            ),
            FromZoneToPlant(
                name=(test_zone_1.name, test_plant.name),
                instance_from=test_zone_1,
                instance_to=test_plant,
            ),
            FromZoneToPlant(
                name=(test_zone_1.name, test_negative_emissions_technology.name),
                instance_from=test_zone_1,
                instance_to=test_negative_emissions_technology,
            ),
            FromZoneToPlant(
                name=(test_zone_1.name, test_negative_emissions_technology_group.name),
                instance_from=test_zone_1,
                instance_to=test_negative_emissions_technology_group,
            ),
            FromZoneToPlant(
                name=(test_zone_1.name, test_sequestration.name),
                instance_from=test_zone_1,
                instance_to=test_sequestration,
            ),
            FromZoneToPlant(
                name=(test_zone_1.name, test_sequestration_group.name),
                instance_from=test_zone_1,
                instance_to=test_sequestration_group,
            ),
        ],
        "ToZoneToPlant": [
            ToZoneToPlant(
                name=(test_zone_2.name, test_plant_group.name),
                instance_from=test_zone_2,
                instance_to=test_plant_group,
            ),
            ToZoneToPlant(
                name=(test_zone_2.name, test_plant.name),
                instance_from=test_zone_2,
                instance_to=test_plant,
            ),
            ToZoneToPlant(
                name=(test_zone_1.name, test_negative_emissions_technology.name),
                instance_from=test_zone_1,
                instance_to=test_negative_emissions_technology,
            ),
            ToZoneToPlant(
                name=(test_zone_1.name, test_negative_emissions_technology_group.name),
                instance_from=test_zone_1,
                instance_to=test_negative_emissions_technology_group,
            ),
            ToZoneToPlant(
                name=(test_zone_1.name, test_sequestration.name),
                instance_from=test_zone_1,
                instance_to=test_sequestration,
            ),
            ToZoneToPlant(
                name=(test_zone_1.name, test_sequestration_group.name),
                instance_from=test_zone_1,
                instance_to=test_sequestration_group,
            ),
        ],
        "FromZoneToFuelProductionPlant": [
            FromZoneToFuelProductionPlant(
                name=(test_zone_1.name, test_fuel_production_plant.name),
                instance_from=test_zone_1,
                instance_to=test_fuel_production_plant,
            ),
            FromZoneToFuelProductionPlant(
                name=(test_zone_1.name, test_fuel_production_plant_group.name),
                instance_from=test_zone_1,
                instance_to=test_fuel_production_plant_group,
            ),
            FromZoneToFuelProductionPlant(
                name=(test_zone_1.name, test_electrolyzer.name),
                instance_from=test_zone_1,
                instance_to=test_electrolyzer,
            ),
            FromZoneToFuelProductionPlant(
                name=(test_zone_1.name, test_electrolyzer_group.name),
                instance_from=test_zone_1,
                instance_to=test_electrolyzer_group,
            ),
        ],
        "ToZoneToFuelProductionPlant": [
            ToZoneToFuelProductionPlant(
                name=(test_zone_2.name, test_fuel_production_plant.name),
                instance_from=test_zone_2,
                instance_to=test_fuel_production_plant,
            ),
            ToZoneToFuelProductionPlant(
                name=(test_zone_2.name, test_fuel_production_plant_group.name),
                instance_from=test_zone_2,
                instance_to=test_fuel_production_plant_group,
            ),
            ToZoneToFuelProductionPlant(
                name=(test_zone_2.name, test_electrolyzer.name),
                instance_from=test_zone_2,
                instance_to=test_electrolyzer,
            ),
            ToZoneToFuelProductionPlant(
                name=(test_zone_2.name, test_electrolyzer_group.name),
                instance_from=test_zone_2,
                instance_to=test_electrolyzer_group,
            ),
        ],
        "ToZoneToFuelStorage": [
            ToZoneToFuelStorage(
                name=(test_zone_2.name, test_fuel_storage.name),
                instance_from=test_zone_2,
                instance_to=test_fuel_storage,
            ),
            ToZoneToFuelStorage(
                name=(test_zone_2.name, test_fuel_storage_group.name),
                instance_from=test_zone_2,
                instance_to=test_fuel_storage_group,
            ),
        ],
        "FromZoneToFuelStorage": [
            FromZoneToFuelStorage(
                name=(test_zone_2.name, test_fuel_storage.name),
                instance_from=test_zone_2,
                instance_to=test_fuel_storage,
            ),
            FromZoneToFuelStorage(
                name=(test_zone_2.name, test_fuel_storage_group.name),
                instance_from=test_zone_2,
                instance_to=test_fuel_storage_group,
            ),
        ],
    }
    three_way_linkages = {
        "Process": [
            Process(
                name=(test_plant.name, test_product_1.name, test_product_2.name),
                instance_1=test_plant,
                instance_2=test_product_1,
                instance_3=test_product_2,
                conversion_rate=0.9,
            ),
            Process(
                name=(test_plant_group.name, test_product_1.name, test_product_2.name),
                instance_1=test_plant_group,
                instance_2=test_product_1,
                instance_3=test_product_2,
                conversion_rate=0.9,
            ),
            Process(
                name=(test_plant.name, test_product_input2.name, test_product_output2.name),
                instance_1=test_plant,
                instance_2=test_product_input2,
                instance_3=test_product_output2,
                conversion_rate=0.75,
            ),
            Process(
                name=(test_plant_group.name, test_product_input2.name, test_product_output2.name),
                instance_1=test_plant_group,
                instance_2=test_product_input2,
                instance_3=test_product_output2,
                conversion_rate=0.75,
            ),
            Process(
                name=(test_plant.name, test_commodity_product_1.name, test_product_2.name),
                instance_1=test_plant,
                instance_2=test_commodity_product_1,
                instance_3=test_product_2,
                conversion_rate=0.001,
            ),
            Process(
                name=(test_plant_group.name, test_commodity_product_1.name, test_product_2.name),
                instance_1=test_plant_group,
                instance_2=test_commodity_product_1,
                instance_3=test_product_2,
                conversion_rate=0.001,
            ),
            Process(
                name=(test_negative_emissions_technology.name, test_pollutant_1.name, test_pollutant_1.name),
                instance_1=test_negative_emissions_technology,
                instance_2=test_pollutant_1,
                instance_3=test_pollutant_1,
                conversion_rate=0.9,
                input_capture_rate=1.0,
                output_capture_rate=1.0,
            ),
            Process(
                name=(test_negative_emissions_technology_group.name, test_pollutant_1.name, test_pollutant_1.name),
                instance_1=test_negative_emissions_technology_group,
                instance_2=test_pollutant_1,
                instance_3=test_pollutant_1,
                conversion_rate=0.9,
                input_capture_rate=1.0,
                output_capture_rate=1.0,
            ),
            Process(
                name=(test_fuel_storage.name, test_candidate_fuel_2.name, test_candidate_fuel_2.name),
                instance_1=test_fuel_storage,
                instance_2=test_candidate_fuel_2,
                instance_3=test_candidate_fuel_2,
                conversion_rate=0.9,
            ),
            Process(
                name=(test_fuel_storage_group.name, test_candidate_fuel_2.name, test_candidate_fuel_2.name),
                instance_1=test_fuel_storage_group,
                instance_2=test_candidate_fuel_2,
                instance_3=test_candidate_fuel_2,
                conversion_rate=0.9,
            ),
            Process(
                name=(test_fuel_storage.name, test_candidate_fuel_1.name, test_candidate_fuel_2.name),
                instance_1=test_fuel_storage,
                instance_2=test_candidate_fuel_1,
                instance_3=test_candidate_fuel_2,
                conversion_rate=0.75,
            ),
            Process(
                name=(test_fuel_storage_group.name, test_candidate_fuel_1.name, test_candidate_fuel_2.name),
                instance_1=test_fuel_storage_group,
                instance_2=test_candidate_fuel_1,
                instance_3=test_candidate_fuel_2,
                conversion_rate=0.75,
            ),
            Process(
                name=(test_fuel_production_plant.name, test_commodity_product_1.name, test_candidate_fuel_2.name),
                instance_1=test_fuel_production_plant,
                instance_2=test_commodity_product_1,
                instance_3=test_candidate_fuel_2,
                conversion_rate=0.9,
            ),
            Process(
                name=(test_fuel_production_plant_group.name, test_commodity_product_1.name, test_candidate_fuel_2.name),
                instance_1=test_fuel_production_plant_group,
                instance_2=test_commodity_product_1,
                instance_3=test_candidate_fuel_2,
                conversion_rate=0.9,
            ),
            Process(
                name=(test_fuel_production_plant.name, test_product_input2.name, test_product_output2.name),
                instance_1=test_fuel_production_plant,
                instance_2=test_product_input2,
                instance_3=test_product_output2,
                conversion_rate=0.75,
            ),
            Process(
                name=(test_fuel_production_plant_group.name, test_product_input2.name, test_product_output2.name),
                instance_1=test_fuel_production_plant_group,
                instance_2=test_product_input2,
                instance_3=test_product_output2,
                conversion_rate=0.75,
            ),
            Process(
                name=(test_electrolyzer.name, test_electricity.name, test_candidate_fuel_2.name),
                instance_1=test_electrolyzer,
                instance_2=test_electricity,
                instance_3=test_candidate_fuel_2,
                conversion_rate=0.9,
            ),
            Process(
                name=(test_electrolyzer_group.name, test_electricity.name, test_candidate_fuel_2.name),
                instance_1=test_electrolyzer_group,
                instance_2=test_electricity,
                instance_3=test_candidate_fuel_2,
                conversion_rate=0.9,
            ),
            Process(
                name=(test_plant.name, test_product_input2.name, test_product_2.name),
                instance_1=test_plant,
                instance_2=test_product_input2,
                instance_3=test_product_2,
                conversion_rate=0.85,
            ),
        ],
        "ChargeProcess": [
            ChargeProcess(
                name=(test_fuel_storage.name, test_candidate_fuel_2.name, test_candidate_fuel_2.name),
                instance_1=test_fuel_storage,
                instance_2=test_candidate_fuel_2,
                instance_3=test_candidate_fuel_2,
                conversion_rate=0.95,
            ),
            ChargeProcess(
                name=(test_fuel_storage_group.name, test_candidate_fuel_2.name, test_candidate_fuel_2.name),
                instance_1=test_fuel_storage_group,
                instance_2=test_candidate_fuel_2,
                instance_3=test_candidate_fuel_2,
                conversion_rate=0.95,
            ),
        ],
        "SequestrationProcess": [
            SequestrationProcess(
                name=(test_sequestration.name, test_pollutant_1.name, test_pollutant_1.name),
                instance_1=test_sequestration,
                instance_2=test_pollutant_1,
                instance_3=test_pollutant_1,
                conversion_rate=0.9,
                output_capture_rate=0.1,
                sequestration_rate=0.8,
            ),
            SequestrationProcess(
                name=(test_sequestration_group.name, test_pollutant_1.name, test_pollutant_1.name),
                instance_1=test_sequestration_group,
                instance_2=test_pollutant_1,
                instance_3=test_pollutant_1,
                conversion_rate=0.9,
                output_capture_rate=0.1,
                sequestration_rate=0.8,
            ),
        ],
    }

    # Create linkages that assign the resources and their copies to the appropriate groups
    asset_group_linkages = []
    for group_type, group_instance in [
        (Asset, test_asset_group),
        (TxPath, test_tx_path_group),
        (GenericResource, test_generic_resource_group),
        (ThermalResource, test_thermal_resource_group),
        (SolarResource, test_solar_resource_group),
        (WindResource, test_wind_resource_group),
        (HydroResource, test_hydro_resource_group),
        (StorageResource, test_storage_resource_group),
        (HybridVariableResource, test_hybrid_variable_resource_group),
        (HybridVariableResource, test_hybrid_variable_resource_group_2),
        (HybridSolarResource, test_hybrid_solar_resource_group),
        (HybridWindResource, test_hybrid_wind_resource_group),
        (HybridStorageResource, test_hybrid_storage_resource_group),
        (HybridStorageResource, test_hybrid_storage_resource_group_2),
        (HybridStorageResource, test_hybrid_storage_resource_group_3),
        (HybridStorageResource, test_hybrid_storage_resource_group_4),
        (Plant, test_plant_group),
        (FuelProductionPlant, test_fuel_production_plant_group),
        (Electrolyzer, test_electrolyzer_group),
        (FuelStorage, test_fuel_storage_group),
        (NegativeEmissionsTechnology, test_negative_emissions_technology_group),
        (Sequestration, test_sequestration_group),
    ]:
        for asset_instance in components["assets"].values():
            if (type(asset_instance) == group_type) and (asset_instance.name.endswith("_copy")):
                if (group_type == HybridStorageResource or group_type == HybridVariableResource) and str(
                    re.search(r"\d+", asset_instance.name).group()
                ) not in group_instance.name:
                    continue  # hacky guard clause to avoid putting assets in multiple operational groups
                asset_group_linkages.append(
                    AssetToAssetGroup(
                        name=(asset_instance.name, group_instance.name),
                        instance_from=asset_instance,
                        instance_to=group_instance,
                    )
                )
                original_asset = components["assets"][asset_instance.name.replace("_copy", "")]
                asset_group_linkages.append(
                    AssetToAssetGroup(
                        name=(original_asset.name, group_instance.name),
                        instance_from=original_asset,
                        instance_to=group_instance,
                    )
                )
    linkages["AssetToAssetGroup"] = asset_group_linkages

    # Append HybridStorageResourceToHybridVariableResource linkages to copies of resources
    original_hybrid_linkages = linkages["HybridStorageResourceToHybridVariableResource"].copy()
    for link in original_hybrid_linkages:
        if "group" not in link.instance_to.name.lower():
            new_linkage = HybridStorageResourceToHybridVariableResource(
                name=(f"{link.instance_from.name}_copy", f"{link.instance_to.name}_copy"),
                instance_from=components["assets"][f"{link.instance_from.name}_copy"],
                instance_to=components["assets"][f"{link.instance_to.name}_copy"],
                grid_charging_allowed=True,
                interconnection_limit_mw=ts.NumericTimeseries(
                    name="interconnection_limit_mw",
                    data=pd.Series(
                        index=pd.DatetimeIndex(
                            [
                                "2025-01-01 00:00",
                                "2030-01-01 00:00",
                                "2035-01-01 00:00",
                                "2045-01-01 00:00",
                            ],
                            name="timestamp",
                        ),
                        data=[1, 2, 3, 4],
                        name="value",
                    ),
                ),
                pairing_ratio=1,
                paired_charging_constraint_active_in_year=ts.NumericTimeseries(
                    name="paired_charging_constraint_active_in_year",
                    data=pd.Series(
                        index=pd.DatetimeIndex(["2025-01-01 00:00"]),
                        data=[1],
                    ),
                ),
            )
            if "2" in link.instance_to.name:
                new_linkage.pairing_ratio = 0.95
            linkages["HybridStorageResourceToHybridVariableResource"].append(new_linkage)

    # Append Processes for all "copied" plants
    original_process_linkages = three_way_linkages["Process"].copy()
    for process in original_process_linkages:
        if f"{process.plant.name}_copy" in components["assets"]:
            three_way_linkages["Process"].append(
                Process(
                    name=(f"{process.plant.name}_copy", process.consumed_product.name, process.produced_product.name),
                    instance_1=components["assets"][f"{process.plant.name}_copy"],
                    instance_2=process.consumed_product,
                    instance_3=process.produced_product,
                    conversion_rate=process.conversion_rate,
                )
            )
    original_charge_process_linkages = three_way_linkages["ChargeProcess"].copy()
    for charge_process in original_charge_process_linkages:
        if f"{charge_process.plant.name}_copy" in components["assets"]:
            three_way_linkages["ChargeProcess"].append(
                ChargeProcess(
                    name=(
                        f"{charge_process.plant.name}_copy",
                        charge_process.consumed_product.name,
                        charge_process.produced_product.name,
                    ),
                    instance_1=components["assets"][f"{charge_process.plant.name}_copy"],
                    instance_2=charge_process.consumed_product,
                    instance_3=charge_process.produced_product,
                    conversion_rate=charge_process.conversion_rate,
                )
            )
    original_sequestration_process_linkages = three_way_linkages["SequestrationProcess"].copy()
    for sequestration_process in original_sequestration_process_linkages:
        if f"{sequestration_process.plant.name}_copy" in components["assets"]:
            three_way_linkages["SequestrationProcess"].append(
                SequestrationProcess(
                    name=(
                        f"{sequestration_process.plant.name}_copy",
                        sequestration_process.consumed_product.name,
                        sequestration_process.produced_product.name,
                    ),
                    instance_1=components["assets"][f"{sequestration_process.plant.name}_copy"],
                    instance_2=sequestration_process.consumed_product,
                    instance_3=sequestration_process.produced_product,
                    conversion_rate=sequestration_process.conversion_rate,
                    input_capture_rate=sequestration_process.input_capture_rate,
                    output_capture_rate=sequestration_process.output_capture_rate,
                    sequestration_rate=sequestration_process.sequestration_rate,
                )
            )

    # Instantiate a system with the components, their copies, the resource groups, and appropriate linkages
    system = System(
        name="test_system_with_operational_groups",
        dir_str=dir_structure,
        linkages=linkages,
        three_way_linkages=three_way_linkages,
        **components,
    )

    return system


@pytest.fixture(scope="session")
def test_model(test_temporal_settings, test_system):
    # Resample the timeseries attributes of the System to ensure data is interpolated and extrapolated correctly
    #  to cover all required model years and weather years
    system = test_system.copy()
    modeled_years = test_temporal_settings.modeled_years.data.loc[
        test_temporal_settings.modeled_years.data.values
    ].index
    system.resample_ts_attributes(
        modeled_years=(min(modeled_years).year, max(modeled_years).year),
        weather_years=(
            min(test_temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
            max(test_temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
        ),
    )

    # Construct the model
    model = ModelTemplate(
        system=system,
        temporal_settings=test_temporal_settings,
        construct_investment_rules=True,
        construct_operational_rules=True,
        construct_costs=True,
    )
    model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)

    return model


@pytest.fixture(scope="session")
def test_model_with_operational_groups(test_temporal_settings, test_system_with_operational_groups):
    # Resample the timeseries attributes of the System to ensure data is interpolated and extrapolated correctly
    #  to cover all required model years and weather years
    system = test_system_with_operational_groups.copy()
    modeled_years = test_temporal_settings.modeled_years.data.loc[
        test_temporal_settings.modeled_years.data.values
    ].index
    system.resample_ts_attributes(
        modeled_years=(min(modeled_years).year, max(modeled_years).year),
        weather_years=(
            min(test_temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
            max(test_temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
        ),
    )

    model = ModelTemplate(
        system=system,
        temporal_settings=test_temporal_settings,
        construct_investment_rules=True,
        construct_operational_rules=True,
        construct_costs=True,
    )
    model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)

    return model


@pytest.fixture(scope="session")
def test_model_inter_period_sharing(test_temporal_settings, test_system):
    # Change the TemporalSettings to enable inter-period sharing
    temporal_settings = copy.deepcopy(test_temporal_settings)
    temporal_settings.dispatch_window_edge_effects = DispatchWindowEdgeEffects.INTER_PERIOD_SHARING

    # Resample the timeseries attributes of the System to ensure data is interpolated and extrapolated correctly
    #  to cover all required model years and weather years
    system = test_system.copy()
    modeled_years = temporal_settings.modeled_years.data.loc[temporal_settings.modeled_years.data.values].index
    system.resample_ts_attributes(
        modeled_years=(min(modeled_years).year, max(modeled_years).year),
        weather_years=(
            min(temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
            max(temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
        ),
    )

    # Construct the model
    model = ModelTemplate(
        system=system,
        temporal_settings=temporal_settings,
        construct_investment_rules=True,
        construct_operational_rules=True,
        construct_costs=True,
    )
    model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)

    return model


@pytest.fixture(scope="session")
def test_model_production_simulation_mode(test_temporal_settings, test_results_settings, test_system):
    system = test_system.copy()
    modeled_years = test_temporal_settings.modeled_years.data.loc[
        test_temporal_settings.modeled_years.data.values
    ].index
    for asset in system.assets.values():
        asset.selected_capacity = 0
        asset.operational_capacity = ts.NumericTimeseries(
            name="operational_capacity", data=pd.Series(index=modeled_years, data=0)
        )
        asset.retired_capacity = ts.NumericTimeseries(
            name="retired_capacity", data=pd.Series(index=modeled_years, data=0)
        )
        asset.cumulative_retired_capacity = ts.NumericTimeseries(
            name="cumulative_retired_capacity", data=pd.Series(index=modeled_years, data=0)
        )
    for storage_resource in system.storage_resources.values():
        storage_resource.selected_storage_capacity = 0
        storage_resource.operational_storage_capacity = ts.NumericTimeseries(
            name="operational_storage_capacity", data=pd.Series(index=modeled_years, data=0)
        )
        storage_resource.retired_storage_capacity = ts.NumericTimeseries(
            name="retired_storage_capacity", data=pd.Series(index=modeled_years, data=0)
        )
        storage_resource.cumulative_retired_capacity = ts.NumericTimeseries(
            name="cumulative_retired_storage_capacity", data=pd.Series(index=modeled_years, data=0)
        )
    for fuel_storage_resource in system.fuel_storage_plants.values():
        fuel_storage_resource.selected_storage_capacity = 0
        fuel_storage_resource.operational_storage_capacity = ts.NumericTimeseries(
            name="operational_storage_capacity", data=pd.Series(index=modeled_years, data=0)
        )
        fuel_storage_resource.retired_storage_capacity = ts.NumericTimeseries(
            name="retired_storage_capacity", data=pd.Series(index=modeled_years, data=0)
        )
        fuel_storage_resource.cumulative_retired_capacity = ts.NumericTimeseries(
            name="cumulative_retired_storage_capacity", data=pd.Series(index=modeled_years, data=0)
        )

    model = ResolveModel(
        temporal_settings=test_temporal_settings,
        results_settings=test_results_settings,
        system=system,
        production_simulation_mode=True,
    )
    model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)

    return model


@pytest.fixture(scope="session")
def test_model_with_operational_groups_inter_period_sharing(
    test_temporal_settings, test_system_with_operational_groups
):
    # Change the TemporalSettings to enable inter-period sharing
    temporal_settings = copy.deepcopy(test_temporal_settings)
    temporal_settings.dispatch_window_edge_effects = DispatchWindowEdgeEffects.INTER_PERIOD_SHARING

    # Resample the timeseries attributes of the System to ensure data is interpolated and extrapolated correctly
    #  to cover all required model years and weather years
    system = test_system_with_operational_groups.copy()
    modeled_years = temporal_settings.modeled_years.data.loc[temporal_settings.modeled_years.data.values].index
    system.resample_ts_attributes(
        modeled_years=(min(modeled_years).year, max(modeled_years).year),
        weather_years=(
            min(temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
            max(temporal_settings.dispatch_windows_map.index.get_level_values("timestamp").year),
        ),
    )

    # Construct the model
    model = ModelTemplate(
        system=system,
        temporal_settings=temporal_settings,
        construct_investment_rules=True,
        construct_operational_rules=True,
        construct_costs=True,
    )
    model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT)

    return model


@pytest.fixture(scope="session")
def mini_fuels_system(dir_structure):
    """Creates an instance of the system that is associated with the class to be tested.

    This method is not intended to be called directly. Instead, use the `make_resource_group_copy()` fixture,
    which is a factory for generating a clean copy of the resource group.
    """
    _, group = System.from_csv(
        filename=dir_structure.data_interim_dir / "systems" / "TEST_fuels" / "attributes.csv",
        scenarios=["Test Scenario"],
        data={"dir_str": dir_structure, "year_start": 2020, "year_end": 2050},
    )

    return group


@pytest.fixture(scope="session")
def pathways_series_index():
    index = pd.DatetimeIndex(
        [
            "2031-01-01",
            "2032-01-01",
            "2033-01-01",
            "2034-01-01",
            "2035-01-01",
        ]
    )
    return index
