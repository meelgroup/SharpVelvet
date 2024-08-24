#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Helper functions for managing files and directories for SharpVelvet.

Authors:     Anna L.D. Latour, Mate Soos
Contact:     a.l.d.latour@tudelft.nl
Date:        2024-07-06
Maintainers: Anna L.D. Latour, Mate Soos
Version:     0.0.1
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

import errno
import tarfile
import os
from pathlib import Path

from tools import Counter
from report_manager import log_message

SHARPVELVET_DIR = Path(os.path.dirname(__file__)).parent.absolute()


def silent_remove(filename):
    """ Silently remove file that may or may not exist.
    Source: https://stackoverflow.com/a/10840586
    """
    try:
        os.remove(filename)
    except OSError as e: # this would be "except OSError, e:" before Python 2.6
        if e.errno != errno.ENOENT: # errno.ENOENT = no such file or directory
            raise # re-raise exception if a different error occurred


def get_file_name(path_to_file):
    return os.path.splitext(os.path.basename(path_to_file))[0]


def create_instance_directories(
        instance_dir: str,
        weighted=False,
        projected=False
):
    if not os.path.isdir(instance_dir):
        log_message(f"Creating directory to store generated test instances: {instance_dir}.")
        os.makedirs(f"{instance_dir}", exist_ok=True)

    child_dirs = ['cnf']
    if weighted and not projected:
        child_dirs.append('wcnf')
    elif projected and not weighted:
        child_dirs.append('pcnf')
    elif weighted and projected:
        child_dirs.append('pwcnf')

    new_dirs = dict()
    for child_dir in child_dirs:
        new_dir = f"{instance_dir}/{child_dir}"
        new_dirs[child_dir] = new_dir
        os.makedirs(new_dir, exist_ok=True)
    return new_dirs


def store_counter_output(command: str,
                         path_to_instance: str,
                         counter_output: str,
                         counter: Counter,
                         log_dir: str):

    log_file = f"{log_dir}/{get_file_name(path_to_instance)}_{counter.name}_output.log"
    with open(log_file, 'w') as lf:
        lf.write(f"$ {command}\n")
        lf.write(counter_output)
    return log_file


def clean_up_proof(instance: str):
    basename = os.path.basename(instance)
    proof_dir = f"{SHARPVELVET_DIR}/proofs"
    nnf_file = f"{proof_dir}/{basename}.nnf"
    proof_file = f"{proof_dir}/{basename}.trace"
    out_file = f"{proof_dir}/{basename}.output"
    log_file = f"{proof_dir}/{basename}.log"

    for f in [nnf_file, proof_file, out_file, log_file]:
        silent_remove(f)
