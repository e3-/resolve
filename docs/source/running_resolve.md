(running_resolve)=
# Running `Resolve`

## Running `Resolve` from Command Line

If you plan to run `Resolve` via a command line/terminal, use the following instructions.

1. In a command line (e.g., Command Prompt), navigate into the `./resolve/resolve` directory
2. Activate `kit` conda environment: `conda activate kit`
3. Use the command `python run_opt.py` to run a case. The `run_opt.py` script accepts four arguments/options:
    ``` 
    Usage: run_opt.py [OPTIONS] [RESOLVE_SETTINGS_NAME]
   
   ╭─ Arguments ───────────────────────────────────────────────────────────────────────────────╮
   │   resolve_settings_name      [RESOLVE_SETTINGS_NAME]  Name of a RESOLVE case (under       │
   │                                                       ./data/settings/resolve). If        │
   │                                                       `None`, will run all cases listed   │
   │                                                       in                                  │
   │                                                       ./data/settings/resolve/cases_to_r… │
   │                                                       [default: None]                     │
   ╰───────────────────────────────────────────────────────────────────────────────────────────╯
   ╭─ Options ─────────────────────────────────────────────────────────────────────────────────╮
   │ --data-folder                                            TEXT  Name of data folder, which │
   │                                                                is assumed to be in the    │
   │                                                                same folder as             │
   │                                                                `new_modeling_toolkit`     │
   │                                                                folder.                    │
   │                                                                [default: data]            │
   │ --solver-name                                            TEXT  Name of the solver to use. │
   │                                                                Currently supported        │
   │                                                                options are 'cbc', which   │
   │                                                                requires a local CBC       │
   │                                                                executable (included in    │
   │                                                                this package), or          │
   │                                                                'gurobi', which requires a │
   │                                                                local gurobi.lic file in   │
   │                                                                your computer's root       │
   │                                                                gurobi directory.          │
   │                                                                [default: cbc]             │
   │ --symbolic-solver-labels    --no-symbolic-solver-lab…          use symbolic solver labels │
   │                                                                [default:                  │
   │                                                                no-symbolic-solver-labels] │
   │ --log-json                  --no-log-json                      Serialize logging          │
   │                                                                infromation as JSON        │
   │                                                                [default: no-log-json]     │
   │ --log-level                                              TEXT  Any Python logging level:  │
   │                                                                [DEBUG, INFO, WARNING,     │
   │                                                                ERROR, CRITICAL]. Choosing │
   │                                                                DEBUG will also enable     │
   │                                                                Pyomo `tee=True` and       │
   │                                                                `symbolic_solver_labels`   │
   │                                                                options.                   │
   │                                                                [default: CRITICAL]        │
   │ --extras                                                 TEXT  Enables a RESOLVE 'extras' │
   │                                                                module, which contains     │
   │                                                                project-specific add-on    │
   │                                                                constraints.               │
   │                                                                [default: cpuc_irp]        │
   │ --raw-results               --no-raw-results                   If this option is passed,  │
   │                                                                the model will report all  │
   │                                                                Pyomo model components     │
   │                                                                directly.                  │
   │                                                                [default: no-raw-results]  │
   │ --return-cases              --no-return-cases                  Whether or not to return a │
   │                                                                list of the completed      │
   │                                                                cases when finished.       │
   │                                                                [default: no-return-cases] │
   │ --raise-on-error            --no-raise-on-error                Whether or not to raise an │
   │                                                                exception if one occurs    │
   │                                                                during running of cases.   │
   │                                                                Note that if you are       │
   │                                                                running multiple cases,    │
   │                                                                any cases subsequent to    │
   │                                                                the raised exception will  │
   │                                                                not run.                   │
   │                                                                [default: raise-on-error]  │
   │ --help                                                         Show this message and      │
   │                                                                exit.                      │
   ╰───────────────────────────────────────────────────────────────────────────────────────────╯
   ```

```{note}
Hint: If you're in your command line and unsure what arguments to pass to `run_opt.py`, use the command 
`python run_opt.py --help` to get help!
```
