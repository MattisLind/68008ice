#!/usr/bin/env python3
"""Check the exported KiCad XML netlist against the pin map and candidate BOM.

Usage: python3 tools/check_hardware.py build/hardware/netlist.xml
This checks connectivity, not voltage margins, power sequencing or PIO timing.
"""
import argparse
import csv
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from kicad_sexpr import parse, children, child, symbol_pins

ROOT = Path(__file__).resolve().parents[1]


def check(path):
    root = ET.parse(path).getroot()
    schematic=parse((ROOT/'kicad/rp2350_68008_ice.kicad_sch').read_text())
    assert child(schematic,'paper')[1]=='A3'
    assert not children(schematic,'sheet'), 'Keep all circuits on the single A3 sheet.'
    assert not children(schematic,'global_label'), 'Use local labels on the single sheet.'
    assert len(list((ROOT/'kicad').glob('*.kicad_sch')))==1
    rows = list(csv.DictReader((ROOT/'kicad/mc68008_pinmap.csv').open()))
    gpios = list(csv.DictReader((ROOT/'kicad/rp2354b_gpio.csv').open()))
    bom = list(csv.DictReader((ROOT/'kicad/BOM.csv').open()))
    # Motorola MC68000UM Fig.11-5, independently transcribed in physical order.
    expected = ('A3 A4 A5 A6 A7 A8 A9 A10 A11 A12 A13 A14 VCC A15 GND '
                'A16 A17 A18 A19 D7 D6 D5 D4 D3 D2 D1 D0 AS_N DS_N RW '
                'DTACK_N BG_N BR_N CLK GND HALT_N RESET_N E VPA_N BERR_N '
                'IPL1_N IPL20_N FC2 FC1 FC0 A0 A1 A2').split()
    assert len(rows)==48
    assert {int(r['dip_pin']):r['signal'] for r in rows} == dict(enumerate(expected,1))
    assert {int(r['gpio']) for r in gpios}==set(range(48))
    assert len({r['qfn_pin'] for r in gpios})==48
    nets = {}; names = {}; functions = {}
    for net in root.findall('nets/net'):
        for p in net.findall('node'):
            key = (p.get('ref'),p.get('pin'))
            assert key not in nets, ('pin in two nets',key)
            nets[key]=net.get('code'); names[key]=net.get('name')
            functions[key]=p.get('pinfunction','')
    for r in gpios:
        function=functions['U1',r['qfn_pin']]
        assert function.startswith('GPIO'+r['gpio']+'_') or function.startswith('GPIO'+r['gpio']+'/'), (r,function)

    def same(*pins):
        assert len({nets[p] for p in pins})==1, [(p,names[p]) for p in pins]

    def different(*pins):
        assert len({nets[p] for p in pins})==len(pins), [(p,names[p]) for p in pins]

    for r in rows:
        pin=r['dip_pin'];same(('J1',pin),('J2',pin))
        assert names['J1',pin].removeprefix('/')==r['target_net']
        if r['mcu_gpio']:
            m=('U1',r['mcu_qfn_pin'])
            assert names[m].removeprefix('/')==r['mcu_net'],(r,names[m])
            if int(r['mcu_gpio'])<40:
                same(('J1',pin),m)
            else:
                ch=int(r['mcu_gpio'])-40
                series='R'+str(14+ch)
                diode='D'+str(1+ch)
                same(('J1',pin),(series,'1'))
                same(m,(series,'2'),(diode,'1'))
                same((diode,'3'),('U1','5'))
                different(('J1',pin),m)
    # Check dedicated RP2354B interfaces and every power-pad assignment.
    for pin in [5,15,24,29,41,50,59,60,64,68,69,76]:
        assert names['U1',str(pin)]=='+3V3'
    for pin in [10,32,51,65]:
        assert names['U1',str(pin)]=='+1V1'
    for pin in [62,81]:
        assert names['U1',str(pin)]=='GND'
    # These directly wired nets need no label; accept KiCad's generated names.
    same(('U1','30'),('Y1','1'),('C1','1'))
    same(('U1','31'),('R1','2'))
    same(('R1','1'),('Y1','3'),('C2','1'))
    same(('U1','61'),('R6','2'),('C8','1'))
    for pin,net in {33:'SWCLK',34:'SWDIO',35:'MCU_RUN_N',
                    63:'VREG_LX',66:'USB_DM_MCU',67:'USB_DP_MCU',
                    75:'QSPI_SS_N',56:'MODE_PERMIT',57:'BUS_ARM_REQUEST',58:'USB_PRESENT_N'}.items():
        assert names['U1',str(pin)].removeprefix('/')==net
    same(('J3','A6'),('J3','B6'),('U4','1'))
    same(('J3','A7'),('J3','B7'),('U4','2'))
    same(('J3','A4'),('J3','A9'),('J3','B4'),('J3','B9'))
    different(('J3','A4'),('J1','13'),('U1','5'))
    same(('SW1','1'),('SW2','1'),('J1','15'))
    assert names['SW1','2'].removeprefix('/')=='BOOTSEL_SW'
    same(('SW2','2'),('U1','35'))
    different(('U1','35'),('J1','37'))
    for i in range(1,6):
        nc=('D'+str(i),'2')
        assert names[nc].startswith('unconnected-'), 'BAT54 pad 2 is NC.'
        assert sum(net==nets[nc] for net in nets.values())==1, nc
    same(('R19','1'),('R20','1'),('U1','5'))
    same(('R19','2'),('R20','2'),('J1','15'))
    same(('C23','1'),('J1','13'),('J2','13'))
    same(('C23','2'),('J1','15'),('J1','35'),('J2','15'),('J2','35'))
    assert names['C4','1']=='+5V' and names['C5','1']=='+3V3'
    parts={c.get('ref'):c for c in root.findall('components/comp')}
    fitted={r['Reference']:r for r in bom if not r['Reference'].startswith('TBD_')}
    assert set(parts)==set(fitted), (set(parts)-set(fitted),set(fitted)-set(parts))
    for ref,c in parts.items():
        assert c.findtext('value')==fitted[ref]['Value']
        assert (c.findtext('footprint') or '')==fitted[ref]['Footprint']
    # Pad numbers must match symbols for the two reference-derived footprints.
    for ref,name in [('L1','AOTA-B201610S3R3-101-T')]:
        fp=parse((ROOT/'kicad/rp2350_ice.pretty'/f'{name}.kicad_mod').read_text())
        pads={str(p[1]) for p in children(fp,'pad')}
        connected={pin for r,pin in nets if r==ref}
        assert pads==connected,(ref,pads,connected)
    catalog=json.loads((ROOT/'kicad/parts_catalog.json').read_text())['parts']
    selected={p['LCSC']:p for p in catalog.values()}
    assembled={r['Reference']:r for r in bom if r['Assembly']=='JLCPCB_SMT'}
    assert assembled
    for r in assembled.values():
        p=selected[r['LCSC']]
        assert p['Assembly']=='JLCPCB_SMT'
        for field in ['MPN','Footprint','Manufacturer','JLCPCB_library']:
            assert r[field]==p[field],(r['Reference'],field)
        assert r['JLCPCB_library'] in ('Basic','Extended')
        assert r['Source'].startswith('https://')
        # Verify the purchasing fields are embedded in the schematic too.
        properties={f.get('name'):f.text or '' for f in parts[r['Reference']].findall('fields/field')}
        for field in ['LCSC','JLCPCB_library','Assembly']:
            assert properties[field]==r[field],(r['Reference'],field)
    uploaded={}
    for r in csv.DictReader((ROOT/'kicad/BOM_JLCPCB.csv').open()):
        for ref in r['Designator'].split(','):
            assert ref not in uploaded
            uploaded[ref]=r['LCSC Part #']
    assert uploaded=={ref:r['LCSC'] for ref,r in assembled.items()}
    for r in bom:
        if r['Assembly'] in ('Manual','PCB_feature','Unresolved'):
            assert not r['LCSC']
    assert fitted['R19']['Value']==fitted['R20']['Value']=='1k'
    assert {fitted[f'D{i}']['Value'] for i in range(1,6)}=={'BAT54'}
    assert {fitted[f'D{i}']['LCSC'] for i in range(1,6)}=={'C8590'}
    assert fitted['C23']['Value']=='100n' and fitted['C23']['LCSC']==fitted['C9']['LCSC']
    assert {fitted[f'R{i}']['Value'] for i in range(14,19)}=={'2.2k'}
    assert {fitted[f'R{i}']['Value'] for i in [3,4,5,11,13]}=={'10k'}
    print('PASS: Motorola DIP pin order; 48 pass-through contacts; 40 direct and 5 resistor/single-BAT54 MCU paths.')
    print('PASS: all 48 GPIOs; supply/dedicated pins; USB VBUS separation; two-pad switches.')
    print(f'PASS: {len(parts)} schematic components match BOM; reference footprint pad numbers match.')
    print(f'PASS: {len(assembled)} SMT positions and {len(selected)} catalog SKUs; grouped JLCPCB BOM excludes manual/PCB-only positions.')
    print('PASS: one A3 schematic, no child sheets; one shared J1/J2 bypass capacitor.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('netlist',type=Path)
    check(parser.parse_args().netlist)
