"""Independent BOLT 3 Appendix D/E vectors plus algebraic consistency checks."""
import pytest
from lnchannel import crypto as c, shachain as s
from conftest import BOLT3_VECTORS

BASE=bytes(range(32)); PER=bytes(reversed(range(32)))

@pytest.mark.parametrize('operation,expected',[
    ('public','0235f2dbfaa89b57ec7b055afe29849ef7ddfeb1cefdb9ebdc43f5494984db29e5'),
    ('private','cbced912d3b21bf196a766651e436aff192362621ce317704ea2f75d87e7be0f'),
    ('revpublic','02916e326636d19c33f13e8c0c3a03dd157f332f3e99c317c141dd865eb01f8ff0'),
    ('revprivate','d09ffff62ddb2297ab000cc85bcb4283fdeb6aa052affbc9dddcf33b61078110')])
def test_key_vectors(operation,expected):
    result={'public':lambda:c.derive_public(c.pubkey(BASE),c.pubkey(PER)),
            'private':lambda:c.derive_private(BASE,c.pubkey(PER)),
            'revpublic':lambda:c.revocation_public(c.pubkey(BASE),c.pubkey(PER)),
            'revprivate':lambda:c.revocation_private(BASE,PER)}[operation]()
    assert result.hex()==expected

@pytest.mark.parametrize('seed,index,expected', BOLT3_VECTORS['shachain_generation'])
def test_generation_vectors(seed,index,expected):
    assert s.derive(bytes.fromhex(seed), 48, index).hex() == expected

def test_all_published_storage_sequences():
    sequences = BOLT3_VECTORS['shachain_storage']
    assert len(sequences) == 9
    assert sum(map(len, sequences.values())) == 56
    for name, entries in sequences.items():
        chain = s.ShaChain()
        for index, value, result in entries:
            secret = bytes.fromhex(value)
            if result == 'ERROR':
                with pytest.raises(ValueError):
                    chain.insert(index, secret)
            else:
                assert result == 'OK', (name, index)
                chain.insert(index, secret)
                assert chain.get(index) == secret, (name, index)

def test_compact_storage_and_unknown_future():
    chain=s.ShaChain()
    for n in range(1000): chain.insert(s.MAX_INDEX-n,s.secret(BASE,n))
    assert len(chain.buckets)<=49
    restored=s.ShaChain(chain.export())
    for n in range(1000): assert restored.get(s.MAX_INDEX-n)==s.secret(BASE,n)
    with pytest.raises(ValueError): restored.get(s.MAX_INDEX-1000)

def test_signature_does_not_double_hash():
    digest=c.sha256(b'hello'); sig=c.sign(BASE,digest)
    assert c.verify(c.pubkey(BASE),sig,digest)
    assert not c.verify(c.pubkey(BASE),sig,c.sha256(digest))
