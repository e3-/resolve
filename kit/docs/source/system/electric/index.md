# Electric Sector

```{toctree}
:hidden:

resources/index
load
reserve
tx_paths
```

## Modeled Components

| Components                                                                                                | Used in Resolve | Used in Recap | Recap Test Case Example |
|-----------------------------------------------------------------------------------------------------------|:---------------:|:-------------:|-------------------------|
| [`AnnualEmissionsPolicy`](#new_modeling_toolkit.system.policy.AnnualEmissionsPolicy)                      |        ✓        |               |                         | 
| [`AnnualEnergyStandard`](#new_modeling_toolkit.system.policy.AnnualEnergyStandard)                        |        ✓        |               |                         |
| [`HourlyEnergyStandard`](#new_modeling_toolkit.system.policy.HourlyEnergyStandard)                        |        ✓        |               |                         |
| [`PlanningReserveMargin`](#new_modeling_toolkit.system.policy.PlanningReserveMargin)                      |        ✓        |               |                         |
| [`Asset`](#new_modeling_toolkit.system.asset.Asset)                                                       |        ✓        |               |                         |
| [`CandidateFuel`](#new_modeling_toolkit.system.fuel.CandidateFuel)                                        |        ✓        |               |                         |
| [`ELCCSurface`](#new_modeling_toolkit.system.electric.elcc.ELCCSurface)                                   |        ✓        |               |                         |
| [`Load`](#new_modeling_toolkit.system.electric.load_component.Load)                                       |        ✓        |       ✓       | `ISONE_load_2yr`        |
| [`TXPath`](#new_modeling_toolkit.system.electric.tx_path.TxPath)                                          |        ✓        |               |                         |
| [`Zone`](#new_modeling_toolkit.system.zone.Zone)                                                          |        ✓        |       ✓       | `ISONE`                 |
| [`ThermalResource`](#new_modeling_toolkit.system.electric.resources.thermal.ThermalResource)              |        ✓        |       ✓       | `gas_CT`                |
| [`HydroResource`](#new_modeling_toolkit.system.electric.resources.hydro.HydroResource)                    |        ✓        |       ✓       | `hydro`                 |
| [`VariableResource`](#new_modeling_toolkit.system.electric.resources.variable.VariableResource)           |        ✓        |       ✓       | `Solar`                 |
| [`HybridVariableResource`](#new_modeling_toolkit.system.electric.resources.hybrid.HybridVariableResource) |                 |       ✓       | `Solar`                 |
| [`StorageResource`](#new_modeling_toolkit.system.electric.resources.storage.StorageResource)              |        ✓        |       ✓       | `storage_4hr`           |
| [`HybridStorageResource`](#new_modeling_toolkit.system.electric.resources.hybridHybridStorageResource)    |        ✓        |       ✓       | `storage_4hr`           |
| [`ShedDrResource`](#new_modeling_toolkit.system.electric.resources.shed_dr.ShedDrResource)                |        ✓        |       ✓       | `shed_dr`               |
| [`FlexLoadResource`](#new_modeling_toolkit.system.electric.resources.flex_load.FlexLoadResource)          |        ✓        |       ✓       | `flex_load`             |