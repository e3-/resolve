```{eval-rst}
:tocdepth: 3
```

# Development Guide

Thanks for your interest in helping build `kit`!

## Style Guide

## Setting Up the Dev Environment

1. Please install the conda environment listed in `environment-dev.yml`. Update regularly—-particularly if you see
   updates to the `environment.yml` file as you merge in new changes from other folks.

(pre-commit)=

2. Please install the [pre-commit](https://pre-commit.com/) hooks by using the command `pre-commit install`
   (Note: This should be done inside `kit` `conda` environment.)
   Once installed, pre-commit hooks will automatically run before each commit and check several nitpicky things about
   your commit:
    - Hooks like the `black` code formatter (among others) will automatically edit your code and cause the commit to
      fail if they find code that they want to reformat. This is okay! Just re-commit, and now that the code has been
      formatted, the commit should succeed.
    - Cannot commit directly to the `main` branch
    - *Troubleshooting: Pre-commit hooks can be skipped by passing the `git` command the `--no-verify` argument or by
      turning off the "Run git hooks" setting in Pycharm's commit view. However, this you should not be skipping this
      step on a regular basis.* If you continue to have issues with the pre-commit hooks, please reach out to try to fix
      them. Some initial things to check:
        - Try reinstalling the pre-commit hooks by running `precommit uninstall` and then `pre-commit install`
        - Make sure that you have `conda` and `python` in your computer's `PATH`

## Dev Workflow Checklist

:::{raw} html
<br>
<div class="checkbox-wrapper-11">
  <input id="02-11" type="checkbox" name="r" value="2">
  <label for="02-11">Create a new branch</label>
</div>

<div class="checkbox-wrapper-11">
  <input id="02-11" type="checkbox" name="r" value="2">
  <label for="02-11">Make your changes, including tests & documentation</label>
</div>

<div class="checkbox-wrapper-11">
  <input id="02-11" type="checkbox" name="r" value="2">
  <label for="02-11">Open a pull request to discuss your changes</label>
</div>

<div class="checkbox-wrapper-11">
  <input id="02-11" type="checkbox" name="r" value="2">
  <label for="02-11">Make sure that all status checks/tests pass in your PR</label>
</div>

<div class="checkbox-wrapper-11">
  <input id="02-11" type="checkbox" name="r" value="2">
  <label for="02-11">Get your changes approved by one of the codeowners</label>
</div>

<div class="checkbox-wrapper-11">
  <input id="02-11" type="checkbox" name="r" value="2">
  <label for="02-11">Squash and merge your PR into `main`</label>
</div>
:::

## Key Frameworks

### Pydantic: `_DataModel` 

```{versionchanged} 0.19.1
`kit` has migrated to pydantic v2, which is not fully backwards-compatible with the v1 syntax.
```

A key energy system modeling challenge that `kit` is trying to address is data handling. The core data models (
Component, Linkage, System) use the [Pydantic](https://pydantic-docs.helpmanual.io) package for data validation.

In addition to data validation, Pydantic provides a simple API for converting Python objects to JSON files, which seem
the most promising way to store the entire hierarchy of `System` instance data
(as opposed to a complex, custom CSV format).

```{note}
A long-term goal of building `kit` on the wildly popular Pydantic package is to also 
leverage [FastAPI](https://fastapi.tiangolo.com) and [SQLModel](https://sqlmodel.tiangolo.com)
```

The `CustomModel` is the standard `kit` implementation of a Pydantic model that sets default configuration behavior for
the data models.

```{eval-rst}
.. autoclass:: new_modeling_toolkit.core.custom_model.CustomModel
   :no-index:
   :show-inheritance:
   :members: parse
```

### Pyomo: `ModelTemplate` & `FormulationBlock`

[Pyomo](https://pyomo.readthedocs.io/en/stable/index.html) is the Python optimization package that E3 has used for many
years. The `kit` uses some undocumented behavior of Pyomo to streamline the formulation, documented here for
contributors to understand.

#### `ModelTemplate` Framework

#### Formatting Pyomo Formulation Components

Instead, developers & contributors are asked to format the code manually as follows:

1. Use standard Python `snake_case` for **all** formulation components (parameters, variables, expressions, etc.)
2. Use vertical space (i.e., more lines) to make expressions more readable:
    - Use parentheses in the `return` statement, which will allow you to neatly break up long mathematical expressions
      without the use of line breaks (i.e., `\`).
    - Break up terms in the expression on new lines when possible
    - Put constraint operators (i.e., `>=`, `<=`, `==`) on their own line to clearly delineate left- and right-hand
      sides of equations
   ```python
   @self.model.Constraint(self.model.SET)
   def Example_Constraint(model, idx):
       return (
           model.X[idx] +
           model.Y[idx] 
           ==
           model.z[idx]
       )
   ```
3. Use list comprehensions when it makes sense, rather than `for` loops:
   ```python
   @self.model.Expression()
   def Good_Example_Sum(model):
       return sum(
           model.X[idx]
           for idx in model.SET
       )
   ```
   instead of
   ```python
   @self.model.Expression()
   def Bad_Example_Sum(model):
       total = float()
       for idx in model.SET:
           total += model.X[idx]
       return total
   ```

## Documentation

These links contain tips + tricks for writing Markdown documentation.

- [Myst](https://myst-parser.readthedocs.io/en/latest/)
- [Sphinx Awesome Theme](https://sphinxawesome.xyz)
- [Sphinx-Design](https://sphinx-design.readthedocs.io/en/latest/index.html)

### How do I edit the documentation?

1. Go to the `main` branch; checkout a new branch to work from.

2. Make edits to the markdown files in the `> docs > source` folder.

3. Confirm that edits behave as expected in HTML files.
    1. Activate the `kit-dev` Anaconda environment.
    2. Generate html files using the Sphinx `make html` command in the `> docs` folder.
    3. Open the `index.html` folder using Chrome/Firefox and click around the page to make sure everything looks OK.

4. Commit and push changes to main!

If you do not know how to perform some of the steps above related to GitHub, schedule a working session with someone on
the Recap 3.0 development team 😊.

[Video Tutorial Here](https://ethreesf-my.sharepoint.com/:v:/g/personal/roderick_ethree_com/EYkGMjyzYvdGjNd6SZ-agDABCZ-2CopFTBn9r_i6gbC56g)

### Docstrings

- We are also using the Sphinx extension `sphinx.ext.napoleon`, which allows Sphinx to auto-document
  ["Google-style" docstrings](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings).
- Autodoc-Pydantic: https://autodoc-pydantic.readthedocs.io/en/stable/


#### Docstring Math

To write math inside the docstring, you'll need to use the `.. math::` directive. Labels and content within the 
`.. math::` block should be indented **3 spaces** (to match exactly where the word `math` begins). 
**Be very careful with the spacing of the directive**:
- 2 periods
- 1 space
- `math`
- 2 colons (no space between `math` and the colons)

There are two ways to get $\LaTeX$ written in the docstrings to show up:

- Option 1: Declare the docstring as a "raw text" docstring by starting with an `r` before the triple quote (e.g., `r"""`, as shown below):
    :::{code-block} rest
    :caption: Escaping math in docstrings using `r"""`
    
    r"""[One sentence description.]
    
    [Additional description & examples]
    
    .. math::
       :label: [add-a-label]
      
       \examplecommand
    
       [Insert LaTeX math here, such as x \leq 100]
    """
    :::
- Option 1: Instead of `r"""`, you can escape every backslash every time you use it within the docstring (e.g., instead of `\`, use `\\`):

    :::{code-block} rest
    :caption: Escaping math in docstrings using `\\`
    
    """[One sentence description.]
    
    [Additional description & examples]
    
    .. math::
       :label: [add-a-label]
       
       \\examplecommand
       
       [Insert LaTeX math here, such as x \\leq 100]
    """
    :::


## xlwings

### Old: Excel UIs
:::{deprecated} 0.26.0

In early 2024, users noted that (a) inconsistent behavior for workbook- vs. worksheet-scoped named ranges 
(which the older UI `xlwings` implementation relied on) and (b) CSV writing from the UI timing out for 
some macOS users. 

To allow users to continue using existing UIs with `kit` v0.26.0+, a few VBA & `xlwings` code changes were made, 
which require some manual user intervention.
:::



#### Making an Older UIs Compatible with `kit` Code v0.26.0+

1. Update your `conda` environment
2. Copy the VBA modules from E3 Model Template.xlsm into your existing UI spreadsheet:
    1. `LibFileTools`
    2. `E3Tools`
    3. `xlwings`
    4. For Resolve & Recap Scenario Tools, update the VBA code in the `System` sheet (Sheet5) by copying the 
       code block below (also in `Recap-Resolve Scenario Tool.xlsm`):
       :::{code-block} vbscript
       :caption: Sheet5
        Sub Save_System()
            Application.Calculate

            RunPython "import new_modeling_toolkit.ui.scenario_tool as st; st.save_linkages_csv(model='resolve', data_folder=r'" & Sheet1.Range("DATA_FOLDER_PATH").Value2 & "')"
            RunPython "import new_modeling_toolkit.ui.scenario_tool as st; st.save_system(sheet_name=r'" & Me.Name & "', data_folder=r'" & Sheet1.Range("DATA_FOLDER_PATH").Value2 & "')"
        End Sub

        Sub Save_Attributes()
            Application.Calculate
            
            wb_path = GetThisWorkbookLocalPath(True)
            
            RunPython "import new_modeling_toolkit.ui.scenario_tool as st; import xlwings as xw; st.save_attributes_files(model='resolve', wb=xw.Book('" & wb_path & "'), data_folder=r'" & Sheet1.Range("DATA_FOLDER_PATH").Value2 & "')"
            Call Save_Linkages
        End Sub
        
        Sub Save_Linkages()
            Application.Calculate
            wb_path = GetThisWorkbookLocalPath(True)
            
            RunPython "import new_modeling_toolkit.ui.scenario_tool as st; st.save_linkages_csv(model='resolve', data_folder=r'" & Sheet1.Range("DATA_FOLDER_PATH").Value2 & "')"
        End Sub
       :::
3. Create a blank tab called `__names__` in your existing UI spreadsheet.
4. Make the following updates to the `xlwings.conf` tab (check E3 Model Template.xlsm if you need a reference):
    1. New named ranges:
        1. `__INTERPRETERPATH__`: : Assigned to the cells on `xlwings.conf` for `Interpreter_Win` and `Interpreter_Mac`
        2. `__KITPATH__`: Assign any blank cell on the `xlwings.conf` tab
        3. `__SHOWCONSOLE__` named range
    2. Use the formula `=GetThisWorkbookLocalPath(FALSE)` for all the following:
        1. `ONEDRIVE_WIN`
        2. `ONEDRIVE_MAC`
        3. `ONEDRIVE_COMMERCIAL_WIN`
        4. `ONEDRIVE_COMMERCIAL_MAC`
        5. `SHAREPOINT_WIN`
        6. `SHAREPOINT_MAC`
      :::{note}
      If `=GetThisWorkbookLocalPath` is not working, users may need to manually enter the data folder paths like before.
      :::
5. For tools (e.g., `Pathways`) that have kit as a dependency in their `pyproject.toml`:
    1. Remove xlwings as a dependency (so that you're always just inheriting the version of xlwings that kit is set up for
    2. Add [ui] to your pyproject.toml: So it should say "new-modeling-toolkit[ui] @ git+https://github.com/e3-/new-modeling-toolkit.git@... instead of "new-modeling-toolkit @ git+https://github.com/e3-/new-modeling-toolkit.git@...
6. macOS only: Use the new CLI command (i.e., in Terminal) `kit-ui connect [PATH TO SPREADSHEET]` to make sure `xlwings` 
is properly set up. This will run the `xlwings runpython install` and copy the `runTerminalCommand-0.24.0.applescript` 
to `~/Library/Application Scripts/com.microsoft.Excel/` on macOS to enable running commands in an external Terminal window.

`Optional`: Users can use the `kit-ui connect [PATH TO SPREADSHEET]` command to update the Python interpreter path 
instead of users needing to manually enter it themselves. This CLI utility relies on having the named ranges defined in Step 4. 


### New: `ExcelTemplate`

:::{versionadded} 0.26.0

As a longer-term solution to the `xlwings` UI issues, a new `ExcelTemplate` interface class was created. This new 
class allows UIs to be **programmatically** generated from the class definitions embedded in the `kit` code.
:::

For Excel-based interfaces, we have created a standard `ExcelTemplate` class to smooth out some of the rough edges 
associated with using `xlwings` to interact with spreadsheets. 

| Feature                                           | Windows | macOS | Linux |
|---------------------------------------------------|:-------:|:-----:|:-----:|
| Reading ranges                                    |    ✓    |   ✓   |   ✕   |
| Writing to ranges                                 |    ✓    |   ✓   |   ✕   |
| Call VBA macros from Python                       |    ✓    |   ✓   |   ✕   |
| Use `RunPython` to call Python functions from VBA |    ✓    |   ✓   |   ✕   |
| `xlwings vba ...` CLI commands to update workbook |    ✓    |   ✕   |   ✕   |

- On macOS, you may be prompted to allow Python to control Excel. You **must** allow this for `xlwings` to work properly:
  - Full disk access
  - 
- There is a standard "Model Template" spreadsheet in the repo. This template has:
    - New and/or updated VBA modules into the existing spreadsheet:
        * `LibFileTools`
        * `E3Tools`
        * `xlwings`
- In the standalone `xlwings` VBA module, the `XLWINGS_VERSION` has to match the pip-installed version 
(at least at the time of install). It seems like `xlwings` checks that there is an AppleScript file with the  
same version number in `~/Library/Application Scripts/com.microsoft.Excel`, which is installed when you run 
`xlwings runpython install`.
