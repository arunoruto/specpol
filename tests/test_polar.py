"""Polarization math: Malus's law, frame averages, binning."""

import numpy as np

from specpol.polar import PATTERN, from_intensities, mean_stokes, split, stokes


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


def test_binning():
    # 2x2 binning keeps the polarization, halves each side (odd edge cropped), halves the noise.
    rng = np.random.default_rng(0)
    raw = rng.poisson(mosaic(lambda a: 1000 * np.cos(np.radians(a - 30)) ** 2, (202, 302))).astype(np.uint16)
    b = split(raw, 2)
    assert b[0].shape == (50, 75)
    x = raw[1::2, 1::2][:100, :150].astype(np.float32)  # PATTERN (1, 1) = 0°: plain n×n mean as reference
    assert np.allclose(b[0], x.reshape(50, 2, 75, 2).mean(axis=(1, 3)))
    assert np.isclose(np.median(from_intensities(b)["aolp"]), 30, atol=0.5)
    noise = [from_intensities(split(raw, n))["s0"].std() for n in (1, 2)]
    assert 1.8 < noise[0] / noise[1] < 2.2, noise
    # Only what's asked for is computed.
    assert set(from_intensities(b, need=())) == {"s0", "s1", "s2"}

