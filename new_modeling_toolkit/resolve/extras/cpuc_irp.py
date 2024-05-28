"""CPUC IRP-specific functionality.
  - Forward & reverse simultaneous transmission flow constraints
  - Hydro dispatch constraints (Pmin, Pmax, daily energy budgets) for 37 representative days
"""
import pandas as pd
import pyomo.environ as pyo
from loguru import logger

from new_modeling_toolkit.core.utils.pyomo_utils import mark_pyomo_component
from new_modeling_toolkit.resolve.model_formulation import ResolveCase


def main(resolve: ResolveCase) -> ResolveCase:
    """Main function, which will be called by `run_opt.py`.

    Args:
     resolve:

    Returns:
     resolve: Updated resolve instance (e.g., with additional/modified constraints).
    """

    if (resolve.dir_structure.resolve_settings_dir / "extras" / "simultaneous_flow_groups.csv").exists():
        logger.info("Adding simultaneous flow constraints")

        ### Simultaneous Flows ###

        simultaneous_flow_groups = pd.read_csv(
            resolve.dir_structure.resolve_settings_dir / "extras" / "simultaneous_flow_groups.csv", index_col=[0, 1]
        )

        resolve.model.SIMULTANEOUS_FLOW_GROUPS_MAP = pyo.Set(
            initialize=sorted(simultaneous_flow_groups.index.unique().values)
        )
        resolve.model.SIMULTANEOUS_FLOW_GROUPS = pyo.Set(
            initialize=sorted(set(tup[0] for tup in simultaneous_flow_groups.index.values))
        )
        resolve.model.TX_PATHS_BY_SIMULTANEOUS_FLOW_GROUP = pyo.Set(
            resolve.model.SIMULTANEOUS_FLOW_GROUPS,
            within=resolve.model.TRANSMISSION_LINES,
            initialize=(
                lambda m, sim_flow: sorted(
                    set(tup[1] for tup in simultaneous_flow_groups.index.values if tup[0] == sim_flow)
                )
            ),
        )

        resolve.model.simultaneous_flow_direction = pyo.Param(
            resolve.model.SIMULTANEOUS_FLOW_GROUPS_MAP,
            within=["forward", "reverse"],
            initialize=lambda m, sim_flow, tx_path: simultaneous_flow_groups.loc[sim_flow, tx_path].values[0],
        )

        simultaneous_flow_limits = pd.read_csv(
            resolve.dir_structure.resolve_settings_dir / "extras" / "simultaneous_flow_limits.csv", index_col=[0, 1]
        )
        simultaneous_flow_limits.columns = simultaneous_flow_limits.columns.astype(int)

        resolve.model.simultaneous_flow_limit = pyo.Param(
            resolve.model.SIMULTANEOUS_FLOW_GROUPS,
            resolve.model.MODEL_YEARS,
            initialize=lambda m, sim_flow, model_year: simultaneous_flow_limits.loc[sim_flow, model_year].values[0],
        )

        @mark_pyomo_component
        @resolve.model.Constraint(resolve.model.SIMULTANEOUS_FLOW_GROUPS, resolve.model.TIMEPOINTS)
        def Simultaneous_Flow_Constraint(model, sim_flow, model_year, rep_period, hour):
            """Constrain the sum of gross forward or reverse flows on groups of transmission paths"""
            return (
                sum(
                    model.Transmit_Power_MW[tx_path, model_year, rep_period, hour]
                    if resolve.model.simultaneous_flow_direction[sim_flow, tx_path] == "forward"
                    else -1 * model.Transmit_Power_MW[tx_path, model_year, rep_period, hour]
                    for tx_path in model.TX_PATHS_BY_SIMULTANEOUS_FLOW_GROUP[sim_flow]
                )
                <= model.simultaneous_flow_limit[sim_flow, model_year]
            )

    return resolve
