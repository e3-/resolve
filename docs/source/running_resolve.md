(running_resolve)=
# Running `Resolve`

## Running `Resolve` from the Scenario Tool

## Running `Resolve` from Command Line

If you plan to run `Resolve` via a command line/terminal, use the following instructions. 
Running `Resolve` via the command line gives you more options for how the model is run, as discussed below.

1. In a command line (e.g., Command Prompt), navigate into the `./resolve/resolve` directory
2. Activate `kit` conda environment: `conda activate kit`
3. Use the command `python run_opt.py` to run a case. The `run_opt.py` script accepts the following arguments:
- `--data-folder`: The name of your data folder (if different than the default `.\data`)
- `--solver-name`: The name of the solver to use
- `--log-level`: Controls how many log messages you see as `Resolve` runs
- `--raw-results`: Save all raw Pyomo model components as CSVs (for detailed model inspection).
- `--symbolic-solver-labels`: To enable descriptive variable names in the Pyomo model formulation--helpful for debugging.

```{note}
Hint: If you're in your command line and unsure what arguments to pass to `run_opt.py`, use the command 
`python run_opt.py --help` to get help!
```
