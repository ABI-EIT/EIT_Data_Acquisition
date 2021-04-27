from Analysis.analysis_lib import *
from config_lib import Config
from pandas.core.common import flatten
from tqdm import tqdm

configuration_directory = "configuration/"
config_file = "config_multiple.yaml"
config_path = configuration_directory + config_file

subject_directory_glob = "Subject *"
dataset_config_glob = "Subject Information.yaml"
data_filename_glob = "?*eit*.csv"

meshes = {
    "generic_chest": "mesh/mesha06_bumpychestslice.stl",
    "oval": "mesh/oval_chest_3.stl",
    "generic_lungs": "mesh/"
}
eit_configuration = {
  "chest_and_spine_ratio": 2,
  "dist": 3,
  "image_threshold_proportion": 0.15,
  "lamb": 0.4,
  "method": "kotre",
  "n_electrodes": 16,
  "p": 0.5
}
resample_freq_hz = 1000
test_configurations = {
  "linearity": {
    "analysis_max": -1,
    "hold": "10s",
    "normalize_volume": "VC"
    }
}
test_tags = {
    "linearity": ["Test 3"],
    "drift": ["Test 1", "Test 4"]
}

# run_tests = ["drift", "linearity"]
run_tests = ["linearity"]
run_configurations = [
    {
        "name": "Generic Chest",
        "mesh": "generic_chest",
        "electrode_placement": "equal_spaced_single_gap_chest_and_spine",
        "mask": "none"
    },
    {
        "name": "Oval Chest",
        "mesh": "oval",
        "electrode_placement": "equal_spaced_single_gap_chest_and_spine",
        "mask": "none"
    }
    # ,
    # {
    #     "mesh": "generic_chest",
    #     "electrode_placement": "subject_lidar"
    # },
    # {
    #     "mesh": "subject_lidar"
    # },
    # {
    #     "mesh": "subject_pca"
    # },
    # {
    #     "mesh": "generic_chest",
    #     "mask": "generic_lungs"
    # }
]


codes = [
    "JB1",
    "AC2",
    "LS1",
    "SR3",
    "MW1",
    "HR1"
]

def main():
    config = Config(config_path, type="yaml")
    parent_directory = load_directory(config)
    directories = list(pathlib.Path(parent_directory).glob(subject_directory_glob))

    # Preprocess all data files and get all ginput
    dataset_information_dict = {}
    for directory in tqdm(directories, desc="Pre-processing data"):
        filename = list(pathlib.Path(directory).glob(data_filename_glob))[0]

        data, dataset_config = read_and_preprocess_data(filename, dataset_config_glob, resample_freq_hz)

        # Construct ginput file name based on data file name
        ginput_name = pathlib.Path(pathlib.Path(filename).stem + "_ginput.json")
        ginput_path = pathlib.Path(filename).parent / ginput_name
        data_ginput = Config(ginput_path, type="json")

        # Get ginput for all desired tests, either from user or from file
        run_tags_notflat = [test_tags[test] for test in run_tests]
        run_test_tags = list(set(flatten(run_tags_notflat)))
        for tag in run_test_tags:
            if tag not in data_ginput:
                points = get_input(data, show_columns=["Volume (L)"], test_name=tag)
                data_ginput[tag] = [point[0] for point in points]  # save only times
                data_ginput.save()

        dataset_information_dict[str(directory)] = {"data": data, "dataset_config": dataset_config, "dataset_ginput": data_ginput}

    # Run each test configuration on all data
    results = []
    for run_configuration in tqdm(run_configurations, desc="Analysis configurations"):
        single_config_results = {}
        for directory in tqdm(directories, desc="Data sets"):
            directory_results = {}
            single_eit_config = eit_configuration.copy()
            configure_run(run_configuration, single_eit_config)

            dataset_information = dataset_information_dict[str(directory)]
            dataset_config = dataset_information["dataset_config"]
            data_ginput = dataset_information["dataset_ginput"]
            data = dataset_information["data"]

            if "linearity" in run_tests:
                lin_out = {}
                linearity_test(data[["Volume (L)", "EIT"]], test_config=test_configurations["linearity"],
                               test_ginput=data_ginput["Test 3"], eit_config=single_eit_config,
                               dataset_config=dataset_config, out=lin_out, cache_pyeit_obj=True)

                directory_results["linearity"] = lin_out

            if "drift" in run_tests:
                # do drift analysis
                pass

            single_config_results[str(directory)] = directory_results
        results.append(single_config_results)

    for i, result in enumerate(results):
        dfs = [item[1]["linearity"]["df"] for item in list(result.items())]

        fig, ax = plt.subplots()
        for j, df in enumerate(dfs):
            df.plot(x="Volume delta", y="area^1.5_normalized", label=codes[j], ax=ax)

        ax.set_ylabel("EIT area^1.5 normalized")
        ax.set_xlabel("Volume delta normalized")
        ax.set_title(f"EIT vs Volume delta for {len(codes)} subjects, {run_configurations[i]['name']}")

        r2s = [item[1]["linearity"]["r_squared"] for item in list(result.items())]
        print(f"Mean r squared for configuration {run_configurations[i]['name']}: {np.average(r2s):.4f}")

    plt.show()

def configure_run(run_configuration, eit_configuration):
    """
    Edit the configuration parameters according to the requirements for this iteration.

    More input arguments will be needed in future (maybe)

    Parameters
    ----------
    run_configuration
    eit_configuration
    """
    if run_configuration["mesh"] == "generic_chest":
        eit_configuration["mesh_filename"] = meshes["generic_chest"]
    elif run_configuration["mesh"] == "oval":
        eit_configuration["mesh_filename"] = meshes["oval"]
    else:
        raise ValueError("Invalid mesh configuration")


if __name__ == "__main__":
    main()

# ask user for the data directory then save it in a config

# Open all subject data files and check for ginput
# for each configuration, for each subject, for each test. Run code. TDQM on these three levels
# analyse summary
