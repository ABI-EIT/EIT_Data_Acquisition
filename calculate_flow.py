import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import integrate


# file_name = "data/2021-02-23T13_35_eit_data.csv"  #out one side then out other side with calibrated volume
# file_name = "data/2021-02-23T13_40_eit_data.csv" # andrew out one side then out other side
# file_name = "data/2021-02-23T13_40_eit_data_1.csv"  # andrew out then in one side
# file_name = "data/2021-02-23T13_44_eit_data.csv" # sam out one side then out other side
# file_name = "data/2021-02-23T13_44_eit_data_1.csv" # sam out then in one side
# file_name = "data/2021-02-23T13_48_eit_data.csv" #sam breathing normally then return to full lungs
file_name = "data/2021-02-23T13_52_eit_data.csv" #fixed connections sam breathing normally then return to full lungs


multiplier = 0.108666182

data = pd.read_csv(file_name, dtype=float, index_col=0).fillna(method="ffill")
data.index = data.index - data.index[0]
data["Flow1 (L/s)"] = data["Flow1"].pow(.5).fillna(0) * multiplier
data["Flow2 (L/s)"] = data["Flow2"].pow(.5).fillna(0) * multiplier * -1

data["abs_max"] = data.apply(lambda row: max(row["Flow1 (L/s)"], row["Flow2 (L/s)"], key=abs), axis=1)

data["Naive Volume (L)"] = integrate.cumtrapz(data["abs_max"], x=data.index, initial=0)

data[["Flow1 (L/s)", "Flow2 (L/s)", "abs_max", "Naive Volume (L)"]].plot()

plt.show()


