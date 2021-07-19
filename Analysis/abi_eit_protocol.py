import pandas as pd
from Analysis.analysis_lib import rsquared, filter_data, squash_and_resample
from Analysis.eit_processing import render_reconstruction, calculate_eit_volume
from Analysis.venturi_flow import calculate_volume, infer_flow_direction, venturi_pressure_to_flow
from abi_pyeit.app.utils import *
from abi_pyeit.mesh.utils import *
from config_lib import Config
from itertools import count
from config_lib.utils import cached_caller

"""
abi_eit_protocol.py contains methods for parsing and preprocessing data from our EIT test protocols. It also contains
high level analysis definitions (e.g. linearity test)
"""

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


def linearity_test(data, test_config, test_ginput, eit_config, dataset_config, out=None, cache_pyeit_obj=True):
    if out is None:
        out = {}

    # Create test dataframe
    times = pd.to_timedelta(test_ginput)
    test_data = extract_test_3_data(data, times)

    if test_config["normalize_volume"] == "VC":
        mean_vc = np.average(dataset_config["VC"])
        test_data["Volume delta"] = test_data["Volume delta"] / mean_vc

    if test_config["analysis_max"] > 0:
        test_data = test_data[test_data["Volume delta"] <= test_config["analysis_max"]]

    # Process EIT ------------------------------------------------------------------------------------------------------
    mesh = load_stl(eit_config["mesh_filename"])
    mask_mesh = load_stl(eit_config["mask_filename"]) if eit_config["mask_filename"] is not None else None

    # Place electrodes
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

    # Create pyeit object
    if not cache_pyeit_obj:
        pyeit_obj = JAC(mesh, np.array(electrode_nodes), ex_mat, step=1, perm=1)
    else:
        pyeit_obj = cached_caller(JAC, str, mesh, np.array(electrode_nodes), ex_mat, step=1, perm=1)
    pyeit_obj.setup(p=eit_config["p"], lamb=eit_config["lamb"], method=eit_config["method"])

    # Solve EIT data
    test_data["solution"] = test_data.apply(lambda row: np.real(pyeit_obj.solve(v1=parse_oeit_line(row["EIT In"]),
                                                                                v0=parse_oeit_line(row["EIT Out"]))),
                                            axis=1)

    # Render from solution (mesh + values) to nxn image
    test_data["recon_render"] = render_reconstruction(mesh, test_data["solution"], mask_mesh)

    test_data["area^1.5_normalized"], test_data["threshold_image"] = calculate_eit_volume(test_data["recon_render"], eit_config["image_threshold_proportion"])
    test_data["max_pixels"] = np.sum(np.isfinite(test_data["threshold_image"].iloc[0]))

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


def extract_test_3_data(data, times):
    test_data = pd.DataFrame(columns=["In", "Out"], data=np.array([times[::2], times[1::2]]).T)

    # Time windows where EIT scan occurred
    test_data["In Start"] = test_data.apply(lambda row: data["EIT"].where(data.index > row["In"]).dropna().index[0],
                                            axis=1)
    test_data["In End"] = test_data.apply(lambda row: data["EIT"].where(data.index > row["In"]).dropna().index[1],
                                          axis=1)
    test_data["Out Start"] = test_data.apply(lambda row: data["EIT"].where(data.index > row["Out"]).dropna().index[0],
                                             axis=1)
    test_data["Out End"] = test_data.apply(lambda row: data["EIT"].where(data.index > row["Out"]).dropna().index[1],
                                           axis=1)

    # EIT measurement from each window is the one received at the end of the window
    test_data["EIT In"] = test_data.apply(lambda row: data["EIT"][row["In End"]], axis=1)
    test_data["EIT Out"] = test_data.apply(lambda row: data["EIT"][row["Out End"]], axis=1)

    # Volume for each window is average of measurement within that window
    test_data["In Volume"] = test_data.apply(lambda row: data["Volume (L)"].loc[row["In Start"]:row["In End"]].mean(),
                                             axis=1)
    test_data["Out Volume"] = test_data.apply(
        lambda row: data["Volume (L)"].loc[row["Out Start"]:row["Out End"]].mean(), axis=1)

    # Calculate volume deltas ------------------------------------------------------------------------------------------
    test_data["Volume delta"] = (test_data["In Volume"] - test_data["Out Volume"]).abs()

    test_data = test_data.dropna()
    test_data = test_data.sort_values(by="Volume delta")

    return test_data


def find_last_test_start_and_stop(data, test_name, start_label="Start", stop_label="Stop", join=" "):
    # [::-1] with idxmax() means we find the last index. We want the last index of the start and stop tags because the user might have clicked accidentally.
    # We assume the last index was the correct one
    start = (data[::-1] == (start_label + join + test_name)).idxmax() if (
                data[::-1] == (start_label + join + test_name)).any() else None
    stop = (data[::-1] == (stop_label + join + test_name)).idxmax() if (
                data[::-1] == (stop_label + join + test_name)).any() else None
    return start, stop

