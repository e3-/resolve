# Development Roadmap

```{note}
Describe future updates.
```

# Changelog

```{include} ../../CHANGELOG.md
```

# Old (Manual) Changelog

## [v.0.1.0](https://github.com/e3-/kit/releases/tag/v0.1.0)

- Initial core (Resolve) feature-complete version

## [v0.2.0](https://github.com/e3-/kit/releases/tag/v0.2.0)

- ERA5 data pulling and timeseries regressions
- Add optional unit conversion
- Additional documentation

## [v0.3.0](https://github.com/e3-/kit/releases/tag/v0.3.0)

### Breaking Changes

- Refactored `Policy` components (requires updates to relevant `attributes.csv` and linkage input files)
- Refactored discounting of modeled years, resulting in changes to attribute names (
  see [#520](https://github.com/e3-/kit/pull/520)

### Other Changes

- Unit commitment constraints
- Add optional input data scenario tagging
- Optional feature of `attributes.csv` to point to another CSV path to read in for timeseries data
- New Scenario Tool, with CPUC IRP Preferred System Plan data inputs

### Bug Fixes

- Fix input data scenario tagging
- Speed up results reporting via `export_results.py`

## v0.4.0 (May 2022)

- New Results Viewers

## Summer 2022

- Initial Python Pathways implementation
- Initial Recap3 implementation
- Refactoring to split `common` module into separate `core` (data-handling) and `system` modules

