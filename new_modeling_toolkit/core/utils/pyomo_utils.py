from typing import Union

import pandas as pd
import pyomo.environ as pyo
from loguru import logger
from pyomo import environ as pyo


def mark_pyomo_component(func):
    """Simple timer decorator"""
    logger.info(f"Constructing {func.__name__!r}")
    return func


def get_index_labels(model_component: Union[pyo.Param, pyo.Var, pyo.Expression, pyo.Constraint]) -> list[str]:
    """Get the names of the indices, given a Pyomo model component instance."""
    if model_component.is_indexed():
        # If component has multiple indices, we need to do some additional unpacking using _implicit_subsets
        if model_component._implicit_subsets is not None:
            names = [s.name for s in model_component._implicit_subsets]
        else:
            names = [model_component.index_set().name]

        # Several sets are multi-dimensional, which require yet another (last) unpacking
        if "TIMEPOINTS" in names:  # TIMEPOINTS are a tuple of MODEL_YEARS, REP_PERIODS, and HOURS
            tuple_pos = names.index("TIMEPOINTS")
            names[tuple_pos : tuple_pos + 1] = ("MODEL_YEARS", "REP_PERIODS", "HOURS")

        if "MODEL_YEARS_AND_ADJACENT_REP_PERIODS" in names:
            tuple_pos = names.index("MODEL_YEARS_AND_ADJACENT_REP_PERIODS")
            names[tuple_pos : tuple_pos + 1] = ("MODEL_YEARS", "PREV_REP_PERIODS", "NEXT_REP_PERIODS")

        if "MODEL_YEARS_AND_CHRONO_PERIODS" in names:
            tuple_pos = names.index("MODEL_YEARS_AND_CHRONO_PERIODS")
            names[tuple_pos : tuple_pos + 1] = ("MODEL_YEARS", "CHRONO_PERIODS")

        if "DISPATCH_WINDOWS_AND_TIMESTAMPS" in names:
            tuple_pos = names.index("DISPATCH_WINDOWS_AND_TIMESTAMPS")
            names[tuple_pos : tuple_pos + 1] = ("DISPATCH_WINDOWS", "TIMESTAMPS")

        if "RESOURCE_CANDIDATE_FUELS_FOR_EMISSIONS_POLICY" in names:
            tuple_pos = names.index("RESOURCE_CANDIDATE_FUELS_FOR_EMISSIONS_POLICY")
            names[tuple_pos : tuple_pos + 1] = ("EMISSIONS_POLICIES", "RESOURCES", "CANDIDATE_FUELS")

        if "SIMULTANEOUS_FLOW_GROUPS_MAP" in names:
            tuple_pos = names.index("SIMULTANEOUS_FLOW_GROUPS_MAP")
            names[tuple_pos : tuple_pos + 1] = ("SIMULTANEOUS_FLOW_GROUPS", "TRANSMISSION_LINES")

        if "PLANTS_THAT_INCREMENT_RESERVES" in names:
            tuple_pos = names.index("PLANTS_THAT_INCREMENT_RESERVES")
            names[tuple_pos : tuple_pos + 1] = ("PLANTS", "RESERVES")
    else:
        names = [None]

    return names


def convert_pyomo_object_to_dataframe(
    model_component: Union[pyo.Param, pyo.Var, pyo.Expression, pyo.Constraint],
    exception: bool = True,
    dual_only: bool = False,
) -> pd.DataFrame:
    """Converts an object from a pyomo model (Param, Var, Expression, or Constraint) into a pandas DataFrame.

    If `model_component` is a Constraint, the lower bound, body, upper bound, and dual value will all be returned. Set
    `dual_only=True` to return only the dual value for the constraint.

    Args:
        model_component: the component to convert to a DataFrame
        exception: Passthrough to `pyomo.Value()`. If True, raise an exception for uninitialized components. If False,
            return None for unintialized values.
        dual_only: for a Constraint, whether to return only the dual values

    Returns:
        df: the pyomo object in DataFrame format
    """
    if isinstance(model_component, (pyo.Param, pyo.Var, pyo.Expression)):
        # Get model component results as a dict using extract_values() method
        obj_results = {
            idx: pyo.value(v, exception=exception) if not isinstance(v, tuple) else str(v)
            for idx, v in model_component.extract_values().items()
        }
        # TODO (2022-02-22): We could make the `get_index_labels` function do get both names and the entire index object.
        if model_component.is_indexed():
            names = get_index_labels(model_component)
            if model_component._implicit_subsets is not None or model_component.index_set().name in [
                "TIMEPOINTS",
                "ADJACENT_REP_PERIODS",
                "DISPATCH_WINDOWS_AND_TIMESTAMPS",
                "RESOURCE_CANDIDATE_FUELS_FOR_EMISSIONS_POLICY",
                "SIMULTANEOUS_FLOW_GROUPS_MAP",
            ]:
                if len(obj_results.keys()) == 0:
                    index = pd.MultiIndex.from_tuples([(None,) * len(names)], names=names)
                else:
                    index = pd.MultiIndex.from_tuples(obj_results.keys(), names=names)
            else:
                index = pd.Index(obj_results.keys(), name=names[0])
        else:
            # Scalar values get an empty index with no name
            index = pd.Index([None], name="[None]")
        # Create dataframe from dict
        df = pd.DataFrame(obj_results.values(), index=index, columns=[model_component.name])
    elif isinstance(model_component, pyo.Constraint):
        if dual_only:
            df = pd.DataFrame.from_dict(
                {idx: {"Dual": model_component[idx].get_suffix_value("dual")} for idx in model_component},
                orient="index",
            )
        else:
            constraints_to_print_expr = [
                "Rep_Period_Energy_Budget_Constraint",
            ]
            df = pd.DataFrame.from_dict(
                {
                    idx: {
                        "Lower Bound": pyo.value(model_component[idx].lower),
                        "Body": pyo.value(model_component[idx].body),
                        "Upper Bound": pyo.value(model_component[idx].upper),
                        "Dual": model_component[idx].get_suffix_value("dual"),
                        "Expression": model_component[idx].expr
                        if model_component.name in constraints_to_print_expr
                        else None,
                    }
                    for idx in model_component
                },
                orient="index",
            )
        # TODO (2022-02-22): The way the index is created and named for constraints vs. other model components seems
        #  like could be made to be the same (related to previous TODO)
        index_names = get_index_labels(model_component)
        # If DataFrame is empty, need an extra step to be able to label the index headers
        if df.empty:
            df.index = pd.MultiIndex.from_arrays([[]] * len(index_names))
        df.index.names = index_names
    elif isinstance(model_component, pyo.Set):
        if model_component.name.endswith("_index") or model_component.name.endswith("_domain"):
            return None
        data = model_component.data()
        if isinstance(data, tuple):
            df = pd.DataFrame(data)
        elif isinstance(data, dict) and not all(list(data.values())[0] == length for length in data.values()):
            # If dict is ragged (i.e., values are not the same length), dataframe has to be oriented the other way
            df = pd.DataFrame.from_dict(data, orient="index")
        else:
            df = pd.DataFrame.from_dict(data)
        if len(df) > 0:
            # If data is tuples, pandas doesn't automatically split into columns
            if isinstance(df.iloc[0, 0], tuple):
                df = pd.DataFrame(df.squeeze(axis=1).tolist())
            # Add column names to split tuple dataframe
            if (domain := getattr(model_component, "domain", None)) is not None:
                if domain.name == "Any":
                    df.columns = [model_component.name] * len(df.columns)
                else:
                    df.columns = [model_component.domain.name] * int(
                        len(df.columns) / len([model_component.domain.name])
                    )
    else:
        raise TypeError("This function only takes Pyomo Var, Param, Constraint, Expression, and Set objects.")

    return df
