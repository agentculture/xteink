# Publishing xteink.local with avahi

Containers do not do mDNS, so name advertisement is done by the host's
`avahi-daemon`. Nothing here is installed automatically; run the steps below
yourself with `sudo`.

## Option A: service advertisement (`xteink.service`)

Advertises an `_http._tcp` service on port 8780 (with TXT records for the device
port 8781 and MCP port 8782). Browsers and mDNS-aware clients see "xteink on
`<hostname>`", and the host is reachable as `<hostname>.local`. It does not create
the name `xteink.local`.

```bash
sudo cp docker/avahi/xteink.service /etc/avahi/services/xteink.service
# avahi-daemon watches this directory; reload if it does not pick it up
sudo systemctl reload avahi-daemon
avahi-browse -rt _http._tcp   # verify
```

## Option B: the `xteink.local` alias (`xteink-alias.service`)

Firmware that wants the fixed name `xteink.local` needs an address record for that
exact name. A `.service` file cannot do that; `avahi-publish -a -R` can. The
supplied systemd unit keeps it running.

```bash
# edit the IP in the unit first (the address devices should reach)
sudo cp docker/avahi/xteink-alias.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now xteink-alias.service
avahi-resolve -n xteink.local   # verify
```

Trade-off: the alias unit hard-codes an IP, so it must be edited if the host's
address changes (use a DHCP reservation). Option A follows the host name and
needs no IP, but does not give the fixed `xteink.local` name. Use both if you want
discovery plus the fixed name.

Only one host on the LAN may claim `xteink.local`.
