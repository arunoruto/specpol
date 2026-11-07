"""Run: uv run python test_camera.py  (no hardware: fakes a linear sensor)"""

import numpy as np

from camera import Camera, full_scale


class LinearSensor(Camera):
    def __init__(self, counts_per_us):
        self.k = counts_per_us
        self.cam = type("B", (), {"get_exposure_time_bounds": lambda _: (20.0, 4e6)})()

    def grab(self, exposure_us, gain, pixel_format=None):
        img = np.minimum(np.full((8, 8), self.k * exposure_us), full_scale(np.uint16)).astype(np.uint16)
        return img, {"exposure_us": exposure_us}


def test_auto_exposure():
    for k in (0.05, 1.0, 500.0):  # dim (~1 s needed) → bright scene, start far off and saturated
        exp = LinearSensor(k).auto_exposure(0, None, start_us=10_000)
        level = k * exp / full_scale(np.uint16)
        assert abs(level - 0.8) <= 0.05, (k, exp, level)
    # Too dark even at max exposure: stops at the limit instead of looping.
    assert LinearSensor(1e-6).auto_exposure(0, None, start_us=10_000) == 4e6


if __name__ == "__main__":
    test_auto_exposure()
    print("ok")
