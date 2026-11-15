#!/usr/bin/env python3
"""Create the unrouted KiCad placement starter; never replace GUI edits by default.

Run with KiCad's Python (pcbnew module) after exporting the schematic XML netlist.
Custom connector lands are provisional hand-formed geometry, not supplier SMT parts.
"""
import argparse
import csv
from pathlib import Path
import xml.etree.ElementTree as ET

import pcbnew as pcb

from kicad_sexpr import child, children, dump, library_dir, parse, Q

ROOT = Path(__file__).resolve().parents[1]
KICAD = ROOT / 'kicad'
ORIGIN = (100.0, 100.0)
# Millimetres from the DIP mating-pattern centre. End tab is at positive Y.
OUTLINE = [(-10,-30.98),(10,-30.98),(10.5,-30.48),(10.5,30.5),
           (11,31),(13,31),(13.5,31.5),(13.5,39.48),(13,39.98),
           (-13,39.98),(-13.5,39.48),(-13.5,31.5),(-13,31),
           (-11,31),(-10.5,30.5),(-10.5,-30.48)]

# x, y, rotation, side. These are a placement study, not completed power/QSPI layout.
PLACEMENT = {
    'J1': (0,0,0,'F'), 'J2': (0,0,0,'B'),
    'U1': (0,0,180,'F'), 'U2': (-1,-20,0,'F'),
    'C4': (-4.5,-20,90,'F'), 'C5': (2.5,-20,90,'F'),
    'C23': (-6.3,6.5,90,'B'),
    'Y1': (0,-10.5,0,'F'), 'C1': (-3,-10.5,90,'F'),
    'C2': (3,-10.5,90,'F'), 'R1': (0,-8,0,'F'),
    'R2': (3.7,10.0,90,'F'), 'R3': (-3,-14,0,'F'),
    'L1': (-3,7.4,0,'F'), 'C7': (-4,10,0,'F'),
    'C8': (-6.3,6.5,90,'F'), 'R6': (-6.3,8.8,90,'F'),
    'C6': (-6.3,-3.6,90,'B'),
    'C9': (6.3,2.2,90,'F'), 'C10': (6.3,-1.8,90,'F'),
    'C11': (3.3,-6.3,0,'F'), 'C12': (.8,-6.3,0,'F'),
    'C13': (-6.3,-3.6,90,'F'), 'C14': (-6.3,0,90,'F'),
    'C15': (-6.3,3.6,90,'F'), 'C16': (5,6.3,0,'F'),
    'C17': (0,6.3,0,'F'), 'C18': (2.5,6.3,0,'F'),
    'C19': (-6.3,3.6,90,'B'), 'C20': (-1.7,-6.3,0,'F'),
    'C21': (-6.3,0,90,'B'), 'C22': (6.3,.2,90,'F'),
    'U5': (0,11.5,0,'F'), 'R4': (3.7,12.5,90,'F'),
    'C24': (-3,13,90,'F'), 'C25': (-4.5,13,90,'F'),
    'R5': (5.5,22,90,'F'), 'R19': (-5,18,90,'F'),
    'R20': (-3.5,18,90,'F'),
    'J3': (-7,36.305,0,'F'), 'J4': (1.8,36.4,0,'F'),
    'SW1': (9.5,33,0,'F'), 'SW2': (9.5,38,0,'F'),
    'JP1': (9.5,35.5,0,'F'),
    'U4': (-4,27.8,0,'F'), 'R9': (3.5,8.2,0,'F'),
    'R10': (1.1,8.2,0,'F'), 'R7': (-6.3,27,90,'F'),
    'R8': (-6.3,29.5,90,'F'),
    'Q1': (3.7,27.8,0,'F'), 'R11': (0,29,90,'F'),
    'R12': (0,26.5,90,'F'), 'R13': (3.7,24.3,0,'F'),
}
for i in range(5):
    PLACEMENT['R'+str(14+i)] = (-4.5,-5.6+i*2.8,0,'B')
    PLACEMENT['D'+str(1+i)] = (-2.8,-5.6+i*2.8,90,'B')


def vec(x,y):
    return pcb.VECTOR2I(pcb.FromMM(x),pcb.FromMM(y))


def pos(x,y):
    return vec(x+ORIGIN[0],y+ORIGIN[1])


def shape(board,a,b,layer,width=.05):
    item=pcb.PCB_SHAPE();item.SetShape(pcb.SHAPE_T_SEGMENT)
    item.SetStart(pos(*a));item.SetEnd(pos(*b));item.SetLayer(layer)
    item.SetWidth(pcb.FromMM(width));board.Add(item)


def text(board,value,x,y,layer=pcb.Dwgs_User,size=.75,angle=0):
    item=pcb.PCB_TEXT(board);item.SetText(value);item.SetPosition(pos(x,y))
    item.SetLayer(layer);item.SetTextSize(vec(size,size))
    item.SetTextThickness(pcb.FromMM(.1 if size>=.7 else .08))
    item.SetTextAngle(pcb.EDA_ANGLE(angle,pcb.DEGREES_T))
    if layer==pcb.B_SilkS:
        item.SetMirrored(True)
    board.Add(item)


def add_stackup(path):
    # pcbnew's Python bindings do not expose the stackup descriptor. Insert only
    # this setup subsection, preserving the native board's remaining text.
    layers=[('F.SilkS','Top Silk Screen',None),('F.Paste','Top Solder Paste',None),
            ('F.Mask','Top Solder Mask',.01),('F.Cu','copper',.035),
            ('dielectric 1','prepreg',.18),('In1.Cu','copper',.035),
            ('dielectric 2','core',1.10),('In2.Cu','copper',.035),
            ('dielectric 3','prepreg',.18),('B.Cu','copper',.035),
            ('B.Mask','Bottom Solder Mask',.01),('B.Paste','Bottom Solder Paste',None),
            ('B.SilkS','Bottom Silk Screen',None)]
    stack=['stackup']
    for name,kind,thickness in layers:
        node=['layer',Q(name),['type',Q(kind)]]
        if thickness is not None:
            node.append(['thickness',thickness])
        if kind in ('core','prepreg'):
            node += [['material',Q('FR4')],['epsilon_r',4.5],['loss_tangent',.02]]
        stack.append(node)
    stack += [['copper_finish',Q('ENIG')],['dielectric_constraints','no']]
    content=path.read_text()
    assert '(stackup' not in content
    content=content.replace('\t(setup\n','\t(setup\n'+dump(stack)+'\n',1)
    path.write_text(content)


def build(netlist,output):
    root=ET.parse(netlist).getroot()
    board=pcb.BOARD();board.SetCopperLayerCount(4)
    board.SetLayerName(pcb.In1_Cu,'GND');board.SetLayerName(pcb.In2_Cu,'3V3')
    settings=board.GetDesignSettings()
    settings.SetBoardThickness(pcb.FromMM(1.6))
    settings.m_CopperEdgeClearance=pcb.FromMM(.3)
    settings.m_SolderMaskExpansion=pcb.FromMM(.025)
    settings.m_SolderMaskMinWidth=pcb.FromMM(.075)
    title=board.GetTitleBlock()
    title.SetTitle('MC68008 ICE - placement study, UNROUTED')
    title.SetRevision('0.1 MECHANICAL');title.SetDate('2026-11-10')
    nets={};mapping={}
    for node in root.findall('nets/net'):
        net=pcb.NETINFO_ITEM(board,node.get('name'));board.Add(net)
        nets[node.get('name')]=net
        for pin in node.findall('node'):
            mapping[pin.get('ref'),pin.get('pin')]=net
    components=root.findall('components/comp')
    assert {n.get('ref') for n in components}==set(PLACEMENT)
    schematic=parse((KICAD/'rp2350_68008_ice.kicad_sch').read_text())
    sheet_uuid=str(child(schematic,'uuid')[1])
    audit=[]
    for comp in components:
        ref=comp.get('ref');fp_id=comp.findtext('footprint')
        assert fp_id,ref+' has no footprint'
        lib,name=fp_id.split(':')
        directory=KICAD/'rp2350_ice.pretty' if lib=='rp2350_ice' else library_dir().parent/'footprints'/(lib+'.pretty')
        fp=pcb.FootprintLoad(str(directory),name)
        assert fp is not None,(ref,fp_id)
        fp.SetFPID(pcb.LIB_ID(lib,name));fp.SetReference(ref)
        fp.SetValue(comp.findtext('value') or '')
        path=pcb.KIID_PATH();path.push_back(pcb.KIID(sheet_uuid))
        path.push_back(pcb.KIID(comp.findtext('tstamps')));fp.SetPath(path)
        fp.SetSheetname('/');fp.SetSheetfile('rp2350_68008_ice.kicad_sch')
        x,y,angle,side=PLACEMENT[ref]
        board.Add(fp)
        fp.SetPosition(pos(x,y))
        fp.SetOrientationDegrees(angle)
        if side=='B':
            # Flip also changes the native footprint orientation. Do not reset
            # its angle afterwards: that would rotate the pin pattern again.
            fp.Flip(pos(x,y),pcb.FLIP_DIRECTION_LEFT_RIGHT)
        for field in comp.findall('fields/field'):
            key=field.get('name');fp.SetField(key,field.text or '')
            fp.GetField(key).SetVisible(False)
        expected={pin for r,pin in mapping if r==ref}
        actual={p.GetNumber() for p in fp.Pads() if p.GetNumber()}
        assert expected==actual,(ref,expected-actual,actual-expected)
        for pad in fp.Pads():
            net=mapping.get((ref,pad.GetNumber()))
            if net is not None:
                pad.SetNet(net)
        fp.Reference().SetTextSize(vec(.6,.6));fp.Reference().SetTextThickness(pcb.FromMM(.1))
        fp.Reference().SetLayer(pcb.B_Fab if side=='B' else pcb.F_Fab)
        fp.Reference().SetPosition(pos(x,y-1.4))
        fp.Reference().SetVisible(ref not in ('J1','J2','J3','J4','SW1','SW2','JP1','U1'))
        fp.Value().SetVisible(False)
        if ref in ('J1','J2'):
            fp.SetLocked(True)
        audit.append({'reference':ref,'footprint':fp_id,'side':side,
                      'x_mm':x+100,'y_mm':y+100,'rotation_deg':fp.GetOrientationDegrees(),
                      'status':'provisional hand-formed contacts' if ref in ('J1','J2') else 'assigned; placement review required'})
    for a,b in zip(OUTLINE,OUTLINE[1:]+OUTLINE[:1]):
        shape(board,a,b,pcb.Edge_Cuts)
    # Copper-zone outlines only: no routing/vias or fabricated plane-connection
    # claim. Refill after ground/power stitching and placement have been reviewed.
    for layer,name in [(pcb.In1_Cu,'GND'),(pcb.In2_Cu,'+3V3')]:
        zone=pcb.ZONE(board);zone.SetLayer(layer);zone.SetNet(nets[name])
        zone.SetLocalClearance(pcb.FromMM(.15));zone.SetMinThickness(pcb.FromMM(.15))
        zone.SetThermalReliefGap(pcb.FromMM(.2));zone.SetThermalReliefSpokeWidth(pcb.FromMM(.25))
        zone.SetPadConnection(pcb.ZONE_CONNECTION_FULL)
        zone.SetIslandRemovalMode(pcb.ISLAND_REMOVAL_MODE_ALWAYS)
        poly=zone.Outline();poly.NewOutline()
        for x,y in OUTLINE:
            v=pos(x,y);poly.Append(v.x,v.y)
        board.Add(zone)
    # Mating-pin centre lines are independent of the outward solder-pad rows.
    for x in [-7.62,7.62]:
        shape(board,(x,-29.21),(x,29.21),pcb.Dwgs_User,.1)
    shape(board,(-8.86,30.48),(8.86,30.48),pcb.Dwgs_User,.1)
    for value,x,y in [('USB',-7,37.8),('SWD',1.8,37.8),('BOOT',9.5,33),
                      ('RUN',9.5,38),('MODE',9.5,35.5)]:
        text(board,value,x,y,pcb.B_SilkS,.8)
    text(board,'BOOT',12.9,33,pcb.F_SilkS,.8,90)
    text(board,'RUN',12.9,38,pcb.F_SilkS,.8,90)
    text(board,'ACT',11.9,35.5,pcb.F_SilkS,.8)
    text(board,'1',-6.8,-29.8,pcb.F_SilkS,.8)
    text(board,'1',-6.8,-29.8,pcb.B_SilkS,.8)
    text(board,'68008 ICE / UNROUTED',0,-17,pcb.F_SilkS,.8)
    text(board,'PLACEMENT ONLY - HAND-FORMED CONTACTS\n21 mm body / 27 mm tab / 70.96 mm length\n60.96 mm provisional socket body; 9.50 mm access extension\nMating rows 15.24 mm; solder-pad rows 17.24 mm\nF.Cu signals / In1 GND / In2 3V3 / B.Cu signals',0,46,pcb.Dwgs_User,.9)
    output.parent.mkdir(parents=True,exist_ok=True)
    # SaveBoard also writes the associated project with this fresh BOARD's
    # defaults. Preserve the user's existing project settings around that call.
    project=output.with_suffix('.kicad_pro')
    saved_project=project.read_text() if project.exists() else None
    try:
        pcb.SaveBoard(str(output),board)
    finally:
        if saved_project is not None:
            project.write_text(saved_project)
    add_stackup(output)
    report=ROOT/'build/hardware/footprint_audit.csv'
    report.parent.mkdir(parents=True,exist_ok=True)
    with report.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(audit[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(audit)
    print('Created',output,'with',len(components),'footprints, four copper layers and no tracks.')
    print('Footprint coverage/pad-number audit:',report)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--netlist',type=Path,default=ROOT/'build/hardware/netlist.xml')
    parser.add_argument('--output',type=Path,default=KICAD/'rp2350_68008_ice.kicad_pcb')
    parser.add_argument('--overwrite',action='store_true',help='explicitly discard saved board edits')
    args=parser.parse_args()
    if args.output.exists() and not args.overwrite:
        parser.error('Board already exists; edit it in KiCad or use a different --output path.')
    build(args.netlist,args.output)
