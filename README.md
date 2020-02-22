# PyExp -- Linguistic Experiments using tkinter and Python 3

This is one of my ongoing side projects: an experiment script with Python 3 using tkinter. The scope of this effort is fairly limited for now:

* have a straight forward, simple structure with which to carry out linguistic experiments
    * to achieve this, I made the choice to limit aesthetic flexibility in favor of a broad(-ish) coverage of important paradigms and minimal specification effort before the experiment is ready to go
* include these paradigms (for now):
    * linguistic judgments of text and audio stimuli -- the latter of which can either be present locally or streamed from online sources
    * forced choice (either dynamic or static) between images or text options
    * self-paced-reading (either cumulative or static)
* ability to choose between the various paradigms and to specify the way the experiment is to be run (e.g., with or without a training portion) and what kind of data is to be collected (e.g., different meta-data fields)

## Getting Started

To run the experiment, simply adjust the settings in `config.py` and add your item files to the mix before running `experiment.py`. The experiment should then run as specified (barring any code blunders on my part). Alternatively, if you just want to have a look at the way everything works and looks, you can simply run it as-is; a wide variety of exemplary item lists and items is provided (and used for testing purposes). 

**ADD**: 

* item lists -> data structure
* an explanation of the various settings available in `config.py`

## Details

In order to display the experiment, tkinter is used (unfortunately, so far, I have only tested this script on Mac OS, but I do hope that this should not be a problem), internal data handling and exporting is accomplished with pandas, while anything relating to audio files relies on pygame.

## Feedback

If you have any comments, feature requests or suggestions, please feel free to send me an e-mail: [Maik Thalmann](mailto:maik.thalmann@gmail.com?subject=[GitHub]%20PyExp).

## Acknowledgments

Thank you to anybody whose code I used and likely butchered in my own interpretation!