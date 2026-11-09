# Using the dashboard

Start `specpol` and open <http://localhost:8501> (or `http://<host>:8501` from another PC, see
{doc}`host-setup`).

## Live preview

| View | Shows |
|---|---|
| **Intensity** | S0, the normal camera image |
| **S1 / S2** | 0°–90° and 45°–135° differences (mid-grey = 0) |
| **DoLP** | Degree of linear polarization, black 0 → white at *DoLP at full brightness* (sidebar) |
| **AoLP** | Angle of linear polarization as hue (red 0°, green 60°, blue 120°) |
| **AoLP×DoLP** | Hue = angle, brightness = degree. Usually the most telling view |
| **Error** | (I0+I90) − (I45+I135). Zero for ideal polarizers, so it shows noise and artifacts |
| **Raw** | The full-resolution sensor mosaic |
| **Grid** | Any four views or single-angle images (I0, I45, I90, I135) at once |

The metrics row, refreshed once a second:

Max, Saturated
: Brightest pixel and the fraction at full scale. Use them with **Auto** (brightest pixels to ~80%
  of full scale) to pick exposures.

DoLP, AoLP, Error / S0
: Frame averages (intensities averaged first, then DoLP and AoLP computed from those).

FPS
: Frames reaching *this* browser / what the camera can deliver at this exposure and pixel format
  (Mono16 ≤ 37.5, Mono8 ≤ 75). If the first is clearly lower, rendering or the network is the
  limit: try preview binning.

Sidebar display settings change only the preview, never saved data:

DoLP at full brightness
: The DoLP shown as white in the **DoLP** view and as full colour in **AoLP×DoLP** (default 0.3).
  Lower it for weakly polarized scenes (most real scenes: DoLP 0.05–0.3).

Display gamma
: Brightens shadows and midtones of the linear sensor data.

Preview binning (1 / 2 / 4)
: Averages n×n super-pixels: n× less noise, 1/n resolution, n² fewer pixels to process. About
  35 fps at 2 and 4 against ~17 at 1, with a fifth of the data at 2, which matters over slow links.
  A grid of four images bins 2× more on top.

## Measurement run

Filters are swapped by hand for now. Planned: a motorized **filter wheel**, so a run steps through
all filters by itself after one button press.

1. In the sidebar, enter a **sample ID** (required), operator and notes. Pick the pixel format
   (Mono16 is the default), gain and frames per filter.
2. Fill the **filter table**: name, wavelength and exposure, one row per filter in capture order.
   Add a `dark` row (lens capped) for dark frames. The table is saved to `filters.json` and
   restored next time.
3. Press **Start**. For each step, insert the filter it asks for, optionally **Auto-expose**, then
   press **Capture**. **Abort** keeps everything captured so far.

The preview pauses while a measurement grabs its frames, so every saved frame is exposed with
exactly the requested settings. Files: see {doc}`data`.

## Video snippet

Sidebar **Video**: pick a length (1–30 s) and press **Record**. It records exactly what the page
shows (view or grid, binning, gamma, mirroring) as an H.264 MP4 with real-time timestamps, saved
to `data/videos/<YYYY-MM-DD_HHMMSS>_<views>.mp4` and offered as a download. The frame rate is the
preview's: e.g. ~30 fps for one view at binning 2, ~19 fps for a four-image grid. It's for
showing, not analysis: use a measurement run for raw data.

## Visitor demo

Open <http://localhost:8501/?demo>: a German, sidebar-free view with explanatory text and a fixed
four-image grid (normal image, 0° polarizer, 90° polarizer, AoLP×DoLP), without measurement
controls.

| Parameter | Effect |
|---|---|
| `?demo` | Demo view, mirrored like a mirror (with polarization angles flipped to match) |
| `&cols=4` | All four images in one row, for 21:9 screens |
| `&mirror=0` | Turn mirroring off (or `?mirror=1` to mirror outside the demo) |
| `&bin=2` | Average 2×2 super-pixels: smoother (~14 instead of ~4.5 fps), less noise, half resolution |
