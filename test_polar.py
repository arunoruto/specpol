"""Run: uv run python test_polar.py"""

import numpy as np

from polar import PATTERN, mean_stokes, stokes


def mosaic(fn, shape=(4, 4)):
    raw = np.zeros(shape)
    for (r, c), a in PATTERN.items():
        raw[r::2, c::2] = fn(a)
    return raw


def test_malus():
    # Fully polarized light at 30°: each pixel sees I = cos²(θ_pixel - 30°) (Malus's law).
    s = stokes(mosaic(lambda a: 1000 * np.cos(np.radians(a - 30)) ** 2))
    assert np.allclose(s["aolp"], 30, atol=1e-3)
    assert np.allclose(s["dolp"], 1, atol=1e-4)
    assert np.allclose(s["s0"], 1000, atol=1e-2)
    assert np.allclose(s["error"], 0, atol=1e-2)
    # Unpolarized light: DoLP 0.
    assert np.allclose(stokes(np.full((4, 4), 500))["dolp"], 0)


def test_mean_dolp_averages_intensities_first():
    # Left half polarized at 0°, right half at 90°: per-pixel DoLP is 1 everywhere,
    # but the averaged light is unpolarized, so the frame's DoLP must be 0.
    raw = np.hstack([mosaic(lambda a: 1000 * np.cos(np.radians(a)) ** 2),
                     mosaic(lambda a: 1000 * np.cos(np.radians(a - 90)) ** 2)])
    assert np.allclose(stokes(raw)["dolp"], 1, atol=1e-4)
    assert abs(mean_stokes(raw)["dolp"]) < 1e-6


if __name__ == "__main__":
    test_malus()
    test_mean_dolp_averages_intensities_first()
    print("ok")
