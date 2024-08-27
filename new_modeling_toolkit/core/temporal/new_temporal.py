import enum
from typing import Any

import pandas as pd

from new_modeling_toolkit.core import component


@enum.unique
class DispatchWindowEdgeEffects(enum.Enum):
    LOOPBACK = "loopback"
    CHRONOPERIOD = "chronoperiod"
    FIXED_INITIAL_SOC = "fixed_initial_soc"


class NewTemporalSettings(component.Component):
    dispatch_window_edge_effects: DispatchWindowEdgeEffects

    # Eventually use pandera to enforce schema
    # | Timestamp | Window Label | Include | Weight
    # Recall that DataFrame.loc is slow, so switching to a dict https://github.com/tum-ens/rivus/issues/26
    dispatch_windows_df: pd.DataFrame

    # Hackily adding attributes from other temporal settings that I'm just going to copy from the "old" TemporalSettings
    chrono_periods: Any = None
    map_to_rep_periods: Any = None
    modeled_years: list[Any] = [None]
