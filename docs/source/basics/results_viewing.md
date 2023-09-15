(results)=
# Viewing Results

```{note}
The results viewing process has been updated significantly from v0.4.2. If you haven't updated your environment recently, 
run `pip install -U -e .` to update dependencies. 
```

## Report Folder Structure

## Spreadsheet Results Viewer & Automation

`Resolve` includes a refreshed Excel Results Viewer. The goal of the updated Results Viewer was to streamline results 
reporting formulas while maintaining key results reporting capabilities. As part of this streamlining, 
the `Portfolio Analytics` tab of previous Results Viewers has been removed, so "raw" results reported in CSV format from 
the `Resolve` code are directly calculated into various tables. The new template is also more detailed than before, 
with more granular reporting tabs.

Starting in [version tag to be added later], the Results Viewer is essentially "static", and neither VBA code nor `xlwings` 
code is embedded in the spreadsheet. Instead, the Results Viewer is used as a **_template_** that is copied and loaded with 
scenario-specific results for each case.

In addition, the Results Viewer process now integrates a PowerPoint automation process to automatically add figures 
and tables to slides from a PowerPoint template. 

Relevant Files:
- `Resolve Results Template.xlsx`
- `CPUC Template.pptx`
- `notebooks/results_viewer.py`

```{todo}
Rename template files
```

### 1. Modify the Results Template Spreadsheet

Use the Results Template spreadsheet to customize your results viewing. You can add charts, tables, etc.
Once you've finished customizing your spreadsheet, make sure you name your tables (named ranges), figures, and/or groups 
of figures (see screenshot below):

### 2. Set Up your PowerPoint Template

(pulling-results)=
### 3. Use the Jupyter Notebook to Orchestrate Results Viewer Loading

Open the `notebooks/results_viewer.py` as a Jupyter notebook. You should be able to do this by:
1. Open a terminal (e.g., Command Prompt)
2. Activating your `new-modeling-toolkit` environment 
3. Use the command `jupyter lab` to launch the JupyterLab interface 
4. From the left sidebar file explorer, navigate to `./notebooks/results_viewer.py`
5. Right-click the file and select "Open With > Jupytext Notebook" (see screenshot below):

```{image} ../_images/open-with-jupytext.png
:alt: Screenshot of how to open a `.py` file as a Jupyter Notebook
:width: 60%
:align: center
```

Work your way through the Jupyter notebook. Most of the settings you will need to change are located near the top of 
the notebook (see screenshot below). There are three sets of settings to configure:

1. Where the Results Viewer and PowerPoint slide templates are located:
   - `sharepoint_path`: Local path to SharePoint folder where your templates are stored
   - `ppt_template_path`: Relative to the `sharepoint_path` (if applicable)
   - `xlsx_template_path`: Relative to the `sharepoint_path` (if applicable)
2. Whether to create PowerPoint slides (which is relatively slow): `create_ppt`
3. Where the results are located: `results_path`
   - The recommended practice when running cases on the `ethree.cloud` cluster **is to leave them on AWS (S3)** and use 
     the S3 URI to your submitted run (e.g., `s3://e3x-cpuc-irp-data/runs/rgo-20230904.1/outputs/reports/resolve`) to retrieve
     results files directly from the cloud (rather than downloading them to your computer, SharePoint, etc.). If you are 
     trying retrieve results from an S3 URI, you will be prompted to log into AWS (using your Okta credentials).

```{image} ../_images/jupyter-results-config.png
:alt: Screenshot of how to open a `.py` file as a Jupyter Notebook
:width: 80%
:align: center
```

---

## {bdg-warning}`soon` Jupyter Results Viewer

## {bdg-warning}`soon` Viewing Results via `System` API

The long-run goal of Resolve-based models is to leverage the object-oriented underpinnings to enable more 
consistent & flexible results reporting. At this time, results can be retrieved by a savvy user from the `ResolveCase` 
and `System` instances; however, the public API for doing so is a work in progress.

## Comparing Results

:::{eval-rst}
.. raw:: html

    <div class="giscus-container">
        <script src="https://giscus.app/client.js"
            data-repo="e3-/kit"
            data-repo-id="MDEwOlJlcG9zaXRvcnkzMjkxMzIyNzQ="
            data-category="Documentation"
            data-category-id="DIC_kwDOE54o8s4CWsWE"
            data-mapping="pathname"
            data-strict="0"
            data-reactions-enabled="1"
            data-emit-metadata="0"
            data-input-position="bottom"
            data-theme="preferred_color_scheme"
            data-lang="en"
            crossorigin="anonymous"
            async>
        </script>
    </div>
