#!/bin/bash

# flac_chop.sh
# Usage: ./flac_chop.sh -s <start_seconds> -l <length_seconds> <input_file>

set -e

start_sec=""
length_sec=""
input_file=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        -s|--start)
            start_sec="$2"
            shift # past argument
            shift # past value
            ;;
        -l|--length)
            length_sec="$2"
            shift # past argument
            shift # past value
            ;;
        *)
            input_file="$1"
            shift # past argument
            ;;
    esac
done

# Validation
if [[ -z "$start_sec" || -z "$length_sec" || -z "$input_file" ]]; then
    echo "Usage: $0 -s <seconds> -l <seconds> <input_file>"
    exit 1
fi

if [[ ! -f "$input_file" ]]; then
    echo "Error: Input file '$input_file' not found."
    exit 1
fi

# Calculations (x1000 for RF capture scaling)
calc_start=$((start_sec * 1000))
calc_length=$((length_sec * 1000))

# Convert to HH:MM:SS
seconds_to_hms() {
    local total_seconds=$1
    local h=$((total_seconds / 3600))
    local m=$(( (total_seconds % 3600) / 60 ))
    local s=$((total_seconds % 60))
    printf "%02d:%02d:%02d" $h $m $s
}

start_hms=$(seconds_to_hms $calc_start)
length_hms=$(seconds_to_hms $calc_length)

# Output filename generation
dir=$(dirname "$input_file")
filename=$(basename "$input_file")
extension="${filename##*.}"
name_only="${filename%.*}"
output_file="${dir}/${name_only}-cut.${extension}"

echo "Processing '$input_file'..."
echo "  Start: $start_sec sec -> $calc_start sec -> $start_hms"
echo "  Length: $length_sec sec -> $calc_length sec -> $length_hms"
echo "  Output: $output_file"

# Run ffmpeg
ffmpeg -i "$input_file" -c copy -ss "$start_hms" -t "$length_hms" "$output_file"

echo "Done."
