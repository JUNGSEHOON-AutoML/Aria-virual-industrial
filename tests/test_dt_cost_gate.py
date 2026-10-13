import math
import pytest
from tools.measure_dt_cap import gate_decision


def test_both_limits_required_and_reserve_includes_two_gib():
    required=math.ceil(1000*1.15)+2*1024**3
    assert gate_decision(28800,1000,required)['passed']
    assert not gate_decision(28800.01,1000,required)['passed']
    result=gate_decision(1,1000,required-1)
    assert not result['passed'] and result['shortage_bytes']==1
    assert result['time_gate_passed'] and not result['storage_gate_passed']


@pytest.mark.parametrize('bad', [-1,float('nan'),float('inf')])
def test_invalid_estimates_fail_closed(bad):
    with pytest.raises(ValueError):gate_decision(bad,1,1)
    with pytest.raises(ValueError):gate_decision(1,bad,1)
    with pytest.raises(ValueError):gate_decision(1,1,bad)
