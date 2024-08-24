#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Generate CNF instances in DIMACS format for model counting problems.

Authors:     Anna L.D. Latour, Mate Soos
Contact:     a.l.d.latour@tudelft.nl
Date:        2024-08-13
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
    
Description: This script generates CNF in DIMACS format for model counting
             problems. It takes as input at least one problem generator, and has
             (limited) support for adding weights. It also has support for
             using a verified model counter to obtain verified model counts in
             an unweighted, unprojected setting (mc).
"""

import argparse
from datetime import datetime
import os
from pathlib import Path
import random
import re
import subprocess
import time
import pandas as pd

# Fuzzer modules
import file_manager as fm
import fuzzer_utils as fut
import report_manager as rm

seed_pat = re.compile(r'.*_\d{3}_s(?P<seed>\d+)\.\w+', re.DOTALL)

SHARPVELVET_DIR = Path(os.path.dirname(__file__)).parent.absolute()


def parse_arguments():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    tools = parser.add_argument_group("Tools")
    problem_type = parser.add_argument_group("Problem type")
    admin = parser.add_argument_group("Admin")
    weighted_params = parser.add_argument_group("[OPTIONAL] Parameters for Weighted instances")
    projected_params = parser.add_argument_group("[OPTIONAL] Parameters for Projected instances (NOT IMPLEMENTED YET)")
    verification = parser.add_argument_group(
        "[OPTIONAL] Verification (*only* available for mc and wmc, not for pmc and pwmc!)")

    # -------------------------   TOOLS   ------------------------- #
    tools.add_argument(
        "--generators", "-g", dest="generators", type=str, required=True,
        help="Path to json file with the CNF generators and their configurations."
    )

    # -------------------------   PROBLEM TYPE   ------------------------- #
    problem_type.add_argument(
        "--projected", "-p", dest="projected", default=False, action="store_true", required=False,
        help="If True, all specified counters are expected to do projected model counting, "
             "and all generators are expected to generate projected model counting problems. "
             "If False, all specified counters are expected to not do projected model counting, "
             "and all generators are expected to generate non-projected model counting problems"
    )
    problem_type.add_argument(
        "--weighted", "-w", dest="weighted", default=False, action="store_true", required=False,
        help="Add weights to generated instances."
    )

    # -------------------------   WEIGHTED   ------------------------- #

    weighted_params.add_argument(
        "--both-weights-specified", dest="both_weights_specified", type=str, required=False,
        choices=["yes", "no", "sometimes"], default="yes",
        help="Are the weights for both the positive and the negative specified, or just for one of the two?"
    )
    weighted_params.add_argument(
        "--weight-format", dest="weight_format", type=str, required=False,
        choices=["float", "fraction", "scientific", "mixed"], default="mixed",
        help="Format in which the weights are specified."
    )
    weighted_params.add_argument(
        "--negative-weights", dest="negative_weights", default=False, action="store_true", required=False,
        help="Some weights may be negative."
    )
    weighted_params.add_argument(
        "--percentage-variables", dest="percentage_weighted", type=float, default=50, required=False,
        help="What percentage of the variables is weighted? (number between 0 and 100)."
    )
    weighted_params.add_argument(
        "--precision", type=int, default=9, required=False,
        help="Maximum number of significant digits in weight."
    )

    # -------------------------   PROJECTED   ------------------------- #
    # TODO

    # -------------------------   VERIFICATION   ------------------------- #
    verification.add_argument(
        "--verifier", dest="verifier", type=str, required=False, default=None,
        help="Path to a script that takes as argument a path to a .cnf file and then "
             "generates a verified proof of correctness of the model count.")
    verification.add_argument(
        "--result-dir", dest="result_dir", type=str, required=False,
        help="Specify path to directory to store verification results. Default: /path/to/fuzzer/verified"
    )
    verification.add_argument(
        "--timeout", dest="timeout", type=int, required=False, default=100,
        help="Specify how much time (in seconds) the verifier gets to obtain a verified model count."
    )
    verification.add_argument(
        "--memout", dest="memout", type=int, required=False, default=8000,
        help="Specify how much memory (in MB) the verifier gets to obtain a verified model count."
    )
    verification.add_argument(
        "--clean-up-proofs", dest="clean_up_proofs", default=False, required=False, action="store_true",
        help="Clean up all proof-related files after verified count has been obtained."
    )

    # -------------------------   ADMIN   ------------------------- #

    admin.add_argument(
        "--max-time", "-t", dest="max_time", type=int, default=10, required=False,
        help="Timeout time for individual runs, in seconds."
    )
    admin.add_argument(
        "--max-mem", "-m", dest="max_mem", type=int, default=3200, required=False,
        help="Max memory for individual runs."
    )
    admin.add_argument(
        "--verbosity", "-v", type=int, default=2, required=False,
        dest="verbosity", help="Specify verbosity level 1, 2 or 3"
    )
    admin.add_argument(
        "--seed", "-s", dest="rnd_seed", type=int, required=False,
        help="Fuzz test start seed. If unset, a random seed is picked. "
             "WARNING: the seed for generating new instances is created by "
             "simply adding 1 to the seed for each iteration. Hence, if you are "
             "running multiple instances of this script in parallel, make sure "
             "that they each get seeds that are far enough away from each other "
             "to not risk calling the instance generators with the same seed."
    )
    admin.add_argument(
        "--num-iter", "-n", dest="num_iter", type=int, default=100,
        required=False, help="Specify the maximum number of iterations."
    )
    admin.add_argument(
        "--out-dir", dest="out_dir", type=str, required=False,
        help="Specify path to directory to store generated instances. Default: /path/to/fuzzer/out"
    )
    # admin.add_argument(
    #     "--instance-dir", dest="instance_dir", type=str, required=False,
    #     help="Specify path to directory to store generated instances. Default: /path/to/fuzzer/instances"
    # )

    # -------------------------   SANITY CHECKS   ------------------------- #
    parsed_args = parser.parse_args()

    if parsed_args.projected:
        rm.log_message("Instance generation for projected model counting not yet implemented. Aborting.")
        exit(1)

    if parsed_args.both_weights_specified == "no" and parsed_args.negative_weights:
        rm.log_message("WARNING: If a literal has a negative weight, the other literal's weight must also be given. "
                       "Changing 'both-weights-specified' to 'sometimes'.")
        parsed_args.both_weights_specified = "sometimes"

    out_dir = f"{Path(__file__).parent.resolve().parent.resolve()}/out" \
        if parsed_args.out_dir is None \
        else fut.abs_path(parsed_args.out_dir)
    parsed_args.out_dir = out_dir  # TODO: move to file_manager.py

    if parsed_args.verifier is not None:
        abs_path = fut.abs_path(parsed_args.verifier)
        parsed_args.verifier = abs_path

    seed = fut.get_random_seed(parsed_args.rnd_seed)
    parsed_args.rnd_seed = seed

    return parsed_args


def generate_instance(generator: fut.Generator,
                      new_cnf_path: str,
                      seed: int,
                      verbosity=1
                      ):
    tmp_command = f"{generator.path} {generator.config}"
    if '{out_file}' not in generator.config:
        tmp_command += ' {out_file}'
    command = fut.fstr(tmp_command, out_file=new_cnf_path, seed=seed, PROJECT_DIR=SHARPVELVET_DIR)
    status = subprocess.call(command, shell=True)
    if status != 0:
        rm.log_message(f"Failed generator call: {command}")
        exit(-1)
    elif verbosity >= 3:
        rm.log_message(f"Called generator: {command}")
    elif verbosity >= 2:
        rm.log_message(f"Generated instance {new_cnf_path}.")


def generate_instances(generators: list,
                       cnf_dir: str,
                       num_iter: int,
                       seed: int,
                       projected=False,
                       weighted=False):
    ext = fut.get_extension(projected=projected, weighted=weighted)
    new_instances = []
    subdir = 'cnf'
    progress_interval = max(int(num_iter * len(generators) / 10.0), 1)
    if weighted and not projected:
        subdir = 'wcnf'
    elif weighted and projected:
        subdir = 'pwcnf'
    elif projected and not weighted:
        subdir = 'pcnf'
    for i in range(num_iter):
        for generator in generators:
            file_name = f"{cnf_dir}/{subdir}/{generator.name}_{i:03}_s{seed+i}.{ext}"
            generate_instance(generator=generator, new_cnf_path=file_name, seed=seed+i)
            new_instances.append(file_name)
        if i % progress_interval == progress_interval - 1:
            rm.log_message(f"Progress: generated {(i+1) * len(generators)} / {num_iter * len(generators)} instances.")
    return new_instances


def add_projection(path_to_instance: str,
                   out_dir: str):
    # TODO: implement
    return


def generate_float_weights(precision, negative):
    # TODO: build in functionality for very small weights
    weight = random.uniform(0, 1)
    formatted_weight = f"{weight:.{precision}f}"
    if negative:
        sign = random.choice(['-', ''])
        return f"{sign}{formatted_weight}"
    else:
        return str(formatted_weight), f"{1.0 - weight:.{precision}f}"


def generate_fractional_weights(precision, negative):
    max_val = 1000000
    numerator = random.randint(1, max_val)
    denominator = random.randint(1, max_val)

    if negative:
        sign = random.choice(['-', ''])
        return f"{sign}{numerator}/{denominator}"
    else:
        return f"{numerator}/{denominator}", f"{max_val - numerator}/{denominator}"


def generate_scientific_weights(precision, negative):
    # TODO: Implement scientific notation weights
    return


def add_weights(path_to_instance: str,
                out_dir: str,
                args):

    instance_info = fut.parse_cnf(path_to_cnf=path_to_instance)
    base_file = os.path.basename(path_to_instance)
    new_file = f"{out_dir}/{base_file}"

    assert not instance_info.lits2weights, f"Weights already specified for {path_to_instance}."

    problem_type = instance_info.problem_type
    if problem_type == "mc":
        problem_type = "wmc"
    elif problem_type == "pmc":
        problem_type = "pwmc"

    weight_generator = generate_float_weights
    if args.weight_format == "fraction":
        weight_generator = generate_fractional_weights
    elif args.weight_format == "scientific":
        weight_generator = generate_scientific_weights
    elif args.weight_format == "mixed":
        weight_generator = random.choice([generate_float_weights, generate_fractional_weights, generate_scientific_weights])
    print(f"weight generator: {weight_generator}")

    n_weighted_vars = int(float(args.percentage_weighted) * 0.01 * instance_info.n_vars)
    weighted_vars = random.sample(range(1, instance_info.n_vars), n_weighted_vars)
    lits2weights = dict()

    for w_var in weighted_vars:
        polarity = random.choice([-1, 1])
        if not args.negative_weights:
            w1, w2 = weight_generator(args.precision, args.negative_weights)
            if args.both_weights_specified:
                lits2weights[polarity * w_var] = w1
                lits2weights[-1 * polarity * w_var] = w2

    with open(path_to_instance, 'r') as infile:
        with open(new_file, 'w') as outfile:
            for line in infile.readlines():
                if line.startswith("p"):
                    outfile.write(line)
                    outfile.write(f"c t {problem_type}\n")
                    if instance_info.proj_vars:
                        outfile.write("c p show " + " ".join([str(p_var) for p_var in instance_info.proj_vars]) + " 0 \n")
                    for lit, weight in lits2weights.items():
                        outfile.write(f"c p {lit} {weight} 0\n")
                else:
                    outfile.write(line)
    return new_file


def get_ground_truth(
        path_to_instance: str,
        verifier_script: str,
        out_dir: str,
        timeout=100,
        max_mem=3200,
        verbosity=1) -> dict:
    timed_out = False
    error = False
    # TODO: figure out how to communicate time + space resources
    if verbosity >= 2:
        rm.log_message(f"Running verification script {verifier_script} on instance {path_to_instance}.")

    verification_dir = str(Path(verifier_script).parent.absolute())
    # proof_dir = f"{str(Path(Path(__file__).parent.absolute()).parent.absolute())}/proofs"
    proof_dir = f"{out_dir}/verification"
    output_file = f"{proof_dir}/{os.path.basename(path_to_instance)}.output"
    tmp_command = f"./{os.path.basename(verifier_script)} {path_to_instance}"
    command = fut.fstr(tmp_command, STAREXEC_MAX_MEM=max_mem, STAREXEC_WALLCLOCK_LIMIT=timeout)

    if verbosity >= 2:
        rm.log_message(f"command: {command}")

    start_time = time.time()
    verification_output, err = fut.run(command.split(), verification_dir + '/', verbosity=verbosity)
    if err is None:
        if verbosity >= 3:
            rm.log_message("No error.")
    else:
        error = True
        rm.log_message(f"Error: {err}")

    # Abort if counter exceeds maximum time
    diff_time = time.time() - start_time
    if diff_time > timeout:
        timed_out = True
        rm.log_message(
            f"Aborted! Verification script {verifier_script} exceeded maximum "
            "time of {timeout} s on instance {path_to_instance}.")

    # Otherwise, parse output
    success, result = fut.parse_verifier_output(path_to_instance, output_file, timed_out=timed_out, error=error, verbosity=verbosity)
    result['problem_type'] = 'mc'  # For now only support for ground truth of this type TODO: Implement for weighted
    result['instance'] = path_to_instance
    if not success:
        rm.log_message(f"ERROR when running {verifier_script}. Output written to {output_file}")

    return result


if __name__ == "__main__":
    # TODO: save parameters
    args = parse_arguments()

    generators = fut.parse_generators(args.generators)
    random.seed(args.rnd_seed)

    output_prefix = f"{datetime.now().strftime('%Y-%m-%d')}_s{args.rnd_seed}"
    new_dirs = fm.create_instance_directories(instance_dir=f"{args.out_dir}/instances", weighted=args.weighted, projected=args.projected)
    log_dir = f"{args.out_dir}/logs"
    os.makedirs(f"{args.out_dir}/logs", exist_ok=True)
    rm.save_parameters(args, log_dir, output_prefix, os.path.basename(__file__))

    file_paths = generate_instances(
        generators=generators,
        cnf_dir=f"{args.out_dir}/instances",    # TODO: clean up
        num_iter=args.num_iter,
        seed=args.rnd_seed)
    rm.log_message("")
    rm.log_message(f"Generated {len(file_paths)} problem instances.")
    rm.log_message(f"Saved problem instances to {Path(file_paths[0]).parent.resolve()}")

    if args.weighted:
        rm.log_message("")
        rm.log_message(f"Adding weights to generated instances according to the following parameters:")
        rm.log_message(f"- both weights specified? {args.both_weights_specified}")
        rm.log_message(f"- weight format: {args.weight_format}")
        rm.log_message(f"- negative weights? {args.negative_weights}")
        rm.log_message(f"- percentage of weighted variables: {args.percentage_weighted}%")
        rm.log_message(f"- precision: {args.precision} significant digits")

        file_paths_weighted = [add_weights(path_to_instance=file_path, out_dir=new_dirs['wcnf'], args=args)
                               for file_path in file_paths]
        rm.log_message(f"Saved weighted problem instances to {Path(file_paths_weighted[0]).parent.resolve()}")
        file_paths = file_paths_weighted

    instances_list_file = f"{args.out_dir}/{output_prefix}_generated_instances.txt"
    fm.silent_remove(instances_list_file)

    with open(instances_list_file, 'w') as outfile:
        outfile.write('\n'.join(file_paths))
    rm.log_message(f"Saved a list of all generated instances to {instances_list_file}")

    if args.verifier:
        verified_counts = []
        os.makedirs(f"{args.out_dir}/verification", exist_ok=True) # TODO: move this to file_manager.py
        progress_interval = max(int(args.num_iter / 10.0), 1)
        for i, file_path in enumerate(file_paths):
            result = get_ground_truth(
                path_to_instance=file_path,
                verifier_script=args.verifier,
                out_dir=args.out_dir,
                timeout=args.timeout,
                max_mem=args.memout)
            if 'verified_count' in result:
                result['verified_count'] = str(result['verified_count'])

            verified_counts.append(result)
            if i % progress_interval == progress_interval - 1:
                rm.log_message(f"Progress: verified {(i+1)} / {args.num_iter * len(generators)} instances.", print_time=True)
            df_results = pd.DataFrame(verified_counts)
            df_results['verified_count'] = df_results['verified_count'].astype(str)
            df_results.to_csv(f"{args.out_dir}/{output_prefix}_verified_counts.csv")
        # TODO: implement moving the verification information to the user-specified directory

