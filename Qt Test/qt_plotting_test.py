import matplotlib.tri as tri
import numpy as np
from PyQt5 import QtWidgets
import sys
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import time
from mpl_toolkits.axes_grid1 import make_axes_locatable

# Prepare data to plot ----------------------------------------------------------
text_coords = [[1, 0], [.81, .59], [.31, .95], [-.31, .95], [-.81, .59],
               [-1, 0], [-.81, -.59], [-.31, -.95], [.31, -.95], [.81, -.59]]

n_angles = 36
n_radii = 8
min_radius = 0.25
radii = np.linspace(min_radius, 1.05, n_radii)

angles = np.linspace(0, 2 * np.pi, n_angles, endpoint=False)
angles = np.repeat(angles[..., np.newaxis], n_radii, axis=1)
angles[:, 1::2] += np.pi / n_angles
x = (radii * np.cos(angles)).flatten()
y = (radii * np.sin(angles)).flatten()
triang = tri.Triangulation(x, y)

triang.set_mask(np.hypot(x[triang.triangles].mean(axis=1),
                         y[triang.triangles].mean(axis=1))
                < min_radius)
# -------------------------------------------------------------------------------


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.first_plot = True
        self.color_axis = None
        self._main = QtWidgets.QWidget()
        self.setCentralWidget(self._main)
        layout = QtWidgets.QVBoxLayout(self._main)

        canvas = FigureCanvas(Figure(figsize=(15, 10)))
        layout.addWidget(canvas)

        self.ax = canvas.figure.subplots()
        self.ax.set_aspect('equal')

        self.timer = canvas.new_timer(100)
        self.timer.add_callback(self.update_canvas)
        self.timer.start()

    def update_canvas(self):
        start_time = time.time()
        self.ax.clear()

        z = (np.cos(radii+time.time()) * np.cos(3 * angles+time.time())).flatten()
        plot_image = self.ax.tripcolor(triang, z)

        for i in range(0, 10):
            self.ax.text(text_coords[i][0], text_coords[i][1], i)

        if self.first_plot:
            divider = make_axes_locatable(self.ax)
            self.color_axis = divider.append_axes("right", size="5%", pad=0.1)
            self.color_axis.yaxis.tick_right()
            self.ax.figure.colorbar(plot_image, cax=self.color_axis)
            self.first_plot = False

        else:
            self.color_axis.clear()
            self.ax.figure.colorbar(plot_image, cax=self.color_axis)

        self.ax.figure.canvas.draw()
        elapsed_time = time.time()-start_time
        print("Plotting time: %.2fs" % elapsed_time)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    app.exec()
