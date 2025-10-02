# Timeseries

```{toctree}
:hidden:

data_sources
clustering
nn
```

A key thing to be thinking about for energy system modeling is the difference between "expected" energy demands and how
they may vary with weather, and **"weather years"** are an important "dimension" of timeseries to keep in mind
throughout ``kit``. For example:

- How much variance around expected annual energy demand do we expect, and how should load shapes vary?
- How much should 1-in-X peaks vary compared to median (i.e., 1-in-2) peak demands?
- How much variance around the expected capacity factor (CF) of a wind or solar resource is reasonable?

:::{figure} ../../_images/weather-data.png
:align: center
:width: 75%

Example showing the breadth of weather timeseries data we need for energy system modeling.
:::

In `kit`, all timeseries data should be labeled using a timestamp (e.g., 2021-01-01 10:00:00).

```{note}
Timeseries data is interpreted using [](inv:#pandas.Timestamp), so any datetime format that can be inferred by `pandas` 
will also automatically get interpreted in `kit`. 
``` 

```{caution}
At this time, `kit` does not have any specific logic to handle time zones in timestamps; 
however, we expect a future release to provide better handling for time zone-aware data.

```

## Interpolation & Extrapolation

As previously discussed, one of the key goals for ``kit`` is to provide a standard framework for modeling energy
demands. Right now, all timeseries data in `kit` is encoded as being hourly or annual. For different modeling purposes,
the timeseries data needs to be aligned and potentially sampled to make it more computationally tractable.

:::{figure} ../../_images/load-shaping-flow.png
:align: center
:width: 75%

A general overview of timeseries handling
:::
