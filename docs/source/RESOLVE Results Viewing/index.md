# RESOLVE Results Viewing


Once `Resolve` is done solving, it will save a series of CSVs that summarize the portfolio 
investment & operational decisions. These files are stored in the run's report folder, which 
is found in `./reports/resolve/[case name]/[timestamp]/`

The `Resolve` package includes a spreadsheet Results Viewer, which is powered by VBA and will load 
the data from the CSVs for viewing as formatted figures & tables. See the spreadsheet for more 
instructions.

If users pass the `--raw-results` command line argument when running `Resolve`, a CSV for every 
Pyomo Param, Var, Expression, and Constraint will be created and stored in the run's report folder. 

## Output File Structures

This section will walk you through what a typical output file structure for RESOLVE looks like 

## Raw & Summary Results 

Some files offer valuable insights compared to others, this section will look at key outputs and summary results of the run

## RESOLVE Results Viewer

This section will cover where will the end-of-the-day resolve story live 



