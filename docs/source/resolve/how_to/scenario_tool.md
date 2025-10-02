---
tocdepth: 4
---

# Scenario Tool

The Scenario Tool is intended to be a more familiar interface for analysts to make bulk edits to data & case settings
saved in the CSV files in the `data-folder`. The Scenario Tool is made up of three categories of tabs:

1. Resolve Settings {bdg-primary-line}`multiple tabs`
2. System {bdg-secondary-line}`one tab`
3. Component tabs {bdg-primary-line}`multiple tabs`

Depending on project needs, the component tabs may be configured in different ways; however, the default layout has the
following sub-groups of tabs:

::::{card-carousel} 2
:::{card} System Costs Representing non-optimized costs of the modeled system that would make up a Total Resource Cost (
TRC) or total Revenue Requirement (RR).
:::
:::{card} Loads & Operating Reserve Requirements

- Load Components
- Operating Reserves
  :::
  :::{card} Policies
- PRM
- RPS & CES
- GHG
  :::
  :::{card} Resources
- Thermal
- Variable
- Hydro
- Storage
- Shed DR & Flex Loads
  :::
  :::{card} Zones & Transmission

:::
:::{card} Fuels

- Commodity Fuels
- {bdg-warning-line}`soon` Electrolytic Fuels
- {bdg-warning-line}`soon` Biofuels
- {bdg-warning-line}`soon` Fuel Storage & Transport
  :::
  ::::

---

## Working with `Components`

### Creating a New Component

### Modifying an Existing Component

- Finding where existing data lives
- Using scenario tagging functionality to layer data

## Working with `Linkages`

### Linking Components

### Defining Linkage Data

## Composing a `System`

## Working with Case Settings

### 1. `Component` & `Linkage` Attributes

Currently, component & linkage attributes tabs are colored green.

(scenario_tags)=

#### Scenario tagging functionality

See {ref}`input_scenarios` for discussion about how to determine which scenario tagged data is used in a specific model
run.

On most of the component & linkage attributes tabs, you will find a `Scenario` column. In the Scenario Tool, a single
instance of a component can have **multiple** line entries in the corresponding data table as long as each line is
tagged with a different scenario tag, as shown in the below screenshot.

```{image} ../../_images/resource-scenario-tags.png
:alt: Screenshot from Scenario Tool showing multiple scenario tags for the same resource.
:align: center
```

Scenario tags can be populated *sparsely*; in other words, every line entry for the same resource does not have to be
fully populated across all columns in the data tables. In the example screenshot above, this is demonstrated by
the `base` scenario tag having data for "Total (Planned + New) Resource Potential in Modeled Year (MW)" and no data
for "All-In Fixed Cost by Vintage (
$/kW-year)", whereas the scenario tags `2021_PSP_22_23_TPP` and `2021_PSP_22_23_TPP_High` are the reverse.

#### Hourly load & generation profiles

Hourly load & generation profiles are found [on Box](https://willdan.box.com/s/ryhm8yi22jmzjrk2aalfzb00ium9n71h) due to
the relatively large size of all the CSV files. Users should plan to download the folder and place the `profiles` folder
inside `./data` (next to the `interim`
subfolder).

### 2. System Setup

Currently, the system setup tab is dark blue.

In the initial version of the Scenario Tool, users need to enumerate every component (e.g., resource, transmission path)
and linkage (i.e., relationship between two components) to be included in the modeled `System` instance. Orange
dropdowns help users select the correct data values for the component & linkage class names (e.g., `Asset`
and `AllToPolicy`).

Component names should match the names of components on the various component & linkage attribute tabs. On each of the
component & linkage attribute tabs, users will find a column named "Included in Current System...", which helps users
identify whether any components listed in the data tables is not included in the `System` instance configured on the
System tab. It is then up to the user to determine whether that is intentional or not, as the `System` can include any
subset of the components & linkages defined with data.

### 3. Resolve Case Settings

The Resolve Settings tab is where users specify how Resolve should run, as well as providing a button that will run the
code. The "Run Resolve Case" button will run the equivalent command:

```
python run_opt.py --solver-name [solver name] --log-level INFO --extras cpuc_irp
```

```{warning}
At this time, pressing teh "Run Resolve Case" button will run the model but will not show a Terminal/Command Prompt while the model is running.
```

#### Settings

(input_scenarios)=

##### Input Scenarios

See {ref}`scenario_tags` for discussion about how to input scenario tagged data for components & linkages.

As discussed in {py:func}`new_modeling_toolkit.common.component.Component.from_csv`, input scenario tags are prioritized
based on the order of scenarios in the Resolve case. Scenarios listed toward the bottom of the scenario list are higher
priority and more likely to override other data if data is tagged with a "lower priority" scenario tag. In the
screenshot below, for example, data tagged with the `base` tag will the lowest priority, since it is the first tag in
the scenario list. For any of the subsequent scenario tags (e.g., `2021_PSP_22_23_TPP_ITC_ext`), to the extent that
there is data that is tagged with the higher priority scenario tag, that higher priority data will override any `base`
-tagged data.

```{image} ../../_images/scenario-settings.png
:alt: Screenshot of user dropdown inputs to specify scenarios to be read in Resolve case.
:width: 60%
:align: center
```

On the Resolve Settings tab, users will find an orange dropdown inputs menu to help ensure that input scenarios selected
are based on scenario tags that already are defined on the respective component & linkage attribute tabs. In the first
column, select the sheet on which to look up available scenario tags. Then, in the second column, the dropdown input
should only present scenario tags that are already defined on the respective sheet of the Scenario Too.

##### Representative Period Settings

Users can select whether the representative periods used for chronological dispatch are endogenously clustered (using
the k-medoids method) or manually defined. To replicate the CPUC IRP Preferred System Plan, the Scenario Tool is initial
configured with the `manual` setting for 37 representative periods. Users will find the corresponding inputs to manually
configure the representative periods on the Temporal Settings tab.

```{note}
The UC Merced team may want to change the dropdown input (via Data Validations in Excel) to enable the "critical timesteps" 
functionality.
```

##### Financial Discounting Settings

The model will now endogenously calculate the annual discount factors to use for each modeled year based on four pieces
of information:

1. **Cost dollar year:** The dollar year that costs are input in & should be reported out in. In general, Resolve is
   designed to be in real dollars for a specific dollar year.
2. **Modeled years:** Which modeled years to include in the Resolve case.
3. **End effect years:** The number of years to extrapolate out the last modeled year. In other words, considering 20
   years of end effects after 2045 would mean that the last model year's annual discount factor would represent the
   discounted cost of 2045-2064, assuming that the 2045 costs are representative of a steady-state future for all end
   effect years.
4. **Annual discount rate:** Real discount rate in each year

##### Solver Settings

For now, users must follow the pattern of `solver.[solver name].[solver option].[data type]` when setting the solver
settings. For example, users wanting to set
Gurobi's [`Method` setting](https://www.gurobi.com/documentation/9.5/refman/method.html)
would need to enter `solver.gurobi.Method.int` and the corresponding value.

#### Extras

##### 2021 CPUC IRP PSP Extras

###### IRP Hydro Budgets

For the CPUC IRP case, hydro operational parameters are unique in that they are sampled from 2008, 2009, and 2011 hydro
years. This means that the implementation of the data in the current version of the Scenario Tool on
the `Extras - Hydro` tab is specifically tailored to the 37 representative days from previous versions of Resolve. Hydro
operational parameters provide monthly Pmin, Pmax and energy budgets to be assigned to the representative days.

```{warning}
The hydro operational parameters on the `Extras - Hydro` tab are specific to the original 37 representative days from the 
CPUC IRP. At this time, hydro data is not included in the Box folder but the team hopes to push an update in the coming 
weeks to make parametrizing hydro operations easier.
```

###### Local Capacity Optimization Extras

TBD

##### HECO Energy Reserve Margin Extras

TBD

#### Custom Constraints

Currently, the Scenario Tool is set up to allow users to specify any kind of **annual** constraint, though the
underlying custom constraint functionality is more flexible and can be utilized to constrain any variables in the model
formulation.

Users can define custom constraints by enumerating the coefficient to apply to various model formulation variables &
expressions to define the "left-hand side" of the constraints, then define the corresponding "right-hand side" of the
custom constraints.  
At this time, users will need to manually search {py:obj}`new_modeling_toolkit.resolve.model_formulation.ResolveCase`
for the applicable Pyomo `Var` and `Expression` components.

##### CAISO Deliverability Constraints

The primary use of custom constraints in the CPUC IRP case is to capture transmission deliverability upgrade costs
associated with resource builds (particularly renewables & storage).

```{warning}
While the data for the deliverability constraint upgrades are included in the Scenario Tool, users running the case will find that 
`kit` version of the case does not replicate the upgrade decisions found in the CPUC IRP Preferred System Plan. 
The project team will provide an update on the data in the coming weeks to hopefully resolve this issue.  
```

