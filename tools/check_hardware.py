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

from kicad_sexpr import parse, children, child, symbol_pins, library_dir

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

    # Check physical net membership, including unlabelled point-to-point wires.
    # A label may be removed when a connection becomes a drawn wire; that must
    # not weaken the checks or turn an arbitrary generated net name into a fault.
    circuit=json.loads((ROOT/'tools/hardware_circuit.json').read_text())['components']
    expected={}
    for definition in circuit:
        ref=definition['reference'];mapping=definition['pins'].copy()
        if ref in ('J1','J2'):
            mapping={r['dip_pin']:r['target_net'] for r in rows}
        if ref=='U1':
            mapping.update({r['mcu_qfn_pin']:r['mcu_net'] for r in rows if r['mcu_gpio']})
            mapping.update({r['qfn_pin']:r['net'] for r in gpios})
        for pin,net in mapping.items():
            expected.setdefault(net,set()).add((ref,pin))
    for net,pins in expected.items():
        codes={nets[p] for p in pins}
        assert len(codes)==1,(net,'split connection',[(p,names[p]) for p in sorted(pins)])
        actual={p for p,code in nets.items() if code in codes}
        assert actual==pins,(net,'unexpected net members',actual-pins,pins-actual)

    def same(*pins):
        assert len({nets[p] for p in pins})==1, [(p,names[p]) for p in pins]

    def different(*pins):
        assert len({nets[p] for p in pins})==len(pins), [(p,names[p]) for p in pins]

    for r in rows:
        pin=r['dip_pin'];same(('J1',pin),('J2',pin))
        assert names['J1',pin].removeprefix('/')==r['target_net']
        if r['mcu_gpio']:
            m=('U1',r['mcu_qfn_pin'])
            if int(r['mcu_gpio'])<40:
                same(('J1',pin),m)
            else:
                ch=int(r['mcu_gpio'])-40
                series='R'+str(14+ch)
                diode='D'+str(1+ch)
                same(('J1',pin),(series,'1'))
                same(m,(series,'2'),(diode,'2'))
                same((diode,'1'),('U1','5'))
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
    same(('J4','1'),('U1','33'))
    same(('J4','3'),('U1','34'))
    same(('J4','2'),('J4','MP'),('J1','15'))
    different(('J4','1'),('J4','2'),('J4','3'),('U1','5'))
    same(('L1','2'),('U1','63'))
    same(('U1','56'),('JP1','2'),('R5','1'))
    same(('U1','57'),('Q1','3'),('R13','2'))
    same(('JP1','1'),('U1','5'))
    same(('R5','2'),('J1','15'))
    # AP Memory APS6404L pinout and RP2354B dedicated QSPI pinout.
    same(('U5','1'),('U1','58'),('R4','2'))
    for ram_pin,mcu_pin in [('6','71'),('5','72'),('2','74'),('3','73'),('7','70')]:
        same(('U5',ram_pin),('U1',mcu_pin))
    same(('U5','8'),('R4','1'),('C24','1'),('C25','1'),('U1','5'))
    same(('U5','4'),('C24','2'),('C25','2'),('J1','15'))
    different(('U5','1'),('U1','75'))
    assert names['U5','9'].startswith('unconnected-'), 'Leave the unassigned PSRAM paddle floating.'
    assert sum(net==nets['U5','9'] for net in nets.values())==1
    same(('J3','A6'),('J3','B6'),('U4','1'))
    same(('J3','A7'),('J3','B7'),('U4','2'))
    same(('J3','A4'),('J3','A9'),('J3','B4'),('J3','B9'))
    different(('J3','A4'),('J1','13'),('U1','5'))
    same(('SW1','1'),('SW2','1'),('J1','15'))
    same(('SW1','2'),('R2','1'))
    same(('U1','75'),('R2','2'))
    same(('SW2','2'),('U1','35'))
    different(('U1','35'),('J1','37'))
    # SOD-523 clamps have exactly two pads: 1 cathode, 2 anode.
    diode_symbol=next(n for n in children(child(schematic,'lib_symbols'),'symbol')
                      if n[1]=='rp2350_ice:BAT54X')
    assert {str(child(p,'number')[1]):str(child(p,'name')[1])
            for p in symbol_pins(diode_symbol)}=={'1':'K','2':'A'}
    for i in range(1,6):
        assert {pin for ref,pin in nets if ref==f'D{i}'}=={'1','2'}
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
    # Standard KiCad footprint: manufacturer drawing is USON 3x2 mm,
    # 0.5 mm pitch, with a 0.2x1.6 mm centre paddle.
    ram_footprint=parts['U5'].findtext('footprint')
    lib,name=ram_footprint.split(':')
    fp=parse((library_dir().parent/'footprints'/(lib+'.pretty')/(name+'.kicad_mod')).read_text())
    pads={str(p[1]):p for p in children(fp,'pad') if p[1]}
    assert set(pads)=={str(i) for i in range(1,10)}
    assert [float(v) for v in child(pads['9'],'size')[1:]]==[0.2,1.6]
    for i in range(1,4):
        y1=float(child(pads[str(i)],'at')[2]);y2=float(child(pads[str(i+1)],'at')[2])
        assert abs(y2-y1-0.5)<1e-6
    diode_fp=parse((library_dir().parent/'footprints'/'Diode_SMD.pretty'/'D_SOD-523.kicad_mod').read_text())
    assert {str(p[1]) for p in children(diode_fp,'pad')}=={'1','2'}
    connector_fp=parts['J4'].findtext('footprint')
    assert connector_fp=='Connector_JST:JST_SH_SM03B-SRSS-TB_1x03-1MP_P1.00mm_Horizontal'
    lib,name=connector_fp.split(':')
    fp=parse((library_dir().parent/'footprints'/(lib+'.pretty')/(name+'.kicad_mod')).read_text())
    pads=children(fp,'pad')
    assert {str(p[1]) for p in pads}=={'1','2','3','MP'}
    signal_pads={str(p[1]):p for p in pads if p[1] in ['1','2','3']}
    for i in range(1,3):
        assert float(child(signal_pads[str(i+1)],'at')[1])-float(child(signal_pads[str(i)],'at')[1])==1.0
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
        for field in ['LCSC','JLCPCB_library','Assembly','Selection_reason']:
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
    assert fitted['R4']['Value']=='1k' and fitted['R4']['LCSC']==fitted['R1']['LCSC']
    assert fitted['U5']['LCSC']=='C3040877'
    assert fitted['C24']['LCSC']==fitted['C6']['LCSC'] and fitted['C25']['LCSC']==fitted['C9']['LCSC']
    assert {int(r['gpio']):r['net'] for r in gpios if int(r['gpio'])>=45}=={45:'MODE_PERMIT',46:'USB_PRESENT_N',47:'PSRAM_CS_N'}
    assert {fitted[f'D{i}']['Value'] for i in range(1,6)}=={'BAT54X'}
    assert {fitted[f'D{i}']['LCSC'] for i in range(1,6)}=={'C19627026'}
    assert {fitted[f'D{i}']['Footprint'] for i in range(1,6)}=={'Diode_SMD:D_SOD-523'}
    assert fitted['J4']['LCSC']=='C160403' and fitted['J4']['Assembly']=='JLCPCB_SMT'
    assert fitted['C23']['Value']=='100n' and fitted['C23']['LCSC']==fitted['C9']['LCSC']
    assert {fitted[f'R{i}']['Value'] for i in range(14,19)}=={'2.2k'}
    assert {fitted[f'R{i}']['Value'] for i in [3,5,11,13]}=={'10k'}
    print('PASS: Motorola DIP pin order; 48 pass-through contacts; 40 direct and 5 resistor/single-BAT54 MCU paths.')
    print('PASS: all 48 GPIOs; supply/dedicated pins; USB VBUS separation; two-pad switches.')
    print('PASS: JST-SH SWD pinout 1=CLK, 2=GND, 3=IO; grounded mounting pads; no supply contact.')
    print('PASS: 8 MiB PSRAM on QSPI/CS1; distinct flash select; GPIO46 USB sense; 1k pull-up and local bypass.')
    print('PASS: every circuit-source net matches physical connections, including unlabelled wires.')
    print(f'PASS: {len(parts)} schematic components match BOM; reference footprint pad numbers match.')
    print(f'PASS: {len(assembled)} SMT positions and {len(selected)} catalog SKUs; grouped JLCPCB BOM excludes manual/PCB-only positions.')
    print('PASS: one A3 schematic, no child sheets; one shared J1/J2 bypass capacitor.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('netlist',type=Path)
    check(parser.parse_args().netlist)
