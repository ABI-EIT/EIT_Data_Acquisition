import pickle
import pathlib
import matplotlib.pyplot as plt
from scipy import stats
import numpy as np
from Analysis.analysis_lib import *

config_file = "../configuration/config_analyse.json"


def main():
    config = Config(config_file)
    data_filename = get_filename(config)
    with open(data_filename, "rb") as f:
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


if __name__ == "__main__":
    main()
