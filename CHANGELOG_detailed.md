# Detailed Changelog

This file records detailed technical notes on significant refactors and migrations.

---

## 2026-11-19 — Power-sector coefficient residuals

### Summary

Power-share-driven IO replacements used global recipe values, discarding country-specific input structure. A residual fixed in the first model year now keeps it.

### Details

- `scenario.py`: `set_power_io_changes` split into `_power_totals` (sheet x recipe, summed over exporters, cached per instance), `compute_power_residual(ind_trade)`, and the spread step. `set_io_changes` keeps the non-power rows in `_io_changes_nonpower`; `rebuild_io_changes()` re-assembles `io_changes` once the residual exists (first year).
- `initiate_modules.py`: first year, right after `Trade_model.calc_IO_coef`, computes and writes `power_io_resid` and rebuilds `io_changes`; later years read it from `model_start` and set `Scenario.power_resid` before `set_io_changes()`.
- `InputOutput.io_change`: `replace_new` rows are appended to the sparse matrix when the cell does not exist, then treated as `replace`.
- `variables.xlsx`: `power_io_resid` (REG_imp, PROD_COMM, TRAD_COMM), MIN/MAX +-Inf.
- Residual is additive with a floor of 0 on the sum; the existing 0.03-0.97 column-sum guard in `io_change` still applies.
- Test: IEA_CP 2019-2021 ran cleanly; max change of any power-sector input coefficient 2019->2020 was about 0.011.

---

## 2026-03-31 — Type 1 DYNAMIC variable migration to `self.V`

### Summary

All "Type 1" cross-year state variables were migrated from the plain Python dict `self.DYNAMIC` to the typed `variables_table` (`self.V`) via `self.V.write_var` / `self.V.read_var`. This centralises cross-year state in the validated variable store and removes the need for dict lookups.

### Variables migrated

| Old key in `self.DYNAMIC` | New variable name in `self.V` | Notes |
|---|---|---|
| `price_index` | `price_index` | |
| `investment_price_index` | `investment_price_index` | |
| `delta_price_yoy` | `delta_price_yoy` | Numerically identical to `dp_all`; written as raw numpy array |
| `normal_output` | `normal_output` | Written/read as DataFrame with `from_df=True` |
| `normal_output_growth_helper` | `normal_output_growth_helper` | Written as raw numpy array |
| `profit_rate_mean` | `profit_rate_mean` | In-place numpy modification possible (read_var returns reference) |
| `cpi` | `cpi` | |
| `labour_force` | `labour_force` | Column renamed `LF` → `labour_force` on write, back on read |
| `inc_exog` | `inc_exog` | Column renamed `dlabor_exog` → `inc_exog` on write, back on read |
| `gdp_history` | `gdp_base` | `gdp_base` was already written to `self.V`; DYNAMIC write removed and reads updated |

### Files changed

- `SourceCode/model_class.py`
- `SourceCode/initiate_modules.py`
- `SourceCode/ftt_power.py`

### Design notes

- `write_var(from_df=True)` requires the input DataFrame to have a column named **exactly** `var_name`; variables whose DataFrames used a different column name require a rename before write and a rename-back after read
- `read_var` returns a **direct reference** (no copy) to the stored numpy array, so in-place modifications (e.g. the `profit_rate_mean` first-year correction) propagate without an explicit write-back
- `delta_price_yoy` is stored as a flat numpy array; downstream code that needs a labelled DataFrame reconstructs it via `MRIO_vec_to_df_DEF(self.V.read_var('delta_price_yoy', year), 'dp')`
- `gdp_base` was already registered in `self.V` and written there alongside the old DYNAMIC write; migration simply removed the DYNAMIC write and updated all reads

---

## 2026-03-31 — 3D final demand variable migration to `self.V`

### Summary

Three 3-dimensional final demand consumption variables (`household_consumption`, `fcf_consumption`, `government_consumption`) were migrated from `self.DYNAMIC` to `self.V`. These are indexed by `[REG_imp × REG_exp × TRAD_COMM]` and hold constant-price consumption flows in thousands of USD.

### Variables migrated

| Old key in `self.DYNAMIC` | New variable name in `self.V` | Original column | Notes |
|---|---|---|---|
| `household_consumption` | `household_consumption` | `VIPA` | Stored as flat array; indexed form reconstructed on read |
| `fcf_consumption` | `fcf_consumption` | `VDFA` | Same pattern |
| `government_consumption` | `government_consumption` | `VIGA` | Index order `[REG_exp, REG_imp, TRAD_COMM]` on read to match downstream usage |

### Files changed

- `SourceCode/model_class.py`
- `SourceCode/initiate_modules.py`

### Design notes

- All three variables are stored as flat numpy arrays (163 regions × 163 regions × 120 sectors at full resolution; the sizes follow the active aggregation, e.g. 10 × 10 × 23 for IPCC R10×S23); downstream code that requires the original indexed DataFrame form uses `read_var(..., as_df=True).rename(columns={var_name: original_col}).set_index([...])`
- `EXOG_VARS.HH_BASE`, `EXOG_VARS.FCF_BASE`, and `EXOG_VARS.GOV_BASE` are set from `self.V` at the start of each year `> model_start`; for `year == model_start` they retain their original values loaded by `exog_vars.py`
- Init block (`year == model_start`) writes `year-1` values from the initial `EXOG_VARS` bases so the variable store has meaningful values from the start
- `government_consumption` is written in two code paths: the dynamic path (drops helper columns, renames VIGA) and the base-year fallback that resets `EXOG_VARS.GOV_BASE`'s index before writing

---

## 2026-03-31 — 4D sparse variable migration to `self.V` and new DataFrame store methods

### Summary

Four-dimensional variables (indexed by `[REG_imp × PROD_COMM × REG_exp × TRAD_COMM]`) cannot be stored as flat numpy arrays in the existing `variables_table` without prohibitive memory use. Two new methods were added to `variables_table` to handle sparse DataFrames, and the 4D variables were migrated from `self.DYNAMIC` (or equivalent local state) to `self.V`.

### New methods in `variables_table` (`SourceCode/variables.py`)

| Method | Behaviour |
|---|---|
| `write_var_df(var_name, year, df)` | Writes a DataFrame as parquet to `GLORIA_results/` _(Update 2026-11-02: the code writes to `Results/`, i.e. `variables_table.results_path`)_ following the `generate_var_table` naming convention; keeps the two most recent years in an in-memory cache (`df_data`); older years are evicted from memory (parquet on disk remains available) |
| `read_var_df(var_name, year)` | Serves from memory cache if available; loads from parquet on miss without re-caching |

Parquet file naming: `results_file_long_{scenario_name}_{var_name}_{year}.parquet` (in `Results/`)

### Variables migrated

| Variable | Source | Dimensions | Notes |
|---|---|---|---|
| `energy_flows` | local in `initiate_modules` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | Written once per year; read cross-year in `ftt_power.py` |
| `emission_cost_intermediates` | `self.DYNAMIC` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | Carbon tax incidence on intermediate flows |
| `emission_cost_hh` | `self.DYNAMIC` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | Carbon tax incidence on household consumption |
| `emission_cost_fcf` | `self.DYNAMIC` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | Carbon tax incidence on FCF |
| `emission_cost_gov` | `self.DYNAMIC` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | Carbon tax incidence on government consumption |
| `cbam_cost_intermediates` | `self.DYNAMIC` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | CBAM incidence on intermediate flows |
| `cbam_cost_hh` | `self.DYNAMIC` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | CBAM incidence on household consumption |
| `cbam_cost_fcf` | `self.DYNAMIC` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | CBAM incidence on FCF |
| `cbam_cost_gov` | `self.DYNAMIC` | `[REG_imp, REG_exp, PROD_COMM, TRAD_COMM]` | CBAM incidence on government consumption |
| `new_IO` | `IO_model.IND_BASE` (end-of-year snapshot) | `[REG_imp, PROD_COMM, REG_exp, TRAD_COMM]` | IO table (z_bp, output, a_bp, a_tech); written at end of year, consumed as `EXOG_VARS.IND_BASE` at start of next year |

### Files changed

- `SourceCode/variables.py`
- `SourceCode/initiate_modules.py`
- `SourceCode/model_class.py`
- `SourceCode/ftt_power.py`

> **Update 2026-11-02:** `emission_cost_hh/fcf/gov` and `cbam_cost_hh/fcf/gov` are now registered with dimensions `[REG_imp, REG_exp, TRAD_COMM]` (no `PROD_COMM`), matching what the code writes; see the 2026-11-02 entry below.

### Design notes

- DataFrame (not `scipy.sparse`) was chosen for the sparse store: easier groupby/merge/filter operations, direct parquet serialisation, and no need to manage index mappings
- `scipy.sparse` is imported in `InputOutput.py` but is not used — actual matrix conversion goes DataFrame → dense numpy via `.unstack().to_numpy()`
- `new_IO` is not year-indexed in the original code but is effectively year-indexed (written at end of year Y, read as `year-1` at start of year Y+1); migrated accordingly
- `ftt_power.py` uses `read_var_df('energy_flows', year-1)` and a read-modify-write pattern for `energy_flows` in the same year (reads, calls `.update()`, writes back)

---

## 2026-03-31 — Eliminate redundant pre-loop parquet writes for emission/cbam cost variables

### Summary

`emission_cost_intermediates/hh/fcf/gov` and `cbam_cost_intermediates/hh/fcf/gov` followed a write → internal use → write again pattern inside `initiate_modules`. The initial write (pre-loop) was immediately overwritten by the first iteration of the within-year convergence loop. The pre-loop writes were replaced with local Python dicts (`emission_cost_dfs`, `cbam_cost_dfs`), eliminating 8 unnecessary parquet writes per simulation year.

### Pattern before

1. Pre-loop: calculate tax/cbam incidence → `self.V.write_var_df('emission_cost_*', year, ...)` × 4, `self.V.write_var_df('cbam_cost_*', year, ...)` × 4
2. Pre-loop reads: `self.V.read_var_df('emission_cost_*', year)` and `self.V.read_var_df('cbam_cost_*', year)` in tax_rev, price, and HH sections
3. Iteration loop: recalculate and `self.V.write_var_df(...)` again on every iteration

### Pattern after

1. Pre-loop: calculate → store in `emission_cost_dfs` / `cbam_cost_dfs` dicts (no V write)
2. Pre-loop reads: access `emission_cost_dfs['intermediates']` etc. directly
3. Iteration loop: recalculate and `self.V.write_var_df(...)` as before (first and only write to V)

The iteration loop's `emission_cost_old` capture uses `emission_cost_dfs['intermediates']` on the first iteration and reads from `self.V` on subsequent iterations (after the loop's own write).

### Edge case

If `SWITCH_WITHIN_YEAR_LOOP = False`, the loop body never executes and `self.V` would never receive the values. A post-loop block writes the local dicts to `self.V` in this case to ensure cross-year reads remain valid.

### Files changed

- `SourceCode/initiate_modules.py`

---

## 2026-11-02 — Aggregation-independent sector roles

### Summary

Several modules used GLORIA-120 sector numbers directly (cost-curve sectors 24–26, refining 62/63/94, non-market 115–118, royalty sectors 22–40, electricity 93), and the HU_CI fork had partly replaced them with 56-sector numbers. Both are wrong for any other aggregation. Roles are now defined once in GLORIA-120 codes and mapped to the active aggregation at start-up.

### How it works (`SourceCode/exog_vars.py`)

| Item | Behaviour |
|---|---|
| `GLORIA_SECTOR_ROLES` | Module-level dict of role → GLORIA-120 sector list |
| `exog_vars.SECTOR_ROLES` | Same roles in model sector numbers, built in `__init__` |
| `gloria_sectors(ids)` | With 120 sectors returns `ids` unchanged; otherwise a model sector gets the role when **more than half** of its GLORIA sectors are in `ids` |
| `sector_concordance()` | Scans `Data/MSET_data/Country_groupings/*.xlsx` (skipping `~$` lock files) for a `product_groups` sheet with 120 rows and columns `Lfd_Nr`, `Lfd_Nr_agg`, `Agg_sector_name`, and uses the one whose (`Lfd_Nr_agg`, `Agg_sector_name`) pairs equal (`Lfd_Nr`, `Sector_names`) in sheet `P` of `Variable_list_MINDSET.xlsx` (names compared after stripping spaces) |

Start-up prints, for example: `--- Sector roles (IPCC_regions_23sectors.xlsx): cost_curve [2, 3, 4]; refining [9, 10, 16]; non_market [23]; royalty [2, 3, 4, 5, 6]; electricity [15] ---`.

### Where roles are used

| Role | Used in | Replaces |
|---|---|---|
| `cost_curve` | `model_class.py` `cost_curve_employment` | `[24, 25, 26]` / HU_CI `[]` |
| `refining` | `model_class.py` `refining_sectors` → `ener_balance` | `[62, 63, 94]` / HU_CI `[23, 24, 35]` |
| `non_market` | `initiate_modules.py` profit-rate floor exemption | `[115…118]` / HU_CI `[52, 53, 54]` |
| `royalty` | `government.py` royalty revenue | `PROD_COMM 22–40` / HU_CI `10–18` |
| `electricity` | `BTA.py` CBAM scope-2 emissions | `93` |

Scenario "ALL" expansion uses `scenario.P_IDS` (the model's sector list) instead of `np.arange(1, 121)` or `np.arange(1, 57)`.

### Design notes

- No setting is needed: the grouping workbook is found by matching sector numbers **and** names with sheet `P`. Start-up stops with `FileNotFoundError` if no workbook matches, and with `ValueError` if several match but disagree.
- A role can disappear when its GLORIA sectors are merged into a larger sector made mostly of other activities; check the printed line after changing the aggregation.
- Not yet converted: `set_power_io_changes` (ALL → 1–56) and the FTT code paths (sector 93).

---

## 2026-11-02 — `variables.xlsx` registrations and dimension corrections

### Summary

The 2026Q3–Q4 code (HU_CI fork) writes and reads variables through `self.V` that were never added to `variables.xlsx`, so the first baseline year stopped with `IndexError` in `write_var` (`save_rate_ex_windfall`). 24 variables were registered and 7 existing rows were corrected.

### Variables added (all `TYPE = FLOAT16`)

| Dimensions | Variables | Bounds |
|---|---|---|
| `REG_imp` | `save_rate_ex_windfall` | −Inf … 1 (as `save_rate`) |
| `REG_imp` | `real_income_hh`, `real_spend_hh` | −Inf … Inf |
| `REG_imp`, `PROD_COMM` | `dq_structural_change`, `dq_hh_tech_substitution`, `dq_calibration_residual`, `dq_hh_exog_fd`, `dq_hh_exog`, `dq_gov_exog_fd`, `dq_fcf_exog_fd`, `dq_supply_constraint`, `dq_supply_constraint_no_empl`, `dempl_hh_save`, `dempl_io_change`, `va_current`, `comp_current`, `tax_current`, `depr_current`, `profit_current`, `dk_exog` | −Inf … Inf |
| `REG_imp`, `TRAD_COMM`, `REG_exp` | `delta_y_save`, `gov_consumption_wo_residual` | −Inf … Inf |
| `REG_imp`, `TRAD_COMM`, `REG_exp` | `hh_ctax_rate` (`write_var_df`) | none |
| `REG_imp`, `REG_exp`, `PROD_COMM`, `TRAD_COMM` | `ctax_ratchet_diag` (`write_var_df`) | none |

Bounds are open because `write_var` now clips out-of-range values (2026Q3–Q4 change); a tight bound would silently change results.

### Dimension corrections

| Variable | Was | Now | Reason |
|---|---|---|---|
| `flow_price_impact_hh` | `REG_imp`, `PROD_COMM`, `TRAD_COMM` | `REG_imp`, `TRAD_COMM` | Code drops `PROD_COMM` (always `FD_1`) before writing |
| `emission_cost_hh/fcf/gov` | `REG_imp`, `REG_exp`, `PROD_COMM`, `TRAD_COMM` | `REG_imp`, `REG_exp`, `TRAD_COMM` | Code drops `PROD_COMM`; readers re-add it with `.assign(PROD_COMM='FD_x')` |
| `cbam_cost_hh/fcf/gov` | `REG_imp`, `REG_exp`, `PROD_COMM`, `TRAD_COMM` | `REG_imp`, `REG_exp`, `TRAD_COMM` | `PROD_COMM` holds `FD_1/3/4`, which `write_var_df` rejects as invalid sector codes once CBAM is non-zero |

Each corrected row has a note in the `Note` column with its old dimensions.

### Rules for new variables

- `write_var` / `read_var`: the name must be in sheet `vars`, otherwise `IndexError` when looking up its empty table. With `from_df=True` the DataFrame needs the dimension columns plus a column named exactly like the variable.
- `write_var_df`: the name must be registered, every listed dimension must be a column, and each dimension's values must belong to the model's lists (`REG_imp`/`REG_exp` regions, `PROD_COMM`/`TRAD_COMM` model sectors, `FD` = `FD_1`, `FD_3`, `FD_4`); extra columns are allowed.
- `PERSISTENT` is informational only; `MIN`/`MAX` are enforced by `write_var` (warn and clip).

---

## 2026-11-02 — Debug iteration file

`initiate_modules.py` writes `Temp/iter{year}-{iter}.csv` on every within-year iteration after the first. Rows are labelled `REG_imp` × `PROD_COMM`; columns are `output` (= `dq_total` before the labour-supply constraint), every component of `dq_total`, employment change, price changes (`current` = `dp_all`) and the direct price effects available at that point (`v_all`, `v_labor`, `v_dev_normal_output`, `v_costcurve`, `v_output_growth`). `v_dev_profit_rate`, `v_ctax`, `v_cbam`, `v_exog` and `v_scarcity_rent` are not written; `v_all` minus the listed effects gives their sum. A failed write prints a message instead of stopping the run.

---

## 2026-11-02 — Capital stock data correction (data only; `Data/` is git-ignored)

### Symptom

Baseline (R10×S23, empty scenario) produced zero changes from 2023 onward: within-year iterations diverged in LAC services, `dq_hh_inc` became infinite, the year ended in NaN and every later year stayed at 2022 levels.

### Chain

1. `initial_capital_stock_gloria.csv`: Brazil's capital stock was ~2,400× too large (1.95e13 thousand USD; 97 % of world capital in the file). Brazil's series comes from WIOD SEA; dividing by 2,750 (1994 cruzeiro-real → real) gives a plausible capital/output of 2.0–2.3.
2. LAC depreciation ÷ capital fell below the 0.1 % floor, so depreciation came out at ~2× LAC output; model profit rates hit the −1 clip; `profit_rate_min` (which scales with capital/output) hit its 0.95 cap.
3. The profit-rate price term raised LAC prices ~40 % in 2020 (other regions 2–4 %).
4. Capital-tax revenue grows with the change in positive profits (`government.calc_endog_spending_change`); from a near-zero base it exploded, and LAC government demand rose by 6.5e9 in 2021 (≈ 5× its budget), mostly in sector 23.
5. Calibration failed in 2020–2022 and 2023 diverged.

### Fix

In `DATA/MSET_data_original/Investment/` (source of `collapse_MRIO.py`), BRA, TUR, ROU, BIH, BGR, UKR, GHA and MWI were each multiplied by one factor (all sectors, years and the `HH` row) so that capital ÷ GLORIA gross output (2016–19 average) equals the WIOD SEA 2016 ratio `K / GO` (2010–14 average) × 1.569, the median file-to-WIOD ratio of 39 normal WIOD countries. Proxies: Croatia for BIH, Russia for UKR, the median of 40 African countries in the file for GHA and MWI. Original: `initial_capital_stock_gloria_orig.csv`; factors and method: `initial_capital_stock_gloria_rescale_note.csv`. Region capital/output after collapsing: LAC 2,078 → 3.19, EUR 8.64 → 2.58, AFR 4.06 → 3.15, EEA 4.28 → 3.82.

Sources: WIOD 2016 release, Socio-Economic Accounts and exchange rates (DataverseNL files 199095 and 199097).

---

## 2026-11-02 — Single `Results/` folder, per-scenario archives and figure folders

### Summary

The 2026Q3–Q4 code wrote some outputs to `GLORIA_results/` and archived that whole folder at the start of every run. All outputs now go to `Results/`, archives are per scenario, and the figure scripts can plot any results folder.

### Model side (`SourceCode/model_class.py`)

| Item | Behaviour |
|---|---|
| `ModelRun.RESULTS_DIR` | `"Results"`; used for `emissions_{scenario}_{year}.parquet`, `remittance_{scenario}[_{year}].parquet` and `calibration_convergence_summary_{scenario}.csv` (`results.py` FullResults path too, unused) |
| `_is_result_of_scenario(fname, scenario, var_names)` | Exact patterns: `results_file_long_{s}_{n}.(csv\|parquet)`, `results_file_long_{s}_{registered variable}_{YYYY}.parquet`, `emissions_{s}_{YYYY}.parquet`, `remittance_{s}[_{YYYY}].parquet`, `calibration_convergence_summary_{s}.csv`, `(baseline\|scenario)_figures_{s}.pdf` |
| `_archive_scenario_results()` | At run start, moves the matching files to `Results/archive_{kind}_{scenario}_{YYYYMMDD_HHMM}/`; `kind` = `calibration` if a calibration summary is among them (calibrating run), `baseline` for a forward run of `BASELINE_SCENARIO` (`empty`), else `scenario`; timestamp = newest file's modification time; `_2`, `_3`, … if the folder exists |
| `_clear_temp_iterations()` | Deletes `Temp/iter*-*.csv` at run start |
| `Residuals/` | Unchanged: `_archive_folder("Residuals")` at the start of a calibrating run |
| `_cleanup_working_parquets()` | Still not called; now points at `Results/`, and its docstring warns that it would delete the per-year files the figure scripts read |

Prefix matching would be wrong here: `cprice_disagg` is a prefix of `cprice_disagg_rr`, `_hh`, `_full`, and the variable `hh_ctax_rate` makes a `cprice_disagg` file look like scenario `cprice_disagg_hh`. Tested on these cases and with two consecutive 2019–2020 baseline runs in a throwaway copy.

### Figure scripts (`Results/*.Rmd`)

- YAML `params`: `results_dir` (both), `baseline_dir` and `scenario` (scenario figures); folders are relative to `Results/`.
- `rfiles(pattern)` replaces `list.files(pattern = ...)`: baseline figures read only baseline (`empty`) files from `results_dir`; scenario figures read baseline files from `baseline_dir` and scenario files (all non-baseline scenarios, or `scenario`) from `results_dir`.
- `str_extract(basename(filename), ...)`: the scenario and year are taken from the file name only (an archive folder name contains a timestamp that would otherwise be read as a year).
- A `knit:` function in the YAML renders into `results_dir` with output names `baseline_figures_empty.pdf` and `scenario_figures_<scenario>.pdf` (`_all` when several scenarios are plotted), so PDFs are archived together with their results.
- `scenario_figures.Rmd` table headers: the hard-coded two-scenario headers (`cprice` / `cprice_rr` under each year) are replaced by `pivot_header()`, which builds both header rows from the pivoted table's columns. With any other number of scenarios the hard-coded headers had more columns than the table (LaTeX "Extra alignment tab"), and with other names they were mislabelled.
- Fuel sectors (`fuel_of`, `fuel_detail_of`, `primary_fuel_sectors`) are built from sector names in sheet `P` of `Variable_list_MINDSET.xlsx`.

---

## 2026-11-18 — Household EV channel (petrol → electricity)

### Summary

The `EV stock shares` sheet of a scenario workbook drives a shift of household final demand from refined petroleum (sector "Refined petroleum products") to electricity, in physical (TJ) terms, and the resulting net money effect is passed into the household saving routine. Draft; compiles, scenario reader tested on `IEA_CP.xlsx`, model not run.

### Files changed

- `SourceCode/scenario.py`
- `SourceCode/ener_balance.py`
- `SourceCode/initiate_modules.py`
- `SourceCode/household.py`

### Logic

- `Scenario.set_ev_share()` (called in `__init__`, structure as `set_hh_permanent`): reads sheet `EV stock shares` (`skiprows=13`, columns `Country ISO*`, previous year, current year), `resolve_comma` / `resolve_all` on `REG_imp`; result `REG_imp | ev_share | ev_share_prev`, clipped to 0–1. Previous year is `max(YEAR-1, YEARS[0])`, so the first year has zero change. Missing sheet → empty frame → channel off. The `Sector code*` and `FD code*` columns are ignored (`FD code*` is a row counter FD_1..FD_10).
- `Energy_emissions.load_dynamic` receives `'ev_share': Scenario.ev_share`; `hh_fuel_substitution` reads it and `price_index` (year-1) from `self.common`.
- In `hh_fuel_substitution`, after household TJ is aggregated by `REG_imp` × `TRAD_COMM`:
  - `frac_switch = clip(ΔS⁺ / max(1 − S_prev, 0.05), ≤ 1)`, `ΔS⁺` = increase in share (no EV → ICE reversal).
  - `d_petrol = −road_share × (petrol TJ / price_index_petrol) × frac_switch`; `d_ely = −d_petrol / ev_efficiency` (defaults `road_share = 0.9`, `ev_efficiency = 3.0`). Sectors are found by name ("Refined petroleum", "Electric power"); an assertion requires exactly one match each.
  - `physical_value` is shifted by `d_ev` before shares, relative prices and the income/price response are computed. The existing normalisation (total TJ held constant) now targets the **post-EV** total; otherwise it would cancel the efficiency gain. `physical_value_imp` is measured against the original (pre-EV) TJ, so `VIPA_imp` contains EV shift plus substitution. Conversion to money uses the existing base-year implicit prices (kUSD/TJ), so only the electricity/petrol price ratio matters for the EV part.
- `initiate_modules.py`: `hh_fuel_substitution` is now called **before** `calc_hh_demand_change` (it only uses year-1 `HH_price` / `HH_delta_inc_rel`); its output is passed as `dy_tech` to both `calc_hh_demand_change` calls (first pass and within-year loop) and still feeds `dq_hh_tech_substitution` as before. Gating by `fuel_substitution_start` applies to the EV channel too.
- `household.py`: `calc_hh_demand_change(..., dy_tech=None)`; `real_spend = VIPA + delta_y_price + delta_y_inc + dy_exog + dy_tech` (`dy_tech` = regional sum of `VIPA_imp`). A lower net spend raises `endog_save`, which feeds `windfall_save` and the `lambda_save` re-spend.

### Notes and risks

- Including the full `VIPA_imp` (not only the EV part) in `real_spend` changes results of every run with `fuel_substitution` active, also without an EV sheet, because TJ-neutral substitution is not money-neutral. `real_spend_hh` also feeds the trailing `save_rate1/2/3` benchmark, so recalibrate and re-run the baseline before comparing.
- Pre-existing inconsistency, unchanged: the household TJ in `hh_fuel_substitution` is nominal spend / base implicit price (not deflated by the price index); the EV step deflates petrol by the petrol price index.
- Calibration may partly absorb the EV shift if `output_projection` already embeds electrification; the baseline `empty.xlsx` has no EV sheet, so the channel only acts in scenario runs.
- Not modelled: EV purchase cost (sector 14 demand), fuel-tax revenue loss, EV vs ICE mileage differences.

---
