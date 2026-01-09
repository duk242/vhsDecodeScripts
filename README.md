# vhsDecodeScripts
Scripts and extras I use for vhs importing with the vhs-decode project

# flac_chop.sh
## Purpose
This allows you to grab a small sample from a longer RF Capture FLAC file.
Because the RF Captures are massive and the sample rate is in msps instead of ksps, you need to multiply the time by 1000 to get the correct time - this script will automatically do this for you!

## Requirements
Requires ffmpeg installed and a bash terminal (Sorry Windows users!)

## Usage
`./flac_chop.sh -s <start_seconds> -l <length_seconds> <input_file>`

If you're chopping a small sample to open in Audacity to look at waveforms, set your length_seconds to 1 - that's 16 minutes worth of audio!

## Side Note
I named it after the [Vince Slap Chop Rap](https://www.youtube.com/watch?v=UWRyj5cHIQA) meme