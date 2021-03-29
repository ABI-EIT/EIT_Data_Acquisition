import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

delta_threshold = 4


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


df = pd.DataFrame(columns=["A", "B"], data=np.array([[1, 0, 1, 1, 0, 1, 1, 1, 0, 1], [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]]).T)
df.index = pd.to_datetime(df.index, unit="s")

fig, ax = plt.subplots()
df.plot(ax=ax)

df2 = df[df["A"] == 0].apply(lambda row: delta_to_next(row, df["A"], df["B"]), axis=1)
print(df2)

for item in df2.iteritems():
    if item[1] != np.NaN and item[1] >= delta_threshold:
        ax.vlines(item[0], ax.get_ybound()[0], ax.get_ybound()[1], color="red")
        ax.vlines(df2.loc[item[0]:].index[1], ax.get_ybound()[0], ax.get_ybound()[1], color="red")

