from pyeit.eit.base import EitBase
from pyeit.eit.interp2d import sim2pts
import json
import numpy as np
from pyeit.mesh.external import load_mesh, place_electrodes_equal_spacing
from pyeit.eit.jac import JAC
from pyeit.eit.utils import eit_scan_lines
import pyeit.eit.protocol as protocol
import pathlib
import os


def load_conf(conf_file):
    with open(conf_file, "r") as f:
        return json.load(f)


def process_frame(pyeit_obj: EitBase, frame, conf, background):
    if background is None:
        background = np.zeros(len(frame))

    if conf["solve_type"] == "solve":
        ds = pyeit_obj.solve(frame, background, conf["normalize"])
        ds_jac = sim2pts(pyeit_obj.mesh.node, pyeit_obj.mesh.element, ds)
        eit_image = np.real(ds_jac)
    elif conf["solve_type"] == "gn":
        ds = pyeit_obj.gn(frame, lamb_decay=conf["solve_params"]["lamb_decay"],
                          lamb_min=conf["solve_params"]["lamb_min"], maxiter=conf["solve_params"]["maxiter"],
                          verbose=True)
        ds_jac = sim2pts(pyeit_obj.mesh.node, pyeit_obj.mesh.element, ds)
        eit_image = np.real(ds_jac)
    else:
        eit_image = None

    return eit_image


def load_oeit_data(file_name):
    with open(file_name, "r") as f:
        lines = f.readlines()

    data = []
    for line in lines:
        eit = parse_oeit_line(line)
        if eit is not None:
            data.append(eit)

    return data


def parse_oeit_line(line):
    try:
        _, data = line.split(":", 1)
    except (ValueError, AttributeError):
        return None
    items = []
    for item in data.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            items.append(float(item))
        except ValueError:
            return None
    return np.array(items)


def setup_eit(mesh_file_name, conf_file_name):
    with open(conf_file_name, "r") as f:
        conf = json.load(f)
    elec_conf = conf["electrodes"]
    ex_mat_conf = conf["ex_mat"]
    setup = conf["setup"]

    mesh_obj = load_mesh(mesh_file_name)

    electrode_nodes = place_electrodes_equal_spacing(mesh_obj, n_electrodes=elec_conf["number"],
                                                     starting_angle=elec_conf["starting_angle"],
                                                     starting_offset=elec_conf["starting_offset"],
                                                     counter_clockwise=elec_conf["counter_clockwise"])

    mesh_obj.el_pos = np.array(electrode_nodes)

    if conf["type"] == "JAC":
        protocol_obj = protocol.create(elec_conf["number"], dist_exc=ex_mat_conf["dist"], step_meas=ex_mat_conf["step"], parser_meas=conf["parser"])
        pyeit_obj = JAC(mesh_obj, protocol_obj)
        pyeit_obj.setup(p=setup["p"], lamb=setup["lamb"], method=setup["method"])
    else:
        pyeit_obj = None

    return pyeit_obj