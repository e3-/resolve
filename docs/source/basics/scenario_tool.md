(inputs)=
# Using the Scenario Tool
Using the Scenario Tool can be thought of as three separate steps:

1. **Defining component & linkage attributes**: This is synonymous with creating the attribute CSV files in `./data/interim` and 
can be thought of as creating the conceptual "database" (in lieu of an actual database structure) of all the possible component & linkage options. 
2. **Defining a system**: This is synonymous with creating the `./data/interim/system` instance folder, listing out all the 
components & linkages that will constitute the system of study.
3. **`Resolve` case settings**: These are the specific case configuration options, such as modeled years & which scenario inputs to include.

```{image} ../_images/scenario-tool-steps.png
:alt: Screenshot of three "steps" of `Resolve` model setup, consisting of (1) defining component & linkage attributes, (2) defining a system, and (3) `Resolve` case settings. 
:width: 80%
:align: center
```

```{warning}
At this time, saving data out of the Scenario Tool may not work properly when there are row filters applied. 
For now, users will need to remember to **clear or turn off any filters** on all sheets before saving data. 

_Track progress on a resolution with issue [#545](https://github.com/e3-/kit/issues/545)._
```

```{note}
Two major data structure changes from previous versions of the `main` Resolve code will affect 
data management. 
1. [#214](https://github.com/e3-/kit/issues/214) has been addressed, removing the extra 
level of folders where all input CSVs were named `attributes.csv`. 
2. Users can configure which `data` folder to point the 
code to--this will be reflected in that the `test` case will be moved to a `data-test` folder, while "main" data from 
the CPUC IRP and Scenario Tool will populate a new, blank `./data` folder. This change has been done to prevent collisions between 
linkage attributes while the team works on a longer-term solution to our linkage attributes design.
```


### 1. Component & Linkage Attributes

Currently, component & linkage attributes tabs are colored green. 

(scenario_tags)=
#### Scenario tagging functionality

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

#### Hourly load & generation profiles

Hourly load & generation profiles are found [on Box](https://willdan.box.com/s/ryhm8yi22jmzjrk2aalfzb00ium9n71h) due to the relatively large size of all the CSV files. 
Users should plan to download the folder and place the `profiles` folder inside `./data` (next to the `interim` subfolder). 

### 2. System Setup

Currently, the system setup tab is dark blue. 

In the initial version of the Scenario Tool, users need to enumerate every component (e.g., resource, transmission path) and 
linkage (i.e., relationship between two components) to be included in the modeled `System` instance. Orange dropdowns help 
users select the correct data values for the component & linkage class names (e.g., `Asset` and `AllToPolicy`). 

Component names should match the names of components on the various component & linkage attribute tabs. On each of the 
component & linkage attribute tabs, users will find a column named "Included in Current System...", which helps users identify 
whether any components listed in the data tables is not included in the `System` instance configured on the System tab. 
It is then up to the user to determine whether that is intentional or not, as the `System` can include any subset of the 
components & linkages defined with data.

### 3. `Resolve` Case Settings

The `Resolve` Settings tab is where users specify how `Resolve` should run, as well as providing 
a button that will run the code. The "Run `Resolve` Case" button will run the equivalent command:

```
python run_opt.py --solver-name [solver name] --log-level INFO --extras cpuc_irp
```

```{warning}
At this time, pressing teh "Run `Resolve` Case" button will run the model but will not show a Terminal/Command Prompt while the model is running.
```

#### Settings

(input_scenarios)=
##### Input Scenarios

See {ref}`scenario_tags` for discussion about how to input scenario tagged data for components & linkages. 

As discussed in {py:func}`new_modeling_toolkit.common.component.Component.from_csv`, input scenario tags are prioritized 
based on the order of scenarios in the `Resolve` case. Scenarios listed toward the bottom of the scenario list are higher priority 
and more likely to override other data if data is tagged with a "lower priority" scenario tag. In the screenshot below, for example, 
data tagged with the `base` tag will the lowest priority, since it is the first tag in the scenario list. For any of the 
subsequent scenario tags (e.g., `2021_PSP_22_23_TPP_ITC_ext`), to the extent that there is data that is tagged with the higher 
priority scenario tag, that higher priority data will override any `base`-tagged data.

```{image} ../_images/scenario-settings.png
:alt: Screenshot of user dropdown inputs to specify scenarios to be read in `Resolve` case.
:width: 60%
:align: center
```
On the `Resolve` Settings tab, users will find an orange dropdown inputs menu to help ensure that input scenarios selected 
are based on scenario tags that already are defined on the respective component & linkage attribute tabs. 
In the first column, select the sheet on which to look up available scenario tags. Then, in the second column, the dropdown input 
should only present scenario tags that are already defined on the respective sheet of the Scenario Too.

##### Representative Period Settings

Users can select whether the representative periods used for chronological dispatch are endogenously clustered (using the 
k-medoids method) or manually defined. To replicate the CPUC IRP Preferred System Plan, the Scenario Tool is initial configured with 
the `manual` setting for 37 representative periods. Users will find the corresponding inputs to manually configure the 
representative periods on the Temporal Settings tab. 

```{note}
The UC Merced team may want to change the dropdown input (via Data Validations in Excel) to enable the "critical timesteps" 
functionality.
```

##### Financial Discounting Settings

The model will now endogenously calculate the annual discount factors to use for each modeled year based on four pieces 
of information:
1. **Cost dollar year:** The dollar year that costs are input in & should be reported out in. In general, `Resolve` is designed 
to be in real dollars for a specific dollar year.
2. **Modeled years:** Which modeled years to include in the `Resolve` case.
3. **End effect years:** The number of years to extrapolate out the last modeled year. In other words, considering 20 years 
of end effects after 2045 would mean that the last model year's annual discount factor would represent the discounted cost 
of 2045-2064, assuming that the 2045 costs are representative of a steady-state future for all end effect years.
4. **Annual discount rate:** Real discount rate in each year

##### Solver Settings

For now, users must follow the pattern of `solver.[solver name].[solver option].[data type]` when setting the solver settings. 
For example, users wanting to set Gurobi's [`Method` setting](https://www.gurobi.com/documentation/9.5/refman/method.html) 
would need to enter `solver.gurobi.Method.int` and the corresponding value. 

#### Custom Constraints

Currently, the Scenario Tool is set up to allow users to specify any kind of **annual** constraint, though the underlying 
custom constraint functionality is more flexible and can be utilized to constrain any variables in the model formulation.

Users can define custom constraints by enumerating the coefficient to apply to various model formulation variables & expressions 
to define the "left-hand side" of the constraints, then define the corresponding "right-hand side" of the custom constraints.  
At this time, users will need to manually search {py:obj}`new_modeling_toolkit.resolve.model_formulation.ResolveCase` for the 
applicable Pyomo `Var` and `Expression` components.

## Comparing Cases & Systems

### Comparing Cases

### Comparing Systems

The fundamental design decision was that the `Resolve` data folder should be thought of as a pseudo-database, 
shared across various cases. This does come with the tradeoff that—without careful planning—you can overwrite data in your pseudo-database. 

1. Save different `data` folders and compare the `[data folder]/interim` subfolders (using some text copmarison tool like `Kdiff`)
   - From the Scenario Tool, you can save your data to different folders. This specified on the `Cover & Configuration` tab
2. Compare `System` instance JSONs (also using some text copmarison tool like `Kdiff`)
3. Use `xltrail` to compare Scenario Tools
---

:::{eval-rst}
.. raw:: html

    <div class="giscus-container">
        <script src="https://giscus.app/client.js"
            data-repo="e3-/kit"
            data-repo-id="MDEwOlJlcG9zaXRvcnkzMjkxMzIyNzQ="
            data-category="Documentation"
            data-category-id="DIC_kwDOE54o8s4CWsWE"
            data-mapping="pathname"
            data-strict="0"
            data-reactions-enabled="1"
            data-emit-metadata="0"
            data-input-position="bottom"
            data-theme="preferred_color_scheme"
            data-lang="en"
            crossorigin="anonymous"
            async>
        </script>
    </div>
