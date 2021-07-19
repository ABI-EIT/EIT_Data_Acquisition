import numpy as np
import pandas as pd
from scipy import signal
from scipy.stats import linregress


def get_ith(data, i):
    """
    Wrapper for pandas iloc that returns None if index is out of range
    """
    if len(data) > i:
        return data.iloc[i]
    else:
        return None


def rsquared(x, y):
    """ Return R^2 where x and y are array-like."""

    slope, intercept, r_value, p_value, std_err = linregress(x, y)
    return r_value ** 2


def filter_data(column, fs=1000, fc=50, order=5, how="low"):
    w = fc / (fs / 2)  # Normalize the frequency
    b, a = signal.butter(order, w, how)

    filtered = signal.filtfilt(b, a, column)
    return filtered


def lambda_max(arr, axis=None, key=None, keepdims=False):
    """

    See: https://stackoverflow.com/questions/61703879/in-numpy-how-to-select-elements-based-on-the-maximum-of-their-absolute-values

    Parameters
    ----------
    arr
    axis
    key
    keepdims

    Returns
    -------
    calculated maximum

    """
    if callable(key):
        idxs = np.argmax(key(arr), axis)
        if axis is not None:
            idxs = np.expand_dims(idxs, axis)
            result = np.take_along_axis(arr, idxs, axis)
            if not keepdims:
                result = np.squeeze(result, axis=axis)
            return result
        else:
            return arr.flatten()[idxs]
    else:
        return np.amax(arr, axis)


def squash_and_resample(data, freq_column=None, resample_freq_hz=1000, output=None, no_pad_columns=None, interpolate=False):
    # Todo: The squashing is necessary but I don't think it's actually advisable to do the resampling.
    #   It can definitely mess with filtering and fft analysis. If we want to know the average frequency we can estimate
    #   it using the calculation below. For the integration, we can input the index, so we don't need a constatn dx

    if no_pad_columns is None:
        no_pad_columns = []
    # For each column, group by repeated index and take the first non na.
    # This "squashes" data where each row contains data from only one column, but data from two different columns
    #   could have the same timestamp
    data = data.groupby(data.index).first()

    # Frequency analysis of raw data for our own interest
    if freq_column is None:
        freq_column = data.columns[0]
    mean_freq = 1 / ((data[freq_column].dropna().index[-1] / len(
        data[freq_column].dropna())).value * 1e-9)  # timedelta.value is returned in nanoseconds
    if output is not None:
        time_deltas = [*data.index[1:], np.NaN] - data.index
        output["mean_freq"] = mean_freq
        output["time_deltas"] = time_deltas

    # Fillna fixes the opposite issue to the "squashing". Columns are recorded each with their own timestamp, so we need to
    # fill the gaps to get rows with all columns
    pad_cols = [col for col in data.columns if col not in no_pad_columns]
    if not interpolate:
        data[pad_cols] = data[pad_cols].fillna(method="pad")
    else:
        data[pad_cols] = data[pad_cols].interpolate()

    # Resample so we have a constant frequency which make further processing nicer
    if not interpolate:
        data = data.resample(pd.to_timedelta(1 / resample_freq_hz, unit="s")).first()
        data[pad_cols] = data[pad_cols].pad()
    else:
        data = data.resample(pd.to_timedelta(1 / resample_freq_hz, unit="s")).first()
        data[pad_cols] = data[pad_cols].interpolate()
    return data