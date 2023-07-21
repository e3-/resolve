(running_resolve)=
# Running `Resolve`

1. In a command line, navigate into the `./new_modeling_toolkit/resolve` directory
2. Activate the `new-modeling-toolkit` conda environment: `conda activate new-modeling-toolkit`
3. Use the command `python run_opt.py` to run a case. The `run_opt.py` script accepts four arguments/options:
    ```
     Usage: run_opt.py [OPTIONS] [RESOLVE_SETTINGS_NAME]                                    

    ╭─ Arguments ──────────────────────────────────────────────────────────────────────────╮
    │   resolve_settings_name      [RESOLVE_SETTINGS_NAME]  Name of a RESOLVE case (under  │
    │                                                       ./data/settings/resolve). If   │
    │                                                       `None`, will run all cases     │
    │                                                       listed in                      │
    │                                                       ./data/settings/resolve/cases… │
    │                                                       [default: None]                │
    ╰──────────────────────────────────────────────────────────────────────────────────────╯
    ╭─ Options ────────────────────────────────────────────────────────────────────────────╮
    │ --data-folder                               TEXT  Name of data folder, which is      │
    │                                                   assumed to be in the same folder   │
    │                                                   as `new_modeling_toolkit` folder.  │
    │                                                   [default: data]                    │
    │ --solver-name                               TEXT  [default: cbc]                     │
    │ --log-level                                 TEXT  Any Python logging level: [DEBUG,  │
    │                                                   INFO, WARNING, ERROR, CRITICAL].   │
    │                                                   Choosing DEBUG will also enable    │
    │                                                   Pyomo `tee=True` and               │
    │                                                   `symbolic_solver_labels` options.  │
    │                                                   [default: INFO]                    │
    │ --extras                                    TEXT  Enables a RESOLVE 'extras' module, │
    │                                                   which contains project-specific    │
    │                                                   add-on constraints.                │
    │                                                   [default: None]                    │
    │ --raw-results           --no-raw-results          If this option is passed, the      │
    │                                                   model will report all Pyomo model  │
    │                                                   components directly.               │
    │                                                   [default: no-raw-results]          │
    │ --help                                            Show this message and exit.        │
    ╰──────────────────────────────────────────────────────────────────────────────────────╯
    ```

```{note}
Hint: If you're in your command line and unsure what arguments to pass to `run_opt.py`, use the `--help` argument!
```