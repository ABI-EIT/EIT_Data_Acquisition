import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import integrate
from scipy import signal

# file_name = "data/20210309-162947.txt" # 3 speeds recorded with readArduino
# file_name = "data/2021-03-09T16_40_data.csv" # 3 speeds recorded with dual_venturi
file_name = "data/2021-03-09T16_50_eit_data.csv" # 3 speeds recorded with main (with EIT)
file_name = "data/2021-03-15T16_39_eit_data.csv" #andrew. no eit v1
file_name = "data/20210316-135513.txt" # josh samey v1
# file_name = "data/20210316-140750v2.txt" #andrew v2
file_name = "data/2021-03-16T16_37_eit_with_eit.csv" #v1 with eit

flow_threshold = 0.02
# flow_threshold = 0

flow_1_multiplier = 0.108666182  # Theoretical value from Alex
flow_1_offset = 0
flow_1_multiplier = 0.09302907076 # Calculated calibration v1
# flow_1_multiplier = 0.09372544465 # Calculated calibration v2
flow_2_multiplier = 0.1
flow_2_offset = 0

cols = ["Time", "Flow1", "Flow2"]

trigger = 0.3
reference_volume = 1

if __name__ == "__main__":
    data = pd.read_csv(file_name, dtype=float, usecols=cols, index_col=0)
    data.index = data.index - data.index[0]
    data = data.groupby(data.index).first()  # In groups of duplicate index, for each column, find the first non na row. (This merges duplicate timestamps keeping non na cells)
    mean_freq = 1/(data["Flow1"].dropna().index[-1]/len(data["Flow1"].dropna()))
    print("Mean frequency is %.2fhz" % mean_freq)
    time_deltas = [*data.index[1:], np.NaN] - data.index
    plt.plot(time_deltas, marker=".")
    data = data.fillna(method="pad")  # All measurements collected at different times, so we pad to get columns side by side
    data.index = pd.to_datetime(data.index, unit="s")
    data = data.resample("1ms").pad()

    data["Flow1 (L/s)"] = (data["Flow1"].pow(.5).fillna(0)) * flow_1_multiplier - flow_1_offset
    data["Flow2 (L/s)"] = (data["Flow2"].pow(.5).fillna(0)) * flow_2_multiplier * -1 - flow_2_offset

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

    above = data["abs_max_filtered"] >= trigger
    up = np.logical_and(above == False, [*above[1:], False])
    down = np.logical_and(above == True, [*(above[1:] == False), False])

    change = np.logical_or(up, down)
    data["categories"] = np.cumsum(change)
    odd_categories = data["categories"].where(data["categories"] % 2 == 1)  # we use odd categories, because we assume flow starts close to zero
    diffs = data.groupby(odd_categories).apply(lambda group: group["Naive Volume (L)"].iloc[-1]-group["Naive Volume (L)"].iloc[0])
    diffs = diffs.values

    df = pd.DataFrame(columns=["diffs"], data=diffs, index=reference_volume*list(range(1, 12)))
    df["cumsum"] = np.cumsum(diffs)
    d = np.polyfit(df.index, df["cumsum"], 1)
    f = np.poly1d(d)
    df["calculated"] = f(df.index)
    fig, ax = plt.subplots()
    ax.plot(df.index, df["cumsum"], ".")
    ax.plot(df.index, df["calculated"])
    print("Intercept: " + str(f[0]))
    print("Slope: " + str(f[1]))
    df["resid"] = df["calculated"]-df["cumsum"]
    max_resid = df["resid"].abs().max()
    full_scale = df.index.max()
    print("Max residual: %.2f%% of full scale" % ((max_resid/full_scale)*100))
    df["error_unadjusted"] = df["cumsum"]-df.index
    max_unadj = df["error_unadjusted"].abs().max()
    print("Max unadjusted error: %.2f%% of full scale" % ((max_unadj/full_scale)*100))


    plt.show()


