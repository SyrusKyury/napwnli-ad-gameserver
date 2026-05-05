import sys
import json


def result(status: str, flag_id: str = "", secret: str = ""):
    print(json.dumps({"status": status, "flag_id": flag_id, "secret": secret}))
    sys.exit(0)


def check(ip: str):
    # Verify that the service is reachable and working correctly.
    # Does not involve flags. Call result("DOWN") or raise an exception
    # if the service does not respond as expected.
    #
    # Example:
    #   import requests
    #   r = requests.get(f"http://{ip}:8080/health", timeout=5)
    #   assert r.status_code == 200
    result("UP")


def put(ip: str, flag: str, tick: int):
    # Insert the flag into the service. Return:
    #   - flag_id: public identifier, exposed to opposing players via /api/flagids
    #   - secret:  private credential (e.g. password), stored by the gameserver
    #              and passed to get() for legitimate access.
    #              Never exposed via public APIs.
    #
    # Example:
    #   import requests, uuid
    #   username = f"user_{uuid.uuid4().hex[:8]}"
    #   password = uuid.uuid4().hex
    #   requests.post(f"http://{ip}:8080/register", json={"username": username, "password": password})
    #   requests.post(f"http://{ip}:8080/save", json={"flag": flag}, headers={"Authorization": password})
    #   flag_id = username  # public
    #   secret  = password  # private
    flag_id = f"user_{tick}"  # placeholder
    secret  = f"pass_{tick}"  # placeholder
    result("UP", flag_id=flag_id, secret=secret)


def get(ip: str, flag_id: str, flag: str, secret: str):
    # Retrieve the flag using flag_id (public) and secret (private).
    # Use secret to authenticate to the service as the legitimate owner of the flag.
    # Use flag to verify that the correct value is returned by the service.
    #
    # Example:
    #   import requests
    #   r = requests.get(f"http://{ip}:8080/notes/{flag_id}",
    #                    headers={"Authorization": secret})
    #   assert flag in r.text
    result("UP")


def main():
    try:
        input_data = json.loads(sys.stdin.read())
        action = input_data.get("action")
        ip     = input_data.get("ip")

        if action == "check":
            check(ip)
        elif action == "put":
            put(ip, input_data.get("flag"), input_data.get("tick"))
        elif action == "get":
            get(ip, input_data.get("flag_id"), input_data.get("flag"), input_data.get("secret", ""))
        else:
            result("DOWN")

    except Exception as e:
        print(json.dumps({"status": "DOWN"}), flush=True)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()