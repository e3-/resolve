import pathlib

import pandas as pd
from loguru import logger
from pydantic import Field
from pydantic import validator

from new_modeling_toolkit.core import custom_model
from new_modeling_toolkit.core.utils import util


class CustomConstraints(custom_model.CustomModel):
    # a dictionary of the dictionaries.
    LHS: dict[str, pd.DataFrame] = Field(
        default=None,
        description="A dictionary defining the left hand side of the custom constraint. "
        "The keys are the Variable/Expression to sum, and the values are dataframes determing index "
        "combinations to be summed, and also the multiplier for each combination.",
    )
    operator: str = Field(default=None, description="operator linking the LHS and RHS of this custom constraint.")
    target: float = Field(default=None, description="The right hand side of the custom constraints as a float")

    @validator("operator")
    def validate_operator(cls, operator, values):
        valid_constraints = [">=", "<=", "==", "gt", "lt", "eq"]
        if operator not in valid_constraints:
            raise ValueError(f"Policy '{values['name']}' attribute 'operator' must be in {valid_constraints}")
        return operator

    @classmethod
    def get_constraint_group(cls, constraint_dir: pathlib.Path):
        """Create a single group of CustomConstraint instances.

        Args:
            constraint_dir:

        Returns:
            constraint_dict
        """
        constraint_name = constraint_dir.stem
        logger.debug(f"Reading custom constraint group: {constraint_name}")

        targets = pd.read_csv(constraint_dir / "target.csv", index_col="Sum Range ID")
        operators = pd.read_csv(constraint_dir / "operator.csv", index_col="Sum Range ID")

        lhs_dict = {
            file_path.stem: pd.read_csv(file_path, index_col="Sum Range ID").groupby("Sum Range ID")
            for file_path in constraint_dir.glob("*.csv")
            if file_path.name not in ["target.csv", "operator.csv"]
        }
        # TODO (2021-12-07): This conditional could probably be a regex search

        constraint_dict = {
            f"{constraint_name}_{idx}": cls(
                name=f"{constraint_name}_{idx}",
                target=targets.loc[idx],
                operator=operators.loc[idx].values[0],
                LHS={
                    # Relying on pd.to_numeric to correctly convert `object` columns to `int` when possible
                    model_component: df.get_group(idx).apply(pd.to_numeric, errors="ignore")
                    if idx in df.groups
                    else pd.DataFrame()
                    for model_component, df in lhs_dict.items()
                },
            )
            for idx in targets.index.unique()
        }

        return constraint_name, constraint_dict

    @classmethod
    def from_dir(cls, constraints_dir):
        """Initialize all CustomConstraintGroups listed in a directory.

        Args:
            constraints_dir (pathlib.Path):

        Returns:
            custom_constraint_dict

        """
        constraints_to_load_filename = constraints_dir / "constraints_to_load.csv"
        if constraints_to_load_filename.exists():
            read_all_constraints = False
            constraints_to_load = pd.read_csv(constraints_to_load_filename).iloc[:, 0].to_list()
        else:
            read_all_constraints = True
            constraints_to_load = {}
            logger.info(f"Settings file '{constraints_to_load_filename}' not found. Reading all custom constraints...")

        custom_constraint_dict = {}
        for constraint_path in constraints_dir.iterdir():
            if constraint_path.is_dir() and (read_all_constraints or constraint_path.stem in constraints_to_load):
                _, constraint_dict = cls.get_constraint_group(constraint_path)
                custom_constraint_dict.update(constraint_dict)

        return custom_constraint_dict

    # TODO (2021-12-08): "new" from_dir method is slower than this one and also doesn't have some of the error messaging
    #
    #  @classmethod
    # def from_dir(cls, constraints_dir):
    #     """
    #     Args:
    #         constraints_dir:
    #
    #     Returns:
    #     """
    #
    #     # Initialize dictionaries to store the LHS and RHS of constraints
    #     # The left hand side of the custom constraints formulated as a dict of dictionaries. For the first layer, the
    #     # keys are Constraint name + sum range IDs. Each key uniquely identify an inequality. For the second layer, the
    #     # keys are the Variable/Expression to sum, and the values are dataframes determing index combinations to be
    #     # summed, and also the multiplier for each combination.
    #     LHS_dict = {}
    #     operator_dict = {}
    #     target_dict = {}
    #     custom_constraint_dict = {}
    #
    #     # read in all the constraints file as CSV
    #     for constraint_path in constraints_dir.glob("*"):
    #         if not constraint_path.is_dir():
    #             continue
    #         constraint_name = constraint_path.stem  # parse the name of the constraint thru path
    #         LHS_dict[constraint_name] = {}  # initialize empty dict for this constraint
    #
    #         # iterate through all files for this constraint
    #         for file_path in constraint_path.glob("*.csv"):
    #             var_name = file_path.stem.replace(".csv", "")
    #             LHS_dict[constraint_name][var_name] = pd.read_csv(file_path, index_col="Sum Range ID")
    #
    #     # Reorganize the first and second layer of the dictionary so that the first key represents both
    #     # constraint name and sum range ID
    #     LHS_dict_reorganized = {}
    #     for constraint_name in LHS_dict.keys():
    #         for var_name, var_df in LHS_dict[constraint_name].items():
    #             for sum_range_ID in var_df.index.unique():
    #                 constraint_ID = "_".join([constraint_name, str(sum_range_ID)])
    #                 # Split each file based on sum range ID.
    #                 if constraint_ID not in LHS_dict_reorganized.keys():
    #                     LHS_dict_reorganized[constraint_ID] = {}
    #                 LHS_dict_reorganized[constraint_ID][var_name] = var_df.loc[[sum_range_ID]]
    #     # replace the LHS dict with the reorganized version
    #     LHS_dict = LHS_dict_reorganized
    #
    #     # break out operators and targets into a separate dictionary
    #     for constraint_ID in LHS_dict.keys():
    #         for breakout_item in ["target", "operator"]:
    #             if breakout_item not in LHS_dict[constraint_ID].keys():
    #                 raise KeyError("{} not found for constraint {}".format(breakout_item, constraint_ID))
    #
    #             # gather information into the approriate dictionaries
    #             breakout_df = LHS_dict[constraint_ID].pop(breakout_item)
    #             # uniqueness check
    #             if breakout_df.shape[0] > 1:
    #                 raise ValueError(
    #                     "There should only be 1 {} for constraint {}, {} were found instead".format(
    #                         breakout_item, constraint_ID, breakout_df.shape[0]
    #                     )
    #                 )
    #             if breakout_item == "target":
    #                 target_dict[constraint_ID] = breakout_df.iloc[0, 0]
    #             else:
    #                 operator_dict[constraint_ID] = breakout_df.iloc[0, 0]
    #    #
    #     # iterate through all custom constraint and sum range, iterate each into a custom constraint settings class
    #     for constraint_ID in LHS_dict.keys():
    #         custom_constraint_dict[constraint_ID] = cls(
    #             name=constraint_ID,
    #             LHS=LHS_dict[constraint_ID],
    #             operator=operator_dict[constraint_ID],
    #             target=target_dict[constraint_ID],
    #         )
    #
    #     return custom_constraint_dict


def main():
    dir_str = util.DirStructure()
    dir_eg = dir_str.data_settings_dir / "resolve" / "toy" / "custom_constraints"
    # import datetime

    # print(str(datetime.datetime.now()))
    # custom_constraint_dict = CustomConstraints.from_dir(dir_eg)
    # print(str(datetime.datetime.now()))
    custom_constraint_dict_new = CustomConstraints.from_dir(dir_eg)
    # print(str(datetime.datetime.now()))
    test = CustomConstraints.get_constraint_group(
        dir_str.data_settings_dir / "resolve" / "toy" / "custom_constraints" / "solar_budget"
    )
    print()


if __name__ == "__main__":
    main()
