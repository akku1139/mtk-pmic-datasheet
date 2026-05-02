#!/usr/bin/env python3
"""
Convert MT6320 PMIC register map JSON to bit-field HTML tables.

Usage: python json2bitmap.py register_map.json > register_map_bitview.html
"""

import json
import sys
import html
from math import floor, log2

def get_bit_range(mask: int, shift: int) -> tuple:
    """
    Given mask and shift, return (lsb, msb) inclusive.
    mask is a positive integer, shift is LSB position.
    """
    if mask == 0:
        return (shift, shift)
    width = mask.bit_length()
    return (shift, shift + width - 1)

def build_bitmap(fields, bits=16):
    """
    Build arrays for bits [bits-1 .. 0] containing field info.
    Returns:
        bit_fields: list of length bits, each a dict with 'name', 'type', 'reset', 'span'
        Also returns list of unique fields with start/end/name/type to generate colspan rows.
    """
    bit_fields = [None] * bits  # index 0 = LSB (bit0), but we will later reverse for display
    field_list = []  # list of (name, type, reset, start, end, mask)

    for fname, info in fields.items():
        mask_str = info.get('mask', '?')
        shift_val = info.get('shift')
        access = info.get('access', '')
        if mask_str == '?':
            continue
        try:
            mask = int(mask_str, 16) if isinstance(mask_str, str) and mask_str.startswith('0x') else int(mask_str)
        except:
            continue
        if shift_val == '?' or shift_val is None:
            continue
        shift = int(shift_val)
        lsb, msb = get_bit_range(mask, shift)
        if msb >= bits:
            msb = bits - 1  # clamp
        # Type string
        if access == 'read':
            rw = 'R'
        elif access == 'write':
            rw = 'W'
        elif 'read' in access and 'write' in access:
            rw = 'R/W'
        else:
            rw = '?'
        field_list.append((fname, rw, '?', lsb, msb, mask))
        # Fill each bit position
        for b in range(lsb, msb+1):
            if b < bits:
                if bit_fields[b] is None:
                    bit_fields[b] = {'name': fname, 'type': rw, 'reset': '?', 'start': lsb, 'end': msb}
                else:
                    # Overlap? Should not happen, but keep first
                    pass
    # For bits not covered, mark as reserved
    for b in range(bits):
        if bit_fields[b] is None:
            bit_fields[b] = {'name': 'Reserved', 'type': '-', 'reset': '-', 'start': b, 'end': b}
            # Also add to field_list as dummy for colspan? better handle in rendering
    # To avoid duplicate fields for same contiguous region in bit_fields, we will generate field_list sorted by msb descending
    # Consolidate fields: merge adjacent same name? Not necessary, each field has its own span.
    # But bit_fields already has per-bit info; for table we want one row per distinct field spanning its bits.
    unique_fields = {}
    for f in field_list:
        key = (f[0], f[1], f[2], f[3], f[4])
        if key not in unique_fields:
            unique_fields[key] = f
    # Add reserved fields not present in field_list (bits not covered) - but we already filled bit_fields with reserved per bit.
    # To get reserved spans, we can group consecutive bits with same name 'Reserved' in bit_fields when rendering.
    # Simpler: In rendering, we will use bit_fields to generate the name row with colspan per continuous segment.
    # Let's return bit_fields and also the grouped segments.
    segments = []
    i = 0
    while i < bits:
        curr = bit_fields[i]
        start = i
        while i < bits and bit_fields[i]['name'] == curr['name'] and bit_fields[i]['type'] == curr['type'] and bit_fields[i]['reset'] == curr['reset']:
            i += 1
        end = i - 1
        segments.append({
            'name': curr['name'],
            'type': curr['type'],
            'reset': curr['reset'],
            'start': start,
            'end': end,
            'width': end - start + 1
        })
    # segements now ordered LSB to MSB. For display (MSB to LSB) we need reverse order.
    return bit_fields, segments

def generate_html_for_register(reg_name, reg_info):
    """Generate HTML table for a single register."""
    addr = reg_info.get('address', '?')
    fields = reg_info.get('fields', {})
    bits = 16  # assume 16-bit registers
    bit_fields, segments = build_bitmap(fields, bits)

    # Build table rows
    # Row 1: Bit numbers (MSB to LSB)
    bit_header_cells = []
    for b in range(bits-1, -1, -1):
        bit_header_cells.append(f'<th class="bit-num">{b}</th>')
    bit_row = f'<tr class="bit-row"><th class="bit-label">Bit</th>{"".join(bit_header_cells)}</tr>'

    # Row 2: Field names (with colspan)
    # segments are from LSB to MSB, we need MSB to LSB
    segments_rev = list(reversed(segments))
    name_cells = []
    for seg in segments_rev:
        width = seg['width']
        name = html.escape(seg['name'])
        colspan = width
        name_cells.append(f'<td colspan="{colspan}" class="field-name-cell">{name}</td>')
    name_row = f'<tr class="field-name-row"><th class="field-label">Name</th>{"".join(name_cells)}</tr>'

    # Row 3: Type (R/W/R/W/ etc)
    type_cells = []
    for seg in segments_rev:
        width = seg['width']
        typ = html.escape(seg['type'])
        type_cells.append(f'<td colspan="{width}" class="field-type-cell">{typ}</td>')
    type_row = f'<tr class="field-type-row"><th class="field-label">Type</th>{"".join(type_cells)}</tr>'

    # Row 4: Reset value (all '?' for now)
    reset_cells = []
    for seg in segments_rev:
        width = seg['width']
        reset_val = seg['reset']
        reset_cells.append(f'<td colspan="{width}" class="field-reset-cell">{reset_val}</td>')
    reset_row = f'<tr class="field-reset-row"><th class="field-label">Reset</th>{"".join(reset_cells)}</tr>'

    # Build register description block
    reg_desc = f"<span class='reg-addr'>Address: {addr}</span>"
    # optionally add description if available (none in JSON)
    title = f"""
    <div class="register-title">
        <h3>{html.escape(reg_name)}</h3>
        <div class="reg-desc">{reg_desc}</div>
    </div>
    """
    table = f"""
    <div class="register-container">
        {title}
        <table class="bitfield-table">
            {bit_row}
            {name_row}
            {type_row}
            {reset_row}
        </table>
    </div>
    """
    return table

def generate_html(register_map):
    """Full HTML page."""
    css = """
    <style>
        body {
            font-family: 'Segoe UI', 'Courier New', monospace;
            margin: 20px;
            background-color: #f0f0f0;
        }
        h1 {
            color: #2c3e50;
        }
        .summary {
            background: #fff;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .register-container {
            background: white;
            margin-bottom: 30px;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            break-inside: avoid;
            page-break-inside: avoid;
        }
        .register-title h3 {
            margin: 0 0 5px 0;
            color: #2980b9;
        }
        .reg-desc {
            font-size: 0.9em;
            color: #555;
            margin-bottom: 10px;
        }
        table.bitfield-table {
            border-collapse: collapse;
            width: auto;
            min-width: 100%;
            font-size: 0.9em;
        }
        .bitfield-table th, .bitfield-table td {
            border: 1px solid #aaa;
            text-align: center;
            vertical-align: middle;
            padding: 4px 2px;
        }
        .bit-row th {
            background-color: #34495e;
            color: white;
            font-weight: normal;
        }
        .bit-label, .field-label {
            background-color: #ecf0f1;
            font-weight: bold;
            width: 60px;
        }
        .field-name-cell {
            background-color: #d9eaf7;
            font-weight: bold;
            font-family: monospace;
        }
        .field-type-cell {
            background-color: #f9e79f;
        }
        .field-reset-cell {
            background-color: #f5cba7;
        }
        .bit-num {
            background-color: #5d6d7e;
            font-family: monospace;
        }
        @media print {
            body {
                margin: 0;
                background: white;
            }
            .register-container {
                break-inside: avoid;
                box-shadow: none;
            }
        }
    </style>
    """
    regs = register_map.get('registers', {})
    summary = register_map.get('summary', {})
    tables = []
    for reg_name, reg_info in sorted(regs.items(), key=lambda x: int(x[1]['address'], 16)):
        tables.append(generate_html_for_register(reg_name, reg_info))

    full = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>MT6320 PMIC Register Bitmap View</title>
{css}
</head>
<body>
    <h1>MT6320 PMIC Register Map (Bitfield View)</h1>
    <div class="summary">
        <strong>Summary:</strong> Total registers: {summary.get('total_registers', 0)},
        Total fields with access: {summary.get('total_fields', 0)}<br>
        <em>Note: Reset values are not available from source, shown as '?'. Reserved bits are indicated.</em>
    </div>
    {''.join(tables)}
</body>
</html>
"""
    return full

def main():
    if len(sys.argv) != 2:
        print("Usage: python json2bitmap.py <register_map.json>")
        sys.exit(1)

    json_file = sys.argv[1]
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    html_output = generate_html(data)
    print(html_output)

if __name__ == '__main__':
    main()
