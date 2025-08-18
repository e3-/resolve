from typing import ClassVar
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from new_modeling_toolkit.core import component
from new_modeling_toolkit.core import dir_str
from new_modeling_toolkit.core import linkage


class OutageDistribution(component.Component):
    SAVE_PATH: ClassVar[str] = "outage_distributions"
    ### LINKAGES ###
    resources: dict[str, linkage.Linkage] = {}

    ### ATTRIBUTES ###

    # Dataframe containing paired derate fractions and probabilities
    # Includes derate = 0 (on)
    # assigned, not in CSV (col1: % derate, col2: probability of derate)
    probability_mass_function: Optional[pd.DataFrame] = None

    # To support derate fractions and derate probabilities of unknown number (i.e., derate_1, derate_prob_1, derate_2, ...)
    # I have not used an __init__ function (which would have enforced a particular set of inputs)
    # Instead I have used a @property (PMF) which is defined using a function (set_pmf()) which will work with
    # as many derate and derate probabilities as you would like

    @property
    def PMF(self):
        """
        Returns probability mass function for outages
        """
        if self.probability_mass_function is None:
            self.set_pmf()
        return self.probability_mass_function

    def set_pmf(self):
        # Identify variables with derate in the name
        d_derates = [k for k in self.model_extra.keys() if "derate" in k]
        if len(d_derates) % 2 != 0:
            logger.exception(f"There must be an equal number of derates and derate probabilities in {self.name}")
        n_derates = int(len(d_derates) / 2)
        l_derate = []
        l_derate_prob = []
        for i in range(1, n_derates + 1):
            l_derate.append(self.model_extra[f"derate_{i}"])
            l_derate_prob.append(self.model_extra[f"derate_prob_{i}"])

        # Check that sum of probabilties is 1 and values are between 0 and 1
        self.derate_checks(l_derate_prob, l_derate)

        # Derate probabilities given outage (P(derate | outage))
        l_derate_prob = [d for d in l_derate_prob]
        data = {"derate": l_derate, "derate_prob": l_derate_prob}
        self.probability_mass_function = pd.DataFrame.from_dict(data)

    def get_random_derate_fraction_arr(self, size, seed):
        # percent_on_during_outage = 1 - derate_fraction
        l_derate = self.PMF["derate"].tolist()
        l_derate_prob = self.PMF["derate_prob"].tolist()
        np.random.seed(seed)
        derate_fracs = np.random.choice(l_derate, size=size, p=l_derate_prob)
        return derate_fracs

    def derate_checks(self, l_derate_prob, l_derate):
        if sum(l_derate_prob) != 1:
            logger.exception(f"Sum of derate probabilities in outage distribution {self.name} must sum to 1")
        if any(d_p < 0 for d_p in l_derate_prob):
            logger.exception(f"Derate probabilities in outage distribution {self.name} must be non-negative")
        if any(d < 0 or d > 1 for d in l_derate):
            logger.exception(f"Derate fractions in outage distribution {self.name} must be between 0 and 1")

    @classmethod
    def get_data_from_xlwings(
        cls, wb: "Book", sheet_name: str, fully_specified: bool = False, new_style: bool = False
    ) -> pd.DataFrame:
        """Override ``Component.get_data_from_xlwings``, because outage distribution points are special.

        Currently, this class does not have any particular input attributes. All attributes are in the form of "derate_#" and "derate_prob_#",
        so we cannot read directly from the Scenario Tool the way we would for standard component classes.
        This way of defining attributes works because in ``CustomModel`` we are allow extra attributes to be passed.

        To accommodate the extra "index", we assume that the ``index`` named range (``OutageDistribution``) is two columns,
        where the second column is the distribution point.
        """
        sheet = wb.sheets[sheet_name]

        # Clear filters applied to sheet
        wb.app.status_bar = f"Clearing filters on {sheet_name}"
        sheet.api.AutoFilterMode = False

        # Get all named ranges that refer to the current sheet
        named_ranges: set = {
            name.name for name in wb.names if name.refers_to.split("!")[0][1:].replace("'", "") == sheet_name
        }

        # Get index as two long lists (assumes range is "tall" and not "wide")
        # We force xlwings to return the range as 2-dimensional and transpose is to ensure that we always get a list of "long" lists
        index: list = sheet.range(cls.__name__).options(ndim=2, transpose=True).value

        # Get all scenario tags (or return a index-length list of None)
        scenario: list = [
            (
                sheet.range(f"{cls.__name__}.scenario").value
                if f"{sheet_name}!{cls.__name__}.scenario" in named_ranges
                else [None] * len(index[0])
            )
        ]

        # Find all attribute names that correspond to named ranges on this sheet
        ranges_to_search: list = ["derate", "derate_prob"]

        # Create one large dataframe of all instances & attributes from this sheet
        data = pd.concat(
            [sheet.range(attribute).options(pd.DataFrame, header=2, index=0).value for attribute in ranges_to_search],
            axis=1,
        )
        data.index = index + scenario

        # Unpivot dataframe
        data = data.melt(ignore_index=False).rename(
            columns={
                "variable_0": "attribute",
                "variable_1": "timestamp",
            }
        )

        # Do cleanup to append distribution point number to attribute names
        data = data.reset_index()
        data["attribute"] = data[["attribute", "level_1"]].apply(
            lambda x: x.iloc[0] if pd.isna(x.iloc[1]) else f"{x.iloc[0]}_{int(x.iloc[1])}", axis=1
        )
        data = data.drop(["level_1"], axis=1)
        data = data.set_index(["level_0", "level_2"])
        data.index.names = ["instance", "scenario"]

        # Clean up `timestamp` column (fill None and convert to dates, assuming header timestamp is just a year number)
        data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce").fillna("None")

        # Replace any empty strings with `None`
        data["value"] = data["value"].replace("", None)

        return data


if __name__ == "__main__":
    test_outage_distribution = OutageDistribution(
        name="Test outage distribution", derate_1=1, derate_prob_1=0.1, derate_2=0.5, derate_prob_2=0.9
    )

    test_outage_distribution_csv = OutageDistribution.from_dir(
        data_path=dir_str.data_dir / "interim" / "outage_distributions"
    )
    print(f"From csv file: {test_outage_distribution_csv}")
    print(test_outage_distribution_csv["outage_dist_1"].get_random_percent_on_during_outage_arr(50, seed=212))
