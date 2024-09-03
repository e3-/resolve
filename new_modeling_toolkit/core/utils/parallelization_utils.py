from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Sequence

from joblib import cpu_count
from joblib import delayed
from joblib import Parallel
from loguru import logger
from tqdm.auto import tqdm


def parallelize(
    func: Callable,
    args_list: Optional[Sequence[Sequence[Any]]] = None,
    kwargs_list: Optional[Sequence[Dict[str, Any]]] = None,
    num_processes: Optional[int] = None,
    show_progress_bar: bool = True,
    progress_bar_description: Optional[str] = None,
    debug: Optional[bool] = False,
    backend: Optional[str] = "loky",
    temp_folder: Optional[str] = None,
) -> List[Any]:
    """Parallelizes calling the function with specified arguments using `joblib` as the backend.

    Args:
        func: function to be called
        args_list: list of positional arguments for each function call
        kwargs_list: list of keyword arguments for each function call
        num_processes: number of parallel processes to use. Default is the detected number of CPUs
        show_progress_bar: whether to show a progress bar
        progress_bar_description: short title for the progress bar

    Returns:
        outputs (list): output of function for each of the arguments
    """
    if args_list is None and kwargs_list is not None:
        args_list = [tuple()] * len(kwargs_list)
    elif kwargs_list is None and args_list is not None:
        kwargs_list = [dict()] * len(args_list)
    elif len(args_list) != len(kwargs_list):
        raise ValueError("Length of `args` and `kwargs` must be the same")

    if num_processes is None:
        num_processes = cpu_count()
    if debug:
        num_processes = 1
    num_processes = min(num_processes, len(args_list))
    logger.debug(f"Number of sub-processes: {num_processes}")

    outputs = Parallel(n_jobs=num_processes, backend=backend, temp_folder=temp_folder)(
        delayed(func)(*args, **kwargs)
        for args, kwargs in tqdm(
            zip(args_list, kwargs_list),
            disable=not show_progress_bar,
            total=len(args_list),
            desc=progress_bar_description,
        )
    )

    return outputs
