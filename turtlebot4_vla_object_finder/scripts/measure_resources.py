#!/usr/bin/env python3
"""Record host usage, Docker stats, and cgroup peaks as JSONL; no RAM claims inferred."""
import argparse
import datetime
import json
import subprocess
import time
from pathlib import Path


def host_memory():
    values = {line.split(':')[0]: int(line.split()[1])*1024
              for line in Path('/proc/meminfo').read_text().splitlines()
              if len(line.split()) > 1 and line.split()[1].isdigit()}
    return {'total_bytes': values['MemTotal'], 'available_bytes': values['MemAvailable'],
            'used_bytes': values['MemTotal']-values['MemAvailable'],
            'swap_used_bytes': values['SwapTotal']-values['SwapFree']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seconds', type=int, default=180)
    parser.add_argument('--output', default='artifacts/resources.jsonl')
    parser.add_argument('--containers', nargs='*', default=[])
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    peak, initial_swap = 0, host_memory()['swap_used_bytes']
    with output.open('w') as stream:
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            stats = subprocess.run(['docker', 'stats', '--no-stream', '--format', '{{json .}}']
                                   + args.containers, capture_output=True, text=True)
            memory = host_memory()
            peak = max(peak, memory['used_bytes'])
            stream.write(json.dumps({'time_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                     'host': memory, 'docker_stats_error': stats.stderr.strip() or None, 'containers': [json.loads(line) for line
                                      in stats.stdout.splitlines() if line.strip()]})+'\n')
            stream.flush()
            time.sleep(1)
        peaks = {}
        for name in args.containers:
            result = subprocess.run(['docker', 'exec', name, 'cat', '/sys/fs/cgroup/memory.peak'],
                                    capture_output=True, text=True)
            peaks[name] = int(result.stdout.strip()) if result.returncode == 0 else None
        stream.write(json.dumps({'host_peak_used_bytes': peak, 'container_cgroup_peaks_bytes': peaks,
                                 'initial_swap_used_bytes': initial_swap,
                                 'final_swap_used_bytes': host_memory()['swap_used_bytes']})+'\n')
    print('Resource measurements:', output)
    print('Host peak used GiB:', round(peak/2**30, 3))


if __name__ == '__main__':
    main()
