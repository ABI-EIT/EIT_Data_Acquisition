from tkinter import Tk
from tkinter.filedialog import askopenfilename
from tkinter.filedialog import askdirectory
import pandas as pd
import numpy as np
from scipy import signal
from scipy import integrate
from scipy.stats import linregress
import pathlib
import matplotlib.pyplot as plt
from abi_pyeit.eit.render import model_inverse_uv, map_image, calc_absolute_threshold_set
from abi_pyeit.plotting import get_img_bounds
from abi_pyeit.app.utils import *
from abi_pyeit.mesh.utils import *
import matplotlib.animation as animation
import math
from config_lib import Config
from itertools import count
from functools import lru_cache, wraps
import re
from datetime import datetime


# # ABI EIT DATA PROCESSING ---------------------------------------------------------------------------------------------
# # This section contains code that knows about the format of the data we get from the QT app

ABI_EIT_time_unit = "s"


def read_and_preprocess_data(filename, dataset_config_glob, resample_freq):
    dataset_config_filename = list(pathlib.Path(filename).parent.glob(dataset_config_glob))[0]
    dataset_config = Config(dataset_config_filename, type="yaml")

    # Read data in
    data = pd.read_csv(filename, index_col=0, low_memory=False)
    data.index = pd.to_datetime(data.index, unit=ABI_EIT_time_unit)
    parse_flow(data)
    data.index = data.index - data.index[0]

    # Tidy data. Don't fill Tag column to preserve precise timing
    data = squash_and_resample(data, resample_freq_hz=resample_freq, freq_column="Pressure1",
                               no_pad_columns=["Tag", "EIT"])

    # Orient
    sensor_orientations = [dataset_config["Flow1_sensor_orientation"], dataset_config["Flow2_sensor_orientation"]]
    data[["Pressure1", "Pressure2"]] = data[["Pressure1", "Pressure2"]] * sensor_orientations

    # Subtract offset from pressure reading
    offsets = [dataset_config["Flow1_offset"], dataset_config["Flow2_offset"]]
    data[["Pressure1", "Pressure2"]] = data[["Pressure1", "Pressure2"]] - offsets

    # Low pass filter pressure data
    data[["Pressure1_filtered", "Pressure2_filtered"]] = data[["Pressure1", "Pressure2"]].apply(
        lambda column: filter_data(column, fs=resample_freq))

    # Convert pressure to flow
    multipliers = [dataset_config["Flow1_multiplier"], dataset_config["Flow2_multiplier"]]
    data[["Flow1 (L/s)", "Flow2 (L/s)"]] = data[["Pressure1_filtered", "Pressure2_filtered"]].apply(
        lambda column, params: venturi_pressure_to_flow(column, multiplier=multipliers[next(params)]), params=count())

    # Find flow in correct direction
    data["Flow (L/s)"] = infer_flow_direction(data["Flow1 (L/s)"], data["Flow2 (L/s)"])

    # Calculate volume
    data["Volume (L)"] = calculate_volume(data["Flow (L/s)"], x="index_as_seconds")

    return data, dataset_config


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


def cached_caller(callable, hashable_transform=str, *args, **kwargs):
    """
    A function to wrap the arguments of a callable into hashable containers, then run the callable with lru_cache turned on.
    The hashable transform is a callable used to transform the args and kwargs into a form that implements the __hash__()
    and __eq__() methods.

    TODO: Add ability to control the size of the lru_cache
    TODO: Add ability to specify a different hashable transform for each arg and kwarg

    Parameters
    ----------
    callable: callable to call with lru_cache
    hashable_transform: callable. default is str. Another option is pickle.dumps. If None is passed, the arguments must
                        already be hashable
    args: args for callable
    kwargs: kwargs for callable

    Returns
    -------
    result of callable

    """
    if hashable_transform is not None:
        hashable_args = [HashableContainer(arg, hashable_transform) for arg in args]
        hashable_kwargs = {key: HashableContainer(val, hashable_transform) for key, val in kwargs.items()}
    else:
        hashable_args = args
        hashable_kwargs = kwargs
    return _call_with_hashables(callable, *hashable_args, **hashable_kwargs)


class HashableContainer:
    def __init__(self, object, hashable_transform):
        self.object = object
        self.hash_trans = hashable_transform

    def __eq__(self, other):
        return self.hash_trans(self.object) == self.hash_trans(other.object)

    def __hash__(self):
        return hash(self.hash_trans(self.object))


@lru_cache(maxsize=100)
def _call_with_hashables(wrapped, *hashable_args, **hashable_kwargs):
    original_args = [arg.object for arg in hashable_args]
    original_kwargs = {key: val.object for key, val in hashable_kwargs.items()}
    result = wrapped(*original_args, **original_kwargs)
    return result


def linearity_test(data, test_config, test_ginput, eit_config, dataset_config, out=None, cache_pyeit_obj=True):
    if out is None:
        out = {}

    # Process time windows ---------------------------------------------------------------------------------------------
    times = pd.to_timedelta(test_ginput)
    hold = test_config["hold"]
    test_data = pd.DataFrame(columns=["In", "Out"], data=np.array([times[::2], times[1::2]]).T)
    test_data["In end"] = test_data["In"].apply(lambda row: row + hold)
    test_data["In Volume"] = test_data.apply(lambda row: data["Volume (L)"].loc[row["In"]:row["In end"]].mean(), axis=1)
    test_data["Out end"] = test_data["Out"].apply(lambda row: row + hold)
    test_data["Out Volume"] = test_data.apply(lambda row: data["Volume (L)"].loc[row["Out"]:row["Out end"]].mean(),
                                              axis=1)

    # get_ith(data,1) gets the second EIT frame in the window. This ensures it is a frame completely scanned during the window
    test_data["EIT in"] = test_data.apply(
        lambda row: get_ith(data["EIT"].where(data["EIT"].loc[row["In"]:row["In end"]].notna()).dropna(), 1), axis=1)
    test_data["EIT out"] = test_data.apply(
        lambda row: get_ith(data["EIT"].where(data["EIT"].loc[row["Out"]:row["Out end"]].notna()).dropna(), 1), axis=1)

    # Calculate volume deltas ------------------------------------------------------------------------------------------
    test_data["Volume delta"] = (test_data["In Volume"] - test_data["Out Volume"]).abs()

    test_data = test_data.dropna()
    test_data = test_data.sort_values(by="Volume delta")

    if test_config["normalize_volume"] == "VC":
        mean_vc = np.average(dataset_config["VC"])
        test_data["Volume delta"] = test_data["Volume delta"] / mean_vc

    if test_config["analysis_max"] > 0:
        test_data = test_data[test_data["Volume delta"] <= test_config["analysis_max"]]

    # Process EIT ------------------------------------------------------------------------------------------------------
    mesh = load_stl(eit_config["mesh_filename"])

    place_e_output = {}
    if eit_config["electrode_placement"] == "equal_spacing_with_chest_and_spine_gap":
        electrode_nodes = place_electrodes_equal_spacing(mesh, n_electrodes=eit_config["n_electrodes"],
                                                         starting_angle=eit_config["starting_angle"],
                                                         counter_clockwise=eit_config["counter_clockwise"],
                                                         chest_and_spine_ratio=eit_config["chest_and_spine_ratio"],
                                                         output_obj=place_e_output)
    elif eit_config["electrode_placement"] == "lidar":
        electrode_points = pd.read_csv(eit_config["electrode_points_filename"], header=None)
        electrode_nodes = map_points_to_perimeter(mesh, points=np.array(electrode_points), map_to_nodes=True)
    else:
        raise ValueError("Invalid entry for the \"electrode_placement\" field")

    ex_mat = eit_scan_lines(eit_config["n_electrodes"], eit_config["dist"])
    if not cache_pyeit_obj:
        pyeit_obj = JAC(mesh, np.array(electrode_nodes), ex_mat, step=1, perm=1)
    else:
        pyeit_obj = cached_caller(JAC, str, mesh, np.array(electrode_nodes), ex_mat, step=1, perm=1)
    pyeit_obj.setup(p=eit_config["p"], lamb=eit_config["lamb"], method=eit_config["method"])

    # Solve EIT data
    test_data["solution"] = test_data.apply(lambda row: np.real(pyeit_obj.solve(v1=parse_oeit_line(row["EIT in"]),
                                                                                v0=parse_oeit_line(row["EIT out"]))),
                                            axis=1)

    # Render from solution (mesh + values) to nxn image
    test_data["recon_render"] = render_reconstruction(mesh, test_data["solution"])

    test_data["area^1.5_normalized"], test_data["threshold_image"] = calculate_eit_volume(test_data["recon_render"], eit_config["image_threshold_proportion"])

    # Linear fit -------------------------------------------------------------------------------------------------------
    d = np.polyfit(test_data["Volume delta"], test_data["area^1.5_normalized"], 1)
    f = np.poly1d(d)
    test_data["calculated"] = f(test_data["Volume delta"])
    r_squared = rsquared(test_data["calculated"], test_data["area^1.5_normalized"])

    out["df"] = test_data
    out["r_squared"] = r_squared
    out["mesh"] = mesh
    out["electrode_nodes"] = electrode_nodes
    out["place_electrodes"] = place_e_output

    return test_data


# # -------------------------------------------------------------------------------------------------------------------
# # -------------------------------------------------------------------------------------------------------------------


# # Support code for linearity test -----------------------------------------------------------------------------------
def render_reconstruction(mesh, reconstruction_series, mask_filename=None):
    # TODO: mask should be passed as a mesh not a filename to make this more consistent plus have better separation of concerns

    bounds = [
        (np.min(mesh["node"][:, 0]), np.min(mesh["node"][:, 1])),
        (np.max(mesh["node"][:, 0]), np.max(mesh["node"][:, 1]))
    ]
    image = model_inverse_uv(mesh, resolution=(1000, 1000), bounds=bounds)

    if mask_filename is not None:
        mask_mesh = load_stl(mask_filename)
        image = model_inverse_uv(mask_mesh, resolution=(1000, 1000), bounds=bounds)

    recon_render = [map_image(image, np.array(row)) for row in reconstruction_series]

    return recon_render


def calculate_eit_volume(recon_render_series, threshold_proportion=0.15):
    # Todo: maybe an intermediate should be area. We should also output the not normalized volume (or the max_pixels).
    # Find the point in the rendered image with greatest magnitude (+ or -) so we can threshold on this
    greatest_magnitude = [lambda_max(row, key=lambda val: np.abs(np.nan_to_num(val, nan=0))) for row in recon_render_series]

    # Find the max over all frames
    max_all_frames = lambda_max(np.array(greatest_magnitude), key=lambda val: np.abs(np.nan_to_num(val, nan=0)))

    # Create a threshold image
    threshold_image_series = [calc_absolute_threshold_set(row, max_all_frames * threshold_proportion) for row in recon_render_series]

    # Count pixels in the threshold image
    reconstructed_area_series = [np.count_nonzero(row == 1) for row in threshold_image_series]

    max_pixels = np.sum(np.isfinite(threshold_image_series[0]))

    # Raise to power of 1.5 to obtain a linear relationship with volume
    volume_series = np.power(reconstructed_area_series, 1.5)

    volume_normalized_series = volume_series / max_pixels ** 1.5

    return volume_normalized_series, threshold_image_series


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



# # --------------------------------------------------------------------------------------------------------------------
# # --------------------------------------------------------------------------------------------------------------------


# # Support code for using ginput to set time points for data analysis--------------------------------------------------
def get_input(data, show_columns, test_name):
    start, stop = find_last_test_start_and_stop(data["Tag"], test_name)
    if start is None:
        start = data.index[0]
    if stop is None:
        stop = data.index[-1]

    ax = data[show_columns][start:stop].plot()
    ax.text(1.025, 0.985, "Add point: Mouse left\nRemove point: Mouse right\nClose: Mouse middle",
            transform=ax.transAxes, va="top", bbox=dict(ec=(0, 0, 0), fc=(1, 1, 1)))
    ax.set_title("Input for " + test_name)
    ax.figure.tight_layout(pad=1)
    points = plt.ginput(n=-1, timeout=0)
    return points


def find_last_test_start_and_stop(data, test_name, start_label="Start", stop_label="Stop", join=" "):
    # [::-1] with idxmax() means we find the last index. We want the last index of the start and stop tags because the user might have clicked accidentally.
    # We assume the last index was the correct one
    start = (data[::-1] == (start_label + join + test_name)).idxmax() if (
                data[::-1] == (start_label + join + test_name)).any() else None
    stop = (data[::-1] == (stop_label + join + test_name)).idxmax() if (
                data[::-1] == (stop_label + join + test_name)).any() else None
    return start, stop


# # --------------------------------------------------------------------------------------------------------------------
# # --------------------------------------------------------------------------------------------------------------------


# # Support code for volume calculations -------------------------------------------------------------------------------
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
    flow = pressure.clip(lower=0).pow(0.5) * multiplier
    return flow


def squash_and_resample(data, freq_column=None, resample_freq_hz=1000, output=None, no_pad_columns=None):
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
    data[pad_cols] = data[pad_cols].fillna(method="pad")

    # Resample so we have a constant frequency which make further processing nicer
    data = data.resample(pd.to_timedelta(1 / resample_freq_hz, unit="s")).first()
    data[pad_cols] = data[pad_cols].pad()
    return data


# # --------------------------------------------------------------------------------------------------------------------
# # --------------------------------------------------------------------------------------------------------------------

# # Function to get a filename by asking the user.
# Maybe this should be in the config lib
def get_filename(config=None, key="data", remember_directory=True):
    # Todo: we probably should put the config stuff in a separate function.
    return _get_filename_or_directory(config=config, key=key, which="filename", remember_directory=remember_directory)


# # Function to get a directory by asking the user.
# Maybe this should be in the config lib
def get_directory(config=None, key="data", remember_directory=True):
    return _get_filename_or_directory(config=config, key=key, which="directory", remember_directory=remember_directory)


def _get_filename_or_directory(config=None, key="data", which="filename", remember_directory=True):
    """
    Finds a filename by asking the user through a Tk file select dialog.
    If remember_directory is set to True, the directory is remembered for next time
    If the filename key exists in the input config, this is used instead of the dialog

    Parameters
    ----------
    config
    key
    which
    remember_directory

    Returns
    -------
    item
        config or directory name

    """
    if config is not None and key in config:
        item = config[key]  # Secret option to not get dialog
    else:
        Tk().withdraw()  # we don't want a full GUI, so keep the root window from appearing
        try:
            initial_dir = None
            if config is not None and f"initial_{key}_directory" in config:
                initial_dir = config[f"initial_{key}_directory"]

            if which == "filename":
                item = askopenfilename(initialdir=initial_dir, title=f"Select {key} file")
            else:
                item = askdirectory(initialdir=initial_dir, title=f"Select {key} directory")

        except FileNotFoundError:
            raise

        if item == "" or item == ():
            error_message = f"Invalid {which} selection"
            raise ValueError(error_message)

        if config is not None and remember_directory:
            if which == "directory":
                directory = item
            else:
                directory = str(pathlib.Path(item).parent)

            if f"initial_{key}_directory" not in config or directory != config[f"initial_{key}_directory"]:
                config[f"initial_{key}_directory"] = directory
                config.save()

        return item


def parse_relative_paths(input_dict, alternate_working_directory, awd_indicator="alternate", path_tag="filename",
                         wd_tag="_wd"):
    """
    Modify paths in an input dict to make them relative to an alternate working directory if indicated.

    Parameters
    ----------
    input_dict
    alternate_working_directory
    awd_indicator
    path_tag
    wd_tag

    Returns
    -------

    """
    for key, value in input_dict.items():
        # check if key indicates that this is a path
        if re.match(".*(?:" + path_tag + "$)", key) is not None:
            # check if the dict contains an instruction to modify the identified path
            if key + wd_tag in input_dict:
                # if the instruction is awd_indicator, we prepend the alternate working directory to the path
                if input_dict[key + wd_tag] == awd_indicator:
                    input_dict[key] = alternate_working_directory + "/" + input_dict[key]
                # else we just assume prepend whatever we see
                else:
                    input_dict[key] = input_dict[key + wd_tag] + "/" + input_dict[key]


def create_unique_timestamped_file_name(directory=".", date_format="%Y-%m-%dT%H_%M", prefix="", suffix="", extension=""):
    # TODO: don't create the directory (for better separation of concerns)
    if not os.path.exists(directory):
        os.mkdir(directory)

    if prefix != "":
        prefix = prefix + "_"
    if suffix != "":
        suffix = "_" + suffix

    file_name = prefix + datetime.now().strftime(date_format) + suffix

    addition = ""
    i = 0
    while True:
        try_name = directory + "/" + file_name + addition + extension
        if not(os.path.exists(try_name)):
            return try_name
        i += 1
        addition = "_" + str(i)
