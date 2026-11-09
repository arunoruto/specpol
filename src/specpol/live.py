"""MJPEG live preview: one capture thread, frames pushed to the browsers over plain HTTP.

Streamlit has no widget for a server-side camera, and rerunning a fragment per frame costs a full
round trip, shows "Running" forever and flickers in Safari. Here every preview image is an
<img src="/live/<session>/<slot>"> that the browser updates by itself (multipart/x-mixed-replace).
The route is served by Streamlit's own server (server.py), so the stream uses the page's host,
port and protocol: whatever reaches the page (tunnel, proxy, firewall rule) also carries the images.
Each stream sends the newest frame once the previous one is out, so a slow link drops frames
instead of queueing them.
"""

import io
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from fractions import Fraction

import av
import numpy as np
from anyio import to_thread
from PIL import Image
from starlette.responses import Response, StreamingResponse
from starlette.routing import Route

#: Renders and JPEG-encodes the images of a frame in parallel (numpy and PIL release the GIL).
POOL = ThreadPoolExecutor(8)


def tile(ims, cols) -> np.ndarray:
    """One RGB image: the slot images in rows of `cols` (grey ones converted), like the page grid."""
    ims = [np.repeat(im[..., None], 3, axis=2) if im.ndim == 2 else im for im in ims]
    h, w = max(im.shape[0] for im in ims), max(im.shape[1] for im in ims)
    rows = -(-len(ims) // cols)
    out = np.zeros((rows * h, min(cols, len(ims)) * w, 3), np.uint8)
    for k, im in enumerate(ims):
        r, c = divmod(k, cols)
        out[r * h:r * h + im.shape[0], c * w:c * w + im.shape[1]] = im
    return out


def jpeg(im) -> bytes:
    """A uint8 grey or RGB image as JPEG (quality 85)."""
    buf = io.BytesIO()
    Image.fromarray(im).save(buf, "JPEG", quality=85)
    return buf.getvalue()


class LiveFeed:
    """Capture thread plus per-session rendering for the preview streams and video recording.

    The app sets :attr:`settings` (exposure, gain, pixel format) and registers each browser
    session's render function in :attr:`views`; :func:`stream` serves the result. One instance per
    process, available as ``live.FEED``.
    """

    def __init__(self, cam, max_fps=40):
        self.cam, self.max_fps = cam, max_fps
        self.settings = None  # (exposure_us, gain, pixel_format), set by the app on every run
        self.frame = None  # (frame id, raw mosaic, metadata) of the newest frame
        self.error = None  # last grab error, shown by the app
        self.views = {}  # session -> function(raw) -> list of uint8 images, one per slot
        self.cache, self.locks = {}, {}  # session -> (frame id, [jpeg per slot]); render once per frame
        self.clients = self.holds = 0
        self.grabbed, self.sent = deque(maxlen=100), {}  # timestamps: camera frames, frames sent per session
        self.cond = threading.Condition()
        threading.Thread(target=self._capture, daemon=True).start()
        global FEED
        FEED = self

    def fps(self, sid=None, window=2.0) -> float:
        """Frames per second over the last `window` s: sent to session `sid`, or grabbed from the camera.
        Sending blocks while the network is busy, so the sent rate is what the browser actually gets."""
        times, now = self.grabbed if sid is None else self.sent.get(sid, ()), time.monotonic()
        return sum(now - t < window for t in list(times)) / window

    @contextmanager
    def paused(self):
        """Keep the capture thread off the camera, e.g. while a measurement grabs its frames."""
        with self.cond:
            self.holds += 1
        try:
            yield
        finally:
            with self.cond:
                self.holds -= 1
                self.cond.notify_all()

    def _capture(self):
        while True:
            with self.cond:
                # Free-running, so a fresh frame is ready whenever a stream wants one (grabbing only
                # on demand measured slower: each request then waits for the grab).
                if not self.cond.wait_for(lambda: self.clients and self.settings and not self.holds, timeout=2):
                    if not self.holds:
                        self.cam.stop_live()  # nobody watching: stop streaming over USB
                    continue
                settings = self.settings
            t = time.perf_counter()
            try:
                img, meta = self.cam.grab_live(*settings)
            except Exception as e:  # noqa: BLE001 - shown in the app, retried
                with self.cond:
                    self.error = str(e)
                time.sleep(1)
                continue
            with self.cond:
                self.error = None
                self.frame = ((self.frame[0] + 1) if self.frame else 1, img, meta)
                self.grabbed.append(time.monotonic())
                self.cond.notify_all()
            time.sleep(max(0.0, 1 / self.max_fps - (time.perf_counter() - t)))

    def _next(self, sid, last):
        """(frame id, [jpeg per slot], [image per slot]) newer than `last` for session `sid`, or Nones
        after 5 s. All streams of a session (and a recording) share one rendered frame: a caller that
        already has it renders the newest camera frame, the others pick that up. Otherwise each
        stream would chase a different frame and every frame would be rendered once per slot."""
        with self.locks.setdefault(sid, threading.Lock()):
            cached = self.cache.get(sid)
            if cached and cached[0] > last:
                return cached
            with self.cond:
                if not self.cond.wait_for(lambda: self.frame and self.frame[0] > last, timeout=5):
                    return None, None, None
                fid, img = self.frame[0], self.frame[1]
            ims = self.views[sid](img)
            cached = self.cache[sid] = (fid, list(POOL.map(jpeg, ims)), ims)
            return cached

    def record(self, sid, seconds, path, cols=2, progress=None) -> int:
        """Record what session `sid` sees for `seconds` as an H.264 MP4 (grids tiled `cols` wide).
        Frames carry their real timestamps, so playback runs at real speed whatever the frame rate.
        Returns the number of frames; `progress(fraction)` is called after each one."""
        with self.cond:
            self.clients += 1  # keeps the camera streaming even if no browser is watching
            self.cond.notify_all()
        try:
            with av.open(str(path), "w", options={"movflags": "+faststart"}) as out:
                stream, t0, last, n = None, time.monotonic(), 0, 0
                while time.monotonic() - t0 < seconds:
                    fid, _, ims = self._next(sid, last)
                    if fid is None or (t := time.monotonic() - t0) >= seconds:
                        continue
                    last, frame = fid, tile(ims, cols)
                    if stream is None:  # size known only now; yuv420p needs even dimensions
                        h, w = frame.shape[0] // 2 * 2, frame.shape[1] // 2 * 2
                        stream = out.add_stream("libx264", options={"crf": "20", "preset": "veryfast"})
                        stream.width, stream.height, stream.pix_fmt = w, h, "yuv420p"
                        stream.time_base = stream.codec_context.time_base = Fraction(1, 1000)  # ms timestamps
                    vf = av.VideoFrame.from_ndarray(np.ascontiguousarray(frame[:h, :w]), format="rgb24")
                    vf.pts, vf.time_base = int(t * 1000), Fraction(1, 1000)
                    out.mux(stream.encode(vf))
                    n += 1
                    if progress:
                        progress(min(t / seconds, 1.0))
                if stream is not None:
                    out.mux(stream.encode(None))  # flush the encoder
            return n
        finally:
            with self.cond:
                self.clients -= 1

    async def parts(self, sid, slot):
        """The multipart body of one stream: a JPEG part per frame, for as long as the browser listens."""
        with self.cond:
            self.clients += 1
            self.cond.notify_all()
        try:
            last = 0
            while True:
                # Blocking wait and render in a worker thread; abandoned (finishes on its own within
                # 5 s) when the browser goes away and Starlette cancels this generator.
                fid, jpegs, _ = await to_thread.run_sync(self._next, sid, last, abandon_on_cancel=True)
                if fid is None:
                    continue
                last = fid
                if slot < len(jpegs):  # the view may have fewer slots since the page last loaded
                    data = jpegs[slot]
                    if slot == 0:  # all slots of a session get the same frames; the next one is only
                        # rendered once this one is sent, so the count still follows the network
                        self.sent.setdefault(sid, deque(maxlen=100)).append(time.monotonic())
                    yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(data) + data + b"\r\n"
        finally:
            with self.cond:
                self.clients -= 1


#: The LiveFeed of this process (created by app.py on the first page load).
FEED = None


async def stream(request):
    """Endpoint for ``/live/<session>/<slot>``: that image's MJPEG stream, 404 for unknown sessions."""
    sid, slot = request.path_params["sid"], request.path_params["slot"]
    if FEED is None or sid not in FEED.views:
        return Response(status_code=404)
    return StreamingResponse(FEED.parts(sid, slot), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


#: Starlette routes, mounted by server.py next to Streamlit's own.
routes = [Route("/live/{sid}/{slot:int}", stream)]
