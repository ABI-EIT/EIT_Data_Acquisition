from abi_eit_analysis import *
import matplotlib.pyplot as plt
from abi_pyeit.app.utils import *
from abi_pyeit.plotting import create_mesh_plot, update_image_plot
import matplotlib.animation as animation
from config_lib import Config
from config_lib.utils import get_input, parse_relative_paths

"""
analyse_single_trial is a script used to analyse the results of a trial based on our EIT + Venturi Spirometry test procedure.
"""


def main():
    config = Config(config_path, default_config, type="yaml")
    filename = config.get_filename(remember_directory_key="initial_data_directory", prompt="Select a data file")
    parse_relative_paths(config["eit_configuration"], alternate_working_directory=str(pathlib.Path(pathlib.Path(filename).parent)), awd_indicator="data_directory")

    data, dataset_config = read_and_preprocess_data(filename, config["dataset_config_glob"], config["resample_freq_hz"])

    # Construct ginput file name based on data file name
    ginput_name = pathlib.Path(pathlib.Path(filename).stem + "_ginput.json")
    ginput_path = pathlib.Path(filename).parent / ginput_name
    data_ginput = Config(ginput_path, type="json")

    # Get ginput for all desired tests, either from user or from file
    for test in config["tests"]:
        if test not in data_ginput:
            start, stop = find_last_test_start_and_stop(data["Tag"], test)
            points = get_input(data[start:stop], show_columns=["Volume (L)"], test_name=test)
            data_ginput[test] = [point[0] for point in points]  # save only times
            data_ginput.save()

    # Run linearity test
    lin_out = {}
    linearity_test(data[["Volume (L)", "EIT"]], test_config=config["tests"]["Test 3"],
                   test_ginput=data_ginput["Test 3"], eit_config=config["eit_configuration"], dataset_config=dataset_config, out=lin_out)


    # Plotting ---------------------------------------------------------------------------------------------------------
    fig, ax = plt.subplots()
    create_mesh_plot(ax, lin_out["mesh"], electrodes=lin_out["electrode_nodes"])

    # Plot volume with EIT frames
    fig, ax = plt.subplots()
    data["Volume (L)"].plot(ax=ax)
    ax.plot(data["Volume (L)"].where(data["EIT"].notna()).dropna(), "rx")
    # ax.plot(data["Flow1 (L/s)"])
    ax.set_title("Expiration volume with EIT frame times")
    ax.set_ylabel("Volume (L)")

    # Linearity test plots
    recon_min = np.nanmin(lin_out["df"]["recon_render"].apply(np.nanmin))
    recon_max = np.nanmax(lin_out["df"]["recon_render"].apply(np.nanmax))

    # Create animated plots
    fig, _ = plt.subplots()
    ani1 = animation.FuncAnimation(fig, update_image_plot, fargs=(fig, [v.T for v in lin_out["df"]["recon_render"].values], {"title":"Threshold image animation",
                                   "vmin": recon_min, "vmax": recon_max}), frames=len(lin_out["df"]["recon_render"].values), interval=500, repeat_delay=500)

    fig, _ = plt.subplots()
    ani2 = animation.FuncAnimation(fig, update_image_plot, fargs=(fig, [v.T for v in lin_out["df"]["threshold_image"].values], {"title":"Threshold image animation"}),
                                   frames=len(lin_out["df"]["threshold_image"].values), interval=500, repeat_delay=500)

    # # Save animations
    writer_gif = animation.PillowWriter(fps=2, bitrate=2000)
    ani1.save(str(pathlib.Path(filename).parent) + "\\" + "Reconstruction image animation.gif", writer_gif, dpi=1000)
    ani2.save(str(pathlib.Path(filename).parent) + "\\" + "Threshold image animation.gif", writer_gif, dpi=1000)

    fig, ax = plt.subplots()
    ax.plot(lin_out["df"]["Volume delta"], lin_out["df"]["area^1.5_normalized"], ".")
    ax.plot(lin_out["df"]["Volume delta"], lin_out["df"]["calculated"])
    ax.text(0.8, 0.1, "R^2 = {0:.4}".format(lin_out["r_squared"]), transform=ax.transAxes)
    if config["tests"]["Test 3"]["normalize_volume"] == "VC":
        ax.set_title("Volume delta (normalized to vital capacity) \nvs EIT image area^1.5")
        ax.set_xlabel("Volume delta normalized to vital capacity")
        ax.set_ylabel("EIT image area (pixels)^1.5/max_pixels^1.5")
        ax.figure.tight_layout(pad=1)

    # # Save data
    # lin_out["df"][["Volume delta", "area^1.5_normalized"]].to_csv(str(pathlib.Path(filename).parent) + "\\" + "eit_vs_volume.csv")

    plt.show()

# Default configurations -----------------------------------------------------
# Don't change these to configure a single test! Change settings in the config file!
configuration_directory = "configuration/"
config_file = "config_single.yaml"
config_path = configuration_directory + config_file
default_config = {
    "dataset_config_glob": "Subject Information.yaml",
    "tests": {
        "Test 3": {"analysis_max": -1, "normalize_volume": "VC"}
    },
    "eit_configuration": {
        # "mesh_filename_wd": "data_directory",
        "mesh_filename": "mesh/oval_chest_3.stl",
        "n_electrodes": 16,
        "dist": 3,
        # Recon:
        "p": 0.5,
        "lamb": 0.4,
        "method": "kotre",
        # Electrode placement:
        "electrode_placement": "equal_spacing_with_chest_and_spine_gap",
        "chest_and_spine_ratio": 2,
        "starting_angle": 0,
        "counter_clockwise": True,
        # Analysis:
        "image_threshold_proportion": .15,
        "mask_filename": None
    },
    "resample_freq_hz": 1000
}


if __name__ == "__main__":
    main()
