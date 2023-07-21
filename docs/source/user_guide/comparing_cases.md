# Comparing Cases & Systems

## Comparing Cases

## Comparing Systems

The fundamental design decision was that the `Resolve` data folder should be thought of as a pseudo-database, 
shared across various cases. This does come with the tradeoff that—without careful planning—you can overwrite data in your pseudo-database. 

1. Save different `data` folders and compare the `[data folder]/interim` subfolders (using some text copmarison tool like `Kdiff`)
   - From the Scenario Tool, you can save your data to different folders. This specified on the `Cover & Configuration` tab
2. Compare `System` instance JSONs (also using some text copmarison tool like `Kdiff`)
3. Use `xltrail` to compare Scenario Tools