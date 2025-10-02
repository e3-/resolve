---
tocdepth: 4
---

# Energy Storage

:::::{dropdown} Data Fields & Method Definitions
:icon: codescan

::::{dropdown} New
```{eval-rst}
.. autopydantic_model:: new_modeling_toolkit.system.electric.resources.storage.StorageResource
   :no-index:
   :no-inherited-members:
```
::::

::::{dropdown} Inherited
```{eval-rst}
.. autopydantic_model:: new_modeling_toolkit.system.electric.resources.generic.GenericResource
   :no-index:
   :inherited-members: new_modeling_toolkit.system.asset.Asset
```
::::

:::::

The StorageResources and HybridStorageResource class represent resources that both provide power and take power and
energy capacity. These resources are typically described as "energy-limited resources" or ELRs.

The keystone feature in rebuilding `resolve` in `kit` in 2021 was to migrate to a more flexible formulation for storage
energy tracking based on [^kotzur].

[^kotzur]: Kotzur, et al., "Time series aggregation for energy system design: Modeling seasonal storage", Applied
Energy, Volume 213, 2018, Pages 123-135, ISSN
0306-2619, [https://doi.org/10.1016/j.apenergy.2018.01.023/](https://doi.org/10.1016/j.apenergy.2018.01.023/).
(PDF also
available [on SharePoint](https://ethreesf.sharepoint.com/:b:/s/CECLong-DurationStorageStudy/EacPRyNYsrNMsVyjofK0XDwBaGL9APtBnctld_vl9vMqwQ?e=Z5tBc7)).

## Recap

### What are considered Energy-limited Resources?

![](../../../_images/infographic_ELRs.png)
Batteries are the most obvious technology that fits into this category, but as more ELRs emerge, this class can flexibly
take on resources of different durations, round-trip efficiencies (RTE) and performance characteristics

### Where do the data inputs go?

1. Resource Attributes will be specified **in the UI**
2. Custom attributes below can be specified as a timeseries, placed in `data > profiles`
    - Pmin Rating
    - Pmax Rating
    - Max Charging Rating (CSV file)
    - Daily Energy Budget
    - Annual Energy Budget

> ##### Important considerations when modeling storage:
>1. Symmetric or Asymmetric round-trip efficiency (RTE)
>2. Total energy capacity / duration relative to RTE
    >

3. is the 4-hr duration inclusive of RTE losses?

> 4. Forced outage rate assumption
     >

5. During the Summer of Sept 2022 when CAISO avoided a near black-out, the 2GW storage fleet experienced unplanned
   outages of ~10% of the total nameplate

In Recap, `StorageResource` are considered energy-limited resources, a special class of resources in Recap that has two
types of dispatch: Heuristic or Optimized dispatch.

![](../../../_images/infographic_heuristic.png)

![](../../../_images/inforgraphic_optimization.png)


