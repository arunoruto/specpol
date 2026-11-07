"""Thin wrapper around Aravis (open-source USB3 Vision driver) for the DZK 33UX250."""

import os
import threading
from datetime import datetime

import gi
import numpy as np

gi.require_version("Aravis", "0.8")
from gi.repository import Aravis  # noqa: E402


def full_scale(dtype) -> int:
    return 255 if dtype == np.uint8 else 0xFFF0  # 12-bit ADC, MSB-aligned in 16 bit


class Camera:
    def __init__(self):
        if os.environ.get("DZK_FAKE"):  # DZK_FAKE=1 → Aravis' simulated camera, for dev without hardware
            Aravis.enable_interface("Fake")
        Aravis.update_device_list()
        if not Aravis.get_n_devices():
            raise RuntimeError("No camera found. Check USB cable and udev permissions (README).")
        self.cam = Aravis.Camera.new(Aravis.get_device_id(0))
        self.lock = threading.Lock()  # preview and capture share one device
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

    def grab(self, exposure_us: float, gain: float, pixel_format: str | None = None) -> tuple[np.ndarray, dict]:
        """Single frame with the given settings. Returns (raw mosaic, actual settings read back)."""
        with self.lock:
            c = self.cam
            if pixel_format and c.get_pixel_format_as_string() != pixel_format:
                c.set_pixel_format_from_string(pixel_format)
            c.set_exposure_time(exposure_us)
            c.set_gain(gain)
            for _ in range(3):  # incomplete USB frames happen (see README: usbfs); bad ones are dropped, never returned
                buf = c.acquisition(int(exposure_us + 3_000_000))
                if buf is not None and buf.get_status() == Aravis.BufferStatus.SUCCESS:
                    break
            else:
                status = buf.get_status().value_nick if buf else "no buffer"
                raise RuntimeError(f"Frame failed 3x ({status}). Check usbfs_memory_mb (README).")
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
