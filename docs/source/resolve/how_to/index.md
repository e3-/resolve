---
tocdepth: 3
---

# How-To Guide

```{toctree}
:hidden:

scenario_tool
results_viewing
examples
customization
```

## FAQs

### How do I run `Resolve` from the command line?

1. In a command line, navigate into the `./new_modeling_toolkit/resolve` directory
2. Activate `kit` conda environment: `conda activate kit`
3. Use the command `python run_opt.py` to run a case. The `run_opt.py` script accepts four arguments/options:
    ```
     Usage: run_opt.py [OPTIONS] [Resolve_SETTINGS_NAME]                                    

    ╭─ Arguments ──────────────────────────────────────────────────────────────────────────╮
    │   resolve_settings_name      [Resolve_SETTINGS_NAME]  Name of a Resolve case (under  │
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
    │ --solver-name                               TEXT  [default: HiGHS]                   │
    │ --log-level                                 TEXT  Any Python logging level: [DEBUG,  │
    │                                                   INFO, WARNING, ERROR, CRITICAL].   │
    │                                                   Choosing DEBUG will also enable    │
    │                                                   Pyomo `tee=True` and               │
    │                                                   `symbolic_solver_labels` options.  │
    │                                                   [default: INFO]                    │
    │ --extras                                    TEXT  Enables a Resolve 'extras' module, │
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

### How do I create a new resource?

### How do I create an electrolytic fuel?

### How do I parametrize flexible load resource shifting constraints?

.

