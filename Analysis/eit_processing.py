import numpy as np
from Analysis.analysis_lib import lambda_max
from abi_pyeit.eit.render import model_inverse_uv, map_image, calc_absolute_threshold_set
from abi_pyeit.mesh.utils import load_mesh, load_stl, load_permitivities, place_electrodes_equal_spacing, \
    map_points_to_perimeter
from abi_pyeit.eit.jac import JAC
from abi_pyeit.eit.utils import eit_scan_lines
from config_lib.utils import cached_caller


def initialize_eit(conf, electrode_placement="equal_spacing", eit_type="JAC", cache_pyeit_obj=True, output_obj=None):
    """
    Create and setup an EIT object using a configuration dict

    Parameters
    ----------
    conf:
        Flat configuration dict specifying all required args:
            electrode_placement:
                equal_spacing:
                    n_electrodes, starting_angle, counter_clockwise, chest_and_spine_ratio
                from_file:
                    electrode_points_filename
            scan_lines:
                n_electrodes, dist
            eit_type:
                JAC:
                    init: step, perm, jac_normalized, parser
                    setup: p, lamb, method
    electrode_placement:
        equal_spacing
        from_file
    eit_type
        JAC (only JAC is supported right now)

    Returns
    -------
    pyeit_obj

    """
    if output_obj is None:
        output_obj = {}

    mesh = load_mesh(conf["mesh_filename"])

    place_e_output = {}
    if electrode_placement == "equal_spacing":
        # Make all keys optional for place_electrodes_equal_spacing
        place_e_keys = ["n_electrodes", "starting_angle", "counter_clockwise", "chest_and_spine_ratio"]
        place_e_kwargs = {k: conf[k] for k in place_e_keys if k in conf}
        electrode_nodes = place_electrodes_equal_spacing(mesh, **place_e_kwargs, output_obj=place_e_output)
    elif electrode_placement == "from_file":
        electrode_points = np.genfromtxt(conf["electrode_points_filename"], delimiter=",")
        electrode_nodes = map_points_to_perimeter(mesh, points=np.array(electrode_points), map_to_nodes=True)
    else:
        raise ValueError("Invalid entry for the \"electrode_placement\" field")

    # Make all keys optional for eit_scan_lines
    scan_lines_keys_map = {"n_electrodes": "ne", "dist": "dist"}
    scan_lines_kwargs = {v: conf[k] for k, v in scan_lines_keys_map.items() if k in conf}
    ex_mat = eit_scan_lines(**scan_lines_kwargs)

    if eit_type == "JAC":
        # Make all keys optional for JAC and setup
        jac_keys = ["step", "perm", "jac_normalized", "parser"]
        jac_kwargs = {k: conf[k] for k in jac_keys if k in conf}
        if not cache_pyeit_obj:
            pyeit_obj = JAC(mesh, np.array(electrode_nodes), ex_mat, **jac_kwargs)
        else:
            pyeit_obj = cached_caller(JAC, str, mesh, np.array(electrode_nodes), ex_mat, **jac_kwargs)
        setup_keys = ["p", "lamb", "method"]
        setup_kwargs = {k: conf[k] for k in setup_keys if k in conf}
        pyeit_obj.setup(**setup_kwargs)
    else:
        raise ValueError(f"EIT type {eit_type} not implemented")

    output_obj["electrode_nodes"] = electrode_nodes
    output_obj["place_e_output"] = place_e_output

    return pyeit_obj


def render_reconstruction(mesh, reconstruction_series, mask_mesh=None, resolution=(1000, 1000)):
    bounds = [
        (np.min(mesh["node"][:, 0]), np.min(mesh["node"][:, 1])),
        (np.max(mesh["node"][:, 0]), np.max(mesh["node"][:, 1]))
    ]

    if mask_mesh is not None:
        image = model_inverse_uv(mask_mesh, resolution=resolution, bounds=bounds)
    else:
        image = model_inverse_uv(mesh, resolution=resolution, bounds=bounds)

    recon_render = [map_image(image, np.array(row)) for row in reconstruction_series]

    return recon_render


def calculate_eit_volume(recon_render_series, threshold_proportion=0.15, sensitivity=None):
    # Todo: maybe an intermediate should be area. We should also output the not normalized volume (or the max_pixels).
    # Find the point in the rendered image with greatest magnitude (+ or -) so we can threshold on this
    greatest_magnitude = [lambda_max(row, key=lambda val: np.abs(np.nan_to_num(val, nan=0))) for row in recon_render_series]

    # Find the max over all frames
    max_all_frames = lambda_max(np.array(greatest_magnitude), key=lambda val: np.abs(np.nan_to_num(val, nan=0)))

    # Create a threshold image
    threshold_image_series = [calc_absolute_threshold_set(row, max_all_frames * threshold_proportion) for row in recon_render_series]

    # Count pixels in the threshold image
    reconstructed_area_series = [np.count_nonzero(row == 1) for row in threshold_image_series]

    max_pixels = np.sum(np.isfinite(threshold_image_series[0]))

    # Raise to power of 1.5 to obtain a linear relationship with volume
    volume_series = np.power(reconstructed_area_series, 1.5)

    volume_normalized_series = volume_series / max_pixels ** 1.5

    if sensitivity is not None:
        volume_normalized_series = volume_normalized_series * sensitivity

    return volume_normalized_series, threshold_image_series