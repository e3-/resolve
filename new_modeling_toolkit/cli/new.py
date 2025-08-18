import sys

import typer
import xlwings as xw
from upath import UPath

from new_modeling_toolkit import resolve

app = typer.Typer()


@app.command()
def connect(filepath: str):
    """Connect to a scenario tool, embedding the environment's interpreter path in `xlwings.conf`."""
    ui_path = UPath(filepath)
    with xw.App(visible=False):
        wb = xw.Book(ui_path)
        wb.sheets["xlwings.conf"].range("__INTERPRETERPATH__").value = sys.executable
        wb.sheets["xlwings.conf"].range("__KITPATH__").value = str(UPath(resolve.__file__).parents[2])
        wb.sheets["xlwings.conf"].range("__LOCALPATH__").value = None
        wb.save()

    if sys.platform == "darwin":
        import shutil
        import new_modeling_toolkit.ui

        # Install the xlwings applescript
        from xlwings.cli import runpython_install

        runpython_install(None)

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
