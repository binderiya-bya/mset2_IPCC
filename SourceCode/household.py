# -*- coding: utf-8 -*-
"""
Created on Thu Jun 29 16:54:26 2023

@author: wb582890
"""

import pandas as pd
import numpy as np
import time

from SourceCode.InputOutput import IO
from SourceCode.scenario import scenario
from SourceCode.utils import MRIO_df_to_vec, MRIO_vec_to_df

class household:
    """
    This class collects the variables and parameters related to households and calculates household prices,and changes in prices and income.

    Parameters
    ----------
    EXOG_VARS : class
        Class for exogenous variables.
    
    Methods
    -----------
    build_hh_price
        Calculates household prices.
        
    calc_hh_demand_change
        Calculates changes in household prices and income.

    """  
    def __init__(self, EXOG_VARS):
        
        self.HH = EXOG_VARS.HH_BASE

        self.multiyear = EXOG_VARS.MULTIYEAR
        
        self.cons_sec = [
            "Food_beverages_tobacco","Clothing_footwear", "Housing",
            "House_furnishing", "Medical_health", "Transport_communication",
            "Recreation", "Education", "Other"]
        self.COU_ID = EXOG_VARS.COU_ID

        self.R_list = EXOG_VARS.R_list
        self.P_list = EXOG_VARS.P_list
        self.R = EXOG_VARS.R

        # set up params
        self.params = EXOG_VARS.PARAMETERS[['REG_imp','PROD_COMM','consumption_Price_ln','consumption_Income_ln']].copy()
        self.params = self.params.rename(columns={'PROD_COMM':'TRAD_COMM'})
        self.params.columns = [x.replace("consumption_","") for x in self.params.columns]

        self.comp_shares = EXOG_VARS.COMPENSATION_SHARE.copy()

    def load_dynamic(self, vars_):
        self.common = {}
        for k,v in vars_.items():
            self.common[k] = v

    def build_hh_price(self, dp_pre_trade, emission_cost_hh, price_index, prev=None, year=None):
        # emission cost hh is: REG_imp | PROD_COMM == FD_1 | TRAD_COMM | REG_exp | emission_cost (nominal USDk)
        # price index is: REG_imp | PROD_COMM | price_index

        # ? HH price considers dp_pre_trade, but also includes 
        # ? direct tax on households, which is based on the emission cost, 
        # ? emission cost however is in nominal terms, so we need to consider how the price_index changes
          
        # we start with pre-trade price impacts
        dp_pre_trade = dp_pre_trade.set_index(["REG_imp","TRAD_COMM","REG_exp"])
        
        HH_elas = self.HH.reset_index().merge(dp_pre_trade, how='left', on=['REG_imp','REG_exp','TRAD_COMM'])
        # HH_elas = HH_elas.astype({'TRAD_COMM':'str'})

        # we then allocate emission costs
        emission_costs = emission_cost_hh.copy()
        emission_costs = emission_costs.groupby(['REG_imp','REG_exp','TRAD_COMM']).agg({'emission_cost':'sum'}).reset_index()
        
        HH_elas = HH_elas.merge(emission_costs, how='left', on=['REG_imp','REG_exp','TRAD_COMM']).fillna(0)

        # and nominal price indices
        price_index_ = price_index.copy()
        # .astype({'PROD_COMM':'str'})
        HH_elas = HH_elas.merge(price_index_.rename(columns={'REG_imp':'REG_exp','PROD_COMM':'TRAD_COMM'}), how='left', on=['REG_exp','TRAD_COMM'])
        # then calculate tax price hike
        HH_elas['VIPA_nominal'] = HH_elas['VIPA'] * HH_elas['price_index']

        HH_elas['delta_tax_hh'] = np.nan_to_num(HH_elas['emission_cost'] / HH_elas['VIPA_nominal'], nan=0)

        if prev is not None:
            hh_ctax_rate_prev = prev.copy()
            hh_ctax_rate_prev = hh_ctax_rate_prev.rename(columns={'delta_tax_hh':'delta_tax_hh_prev'})

            HH_elas = HH_elas.merge(hh_ctax_rate_prev, how='left', on=['REG_imp','REG_exp','TRAD_COMM'])
            HH_elas['delta_tax_hh'] = HH_elas['delta_tax_hh'] - HH_elas['delta_tax_hh_prev']
            HH_elas = HH_elas.drop(columns=['delta_tax_hh_prev'])

        # limit to max 0-500%
        # HH_elas['delta_tax_hh'] = HH_elas['delta_tax_hh'].clip(lower=-5.0, upper=5.0)
        _emission_cost_totals = HH_elas.groupby(['REG_imp','TRAD_COMM'])['emission_cost'].transform('sum')
        _value_totals = HH_elas.groupby(['REG_imp','TRAD_COMM'])['VIPA_nominal'].transform('sum')
        _emission_cost_share = np.nan_to_num(HH_elas['emission_cost'] / _emission_cost_totals, nan=0)
        _value_share = np.nan_to_num(HH_elas['VIPA_nominal'] / _value_totals, nan=0)
        _out_of_range = HH_elas.loc[(HH_elas['delta_tax_hh'] > 3.0) | (HH_elas['delta_tax_hh'] < -3.0)]
        for _idx, _row in _out_of_range.iterrows():
            print(f"WARNING: delta_tax_hh out of range [-3.0, 3.0]: REG_imp={_row['REG_imp']} REG_exp={_row['REG_exp']} TRAD_COMM={_row['TRAD_COMM']} delta_tax_hh={_row['delta_tax_hh']} "
                  f"emission_cost_share_of_country_product={_emission_cost_share[_idx]:.2%} value_share_of_country_product={_value_share[_idx]:.2%}")

        # ? this comes on top of other price effects! 
        # ? so dp_pre_trade + delta_tax_hh together gives consumer price
        # ? we get the weighted average price change for consumers across all
        # import pdb; pdb.set_trace()

        HH_ctax = HH_elas[['REG_imp','REG_exp','TRAD_COMM','delta_tax_hh']].copy()

        HH_elas['delta_p_avg'] = HH_elas['VIPA_nominal'] / HH_elas.groupby(['REG_imp','TRAD_COMM'])['VIPA_nominal'].transform('sum')
        HH_elas['delta_p_avg'] = HH_elas['delta_p_avg'] * (HH_elas['delta_tax_hh'] + HH_elas['delta_p'])

        VIPA_prod = HH_elas.groupby(["REG_imp","TRAD_COMM"]).agg({'VIPA':'sum','delta_p_avg':'sum'}).reset_index()
        VIPA_prod = VIPA_prod.rename(columns={"VIPA": "VIPA_prod"})

        HH_price = VIPA_prod[['REG_imp','TRAD_COMM','delta_p_avg','VIPA_prod']]

        #? output is: HH_price: REG_imp | TRAD_COMM | delta_p_avg | VIPA_prod

        return HH_price, HH_ctax
        
    def calc_hh_demand_change(self, HH_price_, recyc_rev, inc_exog, inc_exog_prev, dlabor_inc_nat=None, cpi_d_wage=None, dy_tech=None, year=None):
        # dy_tech: REG_imp | REG_exp | TRAD_COMM | VIPA_imp, net money effect of household fuel substitution (counted in real_spend)
        #? inc_exog is: REG_imp | dlabor_exog

        HH_price = HH_price_.copy()
        HH_price = HH_price.merge(self.params, how='left')
        HH_price = HH_price[['REG_imp','TRAD_COMM','VIPA_prod','delta_p_avg','Price_ln','Income_ln']]

        # ? dlabor is nominal compensation change. dlabor_cpi is the slice of it that comes
        # ? purely from CPI-indexation of wages (income.py wage_CPI_ln_L1 term) -- kept out of
        # ? delta_inc here and deflated separately below (by cpi_d_wage, the same inflation
        # ? measure that generated it) instead of by quasi_CPI, which is a narrower
        # ? household-basket price measure that can diverge sharply from headline CPI under a
        # ? carbon tax and otherwise leaves a nominal-inflation residual in delta_inc_rel.
        if type(dlabor_inc_nat) == pd.DataFrame:
            HH_price = HH_price.merge(dlabor_inc_nat["dlabor"], how='left', on=["REG_imp"])
            HH_price = HH_price.merge(dlabor_inc_nat["dlabor_cpi"], how='left', on=["REG_imp"])
            HH_price = HH_price.merge(recyc_rev["recyc_inc_base"], how='left', on=["REG_imp"])
            HH_price = HH_price.merge(inc_exog_prev.rename(columns={'dlabor_exog':'prev_dlabor_exog'}), how='left', on=['REG_imp'])
            HH_price = HH_price.merge(inc_exog, how='left', on=['REG_imp'])
            HH_price = HH_price.fillna(0)
            HH_price["recyc_inc_base"] = HH_price["recyc_inc_base"] + (HH_price["dlabor"] - HH_price["dlabor_cpi"]) + HH_price['dlabor_exog'] - HH_price["prev_dlabor_exog"]
            HH_price = HH_price.drop(columns=["dlabor","dlabor_exog","prev_dlabor_exog"])
        else:
            HH_price = HH_price.merge(recyc_rev["recyc_inc_base"], how='left', on=["REG_imp"])
            HH_price = HH_price.merge(inc_exog_prev.rename(columns={'dlabor_exog':'prev_dlabor_exog'}), how='left', on=['REG_imp'])
            HH_price = HH_price.merge(inc_exog, how='left', on=['REG_imp'])
            HH_price = HH_price.fillna(0)
            HH_price["recyc_inc_base"] = HH_price["recyc_inc_base"] + HH_price['dlabor_exog'] - HH_price["prev_dlabor_exog"]
            HH_price = HH_price.drop(columns=["dlabor_exog","prev_dlabor_exog"])
            HH_price["dlabor_cpi"] = 0.0

        if type(cpi_d_wage) == pd.DataFrame:
            HH_price = HH_price.merge(cpi_d_wage.rename(columns={'cpi_d':'cpi_d_wage'}), how='left', on=['REG_imp'])
        else:
            HH_price["cpi_d_wage"] = 0.0
        HH_price["cpi_d_wage"] = HH_price["cpi_d_wage"].fillna(0)

        HH_price = HH_price.rename(columns={'recyc_inc_base':'delta_inc'}).fillna(0)

        # if year == 2021:
            # import pdb; pdb.set_trace()

        # ? ok, so here recyc_inv is the total nominal(!) income growth; we need to know what was income before
        # ? not CONSUMPTION <> INCOME, so cannot just sum(VIPA)

        empl_base = self.common['employment_base'].merge(self.common['wage_base'])
        empl_base['compensation'] = empl_base['employment_base'] * empl_base['wage']
        empl_base = empl_base.groupby(['REG_imp']).agg({'compensation':'sum'}).reset_index()

        HH_price = HH_price.merge(empl_base, how='left', on=['REG_imp'])
        HH_price = HH_price.merge(self.common['cpi'], how='left', on=['REG_imp'])
        
        # ? income change; but delta_inc is nominal; VIPA_nat is real
        # ? real income change needs to consider price levels
        HH_price['quasi_CPI'] = (HH_price['VIPA_prod'] / HH_price.groupby(['REG_imp'])['VIPA_prod'].transform('sum')) * HH_price['delta_p_avg']
        HH_price['quasi_CPI'] = HH_price.groupby(['REG_imp'])['quasi_CPI'].transform('sum')
        HH_price = HH_price.merge(self.comp_shares, how='left', on=['REG_imp'])
        # ? cpi is a cumulative index (base 1), quasi_CPI is this year's proportional
        # ? change only; combine them multiplicatively (cpi_prev*(1+quasi_CPI)), not
        # ? additively, else quasi_CPI is washed out once cpi has compounded away from 1
        delta_inc_rel_other = (HH_price["delta_inc"] / (HH_price['cpi'] * (1 + HH_price['quasi_CPI']))) / ((HH_price["compensation"]/HH_price['share_compensation_in_gross_disposable_income']) / (HH_price['cpi']))
        # ? CPI-indexed wage slice: a wage rise that exactly tracks inflation leaves REAL wages
        # ? unchanged, i.e. should contribute ZERO to delta_inc_rel (confirmed: TJK's
        # ? wage_CPI_ln_L1 = 1.0, full 1:1 indexation, for every sector). dlabor_cpi alone
        # ? deflated by (1+cpi_d_wage) is NOT zero -- it reproduces ~cpi_d_wage, since it's
        # ? missing the "just keeping pace with inflation" baseline (compensation*cpi_d_wage)
        # ? that has to be netted out first. Only the gap between the two (zero under full
        # ? indexation, negative under partial indexation, i.e. CPI_ln_L1 < 1) is real.
        delta_inc_rel_cpi = (HH_price["dlabor_cpi"] - HH_price["compensation"] * HH_price['cpi_d_wage']) / ((1 + HH_price['cpi_d_wage']) * (HH_price["compensation"]/HH_price['share_compensation_in_gross_disposable_income']))
        HH_price["delta_inc_rel"] = delta_inc_rel_other + delta_inc_rel_cpi
        # apply elasticities
        HH_price["VIPA_inc_eff"] = HH_price['VIPA_prod'] * HH_price["delta_inc_rel"] * HH_price["Income_ln"]
        HH_price["VIPA_op_eff"] = HH_price['VIPA_prod'] * HH_price["delta_p_avg"] * HH_price["Price_ln"]

        HH_price_store = HH_price.copy()
        self.dHH_delta_inc_rel = HH_price_store[['REG_imp','delta_inc_rel']].drop_duplicates(subset=['REG_imp'])
        HH_price = HH_price[['REG_imp','TRAD_COMM','VIPA_inc_eff','VIPA_op_eff','VIPA_prod']].copy()

        # so this is real change
        
        # calculation of VIPA after price change
        dHH = self.HH.reset_index("REG_exp", drop=False)
        dHH = dHH.merge(HH_price, how='left', on=["REG_imp","TRAD_COMM"])

        # Compute new demands assuming constant product and origin country structure
        dHH["delta_y_price"] = dHH["VIPA_op_eff"] * dHH["VIPA"] / dHH["VIPA_prod"]
        dHH["delta_y_inc"] = dHH["VIPA_inc_eff"] * dHH["VIPA"] / dHH["VIPA_prod"]
        
        # add exog
        hh_exog = self.common['hh_exog'].copy().rename(columns={'dy':'dy_exog'})
        hh_exog['TRAD_COMM'] = hh_exog['TRAD_COMM'].astype('int16')
        dHH = dHH.merge(hh_exog, how='left', on=['REG_imp','TRAD_COMM','REG_exp'])

        # TODO need to consider save_rate; need new total income and new total consumption
        dcalc = HH_price_store.copy().groupby(['REG_imp']).agg({'delta_inc':'mean','compensation':'mean','cpi':'mean','quasi_CPI':'mean','dlabor_cpi':'mean'}).reset_index()
        # ? this is a LEVEL deflation (nominal income -> base-year real terms via the single
        # ? cpi*(1+quasi_CPI) price level), not the growth-rate netting used in delta_inc_rel
        # ? above -- no cpi-cancellation bug here, so just add dlabor_cpi back into the nominal
        # ? total (delta_inc excludes it) and deflate everything the same way as before the fix
        dcalc['real_income'] = (dcalc["delta_inc"] + dcalc["dlabor_cpi"] + dcalc["compensation"]) / (dcalc['cpi'] * (1 + dcalc['quasi_CPI']))
        dcalc = dcalc.groupby(['REG_imp']).agg({'real_income':'sum'}).reset_index()
        dcalc = dcalc.merge(dHH.groupby(['REG_imp']).agg({'VIPA':'sum','delta_y_price':'sum','delta_y_inc':'sum','dy_exog':'sum'}).reset_index(), how='left', on=['REG_imp'])
        # ? household fuel substitution (incl. EV petrol->electricity): TJ-neutral substitution is not
        # ? money-neutral, and the EV shift cuts total TJ (~3x efficiency), so net spend changes and flows into endog_save
        # ? -> windfall_save -> partial re-spend (lambda_save) like every other spend change
        if dy_tech is not None and len(dy_tech) > 0:
            tech_net = dy_tech.groupby('REG_imp')['VIPA_imp'].sum().rename('dy_tech').reset_index()
            dcalc = dcalc.merge(tech_net, how='left', on='REG_imp')
            dcalc['dy_tech'] = dcalc['dy_tech'].fillna(0.0)
        else:
            dcalc['dy_tech'] = 0.0
        dcalc['real_spend'] = dcalc['VIPA'] + dcalc['delta_y_price'] + dcalc['delta_y_inc'] + dcalc['dy_exog'] + dcalc['dy_tech']
        dcalc['endog_save'] = 1 - dcalc['real_spend']/dcalc['real_income']

        # ! persisted so the trailing save-rate benchmark (save_rate1/2/3) can be built
        # ! from the exact same income/spend definition as endog_save, instead of the
        # ! compensation-only proxy computed in model_class.py
        self.dHH_real_income_diag = dcalc[['REG_imp','real_income']].rename(columns={'real_income':'real_income_hh'})
        self.dHH_real_spend_diag = dcalc[['REG_imp','real_spend']].rename(columns={'real_spend':'real_spend_hh'})

        # ? save rate is calculate from last 3 period
        save_rate = self.common['save_rate1'].rename(columns={'save_rate':'save_rate1'})\
            .merge(self.common['save_rate2'].rename(columns={'save_rate':'save_rate2'}), how='left', on='REG_imp')\
                .merge(self.common['save_rate3'].rename(columns={'save_rate':'save_rate3'}), how='left', on='REG_imp')
        save_rate['save_rate'] = (save_rate['save_rate1'] + save_rate['save_rate2'] + save_rate['save_rate3']) / 3.0
        save_rate = save_rate[['REG_imp','save_rate']].copy()

        dcalc = dcalc[['REG_imp','endog_save','real_income']].merge(save_rate, how='left', on='REG_imp')
        dcalc['windfall_save'] = (dcalc['endog_save'] - dcalc['save_rate']) # as percentage of real income
        dcalc['windfall_dissave'] = dcalc['windfall_save']
        dcalc.loc[dcalc['windfall_save']<0, 'windfall_save'] = 0.0
        dcalc.loc[dcalc['windfall_dissave']>0, 'windfall_dissave'] = 0.0

        # TODO specify better lambda_save = 0.1
        # TODO I think overspending doesn't reduce stuff here
        lambda_save = 0.15
        lambda_dissave = 0.45
        dcalc['windfall_spend'] = dcalc['windfall_save'] * lambda_save + dcalc['windfall_dissave'] * lambda_dissave
        dcalc = dcalc[['REG_imp','windfall_spend']].copy()

        HH_price_store = HH_price_store.merge(dcalc, how='left', on='REG_imp')
        HH_price_store['VIPA_save_eff'] = HH_price_store['VIPA_prod'] * HH_price_store['windfall_spend'] * HH_price_store['Income_ln']
        HH_price_store = HH_price_store[['REG_imp','TRAD_COMM','VIPA_inc_eff','VIPA_op_eff','VIPA_save_eff','VIPA_prod']].copy()

        dHH = self.HH.reset_index("REG_exp", drop=False)
        dHH = dHH.merge(HH_price_store, how='left', on=["REG_imp","TRAD_COMM"])

        # Compute new demands assuming constant product and origin country structure
        dHH["delta_y_price"] = dHH["VIPA_op_eff"] * dHH["VIPA"] / dHH["VIPA_prod"]
        dHH["delta_y_inc"] = dHH["VIPA_inc_eff"] * dHH["VIPA"] / dHH["VIPA_prod"]
        dHH["delta_y_save"] = dHH["VIPA_save_eff"].astype("float64") * dHH["VIPA"] / dHH["VIPA_prod"]
        
        dHH = dHH.set_index(['REG_imp', 'REG_exp', 'TRAD_COMM'])
        
        # TODO return savings
        self.dHH_price = dHH.loc[:, ["delta_y_price"]]
        self.dHH_inc = dHH.loc[:, ["delta_y_inc"]]
        self.dHH_save = dHH.loc[:, ["delta_y_save"]]

        return self.dHH_price, self.dHH_inc, self.dHH_save, self.dHH_delta_inc_rel, self.dHH_real_income_diag, self.dHH_real_spend_diag
    
