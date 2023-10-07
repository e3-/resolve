# Comparing & Verifying Inputs

- Case settings are saved in the `./settings/resolve/` subdirectory of your `data` folder. Each set of case settings has 
  its own folder of settings files.
- All `System` data is stored in the `./interim/` subdirectory of your `data` folder. Within the `./interim/` directory, 
  you'll find subdirectories for different types of components––such as loads, resources, policies.

The fundamental design decision was that the `Resolve` data folder should be thought of as a pseudo-database, 
shared across various cases. This does come with the tradeoff that—without careful planning—you can overwrite data in your pseudo-database. 

1. Save different `data` folders and compare the `[data folder]/interim` subfolders (using some text copmarison tool like `Kdiff`)
   - From the Scenario Tool, you can save your data to different folders. This specified on the `Cover & Configuration` tab
2. Compare `System` instance JSONs (also using some text copmarison tool like `Kdiff`)
3. Use `xltrail` to compare Scenario Tools

::::{dropdown} Comparing `data` Folders using `kdiff` or PyCharm
Since the `./data/` folders just contain text (mainly `csv`) files, you can use any "diff" tool to compare these folders. 
Many people at E3 use [`kdiff3`](https://download.kde.org/stable/kdiff3/?C=M;O=D), though other tools like PyCharm work. 
In general, you should see highlights of additions, deletions, or modifications at a line level within `csv` files.

:::{image} _images/diffing-folders.png
:alt: Example of how PyCharm shows `diffs` (text file differences) between two data files. 
:width: 80%
:align: center
:::

::::


::::{dropdown} Comparing `System` Instance `json` Files
Finally, you can compare the `json` file reported after the `Resolve` model instance is constructed. This is saved in 
`./reports/resolve/[case name]/[timestamp]/`. `json` files are nested text files. This `json` file gives you the best 
look at the data as `Resolve` understands it, as it includes all the data from the `System` instance that is being 
read into `Resolve` (i.e., after scenario tag filtering and timeseries resampling). 

::::