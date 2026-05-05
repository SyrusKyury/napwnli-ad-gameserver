import sys
import json

def main():
	try:
		input_data = json.loads(sys.stdin.read())
		action = input_data.get("action")
		ip = input_data.get("ip")

		if action == "check":
			# Verifies that the service is reachable and working.
			# Does not involve flags. Raise an exception or return DOWN if the
			# service does not respond correctly.
			#
			# Example:
			#   import requests
			#   r = requests.get(f"http://{ip}:8080/health", timeout=5)
			#   assert r.status_code == 200
			print(json.dumps({"status": "UP"}))

		elif action == "put":
			# Insert the flag into the service. Return:
			#   - flag_id: public identifier, exposed to opposing players
			#   - secret:  private credential (e.g. password), stored by the
			#              gameserver and passed to get() for legitimate access.
			#              It is never exposed via public APIs.
			flag = input_data.get("flag")
			tick = input_data.get("tick")

			# Example:
			#   import requests, uuid
			#   username = f"user_{uuid.uuid4().hex[:8]}"
			#   password = uuid.uuid4().hex
			#   requests.post(f"http://{ip}:8080/register", json={"username": username, "password": password})
			#   requests.post(f"http://{ip}:8080/save", json={"flag": flag}, headers={"Authorization": password})
			#   flag_id = username   # public
			#   secret  = password   # private
			flag_id = f"user_{tick}"  # placeholder
			secret  = f"pass_{tick}"  # placeholder

			print(json.dumps({"status": "UP", "flag_id": flag_id, "secret": secret}))

		elif action == "get":
			# Retrieve the flag using flag_id (public) and secret (private).
			# The secret is the one returned by put, use it to authenticate
			# to the service as the legitimate owner of the flag.
			flag_id = input_data.get("flag_id")
			secret  = input_data.get("secret")

			# Example:
			#   import requests
			#   r = requests.get(f"http://{ip}:8080/notes/{flag_id}",
			#                    headers={"Authorization": secret})
			#   assert "NPW_" in r.text
			print(json.dumps({"status": "UP"}))

		else:
			print(json.dumps({"status": "DOWN"}))
			sys.exit(1)

	except Exception as e:
		print(json.dumps({"status": "DOWN"}))
		print(f"Error: {e}", file=sys.stderr)
		sys.exit(1)

if __name__ == "__main__":
	main()