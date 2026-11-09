# Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `No camera found` | Check the cable. Is `ls -l /dev/bus/usb/*/*` group `video` for the camera? If not, the udev rule isn't active: apply it and replug ({doc}`host-setup`) |
| `Frame failed … size-mismatch` | usbfs buffer still at 16 MB ({doc}`host-setup`) |
| `LIBUSB_ERROR_BUSY` | Another process has the camera, usually a second `specpol` or a script. Only one can open it at a time |
| Page doesn't load from another PC | The port is closed in the firewall. Open it ([network access](host-setup.md#network-access)) and check with `curl http://<host>:8501/_stcore/health` |
| Page loads but the preview images stay empty | Started with `streamlit run …/app.py` instead of `specpol`, so the `/live` route is missing. `curl -s -o /dev/null -w "%{http_code}" http://<host>:8501/live/x/0` should give 404 (route there, unknown session) |
| Preview is slow or stutters | Compare the two FPS numbers. Lower first number: raise **Preview binning** (2 cuts the data to a fifth). A low second number means a long exposure: it limits the frame rate to 1/exposure |
| `Address already in use` | Another specpol (or something else) uses the port: stop it or pass `--port` |
