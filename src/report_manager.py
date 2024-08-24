#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Helper functions for printing information for SharpVelvet, and for saving
information to disk.

Authors:     Anna L.D. Latour, Mate Soos
Contact:     a.l.d.latour@tudelft.nl
Date:        2024-07-06
Maintainers: Anna L.D. Latour, Mate Soos
Version:     0.1.0
Copyright:   (C) 2024, Anna L.D. Latour, Mate Soos
License:     GPLv3
    This program is free software; you can redistribute it and/or
    modify it under the terms of the GNU General Public License
    as published by the Free Software Foundation; version 3
    of the License.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program; if not, write to the Free Software
    Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
    02110-1301, USA.

"""

from datetime import datetime
import json
import os
import sys


def log_message(message: str, print_time=False):
    if print_time:
        print(f'[SharpVelvet], {datetime.now().strftime("%Y-%m-%d, %Hh%Mm%Ss")}: {message}')
    else: print(f'[SharpVelvet]: {message}')
    sys.stdout.flush()


def print_counts(same_counts: bool, counts: dict):
    log_message("")
    if same_counts:
        log_message(f"All counters agree on count: {list(counts.values())[0]}.")
    else:
        log_message("ATTENTION: at least one counter disagrees with the others.")
        name_width = max(len(max(counts.keys(), key=len)), 7) + 1
        count_width = max(len(max([str(count) for count in counts.values()], key=len)), 5) + 1
        log_message(f"{'counter':<{name_width}}|{'count':>{count_width}}")
        log_message("-" * (name_width + 1 + count_width))
        for counter, count in counts.items():
            log_message(f"{counter:<{name_width}}|{str(count):>{count_width}}")


def save_parameters(args, log_dir, output_prefix, script_name):
    args_dict = dict(vars(args))
    param_file = f"{log_dir}/{output_prefix}_{os.path.splitext(script_name)[0]}_parameters.json"
    tool_configs = ['generators', 'counters']
    for tool_config in tool_configs:
        if tool_config in args_dict.keys():
            args_dict[tool_config + '_configs'] = json.load(open(args_dict[tool_config]))
    with open(param_file, 'w') as out_file:
        json.dump(args_dict, out_file, indent=4)


def save_problem_instances(problem_instances, log_dir, output_prefix):
    with open(f"{log_dir}/{output_prefix}_problem_instances.txt", 'w') as out_file:
        out_file.write("\n".join(problem_instances))