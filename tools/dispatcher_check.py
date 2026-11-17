#!/usr/bin/env python3
"""Hardware acceptance checks for the USB dispatcher on two wired Core2350Bs."""
import argparse
import json
from pathlib import Path
import struct
import time
from ice import Device, encode


def rejected(device, op, payload, code):
    try:
        device.request(op,payload)
    except RuntimeError as exc:
        if f"status {code}" in str(exc):return
        raise
    raise AssertionError("Invalid command was accepted")


def raw_reply(device, frame, seq, op):
    device.port.write(frame)
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        for cmd,got_seq,status,payload in device.decoder.feed(device.port.read(.1)):
            if got_seq==seq and cmd==op|0x80:
                assert status==0,(cmd,status)
                return payload
    raise TimeoutError("No replay response")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--generator',required=True)
    p.add_argument('--receiver',required=True)
    p.add_argument('--output',type=Path,default=Path('build/dispatcher-check.json'))
    args=p.parse_args()
    checks=[]
    def passed(name):checks.append(name);print(name,flush=True)
    with Device(args.generator) as source,Device(args.receiver) as rx:
        info=[source.info,rx.info]
        assert all(i['core']==0 and i['worker_core']==1 and i['psram']==8388608 for i in info)
        passed('core0 CDC and explicit 8 MiB PSRAM on both boards')
        rejected(source,10,struct.pack('<I',1),5)
        passed('retired ICECAP disk command rejected')
        source.load('generator','flash')
        rejected(source,4,struct.pack('<5I',0,0,1,5000,0),7)
        rejected(source,4,struct.pack('<5I',0,45,1,5000,1),1)
        passed('generation requires drive opt-in; GPIO45 rejected')
        source.run(0,0,1,5000,1)
        # A corrupt GO must not start generation.
        bad=bytearray(encode(5,(source.seq+1)&65535));bad[5]^=1
        source.port.write(bad)
        status=source.status();assert status['state']==2 and not status['start']
        passed('bad CRC ignored while generator stays armed')
        source.seq=(source.seq+1)&65535
        frame=encode(5,source.seq)
        raw_reply(source,frame,source.seq,5)
        time.sleep(.02)
        raw_reply(source,frame,source.seq,5)
        assert source.status()['state']==4
        passed('duplicate GO replays ACK after completion without rerunning')
        rx.load('analyzer','flash')
        rx.run(1,44,1,100)
        assert json.loads(rx.request(1))['core']==0
        result=rx.wait(states=(5,))
        assert result['error']==2 and result['remaining']==1024
        passed('CDC responsive while armed; missing level times out')
        rx.load('analyzer','flash');rx.run(1,44,1,30000)
        start=time.monotonic();rx.request(7);result=rx.wait(states=(5,))
        abort_seconds=time.monotonic()-start
        assert result['error']==7 and abort_seconds<1
        passed('USB abort wakes worker and releases pins within one second')
        rx.load('analyzer','flash');rx.run(0,0,0,5000);result=rx.wait()
        assert set(rx.read_data(1,0,4096))=={0} and result['fdebug']==0
        passed('already LOW level triggers immediately without an edge')
        source.load('generator','flash');source.run(1,44,1,10000,1)
        rx.load('analyzer','flash');rx.run(0,44,1,5000)
        assert rx.status()['state']==2
        source.request(5);source.wait();result=rx.wait()
        assert set(rx.read_data(1,0,4096))=={0} and result['fdebug']==0
        passed('GPIO44 can trigger GPIO0..31 capture across PIO windows')
        # Check the device-side loader too; the host normally rejects this first.
        image=bytearray(Path('build/multidrop/2/app_analyzer.app').read_bytes());image[-1]^=1
        rx.request(12,struct.pack('<I',len(image)))
        for at in range(0,len(image),252):rx.request(13,struct.pack('<I',at)+image[at:at+252])
        rejected(rx,14,b'',3)
        passed('device rejects a corrupted uploaded executable')
        for device,app in ((source,'generator'),(rx,'analyzer')):
            image=Path(f'build/multidrop/1/app_{app}.app').read_bytes()
            device.upload(image);device.load(app,'uploaded')
        passed('both independently built applications upload and load from PSRAM')
    report={'devices':info,'passed':checks,'abort_seconds':abort_seconds}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
