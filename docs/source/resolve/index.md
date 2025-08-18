# 🔨 Resolve

```{toctree}
:hidden:

reference/index
how_to/index
```

```{note}
Under construction
```

The `ResolveCase` is composed of several components, shown in the below diagram.

```{graphviz}
   :caption: Relationship between `ResolveCase` and `System`

    digraph G {
        splines=polyline;

        // Make all shapes default to "box" instead of "oval"
        node [shape="box"];

        // Nodes --------------------------------------------------------------------------------------------------
        subgraph cluster_resolvecase {
            style=filled;
            color="#E2ECF0";
            node [style=filled,color=white];
            "Custom Constraints"
            "Reporting Settings"
            "Temporal Settings"
            a [label=<<FONT FACE="monospace">Resolve</FONT> Model>]
            "System"
            label = "Resolve Case"
        }
    }
```

- **System:** A `System` instance (itself composed of components & linkages).
  See [System documentation page](../system/index.md) for more details
- **`Resolve` Model:** The Pyomo optimization model, containing all the decision variables, expressions, constraints &
  objective function to be solved.
- **Temporal Settings:** The temporal settings for the given Resolve case. In other words, which future model years to
  be optimizing, discount factors to apply to calculate an NPV over the modeling horizon, and treatment of timeseries
  (e.g., using the built-in k-medoids clustering or a custom/manual sample of representative periods).
- **Custom Constraints:** User-defined custom constraints. The Resolve case allows users to constrain any decision
  variable or expression via CSV.

## Understanding `kit` Structure

For users familiar with the previous Resolve data structure, `kit` structure will take some adjustment. This section
will provide a brief overview on where to find various model files. For more information,
see [the Resolve section](../resolve/index.md)

### System, Component & Linkage Data

The primary location for data is in the `./data/interim` folder. This is where all the data related to resources, loads,
policies, etc. are stored.

See [the System documentation](../system/index.md) for more information on the design of components, linkages, and
systems.

### Resolve Case Settings

Inputs related to Resolve settings are stored in `./data/settings/resolve/[resolve-settings-name]`. These include:

1. `attributes.csv`, which currently only lists which `system` (and related components & linkages) to load
2. Reporting settings (e.g., which Pyomo model components to export to CSV)
3. Temporal settings (e.g., settings to control whether timeseries are clustered using k-medoids or a manual mapping)
4. User-defined custom constraints

### Resolve Case Outputs

Stored in `./reports/resolve/[resolve-settings-name]`. Reported outputs are controlled by the Resolve case's reporting
settings (see above).

At this time, the main outputs of `kit` are directly exported `Var`, `Expression`, `Constraint`, and `Dual` data from
the Resolve Pyomo model.

```{note}
These reported components have not been post-processed in any way but may need to be to be interpreted. 

For example, constraint dual values are reported directly out of the model. For hourly constraints, these duals will 
reflect the impact of (1) the discount factor weighting applied to each modeled year and (2) the weight applied to each 
representative period ("day") if timeseries clustering is used.  
```

```{note}
If you do not see an model output that you are expecting, refer back to the **reporting settings** in `./data/settings`  
to see if that model component is set to `True`.
```

## Case Studies

::::{card-carousel} 1

:::{card} **CEC Climate Resilience** {bdg-warning-line}`soon`

- a
  :::
  :::{card} **CEC Hydrogen** {bdg-warning-line}`soon`
- a
  :::
  :::{card} **CEC Long-Duration Storage** (LDES)
- a
  :::
  :::{card} **CPUC Integrated Resource Plan** (IRP)
- a
  :::
  :::{card} **HECO Integrated Grid Plan** (IGP)
- a
  :::
  :::{card} **NYSERDA Climate Leadership and Community Protection Act** (CLCPA)
- a
  :::
  ::::

## In-Development Features

::::{card-carousel} 1
:::{card} **Formulation Refactor**
(refactor)=
**Goals:**

1. {bdg-warning-line}`in progress` Improve handling of vintages, tranches, unit & unit aggregation
2. {bdg-warning-line}`in progress` Develop more complete suite of Resolve unit & integration tests
3. {bdg-warning-line}`in progress` Improve readability, consistency & modularity of the optimization formulation
4. {bdg-secondary-line}`soon` Enforce stricter input data validation (e.g., different resource types)
5. {bdg-secondary-line}`soon` Integrate updated timeseries clustering implementation
6. {bdg-secondary-line}`soon` Facilitate interaction & connection between Resolve and Pathways for cross-sectoral fuels
   optimization & electrolytic fuels production
   :::
   :::{card} **Component Aggregation**
   (aggregation)=

- a
  :::
  :::{card} **Results Standardization**
  (results-reporting)=
- a
  :::
  :::{card} **Production Simulation Mode**
  (production-simulation)=
- a
  :::
  :::{card} **Climate Impacts**
  (climate-impacts)=
- a
  :::
  :::{card} **Risk-Averse Planning**
  (risk-averse)=
- a
  :::
  :::{card} **Bid Evaluation**
  (bid-evaluation)=
- a
  :::
  :::{card} **`Resolve`-lite**
  (resolve-lite)=
  :::
  ::::
