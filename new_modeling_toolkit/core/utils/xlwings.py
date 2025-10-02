from dataclasses import dataclass
from platform import system
from typing import Literal

import xlwings as xw

@dataclass
class ExcelApiCalls:
    """Simple wrapper to make xlwings `.api` calls cleaner (instead of needing to always write `if/else` every time).

    All methods should take the form of:
        if self.platform == "Darwin":
            ...
        else:
            ...
    where "Darwin" is the platform name for macOS, and "else" would de-facto be Windows.

    Windows VBA API is pretty well-documented here: https://learn.microsoft.com/en-us/office/vba/api/overview/excel
    """

    platform: str = system()

    def set_cell_style(self, obj, style):
        if self.platform == "Darwin":
            obj.api.style_object.set(style)
        else:
            obj.api.Style = style

    def styles(self, obj, style_name):
        if self.platform == "Darwin":
            return obj.api.styles[style_name]
        else:
            return obj.api.Styles(style_name)

    def set_gridlines(self, obj, value):
        if self.platform == "Darwin":
            obj.api.active_window.display_gridlines.set(value)
        else:
            obj.api.ActiveWindow.DisplayGridlines = value

    def group(self, rng: xw.Range, by: Literal["column", "row"] = "column"):
        if by == "column":
            cols = rng.columns
            for col in cols:
                if self.platform == "Darwin":
                    col.api.columns[col.address].group()
                else:
                    # On Windows, Columns() takes just the column letter
                    col.api.Columns(col.address[1]).Group()
        elif by == "row":
            rows = rng.rows
            for row in rows:
                if self.platform == "Darwin":
                    row.api.rows[row.address].group()
                else:
                    # On Windows, Rows() takes just the row number
                    row.api.Rows(row.address[-1]).Group()
        else:
            raise NotImplementedError(f"{by} not implemented. Use `column` or `row`.")

    def hide(self, *args, **kwargs):
        raise NotImplementedError

    def hide_details(self, sheet: xw.Sheet):
        if self.platform == "Darwin":
            sheet.api.outline_object.show_levels(row_levels=1)
            sheet.api.outline_object.show_levels(column_levels=1)
        else:
            sheet.api.Outline.ShowLevels(1, 1)

    def shapes_add_form_control(self, sheet: xw.Sheet, *args):
        if self.platform == "Darwin":
            raise NotImplementedError(f"{self.platform} not implemented.")
        else:
            return sheet.api.Shapes.AddFormControl(*args)
