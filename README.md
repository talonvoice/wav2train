# wav2train
Automatic pipeline to prepare a directory full of (audio clip : transcript) file pairs for wav2letter training. Currently uses [DSAlign](https://github.com/mozilla/DSAlign) for transcript alignment.

This project is part of [Talon Research](https://talonvoice.com/research/). If you find this useful, [please donate](https://www.patreon.com/join/lunixbochs).

## Installation

This process works best on a Mac or Linux computer.

### Debian

    sudo apt install build-essential libboost-all-dev cmake zlib1g-dev libbz2-dev liblzma-dev \
                     python3 python3-pip python3-venv ffmpeg wget sox
    ./setup

### macOS

    brew install python3 ffmpeg wget cmake boost sox
    ./setup

## Usage

    ./wav2train input/ output/
    # ./wfilter output/clips.lst > output/clips-filt.lst # not yet implemented
    ./wsplit  output/clips.lst

## Description

1. Consumes a directory with audio and matching transcripts, such as:

    ```
    input/a.wav input/a.txt
    input/b.wav input/b.txt
    ```

    Most common audio formats (wav, flac, mp3, ogg, sph, etc) will be detected. You can mix formats in the input directory. The audio files can be any length. The only requirement is that the text file is a transcription of the audio file.

2. Finds voice activity in the audio files and time-aligns these segments to the transcription.
3. Extracts the voice segments into .flac files and creates a wav2letter-compatible clips.lst file.
4. The output at this point looks like:

    ```
    output/clips/a.flac
    output/clips/b.flac
    output/clips.lst
    ```

4. [Optional] *not included yet* ~Use the `wfilter` tool to filter out "bad inputs" using a pretrained model and an error threshold.~

    ```
    ./wfilter output/clips.lst > output/clips-filt.lst
    ```

5. [Optional] Use the `wsplit` tool to auto-split a clips.lst file into `dev.lst,test.lst,train.lst`.

    ```
    ./wsplit output/clips.lst
    # or, if you filtered:
    ./wsplit output/clips-filt.lst
    ```

## Extras

    # Print the transcript for each clip and play it, for debugging
    ./wplay output/clips.lst

    # Update the paths in output/*.lst to match its current directory
    # As *.lst uses absolute paths, this is useful to run after moving
    #    datasets around on your disk or to a new machine.
    # Only works if clips are in the dirname(.lst)/clips/* directory
    ./wrebase output/

    # Print some basic stats about a dataset, such as number of clips and total hours.
    ./wstat output/clips.lst
