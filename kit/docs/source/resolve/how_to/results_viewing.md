# Results Viewers

## Spreadsheet Results Viewer

Resolve includes a refreshed Excel Results Viewer. The goal of the updated Results Viewer was to streamline results
reporting formulas while maintaining key results reporting capabilities. As part of this streamlining process,
the `Portfolio Analytics` tab of previous Results Viewers has been removed, so "raw" results reported in CSV format from
the Resolve code are directly calculated into various tables on the `Dashboard` tab

Similar to the updated Scenario Tool, the new Results Viewer uses `xlwings` for its core file operations.

### Setup Instructions

As with the [updated Scenario Tool](scenario_tool.md), the new Results Viewer relies on `xlwings`. As with the Scenario
Tool, you will find an `xlwings.conf` tab in the Results Viewer. The same instructions for
{ref}`configuring xlwings<configure-xlwings>` applies to this spreadsheet.

### Loading a Results Report

The `Dashboard` tab houses all the summarized results & summary charts. This tab has three buttons:

1. **Update Cases List:** Looks at the `reports` subfolder for Resolve results folders that can be loaded and updates
   the "Selected Cases to View" dropdown cell.
2. **Load Summary Results:** Loads the selected case to be displayed in the Results Viewer.
3. **Copy Snapshot of Current Dashboard:** Saves a copy of the `Dashboard` tab with the current time as a timestamp.

```{image} ../../_images/results-viewer-buttons.png
:alt: Screenshot of Results Viewer control buttons.
:width: 60%
:align: center
```

Once the Results Viewer loads in the CSV results files, the tables on the `Dashboard` tab should be updated. An example
of the summary charts is shown below:

```{image} ../../_images/results-viewer-total-build.png
:alt: Example of Total Resource Build chart from Results Viewer.
:width: 60%
:align: center
```

Reported results include:

- System Costs
    - Non-Modeled Cost
    - Capital & Fixed Costs
    - Variable Costs
- System Build
    - Total Nameplate Capacity
    - Selected & Retired Nameplate Capacity
    - Baseline Nameplate Capacity
    - Selected Storage Power
    - Selected Storage Energy
    - Selected Storage Duration
- System Dispatch
    - Annual Energy
    - Zonal Unserved Energy or Overgeneration
- Planning Reserve Margin & ELCCs
    - Achieved PRM
    - Target PRM
    - Marginal ELCC Metrics (CPUC IRP-specific)
- Emissions Target
    - CAISO Emissions
    - Total GHG Abatement Cost (CPUC IRP-specific)
    - Rest of WECC Emissions
    - Fossil Resource Emissions & Average Emissions Factors
- RPS & SB100 Target
- Regional Transmission Paths
    - Gross Imports
    - Gross Exports
    - Gross Regional Market Import Cost
    - Gross Regional Market Export Revenue
    - Unspecified Import Carbon Allowance Cost (CPUC-IRP-specific)
- CAISO Transmission Deliverability Upgrades (CPUC IRP-specific)
    - Selected CAISO Transmission Deliverability Upgrades
    - Selected Upgrades as % of Potential
    - Selected Upgrade Costs
    - On-Peak Deliverability Constraints
    - Secondary Deliverability Constraints
    - Off-Peak Deliverability Constraints
    - CAISO Renewable Build by Location

### Configuring Results Reporting Groups

Results can be grouped in different ways by updating the tables on the `Results Grouping` tab, as shown in the
screenshot below.
![](../../_images/results-viewer-groupings.png)

**Zones to aggregate.** For the most part, formulas should be able to sum over multiple modeled zones. By default in the
CPUC IRP case, the two zones to aggregate are `CAISO` and `CAISO_NW_Hydro`, but users should be able to toggle `SW`, for
example.

**Names of results groups for different categories of results (e.g., system build).** For each category of results, This
table assigns the unique reporting groups. For example, for results reporting using the "Build & Dispatch"
groupings,  
users can expect that results groups such as `Nuclear`, `Coal`, etc.

```{warning}
At this time, the table "indices" on the `Dashboard` tab do not automatically update should a user change, add, or 
remove unique results groups. Users will need to manually update the index names of each summary table.  
```

**Assignment of different resources to the results groups.** Given the unique results groupings, this table lists how
each resource (or transmission path, etc.) is assigned to that grouping. As shown in the screenshot, users can expect
that `Arizona_Li_Battery` and `CAISO_Baseline_Li_Battery` are both summed into the group called `Battery Storage`
for tables on the `Dashboard` tab using the "Build & Dispatch` groupings. Those same resources may be grouped
differently in a different summary table, depending on the groupings assigned in this table.

## Jupyter Results Viewer

```{note}
Under construction
```

## Viewing Results via `System` API

```{note}
Under construction
```

The long-run goal of `kit`-based models is to leverage the object-oriented underpinnings to enable more consistent &
flexible results reporting. At this time, results can be retrieved by a savvy user from the `ResolveCase`
and `System` instances; however, the public API for doing so is a work in progress.

