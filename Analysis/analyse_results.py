import pickle
import pathlib
import matplotlib.pyplot as plt
from scipy import stats
import numpy as np

data_filename = "results/data_four_configs.pickle"

with open(data_filename, "rb") as f:
    data = pickle.load(f)

f.close()

cc = data["config_constants"]
config_variables_list = data["config_variables_list"]
directories_config_dict = data["directories_config_dict"]
results = data["results"]

test_names = [list(item.values())[0]['name'] for item in config_variables_list]
dirnames = [pathlib.Path(path).name for path in list(results[0])]

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
    print(f"p-value for t-test between {test_names[0]} and {test_names[i + 1]} is {ttest.pvalue:.4f}")

stds = [np.std(r2s) for r2s in r2s_list]

plt.show()
