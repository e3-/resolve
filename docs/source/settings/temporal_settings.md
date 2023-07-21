# Temporal Settings

## Timeseries Clustering

`Resolve` leverages [`kmedoids`](https://python-kmedoids.readthedocs.io/en/latest/index.html) Python package for its 
timeseries clustering. The FasterPAM algorithm enables relatively fast (seconds-to-minutes) clustering for relatively 
large datasets (e.g., 25 x 23 years of hourly data). 

Clustering allows us to preserve information about the *chronology* of sampled periods so that we can reconstruct an 
estimate of the original full-fidelity (i.e., 8760 hour/year) timeseries. 

## Operational Representation