# Data and analysis

## Files

```text
data/<sample>/<YYYY-MM-DD_HHMMSS>/
  metadata.json          # sample, operator, notes, camera, settings, filters, polarizer pattern,
                         # every frame's actual settings, started/finished/aborted
  <filter>_000.tiff      # raw mosaic, uint8/uint16; the frame's JSON is also in the TIFF description
data/videos/<YYYY-MM-DD_HHMMSS>_<views>.mp4   # video snippets
filters.json             # the last used filter table
```

Paths are relative to the directory specpol was started in.

`metadata.json` is rewritten after every frame, so a crash never loses frames that are already on
disk. Each frame's settings are read back from the camera (exposure, gain, pixel format, sensor
temperature) rather than taken from what was requested.

Mono16 frames hold the 12-bit sensor values MSB-aligned: full scale is `0xFFF0`.

## Analysis

```python
import tifffile
from specpol import polar

raw = tifffile.imread("data/soil-01/2026-11-07_164600/open_000.tiff")
s = polar.stokes(raw)          # per super-pixel: s0, s1, s2, dolp (0..1), aolp (deg, -90..90), error
m = polar.mean_stokes(raw)     # same, for the whole frame (or a crop): floats
low_noise = polar.from_intensities(polar.split(raw, n=2))  # 2×2 binned
```

See {mod}`specpol.polar` for the details.

## Calibrate the polarizer pattern once

`PATTERN` in `src/specpol/polar.py` maps each 2×2 position to its polarizer angle. ROI offsets or
ReverseX/Y can shift it. Point the camera through a linear polarizer at 0°: **AoLP should read
~0°**. If it reads 90° or ±45°, swap the entries.
