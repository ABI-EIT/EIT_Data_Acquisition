import pandas as pd
import matplotlib.pyplot as plt


files = [
    r"C:\Users\acre018\The University of Auckland\ABI MBIE EIT Project - General\Healthy Volunteer Studies\Data\Subject 3 - JB1\eit_vs_volume.csv",
    r"C:\Users\acre018\The University of Auckland\ABI MBIE EIT Project - General\Healthy Volunteer Studies\Data\Subject 4 - AC2\eit_vs_volume.csv",
    r"C:\Users\acre018\The University of Auckland\ABI MBIE EIT Project - General\Healthy Volunteer Studies\Data\Subject 5 - LS1\eit_vs_volume.csv",
    r"C:\Users\acre018\The University of Auckland\ABI MBIE EIT Project - General\Healthy Volunteer Studies\Data\Subject 6 - SR3\eit_vs_volume.csv",
    r"C:\Users\acre018\The University of Auckland\ABI MBIE EIT Project - General\Healthy Volunteer Studies\Data\Subject 8 - MW1\eit_vs_volume.csv",
]
codes = [
    "JB1",
    "AC2",
    "LS1",
    "SR3",
    "MW1"
]

dfs = [pd.read_csv(file, index_col=0) for file in files]

fig, ax = plt.subplots()
for i, df in enumerate(dfs):
    df.plot(x="Volume delta", y="area^1.5_normalized", label=codes[i], ax=ax)

ax.set_ylabel("EIT area^1.5 normalized")
ax.set_xlabel("Volume delta normalized")
ax.set_title("EIT vs Volume delta for 5 subjects")

plt.show()