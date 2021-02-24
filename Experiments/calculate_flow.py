import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import integrate


# file_name = "data/2021-02-25T10_55_V1_10L_calibration.csv"
# file_name = "data/2021-02-25T10_59_V2_10L_calibration.csv"
file_name = "data/2021-02-25T11_20_V1_10L_repeat_test.csv"
# file_name = "data/2021-02-25T11_32_andrew_breathing_full_to_full_series.csv" # venturis in series
# file_name = "data/2021-02-25T11_40_volume_blowing_one_side_then_other_series.csv" # venturis in series


flow_1_multiplier = 0.08886275685  # V1 calibration
flow_2_multiplier = 0.0886768699  # V2 calibration


data = pd.read_csv(file_name, dtype=float, index_col=0).fillna(method="ffill")
data.index = data.index - data.index[0]
data["Flow1 (L/s)"] = data["Flow1"].pow(.5).fillna(0) * flow_1_multiplier
data["Flow2 (L/s)"] = data["Flow2"].pow(.5).fillna(0) * flow_2_multiplier * -1

data["abs_max"] = data.apply(lambda row: max(row["Flow1 (L/s)"], row["Flow2 (L/s)"], key=abs), axis=1)

data["Naive Volume (L)"] = integrate.cumtrapz(data["abs_max"], x=data.index, initial=0)

data[["Flow1 (L/s)", "Flow2 (L/s)", "abs_max", "Naive Volume (L)"]].plot()

print(integrate.trapz(data["abs_max"], x=data.index))

plt.show()


