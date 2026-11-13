"""Opt-in real-node tests; always separate expensive integration from unit checks."""
import os
import pytest
from lnchannel.lab import run_scenarios

@pytest.mark.integration
@pytest.mark.skipif(os.environ.get('RUN_CORE_TESTS')!='1',reason='Set RUN_CORE_TESTS=1 to run two real Core nodes')
def test_all_core_scenarios(tmp_path):
    result=run_scenarios(tmp_path/'evidence')
    assert len(result)==12 and all(r['result']=='passed' for r in result)
