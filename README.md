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

# vhsDecodeGUI.py
## Purpose
I keep forgetting the commands for vhsdecode and wanted a smoother process.
It's definitely beta software, all vibe coded, but it works for me!

> [!NOTE]
> I made this to make *my* process a bit easier. It may or may not work very well for you!
> There's better things on the way from the dd86 team like [Decode Orc](https://github.com/simoninns/decode-orc) from simon_dd86.  Check that project first to see if it'll suit your needs better!

## Features
* Has a current frame counter, a timecode to show where it's up to, decode speed, dropped field counter and track skip counter.
* Allows you to set your arguments for vhsdecode and will save them to a config file
* Has a button to open your decoded file in ld-analyse
* A button to automatically run Auto Audio Align (On the linear capture only, can be modified to do the other one pretty easily!)
* Video Export button

In theory: Select the video file, hit decode -> check it with ld-analyse -> hit Auto Audio Align -> Hit Video Export
You'll have your exported video file + the audio synced ready to drop into your favourite NLE to edit.

## Requirements 
* Python3 with tkinter
* vhsdecode and ldinstalled to the path
* Mono

## Installation
Download the vhsDecodeGUI folder
Run: `python3 -m venv venv`
`pip install -r requirements.txt`

## Usage
`cd /path/to/vhsDecodeGUI && source ./venv/bin/activate && python3 ./vhsDecodeGUI.py`

Check the vhs_decode_config.txt file - change the settings in there to what you want to use (you can change the vhs-decode arguments in the app itself too - just the export ones I haven't put anywhere yet).

The Auto Audio Align function assumes the audio file is named like this: `*-linear.flac` and is in the same folder as the input file.
It's using the [VhsDecodeAutoAudioAlign.exe](https://gitlab.com/wolfre/vhs-decode-auto-audio-align/-/releases) from Rene Wolf and a slightly modified version of [Harry's Align Script](https://github.com/harrypm/Scripts)
