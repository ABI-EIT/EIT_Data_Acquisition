from statsmodels.stats.power import tt_ind_solve_power

power = 0.8
alpha = 0.05
nobs1 = 9

result = tt_ind_solve_power(effect_size=None, power=power, nobs1=nobs1, ratio=1.0, alpha=alpha)
print(f"Required effect size: {result} standard deviations")
