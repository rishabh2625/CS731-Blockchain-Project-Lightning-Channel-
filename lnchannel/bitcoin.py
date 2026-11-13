"""Small explicit transaction serializer and BIP 143 SIGHASH_ALL implementation."""
from dataclasses import dataclass, field
import struct
from .crypto import hash256, hash160, sha256

def u32(n): return struct.pack('<I', n)
def u64(n): return struct.pack('<Q', n)

def compact(n):
    if n < 0: raise ValueError('Negative CompactSize')
    if n < 253: return bytes([n])
    if n <= 65535: return b'\xfd' + struct.pack('<H', n)
    if n <= 0xffffffff: return b'\xfe' + u32(n)
    return b'\xff' + u64(n)

def varbytes(value): return compact(len(value)) + value

@dataclass
class TxIn:
    txid: str
    vout: int
    sequence: int = 0xffffffff
    witness: list[bytes] = field(default_factory=list)
    def outpoint(self): return bytes.fromhex(self.txid)[::-1] + u32(self.vout)
    def serialize(self): return self.outpoint() + b'\x00' + u32(self.sequence)

@dataclass
class TxOut:
    value: int
    script: bytes
    def serialize(self):
        if not 0 <= self.value <= 21_000_000 * 100_000_000: raise ValueError('Invalid output value')
        return u64(self.value) + varbytes(self.script)

@dataclass
class Transaction:
    inputs: list[TxIn]
    outputs: list[TxOut]
    locktime: int = 0
    version: int = 2
    def serialize(self, witness=True):
        use_witness = witness and any(i.witness for i in self.inputs)
        result = u32(self.version) + (b'\x00\x01' if use_witness else b'')
        result += compact(len(self.inputs)) + b''.join(i.serialize() for i in self.inputs)
        result += compact(len(self.outputs)) + b''.join(o.serialize() for o in self.outputs)
        if use_witness:
            result += b''.join(compact(len(i.witness)) + b''.join(varbytes(w) for w in i.witness) for i in self.inputs)
        return result + u32(self.locktime)
    @property
    def txid(self): return hash256(self.serialize(False))[::-1].hex()
    @property
    def weight(self): return 3 * len(self.serialize(False)) + len(self.serialize())
    @property
    def vsize(self): return (self.weight + 3) // 4
    def hex(self): return self.serialize().hex()
    def sighash(self, index, script_code, amount):
        """SegWit v0 SIGHASH_ALL only; unsupported flags cannot be selected."""
        if not 0 <= index < len(self.inputs): raise ValueError('Input index')
        data = (u32(self.version) + hash256(b''.join(i.outpoint() for i in self.inputs))
                + hash256(b''.join(u32(i.sequence) for i in self.inputs))
                + self.inputs[index].outpoint() + varbytes(script_code) + u64(amount)
                + u32(self.inputs[index].sequence)
                + hash256(b''.join(o.serialize() for o in self.outputs))
                + u32(self.locktime) + u32(1))
        return hash256(data)

def push(data: bytes):
    if len(data) < 76: return bytes([len(data)]) + data
    if len(data) <= 255: return b'\x4c' + bytes([len(data)]) + data
    return b'\x4d' + struct.pack('<H', len(data)) + data

def number(n):
    if n == 0: return b'\x00'
    if 1 <= n <= 16: return bytes([0x50 + n])
    if n < 0: raise ValueError('Negative script number unsupported')
    raw = n.to_bytes((n.bit_length() + 7) // 8, 'little')
    if raw[-1] & 0x80: raw += b'\x00'
    return push(raw)

def p2wsh(script): return b'\x00\x20' + sha256(script)
def p2wpkh(public): return b'\x00\x14' + hash160(public)
def p2pkh_code(public): return b'\x76\xa9\x14' + hash160(public) + b'\x88\xac'
