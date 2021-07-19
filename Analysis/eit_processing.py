import numpy as np
from Analysis.analysis_lib import lambda_max
from abi_pyeit.eit.render import model_inverse_uv, map_image, calc_absolute_threshold_set


def render_reconstruction(mesh, reconstruction_series, mask_mesh=None):
    bounds = [
        (np.min(mesh["node"][:, 0]), np.min(mesh["node"][:, 1])),
        (np.max(mesh["node"][:, 0]), np.max(mesh["node"][:, 1]))
    ]

    if mask_mesh is not None:
        image = model_inverse_uv(mask_mesh, resolution=(1000, 1000), bounds=bounds)
    else:
        image = model_inverse_uv(mesh, resolution=(1000, 1000), bounds=bounds)

    recon_render = [map_image(image, np.array(row)) for row in reconstruction_series]

    return recon_render


def calculate_eit_volume(recon_render_series, threshold_proportion=0.15):
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

    return volume_normalized_series, threshold_image_series