#!/usr/bin/env python3

import sys
import requests
import random
import checklib

"""
# Checker pfr

A pfr checker returns public flag data (e.g. username of flag user) from PUT action as a public message,
private flag data (flag_id) as a private message, and public message is shown on /api/client/attack_data
for participants. If checker does not have this tag, no attack data is shown for the task.

## GETTING STARTED:

1. Implement check(ip_address : str)
2. Implement put(ip_address : str, flag_id : str, flag : str)
3. Implement get(ip_address : str, flag_id : str)

## How to return the result

All the functions listed above should terminate with close() function. It will print the result so 
that the checker can read it. The function close() takes 4 arguments:
    - code: int, the return code. Use one of the following:
        - OK = 101
        - CORRUPT = 102
        - MUMBLE = 103
        - DOWN = 104
        - CHECKER_ERROR = 110
    - public: str, the message that will be shown to the participants
    - private: str, the message that will be shown to the admins
    - flag_id: str, the flag_id that was used in the put() or get() function. It is used to cache the flag_id
        so that the checker can use it in the get() function. If you don't use it, pass an empty string.

## Resources

- https://github.com/pomo-mondreganto/ForcAD/wiki/Writing-a-checker
- https://github.com/HackerDom/ructf-2017/wiki/%D0%98%D0%BD%D1%82%D0%B5%D1%80%D1%84%D0%B5%D0%B9%D1%81-%C2%AB%D0%BF%D1%80%D0%BE%D0%B2%D0%B5%D1%80%D1%8F%D1%8E%D1%89%D0%B0%D1%8F-%D1%81%D0%B8%D1%81%D1%82%D0%B5%D0%BC%D0%B0-%D1%87%D0%B5%D0%BA%D0%B5%D1%80%D1%8B%C2%BB

"""
def random_string() -> str:
    import string
    players = ["cavani", "hamsik", "1nsigne", "lavezzi", "di_l0renzo", "mertens", "koulibaly", "4llan", "sarri", "mazzarri", "pocho", "ca1lej0n", "maggio", "marad0na", "h1gua1n_tradit0re", "diego"]
    result = "_".join(random.choices(players, k=3)) + "___" + "".join(random.choices(string.digits, k=10))
    return result


def close(code : int, public="", private="", flag_id=""):
    """
    :param code: answer code
    :param public: anyone will see it
    :param private: only for admins
    :param flag_id: cache for put->get
    :return:
    """
    if flag_id:
        print(flag_id)
        exit(code)
    if public:
        print(public)
    if private:
        print(private, file=sys.stderr)
    exit(code)



def check(ip_address : str) -> int:
    """
    Checks that team's service is running normally. Visits some pages, checks registration, login, etc...
    """
    try:
        user_agent = checklib.rnd_useragent()
        response : requests.Response = requests.get(f"http://{ip_address}:5000", headers={"User-Agent": user_agent})
        if response.status_code != 200:
            close(
                MUMBLE,
                "Service is not working correctly",
                "Service is not working correctly"
            )
        else:
            response : requests.Response = requests.get(f"http://{ip_address}:5000/register", headers={"User-Agent": user_agent})
            if response.status_code == 200 and "Enter your username" in response.text:
                close(
                    OK,
                    "Service is up",
                    "Service is up"
                )
            else:
                close(
                    MUMBLE,
                    "Service is not working correctly",
                    "Service is not working correctly"
                )
    except Exception as _:
        close(
            DOWN,
            "Service is down",
            "Service is down"
        )
    


def put(ip_address : str, flag_id : str, flag : str, vuln_num : str) -> int:
    """
    Puts a flag to the team's service.
    - ip_address: str, the ip address of the team's service
    - flag_id: str, the flag_id that will be used to get the flag back (It looks like it will be always passed
        as an argument, but it is not necessary to use it every time, but I'm not sure)
    - flag: str, the flag that will be put to the team's service
    """

    session : requests.Session = requests.Session()
    user_agent : str = checklib.rnd_useragent()

    try:
        response : requests.Response = session.get(f"http://{ip_address}:5000/register", headers={"User-Agent": user_agent})
        if response.status_code != 200:
            close(
                MUMBLE,
                "Service is not working correctly",
                "Service is not working correctly"
            )
        else:
            username = random_string()
            password = random_string()
            form_data : dict = {
                "username": username,
                "password": password,
            }

            response : requests.Response = session.post(f"http://{ip_address}:5000/register", headers={"User-Agent": user_agent}, data=form_data)
            if response.status_code != 200:
                close(
                    MUMBLE,
                    "Service is not working correctly",
                    "Service is not working correctly"
                )
            
            response : requests.Response = session.get(f"http://{ip_address}:5000/login", headers={"User-Agent": user_agent})
            form_data : dict = {
                "username": username,
                "password": password,
            }

            response : requests.Response = session.post(f"http://{ip_address}:5000/login", headers={"User-Agent": user_agent}, data=form_data)
            if response.status_code != 200:
                close(
                    MUMBLE,
                    "Service is not working correctly",
                    "Service is not working correctly"
                )


            response : requests.Response = session.get(f"http://{ip_address}:5000/login", headers={"User-Agent": user_agent})
            flag_text : str = f"{flag}\n!hidden!"
            form_data : dict = {"content": flag_text}

            response : requests.Response = session.post(f"http://{ip_address}:5000/save", headers={"User-Agent": user_agent}, data=form_data)
            if response.status_code != 200:
                close(
                    MUMBLE,
                    "Service is not working correctly",
                    "Service is not working correctly"
                )
            else:
                close(
                    OK,
                    private = ",".join([username, password]),
                    public = username
                )

    except Exception as E:
        close(
            DOWN,
            "Service is down",
            E
        )



def get(ip_address : str, flag_id : str, flag : str, vuln_num : str) -> int:
    """
    Fetches one random old flag from last flag_lifetime rounds.
    """
    session : requests.Session = requests.Session()
    user_agent : str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
    ##url = "https://webhook.site/57b99aae-7e11-4c1a-8ba8-446378565745"

    #requests.post(url, json={"ip": ip_address, "flag_id":flag_id, "flag":flag})
    try:
        response : requests.Response = session.get(f"http://{ip_address}:5000/login", headers={"User-Agent": user_agent})
        if response.status_code != 200:
            close(
                MUMBLE,
                "Service is not working correctly",
                "Service is not working correctly"
            )
        
        username = flag_id.split(",")[0]
        password = flag_id.split(",")[1]
        form_data : dict = {
            "username": username,
            "password": password,
        }

        response : requests.Response = session.post(f"http://{ip_address}:5000/login", headers={"User-Agent": user_agent}, data=form_data)
        if response.status_code != 200:
            close(
                MUMBLE,
                "Service is not working correctly",
                "Service is not working correctly"
            )

        response : requests.Response = session.get(f"http://{ip_address}:5000/login", headers={"User-Agent": user_agent})
        if flag in response.text:
            close(
                OK,
                "Flag is found",
                "Flag is found"
            )
        else:
            close(
                MUMBLE,
                "Flag is not found",
                "Flag is not found"
            )
    except Exception as E:
        print(E)
        close(
            DOWN,
            "Service is down",
            "Service is down"
        )
    


OK = 101                # OK code, everything works
CORRUPT = 102           # CORRUPT, service's working correctly, but didn't return flags from previous rounds (returned by GET only)
MUMBLE = 103            # MUMBLE, service's not working correctly
DOWN = 104              # DOWN, could not connect normally
CHECKER_ERROR = 110     # CHECKER_ERROR, unexpected error in checker


COMMANDS = {
    'check': check,
    'put': put,
    'get': get
}


def not_found(*_):
    close(
        CHECKER_ERROR,
        "Checker error",
        "Unsupported command {}".format(sys.argv[1])
    )


def main():
    try:
        COMMANDS.get(sys.argv[1], not_found)(*sys.argv[2:])
    except Exception as e:
        close(
            CHECKER_ERROR,
            "Checker error",
            "Unexpected error: {}".format(str(e))
        )


if __name__ == "__main__":
    main()