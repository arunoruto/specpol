"""Camera wrapper, live feed and recording against fakes (a linear-sensor stub and Aravis' simulated camera)."""

import os
import time

import numpy as np

from specpol.camera import Camera, full_scale


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
    os.environ["SPECPOL_FAKE"] = "1"
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


def test_feed_fake():
    """MJPEG stream from live.py: first part is a JPEG, unknown sessions get 404."""
    import asyncio

    from specpol import live

    os.environ["SPECPOL_FAKE"] = "1"
    feed = live.LiveFeed(Camera())
    feed.views["s"] = lambda img: [(img >> 8 if img.dtype == np.uint16 else img).astype(np.uint8)]
    feed.settings = (10_000, 0, None)

    async def first_part():
        parts = feed.parts("s", 0)
        try:
            return await asyncio.wait_for(anext(parts), 10)
        finally:
            await parts.aclose()

    part = asyncio.run(first_part())
    head, data = part.split(b"\r\n\r\n", 1)
    assert head.startswith(b"--frame\r\nContent-Type: image/jpeg") and data[:2] == b"\xff\xd8"  # JPEG SOI
    assert feed.fps() > 0 and feed.fps("s") > 0 and feed.fps("other") == 0
    assert feed.clients == 0  # closing the stream releases it
    request = type("Request", (), {"path_params": {"sid": "nope", "slot": 0}})()
    assert asyncio.run(live.stream(request)).status_code == 404
    with feed.paused():  # a one-shot grab while paused must not be undone by the capture thread
        feed.cam.grab(20_000, 0)
        time.sleep(0.3)
        assert feed.cam.stream is None


def test_record_fake():
    """Video snippet: a 2-slot grid recorded for 1.5 s plays back as H.264, tiled, at real speed."""
    import tempfile
    from pathlib import Path

    import av

    from specpol.live import LiveFeed

    os.environ["SPECPOL_FAKE"] = "1"
    feed = LiveFeed(Camera())
    grey = lambda img: (img >> 8 if img.dtype == np.uint16 else img).astype(np.uint8)  # noqa: E731
    feed.views["s"] = lambda img: [grey(img), np.stack([grey(img)] * 3, axis=2)]  # grey + RGB slot
    feed.settings = (10_000, 0, None)
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "clip.mp4"
        n = feed.record("s", 1.5, path, cols=2)
        assert n > 5, n
        with av.open(str(path)) as f:
            v = f.streams.video[0]
            frames = list(f.decode(v))
            h, w = feed.cam.size()[::-1]
            assert v.codec_context.name == "h264" and (v.width, v.height) == (w * 2 // 2 * 2, h // 2 * 2)
            assert len(frames) == n and 1.0 < frames[-1].time <= 1.5, (len(frames), frames[-1].time)

