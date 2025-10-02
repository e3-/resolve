from typing import Union

import numpy as np
import pandas as pd
import pyomo.environ as pyo
from loguru import logger
from pyomo import environ as pyo


def mark_pyomo_component(func):
    """Simple timer decorator"""
    logger.info(f"Constructing {func.__name__!r}")
    return func


def get_index_labels(model_component: Union[pyo.Param, pyo.Var, pyo.Expression, pyo.Constraint]) -> list[str]:
    """
    Get the names of the indices, given a Pyomo model component instance.
    Unpack the tuple listed in "doc" input of Set definition
    """
    if model_component.is_indexed():
        # If component has multiple indices, we need to do some additional unpacking using _implicit_subsets
        if model_component._implicit_subsets is not None:
            names = [
                elem
                for s in model_component._implicit_subsets
                for elem in (tuple(s.doc) if s.doc is not None else [s.name])
            ]
            # Several sets are multi-dimensional, which require yet another (last) unpacking
            if "CHRONO_PERIODS_AND_TIMESTAMPS" in names:
                tuple_pos = names.index("CHRONO_PERIODS_AND_TIMESTAMPS")
                names[tuple_pos : tuple_pos + 1] = ("CHRONO_PERIODS", "TIMESTAMPS")
            elif [name for name in names if name.endswith(".connect_process_outputs_index_0")]:
                tuple_pos = names.index(
                    [name for name in names if name.endswith(".connect_process_outputs_index_0")][0]
                )
                names[tuple_pos : tuple_pos + 1] = ("PROCESS_INPUT", "PROCESS_OUTPUT")
            elif "WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS" in names:
                tuple_pos = names.index("WEATHER_PERIODS_AND_WEATHER_TIMESTAMPS")
                names[tuple_pos : tuple_pos + 1] = ("WEATHER_PERIODS", "WEATHER_TIMESTAMPS")

        else:
            names = [model_component.index_set().name]
    else:
        names = [None]

    return names


def convert_pyomo_object_to_dataframe(
    model_component: Union[pyo.Param, pyo.Var, pyo.Expression, pyo.Constraint],
    exception: bool = True,
    dual_only: bool = False,
    use_doc_as_column_name: bool = False,
) -> pd.DataFrame:
    """Converts an object from a pyomo model (Param, Var, Expression, or Constraint) into a pandas DataFrame.

    If `model_component` is a Constraint, the lower bound, body, upper bound, and dual value will all be returned. Set
    `dual_only=True` to return only the dual value for the constraint.

    Args:
        model_component: the component to convert to a DataFrame
        exception: Passthrough to `pyomo.Value()`. If True, raise an exception for uninitialized components. If False,
            return None for unintialized values.
        dual_only: for a Constraint, whether to return only the dual values
        use_doc_as_column_name: True if the column name should be what is defined in optional `doc` attribute, otherwise the column name will be returned as the name of the component

    Returns:
        df: the pyomo object in DataFrame format
    """
    column_name = [
        model_component.name if model_component.doc is None and not use_doc_as_column_name else model_component.doc
    ]
    if isinstance(model_component, (pyo.Param, pyo.Var, pyo.Expression)):
        # Get model component results as a dict using extract_values() method
        obj_results = {
            idx: pyo.value(v, exception=exception) if not isinstance(v, tuple) else str(v)
            for idx, v in model_component.extract_values().items()
        }
        if model_component.is_indexed():
            names = get_index_labels(model_component)
            if len(names) > 1:
                index = pd.MultiIndex.from_tuples(obj_results.keys(), names=names)
            else:
                index = pd.Index(obj_results.keys(), name=names[0])
        else:
            # Scalar values get an empty index with no name
            index = pd.Index([None], name="[None]")
        # Create dataframe from dict
        df = pd.DataFrame(
            obj_results.values(),
            index=index,
            columns=column_name,
        )

    elif isinstance(model_component, pyo.Constraint):
        if dual_only:
            df = pd.DataFrame.from_dict(
                {
                    idx: {"Dual": model_component[idx].get_suffix_value("dual", default=np.nan)}
                    for idx in model_component
                },
                orient="index",
            )
            df.columns = column_name
        else:
            # todo: why do these get special treatment?
            constraints_to_print_expr = [
                "Rep_Period_Energy_Budget_Constraint",
            ]
            df = pd.DataFrame.from_dict(
                {
                    idx: {
                        "Lower Bound": pyo.value(model_component[idx].lower),
                        "Body": pyo.value(model_component[idx].body),
                        "Upper Bound": pyo.value(model_component[idx].upper),
                        "Dual": model_component[idx].get_suffix_value("dual", default=np.nan),
                        "Expression": model_component[idx].expr
                        if model_component.name in constraints_to_print_expr
                        else None,
                    }
                    for idx in model_component
                },
                orient="index",
            )
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
