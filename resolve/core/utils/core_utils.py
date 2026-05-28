import time
from functools import partial
from io import StringIO
from operator import is_not
from typing import Any
from typing import Callable
from typing import Dict
from typing import Iterable
from typing import List

from loguru import logger


def map_dict(func: Callable, dict_: Dict[Any, Any]) -> Dict[Any, Any]:
    """Returns a copy of the dictionary with the function applied to all of its values.

    Args:
        dict_: dictionary to apply the function to
        func (function): function to apply to the values of the dictionary

    Returns:
        mapped_dict (dict): dict with mapped values
    """
    keys, values = list(dict_.keys()), list(dict_.values())
    mapped_dict = dict(list(zip(keys, list(map(func, values)))))

    return mapped_dict


def filter_not_none(values: List) -> List:
    """Filters the passed values for ones that are not None.

    Args:
        values: values to filter

    Returns:
        filtered_values: filtered values
    """
    filtered_values = list(filter(partial(is_not, None), values))

    return filtered_values


def map_not_none(func: Callable, values: List) -> List:
    """Applies a function to each item in a list, skipping values in the list that are None

    Args:
        func: function to apply to list values
        values: list of values to apply the function to

    Returns:
        mapped_values: list of values with the function applied
    """

    mapped_values = list(map(func, filter_not_none(values)))

    return mapped_values


def sum_not_none(values: Iterable) -> Any:
    """Sums the values in an Iterable, ignoring those values which are None.

    Args:
        values: values to sum

    Returns:
        sum of values, without those that are None
    """
    non_none_values = filter_not_none(values)
    if len(non_none_values) == 0:
        sum_ = None
    else:
        sum_ = sum(non_none_values)

    return sum_


def timer(func):
    """Simple timer decorator"""

    def wrapper(*args, **kwargs):
        start = time.time()
        value = func(*args, **kwargs)
        end = time.time()
        logger.debug(f"{func.__name__!r} took {(end - start):.2f} seconds")

        return value

    return wrapper


def cantor_pairing_function(a: int, b: int) -> int:
    """
    Encodes two natural number into a single, unique natural number.
    Makes sure we have unique seeds for each combination of Monte Carlo Seed and Generator Seed
    """
    if a < 0 or b < 0:
        raise ValueError("All arguments to `cantor_pairing_function()` must be non-negative integers")

    return int(0.5 * (a + b) * (a + b + 1) + b)


def profile_time(function, *args, **kwargs):
    from line_profiler import LineProfiler

    def wrapper(*args, **kwargs):
        # profile the construct operation block function and save results to log file
        lp = LineProfiler()
        lp.add_function(function)
        lp_wrapper = lp(function)
        return_value = lp_wrapper(*args, **kwargs)
        profiler_output = StringIO()
        lp.print_stats(stream=profiler_output)
        logger.info("Line Profiler Results:\n{}", profiler_output.getvalue())
        return return_value

    return wrapper


def profile_memory(function, *args, **kwargs):
    from memory_profiler import profile

    def wrapper(*args, **kwargs):
        profiler_output = StringIO()
        return_value = profile(function)(*args, **kwargs)
        logger.info("Memory Profiler Results:\n%s", profiler_output.getvalue())
        return return_value

    return wrapper


def convert_to_bool(v):
    if type(v) == bool:
        bool_value = v
    elif type(v) == str:
        bool_value = v.lower() in ("yes", "true", "t", "1")
    elif type(v) == int or type(v) == float:
        bool_value = bool(v)
    else:
        raise ValueError(f"Unsupported type `{type(v)}` for input value `{v}`")

    return bool_value
