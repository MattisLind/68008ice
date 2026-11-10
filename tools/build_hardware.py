#!/usr/bin/env python3
"""Generate one editable A3 schematic from the circuit, pin map and parts catalog.

Review GUI edits before regeneration: --overwrite replaces the generated drawing.
Use --bom-only to refresh purchasing outputs while preserving the edited drawing.
Circuit topology lives in hardware_circuit.json; purchasing data lives in
kicad/parts_catalog.json. MCU/CPU bus connections follow the reviewed pin CSV.
"""
import argparse
import csv
import json
from pathlib import Path

from kicad_sexpr import Libraries, Sheet, child, children, parse

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'kicad'
PROJECT = 'rp2350_68008_ice'

# Millimetres on the 1.27 mm schematic grid. The drawing remains true A3 size;
# symbol geometry is not scaled down to fit several pages into a single page.
PLACEMENT = {
    'J1':(44.45,76.2), 'J2':(105.41,76.2), 'U1':(207.01,83.82),
    'R14':(256.54,27.94), 'D1':(256.54,52.07),
    'R15':(287.02,27.94), 'D2':(287.02,52.07),
    'R16':(317.5,27.94), 'D3':(317.5,52.07),
    'R17':(347.98,27.94), 'D4':(347.98,52.07),
    'R18':(378.46,27.94), 'D5':(378.46,52.07),
    'R19':(358.14,83.82), 'R20':(393.7,83.82),
    'R1':(261.62,109.22), 'Y1':(292.1,109.22),
    'C1':(269.24,137.16), 'C2':(309.88,137.16),
    'R2':(337.82,107.95), 'SW1':(337.82,137.16),
    'R3':(382.27,107.95), 'SW2':(384.81,137.16),
    'J4':(78.74,139.7), 'C23':(140.97,119.38),
    'U2':(45.72,180.34), 'C4':(15.24,180.34), 'C5':(78.74,180.34),
    'L1':(114.3,180.34), 'C6':(149.86,180.34), 'C7':(177.8,180.34),
    'R6':(213.36,180.34), 'C8':(246.38,180.34),
    'J3':(285.75,190.5), 'R7':(337.82,175.26), 'R8':(368.3,175.26),
    'U4':(347.98,213.36), 'R9':(327.66,236.22), 'R10':(383.54,236.22),
    'R11':(205.74,215.9), 'R12':(205.74,248.92),
    'Q1':(241.3,231.14), 'R13':(256.54,205.74),
    'R4':(256.54,245.11), 'R5':(284.48,245.11), 'JP1':(256.54,278.13),
    'U5':(335.28,63.5), 'C24':(360.68,66.04), 'C25':(382.27,66.04),
}
for i in range(14):
    PLACEMENT['C'+str(9+i)] = (15.24+(i%7)*27.94,228.6+(i//7)*30.48)


def build(bom_only=False):
    libs = Libraries()
    # Project symbol definitions are checked-in CAD sources, including the
    # passive CPU contact symbol and pin-compatible RP2354B symbol.
    library = parse((OUT/'rp2350_ice.kicad_sym').read_text())
    libs.used = {str(n[1]):n for n in children(library,'symbol')}
    catalog = json.loads((OUT/'parts_catalog.json').read_text())['parts']
    circuit = json.loads((ROOT/'tools/hardware_circuit.json').read_text())['components']
    rows = list(csv.DictReader((OUT/'mc68008_pinmap.csv').open()))
    by_gpio = {int(r['mcu_gpio']):r for r in rows if r['mcu_gpio']}
    assert len(rows)==48 and len(by_gpio)==45
    diagram = Sheet(PROJECT,PROJECT+'.kicad_sch','RP2354B / MC68008 emulator and analyzer',1,libs)
    sheets = [diagram]
    assert set(PLACEMENT)=={p['reference'] for p in circuit}
    for definition in circuit:
        ref = definition['reference']
        props = definition['properties'].copy()
        value = props.pop('Value')
        chosen = catalog.get(definition['catalog_key'])
        if chosen:
            footprint = chosen['Footprint']
            props.update({k:chosen[k] for k in ['Manufacturer','MPN','LCSC','JLCPCB_library',
                         'Assembly','JLCPCB_URL','Verified_date','Selection_reason']})
            props['Source'] = chosen['Datasheet_URL']
        else:
            footprint = props.pop('Footprint','')
            props.update(LCSC='',JLCPCB_library='',JLCPCB_URL='',Verified_date='')
        pins = definition['pins'].copy()
        if ref in ('J1','J2'):
            pins = {r['dip_pin']:r['target_net'] for r in rows}
        if ref=='U1':
            pins.update({r['mcu_qfn_pin']:r['mcu_net'] for r in rows if r['mcu_gpio']})
            pins.update({'56':'MODE_PERMIT','57':'USB_PRESENT_N','58':'PSRAM_CS_N'})
        symbol = definition['symbol']
        part = diagram.symbol(libs.used[symbol],ref,*PLACEMENT[ref],value,footprint,**props)
        diagram.connect(part,pins)
    flags = [(30.48,'+5V'),(58.42,'GND'),(86.36,'+1V1'),(114.3,'VREG_AVDD')]
    for i,(x,net) in enumerate(flags,1):
        part = diagram.symbol(libs.used['PWR_FLAG'],f'#FLG0{i:03d}',x,276.86)
        diagram.connect(part,{'1':net})

    # Short display text leaves full engineering values and metadata in the BOM.
    compact = {'J1':'TOP CPU SOCKET (manual)', 'J2':'MOTHERBOARD PLUG (manual)',
               'J4':'SWD JST-SH: CLK / GND / IO', 'JP1':'ACTIVE PERMIT',
               'L1':'3.3uH'}
    for instance in [n for n in diagram.parts if n[0]=='symbol']:
        properties = {str(p[1]):p for p in children(instance,'property')}
        ref = str(properties['Reference'][2])
        if ref in compact:
            display = child(properties['Value'],'effects')
            if 'hide' not in display: display.append('hide')
            pos = child(properties['Value'],'at')
            text = compact[ref]
            if ref=='JP1':
                child(properties['Reference'],'at')[1:3] = [275.59,269.24]
                diagram.text(text,269.24,273.05,0.9)
            else:
                diagram.text(text,float(pos[1])-7.62,float(pos[2]),0.9)
        if ref.startswith('#FLG'):
            display = child(properties['Value'],'effects')
            if 'hide' not in display: display.append('hide')

    diagram.text('48-pin MC68008 pass-through',12.7,12.7,1.5)
    diagram.text('Five protected inputs',254,12.7,1.5)
    diagram.text('Clock / recovery',254,93.98,1.27)
    diagram.text('C23: one shared J1/J2 bypass capacitor',123.19,136.525,0.85)
    diagram.text('Target 5V / MCU supplies',12.7,153.67,1.27)
    diagram.text('USB-C (target-powered)',267.97,152.4,1.27)
    diagram.text('MCU local decoupling: place at supply pads',12.7,208.28,1.0)
    diagram.text('VBUS presence',198.12,194.31,0.9)
    diagram.text('PIO0: GPIO0-31; PIO1: GPIO16-47. Synchronization pending.\nJ1 pin n = J2 pin n. RESET/HALT: LOW or release only.\nTarget-only power / TTL bus. Mode interlock remains to be completed.',130.81,273.05,0.85)
    # Circuit notes occupy the open area below the MCU, above the supplies.
    diagram.text('BAT54X Vf margin accepted; see simulations/bat54/.\nMODE_PERMIT: GPIO45 permission input, default passive.\nUSB_PRESENT_N: GPIO46 active-low VBUS detection.\nPSRAM_CS_N: GPIO47 QMI CS1; R4 is a 1k pull-up.',130.81,148.59,0.85)
    if not bom_only:
        diagram.save(OUT)
        for old in ['cpu_bus.kicad_sch','mcu.kicad_sch','protected_inputs.kicad_sch','power_usb.kicad_sch']:
            obsolete = OUT/old
            if obsolete.exists(): obsolete.unlink()

    # One row per fitted part, including unresolved connector positions; no invented quotes.
    parts=[p for s in sheets for p in s.components]
    fields=['Reference','Quantity','Value','Footprint','Manufacturer','MPN','LCSC','JLCPCB_library',
            'Assembly','JLCPCB_URL','Verified_date','Selection_reason','Source','Status']
    for p in parts:
        p['Quantity']=1
    unresolved = [dict(Reference=ref, Value=value, Footprint='', Manufacturer='TBD', MPN='TBD',
                       Source='', Status='NOT_IMPLEMENTED_NOT_COSTED',Assembly='Unresolved')
                  for ref,value in [
                      ('TBD_OUTPUT_INTERLOCK','Independent hardware prevention of active drive in passive mode'),
                  ]]
    with (OUT/'BOM.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore',lineterminator='\n');w.writeheader();w.writerows(parts+unresolved)
    groups={}
    for p in parts:
        if p['Assembly']=='JLCPCB_SMT':
            assert p['LCSC'].startswith('C') and p['JLCPCB_library'] in ('Basic','Extended')
            groups.setdefault(p['LCSC'],[]).append(p)
    with (OUT/'BOM_JLCPCB.csv').open('w',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(['Comment','Designator','Footprint','LCSC Part #'])
        for code,instances in sorted(groups.items()):
            w.writerow([instances[0]['MPN'],','.join(p['Reference'] for p in instances),instances[0]['Footprint'],code])
    report=['# JLCPCB selections — through 2026-11-10','',
            'Basic/Extended and SMT assembly were checked on JLCPCB product pages; each catalog entry carries its verification date. Stock and prices must be checked when ordering.',
            'J1/J2 are manual assemblies and JP1 is a PCB feature, excluded from the JLCPCB upload BOM. J4 is a purchased JST-SH SMT connector included in the BOM.',
            'The independent output interlock remains unimplemented and uncosted.','',
            '| LCSC | Library | MPN | Qty | References | Selection rationale |',
            '| --- | --- | --- | --- | --- | --- |']
    for code,instances in sorted(groups.items()):
        p=instances[0]
        report.append(f"| [{code}]({p['JLCPCB_URL']}) | {p['JLCPCB_library']} | {p['MPN']} | {len(instances)} | {', '.join(i['Reference'] for i in instances)} | {p['Selection_reason']} |")
    (OUT/'JLCPCB_parts.md').write_text('\n'.join(report)+'\n')
    gpios=[]
    aux={45:('MODE_PERMIT','input'),46:('USB_PRESENT_N','input'),47:('PSRAM_CS_N','QMI_CS1_output_active_low')}
    auxiliary_notes={45:'JP1 physical active-mode permission; open means passive. Firmware must enforce it; it does not detect CPU presence or gate the pads.',
                     46:'Active-low Q1 VBUS detector, moved from GPIO47 for PSRAM. VBUS remains sense-only; the former BUS_ARM_REQUEST reservation is removed.',
                     47:'PSRAM CS1 active-low chip select for 8 MiB APS6404L; dedicated QSPI clock/data shared with in-package flash. R4 1k pull-up holds deselected at reset; disable the pad pull-down before enabling QMI CS1.'}
    for gpio in range(48):
        r=by_gpio.get(gpio)
        qfn = r['mcu_qfn_pin'] if r else {45:56,46:57,47:58}[gpio]
        gpios.append({'gpio':gpio,'qfn_pin':qfn,'net':r['mcu_net'] if r else aux[gpio][0],
                      'dip_pin':r['dip_pin'] if r else '',
                      'purpose':r['replacement_mcu'] if r else aux[gpio][1],
                      'notes':r.get('notes','') if r else auxiliary_notes[gpio]})
    with (OUT/'rp2354b_gpio.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(gpios[0]),lineterminator='\n');w.writeheader();w.writerows(gpios)
    print(f'Wrote BOMs for {len(parts)} candidate parts and 48 GPIO assignments.' if bom_only
          else f'Wrote one A3 schematic sheet, {len(parts)} candidate parts and 48 GPIO assignments.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--overwrite',action='store_true',help='replace generated single-sheet schematic and BOM')
    mode.add_argument('--bom-only',action='store_true',help='refresh BOMs and GPIO table without replacing the edited schematic')
    args=parser.parse_args()
    if (OUT/(PROJECT+'.kicad_sch')).exists() and not (args.overwrite or args.bom_only):
        parser.error('Existing schematic: review GUI changes before regenerating with --overwrite.')
    build(bom_only=args.bom_only)
