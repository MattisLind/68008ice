"""Verify the waveform acceptance rules independently of the generator."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bus_timing import check_cycle


class BusTiming(unittest.TestCase):
    def waveform(self, waits=0):
        extra=round(waits*125*150000000/1e9)
        data=[]
        for i in range(4096):
            v=0x400 | (0x5a<<20) | (15<<28)
            if 2029<=i<2077+extra:v&=~(1<<28)
            if 2048<=i<2077+extra:v&=~(1<<29)
            if 2029<=i<2080+extra:v&=~(1<<30)
            if 2052+extra<=i<2080+extra:v&=~(1<<31)
            data.append(v)
        record=dict(hz=150000000,stride=4,flags=17,capacity=4096,trigger=2048,pre_percent=50)
        return record,data

    def test_zero_wait_cycle(self):
        r,data=self.waveform()
        result=check_cycle(r,struct.pack('<4096I',*data),write=True,base=0x400,seed=0x5a)
        self.assertEqual(result['wait_states'],0)
        self.assertEqual(result['nominal_bus_cycle_ns'],500)
        self.assertEqual(result['trigger_index'],2048)

    def test_wait_states_are_reported(self):
        r,data=self.waveform(2)
        result=check_cycle(r,struct.pack('<4096I',*data),write=True,base=0x400,seed=0x5a)
        self.assertEqual(result['wait_states'],2)
        self.assertEqual(result['nominal_bus_cycle_ns'],750)

    def test_wrong_data_or_trigger_rejected(self):
        r,data=self.waveform()
        data[2060]^=1<<20
        with self.assertRaises(ValueError):
            check_cycle(r,struct.pack('<4096I',*data),write=True,base=0x400,seed=0x5a)
        r,data=self.waveform();r['trigger']=2047
        with self.assertRaises(ValueError):
            check_cycle(r,struct.pack('<4096I',*data),write=True,base=0x400,seed=0x5a)


if __name__=='__main__':unittest.main()
