#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Module with helper functions for SharpVelvet.

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
    
Description: This module contains helper functions for the SharpVelvet fuzzer.

"""

from collections import namedtuple
from decimal import Decimal
from functools import partial
from fractions import Fraction
from math import isnan
from pathlib import Path

import pandas as pd
from gmpy2 import mpz, log10, mpfr
import json
import os
import re
import resource
import subprocess
import time

from tools import *
import file_manager as fm
import report_manager as rm


Count = namedtuple("Count", "solver preproc count", defaults=[None, None, -1])

Instance = namedtuple("Instance", "path problem_type n_vars n_clss proj_vars lits2weights",
                           defaults=[None, None, None, None, None, None])

# The following regular expressions are all based on the information in
# https://mccompetition.org/assets/files/mccomp_format_24.pdf
# TODO: add support for alternative precisions
# TODO: add support for all value formats
sat_pat = re.compile(r'\s*s\s+(?P<satisfiability>(UN)?((SATISFIABLE)|(KNOWN)))\s*', re.DOTALL)
type_pat = re.compile(r'\s*c\s+s\s+type\s+(?P<problem_type>((w)|(p)|(pw))?mc)\s*', re.DOTALL)
est_pat = re.compile(r'\s*c\s+s\s+(?P<est_type>(neg)?log10-estimate)\s+(?P<est_val>[\d.e\-inf]+)\s*', re.DOTALL)
count_pat = re.compile(r'\s*c\s+s\s+(?P<counter_type>((exact)|(approximate)))\s+(?P<precision>((arb)|(single)|(double)|(quadruple)))\s+(?P<notation>((log10)|(float)|(prec-sci)|(int)|(frac)))\s+(?P<value>((inf)|(\d+\.*\d*)))\s*', re.DOTALL)
gen_pat = re.compile(r'.*/instances/p?w?cnf/(?P<generator>[\w-]+)_\d+_s\d+\.p?w?cnf', re.DOTALL)
# TODO: add functionality for pac guarantees

# REGEX for parsing verifier output
# trace_pat = re.compile(r'reading from \"(?P<trace_file>.*\.trace)\"...done', re.DOTALL)
verified_count_pat = re.compile(r'(root)?\s*(m|M)odel count: (?P<verified_count>\d+)\s*', re.DOTALL)


def fstr(template, **kwargs):
    return eval(f"f'{template}'", kwargs)


def abs_path(relative_path: str):
    return os.path.abspath(relative_path)


def set_limits(t):
    """

    :param t:
    :return:
    """
    # Set maximum CPU time to 1 second in child process, after fork() but before exec()
    rm.log_message(f"Setting resource limit in child (pid {os.getpid()})")
    resource.setrlimit(resource.RLIMIT_CPU, (t, t))


def is_nan_or_none(value):
    """
    Check if the value is NaN or None.
    (generated by copilot)

    Parameters:
        value: The value to check.

    Returns:
        bool: True if the value is NaN or None, False otherwise.
    """
    if value is None:
        return True
    if (isinstance(value, float) or isinstance(value, int)) and isnan(value):
        return True
    return False


def construct_command(counter, path_to_instance, memout, timeout):
    counter_dir = str(Path(counter.path).parent.absolute())
    if '{INSTANCE}' in counter.config:
        tmp_command = f"./{os.path.basename(counter.path)} {counter.config}"
    else:
        tmp_command = f"./{os.path.basename(counter.path)} {counter.config} {path_to_instance}"
    return fstr(tmp_command, STAREXEC_MAX_MEM=memout, STAREXEC_WALLCLOCK_LIMIT=timeout, INSTANCE=path_to_instance, TMP='/scratch/aldlatour/sharpfuzz'), counter_dir


def handle_errors(err, verbosity):
    if err is None:
        if verbosity >= 3:
            rm.log_message("No error.")
        return False
    else:
        rm.log_message(f"Error: {err}")
        return True


def handle_timeout(start_time, timeout, counter_name, path_to_instance):
    diff_time = time.time() - start_time
    if diff_time > timeout:
        rm.log_message(f"Aborted! Counter {counter_name} exceeded maximum time of {timeout} s on instance {path_to_instance}.")
        return True
    return False


def parse_counter_output(counter_output, counter, path_to_instance, timed_out, error, log_dir, command):
    success, result = parse_output(counter_output, counter, path_to_instance, timed_out=timed_out, error=error)
    if not success:
        log_file = fm.store_counter_output(
            command=command, path_to_instance=path_to_instance,
            counter_output=counter_output, counter=counter, log_dir=log_dir)
        rm.log_message(f"ERROR when running {counter.name}. Output written to {log_file}")
    return result


def run(command: str,
        dir: str,
        verbosity=1,
        timeout=10):
    if verbosity >= 2:
        rm.log_message(f'--> Executing: {" ".join(command)} in dir {dir}')
    if verbosity >= 3:
        rm.log_message(f'CPU limit of parent (pid {os.getpid()}): {resource.getrlimit(resource.RLIMIT_CPU)}')

    this_dir = os.path.dirname(os.path.realpath(__file__))
    os.chdir(dir)
    p = subprocess.Popen(command, stderr=subprocess.STDOUT,
                         stdout=subprocess.PIPE, universal_newlines=True,
                         preexec_fn=partial(set_limits, timeout))
    os.chdir(this_dir)

    console_output, err = p.communicate()
    if verbosity >= 3:
        rm.log_message(
            f"CPU limit of parent (pid {os.getpid()}) after child finished executing: {resource.getrlimit(resource.RLIMIT_CPU)}")
    return console_output, err


def log10cnt(cnt: str):
    """

    Source: adapted from Johannes' parse_counts_util.py.

    :param cnt:
    :return:
    """
    try:
        if 'inf' in cnt:
            log10_value = str(mpfr('nan'))
        elif 'e' in cnt:
            cnt = Decimal(cnt)
            log10_value = str(log10(mpz(cnt)))
        else:
            cnt = Decimal(cnt)
            log10_value = str(log10(mpz(cnt)))
    except ValueError as _:
        print(f"ValueError: {cnt}")
        log10_value = str(mpfr('nan'))
    return log10_value


def normalize_count(count_str):
    """
    Normalize a count string to a gmpy2.mpfr for comparison.
    (partially generated by copilot)
    Parameters:
        count_str (str): The count as a string.

    Returns:
        gmpy2.mpfr: The normalized count.
    """

    if is_nan_or_none(count_str):
        return count_str

    # Check if the count is in scientific notation
    if re.match(r'^[+-]?\d+(\.\d+)?[eE][+-]?\d+$', count_str):
        return mpfr(count_str)

    # Check if the count is a fraction
    if '/' in count_str:
        return mpfr(Fraction(count_str))

    # Otherwise, assume it's a float
    return mpfr(count_str)


def get_random_seed(seed):
    if seed is None:
        b = os.urandom(8)
        seed = int.from_bytes(b, byteorder='big', signed=False)
    rm.log_message(f"Using seed: {seed}")
    return seed


def get_extension(projected=False, weighted=False) -> str:
    if not projected and not weighted:
        return "cnf"
    if projected and not weighted:
        return "pcnf"
    if weighted and not projected:
        return "wcnf"
    if weighted and projected:
        return "pwcnf"


def parse_counters(counter_config_file: str):
    """Read counter configurations from a given json file.

    Parameters:
        counter_config_file (str): Path to json file with counter configuration
    """
    counter_dict = json.load(open(counter_config_file))
    counters = [Counter(name, counter_dict[name]["path"], counter_dict[name]["config"], bool(counter_dict[name]["exact"]))
                for name in counter_dict]
    return counters


def parse_generators(generator_config):
    """
    Read instance generators from a given json file or a dictionary.

    Parameters:
        generator_config (str or dict): Path to json file with generator configuration or a dictionary.

    Returns:
        list: List of Generator objects.
    """
    if isinstance(generator_config, str):
        with open(generator_config, 'r') as file:
            gen_dict = json.load(file)
    elif isinstance(generator_config, dict):
        gen_dict = generator_config
    else:
        raise ValueError("Input must be a string (path to a file) or a dictionary.")

    generators = [Generator(name, gen_dict[name]["path"], gen_dict[name]["config"]) for name in gen_dict]
    assert generators, "Aborting. Please specify at least one instance generator."
    return generators


def parse_preprocessors(preprocessor_config_file: str):
    """Append preprocessors from a given json file with the preprocessor configurations.

    Parameters:
        preprocessor_config_file (str): Path to json file with preprocessor configuration
    """
    preprocessors = []
    if preprocessor_config_file is not None:
        prep_dict = json.load(open(preprocessor_config_file))
        preprocessors = [Preprocessor(name, prep_dict[name]["path"], prep_dict[name]["config"]) for name in prep_dict]
    return preprocessors


def get_instance_list(path_to_instances):
    if os.path.isdir(path_to_instances):
        abs_path = os.path.abspath(path_to_instances)
        return [f"{abs_path}/{file_name}"
                for file_name in os.listdir(abs_path)
                if os.path.isfile(f"{abs_path}/{file_name}")]
    elif os.path.isfile(path_to_instances):
        with open(path_to_instances, 'r') as infile:
            return [filename.strip() for filename in infile.readlines()]
    else:
        print("ERROR: please provide a path to a directory with problem instances "
              "or a path to a file with a path to a problem instance on each line.")


def parse_cnf(path_to_cnf: str) -> Instance:
    """ Parse DIMACS cnf instance following the format specified in
    https://mccompetition.org/assets/files/mccomp_format_24.pdf
    """
    n_vars = 0
    proj_vars = set()
    lits2weights = dict()
    problem_type = ''
    with (open(path_to_cnf, 'r') as infile):
        for line in infile.readlines():
            line = line.strip()
            # DIMACS HEADER
            if line.startswith("p "):
                _, inst_type, n_vars_str, n_clss_str = line.split()
                n_vars = int(n_vars_str)
                n_clss = int(n_clss_str)
                assert inst_type in ["cnf", "wcnf", "pcnf", "pwcnf"], \
                    f"Invalid instance type: {inst_type} for {path_to_cnf}."
            # OPTIONAL MODEL COUNTING HEADER
            elif line.startswith("c t "):
                _, _, problem_type = line.split()
                assert problem_type in ["mc", "wmc", "pmc", "pwmc", ""], \
                    f"Invalid problem type: {problem_type} for {path_to_cnf}."
            # WEIGHTED LITERALS
            elif line.startswith("c p "):
                _, _, w_lit, weight, zero = line.split()
                assert zero == '0', \
                    f"Invalid weight specification in {path_to_cnf}."
                lits2weights[int(w_lit)] = weight
            # PROJECTED VARIABLES
            elif line.startswith("c p show "):
                new_proj_vars = set([int(var) for var in line.split()[2:-1]])
                proj_vars = proj_vars.union(new_proj_vars)

    # Do some sanity checks and clean up
    assert n_vars != 0, f"ERROR: Cannot find 'p cnf' in {path_to_cnf}"
    # TODO: do sanity checks on the given weights

    if len(proj_vars) == n_vars and not lits2weights:
        if problem_type != "mc":
            rm.log_message(f"WARNING: changing problem type from {problem_type} to mc, since all variables are projected and none are weighted.")
        problem_type = "mc"
    elif proj_vars and not lits2weights:
        if problem_type != "pmc":
            rm.log_message(f"WARNING: changing problem type from {problem_type} to pmc, since some variables are projected and none are weighted.")
        problem_type = "pmc"
    elif len(proj_vars) == n_vars and lits2weights:
        if problem_type != "wmc":
            rm.log_message(f"WARNING: changing problem type from {problem_type} to wmc, since all variables are projected and some are weighted.")
        problem_type = "wmc"
    elif proj_vars and lits2weights:
        if problem_type != "pwmc":
            rm.log_message(f"WARNING: changing problem type from {problem_type} to pwmc, since some variables are projected and some are weighted.")
        problem_type = "pwmc"

    # Return info about instance
    instance_info = Instance(path=path_to_cnf, problem_type=problem_type, n_vars=n_vars, n_clss=n_clss, proj_vars=proj_vars, lits2weights=lits2weights)
    return instance_info


def load_verified_counts(verified_counts_path):
    """
    Load verified counts from a CSV file and return as a dictionary.

    Parameters:
        verified_counts_path (str): Path to the CSV file with verified counts.

    Returns:
        dict: Dictionary with instance as key and verified counts as values.
    """
    if verified_counts_path is None:
        return None
    verified_counts_df = pd.read_csv(verified_counts_path, dtype={'verified_count': str})
    verified_counts_dict = {
        row['instance']: {col: row[col] for col in verified_counts_df.columns if col != 'instance'}
        for _, row in verified_counts_df.iterrows()
    }
    return verified_counts_dict

def parse_output(
        counter_output: str,
        counter: Counter,
        path_to_instance: str,
        timed_out=False,
        error=False,
        verbosity=1) -> (bool, dict):

    result = {
        'counter': counter.name,
        'instance': path_to_instance,
        'satisfiability': None,
        'problem_type': None,
        'est_type': None,
        'est_val': None,
        'counter_type': None,
        'count_precision': None,
        'count_notation': None,
        'count_value': None,
        'timed_out': timed_out,
        'error': error,
    }

    if verbosity >= 3:
        rm.log_message("OUTPUT")

    for l in counter_output.split("\n"):
        l = l.strip()

        # Print each line of the counter's output, if verbosity level is high enough
        if verbosity >= 3:
            rm.log_message(l)

        # Skip all optional information:
        if l.startswith('c o'):
            continue

        # Catch some basic errors:
        if "Assertion " in l and "failed" in l:
            rm.log_message(f"Counter {counter.name} reports assertion fail: {l}")  # TODO: come up with better error message
            result['error']: True
            return False, result
        if "ERROR Memory out!" in l:
            if verbosity >= 2:
                rm.log_message(f"Counter {counter.name} ran out of memory on {path_to_instance}.")
            result['error']: True
            return False, result
        if "ERROR" in l:  # TODO: check if this is a reliable way to detect errors
            if verbosity >= 2:
                rm.log_message(f"ERROR found in counter {counter.name} on instance {path_to_instance}: {l}")
            result['error']: True
            return False, result

        # Process lines to retrieve relevant data for reporting and sanity checks
        m = re.match(sat_pat, l)
        if m is not None:
            result['satisfiability'] = m.group("satisfiability")
            continue
        m = re.match(type_pat, l)
        if m is not None:
            result['problem_type'] = m.group("problem_type")
            continue
        m = re.match(est_pat, l)
        if m is not None:
            result['est_type'] = m.group("est_type")
            result['est_val'] = m.group("est_val")  # TODO: check what should happen if neglog10
            continue
        m = re.match(count_pat, l)
        if m is not None:
            result['counter_type'] = m.group("counter_type")
            result['count_precision'] = m.group("precision")
            result['count_notation'] = m.group("notation")
            result['count_value'] = m.group("value")  # TODO: recompute for uniform reporting

    return True, result


def get_generator(path_to_instance: str) -> str:
    m = re.match(gen_pat, path_to_instance)
    if m is not None:
        return m.group('generator')
    return "unknown"


def check_counts(counts: dict) -> bool:
    # TODO: Add functionality for approximate counters
    # TODO: Add functionality for weighted & projected counters
    # If all counts agree, return True
    if len(set([normalize_count(count) for count in counts.values()])) == 1:
        return True
    return False


def parse_verifier_output(path_to_instance: str, output_file: str, timed_out:bool, error: bool, verbosity=1) -> (bool, dict):
    """ Parse the output of a verifier to obtain a verified model count.

    TODO: Right now, much of this is hardcoded for two specific verifier pipelines. Ideally, the user should be able to any verifier they like, but currently there is no support for that.

    """
    result = {'verified': False,
              'satisfiability': None,
              'timed_out': timed_out,
              'error': error,
              'no_root_claim': False,
              'verified_count': None}
    with (open(output_file, 'r') as out_file):
        for l in out_file.readlines():
            l = l.strip()

            m = re.match(verified_count_pat, l)
            if m is not None:
                result['verified_count'] = m.group("verified_count")
                if result['verified_count'] == '0':
                    result['satisfiability'] = 'UNSATISFIABLE'
                else:
                    result['satisfiability'] = 'SATISFIABLE'
                continue

            if ('proofs verified' in l              # When using the nnf2trace-and-sharptrace-verifier.sh script
                or 'PROOF SUCCESSFUL' in l):        # When using the cpog-verifier.sh script
                result['verified'] = True
                continue
            # TODO: implement verified unsatisfiability
            if ('IntegrityError(NoRootClaim)' in l         # I think this means that sharptrace concludes that the instance is UNSAT
                or 'proof done but some clause is neither the asserted root nor a POG definition' in l):                   # I think this means that cpog concludes that the instance is UNSAT
                result['no_root_claim'] = True
                result['satisfiability'] = 'UNSATISFIABLE'
                continue

            # Catch some basic errors:
            if "Assertion " in l and "failed" in l:
                rm.log_message(
                    f"Verifier reports assertion fail: {l}")  # TODO: come up with better error message
                result['error']: True
                return False, result
            if "ERROR Memory out!" in l:
                if verbosity >= 2:
                    rm.log_message(f"Verifier ran out of memory on {path_to_instance}.")
                result['error']: True
                return False, result
            if "error" in l.lower():  # TODO: check if this is a reliable way to detect errors
                if verbosity >= 2:
                    rm.log_message(f"ERROR found in verifier on instance {path_to_instance}: {l}")
                result['error']: True
                return False, result

    return True, result
