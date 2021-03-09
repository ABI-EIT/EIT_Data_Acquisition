import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import integrate
from scipy import signal

# file_name = "data/2021-02-25T10_55_V1_10L_calibration.csv"
# file_name = "data/2021-02-25T10_59_V2_10L_calibration.csv"
# file_name = "data/2021-02-25T11_20_V1_10L_repeat_test.csv"
# file_name = "data/2021-02-25T11_32_andrew_breathing_full_to_full_series.csv" # venturis in series
# file_name = "data/2021-02-25T11_40_volume_blowing_one_side_then_other_series.csv" # venturis in series

# file_name = "data/2021-02-25T14_15_andrew_full_to_full_parallel.csv"  # andrew full to full parallel


# file_name = "data/2021-02-25T14_19_zero_flow_calibration.csv"  # nothin
# file_name = "data/2021-02-25T14_42_sam_full_to_full_parallel.csv"
# file_name = "data/2021-02-26T10_23_vernier_spirometer_drift_test.csv"

# file_name = "data/2021-02-26T11_04_vernier_10L_calibration.csv"
# file_name = "data/2021-03-09T15_01_data.csv"


file_name = "data/20210309-162947.txt" # 3 speeds recorded with readArduino
file_name = "data/2021-03-09T16_40_data.csv" # 3 speeds recorded with dual_venturi
file_name = "data/2021-03-09T16_50_eit_data.csv" # 3 speeds recorded with main (with EIT)


# # Venturi calibration
# flow_1_multiplier = 0.09114830539  # V1 calibration
# flow_2_multiplier = 0.08960919406 # V2 calibration
#
# flow_1_offset = 0.03618421041453358
# flow_2_offset = 0.012253753906233688

flow_threshold = 0.02
# flow_threshold = 0

flow_1_multiplier = 0.108666182  # Theoretical value from Alex
flow_1_offset = 0
flow_2_multiplier = 0.108666182
flow_2_offset = 0

cols = ["Time", "Flow1", "Flow2"]

if __name__ == "__main__":
    data = pd.read_csv(file_name, dtype=float, usecols=cols, index_col=0).fillna(method="ffill")
    data.index = data.index - data.index[0]
    data.index = pd.to_datetime(data.index, unit="s")
    data = data[~data.index.duplicated(keep='first')]
    data = data.resample("1ms").pad()

    data["Flow1 (L/s)"] = (data["Flow1"].pow(.5).fillna(0) - flow_1_offset) * flow_1_multiplier
    data["Flow2 (L/s)"] = (data["Flow2"].pow(.5).fillna(0) - flow_2_offset) * flow_2_multiplier * -1

    data["abs_max"] = data.apply(lambda row: max(row["Flow1 (L/s)"], row["Flow2 (L/s)"], key=abs), axis=1)

    fs = 1000
    fc = 50  # Cut-off frequency of the filter
    w = fc / (fs / 2)  # Normalize the frequency
    b, a = signal.butter(5, w, 'low')
    data["abs_max_filtered"] = signal.filtfilt(b, a, data["abs_max"])

    data["abs_max_filtered"].mask(data["abs_max_filtered"].abs() <= flow_threshold, 0, inplace=True)

    data["Naive Volume (L)"] = integrate.cumtrapz(data["abs_max_filtered"], x=data.index.astype(np.int64)/10**9, initial=0)

    data[["Flow1 (L/s)", "Flow2 (L/s)", "abs_max_filtered", "Naive Volume (L)"]].plot()
    # data[["abs_max", "abs_max_filtered"]].plot()

    print("Flow1 (L/s) mean:" + str(data["Flow1 (L/s)"].mean()))
    print("Flow2 (L/s) mean:" + str(data["Flow2 (L/s)"].mean()))

    print("Volume at end: " + str(data["Naive Volume (L)"].iloc[-1]))
    vol_300 = data["Naive Volume (L)"].iloc[np.argmax(np.isclose(data.index.astype(np.int64)/10**9, 300, atol=0.5))]
    print("Volume at 5 minutes: " + str(vol_300))

    plt.show()


