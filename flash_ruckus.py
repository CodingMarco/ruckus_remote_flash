import time
import logging
import argparse
import paramiko
from custom_logging import CustomFormatter

PROMPT_BUSYBOX_ROOT = "# "


def setup_logging():
    logger = logging.getLogger("flash_ruckus")
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(CustomFormatter())
    logger.addHandler(ch)

    return logger


logger = setup_logging()


def parse_args():
    parser = argparse.ArgumentParser(description="Flash Ruckus AP")
    parser.add_argument(
        "--ip", type=str, default="192.168.0.1", help="IP Address of the AP"
    )
    parser.add_argument(
        "--username", type=str, default="super", help="Username of the AP"
    )
    parser.add_argument(
        "--password", type=str, default="sp-admin", help="Password of the AP"
    )
    parser.add_argument(
        "--firmware",
        type=str,
        default="openwrt-sysupgrade.bin",
        help="Firmware file to flash",
    )
    return parser.parse_args()


def read_shell(shell) -> str:
    while not shell.recv_ready():
        time.sleep(0.1)

    return shell.recv(4096).decode()


def wait_for_prompt(shell, prompt) -> str:
    buffer = ""
    while True:
        output = read_shell(shell)
        logger.debug(output)
        buffer += output

        if prompt in output:
            break

    return buffer


def respond_to_prompt(shell, prompt, response) -> None:
    wait_for_prompt(shell, prompt)
    shell.send(response)


def send_command_wait(shell, command) -> str:
    if not command.endswith("\n"):
        command += "\n"

    shell.send(command)
    output = wait_for_prompt(shell, PROMPT_BUSYBOX_ROOT)
    output = (
        output.replace("\r\n", "\n")
        .replace(PROMPT_BUSYBOX_ROOT, "")
        .replace(command, "")
        .strip()
    )

    return output


def main():
    args = parse_args()
    ip = args.ip
    username = args.username
    password = args.password
    firmware = args.firmware

    # Open the initial root shell
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        ip,
        username=username,
        password=password,
        allow_agent=False,
        look_for_keys=False,
    )

    shell = client.invoke_shell()

    # Respond to the initial prompts
    respond_to_prompt(shell, "Please login: ", f"{username}\n")
    respond_to_prompt(shell, "password : ", f"{password}\n")
    respond_to_prompt(shell, "rkscli: ", "!v54!\n")
    respond_to_prompt(shell, "What's your chow: ", "\n")
    wait_for_prompt(shell, PROMPT_BUSYBOX_ROOT)

    output = send_command_wait(shell, "pwd")  # output -> '/'
    print(f"Output: '{output}'")

    # Close everything
    shell.close()
    client.close()


if __name__ == "__main__":
    main()
