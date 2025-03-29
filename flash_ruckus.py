import argparse
from invoke import Responder
from fabric import Connection


def parse_args():
    parser = argparse.ArgumentParser(description="Flash Ruckus AP")
    parser.add_argument("ip", type=str, help="IP Address of the AP")
    parser.add_argument(
        "username", type=str, default="super", help="Username of the AP"
    )
    parser.add_argument(
        "password", type=str, default="sp-admin", help="Password of the AP"
    )
    parser.add_argument(
        "firmware",
        type=str,
        default="openwrt-sysupgrade.bin",
        help="Firmware file to flash",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    ip = args.ip
    username = args.username
    password = args.password
    firmware = args.firmware

    conn = Connection(host=ip, user=username)

    enter_username = Responder(pattern="Please login: ", response=f"{username}\n")
    enter_password = Responder(pattern="password : ", response=f"{password}\n")
    confirm_root_shell = Responder(pattern="What's your chow: ", response="\n")

    # Open the initial root shell
    conn.run("!v54!", watchers=[enter_username, enter_password, confirm_root_shell])


if __name__ == "__main__":
    main()
