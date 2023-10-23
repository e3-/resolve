import datetime
import pathlib
from typing import Optional

import pandas as pd
import pydantic
from dateutil.parser import parse

from resolve.core import custom_model
from resolve.core import dir_str
from resolve.core import linkage
from resolve.core.temporal import timeseries as ts

#############
# Constants #
#############
# Current pro forma CSV format has data starting on row 6
PROFORMA_INPUT_SKIPROWS = 6
# Current pro forma CSV format has datetime column in column 3
PROFORMA_INPUT_DT_COLUMN = 3


class ProForma(custom_model.CustomModel):
    """
    ProForma object containing resource cost outputs, finance inputs and meta data

    data (pd.Dataframe): raw inputs incl. Installed cost ($/kW-ac), LCOE-Total ($/MWh), LFC-Total ($/kW-yr), etc.
    meta (pd.Dataframe): original file path, user, dollar year
    """

    # TODO: Move this relationship to Resource to be a Linkage class
    name: str = pydantic.Field(alias="Scenario name")
    workbook_name: str = pydantic.Field(alias="Workbook Name")
    date_created: datetime.datetime = pydantic.Field(alias="Date Created")
    created_by: str = pydantic.Field(alias="Created by")
    dollar_year: int = pydantic.Field(alias="Output dollar year")

    resources: dict[str, linkage.Linkage] = {}

    ###############
    # DATA FIELDS #
    ###############
    annual_escalation_fixed_om: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Annual FOM Escalation")
    annual_escalation_variable_om: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Annual VOM Escalation")
    bonus_depreciation: Optional[ts.BooleanTimeseries] = pydantic.Field(alias="Include Bonus Depreciation?")
    capacity_factor: Optional[ts.FractionalTimeseries] = pydantic.Field(alias="Capacity Factor")
    cost_annual_augmentation: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Annual Augmentation Cost")
    cost_fixed_om: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Fixed O&M Cost")
    cost_installed: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Installed Cost")
    cost_interconnection: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Interconnection Cost")
    cost_variable_om: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Variable O&M")
    debt_period: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Debt Period")
    debt_return: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Debt Return")
    debt_share: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Debt Share")
    degradation: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Degradation")
    dscr: Optional[ts.NumericTimeseries] = pydantic.Field(alias="DSCR (>1.4 desired for IPP)")
    equity_return: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Equity Return")
    equity_share: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Equity Share")
    financial_lifetime: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Financing Lifetime")
    fuel_annual_escalation: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Annual Fuel Escalation")
    fuel_type: Optional[ts.Timeseries] = pydantic.Field(alias="Fuel Type")
    fuel_unit_cost: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Unit Fuel Cost")
    heat_rate: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Heat Rate")
    ilr: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Inverter Loading Ratio")
    itc: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Investment Tax Credit")
    itc_cost_eligibility: Optional[ts.NumericTimeseries] = pydantic.Field(alias="ITC Cost Eligibility")
    lcoe_capital: Optional[ts.NumericTimeseries] = pydantic.Field(alias="LCOE - Capital")
    lcoe_fixed_om: Optional[ts.NumericTimeseries] = pydantic.Field(alias="LCOE - Fixed O&M")
    lcoe_fuel: Optional[ts.NumericTimeseries] = pydantic.Field(alias="LCOE - Fuel")
    lcoe_interconnection: Optional[ts.NumericTimeseries] = pydantic.Field(alias="LCOE - Interconnection")
    lcoe_itc: Optional[ts.NumericTimeseries] = pydantic.Field(alias="LCOE - ITC")
    lcoe_ptc: Optional[ts.NumericTimeseries] = pydantic.Field(alias="LCOE - PTC")
    lcoe_total: Optional[ts.NumericTimeseries] = pydantic.Field(alias="LCOE - Total")
    lcoe_variable_om: Optional[ts.NumericTimeseries] = pydantic.Field(alias="LCOE - Variable O&M")
    lcoe_warranty_augmentation: Optional[ts.NumericTimeseries] = pydantic.Field(
        alias="LCOE - Warranty, Augmentation, Periodic Replacement"
    )
    levelized_cost_escalation: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Levelized Cost Escalation")
    lfc_capital: Optional[ts.NumericTimeseries] = pydantic.Field(alias="LFC - Capital")
    lfc_fixed_om: Optional[ts.NumericTimeseries] = pydantic.Field(alias="LFC - Fixed O&M")
    lfc_interconnection: Optional[ts.NumericTimeseries] = pydantic.Field(alias="LFC - Interconnection")
    lfc_itc: Optional[ts.NumericTimeseries] = pydantic.Field(alias="LFC - ITC")
    lfc_ptc: Optional[ts.NumericTimeseries] = pydantic.Field(alias="LFC - PTC")
    lfc_total: Optional[ts.NumericTimeseries] = pydantic.Field(alias="LFC - Total")
    lfc_warranty_augmentation: Optional[ts.NumericTimeseries] = pydantic.Field(
        alias="LFC - Warranty, Augmentation, Periodic Replacement"
    )
    macrs_term: Optional[ts.NumericTimeseries] = pydantic.Field(alias="MACRS Term")
    ptc: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Production Tax Credit")
    ptc_duration: Optional[ts.NumericTimeseries] = pydantic.Field(alias="PTC Duration")
    wacc_after_tax: Optional[ts.NumericTimeseries] = pydantic.Field(alias="After-Tax WACC")
    warranty_annual_extension_cost: Optional[ts.NumericTimeseries] = pydantic.Field(
        alias="Annual Warranty Extension Cost"
    )
    warranty_initial_length: Optional[ts.NumericTimeseries] = pydantic.Field(alias="Initial Warranty Length")

    @pydantic.validator("date_created", pre=True)
    def convert_date_created(cls, date_created):
        """Convert date_created to datetime.

        Assuming that converting to a datetime object isn't a big deal (whether the value is a str or a datetime).
        """
        if isinstance(date_created, datetime.datetime):
            return date_created
        else:
            return parse(date_created)

    @pydantic.validator("name", pre=True)
    def strip_csv_from_name(cls, name):
        if name.endswith(".csv"):
            return name[:-4]
        else:
            return name

    def get_tech_specific_proforma(self, proforma_tech):
        """Create an instance of ProForma that has only the values related to the specified proforma_tech."""

        # Check if proforma_tech is unique (assumes we can check any pro forma attribute for unique tech names)
        techs = self.annual_escalation_fixed_om.data.index.get_level_values(0)
        # Strip out the [Energy]/[Capacity] identifiers
        techs = techs.str.replace("\[Energy\]|\[Capacity\]", "", regex=True)
        unique_techs = list(techs[techs.str.contains(proforma_tech)].unique())
        if len(unique_techs) > 1:
            raise ValueError(
                f"Cannot slice proforma asset costs: multiple technologies with '{proforma_tech}' found in {self.name}: \n {unique_techs}"
            )

        # Slice proforma
        attrs = {}
        for field_name in self.__fields__.keys():
            field_alias = self.__fields__[field_name].alias
            field = getattr(self, field_name)
            if self.__fields__[field_name].type_ in ts.Timeseries.__subclasses__():
                techs = field.data.index.get_level_values(0)
                if ".*" in proforma_tech:
                    field_slice = field.data.loc[
                        techs.str.contains(f"{proforma_tech}"),
                        :,
                    ]
                else:
                    field_slice = field.data.loc[techs == proforma_tech, :]
                if field_slice.empty:
                    attrs.update({field_alias: None})
                else:
                    attrs.update({field_alias: ts.Timeseries(name=field_name, data=field_slice)})
            else:
                attrs.update({field_alias: field})

        return ProForma(**attrs)

    @classmethod
    def from_csv(cls, instance_path):
        """
        Return proforma inputs and meta data associated with the file
        """
        proformas = {}

        if not str(instance_path).endswith(".csv"):
            instance_path = pathlib.Path(str(instance_path) + ".csv")

        # read in proforma outputs
        proforma = pd.read_csv(
            instance_path,
            skiprows=PROFORMA_INPUT_SKIPROWS,
            parse_dates=[PROFORMA_INPUT_DT_COLUMN],
            infer_datetime_format=True,
        )

        # TODO (5/11): Could make each technology a separate proforma
        data = {}
        for name, group in proforma.groupby("Variable"):
            group["Year"] = pd.to_datetime(group["Year"])
            group = group[["Year", "Technology", "Value"]].set_index(["Technology", "Year"]).squeeze()
            data.update({name: ts.Timeseries(name=f"{name}", data=group)})

        metadata = (
            pd.read_csv(
                instance_path,
                header=None,
                nrows=5,
                index_col=0,
            )
            .iloc[:, :1]
            .squeeze()
            .to_dict()
        )

        attrs = {**data, **metadata}

        p = ProForma(**attrs)

        return p.name, p


if __name__ == "__main__":
    data_path = dir_str.data_interim_dir / "proformas" / "E3_ProForma_20210727_outputs_mid.csv"
    # instantiate proforma
    _, proforma = ProForma.from_csv(data_path)
    proforma.get_tech_specific_proforma("Li")
