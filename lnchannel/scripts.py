"""BOLT 3 non-anchor script templates, kept separate for review."""
from .bitcoin import push, number
from .crypto import hash160, ripemd160

def funding(a, b):
    first, second = sorted([a, b])
    return b'\x52' + push(first) + push(second) + b'\x52\xae'

def to_local(revocation, delayed, delay):
    return b'\x63' + push(revocation) + b'\x67' + number(delay) + b'\xb2\x75' + push(delayed) + b'\x68\xac'

def htlc(revocation, local, remote, payment_hash, expiry, offered):
    # DUP HASH160 <revocation hash> EQUAL IF CHECKSIG ELSE ...
    prefix = b'\x76\xa9' + push(hash160(revocation)) + b'\x87\x63\xac\x67'
    prefix += push(remote) + b'\x7c\x82' + number(32) + b'\x87'
    if offered:
        body = b'\x64\x75\x52\x7c' + push(local) + b'\x52\xae\x67\xa9'
        body += push(ripemd160(payment_hash)) + b'\x88\xac\x68'
    else:
        body = b'\x63\xa9' + push(ripemd160(payment_hash)) + b'\x88\x52\x7c'
        body += push(local) + b'\x52\xae\x67\x75' + number(expiry) + b'\xb1\x75\xac\x68'
    return prefix + body + b'\x68'
