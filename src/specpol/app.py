"""Streamlit dashboard: live polarization preview + filter-by-filter measurement runs.

Run with `specpol` (or `specpol --fake` for the simulated camera), not with `streamlit run`.
Open with ?demo (http://localhost:8501/?demo) for the visitor-friendly demo view.
Add &cols=4 for a single row of four images on widescreen monitors.
"""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
import streamlit as st
import tifffile

from specpol.camera import Camera, full_scale
from specpol.live import POOL, LiveFeed
from specpol.polar import PATTERN, from_intensities, mean_stokes, split

DATA = Path("data")
FILTERS = Path("filters.json")  # last used filter table
DEFAULT_FILTERS = [{"name": "open", "wavelength_nm": None, "exposure_ms": 10.0}]

DEMO = "demo" in st.query_params
COLS = int(st.query_params.get("cols", 2))  # grid columns: ?cols=4 puts all four side by side (widescreen)
MIRROR = st.query_params.get("mirror", "1" if DEMO else "0") == "1"  # preview like a mirror; demo default, ?mirror=0 off
BIN = int(st.query_params.get("bin", 1))  # preview: average n×n super-pixels, ?bin=2 = 4x fewer pixels, 2x less noise
st.set_page_config("Polarisationskamera" if DEMO else "DZK 33UX250", layout="wide",
                   initial_sidebar_state="collapsed" if DEMO else "auto")


def safe(s: str) -> str:
    return re.sub(r"[^\w.-]+", "_", s.strip()) or "unnamed"


def to8(x, lo, hi):
    return (np.clip((x - lo) / max(hi - lo, 1e-9), 0, 1) * 255).astype(np.uint8)


def hue(h):
    """Fully saturated RGB (uint8) for hue h in [0, 1): 0 red, 1/3 green, 2/3 blue."""
    return (np.clip(np.abs((h[..., None] * 6 + np.array([0, 4, 2])) % 6 - 3) - 1, 0, 1) * 255).astype(np.uint8)


AOLP_LEGEND = np.tile(hue(np.linspace(0, 1, 360, endpoint=False)), (12, 1, 1))
HUE_LUT = hue(np.linspace(0, 1, 256, endpoint=False))


def aolp_rgb(aolp):
    """hue((aolp % 180) / 180) via a 256-colour LUT, ~4x faster. AoLP is in [-90, 90]:
    +180 makes it positive, & 255 wraps the 180° period (one full colour wheel)."""
    return HUE_LUT[((aolp + 180) * (256 / 180)).astype(np.intp) & 255]


@st.cache_resource
def camera():
    return Camera()


@st.cache_resource
def live_feed():
    """Capture thread and MJPEG streams for the preview images (live.py), one per app process.
    The /live route that serves them is mounted by server.py: run `streamlit run server.py`."""
    return LiveFeed(camera())


try:
    cam, feed = camera(), live_feed()
except Exception as e:
    st.error(f"Camera: {e}")
    st.stop()

# ---- sidebar: settings -------------------------------------------------------------
bounds = cam.bounds()
with st.sidebar:
    st.header("Sample")
    sample = st.text_input("Sample ID")
    operator = st.text_input("Operator")
    notes = st.text_area("Notes")
    st.header("Camera")
    formats = cam.pixel_formats()
    fmt = st.selectbox("Pixel format", formats, index=next((i for i, f in enumerate(formats) if f.endswith("Mono16")), 0))
    gain = st.number_input("Gain", *map(float, bounds["gain"]), value=float(bounds["gain"][0]))
    n_frames = st.number_input("Frames per filter", 1, 1000, 5)
    dolp_full = st.slider("DoLP at full brightness", 0.05, 1.0, 0.3,
                          help="DoLP shown as white (DoLP view) or full colour (AoLP×DoLP). Lower = more "
                               "contrast for weakly polarized scenes (most real scenes: DoLP 0.05–0.3)")
    gamma = st.slider("Display gamma", 1.0, 3.0, 2.2, 0.1,
                      help="Brightens shadows and midtones of the linear sensor data, preview only (saved TIFFs stay raw). 1 = linear")
    preview_bin = st.select_slider("Preview binning", [1, 2, 4], value=BIN if BIN in (1, 2, 4) else 1,
                                   help="Average n×n super-pixels in the preview: n² fewer pixels (faster), "
                                        "n× less noise, 1/n resolution. Preview only, saved TIFFs stay raw")
    st.header("Video")
    rec_s = st.slider("Length (s)", 1, 30, 5)
    rec = st.button("Record", help="MP4 of the preview as you see it (view or grid, binning, gamma), "
                                   "saved under data/videos/")
    st.header("Filters")
    st.caption("One row per filter, captured in this order. Add a `dark` row (lens capped) for dark frames.")
    filters_df = st.data_editor(
        json.loads(FILTERS.read_text()) if FILTERS.exists() else DEFAULT_FILTERS,
        num_rows="dynamic",
        column_config={
            "name": st.column_config.TextColumn("Name", required=True),
            "wavelength_nm": st.column_config.NumberColumn("λ (nm)"),
            "exposure_ms": st.column_config.NumberColumn("Exposure (ms)", min_value=bounds["exposure_us"][0] / 1e3, required=True),
        },
    )
filters = [{k: (None if v != v else v) for k, v in f.items()} for f in filters_df if f.get("name")]  # NaN → None

run = st.session_state.get("run")
# Single column; preview last so its image reload never pushes other elements around.
right = st.container()  # measurement controls
left = st.container()  # live preview

# ---- live preview ------------------------------------------------------------------
VIEWS = ["Intensity", "S1", "S2", "DoLP", "AoLP", "AoLP×DoLP", "Error", "Raw"]
ANGLES = ["I0", "I45", "I90", "I135"]
GRID_DEFAULT = ["Intensity", "DoLP", "AoLP", "Error"]
# Demo grid: the "polarizing sunglasses" story, then the full picture in colour.
DEMO_CAPTIONS = {
    "Intensity": "Normales Kamerabild",
    "I0": "Durch einen Polfilter bei 0° (wie eine Polbrille)",
    "I90": "Durch einen Polfilter bei 90° (Brille gedreht)",
    "AoLP×DoLP": "Polarisation: Farbe = Richtung, Helligkeit = Stärke",
}
DEMO_TEXT = """
Licht ist eine Welle, die in eine bestimmte Richtung schwingt: seine **Polarisation**.
Unser Auge sieht diese Richtung nicht, diese Kamera schon: Vor jedem ihrer 5 Millionen Pixel
sitzt ein winziger Polfilter, abwechselnd in vier Richtungen (0°, 45°, 90°, 135°).
Aus den vier Helligkeiten berechnen wir für jeden Bildpunkt, wie stark und in welche Richtung das Licht polarisiert ist.

**Probier's aus:** Halte dein Handy vor die Kamera und dreh es langsam.
Oder schau dir Spiegelungen auf glänzenden Oberflächen an, und durchsichtiges Plastik vor einem Bildschirm.

Wir nutzen das in der Forschung für **Bodenproben**: Wie stark der Boden das Licht polarisiert,
verrät etwas über seine Oberfläche, z.B. Rauigkeit oder Feuchtigkeit.
"""

with left:
    if DEMO:
        st.title("Polarisation sichtbar machen")
        st.markdown(DEMO_TEXT)
        view, cells = "Grid", list(DEMO_CAPTIONS)
    else:
        view = st.segmented_control("View", VIEWS + ["Grid"], default="Intensity") or "Intensity"
        cells = [view]
    if view == "Grid" and not DEMO:
        cells = [col.selectbox(f"Cell {k + 1}", VIEWS + ANGLES, index=(VIEWS + ANGLES).index(d), key=f"cell{k}")
                 for k, (col, d) in enumerate(zip(st.columns(4), GRID_DEFAULT))]

    def auto_preview():
        with feed.paused():
            st.session_state.preview_ms = cam.auto_exposure(gain, fmt, st.session_state.preview_ms * 1e3) / 1e3

    e1, e2 = st.columns([4, 1], vertical_alignment="bottom")
    st.session_state.setdefault("preview_ms", 10.0)
    preview_ms = e1.number_input("Preview exposure (ms)", min_value=bounds["exposure_us"][0] / 1e3,
                                 key="preview_ms", disabled=bool(run))
    e2.button("Auto", on_click=auto_preview, disabled=bool(run), help="Brightest pixels to ~80% of full scale")


def stretch(x):
    """Percentile stretch plus display gamma (12-bit LUT: fast, and no banding in the shadows)."""
    lo, hi = np.percentile(x[::4, ::4], [0.5, 99.5])  # subsampled: same limits, 10x faster
    lut = (np.linspace(0, 1, 4096) ** (1 / gamma) * 255).astype(np.uint8)
    return lut[(np.clip((x - lo) / max(hi - lo, 1e-9), 0, 1) * 4095).astype(np.intp)]


def render(view, img, s, angles):
    """uint8 image for one view. Raw is full sensor res, everything else one pixel per 2x2 super-pixel."""
    if view == "Raw":
        return stretch(img)
    if view in ANGLES:
        return stretch(angles[int(view[1:])])
    if view in ("S1", "S2", "Error"):  # signed: mid-grey = 0, symmetric stretch
        v = np.percentile(np.abs(s[view.lower()][::4, ::4]), 99.5)
        return to8(s[view.lower()], -v, v)
    if view == "DoLP":
        return to8(s["dolp"], 0, dolp_full)
    if view == "AoLP":
        return aolp_rgb(s["aolp"])
    if view == "AoLP×DoLP":  # colour = angle, brightness = DoLP, dimmed where it's dark (noisy DoLP)
        v = np.clip(s["dolp"] / dolp_full, 0, 1) * stretch(s["s0"]) / 255
        return (aolp_rgb(s["aolp"]) * v[..., None]).astype(np.uint8)
    return stretch(s["s0"])


def frames(img):
    """The preview images for this session, one per cell. Runs in the stream server (live.py) once per
    camera frame, with this run's widget values (gamma, dolp_full, cells)."""
    # Grid outside the demo: small tiles, bin 2x on top (was: render full, then show every 2nd pixel).
    angles = split(img, (BIN if DEMO else preview_bin) * (2 if len(cells) > 1 and not DEMO else 1))
    s = from_intensities(angles, {k for k in ("dolp", "aolp", "error") if any(k in v.lower() for v in cells)})
    if MIRROR:  # images flip left-right; a mirror also flips polarization angles: θ → -θ
        s = {**s, "s2": -s["s2"]} | ({"aolp": -s["aolp"]} if "aolp" in s else {})
        angles = {a: angles[-a % 180] for a in angles}  # 45° ↔ 135°
    ims = POOL.map(lambda v: render(v, img, s, angles), cells)
    return [np.ascontiguousarray(im[:, ::-1]) if MIRROR else im for im in ims]


# The stream server renders with this session's settings; the camera runs with the latest ones.
sid = st.session_state.setdefault("sid", uuid.uuid4().hex)
feed.views[sid] = frames
feed.settings = ((run["filters"][run["i"]]["exposure_ms"] if run else preview_ms) * 1e3, gain, fmt)
STREAM = f"live/{sid}"  # relative: same host, port and protocol as the page (server.py mounts /live)
W, H = cam.size()


def live_image(slot, caption=None, where=st):
    """MJPEG stream from live.py: the browser keeps the image up to date by itself, no reruns.
    aspect-ratio reserves the space before the first frame, so the page height never changes."""
    cap = f'<figcaption style="text-align:center;opacity:.6;font-size:.875rem">{caption}</figcaption>' if caption else ""
    where.html(f'<figure style="margin:0"><img src="{STREAM}/{slot}" '
               f'style="width:100%;aspect-ratio:{W}/{H};display:block">{cap}</figure>')


@st.fragment(run_every=1)
def metrics():
    if feed.error:
        st.warning(f"Preview: {feed.error}")
    if DEMO or not feed.frame:
        return
    _, img, m = feed.frame
    full = full_scale(img.dtype)
    ms = mean_stokes(img)  # frame means of the intensities, then DoLP/AoLP from those
    a, b, c, d, e, f, g = st.columns(7)
    a.metric("Max", f"{img.max()} / {full}")
    b.metric("Saturated", f"{(img >= full).mean():.2%}")
    c.metric("DoLP", f"{ms['dolp']:.3f}")
    d.metric("AoLP", f"{ms['aolp']:.1f}°")
    e.metric("Error / S0", f"{ms['error'] / max(ms['s0'], 1e-9):.2%}")
    f.metric("Exposure", f"{m['exposure_us'] / 1e3:.2f} ms")
    g.metric("FPS", f"{feed.fps(sid):.0f} / {cam.live_fps or 0:.0f}",
             help="Preview frames reaching this browser (last 2 s) / what the camera can deliver at this exposure "
                  "and pixel format (Mono16 ≤ 37.5, Mono8 ≤ 75). If the first is lower, rendering or the network "
                  "is the limit: try preview binning")


with left:
    metrics()
    if {"AoLP", "AoLP×DoLP"} & set(cells):
        st.image(AOLP_LEGEND, width="stretch", caption="Farbe = Schwingungsrichtung des Lichts, 0° bis 180°" if DEMO
                 else "AoLP 0° → 180° (red 0°, green 60°, blue 120°)")
    if len(cells) == 1:
        live_image(0)
    else:
        for i in range(0, len(cells), COLS):
            for j, (col, v) in enumerate(zip(st.columns(COLS), cells[i:i + COLS])):
                live_image(i + j, DEMO_CAPTIONS[v] if DEMO else v, col)

# ---- video snippet: the frames this page shows, as MP4 (live.py) ---------------------
if rec:
    path = DATA / "videos" / f"{datetime.now():%Y-%m-%d_%H%M%S}_{safe('_'.join(cells))}.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    with st.sidebar:
        bar = st.progress(0.0, "Recording…")
        n = feed.record(sid, rec_s, path, COLS, progress=lambda f: bar.progress(f, "Recording…"))
        bar.empty()
    st.session_state.video = (path, n, rec_s)
if "video" in st.session_state:
    path, n, secs = st.session_state.video
    with st.sidebar:
        st.caption(f"`{path.name}`: {n} frames, {n / secs:.0f} fps")
        st.download_button("Download video", path.read_bytes(), path.name, "video/mp4")

if DEMO:
    st.stop()  # no measurement controls for visitors


# ---- measurement run ---------------------------------------------------------------
def write_meta(r):
    (r["dir"] / "metadata.json").write_text(json.dumps(r["meta"], indent=2, default=str))


def capture(r):
    f = r["filters"][r["i"]]
    # ponytail: manual filter swap; a filter wheel would move to f's slot here.
    bar = st.progress(0.0, f"Capturing {f['name']}")
    with feed.paused():  # the preview stream must not restart between the measurement's frames
        for k in range(r["frames"]):
            img, m = cam.grab(f["exposure_ms"] * 1e3, r["meta"]["settings"]["gain"], r["meta"]["settings"]["pixel_format"])
            name = f"{safe(f['name'])}_{k:03d}.tiff"
            entry = {"file": name, "filter": f["name"], "wavelength_nm": f["wavelength_nm"], "frame": k, **m}
            tifffile.imwrite(r["dir"] / name, img, description=json.dumps(entry))
            r["meta"]["frames"].append(entry)
            write_meta(r)  # after every frame, so a crash never loses what's on disk
            bar.progress((k + 1) / r["frames"], f"Capturing {f['name']}: {k + 1}/{r['frames']}")
    r["i"] += 1


with right:
    st.subheader("Measurement")
    if run is None:
        names = [f["name"] for f in filters]
        problem = (
            "Enter a sample ID." if not sample.strip()
            else "Add at least one filter." if not filters
            else "Filter names must be unique." if len(set(map(safe, names))) != len(names)
            else None
        )
        if problem:
            st.warning(problem)
        if st.button("Start", type="primary", disabled=bool(problem)):
            FILTERS.write_text(json.dumps(filters, indent=2))
            started = datetime.now()
            d = DATA / safe(sample) / started.strftime("%Y-%m-%d_%H%M%S")
            d.mkdir(parents=True)
            st.session_state.run = run = {
                "dir": d, "filters": filters, "frames": int(n_frames), "i": 0,
                "meta": {
                    "sample": sample, "operator": operator, "notes": notes,
                    "started": started.isoformat(timespec="seconds"), "finished": None,
                    "camera": cam.info(),
                    "settings": {"gain": gain, "pixel_format": fmt, "frames_per_filter": int(n_frames)},
                    "filters": filters,
                    "polarizer_pattern": {f"{r},{c}": a for (r, c), a in PATTERN.items()},
                    "frames": [],
                },
            }
            write_meta(run)
            st.rerun()
    else:
        f, n = run["filters"][run["i"]], len(run["filters"])
        st.info(f"Step {run['i'] + 1}/{n}: insert filter **{f['name']}**"
                + (f" ({f['wavelength_nm']:g} nm)" if f["wavelength_nm"] else "")
                + f", exposure {f['exposure_ms']:g} ms. Then press Capture.")
        def auto_filter():
            with feed.paused():
                f["exposure_ms"] = cam.auto_exposure(gain, fmt, f["exposure_ms"] * 1e3) / 1e3
            f["exposure_auto"] = True  # recorded in metadata.json
            write_meta(run)

        a, b, c = st.columns(3)
        clicked_capture, clicked_abort = a.button("Capture", type="primary"), b.button("Abort")
        c.button("Auto-expose", on_click=auto_filter, help="Insert the filter first. Brightest pixels to ~80% of full scale")
        if clicked_capture:
            capture(run)
        done = run["i"] == n
        if clicked_abort or done:
            run["meta"]["finished"] = datetime.now().isoformat(timespec="seconds")
            run["meta"]["aborted"] = not done
            write_meta(run)
            st.session_state.last = (run["dir"], len(run["meta"]["frames"]), done)
            del st.session_state.run
        if clicked_capture or clicked_abort:
            st.rerun()
    if "last" in st.session_state:
        d, k, ok = st.session_state.last
        (st.success if ok else st.warning)(f"{'Finished' if ok else 'Aborted'}: {k} frames in `{d}`")
