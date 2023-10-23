import importlib.metadata
import pathlib

import pandas as pd
from pint import UnitRegistry

__version__ = importlib.metadata.version(__package__)

ureg = UnitRegistry()


# Define USD as a currency unit. No additional conversions defined.
# Note: pint does not currently accept Unicode characters like $ and ¢
ureg.define("USD = [currency] = dollar")
ureg.define("cent = 0.01 * USD")

# Add thousand, million, billion, trillion (by default kilo, mega, etc. are already defined)
# Note: pint does not currently accept units or prefixes with spaces, so use underscores
ureg.define("thousand_- = 10 ** 3 = k_")
ureg.define("million_- = 10 ** 6 = M_")
ureg.define("billion_- = 10 ** 9 = B_")

attribute_units = pd.read_csv(pathlib.Path(__file__).parent / "common" / "units.csv")


def get_units(attr_name: str):
    return ureg.Quantity(attribute_units.loc[attribute_units["attribute"] == attr_name, "unit"].values[0])
