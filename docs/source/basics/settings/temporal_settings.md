# Temporal Settings

## Modeled Years

Because `Resolve` is typically run in a "proactive" capacity expansion mode 
(i.e., we optimize builds in all modeled future years simultaneously rather than sequentially), 
it's usually necessary to choose a subset of future years to model. In the example below, we model 
every 5 years. 

```{figure} ../_images/discount_factors.png
Modeled years and discount factors
```

### Real or Nominal Dollars?

The convention in `Resolve` is to model costs in **real dollars**, so the discount rate used is also a real discount rate. 
If users want to model costs as **nominal dollars**, you will need to ensure that the annual discount rate is a nominal rate. 


## Operational Periods

Historically, `Resolve` was designed to model sampled operational days. This latest version of `Resolve` 
generalizes this feature to allow operational periods to be any arbitrary length (e.g., day, week). 

### Timeseries Clustering

`Resolve` leverages [`kmedoids`](https://python-kmedoids.readthedocs.io/en/latest/index.html) Python package for its 
timeseries clustering. The FasterPAM algorithm enables relatively fast (seconds-to-minutes) clustering for relatively 
large datasets (e.g., 25 x 23 years of hourly data). 

Clustering allows us to preserve information about the *chronology* of sampled periods so that we can reconstruct an 
estimate of the original full-fidelity (i.e., 8760 hour/year) timeseries, as shown in the example below.

#### Example Comparison of Clustered Timeseres to Original
```{raw} html
  :file: ../_images/clustering_results.html
```

#### Mapping of Clustered Days to Original Days

```{raw} html
  :file: ../_images/rep-periods.html
```