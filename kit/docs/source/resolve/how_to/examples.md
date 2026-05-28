# Examples

The `kit` repository includes two sets of test case data to start with.

## Minimal Test Case

The `kit` repository includes a minimal test case that should run out-of-the-box by running the `run_opt.py`
script with the `--data-folder data-test` command line argument (see [Quick Start](../../quick_start)).

The `test` case settings can be found [here](https://github.com/e3-/kit/tree/main/data/settings/resolve/test), and
the `test` system components & linkages can be
found  [here](https://github.com/e3-/kit/tree/main/data/interim/systems/test)

### `test` System Components

As you can see in
the [`components.csv` file](https://github.com/e3-/kit/blob/main/data/interim/systems/test/components.csv), the `test`
system is composed of:

- 2 zones
- 4 load components (two per zone)
- 1 transmission path (between the two zones)
- 6 resources (batteries, solar, wind, gas)
- 1 candidate fuel
- 1 operating reserve
- 3 policy constraints
- 1 ELCC surface (for use with PRM policy constraint)

| component     | instance           |
|---------------|--------------------|
| Load          | zone_1             |
| Load          | zone_1_BE          |
| Load          | zone_2             |
| Load          | zone_2_BE          |
| Resource      | Solar              |
| Resource      | Wind               |
| Resource      | Gas_CCGT           |
| Resource      | Gas_CT             |
| Resource      | Battery            |
| Resource      | Gas_CCGT_2         |
| Zone          | zone_1             |
| Zone          | zone_2             |
| CandidateFuel | Fossil_Natural_Gas |
| Reserve       | downward_reg       |
| Policy        | PRM                |
| Policy        | RPS                |
| Policy        | CO2                |
| ELCCSurface   | solar_wind         |
| TXPath        | TxPath             |

## 2021 CPUC IRP Preferred System Plan Case

```{note}
This section is under construction. 

Previously, a Jupyter notebook was supplied in the `./notebooks` directory that would reformat old Resolve input folders 
into `kit` format. This notebook is under re-construction, and the recommended path for getting CPUC IRP PSP 
data is by using the newly-supplied  Scenario Tool.

Please see the [Resolve Scenario Tool page]./scenario_tool.md) for how create a more complete set of CPUC IRP 
Preferred System Plan case data. 
```

