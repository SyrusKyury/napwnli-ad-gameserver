import sys
import json
import pwn
import random
import string

pwn.context.log_level = "CRITICAL"

def random_string(k: int, charset: str = string.ascii_letters + string.digits) -> str:
    return ''.join(random.choices(charset, k=k))

def main():
    try:
        input_data = json.loads(sys.stdin.read())
        action = input_data.get("action")
        ip = input_data.get("ip")
        
        connection = pwn.connect(ip, 1337, timeout=3)
    
        if action == "check":
            # Creates a new game
            name = random_string(10)
            connection.sendlineafter(b'> ', b'1')
            connection.sendlineafter(b': ', name.encode())
            connection.sendlineafter(b': ', random_string(10).encode())
            
            # Plays
            connection.sendlineafter(b': ', b'2 2')
            connection.sendlineafter(b': ', b'1 0')
            connection.sendlineafter(b': ', b'1 1')

            # Retries
            connection.sendlineafter(b'> ', b'2')
            connection.sendlineafter(b': ', name.encode())

            connection.sendlineafter(b': ', b'0 2')
            connection.sendlineafter(b': ', b'2 0')
            connection.sendlineafter(b': ', b'1 2')

            # Exit
            connection.sendlineafter(b'> ', b'4')
            connection.close()
            print(json.dumps({"status": "UP"}))

        elif action == "put":
            flag: str = input_data.get("flag") # Flag
            flag_id: str = random_string(10)   # Game
            secret: str = ""                   # No secret
            
            # Adds the flag
            connection.sendlineafter(b'> ', b'1')
            connection.sendlineafter(b': ', flag_id.encode())
            connection.sendlineafter(b': ', flag.encode())

            # Plays
            connection.sendlineafter(b': ', b'0 2')
            connection.sendlineafter(b': ', b'2 0')
            connection.sendlineafter(b': ', b'1 2')

            # Quits
            connection.sendlineafter(b'> ', b'4')
            connection.close()
            print(json.dumps({"status": "UP", "flag_id": flag_id, "secret": secret}))

        elif action == "get":
            flag_id = input_data.get("flag_id")
            flag = input_data.get("flag")

            # Plays
            connection.sendlineafter(b'> ', b'2')
            connection.sendlineafter(b': ', flag_id.encode())

            connection.sendlineafter(b': ', b'0 2')
            connection.sendlineafter(b': ', b'2 0')
            connection.sendlineafter(b': ', b'1 2')

            # Checks the wrong flag
            connection.sendlineafter(b'> ', b'3')
            connection.sendlineafter(b': ', flag_id.encode())
            res = connection.sendlineafter(b': ', random_string(10).encode())
            if(b"Secret is valid" in res):
                print(json.dumps({"status": "MUMBLE"}))
            else:
                connection.sendlineafter(b'> ', b'3')
                connection.sendlineafter(b': ', flag_id.encode())
                res = connection.sendlineafter(b': ', flag.encode())
                if(b"Secret is valid" in res):
                    print(json.dumps({"status": "UP"}))
                else:
                    print(json.dumps({"status": "MUMBLE"}))

            # Quits
            connection.sendlineafter(b'> ', b'4')
            connection.close()

        else:
            print(json.dumps({"status": "DOWN"}))
            sys.exit(1)

    except Exception as e:
        print(json.dumps({"status": "DOWN"}))
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()