"""Split the IMX250MZR 2x2 micro-polarizer mosaic and compute Stokes parameters."""

import numpy as np

# Polarizer angle (deg) at each (row, col) of the 2x2 super-pixel (Sony IMX250MZR layout).
# ponytail: verify once with a linear polarizer at 0°: AoLP must read ~0°. If it reads
# 90° or ±45°, swap entries here (ROI offsets / ReverseX / ReverseY shift the pattern).
PATTERN = {(0, 0): 90, (0, 1): 45, (1, 0): 135, (1, 1): 0}


def split(raw: np.ndarray, n: int = 1) -> dict[int, np.ndarray]:
    """Return the four half-resolution angle images {0, 45, 90, 135} as float32.

    n > 1 averages n×n super-pixels (binning): n× less resolution, n× better SNR (shot noise).
    """
    out = {}
    for (r, c), a in PATTERN.items():
        x = raw[r::2, c::2].astype(np.float32)
        if n > 1:
            h, w = x.shape[0] // n * n, x.shape[1] // n * n
            x = x[:h, :w].reshape(h // n, n, w // n, n).mean(axis=(1, 3))
        out[a] = x
    return out


def from_intensities(i, need=("dolp", "aolp", "error")):
    """Stokes quantities from the four angle images. S0-S2 always; DoLP, AoLP, error only if in `need`."""
    s0 = (i[0] + i[45] + i[90] + i[135]) / 2
    s1 = i[0] - i[90]
    s2 = i[45] - i[135]
    out = {"s0": s0, "s1": s1, "s2": s2}
    if "dolp" in need:
        out["dolp"] = np.hypot(s1, s2) / np.maximum(s0, 1e-6)
    if "aolp" in need:
        out["aolp"] = 0.5 * np.degrees(np.arctan2(s2, s1))
    if "error" in need:  # I0+I90 and I45+I135 both measure S0; their difference is 0 for ideal polarizers.
        out["error"] = (i[0] + i[90] - i[45] - i[135]) / 2
    return out


def stokes(raw: np.ndarray) -> dict[str, np.ndarray]:
    """Per-super-pixel S0, S1, S2, DoLP (0..1), AoLP (deg, -90..90) and error from a raw mosaic frame."""
    return from_intensities(split(raw))


def mean_stokes(raw: np.ndarray) -> dict[str, float]:
    """Same quantities for the whole frame (or a crop): intensities averaged first, then DoLP/AoLP."""
    return {k: float(v) for k, v in from_intensities({a: x.mean() for a, x in split(raw).items()}).items()}
