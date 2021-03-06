# pylint: disable=no-member,W0614

import datetime
import glob
import io
import logging
import os
import random  # randomize items, and FC options
import re  # regular expressions
import shutil
import smtplib
import ssl
import string  # participant id
import time
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from io import BytesIO  # linked files
from itertools import cycle
from threading import Timer
from tkinter import *
from tkinter import messagebox
from urllib.request import urlopen  # linked files

import pandas as pd
import pygame  # audio
import yaml
from PIL import Image, ImageTk


"""
    TODO:
    - support for video stimuli
    - option to have several experimental blocks with a break inbetween

    FIXME:
    - 
"""


class HouseKeepingError(Exception):
    """Raise when housekeeping checks are not passed, e.g. when not all expected entries are present."""

    pass


class ItemFileError(Exception):
    """Raise when the item file is not usable for the Experiment class, e.g. when it contains missing entries."""

    pass


class Window:
    """General class that harbors some methods for window handling, like centering or resizing operations."""

    def center_window(self):
        """Center a GUI window."""
        # Call all pending idle tasks - carry out geometry management and redraw widgets.
        self.root.update_idletasks()
        # Get width and height of the screen
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        # Calculate the x and y positions of the window
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        # assign the new geometry as well as the x, y positions
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def empty_window(self):
        """Gather all frames and content within them in a GUI window and delete them from view."""
        # get children
        widget_list = self.root.winfo_children()
        # add grandchildren
        for item in widget_list:
            if item.winfo_children():
                widget_list.extend(item.winfo_children())

        # delete all widgets
        for item in widget_list:
            item.pack_forget()

        self.display_spacer_frame()

    def fullscreen(self):
        """Make the GUI window fullscreen (Escape to reset to specified geometry)."""
        self.root.geometry(
            f"{self.root.winfo_screenwidth() - 3}x{self.root.winfo_screenheight() - 3}+0+0"
        )
        if self.config["allow_fullscreen_escape"]:
            self.root.bind("<Escape>", self.reset_geometry)

    def reset_geometry(self, event):
        """Return to initially specified geometry from fullscreen."""
        self.root.geometry(self.config["geometry"])


class Experiment(Window):
    """Main class for the experiment. Relies on python file upon instantiation with the settings to be used."""

    # core values which need to stay the same over the course of one set of participants
    config_core = [
        "experiment_title",
        "meta_fields",
        "warm_up",
        "non_dynamic_button",
        "warm_up_file",
        "use_text_stimuli",
        "self_paced_reading",
        "cumulative",
        "likert",
        "dynamic_fc",
        "dynamic_img",
        "item_file",
        "item_number_col",
        "item_or_file_col",
        "sub_exp_col",
        "cond_col",
        "extra_cols",
        "spr_control_options",
    ]

    def __init__(self, config, window=True):
        """Initialie the experiment class and optionally start up the tkinter GUI. A variety of checks will be performed on the config argument script.

        Arguments:
            config {str} -- Python script name that contains the experiment's configuration parameters.

        Keyword Arguments:
            window {bool} -- Whether to initialize Tkinter and open a GUI window (default: {True})
        """
        self.logger = logging.getLogger(__name__)
        # load the settings from the configation file
        self.config = self.get_config_dict(config)
        # folder for results, feedback and yaml
        self.dir = f"{self.config['experiment_title']}_results"
        # one of the housekeeping files
        self.part_file = os.path.join(self.dir, "participants.txt")
        # second one
        self.config_file = os.path.join(self.dir, "config.yaml")
        # default participant number
        self.part_num = 0
        # phase checker
        self.critical = False
        # check that all settings are present
        self.check_config()
        # assign the item list (for the critical items)
        self.item_list_no = self.housekeeping()
        # randomly generated string as participant identifier
        self.id_string = self.id_generator()
        # read the items and reorder to columns (reads in correct list based on item_list_no)
        self.items_critical = self.retrieve_items(self.config["item_file"])
        # warm up items; None of if they're not gonna be used
        self.items_warm_up = self.retrieve_items(self.config["warm_up_file"])
        # pandas df which we'll append the item results to
        self.outdf = self.prepare_results_df()

        # all the Tkinter stuff that is not necessary when performing other functions
        if window:
            # set up the main window that'll house all the widgets
            self.root = Tk()
            # add title, geometry, centering etc
            self.setup_gui()
            # get the logo file and resize it
            self.logo = self.resize_image(self.config["logo"], 90)

        # time of testing
        self.exp_start = time.time()  # to track eperiment duration
        self.start_time = datetime.datetime.now().strftime("%H:%M:%S")

    def __str__(self):
        """Return the core settings of the experiment, namely those which have to stay the same over subsequent participants

        Returns:
            str -- Description of the experiment
        """
        # only show the most important settings (the ones in the class attribute)
        return f"Experiment with the following core settings: { {k: self.config[k] for k in self.config_core} }"

    """ SECTION I: initializing methods for the various phases of the experiment """

    def start_experiment(self):
        """Initialize the meta-data collection section of the experiment."""
        # show the logo and the line; usually called via empty_window
        self.display_spacer_frame()
        # do not proceed if all participants slots are filled already
        if self.part_num == self.config["participants"]:
            self.experiment_finished()
        else:
            # store for meta data
            self.meta_entries = []
            # show the intro text and the forms
            self.display_meta_information_forms()
            self.submit_button(self.submit_participant_information)
        self.root.mainloop()

    def start_exposition_phase(self):
        """Initialize the expository section of the experiment. Inform participant about the experimental task and procedure."""
        self.logger.info("Starting exposition.")
        self.display_long(self.config["expo_text"], 8)
        self.submit_button(self.exit_exposition)

    def start_item_phase(self, critical=True):
        """Initialize the critical/warm-up section of the experiment.

        Keyword Arguments:
            critical {bool} -- Whether to cycle through the critical items or the warm-up items (default: {True})
        """
        # needs to be instantiated now, because we will use it even if exp is not getting finished
        self.feedback = StringVar()
        self.logger.info(f"Starting {'critical' if critical else 'warm-up'} phase.")
        # assign different item lists depending on the phase of the experiment
        if critical:
            self.critical = True
            self.items = self.items_critical
            self.display_short(self.config["title"], 5)
            self.display_short(self.config["description"])
            # only update the participant number in the critical section
            self.housekeeping_file_update()
            self.logger.info(
                f"Participant {self.part_num}/{self.config['participants']} in list {self.item_list_no}"
            )
        else:
            # make sure item numbers and subexps between warm-up and critical do not overlap
            test.test_that(
                (
                    not self.items_critical[self.config["sub_exp_col"]]
                    .eq(self.items_warm_up[self.config["sub_exp_col"]])
                    .any()
                ),
                "Sub-experiment values between warm-up and critical items overlap.",
            )
            self.items = self.items_warm_up
            self.display_short(self.config["warm_up_title"], 5)
            self.display_short(self.config["warm_up_description"])
        self.init_items()

    def init_items(self):
        """Display the various kinds of elements needed for the different types of experiments (text, play and submit buttons, likert scale, ...)."""
        # judgment variable filled with GUI interaction
        self.judgment = StringVar()
        # index to iterate through items
        self.i_ix = 0
        # intitialize self-paced reading exp
        if self.config["self_paced_reading"]:
            # index to iterate through words
            self.w_ix = 0
            # dict for the reaction times
            self.spr_reaction_times = {}
            # storage for the fully masked item
            self.masked = ""
            self.display_masked_item()
        # init other kinds of experiments
        else:
            if self.config["use_text_stimuli"]:
                self.display_text_item()
            else:
                pygame.init()
                self.playimage = self.resize_image(
                    os.path.join("media", "play.png"), 100
                )
                self.display_audio_stimulus()
                self.update_play_button()
            # stores the buttons (necessary to resolve the judgment value later)
            self.likert_list = []
            # stores images in dynamic FC exps
            self.fc_images = {}
            self.judgment_buttons()
            self.submit_button(self.submit_judgment)
        # disable the submit button (will be reactivated on condition)
        self.submit.config(state="disabled")
        # start reaction timer
        self.time_start = time.time()

    def experiment_finished(self):
        """Show message when all necessary participants have been tested and button to exit the GUI."""
        # show the 'thank you for your interest, but'-message and display exit button
        self.display_long(self.config["finished_message"], 8)
        self.submit_button(self.root.destroy, "Exit")
        self.logger.info(f"All Participants have been tested.")

        # send confirmation e-mail if so specified
        if self.config["confirm_completion"]:
            self.send_confirmation_email()

    def exit_exposition(self):
        """End the exposition stage and move on to either warm-up or critical section."""
        self.empty_window()
        self.start_item_phase(not self.config["warm_up"])

    """ SECTION II: display methods used by the initializing functions """

    def setup_gui(self):
        """Generate the window title and perform some general setups."""
        # set the title to the one specified in the config file
        self.root.wm_title(self.config["window_title"])
        # same with the geometry
        self.root.geometry(self.config["geometry"])
        # either go into fullscreen or center window, depending on setting
        self.fullscreen() if self.config["fullscreen"] else self.center_window()
        # add close warning
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def display_short(self, text, size_mod=0, side="top"):
        """Display a short message without word wrap enabled. Returns the frame that contains the label

        Arguments:
            text {str} -- Text to display; if empty, nothing will happen

        Keyword Arguments:
            size_mod {int} -- Increase or decrease the basesize in the experiment settings (default: {0})
            side {str} -- Where to pack the resulting frame and label in the root window (default: {"top"})

        Returns:
            Frame -- Frame containing the text so that other elements can be added to that same frame
        """
        # only instantiate frame and label if there's actually text to display
        if text:
            frame = Frame(self.root)
            frame.pack(expand=False, fill="both", side="top", pady=2)
            label = Label(
                frame,
                text=text,
                font=(self.config["font"], self.config["basesize"] + size_mod),
            )
            label.pack(pady=2, side=side)
            return frame

    def display_long(self, text, size_mod=0, height=10, font="font"):
        """Display a long message with word wrap enabled.

        Arguments:
            text {str} -- Text to display; if empty, nothing will happen

        Keyword Arguments:
            size_mod {int} -- Increase or decrease the basesize in the experiment settings (default: {0})
            height {int} -- Height of the label element (decrease for shorter texts) (default: {10})
            font {str} -- Which font to use from the experimental settings; either 'font' or 'font_mono' (default: {'font'})

        Returns:
            Label -- Returns the label to that it can be accessed via tkinter's get() method
        """
        # only instantiate frame and label if there's actually text to display
        if text:
            frame = Frame(self.root)
            frame.pack(expand=False, fill="both", side="top", pady=10, padx=25)
            label = Label(
                frame,
                font=(self.config[font], self.config["basesize"] + size_mod),
                text=text,
                height=height,
                wraplength=1000,
            )
            label.pack()
            return label

    def display_meta_information_forms(self):
        """Display the instructions and the meta labels as well as the entry fields for all user-specified meta information that is to be collected."""
        # show the instruction text for the meta data collection
        self.display_short(self.config["meta_instruction"], -5)

        # create frame and label for each of the entry fields
        for i, field in enumerate(self.config["meta_fields"]):
            row = Frame(self.root)
            lab = Label(
                row,
                width=15,
                text=field,
                anchor="w",
                font=(self.config["font"], self.config["basesize"] - 8),
            )
            # create the entry fields and store them
            self.meta_entries.append(Entry(row))

            # deploy all of it
            row.pack(side="top", padx=5, pady=5)
            lab.pack(side="left")
            self.meta_entries[i].pack(side="right", expand=True, fill="x")

    def display_text_item(self):
        """Display frame and label for text items."""
        self.item_text = self.display_long(self.items.iloc[0, self.i_ix], 7, 6)

    def display_audio_stimulus(self):
        """Display frame, label, and play button for audio items."""
        frame_audio = Frame(self.root, height=10)
        frame_audio.pack(expand=False, fill="both", side="top", pady=10, padx=25)
        # display the play button with text and an image next to it
        self.audio_btn = Button(
            frame_audio,
            text=self.config["audio_button_text"],
            image=self.playimage,
            compound="left",
            fg="black",
            font=(self.config["font"], self.config["basesize"]),
            padx=20,
            pady=25,
            command=lambda: self.play_stimulus(),
        )
        self.audio_btn.pack(side="top")

    def display_masked_item(self):
        """Display frame, label, and button for masked items in self-paced reading"""
        # item text and frame
        self.item_text = self.display_long(
            text=self.create_masked_item(), size_mod=8, height=9, font="font_mono"
        )
        # submit button which shows the control question
        self.submit_button(self.display_control_questions)

        # delay prevents a bug where pressing the spacebar takes you back to the exposition
        time.sleep(0.1)
        # press the space bar to show next word
        self.root.bind("<space>", self.next_word)

    def display_control_questions(self):
        """Display the control questions for self-paced reading items, including FC options and a submit button."""
        # empty window, display logo etc and show the control questions from the item file
        self.empty_window()
        self.display_long(self.items.iloc[self.i_ix, 4])

        # place the judgment buttons, taking the text from the config file
        self.frame_judg = Frame(self.root, relief="sunken", bd=2)
        self.frame_judg.pack(side="top", pady=20)
        for x in self.config["spr_control_options"]:
            self.text_or_image_button(
                text=str(x),
                value=str(x).casefold().replace(" ", "_"),
                likert_append=False,
            )
        self.submit_button(self.submit_control)
        # button is disabled by default, but we wanna enable it here
        self.submit.config(state="normal")

    def display_feedback(self):
        """Display instructions and entry field for feedback after the critical section."""
        # unless the feedback field is empty, show a frame to allow feedback entry
        if self.config["feedback"]:
            # instruction for the feedback
            frame = self.display_short(self.config["feedback"], -5)
            # entry field for the feedback
            self.feedback = Entry(frame)
            self.feedback.pack(side="top", expand=True, fill="x", ipady=5, padx=50)
            # button to save the results
            self.submit_button(self.save_complete_results)
        else:
            self.display_over()

    def display_over(self):
        """Show goodbye message and exit button."""
        self.empty_window()
        self.display_long(self.config["bye_message"], 10, 7)
        self.submit_button(self.on_closing, "Exit")
        self.logger.info("Experiment session over.")

    def display_spacer_frame(self):
        """Display frame with logo and line that appears at the top of every stage of the experiment."""
        spacer_frame = Frame(self.root)
        spacer_frame.pack(side="top", fill="both")
        # label with logo instead of text
        spacer_img = Label(spacer_frame, image=self.logo)
        spacer_img.pack(fill="x")
        # also display a line
        spacer_line = Frame(self.root, height=2, width=800, bg="gray90")
        spacer_line.pack(side="top", anchor="c", pady=20)

    def display_error(self, text):
        """Frame and label for error messages that appear if entry fields are blank. Disappears after a delay.

        Arguments:
            text {str} -- Text to display as error message
        """
        error_label = Label(
            self.root,
            font=(self.config["font"], self.config["basesize"] - 8),
            text=text,
            fg="red",
        )
        error_label.pack(side="top", pady=10)
        error_label.after(800, lambda: error_label.destroy())

    """ SECTION III: file management methods """

    def test_that(self, condition, text, error=ItemFileError):
        """Test whether a condition holds and raises an Exception if that is not the case.
        
        Arguments:
            condition {bool} -- Condition to be tested
            text {str} -- Error message that will be logged and re-raised if the test fails 
            error {Exception} -- Exception to be raised if test fails
        
        Raises:
            error: Some Exception that was passed as an argument
        """
        try:
            if not condition:
                raise error(text)
        except error as e:
            self.logger.error(e)
            raise

    def get_config_dict(self, config):
        """Import the configuration file (yaml file) and return it as a dictionary.

        Arguments:
            config {str} -- File name of the python script containing the settings for the experiment

        Returns:
            dict -- Dictionary with the experimental parameters (key) and their settings (value)
        """
        # Read YAML file
        with open(config, "r") as file:
            return yaml.safe_load(file)

    def check_config(self):
        """Check that the configuration file has not been modified from what is expected in the application."""
        compare_config = {
            "fullscreen",
            "allow_fullscreen_escape",
            "geometry",
            "window_title",
            "experiment_title",
            "confirm_completion",
            "receiver_email",
            "tester",
            "logo",
            "meta_instruction",
            "meta_fields",
            "expo_text",
            "warm_up",
            "warm_up_title",
            "warm_up_description",
            "warm_up_file",
            "use_text_stimuli",
            "self_paced_reading",
            "cumulative",
            "title",
            "description",
            "likert",
            "endpoints",
            "dynamic_fc",
            "non_dynamic_button",
            "dynamic_img",
            "google_drive_link",
            "delay_judgment",
            "participants",
            "remove_unfinished",
            "remove_ratio",
            "item_file",
            "item_file_extension",
            "item_number_col",
            "item_or_file_col",
            "sub_exp_col",
            "cond_col",
            "extra_cols",
            "spr_control_options",
            "items_randomize",
            "results_file_extension",
            "feedback",
            "audio_button_text",
            "button_text",
            "finished_message",
            "bye_message",
            "quit_warning",
            "error_judgment",
            "error_meta",
            "font",
            "font_mono",
            "basesize",
        }
        # check if all keys are as they should be
        self.test_that(
            compare_config == set(self.config.keys()),
            f"These entries are either missing from the config file or have been added to it: {compare_config^set(self.config.keys())}",
            HouseKeepingError,
        )

    def id_generator(
        self,
        size=15,
        chars=string.ascii_lowercase + string.ascii_uppercase + string.digits,
    ):
        """Generate a random participant string of character types and return it.

        Keyword Arguments:
            size {int} -- Length of the string to be generated (default: {15})
            chars {str} -- List of characters to use for the string (default: {string.ascii_lowercase + string.ascii_uppercase + string.digits})

        Returns:
            str -- String with random choice from supplied character list of specified length
        """
        return "".join(random.choice(chars) for _ in range(size))

    def housekeeping(self):
        """Retrieve participant number from file (or start from zero) and return the item list number for the current participant.

        Returns:
            int -- Item list number which will define which list (in a Latin Square design) is to be used in the critical phase
        """
        # check if the results path exists, if it doesn't, create it
        os.makedirs(self.dir, exist_ok=True)
        # read in the participant and the config yaml files
        try:
            self.read_housekeeping_files()
        # if they can't be found (because its a new experiment), create them
        except FileNotFoundError as e:
            self.create_housekeeping_files()
            self.logger.info(
                f"Housekeeping file '{self.part_file}' not found, creating one: {e}"
            )
        all_item_lists = glob.glob(f"{self.config['item_file']}[0-9]*")
        # check that all item lists have the same number of rows and columns
        self.test_that(
            len(set([self.read_multi_ext(x).shape for x in all_item_lists])) == 1,
            f"Item lists {self.config['item_file']} differ in number of rows/columns.",
        )
        # assign participant to an item list (using the modulo method for latin square); where glob.glob just finds all item lists
        return self.part_num % len(all_item_lists) + 1

    def create_housekeeping_files(self):
        """Create the yaml file that stores the experiment settings."""
        # no need to write a new participant file now, only upon entering the critical section
        # save self.config in the results directory to validate on later runs that the same settings are being used
        with io.open(self.config_file, "w", encoding="utf8") as file:
            yaml.dump(
                self.config,
                file,
                default_flow_style=False,
                indent=4,
                allow_unicode=True,
            )

    def read_housekeeping_files(self):
        """Read the file that stores the number of participants tested and, if there are more to test, call the yaml file check."""
        # read in the participant file
        with open(self.part_file, "r") as file:
            self.part_num = int(file.read())
        # next step: check the yaml file
        self.check_housekeeping_files()

    def check_housekeeping_files(self):
        """Check if the saved yaml config file is set to the same parameters as the file used to inititialize the class. Throw a warning if not."""
        # read in the yaml file
        with open(self.config_file, "r") as file:
            compare_config = yaml.safe_load(file)

        # compare the yaml and the new config attribute, halt experiment if they're not the same
        self.test_that(
            {k: self.config[k] for k in self.config_core}
            == {k: compare_config[k] for k in self.config_core},
            f"Configurations for the current experiment session have changed from previous participants.\nCheck the config file or start a new experiment to proceed\Current dict: { {k: self.config[k] for k in self.config_core} }\Previous dict: { {k: compare_config[k] for k in self.config_core} }",
            HouseKeepingError,
        )

    def housekeeping_file_update(self, increment=1):
        """Update the participant number and write it to the participants housekeeping file.

        Keyword Arguments:
            increment {int} -- Number by which to modifiy the participant number; use negative numbers to reduce the participants (default: {1})
        """
        # increase participant number
        self.part_num += increment
        # write participant number to the housekeeping file
        with open(self.part_file, "w") as file:
            file.write(str(self.part_num))

    def check_items(self, infile, df):
        """Check that the item list to be used for the experiment passes a number of checks.
        
        Arguments:
            infile {str} -- Path to the file for logging purposes
            df {DataFrame} -- pandas DataFrame to check
        """
        # there are no missing values
        self.test_that(
            df.notnull().all().all(), f"Missing values in {infile}."
        )
        # there are no duplicated rows in the dataset:
        self.test_that(
            ~df.duplicated().any(), f"Duplicated rows in {infile}."
        )
        # items do not occur more than once per subexp:
        self.test_that(
            ~df.duplicated(
                subset=[self.config["sub_exp_col"], self.config["item_number_col"]]
            ).any(),
            f"Some item numbers used multiple times per sub-exp in {infile}.",
        )

    def retrieve_items(self, filename):
        """Retrieve the items from the specified item file and randomize their order if specified, return a pandas DF.

        Arguments:
            filename {str} -- File that contains the items in a table-like format

        Returns:
            df -- pandas DF with all the item info or None if warm-up file is passed and no warm-up is planned
        """
        # with critical items
        if filename == self.config["item_file"]:
            # use the correct list of items
            infile = f"{filename}{self.item_list_no}"
        else:
            # with warm-up, there's no need to add the item list number, since there's only one file
            if self.config["warm_up"]:
                infile = filename
            # if no warm-up is gonna be performed, no need to read in the file
            else:
                return None

        # read in the conditions file
        df_items = self.read_multi_ext(f"{infile}{self.config['item_file_extension']}")

        # if so specified and we're dealing with critical items, randomize the items
        if all([self.config["items_randomize"], filename == self.config["item_file"]]):
            df_items = df_items.sample(frac=1).reset_index(drop=True)

        # rearrange the columns of the data frame using the entries in item_file_columns; don't use the remaining ones
        columns_to_order = list(
            pd.core.common.flatten(
                [
                    self.config["item_or_file_col"],
                    self.config["sub_exp_col"],
                    self.config["item_number_col"],
                    self.config["cond_col"],
                    self.config["extra_cols"],
                ]
            )
        )
        try:
            # try to rearrange the columns and remove all non-mentioned columns in the file; using filter remove remove empty entries
            df_items = df_items[filter(None, columns_to_order)]
            # perform some checks for the item lists to see if they are likely to work for the experiment
            self.check_items(infile, df_items)
            # assign the df as a instance property
            return df_items
        # if some of the columns aren't present, log them
        except KeyError as e:
            self.logger.error(f"Column mismatch. Check the following: {e}")

    def prepare_results_df(self):
        """Initialize the results df with appropriate header depending on the experiment. Set the df as outdf."""
        # outfile in new folder with id number attached
        name = f"result_{str(self.part_num).zfill(len(str(self.config['participants'])))}{self.config['results_file_extension']}"
        # system independent path to file in results directory
        self.outfile = os.path.join(self.dir, name)
        # generate a list with the header names for the results df
        header_list = [
            "id",
            "date",
            "start_time",
            "experimenter",
            self.config["meta_fields"],
            "sub_exp",
            "item",
            "cond",
        ]
        # for standard judgment experiments (either text or audio)
        if self.config["self_paced_reading"]:
            # add a column for each word in the item (of the first item)
            header_list = header_list + [
                self.items_critical.iloc[0, 0].split(),
                "control",
            ]
        else:
            # add judgments and reaction times
            header_list = header_list + ["judgment", "reaction_time"]
        # flatten the list of lists, remove capitalization and spaces (mainly from meta fields)
        header_list = [
            item.strip().casefold().replace(" ", "_")
            for item in pd.core.common.flatten(header_list)
        ]
        # initilize the results df
        return pd.DataFrame(columns=header_list)

    def resize_image(self, x, desired_height=150):
        """Resize and return images as Tkinter-useable objects.

        Arguments:
            x {str} -- Image file name

        Keyword Arguments:
            desired_width {int} -- Value to resize the width to (height is calculated automatically; aspect ratio is kept the same) (default: {250})

        Returns:
            PhotoImage -- Image object for use in tkinter apps
        """
        image = Image.open(x)
        # compute rescaled dimensions
        new_dimensions = (
            int(image.width / (image.height / desired_height)),
            int(image.height / (image.height / desired_height)),
        )
        # resize the image to the desired dims
        image = image.resize(new_dimensions, Image.ANTIALIAS)
        # and return a tkinter-usable version
        return ImageTk.PhotoImage(image)

    def unfinished_participant_results(self):
        """Depending on user settings, delete or keep data from experiment runs that were ended before the intended stopping point."""
        # if specified by user, do not save unfinished participant results (according to the given ratio)
        if all(
            [
                self.config["remove_unfinished"],
                self.i_ix < len(self.items) * self.config["remove_ratio"],
            ]
        ):
            # also reduce the participant number in the housekeeping file
            self.housekeeping_file_update(-1)
            self.logger.info("Participant won't increase participant count.")
        # if not specified, save the dataframe
        else:
            # add finished, duration and feedback columns
            self.append_metrics()
            # save the results file and log it
            self.save_multi_ext(self.outdf, self.outfile)
            self.logger.info(f"Unfinished participant will be counted.")
        # TODO: add a test that checks whether the df is as long as the current item index

    def append_metrics(self):
        """Add three columns to the results df: experiment duration, experiment finished, and feedback."""
        # compute experiment duration in minutes
        duration = round((time.time() - self.exp_start) / 60, 2)
        # whether the experiment was finished or not ('T' or 'F')
        finished = str(not self.critical)[0]
        # feedback or number of items completed
        feedback = self.feedback.get() or f"[{self.i_ix}/{len(self.items)} items]"

        # add all three columns
        self.outdf = self.outdf.assign(
            finished=finished, feedback=feedback, duration=duration
        )

    def delete_file(self, file):
        """Delete files or directories.

        Arguments:
            file {str} -- File/directory to be deleted
        """
        try:
            os.remove(file)
            self.logger.info(f"File deleted: {file}")
        # if permission error, then the file is a dir and we need a different function
        except PermissionError as e:
            shutil.rmtree(file)
            self.logger.info(f"Directory and all files deleted: {file}")
        # log if the file could not be found
        except FileNotFoundError as e:
            self.logger.warning(f"File does not exist: {file}; {e}")

    def delete_all_results(self):
        """Delete both the results directory (including configuration yaml and feedback file) as well as the participants housekeeping file."""
        for x in [self.dir, self.part_file]:
            self.delete_file(x)

    def merge_all_results(self, save_file=True):
        """Merge all results from the various participants into a single df and return as well as optionally save it.

        Keyword Arguments:
            save_file {bool} -- Whether to save the file; just return df if False (default: {True})

        Returns:
            tuple -- (path to the newly saved file, DF)
        """
        outfile = f"{self.config['experiment_title']}_results{self.config['results_file_extension']}"
        # Get results files from results directory
        results_files = glob.glob(
            os.path.join(self.dir, f'*{self.config["results_file_extension"]}')
        )

        # read in all the individual result files and concatenate them length-wise
        df_all = pd.concat([self.read_multi_ext(x) for x in results_files])

        if save_file:
            self.save_multi_ext(df_all, outfile)
            self.logger.info(
                f"Merged file with {len(results_files)} inputs saved: {outfile}"
            )

        return (outfile, df_all)

    def read_multi_ext(self, file):
        """Read csv, xlsx, and txt files and returns a pandas DataFrame.

        Arguments:
            file {str} -- File to read in

        Returns:
            df -- pandas DataFrame
        """
        _, extension = os.path.splitext(file)
        if extension == ".csv":
            df = pd.read_csv(file, sep=";")
        elif extension == ".xlsx":
            df = pd.read_excel(file)
        elif extension == ".txt":
            df = pd.read_table(file)
        return df

    def save_multi_ext(self, df, file):
        """Save a pandas DataFrame, depending on extension used in file name.

        Arguments:
            df {df} -- pandas DataFrame to save
            file {str} -- Name of the saved file
        """
        _, extension = os.path.splitext(file)
        if extension == ".csv":
            df.to_csv(file, sep=";", index=False)
        elif extension == ".xlsx":
            df.to_excel(file, sheet_name="Sheet1", index=False)
        elif extension == ".txt":
            df.to_table(file, index=False)

    def reorder_columns(self, df, item_col, sub_exp_col, item_number_col, cond_col):
        """Reorders the most important columns in a item list dataframe and appends all remaining ones. Returns the df.

        Arguments:
            df {df} -- pandas DataFrame to check
            sub_exp_col {str} -- Name of the subexperiment column
            item_number_col {str} -- Name of the item number column
            cond_col {str} -- Name of the conditions column

        Returns:
            df -- pandas df with reordered columns
        """
        # reorder the most important columns
        col_order = [item_col, sub_exp_col, item_number_col, cond_col]
        # and just add the remaining columns (if any)
        new_cols = col_order + (df.columns.drop(col_order).tolist())
        return df[new_cols]

    def check_permutations(self, df, item_number_col, cond_col, conditions):
        """Check whether all permutations of items and conditions are present in a data frame. Checking method for 'to_latin_square'.

        Arguments:
            df {df} -- pandas DataFrame to check
            item_number_col {str} -- Name of the item number column
            cond_col {str} -- Name of the conditions column
            conditions {list} -- List of unique conditions

        Raises:
            Exception: When not all permutations are present in the df
        """
        # do a cartesian product of item numbers and conditions
        products = [
            (item, cond) for item in set(df[item_number_col]) for cond in conditions
        ]
        # check if all such products exist in the dataframe
        check_list = [
            ((df[item_number_col] == item) & (df[cond_col] == cond)).any()
            for item, cond in products
        ]
        # if they are not all there, raise an error and show which combos are missing
        self.test_that(
            all(check_list),
            f"Not all permutations of items and conditions present in the dataframe: {[''.join(map(str, product)) for product, boolean in zip(products, check_list) if not boolean]}",
        )

    def to_latin_square(
        self,
        df,
        outname,
        sub_exp_col="sub_exp",
        cond_col="cond",
        item_col="item",
        item_number_col="item_number",
    ):
        """Take a dataframe with all conditions and restructure it with Latin Square. Saves the files.

        Arguments:
            df {df} -- pandas Dataframe with all conditions for each item
            outname {str} -- Name for the saved files (uniqueness handled automatically); include extension

        Keyword Arguments:
            sub_exp_col {str} -- Column containing the subexperiment identifier (default: {"sub_exp"})
            cond_col {str} -- Column containing the condition identifiers (default: {"cond"})
            item_col {str} -- Column with the item text (default: {"item"})
            item_number_col {str} -- Column with the item number (default: {"item_number"})
        """
        dfs_critical = []
        name, extension = os.path.splitext(outname)
        # split the dataframe by the sub experiment value
        dfs = [pd.DataFrame(x) for _, x in df.groupby(sub_exp_col, as_index=False)]
        for frame in dfs:
            # get the unique condition values and sort them
            conditions = sorted(list(set(frame[cond_col])))
            # check whether all combos of items and conditions are present
            self.check_permutations(frame, item_number_col, cond_col, conditions)
            # rearrange the most important columns
            frame = self.reorder_columns(
                frame, item_col, sub_exp_col, item_number_col, cond_col
            )

            # for critical sub experiments generate the appropriate amount of lists
            if len(conditions) >= 1:
                for k in range(len(conditions)):
                    # order the conditions to match the list being created
                    lat_conditions = conditions[k:] + conditions[:k]
                    # look for the appriate rows in the argument df (using the conditions multiple times with 'cycle')
                    out_l = []
                    for item, cond in zip(
                        set(sorted(frame[item_number_col])), cycle(lat_conditions)
                    ):
                        out_l.append(
                            frame[frame.item_number.eq(item) & frame.cond.eq(cond)]
                        )
                    # add all the rows we found into a combined df
                    out_df = pd.concat(out_l)
                    # add frame to critical list
                    dfs_critical.append(out_df)
                # remove the frame from the dfs list (which will be the filler list at the end)
                dfs.remove(frame)

        # add the fillers to the critical lists
        for i, df in enumerate(dfs_critical):
            df = pd.concat([df, *dfs])
            # and save the lists
            self.save_multi_ext(df, f"{name}{i+1}{extension}")

    def send_confirmation_email(self):
        """Send confirmation e-mail to specified recipient with merged results file attached."""
        subject = f"{self.config['experiment_title']}: Experiment Finished"
        body = f"Dear User,\n\nThis is to let you know that your experiment {self.config['experiment_title']} has finished and all {self.config['participants']} participants have been tested. We have attached the results file ({self.outfile}') below.\n\nRegards,\nPyExpTK\n\n"
        sender_email = "pyexptk@gmail.com"
        password = "pyexp_1_2_3"

        # Create a multi-part message and set headers
        message = MIMEMultipart()
        message["From"] = sender_email
        # message["To"] = receiver_email
        message["Subject"] = subject
        # Recommended for mass emails
        message["Bcc"] = self.config["receiver_email"]

        # Add body to email
        message.attach(MIMEText(body, "plain"))

        # merged results
        filename = self.merge_all_results(save_file=True)[0]

        # Open file in binary mode
        with open(filename, "rb") as attachment:
            # Add file as application/octet-stream
            # Email client can usually download this automatically as attachment
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())

        # Encode file in ASCII characters to send by email
        encoders.encode_base64(part)

        # Add header as key/value pair to attachment part
        part.add_header(
            "Content-Disposition", f"attachment; filename= {filename}",
        )

        # Add attachment to message and convert message to string
        message.attach(part)
        text = message.as_string()

        # Log in to server using secure context and send email
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, self.config["receiver_email"], text)

        self.logger.info(f"Confirmation e-mail sent: {message['Bcc']}")

    """ SECTION IV: Buttons """

    def text_or_image_button(
        self, value, text=None, image=None, side="left", likert_append=True
    ):
        """Display a button in the judgment frame, either with text or images.

        Arguments:
            value {str} -- Value for the judgment when that button is clicked

        Keyword Arguments:
            text {str} -- Text next to the button (default: {None})
            image {tkinter image} -- Image next to the button (default: {None})
            side {str} -- Where to pack the button (default: {"left"})
            likert_append {bool} -- Whether to add the buttons to the likert list and disable them
        """
        # generate and place a button
        x = Radiobutton(
            self.frame_judg,
            image=image,
            text=text,
            variable=self.judgment,
            value=value,
            font=(self.config["font"], self.config["basesize"]),
        )
        x.pack(side=side, expand=True, padx=10)
        # option below used for spr controls and non-dynamic buttons in dynamic FC
        if likert_append:
            # add the buttons to the likert list and disable them
            self.likert_list.append(x)
            x.config(state="disabled")

    def judgment_buttons(self):
        """Display the likert, FC buttons or images used to give linguistic judgments."""
        # frame for the judgment buttons
        self.frame_judg = Frame(self.root, relief="sunken", bd=2)
        self.frame_judg.pack(side="top", pady=20)

        # get the Forced Choice options from the item file (either txt or img)
        if any([self.config["dynamic_fc"], self.config["dynamic_img"]]):
            self.dynamic_fc_buttons()
        # simply display the static likert buttons
        else:
            self.likert_style_buttons()

        if all(
            [self.config["use_text_stimuli"], not self.config["self_paced_reading"]]
        ):
            # enable likert choice after specified delay is over
            Timer(self.config["delay_judgment"], self.enable_submit).start()

    def likert_style_buttons(self):
        """Display likert style radio buttons, optionally with endpoints. Also used for (static) Forced Choice."""
        # endpoint 1
        if self.config["endpoints"][0]:
            scale_left = Label(
                self.frame_judg,
                text=self.config["endpoints"][0],
                font=(self.config["font"], self.config["basesize"]),
                fg="gray20",
            )
            scale_left.pack(side="left", expand=True, padx=10, pady=5)

        # create a button for each element in the likert list
        for x in self.config["likert"]:
            self.text_or_image_button(
                text=str(x), value=str(x).casefold().replace(" ", "_")
            )

        # endpoint 2
        if self.config["endpoints"][1]:
            scale_right = Label(
                self.frame_judg,
                text=self.config["endpoints"][1],
                font=(self.config["font"], self.config["basesize"]),
                fg="gray20",
            )
            scale_right.pack(side="left", expand=True, padx=10, pady=5)

    def dynamic_fc_buttons(self):
        """Display either image or text buttons that take their arguments from the item file (dynamic FC)."""
        self.fc_images = {}  # reset images dict
        for x, name in zip(
            self.items.iloc[self.i_ix, 4:], self.items.iloc[:, 4:].columns
        ):
            if self.config["dynamic_img"]:
                # store images in dict (otherwise they won't be displayed)
                self.fc_images[x] = self.resize_image(x)
                self.text_or_image_button(
                    value=str(name).casefold().replace(" ", "_"),
                    image=self.fc_images[x],
                    side=random.choice(["left", "right"]),
                )

            else:
                # just create the text buttons
                self.text_or_image_button(
                    text=str(x),
                    value=str(name).casefold().replace(" ", "_"),
                    side=random.choice(["left", "right"]),
                )

        if self.config["non_dynamic_button"]:
            self.text_or_image_button(
                text=self.config["non_dynamic_button"],
                value=self.config["non_dynamic_button"].casefold().replace(" ", "_"),
                likert_append=False,
                side="right",
            )

    def submit_button(self, continue_func, text=None):
        """Display a submit button that takes different continuation functions.

        Arguments:
            continue_func {function} -- Function that should be executed on button press

        Keyword Arguments:
            text {str} -- Text to be displayed on the button; if None, value will be taken from the config file (default: {None})
        """
        # display a line
        spacer_line = Frame(self.root, height=2, width=800, bg="gray90")
        spacer_line.pack(side="top", anchor="c", pady=20)

        # frame and button with text for the submit button
        frame_submit = Frame(self.root)
        frame_submit.pack(expand=False, fill="both", side="top", pady=10)
        self.submit = Button(
            frame_submit,
            text=text or self.config["button_text"],
            command=continue_func,
            fg="blue",
            font=(self.config["font"], self.config["basesize"] - 10),
            highlightcolor="gray90",
            highlightbackground="white",
            highlightthickness=0,
            padx=10,
            pady=5,
        )
        self.submit.pack()

    """ SECTION V: methods that are called upon button or keyboard presses """

    def create_masked_item(self):
        """Take item and mask words with underscores, depending on word counter. Return new string.

        Returns:
            str -- Masked item string
        """
        # replace all non-whitespace characters with underscores
        self.masked = re.sub("[^ ]", "_", self.items.iloc[self.i_ix, 0])
        # generate a list from the strings to be able to manipulate it
        masked_split = self.masked.split()

        # if cumulative option is selected, the word identified by counter and all previous ones will be shown
        if self.config["cumulative"]:
            masked_split[: self.w_ix] = self.items.iloc[self.i_ix, 0].split()[
                : self.w_ix
            ]
        # if non-cumulative, only the target word is displayed
        else:
            # if the index is zero, keep the string as it is
            if self.w_ix > 0:
                # otherwise show the word bearing the index - 1 (without the subtraction we would always skip the first word in the unmasking because of the previous part of the conditional)
                masked_split[self.w_ix - 1] = self.items.iloc[self.i_ix, 0].split()[
                    self.w_ix - 1
                ]

        # start the reaction times
        self.time_start = time.time()

        # return the new list as a space-separated string
        return " ".join(masked_split)

    def play_stimulus(self):
        """Play the file from the item list; either locally or via streaming it from an online source."""
        # start time we need for audio stimuli reaction time
        self.time_start = time.time()
        # play file
        self.sound.play()
        # after sound is over, change the value of played
        Timer(self.sound.get_length(), self.enable_submit).start()

    def update_play_button(self):
        if "https://" in self.items.iloc[self.i_ix, 0]:
            # google drive export link conversion to usable link for playback
            if self.config["google_drive_link"]:
                url = (
                    self.items.iloc[self.i_ix, 0]
                    .replace("file/d/", "uc?export=download&id=")
                    .replace("/view?usp=sharing", "")
                )
                url = BytesIO(urlopen(url).read())
            # for others, just use the link in the item file
            else:
                url = BytesIO(urlopen(self.items.iloc[self.i_ix, 0]).read())
            self.sound = pygame.mixer.Sound(url)
        else:
            # load file into mixer
            self.sound = pygame.mixer.Sound(self.items.iloc[self.i_ix, 0])

    def submit_participant_information(self):
        """Save all the meta fields to a list if all are filled out or display an error. On success, move on to exposition."""
        # store the entries of the fields in the final attribute
        meta_entries_temp = [x.get().casefold().strip() for x in self.meta_entries]
        # if any of the fields are empty, print out an error message
        if "" in meta_entries_temp:
            self.display_error(self.config["error_meta"])
        # if all selections were made, move on to exposition
        else:
            self.meta_entries = meta_entries_temp
            self.empty_window()
            self.start_exposition_phase()

    def next_word(self, event=None):
        """Increase the word counter and update the label text in self-paced-reading experiments. Record reaction times for each word in dictionary.

        Keyword Arguments:
            event {tkinter event} -- Argument not used; but tkinter button presses always pass an event that needs to be dealt with (default: {None})
        """
        # if the word is in the middle of the item, take the reaction times
        if self.w_ix > 0:
            # reaction times for the current word
            self.spr_reaction_times[self.w_ix] = time.time() - self.time_start
        # if all words have been shown, remask the item and activate the continue button
        if self.w_ix == len(self.items.iloc[self.i_ix, 0].split()):
            # re-mask the item text so that participants cant just read the entire item at the end (especially important in the cumulative version)
            self.item_text.config(text=self.masked)
            # allow continuation
            self.enable_submit()
        else:
            # if there are more words, increase word index
            self.w_ix += 1
            # and unmask next word
            self.item_text.config(text=self.create_masked_item())

    def submit_control(self):
        """Submit the judgment for self-paced reading control questions and move to the next item afterwards (if a choice was made)."""
        if self.judgment.get():
            self.logger.info(f"Control {self.i_ix + 1}/{len(self.items)}!")
            self.next_self_paced_reading_item()
        else:
            self.display_error(self.config["error_judgment"])

    def submit_judgment(self):
        """Submit the judgment (likert, FC, image) as well as the reaction times and continue to next item. If at the end of the item list, move on to critical section (if currently in warm-up) or feedback section."""
        # if there's a judgment, compute the reaction times, append to df and move on to next item
        if self.judgment.get():
            # reaction times: subtract start time from stop time to get reaction times
            reaction_time = time.time() - self.time_start
            if self.config["use_text_stimuli"]:
                # with text stimuli also subtract the delay
                reaction_time = reaction_time - self.config["delay_judgment"]
            # for audio stimuli, also subtract the length of the item (because judgments are available only after the item has been played anyway)
            else:
                reaction_time = reaction_time - self.sound.get_length()

            # progress report
            self.logger.info(f"Item {self.i_ix + 1}/{len(self.items)}!")

            # save the judgment and the reaction times
            self.save_dependent_measures(reaction_time)
            # move on to the next item (if any)
            self.next_item_general()
        # if no selection was made using the radio buttons, display error
        else:
            self.display_error(self.config["error_judgment"])

    def next_item_general(self):
        """General waypoint function that performs all necessary tasks to display a new item (if there are more to be shown)."""
        # reset buttons for next item and increase item counter
        self.judgment.set("")
        self.i_ix += 1
        # if there are more items to be shown, do that
        try:
            # reset the time counter for the reaction times
            self.time_start = time.time()
            # and delegate to the appropriate next_X function
            if self.config["use_text_stimuli"]:
                self.next_text_item()
            else:
                # update the play button and start streaming non-local files
                self.update_play_button()
                # disable buttons and play play button
                self.next_audio_item()
            # with dynamic experiment designs, update the judgment options
            if any([self.config["dynamic_fc"], self.config["dynamic_img"]]):
                self.update_judgment_buttons()
        # otherwise either go to the feedback section or enter the critical stage of the exp
        except IndexError:
            self.logger.info(f"No more items to show.")
            self.item_list_over()

    def item_list_over(self):
        """Either launch the feedback or critical section of the experiment (because all items were seen)"""
        self.empty_window()
        if self.critical:
            # remove the binding from the space bar
            self.root.unbind("<space>")
            # go to the feedback section
            self.display_feedback()
        # if we are at the end of the warm up phase, init critical
        else:
            self.start_item_phase()

    def save_dependent_measures(self, reaction_time=None):
        """Compile all the info we need for the results file and add it to the results dataframe.

        Keyword Arguments:
            reaction_time {int} -- Reaction times for current item; only used in non-self-paced-reading experiments (default: {None})
        """
        # add the date to the file
        today = datetime.date.today().strftime("%d/%m/%Y")
        # set up all the info that should be written to the file (in that order)
        out_l = [
            self.id_string,
            today,
            self.start_time,
            self.config["tester"],
            self.meta_entries,
            list(self.items.iloc[self.i_ix, 1:4]),
        ]
        # reaction times for all words
        if self.config["self_paced_reading"]:
            out_l = (
                out_l
                + [round(val, 5) for val in self.spr_reaction_times.values()]
                + [self.judgment.get()]
            )
        # judgments
        else:
            out_l = out_l + [self.judgment.get(), str(round(reaction_time, 5))]
        # flatten list of lists; turn to string, remove capital letters and add rows to pandas df
        self.outdf.loc[len(self.outdf)] = [
            str(item).casefold() for item in pd.core.common.flatten(out_l)
        ]

    def next_self_paced_reading_item(self):
        """Shows the next item in self-paced reading experiment, calls functions to save reaction times and judgments. At the end of item list, moves on to either critical section (if currently in warm-up) or the feedback section."""
        self.logger.info(f"Item {self.i_ix + 1}/{len(self.items)}!")
        self.save_dependent_measures()
        self.i_ix += 1

        try:
            # empty the stored reaction times
            self.spr_reaction_times = {}
            # reset the word index
            self.w_ix = 0
            # reset the control judgment
            self.judgment.set("")
            # and go back to the masked item frame
            self.empty_window()
            self.display_masked_item()
            self.submit.config(state="disabled")
        # otherwise either go to the feedback section or enter the critical stage of the exp
        except IndexError:
            self.logger.info(f"No more items to show.")
            self.item_list_over()

    def next_text_item(self):
        """Update the item text on the screen to show the new item and handle reaction times and button resets."""
        # disable the likert scale button
        for obj in self.likert_list:
            obj.config(state="disabled")
        # disable the submit button as well
        self.submit.config(state="disabled")
        # start the timer for reactivation
        Timer(self.config["delay_judgment"], self.enable_submit).start()
        # show new item
        self.item_text.config(text=self.items.iloc[self.i_ix, 0])

    def next_audio_item(self):
        """Disable the judgment and submit buttons and flash the play button."""
        # because the play button will automatically update itself to play the new item (bc of the item_num), we only need to disable the button for audio stimuli
        # check if the item is a link, if yes retrieve it
        self.submit.config(state="disabled")
        for obj in self.likert_list:
            obj.config(state="disabled")
        self.flash_play_button(0)

    def update_judgment_buttons(self):
        """Update the text/image for the FC buttons; order is randomized."""
        self.fc_images = {}
        for i, item, col in zip(
            random.sample(range(len(self.likert_list)), len(self.likert_list)),
            self.items.iloc[self.i_ix, 4:],
            self.items.iloc[:, 4:].columns,
        ):
            # use images instead of text with dynamic image FC (resize before display)
            if self.config["dynamic_img"]:
                self.fc_images[item] = self.resize_image(item)
                self.likert_list[i].config(value=col, image=self.fc_images[item])
            # change the text to that of the current item (since item counter has been incremented)
            else:
                self.likert_list[i].config(text=item, value=col)

    def save_complete_results(self):
        """Save the results and note that the participant completed all items."""
        # end the critical portion
        self.critical = False
        # add finished, duration, and feedback columns
        self.append_metrics()
        # save the results to disk
        self.save_multi_ext(self.outdf, self.outfile)
        self.logger.info(f"Results file saved: {self.outfile}")
        self.display_over()
        # TODO: add a test that checks that the df has as many rows as the item list and is as long as the current item index

    def enable_submit(self):
        """Unlock disabled submit buttons, either after a timer or after an event (like the audio finishing to play) has occurred."""
        # try to enable the likert the buttons and the submit buttons
        try:
            self.submit.config(state="normal")
            for obj in self.likert_list:
                obj.config(state="normal")
        # do nothing if they do not exist for whatever reason
        except AttributeError:
            pass

    def flash_play_button(self, count):
        """Flash the play button a number of times to encourage that it is clicked by rapidly color swapping.

        Arguments:
            count {int} -- Counter to keep track of how many flashes to perform still (necessary because function calls itself)
        """
        # get the colors
        bg = self.audio_btn.cget("highlightcolor")
        fg = self.audio_btn.cget("highlightbackground")
        # and then assign them to each other's original positions
        self.audio_btn.config(highlightcolor=fg, highlightbackground=bg)
        # count keeps track of how many swaps have been done
        count += 1
        # if the specified amount of flashes has not been reached call the function again, passing the updated count
        if count <= 10:
            self.audio_btn.after(100, self.flash_play_button, count)

    def on_closing(self):
        """Warn before closing the root experiment window with the system buttons."""
        # show a warning message that the exiting participant has to accept
        if messagebox.askokcancel("Quit", self.config["quit_warning"]):
            self.root.destroy()
            # if ended before intended ending, log that and handle results and feedback file
            self.logger.info("Experiment was quit.")
            if self.critical:
                self.unfinished_participant_results()


if __name__ == "__main__":
    logging.basicConfig(
        filename="experiment.log",
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)-8s - %(funcName)s - %(message)s",
    )

    Exp = Experiment("test.yaml")
    Exp.start_experiment()
    # print(Exp)
