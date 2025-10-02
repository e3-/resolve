# Formulation

```{note}
Under construction
```

Capacity expansion models are long-term investment planning models that traditionally have their roots in the regulatory
planning framework to develop least-cost resource plans in electric sector. As electric sector planning has evolved,
capactiy expansion modeling has also grown in complexity, with planners balancing multiple different dimensions of
increasing detail in an attempt to make better decisions.

:::{table} **A non-exhaustive list of tradeoffs in capacity expansion modeling**
:widths: 20 40 40 40

| Dimension                       | Easy                              | Medium                                        | Hard                                                                              |
|---------------------------------|-----------------------------------|-----------------------------------------------|-----------------------------------------------------------------------------------|
| Investment candidates           | Limited candidates                |                                               | Multiple tranches for each technology; commercial & emerging technologies         |
| Dispatch                        | Load blocks & load duration curve | Time slices (non-chronological)               | Chronologial dispatch over many weather years (may involve timeseries clustering) |
| Transmission & geographic scope | Copperplate (one zone)            | Zonal (pipe-and-bubble, transportation model) | Nodal (optimal power flow model)                                                  |
| Reliability & resilience        | Static PRM                        |                                               | ELCC and/or stochastic operations                                                 |
| Cross-sectoral linkages         |                                   |                                               | Electrolytic fuels                                                                |
| Uncertainty                     | Deterministic                     |                                               | Stochastic (probabilistic futures) & risk-averse (e.g., least-regrets)            |

:::

`````{figure}
:align: center
````{card-carousel} 2
:
```{card} Load Duration Curve
```

```{card} Load Blocks
```

```{card} Sampled Chronological Operations
```

```{card} Sampled Chronological Operations
```
````

Evolution of capacity expansion modeling.
`````

To model this investment problem, we must account for the time value of money via discounting. As shown in
[the figure below](#discount-rate), the assumed discount rate can have a big relative impact on how "important"
near-term decisions are in the model compared to long-term decisions.

```{figure} ../../_images/discount_rate.svg
:width: 75%
:align: center
:name: discount-rate
Visualizing the impact of compounding discount rates (3%, 5%, and 8%) over a 20-year modeling horizon. 
Depending on assumed discount rate, a decision made in year 20 will have 55%, 38%, and 21% (respectively) of the impact 
on the objective function as a decision made in year 0.
```

[^1]: For assets that contribute to a Planning Reserve Margin, +1 build variable for qualifying capacity.

```{eval-rst}
+------------------+-----------------------+----------------------------+----------------------------------+---------------------------------+
| Component        | Sub-Type              | # of Build Variables [1]_  | | **# of Dispatch Variables**    | | **# of Dispatch Constraints** |
|                  |                       |                            | | (per timestep)                 | | (per timestep)                |
+==================+=======================+============================+==================================+=================================+
| Asset            |                       | 1                          | n/a                              | n/a                             |
+------------------+-----------------------+----------------------------+----------------------------------+---------------------------------+
| TxPath           |                       | 1                          | | \+ 3                           | | \+ Simultaneous flow          |
+------------------+-----------------------+----------------------------+----------------------------------+---------------------------------+
| ElectricResource | Generic               | 1                          | | \+ 1                           |                                 |
|                  |                       |                            | | \+ 1/reserve                   |                                 |
+------------------+-----------------------+----------------------------+----------------------------------+---------------------------------+
|                  | Variable              | 1                          | | \+ 1                           |                                 |
|                  |                       |                            | | \+ 1/reserve                   |                                 |
+------------------+-----------------------+----------------------------+----------------------------------+---------------------------------+
|                  | Thermal               | 1                          | | \+ 1                           |                                 |
|                  |                       |                            | | \+ 1/fuel                      |                                 |
|                  |                       |                            | | \+ 1/reserve                   |                                 |
+------------------+-----------------------+----------------------------+----------------------------------+---------------------------------+
|                  | ThermalUnitCommitment | 1                          | | \+ 4                           |                                 |
|                  |                       |                            | | \+ 1/fuel                      |                                 |
|                  |                       |                            | | \+ 1/reserve                   |                                 |
+------------------+-----------------------+----------------------------+----------------------------------+---------------------------------+
|                  | Hydro                 | 2                          | | \+ 2                           |                                 |
|                  |                       |                            | | \+ 1/reserve                   |                                 |
+------------------+-----------------------+----------------------------+----------------------------------+---------------------------------+
|                  | Storage               | 3                          | | \+ 3                           |                                 |
|                  |                       |                            | | \+ 1/reserve                   |                                 |
+------------------+-----------------------+----------------------------+----------------------------------+---------------------------------+
|                  | ShedDr                | 1                          | | \+ 1                           |                                 |
|                  |                       |                            | | \+ 1/reserve                   |                                 |
+------------------+-----------------------+----------------------------+----------------------------------+---------------------------------+
|                  | FlexLoad              | 3                          | | \+ #                           |                                 |
|                  |                       |                            | | \+ 1/reserve                   |                                 |
+------------------+-----------------------+----------------------------+----------------------------------+---------------------------------+
```

## Comparison with Other Capacity Expansion Tools

```{eval-rst}
+---------------------------+---------------------------------+---------------------------------------------------+----------------------------------------------------------+----------------------------------------------------+----------------------------+---------------------------------+--------+
|                           | Resolve                         | Open-Source                                                                                                                                                       | Proprietary & Commercial                                              |
+===========================+=================================+===================================================+==========================================================+====================================================+============================+=================================+========+
|                           |                                 | `GenX <https://genxproject.github.io/GenX/dev/>`_ | `GridPath <https://gridpath.readthedocs.io/en/latest/>`_ | `PyPSA <https://pypsa.readthedocs.io/en/latest/>`_ | Encompass                  | Plexos LT                       | SERVM* |
+---------------------------+---------------------------------+---------------------------------------------------+----------------------------------------------------------+----------------------------------------------------+----------------------------+---------------------------------+--------+
| Operational resolution    | Hourly (typically sampled)      | Hourly (typically sampled)                        | Hourly (typically sampled)                               | Hourly (typically sampled)                         | Hourly (typically sampled) | Hourly (typically sampled)      | ?      |
+---------------------------+---------------------------------+---------------------------------------------------+----------------------------------------------------------+----------------------------------------------------+----------------------------+---------------------------------+--------+
| Inter-day energy tracking | Storage, flexible loads         |                                                   |                                                          |                                                    |                            |                                 | ?      |
+---------------------------+---------------------------------+---------------------------------------------------+----------------------------------------------------------+----------------------------------------------------+----------------------------+---------------------------------+--------+
| Planning horizon          | Multi-period, perfect foresight | Multi-period, perfect foresight                   |                                                          |                                                    |                            | Multi-period, perfect foresight | ?      |
|                           |                                 | Multi-period, myopic                              |                                                          |                                                    |                            |                                 |        |
+---------------------------+---------------------------------+---------------------------------------------------+----------------------------------------------------------+----------------------------------------------------+----------------------------+---------------------------------+--------+
| Transmission              | Zonal                           | Zonal (with losses)                               | | Zonal                                                  | | Zonal                                            | | Zonal                    | | Zonal                         | ?      |
|                           |                                 |                                                   | | Nodal (DCOPF)                                          | | Nodal                                            | | Nodal                    | | Nodal                         |        |
+---------------------------+---------------------------------+---------------------------------------------------+----------------------------------------------------------+----------------------------------------------------+----------------------------+---------------------------------+--------+
| Endogenous retirement     |                                 |                                                   |                                                          |                                                    |                            |                                 | ?      |
+---------------------------+---------------------------------+---------------------------------------------------+----------------------------------------------------------+----------------------------------------------------+----------------------------+---------------------------------+--------+
| Unit commitment           | Yes                             | Yes                                               | Yes                                                      | Yes                                                | Yes                        | Yes                             | ?      |
+---------------------------+---------------------------------+---------------------------------------------------+----------------------------------------------------------+----------------------------------------------------+----------------------------+---------------------------------+--------+

```
