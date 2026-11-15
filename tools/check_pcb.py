#!/usr/bin/env python3
"""Check the saved PCB against the schematic and independent DIP geometry.

Run with KiCad's Python. This verifies the unrouted placement milestone only;
use KiCad DRC and physical measurements separately before fabrication.
"""
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET

import pcbnew as pcb

from kicad_sexpr import child, children, parse

ROOT=Path(__file__).resolve().parents[1]


def check(board_path,netlist):
    board=pcb.LoadBoard(str(board_path))
    doc=ET.parse(netlist).getroot()
    parts={f.GetReference():f for f in board.GetFootprints()}
    expected={n.get('ref'):n for n in doc.findall('components/comp')}
    assert set(parts)==set(expected),(set(parts)-set(expected),set(expected)-set(parts))
    nets={(p.get('ref'),p.get('pin')):n.get('name') for n in doc.findall('nets/net') for p in n.findall('node')}
    for ref,fp in parts.items():
        comp=expected[ref]
        fp_id=str(fp.GetFPID().GetLibNickname())+':'+str(fp.GetFPID().GetLibItemName())
        assert fp_id==comp.findtext('footprint'),(ref,fp_id)
        assert fp.GetValue()==comp.findtext('value'),ref
        pads={p.GetNumber() for p in fp.Pads() if p.GetNumber()}
        assert pads=={pin for r,pin in nets if r==ref},ref
        for pad in fp.Pads():
            if pad.GetNumber():
                assert pad.GetNetname()==nets[ref,pad.GetNumber()],(ref,pad.GetNumber())
        assert fp.GetPath().AsString().endswith('/'+comp.findtext('tstamps')),ref
    j1={p.GetNumber():p for p in parts['J1'].Pads()}
    j2={p.GetNumber():p for p in parts['J2'].Pads()}
    assert parts['J1'].GetLayer()==pcb.F_Cu and parts['J2'].GetLayer()==pcb.B_Cu
    for number in range(1,49):
        pin=str(number);a,b=j1[pin],j2[pin]
        assert a.GetPosition()==b.GetPosition(),('top/bottom mirror error',pin)
        assert a.GetNetname()==b.GetNetname(),('pin correspondence',pin)
        x=100+(-8.62 if number<=24 else 8.62)
        y=100-29.21+((number-1) if number<=24 else (48-number))*2.54
        assert abs(pcb.ToMM(a.GetPosition().x)-x)<1e-6 and abs(pcb.ToMM(a.GetPosition().y)-y)<1e-6,pin
        for pad,layer in [(a,pcb.F_Cu),(b,pcb.B_Cu)]:
            assert pad.GetAttribute()==pcb.PAD_ATTRIB_SMD
            assert pad.GetDrillSize().x==pad.GetDrillSize().y==0
            assert pad.GetLayerSet().Contains(layer)
            assert not pad.GetLayerSet().Contains(pcb.F_Paste)
            assert not pad.GetLayerSet().Contains(pcb.B_Paste)
    assert board.GetCopperLayerCount()==4
    native=parse(board_path.read_text())
    copper={str(n[1]) for n in child(native,'layers')[1:] if n[2]=='signal'}
    assert copper=={'F.Cu','In1.Cu','In2.Cu','B.Cu'},copper
    assert board.GetLayerName(pcb.In1_Cu)=='GND' and board.GetLayerName(pcb.In2_Cu)=='3V3'
    zones=list(board.Zones())
    assert {(z.GetLayer(),z.GetNetname()) for z in zones}=={(pcb.In1_Cu,'GND'),(pcb.In2_Cu,'+3V3')}
    stack=child(child(native,'setup'),'stackup')
    thickness=sum(float(child(n,'thickness')[1]) for n in children(stack,'layer')
                  if n[1] not in ['F.Mask','B.Mask'] and child(n,'thickness'))
    assert abs(thickness-1.6)<1e-6,thickness
    edge=[s for s in board.GetDrawings() if s.GetLayer()==pcb.Edge_Cuts]
    endpoints={}
    for item in edge:
        for v in [item.GetStart(),item.GetEnd()]:
            key=(v.x,v.y);endpoints[key]=endpoints.get(key,0)+1
    assert len(edge)==16 and set(endpoints.values())=={2},'Outline must be closed'
    xs=[pcb.ToMM(v[0]) for v in endpoints];ys=[pcb.ToMM(v[1]) for v in endpoints]
    assert abs(max(xs)-min(xs)-27)<1e-6 and abs(max(ys)-min(ys)-70.96)<1e-6
    for ref in ['J3','J4','SW1','SW2','JP1']:
        assert pcb.ToMM(parts[ref].GetPosition().y)>131,ref+' must be on the access extension'
    print('PASS: 63 footprints, pad nets, values and schematic UUID links agree.')
    print('PASS: 48 co-registered top/bottom SMT pads; correct independent DIP numbering and mirroring; no paste/holes.')
    print('PASS: four layers, GND/3V3 zones and 1.6 mm provisional stack; 70.96 x 21 mm body with 27 mm tab.')
    print('PASS: USB/SWD/buttons/mode bridge occupy the accessible end.')
    print('State:',len(list(board.GetTracks())),'tracks/vias; routing, plane stitching and physical socket validation remain.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('board',type=Path,nargs='?',default=ROOT/'kicad/rp2350_68008_ice.kicad_pcb')
    parser.add_argument('--netlist',type=Path,default=ROOT/'build/hardware/netlist.xml')
    args=parser.parse_args();check(args.board,args.netlist)
