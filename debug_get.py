#!/usr/bin/env python3
import sys
import os
os.environ['PWNLIB_NOTERM'] = '1'
os.environ['PWNLIB_SILENT'] = '1'
import pwn
pwn.context.log_level = 'critical'

ip      = sys.argv[1]
flag_id = sys.argv[2]
flag    = sys.argv[3]

c = pwn.connect(ip, 1337, timeout=5)

c.sendlineafter(b'> ', b'2')
c.sendlineafter(b': ', flag_id.encode())
c.sendlineafter(b': ', b'0 2')
c.sendlineafter(b': ', b'2 0')
c.sendlineafter(b': ', b'1 2')

c.sendlineafter(b'> ', b'3')
c.sendlineafter(b': ', flag_id.encode())
c.sendlineafter(b': ', b'WRONGSECRET123')
res_wrong = c.recvline()
print(f"[wrong secret] raw response: {res_wrong!r}")

c.sendlineafter(b'> ', b'3')
c.sendlineafter(b': ', flag_id.encode())
c.sendlineafter(b': ', flag.encode())
res_correct = c.recvline()
print(f"[correct flag] raw response: {res_correct!r}")

c.sendlineafter(b'> ', b'4')
c.close()
