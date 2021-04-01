from tkinter import Tk
from tkinter.filedialog import askopenfilename
import os
import pathlib
import pandas as pd
import yaml
import numpy as np
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

    data = pd.read_csv(filename, index_col=0, low_memory=False)
    data.index = pd.to_datetime(data.index, unit=ABI_EIT_time_unit)
    if "flow" in data.columns:
        parse_flow(data)
    data.index = data.index - data.index[0]
    data = squash_and_resample(data, freq_column="Flow1")

    # venturi_pressure_to_flow
    # infer_flow_direction
    # flow_to_volume

    # Get ginput for each desired test if no file is found (ie. we haven't done it yet). Save in a ginput file


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

