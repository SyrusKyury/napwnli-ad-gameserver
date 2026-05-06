#!/usr/bin/env python3
import sys
import json
import os
import hashlib

REAL_STDOUT = sys.stdout
sys.stdout = sys.stderr

# Aggiunge CCForms-1/ a sys.path per risolvere i suoi import interni
_checker_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'CCForms-1')
sys.path.insert(0, _checker_dir)

import checklib as _checklib
import checker_CCForms_1

# post_flag_id non esiste nella nostra infrastruttura: la rendiamo no-op
_checklib.post_flag_id = lambda *args, **kwargs: None
checker_CCForms_1.post_flag_id = lambda *args, **kwargs: None


def result(status: str, flag_id: str = "", secret: str = ""):
    print(json.dumps({"status": status, "flag_id": flag_id, "secret": secret}), file=REAL_STDOUT)
    sys.exit(0)


def check(ip: str):
    status = "DOWN"
    try:
        checker_CCForms_1.check_sla(ip)
        status = "UP"
    except SystemExit as e:
        status = "UP" if e.code == _checklib.Status.OK.value else "DOWN"
    except Exception:
        status = "DOWN"
    result(status)


def put(ip: str, flag: str):
    checker_CCForms_1.team_id = ip.split(".")[2]
    flag_hash = hashlib.md5(flag.encode()).hexdigest()
    status = "DOWN"
    fid = ""
    try:
        checker_CCForms_1.put_flag(ip, flag)
        status = "UP"
        fid = flag_hash
    except SystemExit as e:
        if e.code == _checklib.Status.OK.value:
            status = "UP"
            fid = flag_hash
        else:
            status = "DOWN"
    except Exception:
        status = "DOWN"
    result(status, flag_id=fid)


def get(ip: str, flag: str):
    status = "MUMBLE"
    try:
        checker_CCForms_1.get_flag(ip, flag)
        status = "UP"
    except SystemExit as e:
        status = "UP" if e.code == _checklib.Status.OK.value else "MUMBLE"
    except FileNotFoundError:
        status = "MUMBLE"
    except Exception:
        status = "MUMBLE"
    result(status)


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
            get(ip, input_data.get("flag"))
        else:
            result("DOWN")

    except Exception as e:
        print(json.dumps({"status": "DOWN"}), file=REAL_STDOUT, flush=True)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
