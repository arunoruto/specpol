# specpol

[![docs](https://github.com/arunoruto/dzk-33ux250/actions/workflows/docs.yml/badge.svg)](https://arunoruto.github.io/dzk-33ux250/)

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

Next: a motorized **filter wheel**, so a measurement steps through all filters after one button press.

## Quick start

```sh
devenv shell          # or, without devenv installed: nix run nixpkgs#devenv -- shell
specpol --fake        # simulated camera, no hardware needed
specpol               # real camera
uv run pytest         # tests
```

Then open <http://localhost:8501>.

## Documentation

**<https://arunoruto.github.io/dzk-33ux250/>**, built from [`docs/`](docs/):

- [Installation](docs/installation.md): Nix/devenv, Ubuntu, the `specpol` command
- [Host setup](docs/host-setup.md): camera access (udev, USB buffer) and opening the firewall on
  NixOS, Ubuntu, Fedora and macOS
- [Using the dashboard](docs/usage.md), [data and analysis](docs/data.md),
  [troubleshooting](docs/troubleshooting.md), [architecture](docs/architecture.md)

Build locally: `uv run --only-group docs sphinx-build docs docs/_build/html`.

## Layout

```text
src/specpol/   cli.py (the `specpol` command), server.py, app.py (dashboard),
               live.py (preview stream, video), camera.py (Aravis), polar.py (Stokes math)
tests/         pytest, against simulated cameras
docs/          Sphinx docs (Markdown via MyST), published by .github/workflows/docs.yml
```
