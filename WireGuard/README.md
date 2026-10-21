# WireGuard: reaching another Unraid server

For occasional access from one Unraid server to another over the internet, e.g. to work on it over SSH.

## A tunnel you start by hand

Put a normal `wg-quick` config in `/boot/config/wireguard/<name>.conf`. It's on the flash drive, so it survives reboots, but Unraid only starts the tunnels listed in `/boot/config/wireguard/autostart`, so it stays down until you start it:

```
wg-quick up <name>      # start
wg show <name>          # "latest handshake: … seconds ago" means it's connected
wg-quick down <name>    # stop
```

The file name is the interface name. Unraid's VPN Manager page only lists `wgN` tunnels, so a tunnel with another name doesn't show there; it works the same from the command line.

## Don't overlap your own tunnels

Every Unraid server starts its WireGuard tunnels in 10.253.0.0/24. If the config from the other server has `AllowedIPs = 10.253.0.0/24`, bringing it up routes that whole range into the new tunnel and can break your own wg0. Set `AllowedIPs` to just the other server's LAN (e.g. `192.168.0.0/24`). That's all you need to reach its machines, and replies come back fine. Also check that its LAN range isn't the same as yours.

## SSH with a key, not a password

Unraid keeps root's SSH files on the flash drive in `/boot/config/ssh/root/` (`/root/.ssh` points there). Append your public key to `authorized_keys` in that folder and it survives reboots. Then test with password login disabled before changing or removing the password:

```
ssh -o PasswordAuthentication=no root@<other-server> hostname
```
