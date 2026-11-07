{ pkgs, ... }:

{
  # Aravis = open-source USB3 Vision driver; PyGObject is built from source by uv,
  # so it needs pkg-config, cairo and gobject-introspection at build time.
  packages = with pkgs; [ aravis aravis.lib gobject-introspection pkg-config cairo zlib ]; # zlib: needed by prebuilt wheels

  env.GI_TYPELIB_PATH = "${pkgs.aravis.lib}/lib/girepository-1.0:${pkgs.gobject-introspection}/lib/girepository-1.0";

  languages.python = {
    enable = true;
    uv.enable = true;
    uv.sync.enable = true;
  };

  scripts.app.exec = "uv run streamlit run app.py";
}
