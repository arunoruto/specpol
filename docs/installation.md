# Installation

specpol is a Python package (`src/specpol`) managed with [uv](https://docs.astral.sh/uv/). Besides
Python packages it needs [Aravis](https://github.com/AravisProject/aravis) (the USB3 Vision
driver, a C library used through GObject introspection) and the headers to build PyGObject.

## With Nix (recommended: NixOS, any Linux, macOS)

The repository has a [devenv](https://devenv.sh) environment that provides Aravis, the build
dependencies and Python, and syncs the Python packages with uv:

```sh
git clone https://github.com/arunoruto/dzk-33ux250.git specpol
cd specpol
devenv shell          # or, without devenv installed: nix run nixpkgs#devenv -- shell
specpol --fake        # simulated camera, no hardware needed
```

The first `devenv shell` builds Aravis and syncs the environment, which takes a minute. Inside
the shell, `specpol` (and the old alias `app`) start the dashboard.

## Ubuntu / Debian

:::{note}
specpol is developed and tested on NixOS. These commands follow the Ubuntu package names but
haven't been run on Ubuntu yet; please report what differs.
:::

```sh
sudo apt install aravis-tools gir1.2-aravis-0.8 libaravis-0.8-0 \
    libgirepository-2.0-dev libcairo2-dev pkg-config python3-dev
curl -LsSf https://astral.sh/uv/install.sh | sh    # uv, if not installed yet
git clone https://github.com/arunoruto/dzk-33ux250.git specpol
cd specpol
uv sync
uv run specpol --fake
```

`gir1.2-aravis-0.8` provides the introspection data PyGObject loads at runtime; the `-dev`
packages are only needed while uv builds PyGObject.

## Command line

```text
specpol [--fake] [--port PORT] [--address ADDRESS] [streamlit options...]
```

`--fake`
: Aravis' simulated camera, no hardware needed (same as setting `SPECPOL_FAKE=1`).

`--port`
: HTTP port for the page **and** the preview images (default 8501). Both use the same port, see
  {doc}`architecture`.

`--address`
: Address to listen on (default: all interfaces).

Anything else is passed on to `streamlit run`, e.g. `--logger.level debug`. `python -m specpol`
works too. Streamlit's usage telemetry is always off.

The camera itself needs a little host setup (USB permissions, a larger USB buffer) and other PCs
need an open port: see {doc}`host-setup`.

## Tests

```sh
uv run pytest
```

The tests need no hardware: they use a simulated linear sensor and Aravis' fake camera. The
docs build with `uv run --only-group docs sphinx-build docs docs/_build/html`.
