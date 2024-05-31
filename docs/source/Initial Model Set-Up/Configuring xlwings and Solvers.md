# Configuring xlwings & Solvers

## xlwings 

We have seen that running resolve requires interfacing with both `excel` as well as `python` based code. xlwings is a tool that helps
in interfacing excel and python and something that is very necessary for the model to run smoothly 

More standalone information on xlwings can be found here: https://docs.xlwings.org/en/latest/

For our purposes we will focus on installing xlwings and making it work with the Resolve Scenario Tool excel workbook

On the Scenario Tool's `Cover & Configuration` tab, you will need to tell the Scenario Tool how to find your `resolve-env` 
**Python path** and the **data folder** where you want to save inputs.

```{image} _images/scenario-tool-config.png
:alt: Screenshot of user dropdown inputs to specify scenarios to be read in `Resolve` case.
:width: 60%
:align: center
```

::::{dropdown} Windows Excel
**Configure Python Path:** 
1. Open Command Prompt or PowerShell and activate the environment with the command `conda activate resolve-env`
2. Type the command `where python` to see where the `resolve-env` version of Python is stored. This should look like: 
  `C:\Users\[username]\Anaconda3\envs\resolve-env\python.exe`. Paste this path into the **Python Path** cell.
  :::{warning}
  Make sure to use a backslash `\` (and not a forward slash `/`) on Windows for the Python path. 
  :::
**Configure Data Folder Path:** 

By default, this folder is called `data` and located in the project folder next to the `scr` folder. 
For completeness, type the full path to the data folder, may look something like `~/.../resolve/data`
::::

::::{dropdown} macOS Excel
**Configure Python Path:** 
1. Open Terminal and activate the environment with the command `conda activate resolve-env`
2. {bdg-warning}`First time setup only` Run the command `xlwings runpython install`. You should see a prompt from macOS 
   asking you for permission for Terminal to automate Excel. **You must allow this.**
3. Type the command `which python` to see where the `resolve-env` version of Python is stored. This should look like: 
  `/Users/[username]/anaconda3/envs/resolve-env/bin/python`. Paste this path into the **Python Path** cell.
  :::{warning}
  Make sure to use a forward slash `/` (and not a backslash `\`) on macOS for the Python path.
  :::
**Configure Data Folder Path:** 

By default, this folder is called `data` and located in the project folder next to the `src` folder. 
For completeness, type the full path to the data folder, may look something like `~/.../resolve/data`
::::

---


## Solvers (optional) for the most part 

{bdg-info-line}`Optional`

The `resolve-env` environment comes with the open-source [`HiGHS`](https://highs.dev/) solver, which enables 
out-of-the-box solving of`Resolve` cases on any platform. 
Commercial solvers like Gurobi, IBM CPLEX, and FICO XPRESS offer additional solver features & 
typically substantially faster solve times. If you have licenses for any of these solvers, `Resolve` will work with them; 
follow the vendor installation & licensing instructions.

See [](./running_resolve.md) for instructions on how to change which solver `Resolve` uses.
