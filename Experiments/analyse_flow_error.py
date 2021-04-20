import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy import integrate
from scipy import signal
import time

# file_name = "data/2021-04-19T11_19_flow_shorter_venturi_f1_calibration.csv"
# file_name = "data/2021-04-19T11_20_flow_shorter_venturi_f1_verification.csv"
# file_name = "data/2021-04-19T11_21_flow_shorter_venturi_f2_calibration.csv"
# file_name = "data/2021-04-19T11_22_flow_shorter_venturi_f2_verification.csv"


cols = ["Time", "Flow"]

trigger = 0.1
delta_trigger = 0.5
reference_volume = -1

config = {
    "sensor_orientations": [-1, 1],  # Orientation of pressure sensor. 1 for positive reading from air flow in correct direction through venturi tube
    "Flow1_multiplier": 0.09693754462,
    "Flow2_multiplier": -0.09648965709,
    # "Flow1_multiplier": 0,
    # "Flow2_multiplier": -0
    "Pressure1_offset": 0.03,
    "Pressure2_offset": -0.01,
    # "Pressure1_offset": 0,
    # "Pressure2_offset": 0,
    "flow_threshold": 0.02,
    "sampling_freq_hz": 1000,
    "cutoff_freq": 50,
    "order": 5,
    "use_filter": True,
    "buffer": "50ms"
}


def delta_to_next(row, column_a, column_b, next_target=0):
    """
        Find change in column b
        starting at input row
        ending where column a is target
    """
    from_val = column_b.loc[row.name]

    a_from_input_row = column_a.loc[row.name:].iloc[1:]  # Get column starting after input row

    if not a_from_input_row.empty:
        next_index = (a_from_input_row == next_target).idxmax()
    else:
        return np.NaN

    next_val = column_b.loc[next_index]
    return next_val-from_val


def main():
    data = pd.read_csv(file_name, usecols=cols, index_col=0)
    data.index = data.index - data.index[0]
    data = data.groupby(data.index).first()  # In groups of duplicate index, for each column, find the first non na row. (This merges duplicate timestamps keeping non na cells)
    data["Pressure1"] = pd.to_numeric(data["Flow"].str.split(",", expand=True)[1], errors="coerce")
    data["Pressure2"] = pd.to_numeric(data["Flow"].str.split(",", expand=True)[2], errors="coerce")

    mean_freq = 1/(data["Pressure1"].dropna().index[-1]/len(data["Pressure1"].dropna()))
    print("Mean frequency is %.2fhz" % mean_freq)
    time_deltas = [*data.index[1:], np.NaN] - data.index
    plt.plot(time_deltas, marker=".")
    data = data.fillna(method="pad")  # All measurements collected at different times, so we pad to get columns side by side
    data.index = pd.to_datetime(data.index, unit="s")

    # Squash and resample
    data = data.resample(pd.to_timedelta(1 / config["sampling_freq_hz"], unit="s")).pad()

    # Orient
    data[["Pressure1", "Pressure2"]] = data[["Pressure1","Pressure2"]] * config["sensor_orientations"]

    # Subtract offset from pressure reading
    offsets = [config["Pressure1_offset"], config["Pressure2_offset"]]
    data[["Pressure1","Pressure2"]] = data[["Pressure1","Pressure2"]] - offsets

    # Low pass filter pressure reading
    fs = config["sampling_freq_hz"]
    fc = config["cutoff_freq"]  # Cut-off frequency of the filter
    w = fc / (fs / 2)  # Normalize the frequency
    b, a = signal.butter(config["order"], w, 'low')
    pad_len = 3 * max(len(a), len(b))  # default filtfilt pad len

    if config["use_filter"]:
        data["Pressure1_filtered"] = signal.filtfilt(b, a, data["Pressure1"].fillna(0))
        data["Pressure2_filtered"] = signal.filtfilt(b, a, data["Pressure2"].fillna(0))
    else:
        data["Pressure1_filtered"] = data["Pressure1"].fillna(0)
        data["Pressure2_filtered"] = data["Pressure2"].fillna(0)

    # Convert pressure to flow
    multipliers = [config["Flow1_multiplier"], config["Flow2_multiplier"]]

    df_flow = data[["Pressure1_filtered", "Pressure2_filtered"]]
    df_flow = df_flow.clip(lower=0)
    df_flow = df_flow.pow(0.5)
    df_flow = df_flow * multipliers

    # Infer flow direction ("Pressure" cols now transformed to unidirectional flow readings)
    data["Flow"] = df_flow.fillna(0).apply(
        lambda row: max((row["Pressure1_filtered"], row["Pressure2_filtered"]), key=abs), axis=1)

    # Threshold flow
    data["Flow"].mask(data["Flow"].abs() <= config["flow_threshold"], 0, inplace=True)

    # Integrate to find volume
    data["Volume"] = integrate.cumtrapz(data["Flow"], x=data.index.astype(np.int64) / 10 ** 9,
                                          initial=0)

    ax = data[["Pressure1_filtered", "Pressure2_filtered", "Flow", "Volume"]].plot()
    ax.set_title("Measured flow (L/s) and calculated volume (L) vs time")

    # -----------------------------------------------------------------------------------------------------

    data["ups"] = np.logical_and(data["Flow"] == 0,
                         np.not_equal(np.append(data["Flow"].iloc[1:].values, 0), 0))

    # data_deltas = data[data["abs_max_filtered"] == 0].apply(lambda row: delta_to_next(row, data["abs_max_filtered"], data["Naive Volume (L)"]), axis=1)
    data_deltas = data[data["ups"]].apply(
        lambda row: delta_to_next(row, data["Flow"], data["Volume"]), axis=1)

    for item in data_deltas.iteritems():
        if item[1] != np.NaN and np.abs(item[1]) >= delta_trigger:
            ax.axvline(item[0], color="red")
            ax.axvline(data_deltas.loc[item[0]:].index[0], color="red")

    data_deltas = data_deltas.dropna()
    data_deltas = data_deltas[data_deltas.abs() >= delta_trigger]

    df = pd.DataFrame(columns=["diffs"], data=data_deltas.values, index=reference_volume*np.array(range(1, 11)))
    df["cumsum"] = np.cumsum(data_deltas.values)
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
    full_scale = np.abs(df.index).max()
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


if __name__ == "__main__":
    # start = time.time()
    main()
    # finish = time.time()
    # print("Execution took {:.3f}s".format(finish-start))
    plt.show()
