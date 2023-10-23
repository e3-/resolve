(inputs)=
# Creating Inputs
Using the Scenario Tool can be thought of as three separate steps:

1. **Defining component & linkage attributes**: This is synonymous with creating the attribute CSV files in `./data/interim` and 
can be thought of as creating the conceptual "database" (in lieu of an actual database structure) of all the possible component & linkage options. 
2. **Defining a system**: This is synonymous with creating the `./data/interim/system` instance folder, listing out all the 
components & linkages that will constitute the system of study.
3. **`Resolve` case settings**: These are the specific case configuration options, such as modeled years & which scenario inputs to include.

```{image} _images/resolve-data-flow.png
:alt: Overview of Resolve data flow from Scenario Tool to CSVs back to Results Viewer. 
:align: center
```

```{hint}
Users can configure which `data` folder to point the Scenario Tool to save to different `data` folders on the 
Cover & Configuration tab. This can be especially useful if your model's dataset is still in flux and you want to save 
older "snapshots" of the `data` folder for comparison. See [](comparing_cases.md) for tips on how to compare these folders.
```
---

## Saving Existing Inputs & Cases

For a "quick start", users can save all necessary inputs from the `RESOLVE Settings` tab of the Scenario Tool.

```{image} _images/scenario-tool-settings.png
:alt: Three buttons on the RESOLVE Settings tab to create case inputs & settings.
:width: 80%
:align: center
```

---

## Updating or Creating New Inputs

### 1. Component Data

The Resolve system being modeled is made up of various components, such as load components, resource, and policies. 
These components have attributes, such as heat rate, generation & load profiles, etc.

(scenario_tags)=
#### Scenario tagging functionality

See {ref}`input_scenarios` for discussion about how to determine which scenario tagged data is used in a specific model run. 

On most of the component & linkage attributes tabs, you will find a `Scenario` column. In the Scenario Tool, a single instance of 
a component can have **multiple** line entries in the corresponding data table as long as each line is tagged with a different scenario 
tag, as shown in the below screenshot. 

```{image} _images/resource-scenario-tags.png
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


#### Timeseries Data

Hourly timeseries data is now stored in separate CSV files under the `./data/profiles/` subfolder to keep the Scenario 
Tool spreadsheet filesize manageable. These CSVs must have the following format:

| timestamp                    | value             |
|------------------------------|-------------------|
| [timestamp (hour beginning)] | [attribute value] |
| ...                          | ...               |

On the Scenario Tool, you'll see certain data attributes have filepaths as their
input, which point the code to the relevant CSV file.

---

### 2. Configure a System

The "System" tab defines the energy system being modeled, which is composed of a list of various modeling components
(loads, resource, policies, etc.). This tab will have any pre-populated system configurations in the yellow table(s) 
to the right of the tab, and different systems are linked to the active case on the "RESOLVE Settings" tab.

```{image} _images/scenario-tool-system.png
:alt: Screenshot example of list of components in System. 
:width: 80%
:align: center
```

If users add any new modeling components (e.g., load components with new names, resources with new names), they will 
need to make sure that these new components are added to either an existing or new system configuration by updating 
the system list.

### 3. Define Case Settings

#### Editing Custom Constraints

#### Editing Timeseries Clustering


---

## Comparing & Verifying Inputs

- Case settings are saved in the `./settings/resolve/` subdirectory of your `data` folder. Each set of case settings has 
  its own folder of settings files.
- All `System` data is stored in the `./interim/` subdirectory of your `data` folder. Within the `./interim/` directory, 
  you'll find subdirectories for different types of components––such as loads, resources, policies.

The fundamental design decision was that the `Resolve` data folder should be thought of as a pseudo-database, 
shared across various cases. This does come with the tradeoff that—without careful planning—you can overwrite data in your pseudo-database. 

1. Save different `data` folders and compare the `[data folder]/interim` subfolders (using some text comparison tool like `kdiff`)
   - From the Scenario Tool, you can save your data to different folders. This specified on the `Cover & Configuration` tab
2. Compare `System` instance JSONs (also using some text comparison tool like `kdiff`)
3. Use `xltrail` to compare Scenario Tools

::::{dropdown} Comparing `data` Folders using `kdiff` or PyCharm
Since the `./data/` folders just contain text (mainly `csv`) files, you can use any "diff" tool to compare these folders. 
Many people at E3 use [`kdiff3`](https://download.kde.org/stable/kdiff3/?C=M;O=D), though other tools like PyCharm work. 
In general, you should see highlights of additions, deletions, or modifications at a line level within `csv` files.

:::{image} _images/diffing-folders.png
:alt: Example of how PyCharm shows `diffs` (text file differences) between two data files. 
:width: 80%
:align: center
:::

::::

::::{dropdown} Comparing `System` Instance `json` Files
Finally, you can compare the `json` file reported after the `Resolve` model instance is constructed. This is saved in 
`./reports/resolve/[case name]/[timestamp]/`. `json` files are nested text files. This `json` file gives you the best 
look at the data as `Resolve` understands it, as it includes all the data from the `System` instance that is being 
read into `Resolve` (i.e., after scenario tag filtering and timeseries resampling).