import pathlib
import sys
from typing import Optional

import pandas as pd
import xlwings as xw

# Set traceback limit to 0 so that error message is more readable in Excel popup window
sys.tracebacklimit = 0


def set_input_messages(wb: Optional[xw.Book] = None):
    """Set input messages (i.e., under Data Validations > Input Messages) programmatically.

    https://github.com/xlwings/xlwings/issues/1446
    https://learn.microsoft.com/en-us/office/vba/api/excel.validation.inputmessage
    """
    if wb is None:
        wb = xw.Book.caller()

    # Read in input messages as a dataframe
    input_messages = wb.sheets["Input Messages"].range("input_messages").options(pd.DataFrame, index=2).value

    # Iterate over dataframe, assigning input message to each range
    for idx, row in input_messages.iterrows():
        sheet_name, range_name = idx
        wb.sheets[sheet_name].range(range_name).api.Validation.InputMessage(row["Input Message"])


if __name__ == "__main__":
    # Create mock caller
    curr_dir = pathlib.Path(__file__).parent
    xw.Book(curr_dir / ".." / ".." / "RECAP-RESOLVE Scenario Tool.xlsm").set_mock_caller()
    wb = xw.Book.caller()

    set_input_messages(wb=wb)
