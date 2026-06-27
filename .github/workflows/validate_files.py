#!/usr/bin/env python3
"""
CDM File Format Validator (validate_files.py)
Validates taxizones.txt, rate.txt, SidInterval.txt, CTOT.txt, slots.txt, and cad.txt
against their expected schemas.

Exits 0 on success, 1 on validation errors.
Writes errors.json to the working directory for use by the GitHub Actions workflow.
"""

import re
import sys
import os
import glob
import json
from pathlib import Path

# Structured error records: {filepath, lineno, original_line, message}
error_records = []
warnings = []


def error(filepath, lineno, msg, original_line=""):
    error_records.append({
        "file": filepath,
        "line": lineno,
        "original": original_line,
        "message": msg,
    })
    print(f"  ❌ Line {lineno}: {msg}")
    # GitHub Actions annotation
    print(f"::error file={filepath},line={lineno}::{msg}")


def warn(filepath, lineno, msg):
    warnings.append(f"::warning file={filepath},line={lineno}::{msg}")
    print(f"  ⚠️  Line {lineno}: {msg}")
    print(f"::warning file={filepath},line={lineno}::{msg}")


def read_lines(filepath):
    """Read non-empty, non-comment lines with their original line numbers."""
    lines = []
    with open(filepath, encoding="utf-8") as f:
        for i, raw in enumerate(f, start=1):
            stripped = raw.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith(";"):
                lines.append((i, stripped))
    return lines


def read_all_lines(filepath):
    """Read ALL lines (including blank/comment) for PR patch generation."""
    with open(filepath, encoding="utf-8") as f:
        return f.readlines()


# ---------------------------------------------------------------------------
# taxizones.txt
# AIRPORT:RUNWAY:BL_LAT:BL_LON:TL_LAT:TL_LON:TR_LAT:TR_LON:BR_LAT:BR_LON:TAXITIME[:REM1,REM2,REM3,REM4,REM5[:EVENT_EXTRA_TIME]]
# ---------------------------------------------------------------------------
LAT_RE  = re.compile(r"^-?\d+(\.\d+)?$")
ICAO_RE = re.compile(r"^[A-Z]{4}$")
RWY_RE  = re.compile(r"^\d{2}[LCR]?$")


def validate_taxizones(filepath):
    print(f"\n📄 Validating {filepath}")
    lines = read_lines(filepath)
    if not lines:
        warn(filepath, 0, "File is empty")
        return

    for lineno, line in lines:
        parts = line.split(":")

        if len(parts) not in (11, 12, 13):
            error(filepath, lineno,
                  f"Expected 11–13 colon-separated fields, got {len(parts)}: {line!r}",
                  line)
            continue

        airport, runway = parts[0], parts[1]
        coords = parts[2:10]
        taxitime_str = parts[10]

        if not ICAO_RE.match(airport):
            error(filepath, lineno,
                  f"AIRPORT '{airport}' is not a valid 4-letter ICAO code", line)

        if not RWY_RE.match(runway):
            error(filepath, lineno,
                  f"RUNWAY '{runway}' does not match expected pattern (e.g. 25L, 09, 36R)", line)

        labels = ["BL_LAT","BL_LON","TL_LAT","TL_LON","TR_LAT","TR_LON","BR_LAT","BR_LON"]
        for idx, coord in enumerate(coords):
            if not LAT_RE.match(coord):
                error(filepath, lineno,
                      f"Coordinate field {labels[idx]} '{coord}' is not a valid decimal number", line)

        try:
            tt = int(taxitime_str)
            if tt <= 0:
                error(filepath, lineno,
                      f"TAXITIME '{taxitime_str}' must be a positive integer", line)
        except ValueError:
            error(filepath, lineno,
                  f"TAXITIME '{taxitime_str}' is not an integer", line)

        if len(parts) >= 12:
            deice_vals = parts[11].split(",")
            if len(deice_vals) != 5:
                error(filepath, lineno,
                      f"De-ice field must have exactly 5 comma-separated values (REM1–REM5), "
                      f"got {len(deice_vals)}: {parts[11]!r}", line)
            for v in deice_vals:
                try:
                    int(v)
                except ValueError:
                    error(filepath, lineno, f"De-ice value '{v}' is not an integer", line)

        if len(parts) == 13:
            try:
                int(parts[12])
            except ValueError:
                error(filepath, lineno,
                      f"EVENT_EXTRA_TIME '{parts[12]}' is not an integer", line)

    print(f"  ✅ {len(lines)} data line(s) checked")


# ---------------------------------------------------------------------------
# rate.txt
# AIRPORT:A:ArrRwyList:NotArrRwyList:D:DepRwyList:NotDepRwyList:DependentRwyList:Rate_RateLvo
# ---------------------------------------------------------------------------
RWY_LIST_RE = re.compile(r"^(\*|(\d{2}[LCR]?)(,\d{2}[LCR]?)*)$")
RATE_RE     = re.compile(r"^\d+_\d+$")


def validate_runway_list(filepath, lineno, value, field_name, line):
    if not RWY_LIST_RE.match(value):
        error(filepath, lineno,
              f"{field_name} '{value}' is invalid (use runway IDs like 24L or * to disregard)", line)


def validate_rate(filepath, lineno, value, line):
    for p in value.split(","):
        if not RATE_RE.match(p):
            error(filepath, lineno,
                  f"Rate '{p}' must be in format RATE_RATELVO (e.g. 30_12)", line)


def validate_rate_txt(filepath):
    print(f"\n📄 Validating {filepath}")
    lines = read_lines(filepath)
    if not lines:
        warn(filepath, 0, "File is empty")
        return

    for lineno, line in lines:
        parts = line.split(":")
        if len(parts) != 9:
            error(filepath, lineno,
                  f"Expected exactly 9 colon-separated fields, got {len(parts)}: {line!r}", line)
            continue

        airport, a_lit, arr_rwy, not_arr, d_lit, dep_rwy, not_dep, dep_rwy_list, rate = parts

        if not ICAO_RE.match(airport):
            error(filepath, lineno,
                  f"AIRPORT '{airport}' is not a valid 4-letter ICAO code", line)
        if a_lit != "A":
            error(filepath, lineno, f"Expected literal 'A' in field 2, got '{a_lit}'", line)

        validate_runway_list(filepath, lineno, arr_rwy,      "ArrRwyList",      line)
        validate_runway_list(filepath, lineno, not_arr,      "NotArrRwyList",   line)

        if d_lit != "D":
            error(filepath, lineno, f"Expected literal 'D' in field 5, got '{d_lit}'", line)

        validate_runway_list(filepath, lineno, dep_rwy,      "DepRwyList",      line)
        validate_runway_list(filepath, lineno, not_dep,      "NotDepRwyList",   line)
        validate_runway_list(filepath, lineno, dep_rwy_list, "DependentRwyList",line)
        validate_rate(filepath, lineno, rate, line)

    print(f"  ✅ {len(lines)} data line(s) checked")


# ---------------------------------------------------------------------------
# SidInterval.txt
# Option 1: ICAO,dep_rwy,SID1,SID2,sep_minutes
# Option 2: ICAO,dep_rwy1,SID1,dep_rwy2,SID2,sep_minutes
# ---------------------------------------------------------------------------
SID_RE = re.compile(r"^[A-Z]{3,5}$")
SEP_RE = re.compile(r"^\d+(\.\d+)?$")


def validate_sid_interval(filepath):
    print(f"\n📄 Validating {filepath}")
    lines = read_lines(filepath)
    if not lines:
        warn(filepath, 0, "File is empty")
        return

    for lineno, line in lines:
        parts = line.split(",")

        if len(parts) not in (5, 6):
            error(filepath, lineno,
                  f"Expected 5 or 6 comma-separated fields, got {len(parts)}: {line!r}", line)
            continue

        airport = parts[0]
        if not ICAO_RE.match(airport):
            error(filepath, lineno,
                  f"AIRPORT '{airport}' is not a valid 4-letter ICAO code", line)

        if len(parts) == 5:
            _, rwy, sid1, sid2, sep = parts
            if not RWY_RE.match(rwy):
                error(filepath, lineno, f"RUNWAY '{rwy}' does not match expected pattern", line)
            if not SID_RE.match(sid1):
                error(filepath, lineno,
                      f"SID1 '{sid1}' must be 3–5 uppercase letters (fix only, e.g. LARPA not LARPA4Q)", line)
            if not SID_RE.match(sid2):
                error(filepath, lineno, f"SID2 '{sid2}' must be 3–5 uppercase letters", line)
            if not SEP_RE.match(sep):
                error(filepath, lineno, f"Separation '{sep}' must be a positive decimal number", line)
        else:
            _, rwy1, sid1, rwy2, sid2, sep = parts
            for rwy, label in ((rwy1, "dep_rwy1"), (rwy2, "dep_rwy2")):
                if not RWY_RE.match(rwy):
                    error(filepath, lineno,
                          f"{label} '{rwy}' does not match expected runway pattern", line)
            for sid, label in ((sid1, "SID1"), (sid2, "SID2")):
                if not SID_RE.match(sid):
                    error(filepath, lineno,
                          f"{label} '{sid}' must be 3–5 uppercase letters", line)
            if not SEP_RE.match(sep):
                error(filepath, lineno, f"Separation '{sep}' must be a positive decimal number", line)

    print(f"  ✅ {len(lines)} data line(s) checked")


# ---------------------------------------------------------------------------
# CTOT.txt / slots.txt  — Event SLOTs
#
#   <cid>,<slot>                                      — 2 fields
#   <cid>,<callsign>,<slot>                           — 3 fields
#   <cid>,<callsign>,<departure>,<destination>,<slot>  — 5 fields
# ---------------------------------------------------------------------------
CID_RE      = re.compile(r"^\d{7}$")
CALLSIGN_RE = re.compile(r"^[A-Z0-9]{3,7}$")
SLOT_RE     = re.compile(r"^([01]\d|2[0-3])[0-5]\d$")


def validate_slot_fields(filepath, lineno, parts, line):
    n = len(parts)
    cid = parts[0]
    if not CID_RE.match(cid):
        error(filepath, lineno, f"CID '{cid}' must be a 7-digit integer (VATSIM CID)", line)

    if n == 2:
        if not SLOT_RE.match(parts[1]):
            error(filepath, lineno,
                  f"SLOT '{parts[1]}' must be a 4-digit HHMM time (0000–2359)", line)
    elif n == 3:
        if not CALLSIGN_RE.match(parts[1]):
            error(filepath, lineno,
                  f"Callsign '{parts[1]}' must be 3–7 uppercase alphanumeric characters", line)
        if not SLOT_RE.match(parts[2]):
            error(filepath, lineno,
                  f"SLOT '{parts[2]}' must be a 4-digit HHMM time (0000–2359)", line)
    elif n == 5:
        callsign, departure, destination, slot = parts[1], parts[2], parts[3], parts[4]
        if not CALLSIGN_RE.match(callsign):
            error(filepath, lineno,
                  f"Callsign '{callsign}' must be 3–7 uppercase alphanumeric characters", line)
        if not ICAO_RE.match(departure):
            error(filepath, lineno,
                  f"Departure '{departure}' is not a valid 4-letter ICAO code", line)
        if not ICAO_RE.match(destination):
            error(filepath, lineno,
                  f"Destination '{destination}' is not a valid 4-letter ICAO code", line)
        if not SLOT_RE.match(slot):
            error(filepath, lineno,
                  f"SLOT '{slot}' must be a 4-digit HHMM time (0000–2359)", line)
    else:
        error(filepath, lineno,
              f"Expected 2, 3, or 5 comma-separated fields, got {n} — "
              f"valid formats: <cid>,<slot> | <cid>,<callsign>,<slot> | "
              f"<cid>,<callsign>,<dep>,<dest>,<slot>", line)


def validate_slots(filepath):
    print(f"\n📄 Validating {filepath}")
    lines = read_lines(filepath)
    if not lines:
        warn(filepath, 0, "File is empty — no slot entries found")
        return
    for lineno, line in lines:
        validate_slot_fields(filepath, lineno, line.split(","), line)
    print(f"  ✅ {len(lines)} slot line(s) checked")


# ---------------------------------------------------------------------------
# cad.txt — schema TBD; check non-empty
# ---------------------------------------------------------------------------
def validate_cad(filepath):
    print(f"\n📄 Validating {filepath}")
    lines = read_lines(filepath)
    if not lines:
        warn(filepath, 0, "cad.txt is empty")
        return
    print(f"  ✅ {len(lines)} data line(s) present (structure check skipped — schema unknown)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
VALIDATORS = {
    "taxizones.txt":   validate_taxizones,
    "rate.txt":        validate_rate_txt,
    "SidInterval.txt": validate_sid_interval,
    "CTOT.txt":        validate_slots,
    "slots.txt":       validate_slots,
    "cad.txt":         validate_cad,
}


def main():
    target_files = sys.argv[1:] if len(sys.argv) > 1 else []

    if not target_files:
        for name in VALIDATORS:
            target_files.extend(glob.glob(f"**/{name}", recursive=True))

    if not target_files:
        print("No CDM files found to validate.")
        sys.exit(0)

    for filepath in sorted(target_files):
        if not os.path.isfile(filepath):
            print(f"⚠️  File not found: {filepath}")
            continue
        basename = Path(filepath).name
        validator = VALIDATORS.get(basename)
        if validator:
            validator(filepath)
        else:
            print(f"⚠️  No validator registered for '{basename}' — skipping")

    print("\n" + "=" * 60)

    # Write structured report for the workflow to consume
    report = {
        "error_count": len(error_records),
        "warning_count": len(warnings),
        "errors": error_records,
    }
    with open("errors.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    if error_records:
        print(f"\n❌ Validation FAILED — {len(error_records)} error(s), {len(warnings)} warning(s)")
        sys.exit(1)
    elif warnings:
        print(f"\n⚠️  Validation passed with {len(warnings)} warning(s)")
        sys.exit(0)
    else:
        print(f"\n✅ All files passed validation!")
        sys.exit(0)


if __name__ == "__main__":
    main()