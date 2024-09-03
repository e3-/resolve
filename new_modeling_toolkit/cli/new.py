import sys

import typer
from upath import UPath

import xlwings as xw
from new_modeling_toolkit import resolve

app = typer.Typer()


@app.command()
def connect(filepath: str):
    """Connect to a scenario tool, embedding the environment's interpreter path in `xlwings.conf`."""
    ui_path = UPath(filepath)
    with xw.App(visible=False):
        wb = xw.Book(ui_path)
        wb.sheets["xlwings.conf"].range("__INTERPRETERPATH__").value = sys.executable
        wb.sheets["RESOLVE Settings"].range("__KITPATH__").value = str(UPath(resolve.__file__).parent)
        wb.save()

    if sys.platform == "darwin":
        import shutil
        import new_modeling_toolkit.ui

        applescript_file = "runTerminalCommand-0.24.0.applescript"
        applescript_path = UPath(new_modeling_toolkit.ui.__file__).parent / applescript_file
        com_excel_path = UPath("~/Library/Application Scripts/com.microsoft.Excel/").expanduser()
        com_excel_path.mkdir(exist_ok=True, parents=True)
        shutil.copyfile(applescript_path, com_excel_path / applescript_file)

    print(f'Spreadsheet "{ui_path.stem}" now connected to current environment ({sys.prefix}).')


@app.command()
def main():
    app()


if __name__ == "__main__":
    app()
