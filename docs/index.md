# specpol

**Multispectral polarization imaging: see the polarization of light live, and measure it filter by filter.**

specpol drives a polarization camera, The Imaging Source **DZK 33UX250** (Sony IMX250MZR,
2448×2048). In front of every pixel sits a tiny polarizer at 0°, 45°, 90° or 135°. From each 2×2
super-pixel specpol computes the Stokes parameters and shows how strongly (**DoLP**) and in which
direction (**AoLP**) the light is polarized, live at up to ~35 fps. Measurement runs step through
spectral filters and save raw frames with full metadata, for spectro-polarimetry of soil samples.

- **Live preview**: eight views (intensity, S1, S2, DoLP, AoLP, AoLP×DoLP, error, raw), any four side by side
- **Measurement runs**: filter by filter, N frames each, raw TIFFs and full metadata written after every frame
- **Video snippets**: record what the preview shows as an MP4 (H.264), one click
- **Visitor demo**: a German, open-day view at `?demo` that tells the "polarizing sunglasses" story
- **No vendor SDK**: the camera runs on [Aravis](https://github.com/AravisProject/aravis), the open-source USB3 Vision driver
- **No hardware needed to try it**: `specpol --fake` runs a simulated camera

```sh
devenv shell      # Nix: everything specpol needs, see Installation
specpol --fake    # simulated camera
specpol           # real camera
```

Then open <http://localhost:8501>.

Next step: a motorized **filter wheel**, so a measurement steps through all filters by itself after
one button press.

```{toctree}
:maxdepth: 2
:caption: Guide

installation
host-setup
usage
data
troubleshooting
```

```{toctree}
:maxdepth: 2
:caption: Reference

architecture
api
```
