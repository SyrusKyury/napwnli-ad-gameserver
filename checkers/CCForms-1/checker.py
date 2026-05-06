#!/usr/bin/env python3

import sys
import os

# Importa il checker originale e checklib dalla stessa directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import checker_CCForms_1 as original_checker
import checklib

# Exit codes compatibili con ForcAD
OK = 101
CORRUPT = 102
MUMBLE = 103
DOWN = 104
CHECKER_ERROR = 110

def close(code: int, public="", private="", flag_id=""):
    if flag_id:
        print(flag_id)
        sys.exit(code)
    if public:
        print(public)
    if private:
        print(private, file=sys.stderr)
    sys.exit(code)

def build_data(ip, flag=None, flag_id=None):
    team_id = ip.split(".")[2]
    os.environ["TEAM_ID"] = team_id  # Imposta TEAM_ID
    os.environ["ROUND"] = "1"  # Imposta il numero di round, potresti doverlo modificare in base alla logica
    os.environ["FLAG"] = flag if flag else "example_flag"  # Imposta il flag
    os.environ["ACTION"] = ""  # Imposta ACTION (sarà poi modificato a seconda del comando)
    return {
        "teamId": team_id,
        "flag": flag,
        "flagId": flag_id,
        "team_host": ip,
        "action": None
    }

def check(ip, flag_id=None, flag=None, vuln=None):
    checklib.data = build_data(ip)
    os.environ["action"] = "CHECK_SLA"
    try:
        original_checker.check_sla(ip)
    except Exception as e:
        close(DOWN, "Check SLA failed", str(e))
    close(OK)

def put(ip, flag_id, flag, vuln):
    checklib.data = build_data(ip, flag=flag, flag_id=flag_id)
    os.environ["action"] = "PUT_FLAG"
    try:
        var, flag_id = original_checker.put_flag(ip, flag) 
    except Exception as e:
        close(CHECKER_ERROR, "Put failed", str(e))
    close(OK, public = var, private = flag_id) #MODIFICARE OPPORTUNAMENTE IN BASE AL SERVIZIO


def get(ip, flag_id, flag, vuln):
    checklib.data = build_data(ip, flag=flag, flag_id=flag_id)
    os.environ["action"] = "GET_FLAG"
    try:
        original_checker.get_flag(ip,flag,flag_id)
    except Exception as e:
        close(CHECKER_ERROR, "Get failed", str(e))
    close(OK)

COMMANDS = {
    'check': check,
    'put': put,
    'get': get
}

def main():
    if len(sys.argv) < 3:
        close(CHECKER_ERROR, "Usage: wrapper.py <check|put|get> <ip> [flag_id] [flag] [vuln]")

    cmd = sys.argv[1]
    ip = sys.argv[2]
    flag_id = sys.argv[3] if len(sys.argv) > 3 else None
    flag = sys.argv[4] if len(sys.argv) > 4 else None
    vuln = sys.argv[5] if len(sys.argv) > 5 else None

    # Validazione comando
    if cmd not in COMMANDS:
        close(CHECKER_ERROR, "Invalid command")
    # Esegui il comando appropriato (check, put, get)
    COMMANDS[cmd](ip, flag_id, flag, vuln)

if __name__ == "__main__":
    main()