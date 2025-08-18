## 3.5.2 (2025-08-15)

### Fix

- don't model PRM and ERM in production simulation (#1306)

## 3.5.1 (2025-08-15)

### Fix

- remove reports-test folder from public release (#1304)

## 3.5.0 (2025-08-15)

### Feat

- data for training (#1300)

## 3.4.1 (2025-08-13)

### Fix

- construct hybrid vintages (#1303)

## 3.4.0 (2025-08-13)

### Feat

- representative day sampling (#1279)

## 3.3.2 (2025-08-12)

### Fix

- Add hybrid solar and wind resource groups to profile rescaling (#1302)

## 3.3.1 (2025-08-12)

### Fix

- reserve warning (#1299)

## 3.3.0 (2025-08-10)

### Feat

- allow contributions to AES policies from thermal resources with eligible candidate fuels (#1296)

## 3.2.0 (2025-08-06)

### Feat

- tx path groups (#1298)

## 3.1.0 (2025-08-04)

### Feat

- relax required attributes on non-operational groups (#1295)
- Make bump version script (#1294)

## 3.0.0 (2025-07-29)

### Feat

- Establish RESOLVE 3.0 branch as resolve/main (#1287 (#1293)

## 0.27.0 (2025-07-28)

### BREAKING CHANGE

- Establish RESOLVE 3.0 branch as resolve/main (#1287)

### Feat

- Allow daily energy budget for shed DR ERM dispatch (#1278)
- allow weather year selection in UI (#1276)
- enable UC and max call limits for shed DR under ERM (#1274)
- CaisoTxConstraint slack and Synchronous Condenser load results reporting (#1272)
- move ERM rules from operations to investment  (#1269)
- synchronous condenser (#1268)
- Add TxPath and generic Asset contributions to ERM policy (#1250)
- add hybrid storage constraints (#1244)
- integer build results reporting (#1245)
- incremental resource contribution to reserves (#1237)
- create Energy Reserve Margin Policy class (#1229)
- hourly dispatch charts notebook (#1233)
- ui-tweaks and fuels optimization to refactor/main (#1225)
- RESOLVE temporal updates (#973)

### Fix

- typo in output expression within reserve.py (#1285)
- skip maintain reliability constraint before build year (#1284)
- create copy of incremental requirement hourly load scalar (#1281)
- set asset potential slack equal to zero if build year =/ modeled year (#1277)
- change order of annual summary columns for CAISO Tx Constraints (#1275)
- policy slack typo (#1260)
- restrict asset selected capacity to zero if build year is not one of the modeled years (#1259)
- correct multiple issues that came up in HECO ERM testing (#1251)
- downsample ts attributes and relative policy targets (#1246)
- electricity product validator in system creation (#1242)
- hard-coded row offset in excel export system (#1240)

### Refactor

- move Pyomo rules onto `kit` `Component` classes (#956)
- RESOLVE Model Formulation Subclasses ALT  (#950)

## 0.26.2 (2025-06-18)

### Fix

- Update bump-version.yml (#1271)
- Update token to GITHUB_TOKEN (#1255)

## 0.26.1 (2025-06-05)

### Fix

- Update bump-version.yml
- update bump-version.yml with GITHUB_TOKEN (#1243)
- Made a small change to Kit Quick Start Guide to test ReadTheDocs Build (#1224)

## 0.26.0 (2024-06-03)

### Feat

- Improved `xlwings` handling (#1016)

## 0.25.0 (2024-05-17)

### Feat

- **resolve**: Hourly CES accounting based on # of hours where eligible demand is 100% met with eligible generation. (#1038)

## 0.24.1 (2024-04-19)

### Refactor

- **recap**: improve structure and flow of RECAP code (#1007)

## 0.24.0 (2024-04-17)

### Feat

- **pathways**: pathways updates (#1005)

## 0.23.2 (2024-04-16)

### Fix

- **ui**: macOS Scenario Tool timeout on `wb.names` (#1008)

## 0.23.1 (2024-04-13)

### Fix

- Remove missing/broken property `opt_annual_energy_value_dollars_per_yr`

## 0.23.0 (2024-04-11)

### Feat

- NYSERDA changes (#987)

## 0.22.1 (2024-03-25)

### Fix

- **cli**: Fix CLI for Windows vs. macOS

## 0.22.0 (2024-03-15)

### Feat

- **resolve**: CPUC IRP pt. 3 fixes & hourly CES (#975)

## 0.21.0 (2024-03-01)

### Feat

- multi-unit, time-varying FOR forced outage simulation (#954)

## 0.20.1 (2024-02-29)

### Fix

- (recap) renewables upsampling bug (#969)

## 0.20.0 (2024-02-27)

### Feat

- **recap**: lolh objective (#967)

## 0.19.3 (2024-02-20)

### Fix

- small bug fixes (#959)

## 0.19.2 (2024-02-20)

### Fix

- Production Simulation (#948)

## 0.19.1 (2024-02-02)

### Refactor

- Update syntax to pydantic v2 (#940)

## 0.19.0 (2024-01-31)

### Feat

- fractional energy budgets merge (#949)

## 0.18.0 (2024-01-17)

### Feat

- Resolve production simulation (#928)

## 0.17.3 (2024-01-09)

### Fix

- **recap**: load bug fix (#939)

## 0.17.2 (2023-12-30)

### Refactor

- Reorganize kit into sectoral sub-modules (#934)

## 0.17.1 (2023-12-29)

### Fix

- Doe UI fix (#891)

## 0.17.0 (2023-12-22)

### Feat

- **recap**: change charging efficiency attribute to timeseries (#905)

## 0.16.0 (2023-12-22)

### Feat

- **recap**: lunch talk fixes (#902)

## 0.15.1 (2023-12-06)

### Fix

- **ui**: Fix simultaneous flow saving (#922)

## 0.15.0 (2023-12-04)

### Feat

- **recap**: timeseries call limits & shed dr heuristic update (#907)

## 0.14.9 (2023-12-04)

### Fix

- **recap**: speed ups and timing updates (#908)

## 0.14.8 (2023-11-27)

### Fix

- **resolve**: Various CPUC IRP-related fixes (#892)

## 0.14.7 (2023-10-10)

### Fix

- **ui**: Add unit_commiment etc attributes for ShedDr and FlexLoad in the UI (#887)

## 0.14.6 (2023-10-05)

### Fix

- shed dr heuristic update (#885)

## 0.14.5 (2023-10-03)

### Fix

- max call duration fix (#884)

## 0.14.4 (2023-09-26)

### Fix

- shed dr bug fix (#883)

## 0.14.3 (2023-09-22)

### Fix

- recap/adj fix (#877)

## 0.14.2 (2023-09-19)

### Fix

- UI bug fix (#878)

## 0.14.1 (2023-09-18)

### Fix

- adding xlwings.conf tab to UI template (#876)

## 0.14.0 (2023-09-13)

### Feat

- **recap**: UI updates (#799)

## 0.13.0 (2023-09-12)

### Feat

- Recap/feat print duals (#824)

## 0.12.1 (2023-09-11)

### Fix

- Recap/update shed dr flex (#817)

## 0.12.0 (2023-09-11)

### Feat

- **system, resolve, viz**: I've made a lot of changes & fixes... (#806)

## 0.11.2 (2023-09-01)

### Fix

- avoid Gurobi pool call when running heuristic only dispatch (#815)

## 0.11.1 (2023-08-23)

### Fix

- **ci**: use explicit "latest" tag on main

## 0.11.0 (2023-08-23)

### Feat

- **recap**: results reporting + pcap reliability setting + other small features (#812)

## 0.10.1 (2023-08-21)

### Fix

- remove obsolete workflow files

## 0.10.0 (2023-08-16)

### Feat

- Recap/hybrid linkage (#775)

## 0.9.2 (2023-08-15)

### Fix

- no_positive_net_load_periods (#810)

## 0.9.1 (2023-08-15)

### Fix

- Recap/bugfix untuned dispatch results (#809)

## 0.9.0 (2023-08-04)

### Feat

- Adding functionality to create and scale pools (#803)

## 0.8.1 (2023-08-02)

### Fix

- Recap/benchmarking (#798)

## 0.8.0 (2023-07-19)

### Feat

- **resolve**: RESOLVE Electrofuels Optimization (#735)

## 0.7.0 (2023-07-11)

### Feat

- **recap**: modular unit tests (#766)

## 0.6.0 (2023-06-06)

### Feat

- **resolve-extras**: Constrain paired discharging in ERM (#764)

## 0.5.0 (2023-06-05)

### Feat

- **ui, core, system**: Make Scenario Tool more flexible and start merging `common` and `common_v2` (#740)

## 0.4.3 (2023-05-28)

### Refactor

- Refactor optimization as blocks and re-implement `Recap` heuristic dispatch (#731)

## 0.4.2 (2023-01-06)

## 0.4.0 (2022-11-23)

## v0.3.2 (2022-05-31)

## v0.3.1 (2022-05-11)

## v0.3.0 (2022-04-26)

## v0.2.0 (2022-02-20)

## v0.1.0 (2022-01-05)
