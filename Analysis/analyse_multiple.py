from Analysis.analysis_lib import *
from config_lib import Config
from pandas.core.common import flatten
from tqdm import tqdm
from deepmerge import merge_or_raise
from copy import deepcopy
from scipy import stats

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
    }
}

base_config_variables = {
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

# run_tests = ["drift", "linearity"]
run_tests = ["linearity"]
config_variable_modifiers = [
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
            "mesh_filename": "Lidar Mesh.STL",
        },
    },
    {
        "name": "Subject Lidar Chest, Subject Lidar Electrodes",
        "eit_configuration": {
            "electrode_placement": "lidar",
            "electrode_points_filename_wd": "data_directory",
            "electrode_points_filename": "centroids.csv",
            "mesh_filename_wd": "data_directory",
            "mesh_filename": "Lidar Mesh.STL",
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


def main():
    cc = config_constants

    config = Config(cc["config_file"], type="yaml")
    parent_directory = load_directory(config)
    directories = list(pathlib.Path(parent_directory).glob(cc["subject_directory_glob"]))

    # Build configs
    config_variables_list = []
    for update in config_variable_modifiers:

        directories_config_dict = {}
        for directory in directories:
            cv = deepcopy(base_config_variables)
            merge_or_raise.merge(cv, update)

            for key in cv:
                if isinstance(cv[key], dict):
                    parse_relative_paths(input_dict=cv[key], alternate_working_directory=str(directory), awd_indicator="data_directory", path_tag="filename", wd_tag="_wd")

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
    # Using a manual tqdm here instead of two nested bars since there is an unresolved bug in tqdm nested bars
    t = tqdm(range(len(config_variables_list)*len(directories_config_dict)), desc="Analysing data")
    for directories_config_dict in config_variables_list:

        single_config_results = {}
        for directory, cv in directories_config_dict.items():
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
            t.update()
        results.append(single_config_results)
    t.close()

    dirnames = [pathlib.Path(path).name for path in list(results[0])]
    test_names = [list(item.values())[0]['name'] for item in config_variables_list]

    r2s_list = []
    for i, result in enumerate(results):
        dfs = [item[1]["linearity"]["df"] for item in list(result.items())]

        fig, ax = plt.subplots()
        for j, df in enumerate(dfs):
            df.plot(x="Volume delta", y="area^1.5_normalized", label=dirnames[j].split(" - ")[0], ax=ax)

        ax.set_ylabel("EIT area^1.5 normalized")
        ax.set_xlabel("Volume delta normalized")
        ax.set_title(f"EIT vs Volume delta for {len(dirnames)} subjects, {test_names[i]}")

        r2s = [result[key]["linearity"]["r_squared"] for key in result]
        r2s_list.append(r2s)
        # print(f"Mean r squared for configuration {config_variable_modifiers[i]['name']}: {np.average(r2s):.4f}")
        # print(f"r squared values for configuration {config_variable_modifiers[i]['name']}: {r2s}")

        ax.text(0.3, 0.05, r'Mean $r^2$' + f' = {np.average(r2s):.4f}')

    sems = [stats.sem(r2s) for r2s in r2s_list]
    ttests = [stats.ttest_ind(r2s_list[0], r2s, equal_var=False) for r2s in r2s_list[1:]]
    r2means = [np.mean(r2s) for r2s in r2s_list]

    fig, ax = plt.subplots()
    y_pos = np.arange(len(r2means))
    ax.barh(y_pos, r2means, align="center", xerr=sems)
    ax.set_yticks(y_pos)
    ax.invert_yaxis()
    test_names_linebreak = []
    for i, name in enumerate(test_names):
        test_names_linebreak.append(name.replace(", ", "\n"))
    ax.set_yticklabels(test_names_linebreak)
    ax.set_xlim(0, 1)
    ax.set_xlabel(r'Mean $r^2$')
    ax.set_ylabel("Analysis Conditions")
    ax.set_title(r'Mean $r^2$ for EIT Area$^{1.5}$ vs Volume Delta' + "\n (Error Bars Show SEM)")
    fig.tight_layout()

    for i, ttest in enumerate(ttests):
        print(f"p-value for t-test between {test_names[0]} and {test_names[i+1]} is {ttest.pvalue:.4f}")


    plt.show()


if __name__ == "__main__":
    main()
