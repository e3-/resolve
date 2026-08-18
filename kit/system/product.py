import os
from typing import Any
from typing import Optional

from pydantic import Field

from kit.core import component
from kit.core import dir_str
from kit.core.temporal import timeseries as ts


class Product(component.BaseComponent):
    pass


class EnergyCarrier(Product):
    pass


class Demand(Product):
    pass


class Market(Product):
    """Data holder for price streams in timeseries format.

    Args:
        name: Name for the price stream/market. Ex: "CAISO SP15
        data: Prices in dataframe. Column headers should be the year of the data.
        nominal: If True, the price_stream data is in nominal dollar years
        dollar_year: If nominal=False, must specify what dollar year the prices are in. Ex: 2030
    """

    price_stream: Optional[ts.NumericTimeseries] = Field(
        None, default_freq="H", up_method="ffill", down_method="mean"
    )
    nominal: bool = True
    dollar_year: Optional[int] = None

    # Optional fields
    import_capability: Any = None  # TODO: RSG Come back after ts.Timeseries is updated
    export_capability: Any = None

    # def __post_init__(self):
    #     self.timeseries_type = "market"

    def __post_init__(self):
        self.dollar_year = int(self.dollar_year)
        self.nominal = Market.str2bool(self.nominal)

    @staticmethod
    def str2bool(v):
        if type(v) == bool:
            return v
        else:
            return v.lower() in ("yes", "true", "t", "1")

    def convert_to_nominal(self, inflation_rate):
        """Converts the price streams from real dollars into nominal dollars based on year of column header.

        Args:
            inflation_rate: inflation rate in percent. Ex: .02

        Returns:
            None
        """
        """convert to dollar year of the column header
        Args: dollar_year is the current dollar year of the price stream"""

        if not self.nominal:
            for year in set(self.price_stream.data.index.year):
                year_filter = self.price_stream.data.index.year == year
                self.price_stream.data.loc[year_filter, :] *= (1 + inflation_rate) ** (
                    int(year) - self.dollar_year
                )
            self.dollar_year = None
            self.nominal = True
        else:
            print("Market in nominal $")

    def convert_to_real(self, inflation_rate, new_dollar_year):
        """Changes the nominal prices streams into a consistent dollar year.

        Args:
            inflation_rate: inflation rate in percent. Ex: .02
            new_dollar_year: dollar year to convert the price streams to. Ex: 2030

        Returns:
           None
        """

        if self.nominal:
            for year in set(self.price_stream.data.index.year):
                year_filter = self.price_stream.data.index.year == year
                self.price_stream.data.loc[year_filter, :] /= (1 + inflation_rate) ** (
                    int(year) - int(new_dollar_year)
                )
            self.dollar_year = int(new_dollar_year)
            self.nominal = False
        else:
            print("Market in real {}$".format(str(self.dollar_year)))

    def change_dollar_year(self, inflation_rate, new_dollar_year):
        """Converts the price streams from a real dollar year into another dollar year.

        Args:
            inflation_rate: inflation rate in percent. Ex: .02
            new_dollar_year: dollar year to convert the price streams to. Ex: 2030

        Returns:
            None
        """
        if not self.nominal:
            self.convert_to_nominal(inflation_rate)
            self.convert_to_real(inflation_rate, new_dollar_year)
        else:
            print("Market in nominal $")


def Main():
    # Testing Market class

    # path to data folder
    data_path = os.path.join(dir_str.data_dir, "interim", "markets")
    # instantiate market objects
    markets = Market.from_dir(data_path)
    print(markets)


if __name__ == "__main__":
    import rich.traceback

    rich.traceback.install()
    Main()
