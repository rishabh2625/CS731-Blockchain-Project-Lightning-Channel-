"""Keep pytest temporary files under the repository, including on sandboxed Windows."""
import pathlib
import subprocess
import sys
import time

root=pathlib.Path(__file__).resolve().parents[1]
target=root/'.runtime'/('pytest-'+str(time.time_ns()))
target.parent.mkdir(exist_ok=True)
raise SystemExit(subprocess.call([sys.executable,'-m','pytest','-q','--basetemp',str(target),
    '--junitxml',str(root/'evidence'/'unit-tests.xml'),*sys.argv[1:]],cwd=root))
