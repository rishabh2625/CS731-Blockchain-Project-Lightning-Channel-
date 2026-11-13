"""48-bit descending per-commitment secrets and compact receiving buckets."""
from .crypto import sha256
MAX_INDEX = (1 << 48) - 1

def derive(seed: bytes, bits: int, index: int) -> bytes:
    if len(seed) != 32 or not 0 <= index <= MAX_INDEX or not 0 <= bits <= 48:
        raise ValueError('Invalid shachain input')
    value = seed
    for bit in reversed(range(bits)):
        if index & (1 << bit):
            changed = bytearray(value)
            changed[bit // 8] ^= 1 << (bit % 8)
            value = sha256(changed)
    return value

def secret(seed: bytes, commitment_number: int) -> bytes:
    if not 0 <= commitment_number <= MAX_INDEX:
        raise ValueError('Commitment number outside 48-bit range')
    return derive(seed, 48, MAX_INDEX - commitment_number)

class ShaChain:
    def __init__(self, data=None):
        data = data or {'next': MAX_INDEX, 'buckets': {}}
        self.next = data['next']
        self.buckets = {int(k): (v[0], bytes.fromhex(v[1])) for k, v in data['buckets'].items()}

    def insert(self, index: int, value: bytes):
        if index != self.next or len(value) != 32:
            raise ValueError('Secrets must arrive in descending order')
        bucket = 48 if index == 0 else (index & -index).bit_length() - 1
        for b, (old_index, old) in self.buckets.items():
            if b < bucket and derive(value, bucket, old_index) != old:
                raise ValueError('Inconsistent shachain secret')
        self.buckets[bucket] = (index, value)
        self.next -= 1

    def get(self, index: int) -> bytes:
        if index <= self.next or index > MAX_INDEX:
            raise ValueError('Secret has not been revealed')
        for b, (base_index, value) in self.buckets.items():
            if index & ~((1 << b) - 1) == base_index:
                return derive(value, b, index)
        raise ValueError('Secret not derivable')

    def export(self):
        return {'next': self.next, 'buckets': {str(b): [i, v.hex()] for b, (i, v) in self.buckets.items()}}
