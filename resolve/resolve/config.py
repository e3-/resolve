import os
import re

"""Configuration and feature flags controlled by environment variables."""
# todo: add unit tests


def _get_env_bool(key: str, default: bool = False) -> bool:
    """Get boolean environment variable with default value.

    Accepts: '1', 'true', 'True', 'TRUE', 'yes', 'Yes', 'YES' as True
    Everything else (including unset) returns False or the default.

    Args:
        key: Environment variable name
        default: Default value if not set or invalid

    Returns:
        Boolean value of the environment variable
    """
    value = os.getenv(key, str(default)).lower()
    return value in ("1", "true", "yes")


def _get_env_int(key: str, default: int = 0) -> int:
    """Get integer environment variable with default value.

    Args:
        key: Environment variable name
        default: Default value if not set or invalid

    Returns:
        Integer value of the environment variable
    """
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


def _get_env_str(key: str, default: str = "") -> str:
    """Get string environment variable with default value.

    Args:
        key: Environment variable name
        default: Default value if not set

    Returns:
        String value of the environment variable
    """
    return os.getenv(key, default)


def _get_env_memory(key: str, default: int = 0) -> int:
    """Get memory environment variable with unit support, return in bytes.

    Supports units: kB, KiB, MB, MiB, GB, GiB
    - kB = 1000 bytes, KiB = 1024 bytes
    - MB = 1000^2 bytes, MiB = 1024^2 bytes
    - GB = 1000^3 bytes, GiB = 1024^3 bytes

    Args:
        key: Environment variable name
        default: Default value in bytes if not set or invalid

    Returns:
        Memory value in bytes

    Examples:
        "1000" -> 1000 bytes
        "10kB" -> 10000 bytes
        "10KiB" -> 10240 bytes
        "5MB" -> 5000000 bytes
        "5MiB" -> 5242880 bytes
        "2GB" -> 2000000000 bytes
        "2GiB" -> 2147483648 bytes
    """
    value = os.getenv(key, "").strip()
    if not value:
        return default

    # Define unit multipliers
    units = {
        "kb": 1000,
        "kib": 1024,
        "mb": 1000**2,
        "mib": 1024**2,
        "gb": 1000**3,
        "gib": 1024**3,
    }

    # Parse value with regex to separate number and unit
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([a-zA-Z]+)?$", value)
    if not match:
        return default

    number_str, unit = match.groups()
    try:
        number = float(number_str)
    except ValueError:
        return default

    # If no unit specified, assume bytes
    if not unit:
        return int(number)

    # Convert unit to lowercase and apply multiplier
    unit_lower = unit.lower()
    if unit_lower in units:
        return int(number * units[unit_lower])

    # Unknown unit, return default
    return default


ENABLE_RICH_TRACEBACK = _get_env_bool("KIT_ENABLE_RICH_TRACEBACK", default=False)
ENABLE_RAY = _get_env_bool("KIT_ENABLE_RAY", default=False)
MAIN_MEMORY = _get_env_memory("KIT_MAIN_MEMORY", default=100e9)  # 100 GB default

RUNNING_ON_ANYSCALE = bool(os.getenv("ANYSCALE_INSTANCE_ID", "").strip())
