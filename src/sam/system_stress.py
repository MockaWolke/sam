import numpy as np
from scipy.optimize import curve_fit
from .data_formats import DoseResponseSeries
from .transforms import *
from .dose_reponse_fit import FitSettings
from .helpers import pad_c0
from sklearn.linear_model import LinearRegression

def weibull_2param(x, b, e):
    return np.exp(-np.exp(b * (np.log(x) - np.log(e))))


def weibull_3param(x, b, d, e):
    return d * np.exp(-np.exp(b * (np.log(x) - np.log(e))))

def fallback_linear_regression(x_data, y_data):
    reg = LinearRegression()
    reg.fit(np.log(x_data).reshape(-1, 1), y_data)  # log-transformed linear regression
    return lambda x: reg.predict(np.log(x).reshape(-1, 1))

def fit_weibull_2param(x_data, y_data):
    initial_guess = [1, 1]
    param_bounds = ([-20, 1e-8], [20, 1e5])

    try:
        # Try to fit Weibull model
        popt, pcov = curve_fit(
            weibull_2param, x_data, y_data, p0=initial_guess, bounds=param_bounds
        )
        return lambda x: weibull_2param(x, *popt)
    except Exception as e:
        print("Weibull 2-param fit failed, defaulting to linear regression")
        return fallback_linear_regression(x_data, y_data)

def fit_weibull_3param(x_data, y_data):
    initial_guess = [1, 1, 1]  # Initial guesses for b, d, e
    param_bounds = ([-20, 1e-8, 1e-8], [20, 1e5, 1e5])

    try:
        # Try to fit Weibull model
        popt, pcov = curve_fit(
            weibull_3param, x_data, y_data, p0=initial_guess, bounds=param_bounds
        )
        return lambda x: weibull_3param(x, *popt)
    except Exception as e:
        print("Weibull 3-param fit failed, defaulting to linear regression")
        return fallback_linear_regression(x_data, y_data)


def pred_surv_without_hormesis(concentration, surv_withhormesis, hormesis_index):
    survival_cleaned = np.concatenate(([1.0], surv_withhormesis[hormesis_index:]))

    concentration_cleaned = np.concatenate((concentration[:1], concentration[hormesis_index:]))

    fitted_func = fit_weibull_2param(x_data=concentration_cleaned, y_data=survival_cleaned)
    survival_cleaned = fitted_func(x=concentration)

    return fitted_func, survival_cleaned



def calc_system_stress(
    only_tox_series: DoseResponseSeries,
    hormesis_index: int,
    cfg: FitSettings = FitSettings(),
):

    if hormesis_index < 1 or hormesis_index >= len(only_tox_series.concentration):
        raise ValueError("wrong hormesis index")

    if cfg.survival_max <= 0:
        raise ValueError("survival_max must be >= 0")

    concentration = pad_c0(only_tox_series.concentration)
    survival_tox_observerd = only_tox_series.survival_rate / cfg.survival_max

    cleaned_func, survival_tox_cleaned = pred_surv_without_hormesis(
        concentration=concentration,
        surv_withhormesis=survival_tox_observerd,
        hormesis_index=hormesis_index,
    )

    orig_stress_tox = cfg.survival_to_stress(survival_tox_observerd)
    stress_tox_cleaned = cfg.survival_to_stress(survival_tox_cleaned)

    system_stress = np.clip(orig_stress_tox - stress_tox_cleaned, 0, 1)
    system_stress[hormesis_index:] = 0

    fitted_func = fit_weibull_3param(x_data=concentration, y_data=system_stress)
    
    return cleaned_func, fitted_func