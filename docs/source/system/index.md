# Overview

A `System` is the basic data structure that defines the energy system that is being modeled. Depending on use-case, this
energy system can encompass the electric sector or multiple sectors of the economy, similar to the Sankey diagram below.

![llnl-sankey](https://flowcharts.llnl.gov/sites/flowcharts/files/2023-10/US%20Energy%202022.png)

## Thinking About Demand & Supply

**Key things to think about are:**

1. What kinds of energy demands does each sector have, and how will those evolve in response to policy scenarios?
2. What fuels/energy carriers can be used to meet each of those energy demands (electricity, fossil fuels, biofuels,
   etc.)?
3. What are the costs & emissions impacts associated with meeting those energy demands?
4. When using electricity as an energy carrier, what does the hourly (or sub-hourly) demand profile look like (i.e.,
   load shaping)?

![pathways-supply-demand](../_images/pathways-supply-demand.png)

[//]: # (## Modeled Sectors)

[//]: # (```{mermaid})

[//]: # (:caption: Asset inheritance diagram <br>&#40;click any of the blue boxes in the diagram to jump to the relevant documentation&#41;)

[//]: # (:align: center)

[//]: # ()

[//]: # (%%{ )

[//]: # (    init: {)

[//]: # (        "theme": "base",)

[//]: # (        "themeVariables": {)

[//]: # (            'primaryColor': '#E2ECF0',)

[//]: # (            'primaryTextColor': '#034E6E',)

[//]: # (            'primaryBorderColor': '#E2ECF0',)

[//]: # (            'lineColor': '#BFBFBF',)

[//]: # (            'secondaryColor': '#E2ECF0',)

[//]: # (            'tertiaryColor': '#E2ECF0',)

[//]: # (            'fontFamily': 'rubik')

[//]: # (        },)

[//]: # (        'flowchart': { )

[//]: # (            'curve': 'bumpY' )

[//]: # (        })

[//]: # (    } )

[//]: # (}%%)

[//]: # ()

[//]: # (flowchart TD)

[//]: # (    %% NODES)

[//]: # (    %% TIER 1)

[//]: # (    system&#40;")

[//]: # (        <font size=4.25><b>System</b></font>)

[//]: # (    "&#41;)

[//]: # (    style system fill:#555555,stroke:#555555,color:#ffffff)

[//]: # (    )

[//]: # (    %% TIER 2)

[//]: # (    agriculture&#40;")

[//]: # (        <font size=4.25><b>Agriculture</b></font>)

[//]: # (        ● Biofuel feedstocks)

[//]: # (    "&#41;)

[//]: # (    style agriculture text-align:left)

[//]: # (   )

[//]: # (    buildings&#40;")

[//]: # (        <font size=4.25><b>Buildings</b></font>)

[//]: # (        ● Residential)

[//]: # (        ● Commercial)

[//]: # (    "&#41;)

[//]: # (    click buildings "./buildings/index.html")

[//]: # (    style buildings text-align:left)

[//]: # (    )

[//]: # (    electric&#40;")

[//]: # (        <font size=4.25><b>Electricity</b></font>)

[//]: # (    "&#41;)

[//]: # (    click electric "./electric/index.html")

[//]: # (    style electric text-align:left)

[//]: # (    )

[//]: # (    fuels&#40;")

[//]: # (        <font size=4.25><b>Fuels</b></font>)

[//]: # (    "&#41;)

[//]: # (    click fuels "./fuels/index.html")

[//]: # (    style fuels text-align:left)

[//]: # (    )

[//]: # (    transportation&#40;")

[//]: # (        <font size=4.25><b>Transportation</b></font>)

[//]: # (        ● Light-duty vehicles)

[//]: # (        ● Medium- & heavy-duty vehicles)

[//]: # (        ● Aviation)

[//]: # (    "&#41;)

[//]: # (    click transportation "./transportation/index.html")

[//]: # (    style transportation text-align:left)

[//]: # (    )

[//]: # (    misc&#40;")

[//]: # (        <font size=4.25><b>Miscellaneous</b></font>)

[//]: # (        ● Industry)

[//]: # (        ● Other)

[//]: # (    "&#41;)

[//]: # (    style misc fill:#eeeeee,stroke:#eeeeee,color:#555555,text-align:left)

[//]: # ()

[//]: # (    %% EDGES)

[//]: # (    system o--o agriculture)

[//]: # (    system o--o buildings)

[//]: # (    system o--o electric)

[//]: # (    system o--o fuels)

[//]: # (    system o--o transportation)

[//]: # (    system o--o misc)

[//]: # (```)

## Assets

```{eval-rst}
.. autopydantic_model:: new_modeling_toolkit.system.asset.Asset
   :undoc-members:
```
---
````{dropdown} Formulation

```{eval-rst}
.. automethod:: new_modeling_toolkit.system.asset.Asset._operational_capacity

.. automethod:: new_modeling_toolkit.system.asset.Asset._physical_lifetime_constraint

.. automethod:: new_modeling_toolkit.system.asset.Asset._potential_constraint

.. automethod:: new_modeling_toolkit.system.asset.Asset._retired_capacity_max_constraint
```
````
````{dropdown} Tests

```{eval-rst}
.. autoclass:: tests.system.test_asset.TestAsset
   :members:
   :undoc-members:
   :no-index:
```
````


`Assets` are one of the foundational modeling components in `kit`, standardizing how we interact with resource costs,
sizes & build years.

```{mermaid}
:caption: Asset inheritance diagram <br>(click any of the blue boxes in the diagram to jump to the relevant documentation)
:align: center

%%{ 
    init: {
        "theme": "base",
        "themeVariables": {
            'primaryColor': '#E2ECF0',
            'primaryTextColor': '#034E6E',
            'primaryBorderColor': '#E2ECF0',
            'lineColor': '#BFBFBF',
            'secondaryColor': '#E2ECF0',
            'tertiaryColor': '#E2ECF0',
            'fontFamily': 'rubik'
        },
        'flowchart': { 
            'curve': 'bumpX' 
        }
    } 
}%%

flowchart LR
    %% NODES
    %% TIER 1
    asset("
        <font size=4.25><b>Asset</b></font>
        A physical asset with 
        a defined size, 
        cost & build year.
    ")
    style asset fill:#555555,stroke:#555555,color:#ffffff
    
    %% TIER 2
    generic("
        <font size=4.25><b>Generic</b></font>
        A generic generator.
    ")
    click generic "./electric/resources/index.html"
    tx_paths("
        <font size=4.25><b>TxPath</b></font>
        A path between 
        two electric zones.
    ")
    click tx_paths "./electric/resources/tx_paths.html"
    
    %% TIER 3
    thermal("
        <font size=4.25><b>Thermal</b></font>
        A fuel-burning generator.
    ")
    click thermal "./electric/resources/thermal.html"
    variable("
        <font size=4.25><b>Variable</b></font>
        Alias for <b>Generic</b>, generally 
        used for solar & wind resources.

    ")
    click variable "./electric/resources/variable.html"
    hydro("
        <font size=4.25><b>Hydro</b></font>
        Alias for <b>Generic</b>, typically
        utilizing energy budgets.
    ")
    click hydro "./electric/resources/hydro.html"
    unit_commitment("
        <font size=4.25><b>Unit Commitment</b> (UC)</font>
        A generator with commitment 
        variables and min up-/down-
        time tracking.
    ")
    click unit_commitment "./electric/resources/unit_commitment.html"
    storage("
        <font size=4.25><b>Energy Storage</b></font>
        An resource that draw power 
        from the grid, store energy 
        with losses & provide power.
    ")
    click storage "./electric/resources/storage.html"
    %% TIER 4
    thermal_uc("
        <font size=4.25><b>Thermal UC</b></font>
        A fuel-burning generator with 
        unit commitment constraints.
    ")
    click thermal_uc "./electric/resources/thermal.html"
    shed_dr("
        <font size=4.25><b>Shed Demand Response</b></font>
        A resource with a limited 
        number of calls per day, 
        month and/or year.
    ")
    click shed_dr "./electric/resources/shed_dr.html"
    %% TIER 5
    flex_loads("
        <font size=4.25><b>Flexible Loads</b></font>
        A resource that can shift 
        its demand for a limited 
        number of hours.
    ")
    click flex_loads "./electric/resources/flex_loads.html"

    %% EDGES
    asset o--o generic
    asset o--o tx_paths
    generic o--o hydro
    generic o--o variable
    generic o--o thermal
    generic o--o unit_commitment
    generic o--o storage
    thermal o--o thermal_uc
    unit_commitment o--o thermal_uc
    unit_commitment o--o shed_dr
    storage o--o flex_loads
    shed_dr o--o flex_loads
    
```

this is sort of hard to explain. basically it sort of exists, but only sparingly because the "starting point" for how
resolve was designed like 8 years ago was that "resources" represent aggregated things, rather than "real physical
generating units".

probably most succinctly, all operations are aggregated to the resource level (so no vintage indices), but builds are by
vintage (since you can select new capacity each year)

## Math Nomenclature

Throughout the documentation, we will try to use consistent nomenclature:

**["Blackboard bold"](https://en.wikipedia.org/wiki/Blackboard_bold) letters generally refer to sets:** 
:::{table} Sets
:widths: 25 75

| Symbol                           | Description                                                      |
|:---------------------------------|------------------------------------------------------------------|
| $\mathbb{A}$                     | Assets                                                           |
| $\mathbb{A}^{r}$                 | Resources                                                        |
| $\mathbb{A}^{tx}$                | Transmission paths                                               |
| $\mathbb{D}({s \in \mathbb{S}})$ | Demands (for each sector, e.g., electric sector load components) |
| $\mathbb{ELCC}$                  | ELCC surfaces                                                    |
| $\mathbb{F}$                     | Fuels                                                            |
| $\mathbb{P}$                     | Policies                                                         |
| $\mathbb{R}$                     | Electric sector operating reserves                               |
| $\mathbb{S}$                     | Sectors                                                          |
| $\mathbb{T}({w \in \mathbb{W}})$ | Timesteps (for each dispatch window)                             |
| $\mathbb{W}$                     | Dispatch windows                                                 |
| $\mathbb{Y}^{m}$                 | Modeled years                                                    |
| $\mathbb{Y}^{w}$                 | Weather years                                                    |
:::

**Upper case Latin letters & some Greek letters refer to input parameters:**
:::{table} Parameters
:widths: 25 25 50

| Symbol      | Examples                                | Description                                                                                      |
|:------------|:----------------------------------------|--------------------------------------------------------------------------------------------------|
| $C$         | $C^{f}, C^{v}$                          | Costs                                                                                            |
| $\eta$      | $\eta^{in}, \eta^{out}, \eta^{idle} $   | Efficiency losses (charging, discharging, idle/parasitic)                                        |
| $\lambda$   |                                         | Price (e.g., GHG price)                                                                          |
| $\hat{D}$   |                                         | Demand derate (%) in timestep (e.g., for outages, seasonal derates)                              |
| $\check{D}$ |                                         | Demand minimum rating (%) in timestep                                                            |
| $\hat{P}$   |                                         | Production derate (%) in timestep (e.g., for outages, seasonal derates, generation profiles)     |
| $\check{P}$ |                                         | Production minimum rating (%) in timestep                                                        |
| $\bar{P}$   | $\bar{P}_{d}, \bar{P}_{m}, \bar{P}_{y}$ | Average daily, monthly or annual production (i,.e., normalized energy budget)                    |
| $Y^{build}$ |                                         | Build year of asset                                                                              |
| $I$         | $I^{build}, I^{retire}$                 | Boolean indicators whether model can choose to build or retire resource (v.s., input trajectory) |
| $L$         | $\hat{L}^{p},\hat{L}^{f}, {L}_{y}$      | Physical & financial lifetimes of asset, and current age of asset (in years)                     |


:::

**Lower case Latin letters & some Greek letters refer to decision variables & expressions:**
:::{table} Decision Variables & Expressions
:widths: 25 25 50

| Symbol            | Examples           | Description                                                     |
|:------------------|:-------------------|-----------------------------------------------------------------|
| $\lambda$         |                    | Constraint dual (shadow price)                                  |
| $\xi$             | $\xi^{+}, \xi^{-}$ | Slack variables                                                 |
| $d$               | $d^{fuel}, d^{e}$  | Demand (e.g., fuel demand in timestep, storage charging demand) |
| $p$               |                    | Production (e.g., storage discharging/power production)         |
| $\hat{\hat{p}}$   |                    | Operational nameplate (power) capacity                          |
| $r$               | $r^{spin}$         | Operating reserves provided                                     |
| $\hat{\hat{soc}}$ |                    | Nameplate storage capacity                                      |
| $soc$             |                    | Storage state-of-charge                                         |
:::

```{attention}
If you notice issues with the written formulation, please leave a comment on the page so that we can fix it!
```