#!/usr/bin/env python3
"""Run the BAT54 DC checks using ngspice's shared library (also shipped by KiCad).

Set NGSPICE_LIBRARY to libngspice if automatic discovery is insufficient.
The Diodes Inc / Zetex model is a nominal proxy, not a JSCJ production corner.
"""
import argparse
import csv
import ctypes as C
from ctypes.util import find_library
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT/'simulations/bat54/BAT54.lib'


class Vector(C.Structure):
    _fields_ = [('name',C.c_char_p),('type',C.c_int),('flags',C.c_short),
                ('real',C.POINTER(C.c_double)),('complex',C.c_void_p),('length',C.c_int)]


class Ngspice:
    def __init__(self):
        candidates = [os.environ.get('NGSPICE_LIBRARY'),find_library('ngspice'),
                      '/Applications/KiCad/KiCad.app/Contents/Frameworks/libngspice.0.dylib']
        path = next((p for p in candidates if p), None)
        if not path:
            raise SystemExit('Install ngspice shared library or set NGSPICE_LIBRARY.')
        self.lib = C.CDLL(path)
        self.log = []
        self.callback_type = C.CFUNCTYPE(C.c_int,C.c_char_p,C.c_int,C.c_void_p)
        self.callback = self.callback_type(self.receive)
        self.lib.ngSpice_Init.argtypes = [C.c_void_p]*7
        self.lib.ngSpice_Command.argtypes = [C.c_char_p]
        self.lib.ngSpice_Circ.argtypes = [C.POINTER(C.c_char_p)]
        self.lib.ngGet_Vec_Info.argtypes = [C.c_char_p]
        self.lib.ngGet_Vec_Info.restype = C.POINTER(Vector)
        assert self.lib.ngSpice_Init(self.callback,None,None,None,None,None,None)==0
        self.command('version')

    def receive(self, text, ident, user):
        self.log.append(text.decode(errors='replace'))
        return 0

    def command(self, command):
        result = self.lib.ngSpice_Command(command.encode())
        if result:
            raise RuntimeError(command+'\n'+'\n'.join(self.log[-15:]))

    def operating_point(self, lines):
        data = [s.encode() for s in lines]
        array = (C.c_char_p*(len(data)+1))(*data,None)
        if self.lib.ngSpice_Circ(array):
            raise RuntimeError('\n'.join(self.log[-15:]))
        self.command('op')

    def scalar(self, name):
        pointer = self.lib.ngGet_Vec_Info(name.encode())
        if not pointer or pointer.contents.length!=1 or not pointer.contents.real:
            raise RuntimeError('Missing scalar '+name+'\n'+'\n'.join(self.log[-15:]))
        return float(pointer.contents.real[0])


def run(out):
    out.mkdir(parents=True,exist_ok=True)
    ng = Ngspice()
    rows = []
    forced = [0.0001,0.0005,(1.7/2.2)*1e-3,0.001]
    for temp in [-20,0,25,70]:
        for current in forced:
            circuit = ['BAT54 forced forward current',f'.include "{MODEL}"',
                       f'Itest 0 anode DC {current:.12g}','Dtest anode 0 BAT54',
                       f'.temp {temp}','.options tnom=27','.end']
            ng.operating_point(circuit)
            rows.append(dict(case='forced_current',temp_C=temp,source_V='',rail_V='',
                             resistor_ohm='',current_mA=current*1000,
                             Vf_V=ng.scalar('v(anode)'),node_V=ng.scalar('v(anode)')))
        for case,source,rail,resistor in [('nominal_resistor',5.0,3.3,2200),
                                          ('supply_resistor_corner',5.25,3.234,2178)]:
            circuit = ['BAT54 input clamp with series resistor',f'.include "{MODEL}"',
                       f'Vinput input 0 {source}',f'Vrail rail 0 {rail}',
                       f'Rseries input node {resistor}','Dclamp node rail BAT54',
                       f'.temp {temp}','.options tnom=27','.end']
            ng.operating_point(circuit)
            node = ng.scalar('v(node)')
            rows.append(dict(case=case,temp_C=temp,source_V=source,rail_V=rail,
                             resistor_ohm=resistor,current_mA=(source-node)/resistor*1000,
                             Vf_V=node-rail,node_V=node))
    # A hand-editable netlist for a conventional ngspice batch installation.
    (ROOT/'simulations/bat54/clamp.cir').write_text('''BAT54 nominal 5V / 2.2k / 3V3 clamp (nominal proxy model)
.include BAT54.lib
Vinput input 0 5
Vrail rail 0 3.3
Rseries input node 2.2k
Dclamp node rail BAT54
.temp 25
.options tnom=27
.op
.end
''')
    with (out/'results.csv').open('w',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    (out/'ngspice.log').write_text('\n'.join(ng.log)+'\n')
    version = next((s for s in ng.log if 'shared library' in s),'unknown')
    metadata = {'engine':version,'model':'Diodes Inc / Zetex BAT54 v1.0 (2000-04-25)',
                'model_source':'https://www.diodes.com/spice/download/510/BAT54.spice.txt',
                'model_sha256':hashlib.sha256(MODEL.read_bytes()).hexdigest(),
                'bom_part':'R+O BAT54X C19627026 SOD-523; different manufacturer, no qualified R+O corner model established',
                'scope':'nominal DC model, temperature sensitivity; no process spread, rail startup, GPIO internal clamp or self-heating proof'}
    (out/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    for row in rows:
        if row['temp_C']==25:
            print(f"{row['case']:25s} {row['current_mA']:.6f} mA: Vf={row['Vf_V']:.6f} V")
    return rows


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'simulations/bat54/results')
    run(parser.parse_args().output)
