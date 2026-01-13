#!/usr/bin/env python3
"""
R-01 Synthetic NDJSON Writer Fixture
Generates monotonic NDJSON log lines with configurable rotation strategies
to validate file-tailing reliability.
"""

import argparse
import json
import os
import shutil
import time
import sys

def write_manifest(args, total_lines):
    manifest = {
        "expected_seq_start": 1,
        "expected_seq_end": total_lines,
        "expected_total": total_lines,
        "config": {
            "rotation_mode": args.rotation_mode,
            "rotate_every_bytes": args.rotate_every_bytes,
            "flush": args.flush
        }
    }
    with open(args.manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)

def rotate(log_path, mode, backup_index):
    backup_path = f"{log_path}.{backup_index}"
    
    if mode == 'rename_create':
        if os.path.exists(log_path):
            os.rename(log_path, backup_path)
            # Create new empty file immediately
            with open(log_path, 'w') as f:
                pass
                
    elif mode == 'copy_truncate':
        if os.path.exists(log_path):
            shutil.copy2(log_path, backup_path)
            # Truncate original
            with open(log_path, 'w') as f:
                f.truncate(0)

def main():
    parser = argparse.ArgumentParser(description="R-01 Synthetic NDJSON Writer")
    parser.add_argument("--output-file", required=True, help="Path to the log file to write")
    parser.add_argument("--total-lines", type=int, default=1000, help="Total number of lines to emit")
    parser.add_argument("--rotate-every-bytes", type=int, default=0, help="Rotate after file exceeds N bytes (0=disabled)")
    parser.add_argument("--rotation-mode", choices=['rename_create', 'copy_truncate'], default='rename_create')
    parser.add_argument("--manifest-path", required=True, help="Path to write the expectation manifest")
    parser.add_argument("--flush", action='store_true', help="Flush after every line")
    parser.add_argument("--delay-ms", type=float, default=1.0, help="Delay between lines in milliseconds")
    
    args = parser.parse_args()
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(args.output_file), exist_ok=True)
    
    # Initialize log file
    if not os.path.exists(args.output_file):
        with open(args.output_file, 'w') as f:
            pass

    rotation_count = 1
    
    for seq in range(1, args.total_lines + 1):
        # Generate record
        record = {
            "seq": seq,
            "source_id": "r01_synthetic_writer",
            "ts": time.time(),
            "payload": "x" * 64  # Padding to create volume
        }
        line = json.dumps(record) + "\n"
        
        # Check rotation before writing if needed (simplified strategy)
        if args.rotate_every_bytes > 0:
            size = os.path.getsize(args.output_file)
            if size >= args.rotate_every_bytes:
                rotate(args.output_file, args.rotation_mode, rotation_count)
                rotation_count += 1

        # Write
        with open(args.output_file, 'a') as f:
            f.write(line)
            if args.flush:
                f.flush()
                os.fsync(f.fileno())
        
        if args.delay_ms > 0:
            time.sleep(args.delay_ms / 1000.0)

    write_manifest(args, args.total_lines)
    print(f"Finished writing {args.total_lines} lines. Rotated {rotation_count - 1} times.")

if __name__ == "__main__":
    main()