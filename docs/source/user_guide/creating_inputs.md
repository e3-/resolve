# 1. `Component` Data

`Components` are the fundamental building block of what `Resolve` models. All `Components` have attributes that 
can be set via the Scenario Tool. 

| Class                 | Description                                                                                           |
|-----------------------|-------------------------------------------------------------------------------------------------------|
| AnnualEmissionsPolicy | Annual emissions accounting that can encompass generation & importing transmission paths.             |
| AnnualEnergyStandard  | Renewable Portfolio Standard (RPS) or Clean Energy Standard (CES)-type policies.                      |
| Asset                 | Any physical asset where we want to track & optimize investment costs.                                |
| CandidateFuel         | A fuel that can be used by generators (or created if using electrolytic fuel production)              |
| ELCCSurface           | ELCC surface inputs                                                                                   |
| Load                  | A load component consisting of an hourly profile and an annual energy and/or peak forecast.           |
| PlanningReserveMargin | A Planning Reserve Margin (PRM) reliability accounting constraint, interacts with `ELCCSurface`.      |
| Reserve               | Operating reserves, such as spin, regulation, load following.                                         |
| Resource              | An `Asset` used for electric sector operations (e.g., thermal generator, battery, variable resource). |
| TXPath                | `Resolve` uses a "transportation" ("pipe-and-bubble") model for transmission flows between zones.     |
| Zone                  | A location, constrained by transmission, where loads & resources are located.                         |


(scenario_tags)=
## Scenario tagging functionality

See {ref}`input_scenarios` for discussion about how to determine which scenario tagged data is used in a specific model run. 

On most of the component & linkage attributes tabs, you will find a `Scenario` column. In the Scenario Tool, a single instance of 
a component can have **multiple** line entries in the corresponding data table as long as each line is tagged with a different scenario 
tag, as shown in the below screenshot. 

```{image} ../_images/resource-scenario-tags.png
:alt: Screenshot from Scenario Tool showing multiple scenario tags for the same resource.
:align: center
```

Scenario tags can be populated *sparsely*; in other words, every line entry for the same resource does not have to be fully populated 
across all columns in the data tables. In the example screenshot above, this is demonstrated by the `base` scenario tag having 
data for "Total (Planned + New) Resource Potential in Modeled Year (MW)" and no data for "All-In Fixed Cost by Vintage ($/kW-year)", 
whereas the scenario tags `2021_PSP_22_23_TPP` and `2021_PSP_22_23_TPP_High` are the reverse. 

The Scenario Tool will automatically create CSVs for all the data entered into the Scenario Tool. These CSVs have a 
four-column, "long" orientation.

| timestamp                            | attribute        | value   | scenario (optional) |
|--------------------------------------|------------------|---------|---------------------|
| [None or timestamp (hour beginning)] | [attribute name] | [value] | [scenario name]     |
| ...                                  | ...              | ...     | ...                 |


## Timeseries Data

Hourly timeseries data is now stored in separate CSV files under the `./data/profiles/` subfolder to keep the Scenario 
Tool spreadsheet filesize manageable. These CSVs must have the following format:

| timestamp                    | value             |
|------------------------------|-------------------|
| [timestamp (hour beginning)] | [attribute value] |
| ...                          | ...               |

On the Scenario Tool, you'll see certain data attributes have filepaths as their
input, which point the code to the relevant CSV file.
