"""Fetch pinned official Bitcoin Core binary and compare its published SHA256."""
import hashlib
import json
import pathlib
import urllib.request
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSION = '28.1'
BASE = f'https://bitcoincore.org/bin/bitcoin-core-{VERSION}/'
NAME = f'bitcoin-{VERSION}-win64.zip'

def main():
    target = ROOT / '.tools'
    target.mkdir(exist_ok=True)
    sums = urllib.request.urlopen(BASE + 'SHA256SUMS', timeout=90).read().decode()
    expected = next(line.split()[0] for line in sums.splitlines() if line.split()[-1] == NAME)
    archive = target / NAME
    if not archive.exists():
        urllib.request.urlretrieve(BASE + NAME, archive)
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError('Core archive hash mismatch')
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            if not (target / member.filename).resolve().is_relative_to(target.resolve()):
                raise RuntimeError('Unsafe archive path')
        z.extractall(target)
    (ROOT / 'references' / 'core-download.json').write_text(json.dumps({
        'version': VERSION, 'url': BASE + NAME, 'sha256': actual,
        'verification': 'SHA256 compared with official HTTPS manifest; release signatures not independently verified'
    }, indent=2))
    print(f'Bitcoin Core {VERSION} extracted; SHA256 {actual}')

if __name__ == '__main__':
    main()
