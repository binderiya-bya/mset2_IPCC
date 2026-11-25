# Changelog


The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


---

## [Unreleased]

### 2026-11-24 — Fuel substitution: full change now reaches the IO coefficients _[Prepared by Claude]_

#### Fixed

* `calc_fuel_substitution`: each supplier's share of a fuel change was divided by the whole fuel's use, so a fuel received only the sum of its squared supplier/product shares of the intended change. Every supplier and product within a fuel now moves by the fuel's own percentage change, and a sector's fuel total is conserved. Results change for all fuels in industry; recalibrate, and review energy elasticities tuned before this fix. Model not re-run.

### 2026-11-20 — Household residential channel: heating fuels ↔ electricity _[Prepared by Claude]_

Scenario-driven shift of household energy use between heating fuels and electricity. Households only (no services). **Draft: compiles, reader and shift tested on `IEA_CP.xlsx` and the 20 Nov results; model not run.**

#### Added

* Scenario sheet `Buildings electricity shares` (electricity share of buildings energy, 0–1, by region and year) is read by `Scenario.set_resid_ely_share()`. A missing sheet switches the channel off.
* `Energy_emissions.resid_heat_shift()`, called in `hh_fuel_substitution` after the EV step and before the price/income substitution. The pool is household coal, lignite, gas, coke, refined petroleum not used by cars, and electricity net of EV electricity. Heating fuels are replaced pro rata by electricity (`heat_efficiency` = 3: a heat pump uses 1/3 of the energy of a boiler, so 1 TJ of fuel is replaced by 1/3 TJ of electricity and total household energy falls).
* Default (`resid_level = False`): the sheet's change is applied to the model's own share, `(1 − target) = (1 − model share) × (1 − sheet_t) / (1 − sheet_t−1)`. `resid_level = True` sets the share to the sheet value.

#### Changed

* `set_ev_share()` also passes the first-year EV share (`ev_share_base`), used to separate car fuel and EV electricity from the residential pool.

#### Known issues

* The sheet level does not match the model's household energy in 2019 (the model has no household biomass among its energy carriers): with `resid_level = True` household electricity falls 77% in AFR, 54% in LAC and 44% in EEA in the first year.
* `heat_efficiency` and `resid_level` are code defaults, not settings.
* Recalibrate before use.

### 2026-11-19 — Power-sector coefficient residuals _[Prepared by Claude]_

#### Added

* The electricity sector's input structure is driven by the exogenous `Power generation shares` sheet and the global recipe in `power_generation_IO.csv`. Local structure differs from the global recipe, so the first model year now stores a **coefficient residual** = observed (`ind_trade`) − share-implied, both summed over exporters, per `REG_imp` × `PROD_COMM` × `TRAD_COMM`. New variable `power_io_resid` (registered in `variables.xlsx`, written to `Results/` as parquet).
* In every later year the coefficient total for non-fuel rows is `max(share-implied + residual, 0)`; in the first year this equals the observed structure, so there is no jump.
* Fuel rows (inputs in the `cost_curve` and `refining` sector roles) are scaled by ratio instead: `observed × share-implied(t) / share-implied(first year)`, capped at 10×. The additive residual drove fuel coefficients to zero while the technology still had a sizeable share (the recipe level is about twice the observed one for coal and gas, e.g. AJN coal row hit 0 by ~2032, NAM by 2025). Rows with no usable first-year ratio (observed or share-implied ~0) fall back to the additive residual, with a warning.

#### Changed

* The total is spread across exporters by the existing `z_bp` shares, so the import structure is preserved.
* Inputs with no existing supply structure (new technology input, or all flows dead) are allocated to `REG_exp = REG_imp` and a warning is printed. New row type `replace_new` makes `InputOutput.io_change` create the flow if it is missing from the sparse matrix (before, such replacements were silently dropped).

### 2026-11-19 — Energy products removed from calibration _[Prepared by Claude]_

#### Changed

* New sector role `calib_exclude` (`exog_vars.py`, GLORIA 24–27, 62, 63, 93, 94: hard coal, lignite, petroleum extraction, gas extraction, coke oven products, refined petroleum, electricity, gas distribution). These sectors are no longer fitted to `output_projection`.
* Calibration loop (`model_class.py`): excluded cells (role `calib_exclude`, plus the cost-curve sectors when `cost_curves_run = True`) get no output target **and** no final-demand residual; their output follows the energy balance, cost curves and the intermediate demand of the calibrated sectors. Before, masked cost-curve sectors were targeted at "zero output change from the residual", which put offsetting residuals on fuels.
* `InputOutput.calc_fd_vec` takes `free=` (boolean vector) and solves only on the remaining rows/columns.
* Convergence metrics (`check_country`, output-weighted sector error, summary CSV) use the projected output of the calibrated cells only.

#### To do after this change

* Re-run calibration and baseline (`s_base.ini`, `CALIBRATING = True`, then `False`); existing `Residuals/residuals_{year}.pkl` still contain energy residuals.

### 2026-11-19 — `IEA_CP.xlsx` scenario data _[Prepared by Claude]_

Data only, no code change.

#### Changed

* `Inv_renew List`: Nuclear is mapped to `Nuclear` (was `Other`), so nuclear generation takes the `Nuclear` column of `power_generation_IO.csv` and nuclear investment the `Nuclear` column of `Inv_renewables.csv`. Bio stays `Other` (no such column in `power_generation_IO.csv`).
* `Power investment`: all year values multiplied by 1,000 (million USD → thousand USD, the model unit).

#### Added

* `Carbon tax`: IEA GEC Model 2025 Current Policies CO2 prices on the electricity sector (15), all fuels, linear from 0 in 2019 to the full value in 2025 and flat to 2050. Country prices are weighted by the country's share of the region's 2019 power-sector CO2: NAM 3.17, EAS 13.80, EUR 66.41, AJN 1.39 USD/tCO2 (USD 2024, not deflated).

#### Known issues

* `Power investment` is still **added** to the model's own electricity investment (`dk_exog` on top of `dk_base`), it does not replace it.

### 2026-11-18 — Household EV channel: petrol → electricity _[Prepared by Claude]_

Scenario-driven shift of household demand from refined petroleum to electricity as the EV stock share rises. **Draft, not yet run end-to-end.**

#### Added

* Scenario sheet `EV stock shares` (EV share of the car fleet, 0–1, by region and year) is read by `Scenario.set_ev_share()`. A missing sheet switches the channel off.
* `hh_fuel_substitution` first moves car km from refined petroleum to electricity according to the *change* in EV share (same km demand; EV uses 1/3 of the energy), then applies the existing price/income substitution. Volumes use the fixed base-year implicit prices.

#### Changed

* The net money effect of the household fuel substitution now enters `real_spend`, so a fuel saving flows through `endog_save` → windfall saving / partial re-spend like other spending changes. **This also changes results of runs without an EV sheet slightly (carrier prices per TJ differ); recalibrate and re-run the baseline.**

#### Known issues

* `road_share` (0.9) and `ev_efficiency` (3.0) are code defaults, not settings.
* EV purchase costs (transport equipment demand) and lost fuel-tax revenue are not modelled.
* The `FD code*` column of the sheet is a row counter and is ignored.

### 2026-11-02 — mset2_IPCC: 10 IPCC regions × 23 sectors _[Prepared by Claude]_

Merged the 2026-11-01 mset2 working-tree changes onto the HU_CI fork (`4087203`) and fixed what blocked the 23-sector baseline.

#### Added

* Aggregation-independent sector roles (`exog_vars.py`): `GLORIA_SECTOR_ROLES` defines cost-curve (24–26), refining (62, 63, 94), non-market (115–118), royalty (22–40) and electricity (93) sectors in GLORIA-120 codes. `gloria_sectors()` / `sector_concordance()` map them to the model's sectors through the `product_groups` sheet of whichever workbook in `Data/MSET_data/Country_groupings/` matches sheet `P` of `Variable_list_MINDSET.xlsx`; a model sector takes a role when more than half of its GLORIA sectors have it. The mapping is printed at start-up. IPCC R10×S23: cost_curve [2, 3, 4], refining [9, 10, 16], non_market [23], royalty [2–6], electricity [15].
* Debug output `Temp/iter{year}-{iter}.csv`: rows labelled `REG_imp` × `PROD_COMM`; all components of `dq_total` added (government, investment, calibration residual, structural change, supply constraints, exogenous demand, technology substitution); a failed write no longer stops the run.
* `console_color()` / `console_title()` helpers in `utils.py` (no-op outside Windows).

#### Changed

* Hard-coded GLORIA-120 / 56-sector lists replaced by sector roles: `cost_curve_employment` and `refining_sectors` (`model_class.py`), royalty sectors (`government.py`), profit-rate floor exemption (`initiate_modules.py`; was the TJK-temporary `[52, 53, 54]`), CBAM scope-2 electricity sector (`BTA.py`; was 93).
* Scenario "ALL" sector expansion uses the model's sector list instead of 1–120 / 1–56 (`scenario.py`, `BTA.py`), except in `set_power_io_changes` (see Known issues).
* `.ini` files: added `remittance_channel = False` and `cost_curves_run = True` (both required by the code); residuals path uses `/`.
* Paths built with `os.path.join` (FTT settings and utilities, `Temp/` debug files); `MINDSET_dynamic_run.py` changes to its own folder; FTT model imported only when `ftt_run = True`; `results.py` `IO_PATH` default without trailing separator.
* Unused GLORIA-120 `CRITICALITY` table no longer built (`InputOutput.py`).
* All outputs go to `Results/`: per-year emissions, calibration summary (now `calibration_convergence_summary_{scenario}.csv`) and remittance files moved from `GLORIA_results/`, which is no longer created.
* Archiving: at the start of a run, only the previous files of the same scenario are moved to `Results/archive_{calibration|baseline|scenario}_{scenario}_{YYYYMMDD_HHMM}/` (`calibration` = calibrating run, `baseline` = forward run of `empty`, `scenario` = others; timestamp = when they were produced; exact file-name matching so overlapping scenario names are not mixed); other scenarios stay in `Results/`. `Temp/iter*.csv` debug files are cleared at the start of every run.
* Figure scripts (`baseline_figures.Rmd`, `scenario_figures.Rmd`): YAML `params` choose the results folder (`results_dir`; scenario figures also `baseline_dir`, `scenario`); data is read from that folder and the PDF (`baseline_figures_empty.pdf`, `scenario_figures_<scenario>.pdf`) is written into it. Fuel sectors are identified by name from sheet `P` instead of GLORIA-120 codes, and filename parsing uses only the file name. Table headers in `scenario_figures.Rmd` are built from the data (`pivot_header()`), so any number of scenarios and any scenario names work.
* `.gitignore`: `.DS_Store`, `GLORIA_results/`.

#### Fixed

* `initiate_modules.py` did not parse: restored the truncated last line of the debug `DataFrame` call; rewrote a nested-quote f-string that needs Python ≥ 3.12.
* `variables.xlsx`: registered 24 variables that the 2026Q3–Q4 code reads or writes (`save_rate_ex_windfall`, `real_income_hh`, `real_spend_hh`, `delta_y_save`, nine `dq_*` components, `dempl_hh_save`, `dempl_io_change`, `va/comp/tax/depr/profit_current`, `dk_exog`, `gov_consumption_wo_residual`, `hh_ctax_rate`, `ctax_ratchet_diag`). Dimensions corrected to match what the code writes: `flow_price_impact_hh` → (`REG_imp`, `TRAD_COMM`); `emission_cost_*` and `cbam_cost_*` for hh / fcf / gov → (`REG_imp`, `REG_exp`, `TRAD_COMM`). See `CHANGELOG_detailed.md`.

#### Data (not tracked — `Data/` is git-ignored)

* `initial_capital_stock_gloria.csv`: Brazil's capital stock was about 2,400× too large (97 % of world capital stock; likely the 1994 cruzeiro-real conversion in the WIOD-sourced series). Through depreciation and the profit-rate price term this pushed LAC prices up ~40 % in 2020, exploded LAC government demand in 2021 and produced NaN / frozen output from 2023. BRA, TUR, ROU, BIH, BGR, UKR, GHA and MWI were rescaled in `DATA/MSET_data_original/Investment/` so that capital ÷ gross output matches WIOD SEA 2016 (× 1.57 file-to-WIOD calibration; proxies: HRV for BIH, RUS for UKR, African peer median for GHA and MWI), then re-collapsed to R10×S23. Original kept as `initial_capital_stock_gloria_orig.csv`; factors in `initial_capital_stock_gloria_rescale_note.csv`.
* `parameters.csv` restored to 10 regions × 23 sectors (a 120-sector version had overwritten it).


### 2026-10-30 — 2026Q3–Q4 modifications from the HU_CI fork (commit `4087203`) _[summarised by Claude]_

By Bence Kiss-Dobronyi, with contributions from Binderiya and Aron Hartvig.

#### Added

* Remittance channel (`remittance_channel` setting): bilateral base flows and remittances as % of GDP from a `remittances` sheet, added to exogenous household income; per-year parquet outputs aggregated after the run.
* Exogenous prices: cost-shock `Type = exog` sets a sector's price change to the scenario value (endogenous effects removed); `exog-cprice` keeps carbon-tax pass-through.
* Power-sector pathways: scenario sheets "Power investment" and "Power generation shares" (`set_ely_investment`, `set_power_io_changes`); zero shares are kept so technologies leaving the mix zero their input coefficients; replacements are spread across exporters by base trade shares.
* Calibration diagnostics: `GLORIA_results/calibration_convergence_summary.csv`; previous year's residuals used on `error_revert`; `Residuals/` and `GLORIA_results/` archived at the start of a calibrating run.
* `cost_curves_run` switch; `fuel_substitution_start` setting (default `model_start + 1`).
* `employment.adjust_labor_productivity()`.

#### Changed

* Carbon tax: emission-cost ratchet (applied cost can rise by at most 2× the flow's nominal value per year) replaces the fixed cap; year-on-year differencing of revenues and costs in real terms; household carbon-tax rate differenced year on year; emission factors clipped to 0–10; out-of-range rates reported instead of clipped.
* Household income: wage growth split into real and CPI-indexed parts (`wage_real`, `glabor_cpi`), with the indexed part deflated separately; `cpi` and `quasi_CPI` combined multiplicatively; saving benchmark built from real income and spending; windfall dissaving added (`lambda_save` 0.15, `lambda_dissave` 0.45; previously 0.1).
* Household fuel substitution driven by real income growth and a share-weighted basket price; fuels below 1 % share ignored.
* IO coefficient changes: blank scenario years no longer zero coefficients; `rel` applied before `replace` in each cell; consistent dtypes after ALL expansion; lines with zero base spread equally.
* Government: royalties allowed for aggregated sectors; consumption tracked without the calibration residual (`gov_consumption_wo_residual`); emission-cost share cap removed.
* Output decline limited per year instead of hard-zeroing negative output; price change capped at +200 %.
* Variable validation warns and clips instead of stopping in the debugger; `Log/` created only when something is written.

### Earlier unreleased changes (before 2026-10-30)

#### Added

* `scenario_figures.Rmd` to results, which produces standard charts for scenarios
* added compensation share (which is `compensation/gross disposable income`) to avoid inflating income effects, this needs to be added to the `VARIABLES_list.xlsx` and to `GLORIA_template\modelinputdata\compensation_share.csv`, format for the file is below:

| REG_imp | share_compensation_in_gross_disposable_income |
|---------|-----------------------------------------------|
| SEP     | 0.580471579                                   |
| AFR     | 0.375162795                                   |

#### Fixed

* Migrated all Type 1 cross-year state variables (`price_index`, `investment_price_index`, `delta_price_yoy`, `normal_output`, `normal_output_growth_helper`, `profit_rate_mean`, `cpi`, `labour_force`, `inc_exog`, `gdp_history`) from `self.DYNAMIC` dict to `self.V` (`variables_table`); see `CHANGELOG_detailed.md` for details. _[Prepared by Claude Code]_
* Migrated 3D final demand variables (`household_consumption`, `fcf_consumption`, `government_consumption`) from `self.DYNAMIC` to `self.V`; see `CHANGELOG_detailed.md` for details. _[Prepared by Claude Code]_
* Added `write_var_df` / `read_var_df` methods to `variables_table` for sparse parquet-backed 4D DataFrame storage; migrated `energy_flows`, `emission_cost_*`, `cbam_cost_*`, and `new_IO` from `self.DYNAMIC` to `self.V`; see `CHANGELOG_detailed.md` for details. _[Prepared by Claude Code]_
* Eliminated 8 redundant pre-loop parquet writes per year for emission/cbam cost variables by replacing the pre-loop `write_var_df` calls with local dicts (`emission_cost_dfs`, `cbam_cost_dfs`); see `CHANGELOG_detailed.md` for details. _[Prepared by Claude Code]_
* cleaned up code a bit (BTA.py, employment.py, exog_vars.py, scenario.py, tax_rev.py)
* making sure that sectors that go zero production, don't become zombie sectors in the next period (i.e., there variables are zeroed out)
* corrections in ener_balance


## [v0.1.1-alpha] - 2026-03-30

Latest status: running with IPCC regions and custom parameters; baseline is stable up to 2045; cprice scenario is running up to 2045.

### Added

#### Energy

* Cost curves approach have been added for main fuel types (24,25,26,27) -- note there is no data yet for natural gas fuel curves; cost curves determine price and input use (labour and intermediate goods used for production); cost curve sectors are excluded from calibration
* Refining sectors have been set not to have energy efficiency and/or fuel substitution
* Fuel substitution is set to maintain fixed ratio between extraction and "refining" sectors (24-62, 26-63, 27-94), price change (used as a basis for substitution) is weighted average of refining and extraction sector
* Constant fuel consumption for sectors with zero parameters, i.e. if specified parameters are zero than the sector won't have efficiency and/or substitution effects
* Lignite (25) is split from coal as it has different cost curve and different refining structures
* No own substitution, i.e. while the extraction sectors can adjust their use of other energy (i.e. mining use of petrol) they won't substitute to themselves, that's kept constant
* note that `cost_curve` price impacts are being dampened for stability (see `initiate_modules.py` L1247)

#### Household

* "Rebound-effect" added, i.e., endogenous savings feed back to consumption; if endogenous savings are above normal savings rate (defined as average historical for now, but dynamic is implemented, not used) then consumption increases by a factor (see `lambda_save` parameter in household.py)

#### Employment

* Labour constraint calculation has been revised; the new calculation first calculates any losses proportional to initial employment that are coming from a shrinking labour force; then new employment demand is added; new employment is then allocated based on sectoral growth

#### Price formulation

* New calculation of target minimum profit rate; the minimum profit rate such as
```
['profit_rate_min'] = ['interest_rate'] * (1 + ['depreciation_rate'] * ['capital_stock']/['output']) / (1 + ['interest_rate'])
```

#### Technical

* Variable table is the primary location for storing dynamic variables and for exporting results; us the `self.V.write_var` and `self.V.read_var` functions; the variable table includes validation for accepted values
* Variable table writes variables into two formats, for 1D and 2D we use CSV, while for 3D and 4D we use __parquet__, parquet can be read with python or R (use the __arrow__ package in R, the __pyarrow__ in python)
* `WRITE_AT_END` flag has been added, which allows results to be only written at the end of the run cycle (i.e. last year of the simulation)
* calibration method in `calc_fd_vec` has been changed from __L-BFGS__ type minimization to `lsq_linear` based solution; higher efficiency

### Fixed
* 47b8fea13bdaebeb399780d2bf8a58085ba6e8b7
    * correcting current price GDP calculation
    * correcting IO change mechanics
* d12123848c4cc514033ccca81f52aa8880dba631, 29070fa06957cb928dc8a42ffb07671bab91abe4, f5b494677a1fdb8a34fd989c50393d1cc6fe0aa7
    * energy balance / fuel substitution corrections
* 29070fa06957cb928dc8a42ffb07671bab91abe4, 7ceac5acfb049d4227b2199dcb2426826f90442f
    * ctax calculation corrections

---

<!-- Links -->
[Unreleased]: https://github.com/cpmodel/MINDSET_dynamic
[0.1.1-alpha]: https://github.com/cpmodel/MINDSET_dynamic/releases/tag/v0.1.1-alpha