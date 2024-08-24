#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Main script to run SharpVelvet. Run after generate_instances.py.

Authors:     Anna L.D. Latour, Mate Soos
Contact:     a.l.d.latour@tudelft.nl
Date:        2024-08-13
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
    
Description: Takes as input a set of model counters and a set of problem
             instances, and runs each counter on each instance, reporting
             whenever at least one of the counters disagrees with the others
             on the value of the model count for an instance. If provided with
             verified counts, the model counts that are reported by the counters
             are also compared to verified counts.
"""

import argparse
from datetime import datetime
import os
import re
import time
from pathlib import Path
import pandas as pd

# Fuzzer modules
import file_manager as fm
import fuzzer_utils as fut
import report_manager as rm

instances_prefix_pat = re.compile(r'(?P<prefix>\d{4}-\d{2}-\d{2}_s\d+)_generated_instances\.txt', re.DOTALL)
instance_seed_pat = re.compile(r'[\w\-]+_000_s(?P<seed>\d+)\.\w+', re.DOTALL)


def parse_arguments():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    tools = parser.add_argument_group("Tools")
    problem_type = parser.add_argument_group("Problem type")
    behaviour = parser.add_argument_group("Fuzzer behaviour")
    admin = parser.add_argument_group("Admin")
    verification = parser.add_argument_group(
        "[OPTIONAL] Verification (*only* available for unweighted, unprojected model counting!)")

    # -------------------------   TOOLS   ------------------------- #
    tools.add_argument(
        "--counters", "-c", dest="counters", type=str, required=True,
        help="Path to json file with the counters and their configurations."
    )

    # -------------------------   PROBLEM TYPE   ------------------------- #

    problem_type.add_argument(
        "--instances", "-i", dest="instances", type=str, required=True,
        help="Path to directory with instances, or file with on each line a path to an instance."
    )
    problem_type.add_argument(
        "--projected", dest="projected", default=False, action="store_true", required=False,
        help="If True, all specified counters are expected to do projected model counting, "
             "and all generators are expected to generate projected model counting problems. "
             "If False, all specified counters are expected to not do projected model counting, "
             "and all generators are expected to generate non-projected model counting problems"
    )
    problem_type.add_argument(
        "--weighted", dest="weighted", default=False, action="store_true", required=False,
        help="If True, all specified counters are expected to do weighted model counting, "
             "and all generators are expected to generate weighted model counting problems. "
             "If False, all specified counters are expected do unweighted model counting, "
             "and all generators are expected to generate unweighted model counting problems."
    )

    # -------------------------   BEHAVIOUR   ------------------------- #
    behaviour.add_argument(
        "--timeout", "-t", dest="timeout", type=int, default=10, required=False,
        help="Timeout time for individual runs, in seconds."
    )
    behaviour.add_argument(
        "--memout", "-m", dest="memout", type=int, default=3200, required=False,
        help="Max memory for individual runs."
    )
    behaviour.add_argument(
        "--verbosity", "-v", type=int, default=2, required=False,
        dest="verbosity", help="Specify verbosity level 1, 2 or 3"
    )
    behaviour.add_argument(  # TODO: Check if this is actually used
        "--keep-bugs-only", dest="keep_bugs_only", default=False, required=False,
        action="store_true",
        help="Only keep the CNFs that yield bugs, clean up all others."
    )

    # -------------------------   ADMIN   ------------------------- #

    admin.add_argument(
        "--out-dir", dest="out_dir", type=str, required=False,
        help="Specify path to directory to store outputs. Default: /path/to/fuzzer/out"
    )
    admin.add_argument(
        "--log-dir", dest="log_dir", type=str, required=False,
        help="Specify path to directory to store outputs. Default: /path/to/fuzzer/out/logs"
    )

    # -------------------------   VERIFICATION   ------------------------- #
    verification.add_argument(
        "--verified-counts", dest="verified_counts", required=False, default=None,
        help="Path to .csv with verified counts, generated by generate_instances.py."
    )
    verification.add_argument(
        "--clean-up-proofs", dest="clean_up_proofs", default=False, required=False, action="store_true",
        help="Clean up all proof-related files after verified count has been obtained."
    )

    # -------------------------   SANITY CHECKS   ------------------------- #
    parsed_args = parser.parse_args()

    if parsed_args.verified_counts is not None and (parsed_args.projected or parsed_args.weighted):
        rm.log_message("Verification not available for projected or weighted model counting. Aborting.")
        exit(1)

    out_dir = f"{Path(__file__).parent.resolve().parent.resolve()}/out" \
        if parsed_args.out_dir is None \
        else fut.abs_path(parsed_args.out_dir)
    parsed_args.out_dir = out_dir
    os.makedirs(out_dir, exist_ok=True)

    log_dir = f"{parsed_args.out_dir}/logs" \
        if parsed_args.log_dir is None \
        else fut.abs_path(parsed_args.log_dir)
    parsed_args.log_dir = log_dir
    os.makedirs(log_dir, exist_ok=True)

    return parsed_args


def run_counter(counter: fut.Counter,
                path_to_instance: str,
                log_dir: str,
                timeout=10,
                memout=3200,
                verbosity=1) -> dict:

    if verbosity >= 2:
        rm.log_message(f"Running counter {counter.name} on instance {path_to_instance}.")

    command, counter_dir = fut.construct_command(counter, path_to_instance, memout=memout, timeout=timeout)
    start_time = time.time()
    counter_output, err = fut.run(command.split(), counter_dir + '/', verbosity=verbosity)
    error = fut.handle_errors(err, verbosity=verbosity)
    timed_out = fut.handle_timeout(start_time=start_time, timeout=timeout,
                                   counter_name=counter.name, path_to_instance=path_to_instance)

    return fut.parse_counter_output(
        counter_output, counter, path_to_instance,
        timed_out=timed_out, error=error, log_dir=log_dir, command=command)


def fuzz(instances: [],
         out_dir: str,
         output_prefix: str,
         counters: list,
         verified_counts=None,
         projected=False,
         weighted=False,
         timeout=10,
         memout=3200,
         verbosity=1,
         clean_up_proofs=False,
         ):
    # Create data structures to store summary of results
    df = pd.DataFrame(columns=[])
    log_dir = f"{out_dir}/logs"
    path_to_csv = f"{out_dir}/{output_prefix}_fuzz-results.csv"
    path_to_problematic_instances = f"{out_dir}/{output_prefix}_problematic-instances.txt"
    fm.silent_remove(path_to_problematic_instances)
    problem_instances = []
    verified = False

    # Main loop
    rm.log_message("")
    for i, path_to_instance in enumerate(instances):
        rm.log_message("")
        rm.log_message(f"Instance {i+1}/{len(instances)}: {path_to_instance}", print_time=True)
        # TODO: Handle preprocessing
        # TODO: Handle delta-debugging
        counts = dict()
        if verified_counts is not None:
            verified = verified_counts[path_to_instance]['verified']
            verified_count_str = verified_counts[path_to_instance]['verified_count']
            counts['verified_count'] = verified_count_str
        for counter in counters:
            result = run_counter(
                counter=counter,
                path_to_instance=path_to_instance,
                log_dir=log_dir,
                timeout=timeout,
                memout=memout,
                verbosity=verbosity
            )
            counts[counter.name] = result['count_value']
            result['generator'] = fut.get_generator(path_to_instance)
            if verified_counts is not None:
                result['verified_count'] = counts['verified_count']
            result['verified'] = verified

            df = pd.concat([df, pd.DataFrame([result])], ignore_index=True)

        if len(counts) == 1:
            name = counters[0].name
            rm.log_message(f"Counter {name} reports count {counts[name]}")
            if result['error']:
                problem_instances.append(path_to_instance)
        else:
            same_counts = fut.check_counts(counts)
            rm.print_counts(same_counts, counts)
            if same_counts:
                if clean_up_proofs:
                    fm.clean_up_proof(instance=path_to_instance)
                    if verbosity >= 2:
                        rm.log_message(f"Cleaned up proof files for instance {path_to_instance}.")
            else:
                problem_instances.append(path_to_instance)

        # Every iteration, store results:
        df.to_csv(path_to_csv)
        rm.save_problem_instances(problem_instances, log_dir, output_prefix)
    rm.log_message("")
    return path_to_csv, problem_instances


if __name__ == "__main__":
    args = parse_arguments()

    # Setup
    counters = fut.parse_counters(args.counters)
    instances = fut.get_instance_list(args.instances)
    verified_counts_dict = fut.load_verified_counts(args.verified_counts)

    os.makedirs(args.log_dir, exist_ok=True)

    os.environ['STAREXEC_WALLCLOCK_LIMIT'] = str(args.timeout)
    os.environ['STAREXEC_MAX_MEM'] = str(args.memout)

    output_prefix = ''
    if os.path.isfile(args.instances):
        m = re.match(instances_prefix_pat, os.path.basename(args.instances))
        output_prefix = m.group('prefix')
    else:
        print(os.path.basename(sorted(instances)[0]))
        m = re.match(instance_seed_pat, os.path.basename(sorted(instances)[0]))
        output_prefix = f"{datetime.now().strftime('%Y-%m-%d')}_s{m.group('seed')}"

    rm.save_parameters(args, args.log_dir, output_prefix, os.path.basename(__file__))
    # TODO: save parameters

    path_to_results, problem_instances = fuzz(
        instances=instances,
        out_dir=args.out_dir,
        output_prefix=output_prefix,
        counters=counters,
        verified_counts=verified_counts_dict,
        projected=args.projected,
        weighted=args.weighted,
        timeout=args.timeout,
        memout=args.memout,
        verbosity=args.verbosity,
        clean_up_proofs=args.clean_up_proofs
    )

    rm.log_message("FINISHED!", print_time=True)
    if problem_instances:
        rm.log_message("The following instances produced miscounts or crashes:")
        for instance in problem_instances:
            rm.log_message(instance)
    elif not problem_instances and len(counters) == 1 and args.verified_counts is None:
        rm.log_message(f"None of the instances triggered a crash on {counters[0].name}")
    else:
        rm.log_message("None of the instances triggered bugs!")
