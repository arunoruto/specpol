# DZK 33UX250 polarimetric measurements

Streamlit dashboard for soil-sample measurements with The Imaging Source DZK 33UX250
(Sony IMX250MZR, 2×2 on-chip polarizers at 0/45/90/135°). The camera is driven through
[Aravis](https://github.com/AravisProject/aravis), the open-source USB3 Vision driver from nixpkgs.
No vendor SDK is needed.

## Setup (NixOS)

The host needs USB access and a bigger usbfs buffer (already set in `~/.config/flake`, host `kuchiki`):

```nix
boot.kernelParams = [ "usbcore.usbfs_memory_mb=1000" ];
services.udev.extraRules = ''
  SUBSYSTEM=="usb", ATTRS{idVendor}=="199e", MODE="0660", GROUP="video", TAG+="uaccess"
'';
```

After switching, replug the camera (and reboot for the kernel parameter). Check with `arv-tool-0.8`.

`Frame failed ... size-mismatch` errors mean the usbfs buffer is still at 16 MB
(`cat /sys/module/usbcore/parameters/usbfs_memory_mb`). Without a reboot:
`echo 1000 | sudo tee /sys/module/usbcore/parameters/usbfs_memory_mb`.

On macOS none of this is needed: plug in the camera and run as below (needs Nix).

## Run

```sh
devenv shell          # or: nix run nixpkgs#devenv -- shell
app                   # = uv run streamlit run app.py
DZK_FAKE=1 app        # simulated camera, no hardware needed
                      # open http://localhost:8501/?demo for the visitor demo view
uv run python test_polar.py
```

## Workflow

1. Sidebar: sample ID, gain, pixel format, frames per filter, and the filter table
   (name, wavelength, exposure per filter). Add a `dark` row for dark frames.
2. Use the preview (Intensity / DoLP / AoLP / Raw) and the saturation readout to pick exposures.
3. **Start**, insert the filter it asks for, then **Capture**. Repeat for each filter.

## Data layout

```
data/<sample>/<YYYY-MM-DD_HHMMSS>/
  metadata.json          # sample, operator, notes, camera, settings, filters, every frame's actual settings
  <filter>_000.tiff      # raw mosaic, uint8/uint16, same per-frame JSON in the TIFF description
```

Analysis: `polar.stokes(tifffile.imread(path))` → S0, S1, S2, DoLP, AoLP.
Check the `PATTERN` in `polar.py` once with a linear polarizer at 0°: AoLP should read about 0°.
