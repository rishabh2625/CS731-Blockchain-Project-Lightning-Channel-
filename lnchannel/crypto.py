"""BOLT 3 key derivation. Curve arithmetic alone is delegated to libsecp256k1."""
import hashlib
import secrets
from coincurve import PrivateKey, PublicKey

ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()

def hash256(data: bytes) -> bytes:
    return sha256(sha256(data))

def ripemd160(data: bytes) -> bytes:
    return hashlib.new('ripemd160', data).digest()

def hash160(data: bytes) -> bytes:
    return ripemd160(sha256(data))

def scalar(n: int) -> bytes:
    n %= ORDER
    if n == 0:
        raise ValueError('Zero private scalar')
    return n.to_bytes(32, 'big')

def new_secret() -> bytes:
    return scalar(secrets.randbelow(ORDER - 1) + 1)

def pubkey(secret: bytes) -> bytes:
    return PrivateKey(secret).public_key.format()

def derive_public(base: bytes, point: bytes) -> bytes:
    tweak = sha256(point + base)
    return PublicKey(base).add(tweak).format()

def derive_private(base_secret: bytes, point: bytes) -> bytes:
    return scalar(int.from_bytes(base_secret, 'big') + int.from_bytes(sha256(point + pubkey(base_secret)), 'big'))

def revocation_public(base: bytes, point: bytes) -> bytes:
    a = PublicKey(base).multiply(sha256(base + point))
    b = PublicKey(point).multiply(sha256(point + base))
    return PublicKey.combine_keys([a, b]).format()

def revocation_private(base_secret: bytes, commitment_secret: bytes) -> bytes:
    base, point = pubkey(base_secret), pubkey(commitment_secret)
    return scalar(int.from_bytes(base_secret, 'big') * int.from_bytes(sha256(base + point), 'big')
                  + int.from_bytes(commitment_secret, 'big') * int.from_bytes(sha256(point + base), 'big'))

def sign(secret: bytes, digest: bytes) -> bytes:
    if len(digest) != 32:
        raise ValueError('Expected 32-byte transaction digest')
    return PrivateKey(secret).sign(digest, hasher=None)

def verify(public: bytes, signature: bytes, digest: bytes) -> bool:
    try:
        return PublicKey(public).verify(signature, digest, hasher=None)
    except (ValueError, TypeError):
        return False
