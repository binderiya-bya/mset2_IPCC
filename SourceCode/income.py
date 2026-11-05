# -*- coding: utf-8 -*-
"""
Created on Mon Jul 24 09:59:11 2023

@author: wb582890
"""

import pandas as pd
import numpy as np
from SourceCode.utils import MRIO_vec_to_df, MRIO_df_to_vec

class income:
    """
    This class collects the variables and parameters related to income and calculates wage and labour compensation,
    and changes in labour compensation, and household and non-residential energy flows.

    Parameters
    ----------
    EXOG_VARS : class
        Class for exogenous variables.
    Prod_cost : class
        Class for production costs.
    
    Methods
    -----------
    calc_wage
        Calculates wages econometrically or based on from labour compensation.
    recalc_labor_comp_delta
        Re-calculates labour compensation change.
    collect_ener_flow
        Collects energy flows.
    collect_ener_flow_hh
        Collects household energy flows.
    calc_labor_comp_change
        Calculates labour compensation change from employment changes and the MRIO.
    calc_labor_iter_cond
        Iterations for labour compensation.
    """ 
    
    def __init__(self, EXOG_VARS, Prod_cost):
        self.REGIONS = EXOG_VARS.R
        self.REGIONS_list = EXOG_VARS.R['Region_acronyms'].to_list()
        self.PRODUCTS = EXOG_VARS.P
        self.ENERGY = EXOG_VARS.E
        self.ENERGY_list = self.ENERGY['Lfd_Nr'].to_list()
        self.R_list = EXOG_VARS.R_list
        self.P_list = EXOG_VARS.P_list

        self.MIN_WAGE = EXOG_VARS.MINIMUM_WAGE
        
        self.labor_comp = Prod_cost.labor_comp

        # set up params
        load_param = lambda var_: MRIO_df_to_vec(EXOG_VARS.PARAMETERS,'REG_imp','PROD_COMM', var_ ,EXOG_VARS.R_list,EXOG_VARS.P_list)

        self.params = {}
        self.params['PROD_ln_L1'] = load_param('wage_PROD_ln_L1')
        self.params['CPI_ln_L1'] = load_param('wage_CPI_ln_L1')
        # Estimated per percentage point of unemployment; the model's unemployment rate is a fraction, hence * 100.
        # Stability bounds are applied to parameters.csv by DATA/bound_parameters.py.
        self.params['UNEMP_ln_L1'] = load_param('wage_UNEMP_ln_L1') * 100
        self.params['W_avg_ln_L1'] = load_param("wage_W_avg_ln_L1")

    def load_dynamic(self, vars_):
        self.common = {}
        for k,v in vars_.items():
            self.common[k] = v
        
    def calc_wage(self, econometrics=False):
        # empl_base: REG_imp | PROD_COMM | employment_base
        # labor_comp: REG_imp | PROD_COMM | labor
        if econometrics:
            # start with the wage dataframe
            unemployment_d = self.common['unemployment_rate'].merge(self.common['unemployment_rate_prev'].rename(columns={'unemployment_rate':'unemployment_rate_prev'}), how='left', on='REG_imp')
            unemployment_d['unemp_d'] = unemployment_d['unemployment_rate'] - unemployment_d['unemployment_rate_prev']
            unemployment_d = unemployment_d[['REG_imp','unemp_d']].copy()

            cpi_d = self.common['cpi'].merge(self.common['cpi_prev'].rename(columns={'cpi':'cpi_prev'}), how='left', on=['REG_imp'])
            cpi_d['cpi_d'] = cpi_d['cpi'] / cpi_d['cpi_prev'] - 1
            cpi_d = cpi_d[['REG_imp','cpi_d']].copy()
            # ? exposed so household.py can deflate the CPI-indexed wage slice by the same
            # ? inflation measure that generated it (see wage_CPI_ln_L1 term below)
            self.cpi_d = cpi_d.copy()

            wage_new = self.common['wage'].merge(cpi_d, how='left', on=['REG_imp']).merge(unemployment_d, how='left', on=['REG_imp'])
            cpi_vector = MRIO_df_to_vec(wage_new, 'REG_imp','PROD_COMM','cpi_d',self.R_list,self.P_list)
            wage_vector = MRIO_df_to_vec(wage_new, 'REG_imp','PROD_COMM','wage',self.R_list,self.P_list)
            unemp_vector = MRIO_df_to_vec(wage_new, 'REG_imp','PROD_COMM','unemp_d',self.R_list,self.P_list)

            def _finalize_wage(new_wage_vec):
                # limit change to 25%
                new_wage_vec = new_wage_vec.copy()
                new_wage_vec[new_wage_vec > 1.25] = 1.25
                new_wage_vec[new_wage_vec < 0.75] = 0.75

                new_wage_vec = new_wage_vec * wage_vector

                wage_df = MRIO_vec_to_df(new_wage_vec, 'wage', len(self.P_list), self.REGIONS)\
                    .rename(columns={'target-sector':'PROD_COMM','target-country-iso3':'REG_imp'}).drop(columns=['target-country'])

                # ! set wage minimums, if wage is below minimal wage, set it to minimal; if wage WAS already below minimum, set it to
                # ! initial value
                # MIN_WAGE is: REG_imp | annual_value_USD
                min_wage = self.common['wage'].merge(self.MIN_WAGE, how='left', on='REG_imp')
                min_wage['annual_value_USD'] = min_wage['annual_value_USD'] / 1000
                min_wage['annual_value_USD'] = min_wage.apply(lambda x: x['annual_value_USD'] if x['wage'] > x['annual_value_USD'] else x['wage'], axis=1)
                min_wage = min_wage.drop(columns=['wage'])

                wage_df = wage_df.merge(min_wage, how='left', on=['REG_imp','PROD_COMM'])
                wage_df['wage'] = wage_df.apply(lambda x: x['annual_value_USD'] if x['wage'] < x['annual_value_USD'] else x['wage'], axis=1)
                wage_df = wage_df.drop(columns=['annual_value_USD'])
                return wage_df

            new_wage = ((self.common['d_productivity'] * self.params['PROD_ln_L1'] + cpi_vector * self.params['CPI_ln_L1'] + unemp_vector * self.params['UNEMP_ln_L1']) + 1)
            self.wage = _finalize_wage(new_wage)

            # ? counterfactual wage excluding the CPI-indexation term (wage_CPI_ln_L1); used to
            # ? isolate how much of nominal wage growth is pure inflation catch-up vs. real
            # ? (productivity/unemployment-driven) growth. See household.py calc_hh_demand_change.
            new_wage_real = ((self.common['d_productivity'] * self.params['PROD_ln_L1'] + unemp_vector * self.params['UNEMP_ln_L1']) + 1)
            self.wage_real = _finalize_wage(new_wage_real)
        else:
            wage = self.labor_comp.reset_index().merge(self.common['employment_base'], how='left', on=['REG_imp','PROD_COMM'])
            wage['wage'] = np.nan_to_num(wage['labor'] / wage['employment_base'], posinf=0, neginf=0)
            wage = wage.drop(columns=['labor','employment_base'])
            self.wage = wage
            # ? no CPI-indexation term outside the econometric wage path (e.g. model_start year)
            self.wage_real = wage.copy()
            self.cpi_d = pd.DataFrame({'REG_imp': self.REGIONS_list, 'cpi_d': 0.0})

    def recalc_labor_comp_delta(self):
        wage = self.common['employment_base'].merge(self.wage, how='left', on=['REG_imp','PROD_COMM'])
        wage['glabor'] = wage['employment_base'] * wage['wage']

        wage = wage.merge(self.labor_comp.reset_index(), how='left', on=['REG_imp','PROD_COMM'])
        wage['glabor'] = wage['glabor'] - wage['labor']

        # ? real (non-CPI-indexed) counterfactual, computed the same way with wage_real
        wage_real = self.common['employment_base'].merge(self.wage_real, how='left', on=['REG_imp','PROD_COMM'])
        wage_real['glabor_real'] = wage_real['employment_base'] * wage_real['wage']
        wage_real = wage_real.merge(self.labor_comp.reset_index(), how='left', on=['REG_imp','PROD_COMM'])
        wage_real['glabor_real'] = wage_real['glabor_real'] - wage_real['labor']

        wage = wage.merge(wage_real[['REG_imp','PROD_COMM','glabor_real']], how='left', on=['REG_imp','PROD_COMM'])
        # ? slice of glabor attributable purely to CPI indexation of wages
        wage['glabor_cpi'] = wage['glabor'] - wage['glabor_real']

        # REG_imp | PROD_COMM | glabor | glabor_cpi
        return wage[['REG_imp','PROD_COMM','glabor','glabor_cpi']].copy()
        
    def collect_ener_flow(self, ind_trade, tax_cou, tax_rate):

        ener_flow = ind_trade.loc[pd.IndexSlice[:, :, :, self.ENERGY_list], :]
        ener_flow = ener_flow.sort_values(["REG_imp","PROD_COMM","TRAD_COMM","REG_exp"])
        ener_flow_idx = ener_flow.index
        
        ener_flow = ener_flow.merge(self.output, how="left", on=["REG_imp","PROD_COMM"])
        ener_flow["z_bp_ener"] = ener_flow["IO_coef_trade"] * ener_flow["output"]
        ener_flow = ener_flow.set_index(ener_flow_idx)
        
        self.ener_flow = pd.DataFrame(ener_flow["z_bp_ener"])
        
        return self.ener_flow
        
    def collect_ener_flow_hh(self, HH_module, tax_cou, tax_rate_hh):
        HH_iter = HH_module.HH.loc[:,:,self.ENERGY_list].merge(
            HH_module.dHH_price, how="left", on=["REG_imp","REG_exp","TRAD_COMM"])
        HH_iter = HH_iter.merge(HH_module.dHH_inc, how="left",
                                on=["REG_imp","REG_exp","TRAD_COMM"])
        HH_iter["VIPA"] = HH_iter["VIPA"] + HH_iter["delta_y_price"] + HH_iter["delta_y_inc"]
        self.HH_iter = HH_iter.loc[:,"VIPA"]
        
        return self.HH_iter
        
    def calc_labor_comp_change(self, dempl_total):
        dempl_total_df = MRIO_vec_to_df(dempl_total, 'dempl_total', len(self.PRODUCTS), self.REGIONS)\
            .rename(columns={'target-country-iso3':'REG_imp','target-sector':'PROD_COMM'})
        dlabor_sec = dempl_total_df.merge(self.wage, how='left', on=['REG_imp','PROD_COMM'])

        dlabor_sec["dlabor"] = dlabor_sec["dempl_total"] * dlabor_sec['wage']
        
        self.dlabor_sec = dlabor_sec[["REG_imp","PROD_COMM","dlabor"]]
        
        return self.dlabor_sec
        
    def calc_labor_iter_cond(self, dlabor_sec, dlabor_nat):
        # Iter_comment:
        # Collect additional labor income
        labor_nat = dlabor_sec.groupby(["REG_imp"])["dlabor"].sum()
        # ? CPI-indexed slice of dlabor, carried alongside so household.py can deflate it
        # ? separately (see calc_hh_demand_change)
        if "dlabor_cpi" in dlabor_sec.columns:
            labor_nat_cpi = dlabor_sec.groupby(["REG_imp"])["dlabor_cpi"].sum()
        else:
            labor_nat_cpi = labor_nat * 0.0

        if type(dlabor_nat) != pd.DataFrame:
            dlabor_nat = pd.DataFrame(labor_nat)
            dlabor_nat.loc[:, "dlabor_before"] = 0
            dlabor_nat["dlabor_cpi"] = labor_nat_cpi
        else:
            dlabor_nat["dlabor_before"] = dlabor_nat["dlabor"]
            dlabor_nat["dlabor"] = labor_nat #["dlabor"]
            dlabor_nat["dlabor_cpi"] = labor_nat_cpi

        return dlabor_nat
    