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

    # Register definitions: #define NAME 0xXXXX
    reg_pattern = re.compile(r'^\s*#define\s+([A-Z0-9_]+)\s+(0x[0-9A-Fa-f]+)\s*$', re.MULTILINE)
    for match in reg_pattern.finditer(content):
        name = match.group(1)
        addr_str = match.group(2)
        # Skip register names that are actually bitfield masks/shifts (they contain MASK/SHIFT)
        if '_MASK' in name or '_SHIFT' in name:
            continue
        addr = int(addr_str, 16)
        regs[name] = addr

    # Mask and shift definitions
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
            # shift without corresponding mask? still store, mask unknown
            field_defs[base] = {'mask': None, 'shift': shift_val}

    return regs, field_defs

def parse_c_source(content: str, regs: Dict, field_defs: Dict) -> Dict:
    """
    Parse upmu_common.c content to find register accesses.
    Returns:
        access_map: dict { register_name: { field_name: {'mask': int, 'shift': int, 'access': str} } }
    """
    access_map = {}

    # Helper to extract macro name from (U32)(MACRO) pattern
    def extract_macro(text, pos):
        # Simple: look for word characters after last '('
        match = re.search(r'\(U32\)\s*\((\w+)\)', text[pos:])
        if match:
            return match.group(1), match.end()
        return None, pos

    # Pattern to find function calls (simplified: find lines with pmic_read_interface or pmic_config_interface)
    # We'll use regex to capture register macro, mask macro, shift macro.
    # For read: pmic_read_interface( (U32)(REG), (&val), (U32)(MASK), (U32)(SHIFT) )
    read_pattern = re.compile(
        r'pmic_read_interface\s*\(\s*\(U32\)\s*\((\w+)\)\s*,\s*\(&\w+\)\s*,\s*\(U32\)\s*\((\w+)\)\s*,\s*\(U32\)\s*\((\w+)\)\s*\)',
        re.DOTALL
    )
    # For write: pmic_config_interface( (U32)(REG), (U32)(val), (U32)(MASK), (U32)(SHIFT) )
    write_pattern = re.compile(
        r'pmic_config_interface\s*\(\s*\(U32\)\s*\((\w+)\)\s*,\s*\(U32\)[^,]+,\s*\(U32\)\s*\((\w+)\)\s*,\s*\(U32\)\s*\((\w+)\)\s*\)',
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
        else:
            # Try to get shift from shift_macro directly if it ends with _SHIFT
            if shift_macro.endswith('_SHIFT') and shift_macro[:-6] == field_base:
                # field_defs might have missing, we can try to parse later, but here we skip
                pass

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
