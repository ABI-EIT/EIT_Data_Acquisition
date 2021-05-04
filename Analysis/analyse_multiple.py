from Analysis.analysis_lib import *
from config_lib import Config
from pandas.core.common import flatten
from tqdm import tqdm
from deepmerge import merge_or_raise
from copy import deepcopy

config_constants = {
    "config_file": "configuration/config_multiple.yaml",
    "subject_directory_glob": "Subject *",
    "dataset_config_glob": "Subject Information.yaml",
    "data_filename_glob": "?*eit*.csv",
    # "meshes": {
    #     "generic_chest": "mesh/mesha06_bumpychestslice.stl",
    #     "oval": "mesh/oval_chest_3.stl",
    #     "generic_lungs": "mesh/"
    # },
    "test_tags": {
        "linearity": ["Test 3"],
        "drift": ["Test 1", "Test 4"]
    },
    "flow_configuration": {
        "resample_freq_hz": 1000
    },
    "codes": [
        "JB2",
        "AC2",
        "LS1",
        "SR3",
        "MW1",
        "HR1"
    ]
}

config_variables = {
    "eit_configuration": {
        "chest_and_spine_ratio": 2,
        "dist": 3,
        "image_threshold_proportion": 0.15,
        "lamb": 0.4,
        "method": "kotre",
        "n_electrodes": 16,
        "p": 0.5,
        "starting_angle": 0,
        "counter_clockwise": True
    },
    "test_configurations": {
        "linearity": {
            "analysis_max": -1,
            "hold": "10s",
            "normalize_volume": "VC"
        }
    }
}

# run_tests = ["drift", "linearity"]
run_tests = ["linearity"]
config_variable_updates = [
    {
        "name": "Generic Chest",
        "eit_configuration": {
            "mesh_filename": "mesh/mesha06_bumpychestslice_flipped.stl",
            "electrode_placement": "equal_spacing_with_chest_and_spine_gap",
            "mask": "none"
        }
    },
    {
        "name": "Oval Chest",
        "eit_configuration": {
            "mesh_filename": "mesh/oval_chest_3.stl",
            "electrode_placement": "equal_spacing_with_chest_and_spine_gap",
            "mask": "none"
        }
    }
    # ,
    # {
    #     "mesh": "generic_chest",
    #     "electrode_placement": "subject_lidar",
    #     #But where do we apply this mapping?
    #     "electrode_placement_file_relative_path": "data_directory",
    #     "electrode_placement_file_name": "electrode_points.csv"
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


def main():
    cc = config_constants

    config = Config(cc["config_file"], type="yaml")
    parent_directory = load_directory(config)
    directories = list(pathlib.Path(parent_directory).glob(cc["subject_directory_glob"]))

    # Build configs
    config_variables_list = []
    for update in config_variable_updates:

        directories_config_dict = {}
        for directory in directories:
            cv = deepcopy(config_variables)
            merge_or_raise.merge(cv, update)

            # Parse filenames here
            # For each variable that uses a filename
            #   If the relative flag is set
            #       filename = directory + filename
            #   Else
            #       filename is unchanged

            directories_config_dict[directory] = cv

        config_variables_list.append(directories_config_dict)



    # Preprocess all data files and get all ginput
    dataset_information_dict = {}
    for directory in tqdm(directories, desc="Pre-processing data"):
        filename = list(pathlib.Path(directory).glob(cc["data_filename_glob"]))[0]

        data, dataset_config = read_and_preprocess_data(filename, cc["dataset_config_glob"], cc["flow_configuration"]["resample_freq_hz"])

        # Construct ginput file name based on data file name
        ginput_name = pathlib.Path(pathlib.Path(filename).stem + "_ginput.json")
        ginput_path = pathlib.Path(filename).parent / ginput_name
        data_ginput = Config(ginput_path, type="json")

        # Get ginput for all desired tests, either from user or from file
        run_tags_notflat = [cc["test_tags"][test] for test in run_tests]
        run_test_tags = list(set(flatten(run_tags_notflat)))
        for tag in run_test_tags:
            if tag not in data_ginput:
                points = get_input(data, show_columns=["Volume (L)"], test_name=tag)
                data_ginput[tag] = [point[0] for point in points]  # save only times
                data_ginput.save()

        dataset_information_dict[str(directory)] = {"data": data, "dataset_config": dataset_config,
                                                    "dataset_ginput": data_ginput}

    # Run each test configuration on all data
    results = []
    for directories_config_dict in tqdm(config_variables_list, desc="Analysis configurations"):

        single_config_results = {}
        for directory, cv in tqdm(directories_config_dict.items(), desc="Data sets"):
            directory_results = {}

            dataset_information = dataset_information_dict[str(directory)]
            dataset_config = dataset_information["dataset_config"]
            data_ginput = dataset_information["dataset_ginput"]
            data = dataset_information["data"]

            if "linearity" in run_tests:
                lin_out = {}
                linearity_test(data[["Volume (L)", "EIT"]], test_config=cv["test_configurations"]["linearity"],
                               test_ginput=data_ginput["Test 3"], eit_config=cv["eit_configuration"],
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
            df.plot(x="Volume delta", y="area^1.5_normalized", label=cc["codes"][j], ax=ax)

        ax.set_ylabel("EIT area^1.5 normalized")
        ax.set_xlabel("Volume delta normalized")
        ax.set_title(f"EIT vs Volume delta for {len(cc['codes'])} subjects, {config_variable_updates[i]['name']}")

        r2s = [item[1]["linearity"]["r_squared"] for item in list(result.items())]
        print(f"Mean r squared for configuration {config_variable_updates[i]['name']}: {np.average(r2s):.4f}")

    plt.show()


if __name__ == "__main__":
    main()
