from tkinter import Tk
from tkinter.filedialog import askopenfilename
import os
import pathlib
import pandas as pd
import yaml
import numpy as np
from scipy import signal
from scipy import integrate
import matplotlib.pyplot as plt

configuration_directory = "configuration/"
config_file = "config.yaml"
config_path = configuration_directory + config_file
default_config = {
    "initial_dir": "",
    "dataset_config_glob": "*.yaml"
}

ABI_EIT_time_unit = "s"


def main():
    config = Config(config_path, default_config)
    filename = load_filename(config)

    dataset_config_filename = list(pathlib.Path(filename).parent.glob(config["dataset_config_glob"]))[0]
    dataset_config = Config(dataset_config_filename)

    # Read data in
    data = pd.read_csv(filename, index_col=0, low_memory=False)
    data.index = pd.to_datetime(data.index, unit=ABI_EIT_time_unit)
    if "flow" in data.columns:
        parse_flow(data)
    data.index = data.index - data.index[0]

    # Tidy data
    data = squash_and_resample(data, freq_column="Flow1")

    # Convert pressure to flow
    data[["Flow1 (L/s)", "Flow2 (L/s)"]] = data[["Flow1", "Flow2"]].apply(
        lambda column: venturi_pressure_to_flow(column, dataset_config[column.name + "_multiplier"]))

    # Find flow in correct direction
    data["Flow (L/s)"] = infer_flow_direction(data["Flow1 (L/s)"], data["Flow2 (L/s)"])

    # Calculate volume
    data["Volume (L)"] = calculate_volume(data["Flow (L/s)"])

    data[["Volume (L)", "Flow (L/s)"]].plot()
    plt.show()
    # Get ginput for each desired test if no file is found (ie. we haven't done it yet). Save in a ginput file


def calculate_volume(flow, x="index_as_seconds", fs=1000, fc=50, flow_threshold=0.02):
    """
    Calculate volume from flow.
    This function performs a cumulative trapezoidal integration after filtering and thresholding the flow data

    Parameters
    ----------
    flow
    fs
    fc
    flow_threshold

    Returns
    -------
    volume

    """

    if x == "index_as_seconds":
        x = flow.index.astype(np.int64)/10**9
    else:
        x = None

    w = fc / (fs / 2)  # Normalize the frequency
    b, a = signal.butter(5, w, 'low')
    flow_filtered = signal.filtfilt(b, a, flow)
    flow_filtered_thresholded = np.where(np.abs(flow_filtered) <= flow_threshold, 0, flow_filtered)
    volume = integrate.cumtrapz(flow_filtered_thresholded,  x=x, initial=0)
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


def venturi_pressure_to_flow(pressure, multiplier, offset=0, sensor_orientation=1):
    flow = ((pressure * sensor_orientation).pow(.5).fillna(0) * multiplier) - offset
    return flow


def squash_and_resample(data, freq_column=None, resample_freq="1ms", output=None):
    # For each column, group by repeated index and take the first non na.
    # This "squashes" data where each row contains data from only one column, but data from two different columns
    #   could have the same timestamp
    data = data.groupby(data.index).first()

    # Frequency analysis of raw data for our own interest
    if freq_column is None:
        freq_column = data.columns[0]
    mean_freq = 1/((data[freq_column].dropna().index[-1]/len(data[freq_column].dropna())).value * 1e-9)  # timedelta.value is returned in nanoseconds
    if output is not None:
        time_deltas = [*data.index[1:], np.NaN] - data.index
        output["mean_freq"] = mean_freq
        output["time_deltas"] = time_deltas

    # Fillna fixes the opposite issue to the "squashing". Columns are recorded each with their own timestamp, so we need to
    # fill the gaps to get rows with all columns
    data = data.fillna(method="pad")

    # Resample so we have a constant frequency which make further processing nicer
    data = data.resample(resample_freq).pad()
    return data


def parse_flow(data):
    """
    Parse the data format of the ABI EIT flow meter.
    Creates columns Flow1 and Flow2 in the input dataframe

    Parameters
    ----------
    data: Pandas DataFrame
    """
    data["Flow1"] = pd.to_numeric(data["Flow"].str.split(",", expand=True)[1], errors="coerce")
    data["Flow2"] = pd.to_numeric(data["Flow"].str.split(",", expand=True)[2], errors="coerce")


def load_filename(config, remember_directory=True):
    """
    Finds a filename by asking the user through a Tk file select dialog.
    If remember_directory is set to True, the directory is remembered for next time
    If the filename key exists in the input config, this is used instead of the dialog

    Parameters
    ----------
    config
    remember_directory

    Returns
    -------
    filename

    """
    if "filename" in config:
        filename = config["filename"]  # Secret option to not get dialog
    else:
        Tk().withdraw()  # we don't want a full GUI, so keep the root window from appearing
        try:
            filename = askopenfilename(initialdir=config["initial_dir"], title="Select data file")
        except FileNotFoundError:
            print("You have to choose a file!")
            raise

    if remember_directory:
        directory = str(pathlib.Path(filename).parent)
        if directory != config["initial_dir"]:
            config["initial_dir"] = directory
            config.save()

    return filename


class Config:
    """
        A class to manage a configuration dict.
        Load safely loads the config from file, using default values if necessary
        Save safely saves the internal config dict to file
    """
    def __init__(self, path, default=None):
        if default is None:
            default = {}
        self.default_config = default
        self.config = default
        self.path = path
        self.load()

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                self.config = yaml.safe_load(f)

            for key, default_value in self.default_config.items():
                if key not in self.config:
                    self.config[key] = default_value
        else:
            self.config = self.default_config

    def save(self):
        pathlib.Path(config_path).parent.mkdir(parents=True, exist_ok=True)

        with open(self.path, "w") as f:
            yaml.dump(self.config, f, width=1000)

    def __getitem__(self, key):
        return self.config[key]

    def __setitem__(self, key, value):
        self.config[key] = value

    def __contains__(self, item):
        return item in self.config


if __name__ == "__main__":
    main()

