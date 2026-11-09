"""Small standard-library helpers for the reproducible KiCad starter.

Generated schematics remain editable in KiCad; this is not a general CAD API.
"""
import copy
import json
import os
from pathlib import Path
import re
import uuid


class Q(str):
    pass


def parse(text):
    tokens = iter(re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text))

    def value(t):
        if t == '(':
            out = []
            for t in tokens:
                if t == ')':
                    return out
                out.append(value(t))
            raise ValueError('Unclosed expression')
        return Q(json.loads(t)) if t.startswith('"') else t

    return value(next(tokens))


def dump(v, level=0):
    if isinstance(v, list):
        if not any(isinstance(x, list) for x in v):
            return '(' + ' '.join(dump(x) for x in v) + ')'
        return '(' + ''.join(('\n' + '  ' * (level + 1) if isinstance(x, list)
                              else ' ' if i else '') + dump(x, level + 1)
                             for i, x in enumerate(v)) + ')'
    if isinstance(v, Q):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, float):
        return f'{v:.4f}'.rstrip('0').rstrip('.') if v else '0'
    return str(v)


def children(node, key):
    return [n for n in node if isinstance(n, list) and n and n[0] == key]


def child(node, key):
    return next(iter(children(node, key)), None)


def uid(name):
    return str(uuid.uuid5(uuid.UUID('cf633e38-f18c-4923-908d-f8981178b385'), name))


def effects(size=1.0, justify=None, hide=False):
    n = ['effects', ['font', ['size', size, size]]]
    if justify:
        n.append(['justify', *justify.split()])
    if hide:
        n.append('hide')
    return n


def symbol_pins(symbol):
    return [p for sub in children(symbol, 'symbol') for p in children(sub, 'pin')]


def library_dir():
    candidates = [os.environ.get('KICAD_SYMBOL_DIR', ''),
                  '/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols',
                  '/usr/share/kicad/symbols',
                  'C:/Program Files/KiCad/10.0/share/kicad/symbols']
    for path in candidates:
        if path and (Path(path) / 'Device.kicad_sym').is_file():
            return Path(path)
    raise SystemExit('Set KICAD_SYMBOL_DIR to the KiCad 10 symbol directory.')


class Libraries:
    def __init__(self):
        self.cache = {}
        self.used = {}
        self.directory = library_dir()

    def load(self, lib, name):
        if lib not in self.cache:
            root = parse((self.directory / (lib + '.kicad_sym')).read_text())
            self.cache[lib] = {str(s[1]): s for s in children(root, 'symbol')}
        node = copy.deepcopy(self.cache[lib][name])
        ext = child(node, 'extends')
        if ext:
            base = self.load(lib, str(ext[1]))
            old = str(base[1])
            for sub in children(base, 'symbol'):
                sub[1] = Q(str(sub[1]).replace(old + '_', name + '_', 1))
            overridden = {str(p[1]) for p in children(node, 'property')}
            base = [n for n in base if not (isinstance(n, list) and n[0] == 'property'
                                            and str(n[1]) in overridden)]
            base[1] = Q(name)
            base.extend(n for n in node[2:] if n != ext)
            node = base
        return node

    def use(self, lib, name, rename=None, passive=False):
        key = rename or name
        if key not in self.used:
            node = self.load(lib, name)
            node[1] = Q(key)
            for sub in children(node, 'symbol'):
                sub[1] = Q(str(sub[1]).replace(name + '_', key + '_', 1))
            for p in symbol_pins(node):
                if passive:
                    p[1] = 'passive'
            if rename:
                for p in children(node, 'property'):
                    if p[1] == 'Value':
                        p[2] = Q(key)
            self.used[key] = node
        return self.used[key]


class Sheet:
    def __init__(self, project, filename, title, page, libs):
        self.project, self.filename, self.page, self.libs = project, filename, page, libs
        self.uuid = uid(filename)
        self.parts, self.embedded, self.components = [], {}, []
        self.serial = 0
        self.node = ['kicad_sch', ['version', 20250114], ['generator', Q('eeschema')],
                     ['uuid', Q(self.uuid)], ['paper', Q('A3')],
                     ['title_block', ['title', Q(title)], ['date', Q('2026-11-09')],
                      ['rev', Q('0.3 DRAFT')],
                      ['comment', 1, Q('RP2354B / 48-pin MC68008 | NOT FOR FABRICATION')]]]

    def ident(self, name):
        self.serial += 1
        return Q(uid(f'{self.filename}/{name}/{self.serial}'))

    def text(self, text, x, y, size=1.27):
        self.parts.append(['text', Q(text), ['at', x, y, 0], effects(size, 'left top'),
                           ['uuid', self.ident('text')]])

    def wire(self, a, b):
        if a != b:
            self.parts.append(['wire', ['pts', ['xy', *a], ['xy', *b]],
                               ['stroke', ['width', 0], ['type', 'default']],
                               ['uuid', self.ident('wire')]])

    def label(self, net, x, y, angle=0):
        self.parts.append(['label', Q(net),
                           ['at', x, y, angle], effects(0.85, 'left' if angle == 0 else 'right'),
                           ['uuid', self.ident('net')]])

    def symbol(self, base, ref, x, y, value=None, footprint=None, **metadata):
        name = str(base[1]); libid = 'rp2350_ice:' + name
        if libid not in self.embedded:
            self.embedded[libid] = copy.deepcopy(base)
            self.embedded[libid][1] = Q(libid)
        inst = ['symbol', ['lib_id', Q(libid)], ['at', x, y, 0], ['unit', 1],
                ['exclude_from_sim', 'no'], ['in_bom', 'no' if ref.startswith('#') else 'yes'],
                ['on_board', 'no' if ref.startswith('#') else 'yes'], ['dnp', 'no'],
                ['uuid', self.ident(ref)]]
        defaults = {str(p[1]): str(p[2]) for p in children(base, 'property')}
        fields = dict(Reference=ref, Value=value or name,
                      Footprint=defaults.get('Footprint', '') if footprint is None else footprint,
                      Datasheet=metadata.get('Source', defaults.get('Datasheet', '')),
                      **metadata)
        for k, val in fields.items():
            px, py = x, y
            if k in ('Reference', 'Value'):
                py = min([y - float(child(p, 'at')[2]) for p in symbol_pins(base)] + [y]) - (15.24 if k == 'Reference' else 12.7)
                if name in ('R', 'C', 'L'):
                    px, py = x + 3.81, y + (-1.27 if k == 'Reference' else 1.27)
                if ref.startswith('#') and k == 'Value':
                    py = y + 3.81 if name == 'GND' else y - 3.81
            inst.append(['property', Q(k), Q(str(val)), ['at', px, py, 0],
                         effects(1.0, hide=k not in ('Reference', 'Value') or (ref.startswith('#') and k == 'Reference'))])
        for p in symbol_pins(base):
            inst.append(['pin', Q(str(child(p, 'number')[1])), ['uuid', self.ident('pin')]])
        path = '/' + uid(self.project + '.kicad_sch')
        if self.page != 1:
            path += '/' + self.uuid
        inst.append(['instances', ['project', Q(self.project),
                                  ['path', Q(path), ['reference', Q(ref)], ['unit', 1]]]])
        self.parts.append(inst)
        if not ref.startswith('#'):
            self.components.append(fields)
        return {'base': base, 'x': x, 'y': y}

    def connect(self, symbol, mapping, rest_nc=True):
        done = set()
        grouped = set()
        # Join adjacent vertical supply pins before placing a single power symbol.
        for angle in (90, 270):
            for net in ('GND', '+5V', '+3V3', '+1V1'):
                pins = [p for p in symbol_pins(symbol['base'])
                        if int(child(p, 'at')[3]) == angle
                        and mapping.get(str(child(p, 'number')[1])) == net]
                positions = {(symbol['x'] + float(child(p, 'at')[1]),
                              symbol['y'] - float(child(p, 'at')[2])) for p in pins}
                if len(positions) < 2 or len({p[1] for p in positions}) != 1:
                    continue
                yy = next(iter(positions))[1] + (5.08 if angle == 90 else -5.08)
                xs = sorted(x for x, _ in positions)
                for x, y in positions:
                    self.wire((x,y),(x,yy))
                    if x not in (xs[0],xs[-1]):
                        self.parts.append(['junction',['at',x,yy],['diameter',0],
                                           ['color',0,0,0,0],['uuid',self.ident('junction')]])
                self.wire((xs[0],yy),(xs[-1],yy))
                self.symbol(self.libs.use('power',net),f'#PWR{self.page}{self.serial:04d}',xs[0],yy)
                grouped.update(str(child(p,'number')[1]) for p in pins)
        for angle in (0,180):
            pins=[p for p in symbol_pins(symbol['base'])
                  if int(child(p,'at')[3])==angle
                  and mapping.get(str(child(p,'number')[1]))=='GND']
            positions={(symbol['x']+float(child(p,'at')[1]),
                        symbol['y']-float(child(p,'at')[2])) for p in pins}
            if len(positions)>1 and len({p[0] for p in positions})==1:
                xx=next(iter(positions))[0]+(-10.16 if angle==0 else 10.16)
                ys=sorted(y for _,y in positions)
                for x,y in positions:
                    self.wire((x,y),(xx,y))
                    if y != ys[0]:
                        self.parts.append(['junction',['at',xx,y],['diameter',0],
                                           ['color',0,0,0,0],['uuid',self.ident('junction')]])
                self.wire((xx,ys[0]),(xx,ys[-1]+5.08))
                self.symbol(self.libs.use('power','GND'),f'#PWR{self.page}{self.serial:04d}',xx,ys[-1]+5.08)
                grouped.update(str(child(p,'number')[1]) for p in pins)
        for p in symbol_pins(symbol['base']):
            number = str(child(p, 'number')[1]); at = child(p, 'at')
            if number in grouped:
                continue
            x, y = symbol['x'] + float(at[1]), symbol['y'] - float(at[2])
            key = (x, y)
            if key in done:
                continue
            done.add(key)
            if number in mapping:
                angle = int(at[3]); length = 5.08
                if angle in (0,180) and mapping[number] in ('GND','+5V','+3V3','+1V1'):
                    length=10.16
                dx, dy = {0: (-length, 0), 180: (length, 0), 90: (0, length), 270: (0, -length)}[angle]
                net = mapping[number]
                self.wire((x, y), (x + dx, y + dy))
                if net in ('GND', '+5V', '+3V3', '+1V1'):
                    # All supplies and grounds use real KiCad power symbols.
                    self.symbol(self.libs.use('power', net), f'#PWR{self.page}{self.serial:04d}', x + dx, y + dy)
                else:
                    self.label(net, x + dx, y + dy, 0 if angle == 180 else 180 if angle == 0 else 0)
            elif rest_nc and p[1] != 'no_connect':
                self.parts.append(['no_connect', ['at', x, y], ['uuid', self.ident('nc')]])

    def save(self, directory):
        node = self.node + [['lib_symbols', *self.embedded.values()]] + self.parts
        if self.page == 1:
            node.append(['sheet_instances', ['path', Q('/'), ['page', Q('1')]]])
        node.append(['embedded_fonts', 'no'])
        (directory / self.filename).write_text(dump(node) + '\n')
