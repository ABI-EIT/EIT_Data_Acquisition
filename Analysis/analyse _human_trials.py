from tkinter import Tk
from tkinter.filedialog import askopenfilename
import os
import pathlib
import pandas as pd
import yaml
import numpy as np
from scipy import signal
from scipy import integrate
from scipy.stats import linregress
import matplotlib.pyplot as plt
import json
from abi_pyeit.quality.plotting import *
from abi_pyeit.app.eit import *
import math
import matplotlib.animation as animation
from itertools import count


def main():
    config = Config(config_path, default_config)
    filename = load_filename(config)

    dataset_config_filename = list(pathlib.Path(filename).parent.glob(config["dataset_config_glob"]))[0]
    dataset_config = Config(dataset_config_filename)

    # Read data in
    data = pd.read_csv(filename, index_col=0, low_memory=False)
    data.index = pd.to_datetime(data.index, unit=ABI_EIT_time_unit)
    parse_flow(data)
    data.index = data.index - data.index[0]

    # Tidy data. Don't fill Tag column to preserve precise timing
    data = squash_and_resample(data, resample_freq_hz=config["resample_freq_hz"], freq_column="Pressure1", no_pad_columns=["Tag", "EIT"])

    # Orient
    sensor_orientations = [dataset_config["Flow1_sensor_orientation"], dataset_config["Flow2_sensor_orientation"]]
    data[["Pressure1", "Pressure2"]] = data[["Pressure1", "Pressure2"]] * sensor_orientations

    # Subtract offset from pressure reading
    offsets = [dataset_config["Flow1_offset"], dataset_config["Flow2_offset"]]
    data[["Pressure1", "Pressure2"]] = data[["Pressure1", "Pressure2"]] - offsets

    # Low pass filter pressure data
    data[["Pressure1_filtered", "Pressure2_filtered"]] = data[["Pressure1", "Pressure2"]].apply(lambda column: filter_data(column, fs=config["resample_freq_hz"]))

    # Convert pressure to flow
    multipliers = [dataset_config["Flow1_multiplier"], dataset_config["Flow2_multiplier"]]
    data[["Flow1 (L/s)", "Flow2 (L/s)"]] = data[["Pressure1_filtered", "Pressure2_filtered"]].apply(
        lambda column, params: venturi_pressure_to_flow(column, multiplier=multipliers[next(params)]), params=count())

    # Find flow in correct direction
    data["Flow (L/s)"] = infer_flow_direction(data["Flow1 (L/s)"], data["Flow2 (L/s)"])

    # Calculate volume
    data["Volume (L)"] = calculate_volume(data["Flow (L/s)"], x="index_as_seconds")

    # Construct ginput file name based on data file name
    ginput_name = pathlib.Path(pathlib.Path(filename).stem + "_ginput.json")
    ginput_path = pathlib.Path(filename).parent / ginput_name
    data_ginput = Config(ginput_path, type="json")

    # Get ginput for all desired tests, either from user or from file
    for test in config["tests"]:
        if test not in data_ginput:
            points = get_input(data, show_columns=["Volume (L)"], test_name=test)
            data_ginput[test] = [point[0] for point in points]  # save only times
            data_ginput.save()

    # Run linearity test
    lin_out = {}
    linearity_test(data[["Volume (L)", "EIT"]], test_config=config["tests"]["Test 3"],
                   test_ginput=data_ginput["Test 3"], eit_config=config["eit_configuration"], dataset_config=dataset_config, out=lin_out)


    # Plotting ---------------------------------------------------------------------------------------------------------
    # Plot volume with EIT frames
    ax = data["Volume (L)"].plot()
    ax.plot(data["Volume (L)"].where(data["EIT"].notna()).dropna(), "rx")
    # ax.plot(data["Flow1 (L/s)"])
    ax.set_title("Expiration volume with EIT frame times")
    ax.set_ylabel("Volume (L)")

    # Linearity test plots
    recon_min = np.nanmin(lin_out["df"]["recon_render"].apply(np.nanmin))
    recon_max = np.nanmax(lin_out["df"]["recon_render"].apply(np.nanmax))
    fig, ani1 = create_animated_image_plot(lin_out["df"]["recon_render"].values, title="Reconstruction image animation", vmin=recon_min, vmax=recon_max)
    fig, ani2 = create_animated_image_plot(lin_out["df"]["threshold_image"].values, title="Threshold image animation")

    # # # Save animations
    # writer_gif = animation.PillowWriter(fps=2, bitrate=2000)
    # # ani1.save(str(pathlib.Path(filename).parent) + "\\" + "Reconstruction image animation.gif", writer_gif, dpi=1000)
    # ani2.save(str(pathlib.Path(filename).parent) + "\\" + "Threshold image animation.gif", writer_gif, dpi=1000)

    fig, ax = plt.subplots()
    ax.plot(lin_out["df"]["Volume delta"], lin_out["df"]["area^1.5_normalized"], ".")
    ax.plot(lin_out["df"]["Volume delta"], lin_out["df"]["calculated"])
    ax.text(0.8, 0.1, "R^2 = {0:.4}".format(lin_out["r_squared"]), transform=ax.transAxes)
    if config["tests"]["Test 3"]["normalize_volume"] == "VC":
        ax.set_title("Volume delta (normalized to vital capacity) \nvs EIT image area^1.5")
        ax.set_xlabel("Volume delta normalized to vital capacity")
        ax.set_ylabel("EIT image area (pixels)^1.5/max_pixels^1.5")
        ax.figure.tight_layout(pad=1)

    # Save data
    lin_out["df"][["Volume delta", "area^1.5_normalized"]].to_csv(str(pathlib.Path(filename).parent) + "\\" + "eit_vs_volume.csv")

    plt.show()


def create_animated_image_plot(images, title, background=np.nan, margin=10, interval=500, repeat_delay=500, **kwargs):
    """
    Create a plot using imshow and set the axis bounds to frame the image

    Parameters
    ----------
    image
        Image array
    title
        Plot title
    background
        Value of the background in the image
    margin
        Margin to place at the sides of the image
    origin
        Origin parameter for imshow

    Returns
    -------
    fig, ax

    """
    fig, ax = plt.subplots()
    ims = [[ax.imshow(im.T, **kwargs, animated=True)] for im in images]
    img_bounds = get_img_bounds(images[0].T, background=background)

    ax.set_ybound(img_bounds[0]-margin, img_bounds[1]+margin)
    ax.set_xbound(img_bounds[2]-margin, img_bounds[3]+margin)
    ax.set_title(title)

    fig.colorbar(ims[0][0])

    ani = animation.ArtistAnimation(fig, ims, interval=interval, blit=True, repeat_delay=repeat_delay)

    return fig, ani


def get_ith(data, i):
    if len(data) > i:
        return data.iloc[i]
    else:
        return None


def linearity_test(data, test_config, test_ginput, eit_config, dataset_config, out=None):

    if out is None:
        out = {}

    # Process time windows ---------------------------------------------------------------------------------------------
    times = pd.to_timedelta(test_ginput)
    hold = test_config["hold"]
    test_data = pd.DataFrame(columns=["In", "Out"], data=np.array([times[::2], times[1::2]]).T)
    test_data["In end"] = test_data["In"].apply(lambda row: row + hold)
    test_data["In Volume"] = test_data.apply(lambda row: data["Volume (L)"].loc[row["In"]:row["In end"]].mean(), axis=1)
    test_data["Out end"] = test_data["Out"].apply(lambda row: row + hold)
    test_data["Out Volume"] = test_data.apply(lambda row: data["Volume (L)"].loc[row["Out"]:row["Out end"]].mean(), axis=1)

    # get_ith(data,1) gets the second EIT frame in the window. This ensures it is a frame completely scanned during the window
    test_data["EIT in"] = test_data.apply(lambda row: get_ith(data["EIT"].where(data["EIT"].loc[row["In"]:row["In end"]].notna()).dropna(), 1), axis=1)
    test_data["EIT out"] = test_data.apply(lambda row: get_ith(data["EIT"].where(data["EIT"].loc[row["Out"]:row["Out end"]].notna()).dropna(), 1), axis=1)

    # Calculate volume deltas ------------------------------------------------------------------------------------------
    test_data["Volume delta"] = (test_data["In Volume"] - test_data["Out Volume"]).abs()

    test_data = test_data.dropna()
    test_data = test_data.sort_values(by="Volume delta")

    if test_config["normalize_volume"] == "VC":
        mean_vc = np.average(dataset_config["VC"])
        test_data["Volume delta"] = test_data["Volume delta"]/mean_vc

    if test_config["analysis_max"] > 0:
        test_data = test_data[test_data["Volume delta"] <= test_config["analysis_max"]]


    # Process EIT ------------------------------------------------------------------------------------------------------
    mesh = load_stl(eit_config["mesh_filename"])
    image = model_inverse_uv(mesh, resolution=(1000, 1000))
    electrode_nodes = place_electrodes_equal_spacing(mesh, n_electrodes=eit_config["n_electrodes"], starting_angle=math.pi)

    ex_mat = eit_scan_lines(eit_config["n_electrodes"], eit_config["dist"])
    pyeit_obj = JAC(mesh, np.array(electrode_nodes), ex_mat, step=1, perm=1)
    pyeit_obj.setup(p=eit_config["p"], lamb=eit_config["lamb"], method=eit_config["method"])

    # Solve EIT data
    test_data["solution"] = test_data.apply(lambda row: np.real(pyeit_obj.solve(v1=parse_oeit_line(row["EIT in"]),
                                                                                v0=parse_oeit_line(row["EIT out"]))), axis=1)

    # Render from solution (mesh + values) to nxn image
    test_data["recon_render"] = test_data.apply(lambda row: map_image(image, np.array(row["solution"])), axis=1)

    # Find the point in the rendered image with greatest magnitude (+ or -) so we can threshold on this
    test_data["greatest_magnitude"] = test_data.apply(lambda row: lambda_max(row["recon_render"],
                                                                             key=lambda val: np.abs(np.nan_to_num(val, nan=0))), axis=1)
    # Find the max over all frames
    max_all_frames = lambda_max(np.array(test_data["greatest_magnitude"]), key=np.abs)

    # Create a threshold image
    test_data["threshold_image"] = test_data.apply(lambda row: calc_absolute_threshold_set(row["recon_render"],
                                                                                           max_all_frames*eit_config["image_threshold_proportion"]), axis=1)

    # Count pixels in the threshold image
    test_data["reconstructed_area"] = test_data.apply(lambda row: np.count_nonzero(row["threshold_image"] == 1), axis=1)

    max_pixels = np.sum(np.isfinite(test_data["threshold_image"].iloc[0]))

    # Raise to power of 1.5 to obtain a linear relationship with volume
    test_data["reconstructed_area^1.5"] = test_data["reconstructed_area"].pow(1.5)

    test_data["area^1.5_normalized"] = test_data["reconstructed_area^1.5"]/max_pixels**1.5

    # Linear fit -------------------------------------------------------------------------------------------------------
    d = np.polyfit(test_data["Volume delta"], test_data["area^1.5_normalized"], 1)
    f = np.poly1d(d)
    test_data["calculated"] = f(test_data["Volume delta"])
    r_squared = rsquared(test_data["calculated"], test_data["area^1.5_normalized"])

    out["df"] = test_data
    out["r_squared"] = r_squared

    return test_data

def rsquared(x, y):
    """ Return R^2 where x and y are array-like."""

    slope, intercept, r_value, p_value, std_err = linregress(x, y)
    return r_value**2

def calc_absolute_threshold_set(image, threshold):
    """


    Parameters
    ----------
    image: np.Array(width,height)
    threshold: float

    Returns
    ---------
    image_set: np.Array(width,height)
    """

    image_set = np.full(np.shape(image), np.nan)

    if threshold < 0:
        with np.errstate(invalid="ignore"):
            image_set[image < threshold] = 1
            image_set[image >= threshold] = 0

    else:
        with np.errstate(invalid="ignore"):
            image_set[image < threshold] = 0
            image_set[image >= threshold] = 1

    return image_set


def get_input(data, show_columns, test_name):
    start, stop = find_last_test_start_and_stop(data["Tag"], test_name)
    if start is None:
        start = data.index[0]
    if stop is None:
        stop = data.index[-1]

    ax = data[show_columns][start:stop].plot()
    ax.text(1.025, 0.985, "Add point: Mouse left\nRemove point: Mouse right\nClose: Mouse middle", transform=ax.transAxes, va="top", bbox=dict(ec=(0, 0, 0), fc=(1, 1, 1)))
    ax.set_title("Input for " + test_name)
    ax.figure.tight_layout(pad=1)
    points = plt.ginput(n=-1, timeout=0)
    return points


def find_last_test_start_and_stop(data, test_name, start_label="Start", stop_label="Stop", join=" "):
    # [::-1] with idxmax() means we find the last index. We want the last index of the start and stop tags because the user might have clicked accidentally.
    # We assume the last index was the correct one
    start = (data[::-1] == (start_label + join + test_name)).idxmax() if (data[::-1] == (start_label + join + test_name)).any() else None
    stop = (data[::-1] == (stop_label + join + test_name)).idxmax() if (data[::-1] == (stop_label + join + test_name)).any() else None
    return start, stop


def filter_data(column, fs=1000, fc=50):
    w = fc / (fs / 2)  # Normalize the frequency
    b, a = signal.butter(5, w, 'low')

    filtered = signal.filtfilt(b, a, column)
    return filtered


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
        x = flow.index.astype(np.int64)/10**9

    flow_thresholded = np.where(np.abs(flow) <= flow_threshold, 0, flow)
    volume = integrate.cumtrapz(flow_thresholded,  x=x, dx=dx, initial=0)
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


def venturi_pressure_to_flow(pressure, multiplier):
    flow = pressure.clip(lower=0).pow(0.5)*multiplier
    return flow


def squash_and_resample(data, freq_column=None, resample_freq_hz=1000, output=None, no_pad_columns=None):
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
    pad_cols = [col for col in data.columns if col not in no_pad_columns]
    data[pad_cols] = data[pad_cols].fillna(method="pad")

    # Resample so we have a constant frequency which make further processing nicer
    data = data.resample(pd.to_timedelta(1 / resample_freq_hz, unit="s")).first()
    data[pad_cols] = data[pad_cols].pad()
    return data


def parse_flow(data):
    """
    Parse the data format of the ABI EIT flow meter.
    Creates columns Flow1 and Flow2 in the input dataframe

    Parameters
    ----------
    data: Pandas DataFrame
    """
    if "Flow1" in data.columns:
        data["Pressure1"] = data["Flow1"]
        data["Pressure2"] = data["Flow2"]
    elif "Flow" in data.columns:
        data["Pressure1"] = pd.to_numeric(data["Flow"].str.split(",", expand=True)[1], errors="coerce")
        data["Pressure2"] = pd.to_numeric(data["Flow"].str.split(",", expand=True)[2], errors="coerce")


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
    def __init__(self, path, default=None, type="yaml"):
        if default is None:
            default = {}
        if type != "yaml" and type != "json":
            raise ValueError("Config type must be yaml or json")
        self.type = type
        self.default_config = default
        self.config = default
        self.path = path
        self.load()

    def load(self):
        if os.path.exists(self.path):
            with open(self.path, "r") as f:
                if self.type == "yaml":
                    self.config = yaml.safe_load(f)
                else:
                    self.config = json.load(f)

            for key, default_value in self.default_config.items():
                resave = False
                if key not in self.config:
                    resave = True
                    self.config[key] = default_value

                if resave:
                    self.save()
        else:
            self.config = self.default_config

    def save(self):
        pathlib.Path(config_path).parent.mkdir(parents=True, exist_ok=True)

        with open(self.path, "w") as f:
            if self.type == "yaml":
                yaml.safe_dump(self.config, f, width=1000)
            else:
                json.dump(self.config, f)

    def __getitem__(self, key):
        return self.config[key]

    def __setitem__(self, key, value):
        self.config[key] = value

    def __contains__(self, item):
        return item in self.config


# Default configurations -----------------------------------------------------
# Don't change these to configure a single test! Change settings in the config file!
configuration_directory = "configuration/"
config_file = "config.yaml"
config_path = configuration_directory + config_file
default_config = {
    "initial_dir": "",
    "dataset_config_glob": "Subject Information.yaml",
    "tests": {
        "Test 3": {"hold": "10s", "analysis_max": -1, "normalize_volume": "VC"}
    },
    "eit_configuration": {
        "mesh_filename": "mesh/mesha06_bumpychestslice.stl",
        "n_electrodes": 16,
        "dist": 3,
        # Recon:
        "p": 0.5,
        "lamb": 0.4,
        "method": "kotre",
        # Electrode placement:
        "chest_and_spine_ratio": 2,
        # Analysis:
        "image_threshold_proportion": .15
    },
    "resample_freq_hz": 1000
}

ABI_EIT_time_unit = "s"

if __name__ == "__main__":
    main()