from Analysis.abi_eit_protocol import *
import matplotlib.pyplot as plt
from abi_pyeit.app.utils import *
from abi_pyeit.plotting import create_mesh_plot, update_image_plot, update_plot, create_plot
from config_lib import Config
from scipy.fft import rfft, rfftfreq
from Analysis.eit_processing import initialize_eit
from config_lib.utils import get_filename, parse_relative_paths
import matplotlib.animation as animation

"""
process_eit_data.py is a script used to process a series of EIT frames
"""

def main():
    config = Config(config_path, default_config, type="json")

    # Load data and background with file select dialogs
    try:
        data_filename = get_filename(config, key="data")
        data = pd.read_csv(data_filename, index_col=0, low_memory=False).dropna(how="all")
        data.index = pd.to_datetime(data.index, unit=ABI_EIT_time_unit)
        data.index = data.index - data.index[0]
        data["EIT"] = [parse_oeit_line(row)for row in data["EIT"]]
        if config["background_type"] == "file":
            background_filename = get_filename(config, key="background", remember_directory=False)
            config["initial_background_directory"] = config["initial_data_directory"]
            background = load_oeit_data(background_filename)[0]
        elif config["background_type"] == "max_magnitude":
            background = data["EIT"].iloc[data["EIT"].apply(lambda row: row[0]).argmax()]
        else:
            background = None
    except (ValueError, FileNotFoundError):
        print("Error loading files")
        exit(1)
    # Initialize EIT
    parse_relative_paths(config["eit_configuration"], alternate_working_directory=str(pathlib.Path(pathlib.Path(data_filename).parent)), awd_indicator="data_directory")
    pyeit_obj = initialize_eit(config["eit_configuration"], electrode_placement=config["eit_configuration"]["electrode_placement"])

    # Solve
    solve_keys = ["normalize"]
    solve_kwargs = {k: config["eit_configuration"][k] for k in solve_keys if k in config["eit_configuration"]}
    eit_images = [pyeit_obj.solve(frame, background, **solve_kwargs) for frame in data["EIT"]]

    # Volume calculations ----------------------------------
    recon_render = render_reconstruction(pyeit_obj.mesh, eit_images, resolution=(100, 100))

    volume, threshold_images = calculate_eit_volume(pd.Series(data=recon_render), config["eit_configuration"]["image_threshold_proportion"])
    data["Volume"] = volume

    # Frequency analysis
    sample_freq = 5.5
    data = squash_and_resample(data, freq_column="Volume", resample_freq_hz=5.5)
    data["Volume High Pass"] = filter_data(data["Volume"], fs=sample_freq, fc=0.1, how="high")
    vol_fft = rfft(data["Volume High Pass"].values)
    vol_fft_freq = rfftfreq(len(data), 1/sample_freq)
    max_power_index = np.argmax(np.abs(vol_fft))
    max_power_freq = vol_fft_freq[max_power_index]

    # Group by the max power period and average
    period = 1/max_power_freq
    sample_period = 1/5.5
    multiple = round(period/sample_period)
    # Have to do the EIT column separately or pandas complains that there are no numerical values to aggregate. WTF???
    EIT_groupby = data.groupby(by=lambda rowindex: rowindex % (data.index.freq * multiple))["EIT"].apply(np.mean)
    data_grouped = data.groupby(by=lambda rowindex: rowindex % (data.index.freq * multiple)).mean()
    data_grouped["EIT"] = EIT_groupby

    # Re-reconstruct using averaged EIT frames
    background = data_grouped["EIT"].iloc[data_grouped["EIT"].apply(np.max).argmax()]
    eit_images_averaged = [pyeit_obj.solve(frame, background, **solve_kwargs) for frame in data_grouped["EIT"]]

    # Recalculate volume
    recon_render_averaged = render_reconstruction(pyeit_obj.mesh, eit_images_averaged, resolution=(1000, 1000))
    volume, threshold_images = calculate_eit_volume(pd.Series(data=recon_render_averaged), config["eit_configuration"]["image_threshold_proportion"])
    data_grouped["Volume Averaged"] = volume

    # Plot Volume ----------------------------------------------------------
    fig, ax = plt.subplots()
    ax.plot(data.index.total_seconds(), data["Volume"])
    ax.set_title("EIT Volume vs time")
    ax.set_xlabel("Time (s)")

    fig, ax = plt.subplots()
    ax.plot(data.index.total_seconds(), data["Volume High Pass"])
    ax.set_title("EIT Volume high pass vs time (cuttoff 0.1Hz)")
    ax.set_xlabel("Time (s)")

    fig, ax = plt.subplots()
    ax.plot(vol_fft_freq, np.abs(vol_fft))
    ax.set_title("EIT Volume FFT")
    ax.set_xlabel("Frequency (Hz)")

    # Plot EIT image at max volume
    fig, ax = plt.subplots()
    ax.plot(data_grouped.index.total_seconds(), data_grouped["Volume Averaged"])
    ax.set_title("EIT (averaged) Volume vs time")
    ax.set_xlabel("Time (s)")

    fig, ax = plt.subplots()
    image = eit_images[data["Volume"].argmax()]
    create_plot(ax, image, eit_obj=pyeit_obj, vmin=np.min(image), vmax=np.max(image))

    fig, ax = plt.subplots()
    image = eit_images_averaged[data_grouped["Volume"].argmax()]
    create_plot(ax, image, eit_obj=pyeit_obj, vmin=np.min(image), vmax=np.max(image), title="EIT (averaged) plot")


    # # Create animated -----------------------------------------------------------------------------------
    # fig, _ = plt.subplots()
    # ani = animation.FuncAnimation(fig, update_plot, frames=len(eit_images), interval=181, repeat_delay=500,
    #                               fargs=(fig, eit_images, pyeit_obj, {"vmax": np.max(eit_images), "vmin": np.min(eit_images),
    #                                                                   "title": "EIT animation raw"}))
    #
    # fig, _ = plt.subplots()
    # ani1 = animation.FuncAnimation(fig, update_plot, frames=len(eit_images_averaged), interval=181, repeat_delay=500,
    #                               fargs=(fig, eit_images_averaged, pyeit_obj, {"vmax": np.max(eit_images_averaged), "vmin": np.min(eit_images_averaged),
    #                                                                            "title": "EIT animation averaged"}))
    #
    # fig, _ = plt.subplots()
    # ani2 = animation.FuncAnimation(fig, update_image_plot, frames=len(threshold_images), interval=181, repeat_delay=500,
    #                                fargs=(fig, [i.T for i in threshold_images], {"title": "Threshold Image Plot"}))
    #
    # # Save gif
    # writer = animation.PillowWriter(fps=int(1000/181))
    # if not os.path.exists(results_directory):
    #     os.mkdir(results_directory)
    # ani.save(results_directory+result_filename, writer, dpi=1000)

    plt.show()

# Default configurations -----------------------------------------------------
# Don't change these to configure a single test! Change settings in the config file!
results_directory = r"results\\"
result_filename = "result.gif"
config_file = r"configuration/process_eit.json"
config_path = config_file
default_config = {
    "background_type": "file",
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
        "electrode_placement": "equal_spacing",
        "chest_and_spine_ratio": 2,
        "starting_angle": 0,
        "counter_clockwise": True,
        # Analysis:
        "image_threshold_proportion": .15,
        "mask_filename": None
    }
}


if __name__ == "__main__":
    main()
