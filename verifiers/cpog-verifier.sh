#!/bin/bash

# Short description.

# Author:     Anna L.D. Latour
# Contact:    a.l.d.latour@tudelft.nl
# Date:       2024-07-24
# Maintainer: Anna L.D. Latour
# Version:    0.0.1
# Copyright:  (C) 2024, Anna L.D. Latour
# License:    GPLv3
#     This program is free software; you can redistribute it and/or
#     modify it under the terms of the GNU General Public License
#     as published by the Free Software Foundation; version 3
#     of the License.

#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.

#     You should have received a copy of the GNU General Public License
#     along with this program; if not, write to the Free Software
#     Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
#     02110-1301, USA.
    
# Description: Long description.


# get relevant paths
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
PROJECT_DIR=$(dirname "$SCRIPT_DIR")

f=$(realpath "$1")

# create relevant directories if necessary
proof_dir=/scratch/aldlatour/mc2024_track1/out/verification
mkdir -p $proof_dir

# get filenames
ddnnf_file="${proof_dir}/${f##*/}.nnf"
proof_file="${proof_dir}/${f##*/}.cpog"
output_file="${proof_dir}/${f##*/}.output"
log_file="${proof_dir}/${f##*/}.log"

rm -f $output_file

# Run 
./d4 -dDNNF $f -out=$ddnnf_file >> $output_file 2>&1
./cpog-gen -v 2 -L $log_file $f $ddnnf_file $proof_file  >> $output_file 2>&1
./cpog_checker -c $f $proof_file >> $output_file 2>&1