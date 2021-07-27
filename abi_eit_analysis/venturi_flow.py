import numpy as np
from scipy import integrate

from abi_eit_analysis.analysis_lib import lambda_max


def calculate_volume(flow, x=None, dx=0.001, flow_threshold=0.02):
    """
    Calculate volume from flow.
    This function performs a cumulative trapezoidal integration after filtering and thresholding the flow data

    Parameters
    ----------
    dx
    x
    flow
    fs
    fc
    flow_threshold

    Returns
    -------
    volume

    """

    if x == "index_as_seconds":
        x = flow.index.astype(np.int64) / 10 ** 9

    flow_thresholded = np.where(np.abs(flow) <= flow_threshold, 0, flow)
    volume = integrate.cumtrapz(flow_thresholded, x=x, dx=dx, initial=0)
    return volume


def infer_flow_direction(flow_a, flow_b):
    """
    A venturi flow meter measures a positive but incorrect value when flow is reversed.
    This function assumes flow_a and flow_b are data sets from two opposing venturi tubes in series (or parallel with check valves)
    one will be measuring correctly, and one will be measuring incorrectly.
    Here we simply take the measurement of the highest magnitude, with the assumption that the magnitude of the measurement
    in the reverse direction will be smaller.

    Parameters
    ----------
    flow_a
    flow_b

    Returns
    -------
    max_magnitude

    """
    max_magnitude = lambda_max(np.array([flow_a, flow_b]).T, axis=1, key=np.abs)
    return max_magnitude


def venturi_pressure_to_flow(pressure, multiplier):
    flow = pressure.clip(lower=0).pow(0.5) * multiplier
    return flow