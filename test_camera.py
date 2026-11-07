"""Run: uv run python test_camera.py  (no hardware: fakes a linear sensor)"""

import os
import time

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


def test_live_fake():
    """Live stream against Aravis' simulated camera: settings changes and one-shot grabs in between."""
    os.environ["DZK_FAKE"] = "1"
    cam = Camera()
    for exp in (10_000, 20_000):
        for _ in range(3):
            img, m = cam.grab_live(exp, 0)
            assert img.ndim == 2 and abs(m["exposure_us"] - exp) < 1, m
        img, m = cam.grab(exp * 2, 0)  # one-shot in between must stop the stream and still work
        assert cam.stream is None and abs(m["exposure_us"] - exp * 2) < 1, m
    t = time.perf_counter()
    for _ in range(10):
        cam.grab_live(10_000, 0)
    print(f"live: {(time.perf_counter() - t) * 100:.0f} ms/frame")


if __name__ == "__main__":
    test_auto_exposure()
    test_live_fake()
    print("ok")
