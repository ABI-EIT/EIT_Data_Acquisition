from Analysis.abi_eit_protocol import *
from config_lib import Config
from pandas.core.common import flatten
from tqdm import tqdm
from deepmerge import merge_or_raise
from copy import deepcopy
from PyQt5 import QtWidgets, uic
import sys
import matplotlib.pyplot as plt
from config_lib.utils import get_input, get_directory, parse_relative_paths, create_unique_timestamped_file_name
from scipy import stats

"""
analyse_multiple is a script used to analyse multiple datasets and configurations from our EIT + Venturi Spirometry test protocol.
processed data is saved in a pickle. 
"""

Ui_MainWindow, QMainWindow = uic.loadUiType("layout/analyse_multiple.ui")


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.setupUi(self)

        self.config_constants = Config(config_file, default_config_constants, type="yaml")
        self.config_variables = Config(config_variables_file, {"base_config_variables": default_base_config_variables,
                                                               "config_variable_modifiers": default_config_variable_modifiers})
        if "initial_data_directory" in self.config_constants:
            self.data_directory_line_edit.setText(self.config_constants["initial_data_directory"])

        self.data_directory_tool_button.clicked.connect(self.get_data_directory)
        self.results_file_tool_button.clicked.connect(self.get_results_file)

        self.run_analysis_button.clicked.connect(lambda: self.run_analysis(self.data_directory_line_edit.text()))
        self.analyse_results_button.clicked.connect(lambda: self.analyse_results(self.results_file_line_edit.text()))

    def get_data_directory(self):
        try:
            d = get_directory(self.config_constants)
            self.data_directory_line_edit.setText(d)
        except (FileNotFoundError, ValueError) as e:
            print(e)

    def get_results_file(self):
        try:
            f, _ = QtWidgets.QFileDialog.getOpenFileName(self, directory=results_directory)
            self.results_file_line_edit.setText(f)
        except (FileNotFoundError,) as e:
            print(e)

    def run_analysis(self, directory):
        if os.path.isdir(directory):
            run_analysis(directory, self.config_constants, self.config_variables)

    def analyse_results(self, file):
        if os.path.isfile(file):
            analyse_results(file)


def run_analysis(parent_directory, config_constants, config_variables):

    data_directories = list(pathlib.Path(parent_directory).glob(config_constants["subject_directory_glob"]))
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
                start, stop = find_last_test_start_and_stop(data["Tag"], tag)
                points = get_input(data[start:stop], show_columns=["Volume (L)"], test_name=tag)
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
    output_filename = create_unique_timestamped_file_name(directory=results_directory, extension=".pickle")

    with open(output_filename, "wb") as f:
        pickle.dump(output, f)
    f.close()

    analyse_results(output_filename)


def analyse_results(results_filename):
    with open(results_filename, "rb") as f:
        data = pickle.load(f)
    f.close()

    config_constants = data["config_constants"]
    analysis_configurations = data["analysis_configurations"]
    results = data["results"]

    test_names = [list(item.values())[0]['name'] for item in analysis_configurations]
    dirnames = [pathlib.Path(path).name for path in list(results[0])]

    if "linearity" in config_constants["run_tests"]:

        r2s_list = [[item["linearity"]["r_squared"] for _, item in list(result.items())] for result in results]
        # For each analysis config, create a plot with all the volume vs eit data
        for i, result in enumerate(results):
            dfs = [item["linearity"]["df"] for _, item in list(result.items())]
            fig, ax = plt.subplots()
            for j, df in enumerate(dfs):
                # df.plot(x="Volume delta", y="area^1.5_normalized", label=dirnames[j].split(" - ")[0], ax=ax)
                df.plot(x="Volume delta", y="area^1.5_normalized", label=dirnames[j], ax=ax)
            ax.set_ylabel("EIT area^1.5 normalized")
            ax.set_xlabel("Volume delta normalized")
            ax.set_title(f"EIT vs Volume delta for {len(dirnames)} datasets,\n {test_names[i]}")
            r2s = [result[key]["linearity"]["r_squared"] for key in result]
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
            print(f"p-value for t-test between {test_names[0]} and {test_names[i + 1]} is {ttest.pvalue:.4f}")

        stds = [np.std(r2s) for r2s in r2s_list]

        # Calculate ratios between lidar mesh and oval mesh
        area_ratios = {}
        for subject in dirnames:
            df = results[2][subject]['linearity']['df']
            lidar_area = np.sum(np.isfinite(df["max_pixels"].iloc[0]))

            df_2 = results[0][subject]['linearity']['df']
            oval_area = np.sum(np.isfinite(df_2["max_pixels"].iloc[0]))
            area_ratios[subject] = lidar_area / oval_area

        # Calculate error in electrode placement measured by lidar compared to equal spaced
        electrode_errors = {}
        for subject in dirnames:
            lin_result_eq = results[0][subject]['linearity']
            centroid_eq = lin_result_eq['place_electrodes']['centroid']
            electrode_positions_eq = lin_result_eq['mesh']['node'][lin_result_eq['electrode_nodes']] - centroid_eq
            angles_eq = np.arctan(electrode_positions_eq[:, 0] / electrode_positions_eq[:, 1])

            lin_result_lid = results[1][subject]['linearity']
            centroid_lid = trimesh.Trimesh(lin_result_lid['mesh']['node'], lin_result_lid['mesh']['element']).centroid
            electrode_positions_lid = lin_result_lid['mesh']['node'][lin_result_lid['electrode_nodes']] - centroid_lid
            angles_lid = np.arctan(electrode_positions_lid[:, 0] / electrode_positions_lid[:, 1])

            ers = angles_lid - angles_eq
            electrode_errors[subject] = float(np.mean(np.abs(ers)))

    plt.show()

results_directory = "results/"
config_file = "../configuration/config_multiple.yaml"
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

config_variables_file = "../configuration/config_multiple_variables.json"
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
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    main_window.setWindowTitle("Analyse Multiple")
    dw = QtWidgets.QDesktopWidget()

    main_window.show()
    app.exec()
