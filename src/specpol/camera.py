"""Thin wrapper around Aravis (open-source USB3 Vision driver) for the DZK 33UX250."""

import os
import threading
import time
from datetime import datetime

import gi
import numpy as np

gi.require_version("Aravis", "0.8")
from gi.repository import Aravis  # noqa: E402


def full_scale(dtype) -> int:
    return 255 if dtype == np.uint8 else 0xFFF0  # 12-bit ADC, MSB-aligned in 16 bit


class Camera:
    def __init__(self):
        if os.environ.get("SPECPOL_FAKE"):  # SPECPOL_FAKE=1 (specpol --fake) → Aravis' simulated camera, for dev without hardware
            Aravis.enable_interface("Fake")
        Aravis.update_device_list()
        if not Aravis.get_n_devices():
            raise RuntimeError("No camera found. Check USB cable and udev permissions (README).")
        self.cam = Aravis.Camera.new(Aravis.get_device_id(0))
        self.lock = threading.Lock()  # preview and capture share one device
        self.stream, self.live = None, None  # running preview stream and the settings it was started with
        self.live_fps = None  # frame rate the running stream can deliver (link limit and exposure)
        if self.cam.is_exposure_auto_available():
            self.cam.set_exposure_time_auto(Aravis.Auto.OFF)
        if self.cam.is_gain_auto_available():
            self.cam.set_gain_auto(Aravis.Auto.OFF)

    def _opt(self, feature):
        try:
            return self.cam.get_float(feature) if feature.endswith("Temperature") else self.cam.get_string(feature)
        except Exception:
            return None

    def info(self) -> dict:
        c = self.cam
        return {
            "vendor": c.get_vendor_name(),
            "model": c.get_model_name(),
            "serial": c.get_device_serial_number(),
            "firmware": self._opt("DeviceFirmwareVersion") or self._opt("DeviceVersion"),
        }

    def pixel_formats(self) -> list[str]:
        return [f for f in self.cam.dup_available_pixel_formats_as_strings() if f.startswith(("Mono", "Polarized")) and not f.endswith("p")]  # packed formats unsupported

    def bounds(self) -> dict:
        return {"exposure_us": tuple(self.cam.get_exposure_time_bounds()), "gain": tuple(self.cam.get_gain_bounds())}

    def auto_exposure(self, gain, pixel_format, start_us, target=0.8, tol=0.05, max_iter=8) -> float:
        """Exposure (µs) that puts the 99.9th-percentile pixel at `target` of full scale.

        Assumes a linear sensor: scale exposure by target/level and repeat. A saturated
        frame says nothing about how far over we are, so then just cut exposure by 4x.
        """
        lo, hi = self.cam.get_exposure_time_bounds()
        exp = start_us
        for _ in range(max_iter):
            img, m = self.grab(exp, gain, pixel_format)
            level = np.percentile(img, 99.9) / full_scale(img.dtype)
            if abs(level - target) <= tol:
                return m["exposure_us"]
            exp = min(max(exp * (target / max(level, 1e-3) if level < 0.98 else 0.25), lo), hi)
            if exp in (lo, hi) and exp == m["exposure_us"]:
                break  # pinned at a limit: too bright/dark for exposure alone, change gain
        return exp

    def _apply(self, exposure_us, gain, pixel_format):
        c = self.cam
        if pixel_format and c.get_pixel_format_as_string() != pixel_format:
            c.set_pixel_format_from_string(pixel_format)
        c.set_exposure_time(exposure_us)
        c.set_gain(gain)

    def size(self) -> tuple[int, int]:
        """Image (width, height) in pixels."""
        _, _, w, h = self.cam.get_region()
        return w, h

    def _stop_live(self):
        if self.stream is not None:
            self.cam.stop_acquisition()
            self.stream, self.live = None, None

    def stop_live(self):
        with self.lock:
            self._stop_live()

    def grab(self, exposure_us: float, gain: float, pixel_format: str | None = None) -> tuple[np.ndarray, dict]:
        """Single fresh frame with the given settings: acquisition starts after this call, so the
        frame is guaranteed to be exposed with them. Returns (raw mosaic, actual settings read back)."""
        with self.lock:
            self._stop_live()
            self._apply(exposure_us, gain, pixel_format)
            for _ in range(3):  # incomplete USB frames happen (see README: usbfs); bad ones are dropped, never returned
                buf = self.cam.acquisition(int(exposure_us + 3_000_000))
                if buf is not None and buf.get_status() == Aravis.BufferStatus.SUCCESS:
                    return self._frame(buf)
            raise RuntimeError(f"Frame failed 3x ({buf.get_status().value_nick if buf else 'no buffer'}). "
                               "Check usbfs_memory_mb (README).")

    def grab_live(self, exposure_us: float, gain: float, pixel_format: str | None = None) -> tuple[np.ndarray, dict]:
        """Preview frame from a continuously running stream: no per-frame start/stop (~250 ms on USB).
        Settings changes restart the stream, so frames always match them. Not for measurements:
        returns the newest frame already received (up to one frame period old) without waiting,
        and the settings in the metadata are read back once per stream start, not per frame."""
        with self.lock:
            if self.live != (exposure_us, gain, pixel_format):
                self._stop_live()
                self._apply(exposure_us, gain, pixel_format)
                # Default is 30 fps; the link allows 75 (Mono8) / 37.5 (Mono16). Exposure still limits it.
                self.cam.set_frame_rate(self.cam.get_frame_rate_bounds()[1])
                self.live_fps = min(self.cam.get_frame_rate(), 1e6 / exposure_us)  # what the stream can deliver
                self.cam.set_acquisition_mode(Aravis.AcquisitionMode.CONTINUOUS)
                self.stream = self.cam.create_stream(None, None)
                for _ in range(4):
                    self.stream.push_buffer(Aravis.Buffer.new_allocate(self.cam.get_payload()))
                self.cam.start_acquisition()
                self.live = (exposure_us, gain, pixel_format)
                c = self.cam  # each read is a USB round trip (~1 ms): once here instead of per frame
                self.live_meta = {"exposure_us": c.get_exposure_time(), "gain": c.get_gain(),
                                  "pixel_format": c.get_pixel_format_as_string()}
                self.live_temp = (0.0, None)  # (monotonic time read, °C), refreshed at most once a second
            # Newest frame already received: older ones go straight back. Nothing queued: wait for one.
            newest = None
            while (buf := self.stream.try_pop_buffer()) is not None:
                if newest is not None:
                    self.stream.push_buffer(newest)
                newest = buf
            for _ in range(3):
                buf = newest or self.stream.timeout_pop_buffer(int(exposure_us + 3_000_000))
                newest = None
                if buf is None:
                    break
                ok = buf.get_status() == Aravis.BufferStatus.SUCCESS
                result = self._live_frame(buf) if ok else None
                self.stream.push_buffer(buf)  # _live_frame copies, so the buffer can be reused
                if ok:
                    return result
            self._stop_live()
            raise RuntimeError(f"Live frame failed ({buf.get_status().value_nick if buf else 'timeout'}). "
                               "Check usbfs_memory_mb (README).")

    def _live_frame(self, buf) -> tuple[np.ndarray, dict]:
        w, h, data = buf.get_image_width(), buf.get_image_height(), buf.get_data()
        if len(data) not in (w * h, 2 * w * h):
            raise RuntimeError(f"Unsupported (packed?) pixel format {self.live_meta['pixel_format']}")
        img = np.frombuffer(data, np.uint8 if len(data) == w * h else np.uint16).reshape(h, w).copy()
        if time.monotonic() - self.live_temp[0] > 1:
            self.live_temp = (time.monotonic(), self._opt("DeviceTemperature"))
        return img, {"timestamp": datetime.now().isoformat(timespec="milliseconds"), **self.live_meta,
                     "width": w, "height": h, "temperature_c": self.live_temp[1]}

    def _frame(self, buf) -> tuple[np.ndarray, dict]:
        c = self.cam
        w, h, data = buf.get_image_width(), buf.get_image_height(), buf.get_data()
        if len(data) not in (w * h, 2 * w * h):
            raise RuntimeError(f"Unsupported (packed?) pixel format {c.get_pixel_format_as_string()}")
        img = np.frombuffer(data, np.uint8 if len(data) == w * h else np.uint16).reshape(h, w).copy()
        return img, {
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
            "exposure_us": c.get_exposure_time(),
            "gain": c.get_gain(),
            "pixel_format": c.get_pixel_format_as_string(),
            "width": w,
            "height": h,
            "temperature_c": self._opt("DeviceTemperature"),
        }
