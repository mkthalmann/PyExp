# GUI Experiment with tkinter

This is one of my ongoing side projects: an experiment script with Python 3 using tkinter. The scope of this effort is fairly limited for now:

* have a straight forward, simple structure with which to carry out linguistic experiments
    * to achieve this, I made the choice to limit aesthetic flexibility in favor of a broad(-ish) coverage of important paradigms
* these paradigms include (for now):
    * linguistic judgments of text and audio stimuli -- the latter of which can either be present locally or streamed from online sources
    * forced choice (either dynamic or static) between images or text options
    * self-paced-reading (either cumulative or static)
* to choose between the various paradigms and to specify the way the experiment is to be run (e.g., with or without a training portion) and what kind of data is to be collected (e.g., different meta-data fields), the user can use `config.py` as well as her own files (such as item lists).

## Getting Started

To run the experiment, simply adjust the settings in `config.py` and add your item files to the mix before running `experiment.py`. Tne experiment should then run as specified (barring any code blunders on my part). 

**ADD**: item lists -> data structure