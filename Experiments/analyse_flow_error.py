import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import integrate
from scipy import signal

file_name = "data/2021-03-26T11_38_eit_data_series_venturi_1.csv"
file_name = "data/2021-03-26T11_52_eit_series_venturi_v1_validation.csv"

file_name = "data/2021-03-26T11_55_eit_series_venturi_2.csv"
# file_name = "data/2021-03-26T11_56_eit_series_venturi_2_validation.csv"

flow_threshold = 0.02
# flow_threshold = 0

flow_1_multiplier = 0.09847950291  # Calibrated value
flow_2_multiplier = -0.09799102959 # Calibrated value
flow_1_offset = 0
flow_2_offset = 0

cols = ["Time", "Flow"]

trigger = 0.4
reference_volume = 1

if __name__ == "__main__":
    data = pd.read_csv(file_name, usecols=cols, index_col=0)
    data.index = data.index - data.index[0]
    data = data.groupby(data.index).first()  # In groups of duplicate index, for each column, find the first non na row. (This merges duplicate timestamps keeping non na cells)
    data["Flow1"] = pd.to_numeric(data["Flow"].str.split(",", expand=True)[1], errors="coerce")
    data["Flow2"] = pd.to_numeric(data["Flow"].str.split(",", expand=True)[2], errors="coerce")

    mean_freq = 1/(data["Flow1"].dropna().index[-1]/len(data["Flow1"].dropna()))
    print("Mean frequency is %.2fhz" % mean_freq)
    time_deltas = [*data.index[1:], np.NaN] - data.index
    plt.plot(time_deltas, marker=".")
    data = data.fillna(method="pad")  # All measurements collected at different times, so we pad to get columns side by side
    data.index = pd.to_datetime(data.index, unit="s")
    data = data.resample("1ms").pad()

    data["Flow1 (L/s)"] = (data["Flow1"].pow(.5).fillna(0)) * flow_1_multiplier - flow_1_offset
    data["Flow2 (L/s)"] = (data["Flow2"].pow(.5).fillna(0)) * flow_2_multiplier - flow_2_offset

    data["abs_max"] = data.apply(lambda row: max(row["Flow1 (L/s)"], row["Flow2 (L/s)"], key=abs), axis=1)

    fs = 1000
    fc = 50  # Cut-off frequency of the filter
    w = fc / (fs / 2)  # Normalize the frequency
    b, a = signal.butter(5, w, 'low')
    data["abs_max_filtered"] = signal.filtfilt(b, a, data["abs_max"])

    data["abs_max_filtered"].mask(data["abs_max_filtered"].abs() <= flow_threshold, 0, inplace=True)

    data["Naive Volume (L)"] = integrate.cumtrapz(data["abs_max_filtered"], x=data.index.astype(np.int64)/10**9, initial=0)

    ax = data[["Flow1 (L/s)", "Flow2 (L/s)", "abs_max_filtered", "Naive Volume (L)"]].plot()
    ax.set_title("Measured flow (L/s) and calculated volume (L) vs time")
    # data[["abs_max", "abs_max_filtered"]].plot()

    print("Flow1 (L/s) mean:" + str(data["Flow1 (L/s)"].mean()))
    print("Flow2 (L/s) mean:" + str(data["Flow2 (L/s)"].mean()))

    print("Volume at end: " + str(data["Naive Volume (L)"].iloc[-1]))
    vol_300 = data["Naive Volume (L)"].iloc[np.argmax(np.isclose(data.index.astype(np.int64)/10**9, 300, atol=0.5))]
    print("Volume at 5 minutes: " + str(vol_300))

    # data["abs_max_filtered"] = data["abs_max_filtered"] * -1 # Multiply by -1 for flow2
    # data["Naive Volume (L)"] = data["Naive Volume (L)"] * -1

    ax.axhline(trigger, color="red")
    ax.axhline(-1*trigger, color="red")
    above = data["abs_max_filtered"].abs() >= trigger
    up = np.logical_and(above == False, [*above[1:], False])
    down = np.logical_and(above == True, [*(above[1:] == False), False])

    change = np.logical_or(up, down)

    data["categories"] = np.cumsum(change)
    odd_categories = data["categories"].where(data["categories"] % 2 == 1)  # we use odd categories, because we assume flow starts close to zero
    diffs = data.groupby(odd_categories).apply(lambda group: group["Naive Volume (L)"].iloc[-1]-group["Naive Volume (L)"].iloc[0])
    diffs = diffs.values

    df = pd.DataFrame(columns=["diffs"], data=diffs, index=reference_volume*list(range(1, 11)))
    df["cumsum"] = np.cumsum(diffs)
    d = np.polyfit(df.index, df["cumsum"], 1)
    f = np.poly1d(d)
    df["calculated"] = f(df.index)
    fig, ax = plt.subplots()
    ax.plot(df.index, df["cumsum"], ".")
    ax.plot(df.index, df["calculated"])
    ax.set_title("Cumulative measured volume (L) vs linear fit")
    print("Intercept: " + str(f[0]))
    print("Slope: " + str(f[1]))
    df["resid"] = df["calculated"]-df["cumsum"]
    max_resid = df["resid"].abs().max()
    full_scale = df.index.max()
    print("Max residual: %.2f%% of full scale" % ((max_resid/full_scale)*100))
    df["error_unadjusted"] = df["cumsum"]-df.index
    max_unadj = df["error_unadjusted"].abs().max()
    print("Max unadjusted error: %.2f%% of full scale" % ((max_unadj/full_scale)*100))

    fig, ax = plt.subplots()

    ax.plot(df.index, df["cumsum"], ".")
    ax.plot(df.index, df.index)
    ax.set_title("Calibrated measured volume (L) vs reference volume (L)")
    ax.legend(["Measured volume (L)", "Reference volume (L)"])
    ax.set_xlabel("Reference volume (L)")
    ax.set_ylabel("Volume (L)")


    plt.show()


