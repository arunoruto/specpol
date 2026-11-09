# Architecture

```text
src/specpol/
  cli.py        `specpol` command: starts Streamlit with server.py and fixed settings
  server.py     ASGI app: app.py plus the /live stream routes, on one server and port
  app.py        the dashboard: preview, demo, video, measurement runs
  live.py       preview stream and video recording
  camera.py     Aravis wrapper
  polar.py      mosaic split, binning, Stokes math
tests/          pytest, against simulated cameras
```

## Data flow

```text
camera (raw 2×2 mosaic) ──Aravis, USB3──▶ camera.py ──▶ polar.py (split, Stokes)
    ├─ measurement: Camera.grab ──▶ TIFF + metadata.json
    └─ preview: Camera.grab_live ──▶ live.py (render, JPEG) ──MJPEG /live──▶ browser <img>
```

## Why the preview isn't a Streamlit widget

Streamlit has no widget for a camera on the *server* (`st.camera_input` uses the viewer's
webcam). The first version reran a Streamlit fragment per frame and sent each frame as an inline
image. That showed "Running" forever, made the frame rate depend on round trips, and in Safari
flickered and reset the scroll position on every frame.

Now every preview image is an `<img src="live/<session>/<slot>">` that receives an **MJPEG**
stream (`multipart/x-mixed-replace`): the browser replaces the image by itself whenever a new
JPEG arrives, without any Streamlit rerun. Only the metrics row is a fragment, refreshed once a
second.

## One port

`server.py` builds an `st.App` with the stream route (`specpol.live.routes`), so the images come
from the Streamlit server itself, at a relative URL. Page and images share host, port and
protocol: an SSH tunnel, a reverse proxy, HTTPS or a firewall rule for the page automatically
covers the images. (A separate stream port, as in an earlier version, broke behind tunnels and
needed its own firewall rule.)

## Frames: capture, render, send

{class}`~specpol.live.LiveFeed` runs one **capture thread** per process. While any stream is open
it calls {meth}`~specpol.camera.Camera.grab_live` in a loop (capped at 40 fps):

- the camera streams at the link's maximum frame rate (Mono16 37.5 fps, Mono8 75 fps) instead of
  its default 30;
- `grab_live` returns the **newest frame already received** without waiting for the next one, and
  reads the settings back once per stream start instead of per frame (each read is a USB round
  trip);
- settings changes restart the camera stream, so a frame never mixes old and new settings.

Each browser **session** registers a render function (its views, binning, gamma, mirroring). All
images of a page share **one rendered frame**: the stream that has sent the current frame renders
the newest camera frame (images and JPEG encoding in parallel threads), and the other images of
the page pick it up. Without that, each image chased a different frame and every frame was
rendered once per image, which made a four-image page about 3× slower.

Each stream sends the next frame only once the previous one has gone out (TCP backpressure). A
slow link therefore **skips frames** instead of queueing them, and the FPS counter shows what the
browser really gets. Video recording (`LiveFeed.record`) uses the same shared frames, so a video
shows exactly what the page shows.

Measurements stay independent: `Camera.grab` stops the live stream, applies the settings and
waits for a frame that started after that, and `LiveFeed.paused()` keeps the capture thread off the
camera for the whole run.

## Performance

Measured with the real camera on `mayuri` (6 cores), each view in a fresh process:

| View | fps |
|---|---|
| One view, binning 2 or 4 | ~35 (camera limit in Mono16) |
| One view, binning 1 | ~17 (rendering 1224×1024 per frame) |
| Four-image grid (demo), binning 2 | ~14 |
| Four-image grid (demo), binning 1 | ~4.5 |

With binning 1 the cost is splitting the mosaic and computing the Stokes parameters per frame
(~60 ms for a grid), which can't be spread over the images.
