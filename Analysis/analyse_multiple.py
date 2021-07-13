from Analysis.analysis_lib import *
from config_lib import Config
from pandas.core.common import flatten
from tqdm import tqdm
from deepmerge import merge_or_raise
from copy import deepcopy


def main():
    # Load config files -----------------------------------------------------------------------------------------------
    config_constants = Config(config_file, default_config_constants, type="yaml")
    parent_directory = get_directory(config_constants)
    data_directories = list(pathlib.Path(parent_directory).glob(config_constants["subject_directory_glob"]))

    config_variables = Config(config_variables_file, {"base_config_variables": default_base_config_variables,
                                                      "config_variable_modifiers": default_config_variable_modifiers})

    base_config_variables = config_variables["base_config_variables"]
    config_variable_modifiers = config_variables["config_variable_modifiers"]

    # Build configs ---------------------------------------------------------------------------------------------------
    # For each analysis configuration, add a config for each directory.
    analysis_configurations = []
    for modifier in config_variable_modifiers:
        subject_configs = {}
        for directory in data_directories:
            config = deepcopy(base_config_variables)
            merge_or_raise.merge(config, modifier)
            for key in config:
                if isinstance(config[key], dict):
                    # 1 level deep in the config_variables, construct subject specific paths if specified in dict
                    parse_relative_paths(input_dict=config[key], alternate_working_directory=str(directory),
                                         awd_indicator="data_directory", path_tag="filename", wd_tag="_wd")
            subject_configs[directory.name] = config
        analysis_configurations.append(subject_configs)

    #  Load data ------------------------------------------------------------------------------------------------------
    data_dict = {}
    for directory in tqdm(data_directories, desc="Pre-processing data"):
        filename = list(pathlib.Path(directory).glob(config_constants["data_filename_glob"]))[0]
        data, dataset_config = read_and_preprocess_data(filename, config_constants["dataset_config_glob"],
                                                        config_constants["flow_configuration"]["resample_freq_hz"])
        ginput_path = pathlib.Path(filename).parent / pathlib.Path(pathlib.Path(filename).stem + "_ginput.json")
        data_ginput = Config(ginput_path, type="json")

        # Get ginput for all desired tests, either from user or from file
        run_tags_notflat = [config_constants["test_tags"][test] for test in config_constants["run_tests"]]
        run_test_tags = list(set(flatten(run_tags_notflat)))
        for tag in run_test_tags:
            if tag not in data_ginput:
                points = get_input(data, show_columns=["Volume (L)"], test_name=tag)
                data_ginput[tag] = [point[0] for point in points]  # save only times
                data_ginput.save()

        data_dict[str(directory.name)] = {"data": data, "dataset_config": dataset_config,
                                                    "dataset_ginput": data_ginput}

    # Run tests  -------------------------------------------------------------------------------------------------------
    results = []
    # Using a manual tqdm here instead of two nested bars since there is an unresolved bug in tqdm nested bars
    t = tqdm(range(len(analysis_configurations)*len(data_directories)), desc="Analysing data")
    for subject_configs in analysis_configurations:

        single_config_results = {}
        for directory, config in subject_configs.items():
            directory_results = {}

            dataset_information = data_dict[str(directory)]
            dataset_config = dataset_information["dataset_config"]
            data_ginput = dataset_information["dataset_ginput"]
            data = dataset_information["data"]

            if "linearity" in config_constants["run_tests"]:
                lin_out = {}
                linearity_test(data[["Volume (L)", "EIT"]], test_config=config["test_configurations"]["linearity"],
                               test_ginput=data_ginput["Test 3"], eit_config=config["eit_configuration"],
                               dataset_config=dataset_config, out=lin_out, cache_pyeit_obj=True)

                directory_results["linearity"] = lin_out

            if "drift" in config_constants["run_tests"]:
                # do drift analysis
                pass

            single_config_results[str(directory)] = directory_results
            t.update()
        results.append(single_config_results)
    t.close()

    # Save Results -----------------------------------------------------------------------------------------------------
    output = {"config_constants": config_constants, "analysis_configurations": analysis_configurations, "results": results}
    output_filename = create_unique_timestamped_file_name(directory="results", extension=".pickle")

    with open(output_filename, "wb") as f:
        pickle.dump(output, f)
    f.close()


config_file = "configuration/config_multiple.yaml"
default_config_constants = {
    "initial_parent_directory": "",
    "subject_directory_glob": "Subject *",
    "dataset_config_glob": "Subject Information.yaml",
    "data_filename_glob": "?*eit*.csv",
    "test_tags": {
        "linearity": ["Test 3"],
        "drift": ["Test 1", "Test 4"]
    },
    "flow_configuration": {
        "resample_freq_hz": 1000
    },
    # run_tests: ["drift", "linearity"]
    "run_tests": ["linearity"]
}

config_variables_file = "configuration/config_multiple_variables.json"
default_base_config_variables = {
    "eit_configuration": {
        "chest_and_spine_ratio": 2,
        "dist": 3,
        "image_threshold_proportion": 0.15,
        "lamb": 0.4,
        "method": "kotre",
        "n_electrodes": 16,
        "p": 0.5,
        "starting_angle": 0,
        "counter_clockwise": True,
        "mask_filename": None
    },
    "test_configurations": {
        "linearity": {
            "analysis_max": -1,
            "hold": "10s",
            "normalize_volume": "VC"
        }
    }
}
default_config_variable_modifiers = [
    # {
    #     "name": "Generic Chest",
    #     "eit_configuration": {
    #         "mesh_filename": "mesh/mesha06_bumpychestslice_flipped.stl",
    #         "electrode_placement": "equal_spacing_with_chest_and_spine_gap"
    #     }
    # },
    {
        "name": "Oval Chest, Generic Electrodes",
        "eit_configuration": {
            "mesh_filename": "mesh/oval_chest_3.stl",
            "electrode_placement": "equal_spacing_with_chest_and_spine_gap"
        }
    }
    ,
    {
        "name": "Oval Chest, Lidar Electrodes",
        "eit_configuration": {
            "mesh_filename": "mesh/oval_chest_3.stl",
            "electrode_placement": "lidar",
            "electrode_points_filename_wd": "data_directory",
            "electrode_points_filename": "centroids.csv"
        }
    }
    ,
    {
        "name": "Subject Lidar Chest, Generic Electrodes",
        "eit_configuration": {
            "electrode_placement": "equal_spacing_with_chest_and_spine_gap",
            "mesh_filename_wd": "data_directory",
            "mesh_filename": "Lidar Mesh_s.STL",
        },
    },
    {
        "name": "Subject Lidar Chest, Subject Lidar Electrodes",
        "eit_configuration": {
            "electrode_placement": "lidar",
            "electrode_points_filename_wd": "data_directory",
            "electrode_points_filename": "centroids.csv",
            "mesh_filename_wd": "data_directory",
            "mesh_filename": "Lidar Mesh_s.STL",
        },
    },
    # {
    #     "name": "PCA Lungs",
    #     "eit_configuration": {
    #         "mask_directory": "subject_data",
    #         "mask_filename": "PCA_lungs"
    #     },
    # }
]

if __name__ == "__main__":
    main()
