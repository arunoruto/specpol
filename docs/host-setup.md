# Host setup

Two things on the PC the camera is plugged into: **USB access** for the camera, and an **open
port** if other PCs should open the dashboard.

## Camera access

The camera needs user access to its USB device and a usbfs buffer large enough for a 5 MP frame.
The kernel default of 16 MB isn't enough: frames then fail with `size-mismatch`.

### NixOS

```nix
boot.kernelParams = [ "usbcore.usbfs_memory_mb=1000" ];
services.udev.extraRules = ''
  SUBSYSTEM=="usb", ATTRS{idVendor}=="199e", MODE="0660", GROUP="video", TAG+="uaccess"
'';
```

On `mayuri` this is in `~/.config/flake/systems/x86_64-linux/mayuri/default.nix`. Then
`sudo nixos-rebuild switch`, **replug the camera** (udev rule) and **reboot** (kernel parameter).

### Ubuntu / Debian

```sh
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="199e", MODE="0660", GROUP="video", TAG+="uaccess"' |
    sudo tee /etc/udev/rules.d/99-specpol.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

For the buffer, add `usbcore.usbfs_memory_mb=1000` to `GRUB_CMDLINE_LINUX_DEFAULT` in
`/etc/default/grub`, then `sudo update-grub` and reboot.

### Without rebooting (any Linux)

```sh
echo 1000 | sudo tee /sys/module/usbcore/parameters/usbfs_memory_mb
```

### Check

```sh
cat /sys/module/usbcore/parameters/usbfs_memory_mb   # 1000
arv-tool-0.8                                         # The Imaging Source Europe GmbH-199E…-… (USB3)
```

### macOS

Nothing to configure: plug in the camera and start specpol.

## Network access

specpol serves the page **and** the live images on one port, **8501** by default (`--port`
changes it). Whatever reaches the page also reaches the images: Tailscale, an SSH tunnel
(`ssh -L 8501:localhost:8501 <host>`), a reverse proxy, or another PC on the network once the
port is open in the firewall.

:::{warning}
The dashboard has no login. Anyone who can reach the port can watch the camera, change its
settings and start measurements. Open it only to networks you trust, ideally just your subnet
(examples below).
:::

### NixOS

Permanently, in the host's configuration (then `sudo nixos-rebuild switch`):

```nix
# all interfaces
networking.firewall.allowedTCPPorts = [ 8501 ];

# or only on the university network interface (here eno1; see `ip -br addr`)
networking.firewall.interfaces.eno1.allowedTCPPorts = [ 8501 ];
```

Temporarily, until the next `nixos-rebuild switch` or reboot:

```sh
sudo nixos-firewall-tool open tcp 8501
sudo nixos-firewall-tool show              # check
sudo nixos-firewall-tool reset             # close again
```

Without that tool, with the default iptables backend:

```sh
sudo iptables  -I nixos-fw -p tcp --dport 8501 -j nixos-fw-accept
sudo ip6tables -I nixos-fw -p tcp --dport 8501 -j nixos-fw-accept
```

Interfaces in `networking.firewall.trustedInterfaces` (e.g. `tailscale0`) need nothing: every
port is open there.

### Ubuntu / Debian (ufw)

```sh
sudo ufw allow 8501/tcp
# or only from your subnet, e.g.
sudo ufw allow from 129.217.143.128/26 to any port 8501 proto tcp
sudo ufw status
```

ufw rules are permanent. Remove with `sudo ufw delete allow 8501/tcp`. If `ufw status` says
`inactive`, the firewall is off and nothing needs opening.

### Fedora / RHEL / openSUSE (firewalld)

```sh
sudo firewall-cmd --add-port=8501/tcp                 # now, until reboot
sudo firewall-cmd --add-port=8501/tcp --permanent     # and after reboots
# or only from your subnet
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="129.217.143.128/26" port port="8501" protocol="tcp" accept'
sudo firewall-cmd --reload
```

### macOS

The application firewall asks the first time specpol (Python) listens: allow incoming
connections. Check under *System Settings → Network → Firewall → Options*.

### Check from another PC

```sh
curl -s -o /dev/null -w "%{http_code}\n" http://<host>:8501/_stcore/health   # 200
```

A timeout means the firewall (or the network) blocks the port. If the page loads but the images
don't, see {doc}`troubleshooting`.
