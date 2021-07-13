from Analysis.analysis_lib import *
import matplotlib.pyplot as plt
from abi_pyeit.app.eit import *
from abi_pyeit.quality.plotting import *
import math
import matplotlib.animation as animation
from config_lib import Config


def main():
    config = Config(config_path, default_config, type="json")

    # Load data and background with file select dialogs
    data_filename = get_filename(config, key="data")
    if config["background_type"] == "file":
        background_filename = get_filename(config, key="background", remember_directory=False)
        config["initial_background_directory"] = config["initial_data_directory"]
        background = load_oeit_data(background_filename)
    else:
        background = None
    data = load_oeit_data(data_filename)

    # Initialize EIT
    parse_relative_paths(config["eit_configuration"], alternate_working_directory=str(pathlib.Path(pathlib.Path(data_filename).parent)), awd_indicator="data_directory")
    pyeit_obj = initialize_eit(config["eit_configuration"], electrode_placement=config["eit_configuration"]["electrode_placement"])

    # Solve
    solve_keys = ["normalize"]
    solve_kwargs = {k: config["eit_configuration"][k] for k in solve_keys if k in config["eit_configuration"]}
    eit_images = [pyeit_obj.solve(frame, background[0], **solve_kwargs) for frame in data]

    # Create plot
    fig, imgs = create_plot(eit_images, pyeit_obj)
    ani = animation.ArtistAnimation(fig, imgs, interval=181, repeat_delay=500)

    # Save gif
    writer = animation.PillowWriter(fps=int(1000/181))
    if not os.path.exists(results_directory):
        os.mkdir(results_directory)
    ani.save(results_directory+result_filename, writer, dpi=1000)

    plt.show()


# Default configurations -----------------------------------------------------
# Don't change these to configure a single test! Change settings in the config file!
results_directory = r"results\\"
result_filename = "result.gif"
config_file = r"configuration\process_eit.json"
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