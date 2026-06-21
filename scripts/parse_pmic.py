#!/usr/bin/env python3
"""
MT6320 PMIC Register Map Parser

Reads upmu_hw.h and upmu_common.c, extracts register addresses,
bitfield definitions, and access functions to produce a JSON register map.
"""

import re
import sys
import json
from typing import Dict

def parse_hw_header(content: str) -> tuple:
    """
    Parse upmu_hw.h content.
    Returns:
        regs: dict { register_name: address_int }
        field_defs: dict { field_name (base): {'mask': int, 'shift': int} }
    """
    regs = {}
    field_defs = {}

    # 登録されたマクロとその数値を一時的に保持する辞書（ベースアドレス解決用）
    macro_map = {}

    # レジスタ定義: #define NAME VALUE (キャストやカッコ、末尾コメントを考慮して幅広くマッチ)
    reg_pattern = re.compile(r'^\s*#define\s+([A-Z0-9_]+)\s+(.+?)\s*(?://.*)?$', re.MULTILINE)

    for match in reg_pattern.finditer(content):
        name = match.group(1)
        value_str = match.group(2).strip()

        # マスクやシフトの定義はここではスキップ
        if '_MASK' in name or '_SHIFT' in name:
            continue

        # 1) 値の文字列から16進数（0xXXXX）をすべて抽出して数値化
        hex_values = [int(x, 16) for x in re.findall(r'0x[0-9A-Fa-f]+', value_str)]

        # 2) 既に解析済みのマクロ（PMIC_REG_BASEなど）が値に含まれているか確認
        base_val = 0
        for m_name, m_val in macro_map.items():
            if m_name in value_str:
                base_val = m_val
                break

        # 3) ベースアドレスと抽出したオフセット値を足し合わせる
        if hex_values:
            actual_val = base_val + sum(hex_values)
            regs[name] = actual_val
            macro_map[name] = actual_val  # 次の行以降でマクロとして使われる可能性に備える

    # Mask and shift definitions (従来通り)
    mask_pattern = re.compile(r'^\s*#define\s+([A-Z0-9_]+)_MASK\s+(0x[0-9A-Fa-f]+)\s*$', re.MULTILINE)
    shift_pattern = re.compile(r'^\s*#define\s+([A-Z0-9_]+)_SHIFT\s+(\d+)\s*$', re.MULTILINE)

    # First collect masks
    masks = {}
    for match in mask_pattern.finditer(content):
        base = match.group(1)
        mask_val = int(match.group(2), 16)
        masks[base] = mask_val

    # Then collect shifts and combine
    for match in shift_pattern.finditer(content):
        base = match.group(1)
        shift_val = int(match.group(2))
        if base in masks:
            field_defs[base] = {'mask': masks[base], 'shift': shift_val}
        else:
            field_defs[base] = {'mask': None, 'shift': shift_val}

    return regs, field_defs

def parse_c_source(content: str, regs: Dict, field_defs: Dict) -> Dict:
    """
    Parse upmu_common.c content to find register accesses.
    Returns:
        access_map: dict { register_name: { field_name: {'mask': int, 'shift': int, 'access': str} } }
    """
    access_map = {}

    # キャストの型（U32 や kal_uint32 など）を柔軟にマッチさせるための正規表現パーツ
    # 例: (U32) や (kal_uint32) にマッチ
    cast_pattern = r'\([\w\s]+\)'

    # For read: pmic_read_interface( (型)(REG), (&val), (型)(MASK), (型)(SHIFT) )
    read_pattern = re.compile(
        r'pmic_read_interface\s*\(\s*' + cast_pattern + r'\s*\((\w+)\)\s*,\s*'
        r'\(&\w+\)\s*,\s*'
        + cast_pattern + r'\s*\((\w+)\)\s*,\s*'
        + cast_pattern + r'\s*\((\w+)\)\s*\)',
        re.DOTALL
    )

    # For write: pmic_config_interface( (型)(REG), (型)(val), (型)(MASK), (型)(SHIFT) )
    write_pattern = re.compile(
        r'pmic_config_interface\s*\(\s*' + cast_pattern + r'\s*\((\w+)\)\s*,\s*'
        + cast_pattern + r'[^,]+,\s*'
        + cast_pattern + r'\s*\((\w+)\)\s*,\s*'
        + cast_pattern + r'\s*\((\w+)\)\s*\)',
        re.DOTALL
    )

    # Process read accesses
    for match in read_pattern.finditer(content):
        reg_macro = match.group(1)
        mask_macro = match.group(2)
        shift_macro = match.group(3)

        if reg_macro not in regs:
            continue  # unknown register

        # Derive field base name from mask macro (strip _MASK)
        if mask_macro.endswith('_MASK'):
            field_base = mask_macro[:-5]
        else:
            field_base = mask_macro  # fallback

        # Get numeric values from field_defs if available
        mask_val = None
        shift_val = None
        if field_base in field_defs:
            mask_val = field_defs[field_base].get('mask')
            shift_val = field_defs[field_base].get('shift')

        reg_name = reg_macro
        if reg_name not in access_map:
            access_map[reg_name] = {}
        field_info = access_map[reg_name].get(field_base, {'mask': mask_val, 'shift': shift_val, 'access': ''})

        # Update access type
        if 'read' not in field_info['access']:
            field_info['access'] += 'read'
        access_map[reg_name][field_base] = field_info

    # Process write accesses
    for match in write_pattern.finditer(content):
        reg_macro = match.group(1)
        mask_macro = match.group(2)
        shift_macro = match.group(3)

        if reg_macro not in regs:
            continue

        if mask_macro.endswith('_MASK'):
            field_base = mask_macro[:-5]
        else:
            field_base = mask_macro

        reg_name = reg_macro
        if reg_name not in access_map:
            access_map[reg_name] = {}
        field_info = access_map[reg_name].get(field_base, {'mask': None, 'shift': None, 'access': ''})

        if 'write' not in field_info['access']:
            field_info['access'] += 'write'

        # Update mask/shift if not already set
        if field_info['mask'] is None and field_base in field_defs:
            field_info['mask'] = field_defs[field_base].get('mask')
            field_info['shift'] = field_defs[field_base].get('shift')
        access_map[reg_name][field_base] = field_info

    return access_map

def build_register_map(regs: Dict, access_map: Dict) -> Dict:
    """
    Combine register addresses and field access information into final JSON structure.
    """
    result = {
        "registers": {},
        "summary": {
            "total_registers": len(regs),
            "total_fields": 0
        }
    }
    field_count = 0
    for reg_name, addr in regs.items():
        reg_entry = {
            "address": f"0x{addr:04X}",
            "fields": {}
        }
        if reg_name in access_map:
            for field_name, info in access_map[reg_name].items():
                reg_entry["fields"][field_name] = {
                    "mask": f"0x{info['mask']:X}" if info['mask'] is not None else "?",
                    "shift": info['shift'] if info['shift'] is not None else "?",
                    "access": info['access']
                }
                field_count += 1
        result["registers"][reg_name] = reg_entry

    result["summary"]["total_fields"] = field_count
    return result

def main():
    if len(sys.argv) != 3:
        print("Usage: python parse_pmic.py upmu_hw.h upmu_common.c")
        sys.exit(1)

    hw_file = sys.argv[1]
    c_file = sys.argv[2]

    try:
        with open(hw_file, 'r', encoding='utf-8', errors='ignore') as f:
            hw_content = f.read()
        with open(c_file, 'r', encoding='utf-8', errors='ignore') as f:
            c_content = f.read()
    except Exception as e:
        print(f"Error reading files: {e}")
        sys.exit(1)

    regs, field_defs = parse_hw_header(hw_content)
    access_map = parse_c_source(c_content, regs, field_defs)
    register_map = build_register_map(regs, access_map)

    print(json.dumps(register_map, indent=2))

if __name__ == "__main__":
    main()
