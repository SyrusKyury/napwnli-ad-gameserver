#!/usr/bin/env python3
import sys
import json

REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr

import random
import string
import requests

PLAYERS = [
    "cavani", "hamsik", "1nsigne", "lavezzi", "di_l0renzo",
    "mertens", "koulibaly", "4llan", "sarri", "mazzarri",
    "pocho", "ca1lej0n", "maggio", "marad0na", "h1gua1n_tradit0re", "diego"
]


def random_username() -> str:
    return "_".join(random.choices(PLAYERS, k=3)) + "___" + "".join(random.choices(string.digits, k=10))


def random_password(k: int = 14) -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=k))


def result(status: str, flag_id: str = "", secret: str = ""):
    print(json.dumps({"status": status, "flag_id": flag_id, "secret": secret}), file=REAL_STDOUT)
    sys.exit(0)


def check(ip: str):
    headers = {"User-Agent": random_password(20)}
    r = requests.get(f"http://{ip}:5000", headers=headers, timeout=5)
    if r.status_code != 200:
        result("MUMBLE")
    r = requests.get(f"http://{ip}:5000/register", headers=headers, timeout=5)
    if r.status_code == 200 and "Enter your username" in r.text:
        result("UP")
    else:
        result("MUMBLE")


def put(ip: str, flag: str):
    session = requests.Session()
    headers = {"User-Agent": random_password(20)}

    username = random_username()
    password = random_password()

    r = session.get(f"http://{ip}:5000/register", headers=headers, timeout=5)
    if r.status_code != 200:
        result("MUMBLE")

    r = session.post(f"http://{ip}:5000/register", headers=headers,
                     data={"username": username, "password": password}, timeout=5)
    if r.status_code != 200:
        result("MUMBLE")

    r = session.get(f"http://{ip}:5000/login", headers=headers, timeout=5)
    if r.status_code != 200:
        result("MUMBLE")

    r = session.post(f"http://{ip}:5000/login", headers=headers,
                     data={"username": username, "password": password}, timeout=5)
    if r.status_code != 200:
        result("MUMBLE")

    r = session.get(f"http://{ip}:5000/login", headers=headers, timeout=5)

    r = session.post(f"http://{ip}:5000/save", headers=headers,
                     data={"content": f"{flag}\n!hidden!"}, timeout=5)
    if r.status_code != 200:
        result("MUMBLE")

    result("UP", flag_id=f"{username},{password}", secret="")


def get(ip: str, flag_id: str, flag: str, _secret: str):
    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    username, password = flag_id.split(",", 1)

    r = session.get(f"http://{ip}:5000/login", headers=headers, timeout=5)
    if r.status_code != 200:
        result("MUMBLE")

    r = session.post(f"http://{ip}:5000/login", headers=headers,
                     data={"username": username, "password": password}, timeout=5)
    if r.status_code != 200:
        result("MUMBLE")

    r = session.get(f"http://{ip}:5000/login", headers=headers, timeout=5)
    if flag in r.text:
        result("UP")
    else:
        result("MUMBLE")


def main():
    try:
        input_data = json.loads(sys.stdin.read())
        action = input_data.get("action")
        ip     = input_data.get("ip")

        if action == "check":
            check(ip)
        elif action == "put":
            put(ip, input_data.get("flag"))
        elif action == "get":
            get(ip, input_data.get("flag_id"), input_data.get("flag"), input_data.get("secret", ""))
        else:
            result("DOWN")

    except Exception as e:
        print(json.dumps({"status": "DOWN"}), file=REAL_STDOUT, flush=True)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
