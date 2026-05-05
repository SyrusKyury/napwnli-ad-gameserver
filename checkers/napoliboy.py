import sys
import json

REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr

import random
import string
import os

os.environ['PWNLIB_NOTERM'] = '1'
os.environ['PWNLIB_SILENT'] = '1'

import pwn
pwn.context.log_level = 'critical'


def random_string(k: int, charset: str = string.ascii_letters + string.digits) -> str:
    return ''.join(random.choices(charset, k=k))


def result(status: str, flag_id: str = "", secret: str = ""):
    print(json.dumps({"status": status, "flag_id": flag_id, "secret": secret}), file=REAL_STDOUT)
    sys.exit(0)


def check(ip: str):
    connection = pwn.connect(ip, 1337, timeout=3)
    name = random_string(10)

    connection.sendlineafter(b'> ', b'1')
    connection.sendlineafter(b': ', name.encode())
    connection.sendlineafter(b': ', random_string(10).encode())

    connection.sendlineafter(b': ', b'2 2')
    connection.sendlineafter(b': ', b'1 0')
    connection.sendlineafter(b': ', b'1 1')

    connection.sendlineafter(b'> ', b'2')
    connection.sendlineafter(b': ', name.encode())
    connection.sendlineafter(b': ', b'0 2')
    connection.sendlineafter(b': ', b'2 0')
    connection.sendlineafter(b': ', b'1 2')

    connection.sendlineafter(b'> ', b'4')
    connection.close()
    result("UP")


def put(ip: str, flag: str):
    flag_id = random_string(10)

    connection = pwn.connect(ip, 1337, timeout=3)

    connection.sendlineafter(b'> ', b'1')
    connection.sendlineafter(b': ', flag_id.encode())
    connection.sendlineafter(b': ', flag.encode())

    connection.sendlineafter(b': ', b'0 2')
    connection.sendlineafter(b': ', b'2 0')
    connection.sendlineafter(b': ', b'1 2')

    connection.sendlineafter(b'> ', b'4')
    connection.close()
    result("UP", flag_id=flag_id, secret="")


def get(ip: str, flag_id: str, flag: str, secret: str):
    connection = pwn.connect(ip, 1337, timeout=3)

    connection.sendlineafter(b'> ', b'2')
    connection.sendlineafter(b': ', flag_id.encode())
    connection.sendlineafter(b': ', b'0 2')
    connection.sendlineafter(b': ', b'2 0')
    connection.sendlineafter(b': ', b'1 2')

    connection.sendlineafter(b'> ', b'3')
    connection.sendlineafter(b': ', flag_id.encode())
    connection.sendlineafter(b': ', random_string(10).encode())
    res_wrong = connection.recvline()
    if b"Secret is valid" in res_wrong:
        connection.close()
        result("MUMBLE")
        return

    connection.sendlineafter(b'> ', b'3')
    connection.sendlineafter(b': ', flag_id.encode())
    connection.sendlineafter(b': ', flag.encode())
    res_correct = connection.recvline()

    connection.sendlineafter(b'> ', b'4')
    connection.close()

    if b"Secret is valid" in res_correct:
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