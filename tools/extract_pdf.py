#!/usr/bin/env python3
"""Haalt de tekst uit een PDF met alleen de standaardbibliotheek.

Nodig omdat poppler (pdftotext) en pypdf in deze omgeving niet beschikbaar zijn.
Pakt de Flate-gecomprimeerde content streams uit en leest de tekstoperatoren
(Tj, TJ) eruit. Goed genoeg om de brieven te lezen; geen volwaardige PDF-parser.

Gebruik:
    python3 tools/extract_pdf.py bronbrieven/uitgewerkt/brief.pdf
"""

import re, sys, zlib

data = open(sys.argv[1], 'rb').read()

# Alle streams uitpakken die met Flate gecomprimeerd zijn.
chunks = []
for m in re.finditer(rb'stream\r?\n', data):
    start = m.end()
    end = data.find(b'endstream', start)
    if end < 0:
        continue
    raw = data[start:end]
    try:
        chunks.append(zlib.decompress(raw))
    except zlib.error:
        try:
            chunks.append(zlib.decompressobj().decompress(raw))
        except Exception:
            pass

def unescape(s):
    out = bytearray(); i = 0
    while i < len(s):
        c = s[i]
        if c == 0x5c and i + 1 < len(s):
            n = s[i+1]
            mapping = {0x6e:10, 0x72:13, 0x74:9, 0x62:8, 0x66:12}
            if n in mapping: out.append(mapping[n]); i += 2; continue
            if 0x30 <= n <= 0x37:
                j = i + 1; oct_ = b''
                while j < len(s) and len(oct_) < 3 and 0x30 <= s[j] <= 0x37:
                    oct_ += bytes([s[j]]); j += 1
                out.append(int(oct_, 8) & 0xFF); i = j; continue
            out.append(n); i += 2; continue
        out.append(c); i += 1
    return bytes(out)

TEXT_OPS = re.compile(rb"""
    \((?P<lit>(?:\\.|[^\\()]|\((?:\\.|[^\\()])*\))*)\)\s*(?P<op1>Tj|TJ|'|")
  | <(?P<hex>[0-9A-Fa-f\s]*)>\s*(?P<op2>Tj|TJ)
  | \[(?P<arr>(?:[^\[\]\\]|\\.)*)\]\s*TJ
  | (?P<td>T\*|Td|TD|TL)
""", re.X | re.S)

ARR_LIT = re.compile(rb'\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>|-?[\d.]+')

for chunk in chunks:
    if b'Tj' not in chunk and b'TJ' not in chunk:
        continue
    line = []
    for m in TEXT_OPS.finditer(chunk):
        if m.group('td'):
            if line:
                print(''.join(line).rstrip()); line = []
            continue
        if m.group('lit') is not None:
            line.append(unescape(m.group('lit')).decode('latin-1'))
        elif m.group('hex') is not None:
            h = re.sub(rb'\s', b'', m.group('hex'))
            if len(h) % 2: h += b'0'
            line.append(bytes.fromhex(h.decode()).decode('latin-1'))
        elif m.group('arr') is not None:
            for tok in ARR_LIT.finditer(m.group('arr')):
                t = tok.group(0)
                if t.startswith(b'('):
                    line.append(unescape(t[1:-1]).decode('latin-1'))
                elif t.startswith(b'<'):
                    h = re.sub(rb'\s', b'', t[1:-1])
                    if len(h) % 2: h += b'0'
                    line.append(bytes.fromhex(h.decode()).decode('latin-1'))
                else:
                    try:
                        if float(t) < -150: line.append(' ')
                    except ValueError:
                        pass
    if line:
        print(''.join(line).rstrip())
