"""Private OP_TRUE signet block producer, for test infrastructure only.

Bitcoin Core validates each submitted block. This is not a channel component.
The six-byte signet solution encodes the BIP 325 header and empty script/witness.
"""
import os
import struct
import subprocess
import time
from .bitcoin import compact, varbytes, number, u32, u64, push
from .crypto import hash256

def merkle(hashes):
    while len(hashes)>1:
        if len(hashes)%2: hashes=hashes+[hashes[-1]]
        hashes=[hash256(hashes[i]+hashes[i+1]) for i in range(0,len(hashes),2)]
    return hashes[0]

def mine(node, count):
    from .network import core_binary
    utility=core_binary().with_name('bitcoin-util.exe' if os.name=='nt' else 'bitcoin-util')
    script=bytes.fromhex(node.wallet.call('getaddressinfo',node.address)['scriptPubKey'])
    result=[]
    for _ in range(count):
        height=node.rpc.call('getblockcount')+1
        previous=node.rpc.call('getbestblockhash')
        head=node.rpc.call('getblockheader',previous)
        if height==1:
            txs=[]; reward=50*100_000_000; version=0x20000000; bits=head['bits']
        else:
            template=node.rpc.call('getblocktemplate',{'rules':['segwit','signet']})
            txs=template['transactions']; reward=template['coinbasevalue']; version=template['version']; bits=template['bits']
        # Keep timestamps recent, monotonically increasing, and below future-time limits.
        timestamp=max(int(time.time())-300,head['time']+1)
        wroot=merkle([bytes(32)]+[bytes.fromhex(t['hash'])[::-1] for t in txs])
        commitment=b'\x6a\x24\xaa\x21\xa9\xed'+hash256(wroot+bytes(32))
        commitment+=push(bytes.fromhex('ecc7daa2')+b'\x00\x00')
        coinbase_input=bytes(32)+u32(0xffffffff)+varbytes(number(height)+b'\x00')+u32(0xffffffff)
        outputs=compact(2)+u64(reward)+varbytes(script)+u64(0)+varbytes(commitment)
        stripped=u32(2)+b'\x01'+coinbase_input+outputs+u32(0)
        coinbase=u32(2)+b'\x00\x01\x01'+coinbase_input+outputs+b'\x01\x20'+bytes(32)+u32(0)
        root=merkle([hash256(stripped)]+[bytes.fromhex(t['txid'])[::-1] for t in txs])
        header=struct.pack('<I',version)+bytes.fromhex(previous)[::-1]+root+u32(timestamp)+u32(int(bits,16))+u32(0)
        solved=subprocess.run([str(utility),'grind',header.hex()],capture_output=True,text=True,check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0).stdout.strip()
        block=bytes.fromhex(solved)+compact(1+len(txs))+coinbase+b''.join(bytes.fromhex(t['data']) for t in txs)
        rejection=node.rpc.call('submitblock',block.hex())
        if rejection is not None: raise RuntimeError(f'Signet block rejected: {rejection}')
        result.append(hash256(bytes.fromhex(solved))[::-1].hex())
    return result
