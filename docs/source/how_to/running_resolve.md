# RESOLVE How-To's

<!---
The heading below is intentionally left blank because 
I want to skip a heading level (to have smaller font size).
-->
##


### How do I run `RESOLVE` from the command line?

1. In a command line, navigate into the `./new_modeling_toolkit/resolve` directory
2. Activate the `new-modeling-toolkit` conda environment: `conda activate new-modeling-toolkit`
3. Use the command `python run_opt.py` to run a case. The `run_opt.py` script accepts four arguments/options:
    ```
     Usage: run_opt.py [OPTIONS] [RESOLVE_SETTINGS_NAME]                                    

    ╭─ Arguments ──────────────────────────────────────────────────────────────────────────╮
    │   resolve_settings_name      [RESOLVE_SETTINGS_NAME]  Name of a RESOLVE case (under  │
    │                                                       ./data/settings/resolve). If   │
    │                                                       `None`, will run all cases     │
    │                                                       listed in                      │
    │                                                       ./data/settings/resolve/cases… │
    │                                                       [default: None]                │
    ╰──────────────────────────────────────────────────────────────────────────────────────╯
    ╭─ Options ────────────────────────────────────────────────────────────────────────────╮
    │ --data-folder                               TEXT  Name of data folder, which is      │
    │                                                   assumed to be in the same folder   │
    │                                                   as `new_modeling_toolkit` folder.  │
    │                                                   [default: data]                    │
    │ --solver-name                               TEXT  [default: cbc]                     │
    │ --log-level                                 TEXT  Any Python logging level: [DEBUG,  │
    │                                                   INFO, WARNING, ERROR, CRITICAL].   │
    │                                                   Choosing DEBUG will also enable    │
    │                                                   Pyomo `tee=True` and               │
    │                                                   `symbolic_solver_labels` options.  │
    │                                                   [default: INFO]                    │
    │ --extras                                    TEXT  Enables a RESOLVE 'extras' module, │
    │                                                   which contains project-specific    │
    │                                                   add-on constraints.                │
    │                                                   [default: None]                    │
    │ --raw-results           --no-raw-results          If this option is passed, the      │
    │                                                   model will report all Pyomo model  │
    │                                                   components directly.               │
    │                                                   [default: no-raw-results]          │
    │ --help                                            Show this message and exit.        │
    ╰──────────────────────────────────────────────────────────────────────────────────────╯
    ```

```{note}
Hint: If you're in your command line and unsure what arguments to pass to `run_opt.py`, use the `--help` argument!
```

### How do I create a new resource?

1. Create a new resource line item in the table on the `Resources` tab. 
   - See 
   {py:class}`new_modeling_toolkit.common.asset.plant.resource.Resource` field list for documentation of various 
   resource parameters available to be set, as well as {ref}`input_scenarios` for how to utilize Resolve's 
   scenario-tagging functionality
2. Add the resource to the `components` table on the `System` tab. Using the dropdown validation, select 
the component type (i.e., `Resource`) and the name of the new resource. 
3. Link the new resource to other components in the system in the `linkages` table on the `System` tab. Key linkages include: 
**`AllToPolicy`** (if resource contribute to any emissions, RPS, or PRM policies),
**`CandidateFuelToResource`** (if resource burns any fuels),
**`PlantToReserve`** (if provides any operational reserves, such as regulating reserves),
**`ResourceToELCC`** (if resource is on an ELCC curve or surface),
**`ResourceToZone`** (which will locate your resource in a zone in the model),
   - Again, use the dropdown validation to select (a) the linkage type (e.g., `AllToPolicy`).
   - As discussed in [The `Linkage` Class](../core/linkages.md), linkages are currently **directional**, so make sure you 
   correctly define the correct "component_from" and "component_to" (which is hinted based on the name of the linkage 
   class, such as `ResourceToZone`) 
4. If necessary, add "linkage parameters" to specify data related to the relationship 
of two components. For example, the GHG emissions factor associated with a generation resource.
5. Save updated components to CSV via the button on the `Components →` tab
6. Save your updated system instance via the button on the `System` tab. 
   - You can keep the same instance name, your system instance CSV files will be overwritten and updated.
   - Alternatively, you can choose to **rename** your new system instance. If you chose to rename your system instance, 
   make sure you update the system that your RESOLVE case setting refer to on `RESOLVE Settings` 
   (otherwise, your next RESOLVE run will not include your new resource).

### How do I create an electrolytic fuel?

```{warning}
Currently, there is no place to configure electrolytic fuels in the Scenario Tool. Users can still parametrize 
electrolytic fuels manually (by creating CSV files in the `./data/interim/` folder by following the steps below). 
```

The `ElectrofuelResource` resource in RESOLVE currently represents a combined electrochemical process + storage asset. 

1. In `./data/interim/electrofuel_resources`, create a new CSV file in the [`attributes.csv` format](../core/components.md).
   - See {py:class}`new_modeling_toolkit.common.asset.plant.electrofuel_resource.ElectrofuelResource` and its parent 
   class {py:class}`new_modeling_toolkit.common.asset.plant.Plant` for a list of applicable input data fields. These 
   include fixed and variable costs, as well as using `increase_load_potential_profile` to optionally constraint hourly 
   electrolytic fuel production
2. Make sure your electrofuel resource has a corresponding candidate fuel. For example, your electrofuel resource may 
be called `Hydrogen_Electrolysis`, and it would have a corresponding candidate fuel called `Hydrogen`.
3. As you would do via the Scenario Tool, update other related parts of the system:
   1. Add the new electrofuel resource to the `components.csv` under `.data/interim/systems/[system name]`
   2. Link your new electrofuel resource to any other components in the `linkages.csv` under `.data/interim/systems/[system name]`. 
   Key linkages likely include: **`ElectrofuelResourceToZone`** and **`ElectrofuelResourceToCandidateFuel`**

### How do I parametrize flexible load resource shifting constraints?

---

:::{eval-rst}
.. raw:: html

    <div class="giscus-container">
        <script src="https://giscus.app/client.js"
            data-repo="e3-/new-modeling-toolkit"
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
