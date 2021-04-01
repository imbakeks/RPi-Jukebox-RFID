#!/usr/bin/env bash
# Extracted from install script with-autohotspot


jukebox_dir="/home/pi/RPi-Jukebox-RFID"
apt_get="sudo apt-get -qq --yes"

    # adapted from https://www.raspberryconnect.com/projects/65-raspberrypi-hotspot-accesspoints/158-raspberry-pi-auto-wifi-hotspot-switch-direct-connection

    # required packages
    ${apt_get} install dnsmasq hostapd
    sudo systemctl unmask hostapd
    sudo systemctl disable hostapd
    sudo systemctl disable dnsmasq

    # configure DNS
    if [ -f /etc/dnsmasq.conf ]; then
        sudo mv /etc/dnsmasq.conf /etc/dnsmasq.conf.orig
        sudo touch /etc/dnsmasq.conf
    else
        sudo touch /etc/dnsmasq.conf
    fi
    sudo bash -c 'cat << EOF > /etc/dnsmasq.conf
#AutoHotspot Config
#stop DNSmasq from using resolv.conf
no-resolv
#Interface to use
interface=wlan0
bind-interfaces
dhcp-range=10.0.0.50,10.0.0.150,12h
EOF'

    # configure hotspot
    if [ -f /etc/hostapd/hostapd.conf ]; then
        sudo mv /etc/hostapd/hostapd.conf /etc/hostapd/hostapd.conf.orig
        sudo touch /etc/hostapd/hostapd.conf
    else
        sudo touch /etc/hostapd/hostapd.conf
    fi
    sudo bash -c 'cat << EOF > /etc/hostapd/hostapd.conf
#2.4GHz setup wifi 80211 b,g,n
interface=wlan0
driver=nl80211
ssid=phoniebox
hw_mode=g
channel=8
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=PlayItLoud
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP TKIP
rsn_pairwise=CCMP

#80211n - Change DE to your WiFi country code
country_code=DE
ieee80211n=1
ieee80211d=1
EOF'

    # configure Hotspot daemon
    if [ -f /etc/default/hostapd ]; then
        sudo mv /etc/default/hostapd /etc/default/hostapd.orig
        sudo touch /etc/default/hostapd
    else
        sudo touch /etc/default/hostapd
    fi
    sudo bash -c 'cat << EOF > /etc/default/hostapd
DAEMON_CONF="/etc/hostapd/hostapd.conf"
EOF'

    if [ $(grep -v '^$' /etc/network/interfaces |wc -l) -gt 5 ]; then
        sudo cp /etc/network/interfaces /etc/network/interfaces-backup
    fi

    # disable powermanagement of wlan0 device
    sudo iw wlan0 set power_save off

    if [[ ! $(grep "nohook wpa_supplicant" /etc/dhcpcd.conf) ]]; then
        sudo echo -e "nohook wpa_supplicant" >> /etc/dhcpcd.conf
    fi

    # create service to trigger hotspot
    sudo bash -c 'cat << EOF > /etc/systemd/system/autohotspot.service
[Unit]
Description=Automatically generates an internet Hotspot when a valid ssid is not in range
After=multi-user.target
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/autohotspot
[Install]
WantedBy=multi-user.target
EOF'

    sudo systemctl enable autohotspot.service

    sudo cp "${jukebox_dir}"/scripts/helperscripts/autohotspot /usr/bin/autohotspot
    sudo chmod +x /usr/bin/autohotspot

    # create crontab entry
    if [[ ! $(grep "autohotspot" /var/spool/cron/crontabs/pi) ]]; then
        sudo bash -c 'cat << EOF >> /var/spool/cron/crontabs/pi
*/5 * * * * sudo /usr/bin/autohotspot >/dev/null 2>&1
EOF'
    fi
    sudo chown pi:crontab /var/spool/cron/crontabs/pi
    sudo chmod 600 /var/spool/cron/crontabs/pi
    sudo /usr/bin/crontab /var/spool/cron/crontabs/pi