(running_resolve)=
# Running Resolve

After saving your input data & case settings (refer below to see how this should
look like) (as described in {ref}`saving-inputs`), you are now ready 
to run `Resolve`!

## Insert details on input file structure and directories and where reht are saved


## Running `Resolve` from the Scenario Tool

As in previous versions of `Resolve`, users can run cases directly from the Scenario Tool. 
Below the "Run Resolve Cases" header on the right of that tab, you'll find a green "Run Resolve Cases Locally" 
button. 
- On Windows, this will create a new command line window, and you will see `Resolve` progress. 
- On macOS, we have not yet figured out how to show the command line window as `Resolve` is running. 
  For now, we recommend macOS users run `Resolve` from Terminal themselves, as described in the next section. 

## Running `Resolve` from Command Line

If you plan to run `Resolve` via a command line/terminal, use the following instructions. 
Running `Resolve` via the command line gives you more options for how the model is run than are exposed in the 
Scenario Tool, as discussed below.

1. In a command line (e.g., Command Prompt), navigate into the `./src/resolve/resolve` directory
2. Activate `resolve-env` conda environment: `conda activate resolve-env`
3. Use the command `python run_opt.py` to run a case. The `run_opt.py` script accepts the following arguments:
- `--data-folder`: The name of your data folder (if different than the default `.\data`)
- `--solver-name`: The name of the solver to use (e.g., `gurobi`, `cplex`, `amplxpress`, `appsi_highs`)
- `--raw-results`: Save all raw Pyomo model components as CSVs (for detailed model inspection).
- `--symbolic-solver-labels`: Enable descriptive variable names in the Pyomo model formulation--helpful for debugging.

Tip: If for the installation process, you had used Pycharm or any other Python software, then the recommended
best practice is to run resolve from there after saving the ST as this avoids using macros which might cause computational
issues relating to excel based macros as these are deprecated in newer configurations. [Ritvik to rephrase\]

Examples:
- Run all cases listed in `./data/settings/resolve/cases_to_run.csv`:
  ```
  python run_opt.py 
  ```
- To run a single case called `Core_25MMT`, type the name of the case into the command line:
  ```
  python run_opt.py Core_25MMT
  ```
- Run all cases from a different data folder called `data-new` (listed in `./data-new/settings/resolve/cases_to_run.csv`):
  ```
  python run_opt.py --data-folder data-new
  ```
- Run all cases using `cplex` as your solver:
  ```
  python run_opt.py --solver-name cplex
  ```


```{note}
Hint: If you're in your command line and unsure what arguments to pass to `run_opt.py`, use the command 
`python run_opt.py --help` to get help!
```

```{admonition} Note for E3 Staff
:class: seealso

Instructions for running Resolve on `ethree.cloud` available on the [encyclopedia](https://e3-encyclopedia.readthedocs-hosted.com/en/latest/cloud/resolve.html)
```
