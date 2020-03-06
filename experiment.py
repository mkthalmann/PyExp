# pylint: disable=no-member,W0614

import datetime
import glob
import json
import logging
import os
import random  # randomize items, and FC options
import re  # regular expressions
import shutil
import smtplib
import ssl
import statistics
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
from PIL import Image, ImageTk
from plotnine import *


'''
    TODO:
    - support for video stimuli
    - option to have several experimental blocks with a break inbetween

    FIXME:
    -
'''


class Window():
    """General class that harbors some methods for window handling, like centering or resizing operations."""

    def __init__(self):
        pass

    def center_window(self):
        """Center the window."""
        # Call all pending idle tasks - carry out geometry management and redraw widgets.
        self.root.update_idletasks()
        # Get width and height of the screen
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        # Calculate the x and y positions of the window
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        # assign the new geometry as well as the x, y positions
        self.root.geometry(f'{width}x{height}+{x}+{y}')

    def empty_window(self):
        """Gather all frames and content within them and delete them from view."""
        # get children
        widget_list = self.root.winfo_children()
        # add grandchildren
        for item in widget_list:
            if item.winfo_children():
                widget_list.extend(item.winfo_children())

        # delete all widgets
        for item in widget_list:
            item.pack_forget()

    def fullscreen(self):
        """Make the window fullscreen (Escape to return to specified geometry)."""
        self.root.geometry("{0}x{1}+0+0".format(
            self.root.winfo_screenwidth() - 3, self.root.winfo_screenheight() - 3))
        if self.config_dict["allow_fullscreen_escape"]:
            self.root.bind('<Escape>', self.return_geometry)

    def return_geometry(self, event):
        """Return to initially specified geometry from fullscreen."""
        self.root.geometry(self.config_dict["geometry"])


class Experiment(Window):
    """Main class for the experiment. Relies on python file upon instantiation with the settings to be used."""

    # class attribute: core values which need to stay the same over the course of one set of participants
    config_core = ["experiment_title", "meta_fields", "warm_up", 'non_dynamic_button', "warm_up_file", "use_text_stimuli",
                   "self_paced_reading", "cumulative", "likert", "dynamic_fc", "dynamic_img", "item_file", 'item_number_col',
                   'item_or_file_col', 'sub_exp_col', 'cond_col', 'extra_cols', "spr_control_options"]

    def __init__(self, config, window=True):
        """Initialie the experiment class and start up the tkinter GUI.

        Arguments:
            config {str} -- Python script name that contains the experiment's configuration parameters.

        Keyword Arguments:
            window {bool} -- Whether to initialize Tkinter and open a GUI window (default: {True})
        """
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.config_dict = self.get_config_dict(self.config)

        # all the Tkinter stuff that is not necessary when performing other functions, like plotting or creating Latin squares
        # will prevent a window from opening
        if window:
            self.root = Tk()
            self.setup_gui()
            self.judgment = StringVar()
            self.feedback = StringVar()
            self.logo = self.resize_image(self.config_dict["logo"], 100)
            if not self.config_dict["use_text_stimuli"]:
                self.playimage = self.resize_image(os.path.join(
                    "media", "play.png"), 100)

        # time of testing
        self.exp_start = time.time()  # track eperiment duration
        self.start_time = datetime.datetime.now().strftime("%H:%M:%S")
        self.today = datetime.date.today().strftime("%d/%m/%Y")

        # housekeeping files which track participants and experiment configuration
        self.part_file = self.config_dict["experiment_title"] + \
            "_participants.txt"
        self.resultsdir = f"{self.config_dict['experiment_title']}_results"
        self.config_file = os.path.join(self.resultsdir, "config.json")

        # store meta data
        self.meta_entries = []
        self.meta_entries_final = []

        # item stuff
        self.item_list_no = ""
        self.likert_list = []
        self.item_num = 0
        self.word_index = 0  # for self-paced reading
        self.masked = ""

        # reaction times
        self.time_start = ""
        self.spr_reaction_times = {}  # for self-paced reading

        self.fc_images = {}  # for dynamic FC with images
        # phase checker dict; for critical phase, finished exp, and quit application
        self.phases = dict.fromkeys(
            ["critical", "finished", "quit", "problem"], False)

    def setup_gui(self):
        """Generate the window title and perform some general setups."""
        self.root.wm_title(self.config_dict["window_title"])
        self.root.geometry(self.config_dict["geometry"])
        self.fullscreen(
        ) if self.config_dict["fullscreen"] else self.center_window()
        # add close warning
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def __str__(self):
        core_dict = {k: self.config_dict[k] for k in self.config_core}
        return "\nExperiment with the following core settings:\n" + '\n'.join(['{key} = {value}'.format(key=key, value=core_dict.get(key)) for key in core_dict])

    def __repr__(self):
        return f"Experiment('{self.config}')"

    ''' SECTION I: initializing methods for the various phases of the experiment '''

    def start_experiment(self):
        """Initialize the meta-data collection section of the experiment."""
        if self.check_config():
            self.display_spacer_frame()
            self.housekeeping()
            # only display the stuff below if more participants are needed and if the housekeeping check was fine
            if self.part_num < self.config_dict["participants"] and not self.phases["problem"]:
                self.id_generator()
                self.display_meta_information_forms()
                self.submit_button(self.save_participant_information)
        else:
            self.display_long(
                f"You seem to have edited some of the configuration identifiers in {self.config}.\nThe experiment cannot proceed unless all and only those keys are present which are supposed to be there.")
        self.root.mainloop()

    def start_exposition_phase(self):
        """Initialize the expository section of the experiment. Inform participant about the experimental task and procedure."""
        self.logger.info("Starting exposition.")
        self.display_spacer_frame()
        self.display_long(self.config_dict["expo_text"], 8)
        self.submit_button(self.exit_exposition)

    def start_warm_up_phase(self):
        """Initialize the warm-up section of the experiment. Only if specified by the user."""
        self.retrieve_items(
            self.config_dict["warm_up_file"], self.config_dict["warm_up"])
        self.prepare_results_df()
        self.logger.info("Starting Warm-Up phase.")
        self.display_spacer_frame()
        self.display_short(self.config_dict["warm_up_title"], 5)
        self.display_short(self.config_dict["warm_up_description"])
        self.init_items()

    def start_critical_phase(self):
        """Initialize the critical section of the experiment."""
        self.phases["critical"] = True
        self.logger.info("Starting critical phase.")
        self.housekeeping_file_update()
        self.retrieve_items(self.config_dict["item_file"])
        if not self.config_dict["warm_up"]:
            self.prepare_results_df()
        self.display_spacer_frame()
        self.display_short(self.config_dict["title"], 5)
        self.display_short(self.config_dict["description"])
        self.init_items()

    def init_items(self):
        """Display the various kinds of elements needed for the different types of experiments (text, play and submit buttons, likert scale, ...)."""
        if self.config_dict["self_paced_reading"]:
            self.display_masked_item()
            self.submit.config(state="disabled")
        else:
            if self.config_dict["use_text_stimuli"]:
                self.display_text_item()
            else:
                pygame.init()
                self.display_audio_stimulus()
            self.judgment_buttons()
            self.submit_button(self.submit_judgment)
            self.submit.config(state="disabled")
        self.time_start = time.time()

    def experiment_finished(self):
        """Show message when all necessary participants have been tested and button to exit the GUI."""
        # show the 'thank you for your interest, but'-message and display exit button
        self.display_long(self.config_dict["finished_message"], 8)
        self.submit_button(self.root.destroy, "Exit")
        self.logger.info(
            f"All Participants have been tested. If you want to test more than {self.config_dict['participants']} people, increase the amount in the specs file!")

        # send confirmation e-mail if so specified
        if self.config_dict["confirm_completion"]:
            self.send_confirmation_email()

    ''' SECTION II: display methods used by the initializing functions '''

    def display_short(self, text, size_mod=0, side="top"):
        """Display a short message without word wrap enabled."""
        # only instantiate frame and label if there's actually text to display
        if text:
            frame = Frame(self.root)
            frame.pack(expand=False, fill="both", side="top", pady=2)
            label = Label(frame, text=text, font=(
                self.config_dict["font"], self.config_dict["basesize"] + size_mod))
            label.pack(pady=2, side=side)

    def display_long(self, text, size_mod=0):
        """Display a long message with word wrap enabled."""
        # only instantiate frame and label if there's actually text to display
        if text:
            frame = Frame(self.root)
            frame.pack(expand=False, fill="both",
                       side="top", pady=10, padx=25)
            label = Label(frame, font=(self.config_dict["font"], self.config_dict["basesize"] + size_mod),
                          text=text, height=10, wraplength=1000)
            label.pack()

    def display_meta_information_forms(self):
        """Display the instructions and the meta labels as well as the entry fields for all user-specified meta information that is to be collected."""
        self.display_short(self.config_dict["meta_instruction"], -5)

        # create frame and label for each of the entry fields
        for i in range(len(self.config_dict["meta_fields"])):
            row = Frame(self.root)
            lab = Label(row, width=15, text=self.config_dict["meta_fields"][i], anchor='w', font=(
                self.config_dict["font"], self.config_dict["basesize"] - 8))
            # create the entry fields and store them
            self.meta_entries.append(Entry(row))

            # deploy all of it
            row.pack(side="top", padx=5, pady=5)
            lab.pack(side="left")
            self.meta_entries[i].pack(side="right", expand=True, fill="x")

    def retrieve_items(self, filename, warm_up=False):
        """Retrieve the items from the specified item file and randomize their order if specified. Items are stored in items object."""
        # with warm-up, there's no need to add the item list number, since there's only one file
        if warm_up:
            infile = filename
        # if were in the critical phase
        else:
            # load the correct item file for the specific participant
            infile = filename + str(self.item_list_no)

        # read in the conditions file
        df_items = self.read_multi_ext(
            f"{infile}{self.config_dict['item_file_extension']}")

        # if so specified and we're past the warm-up phase, randomize the items
        if self.config_dict["items_randomize"] and self.phases["critical"]:
            df_items = df_items.sample(frac=1).reset_index(drop=True)

        # rearrange the columns of the data frame using the entries in item_file_columns
        columns_to_order = list(pd.core.common.flatten([self.config_dict['item_or_file_col'], self.config_dict['sub_exp_col'],
                                                        self.config_dict['item_number_col'], self.config_dict['cond_col'], self.config_dict['extra_cols']]))
        # add the remaining columns after the ones we need in a specific order (if any)
        columns_to_order = columns_to_order + \
            (df_items.columns.drop(columns_to_order).tolist())
        try:
            # try to rearrange the columns
            df_items = df_items[columns_to_order]
            # assign the df as a instance property
            self.items = df_items
        # if some of the columns aren't present, log them
        except KeyError as e:
            self.logger.error(
                f"Column mismatch. Check the following values: {e}")

    def display_text_item(self):
        """Display frame and label for text items."""
        frame_item = Frame(self.root)
        frame_item.pack(expand=False, fill="both",
                        side="top", pady=10, padx=25)
        self.item_text = Label(frame_item, font=(
            self.config_dict["font"], self.config_dict["basesize"] + 7), text=self.items.iloc[0, self.item_num], height=6, wraplength=1000)
        self.item_text.pack()

    def display_audio_stimulus(self):
        """Display frame, label, and play button for audio items."""
        frame_audio = Frame(self.root, height=10)
        frame_audio.pack(expand=False, fill="both",
                         side="top", pady=10, padx=25)
        # display the play button with text and an image next to it
        self.audio_btn = Button(frame_audio, text=self.config_dict["audio_button_text"], image=self.playimage, compound="left", fg="black", font=(
            self.config_dict["font"], self.config_dict["basesize"]), padx=20, pady=25, command=lambda: self.play_stimulus())
        self.audio_btn.pack(side="top")

    def display_masked_item(self):
        """Display frame, label, and button for masked items in self-paced reading"""
        frame_item = Frame(self.root)
        frame_item.pack(expand=False, fill="both",
                        side="top", pady=10, padx=25)
        # label for the frame; text is the continuously unmasked item (word for word)
        self.item_text = Label(frame_item, font=(
            self.config_dict["font_mono"], self.config_dict["basesize"] + 8), text=self.create_masked_item(), height=9, wraplength=1000)
        self.item_text.pack()
        self.submit_button(self.display_control_questions)

        # FIXME: something is wrong such that sometimes when you press the spacebar shortly after exiting the exposition, you get taken back to the expo section
        # a delay helps
        time.sleep(.1)
        # press the space bar to show next word
        self.root.bind('<space>', self.next_word)

    def create_masked_item(self):
        """Take item and mask letters and words with underscores, depending on word counter."""
        # replace all non-whitespace characters with underscores
        self.masked = re.sub(
            "[^ ]", "_", self.items.iloc[self.item_num, 0])
        masked_split = self.masked.split()

        # if cumulative option is selected, the word identified by counter and all previous ones will be shown
        if self.config_dict["cumulative"]:
            for i in range(self.word_index):
                masked_split[i] = self.items.iloc[self.item_num, 0].split()[
                    i]
        # if non-cumulative, only the target word is displayed
        else:
            # if the index is zero, dont unmask anything
            if self.word_index == 0:
                masked_split = masked_split
            # otherwise show the word bearing the index - 1 (without the subtraction we would always skip the first word in the unmasking because of the previous part of the conditional)
            else:
                masked_split[self.word_index - 1] = self.items.iloc[self.item_num, 0].split()[
                    self.word_index - 1]

        # start the reaction times
        self.time_start = time.time()

        return " ".join(masked_split)

    def display_control_questions(self):
        """Display the control questions for self-paced reading items, including FC options and a submit button."""
        # empty window, display logo etc and show the control questions from the item file
        self.empty_window()
        self.display_spacer_frame()
        self.display_long(self.items.iloc[self.item_num, 4])

        # place the judgment buttons, taking the text from the config file
        self.frame_judg = Frame(self.root, relief="sunken", bd=2)
        self.frame_judg.pack(side="top", pady=20)
        for x in self.config_dict['spr_control_options']:
            self.text_or_image_button(text=str(x), value=str(
                x).casefold().replace(" ", "_"), likert_append=False)
        self.submit_button(self.submit_control)
        # button is disabled by default, but we wanna enable it here
        self.submit.config(state="normal")

    def display_feedback(self):
        """Display instructions and entry field for feedback after the critical section."""
        # save the results
        self.save_complete_results()
        # unless the feedback text is empty, show a frame to allow feedback entry
        if self.config_dict["feedback"]:
            # instruction for the feedback
            self.display_spacer_frame()

            feedback_frame = Frame(self.root)
            feedback_frame.pack(expand=False, fill="both",
                                side="top", pady=10, padx=25)
            label = Label(feedback_frame, text=self.config_dict["feedback"],
                          font=(self.config_dict["font"], self.config_dict["basesize"] - 5))
            label.pack(pady=15, side="top")

            # entry field for the feedback
            self.feedback = Entry(feedback_frame)
            self.feedback.pack(side="top", expand=True,
                               fill="x", ipady=5, padx=50)

            # button to submit the feedback
            self.submit_button(self.save_feedback)
        else:
            self.display_over()

    def save_complete_results(self):
        """Save the results and note that the participant completed all items."""
        # end the critical portion
        self.phases["critical"] = False
        # add a column to the results indicating that the participants finished the critical portion entirely
        self.outdf['finished'] = "T"
        # save the results to disk
        self.save_multi_ext(self.outdf, self.outfile)
        self.logger.info(f"Results file saved: {self.outfile}")

    def display_over(self):
        """Show goodbye message and exit button."""
        self.empty_window()
        self.display_spacer_frame()
        self.display_long(self.config_dict["bye_message"], 10)
        self.phases["finished"] = True
        self.logger.info("Experiment has finished.")
        self.submit_button(self.on_closing, "Exit")
        print(self.outdf)

    def display_spacer_frame(self):
        """Display frame with logo and line that appears at the top of every stage of the experiment."""
        spacer_frame = Frame(self.root)
        spacer_frame.pack(side="top", fill="both")
        # label with logo instead of text
        spacer_img = Label(spacer_frame, image=self.logo)
        spacer_img.pack(fill="x")
        self.display_line()

    def display_line(self):
        """Display a horizontal line."""
        spacer_line = Frame(self.root, height=2, width=800, bg="gray90")
        spacer_line.pack(side="top", anchor="c", pady=20)

    def display_error(self, text):
        """Frame and label for error messages that appear if entry fields are blank. Disappears after a delay."""
        error_label = Label(self.root, font=(
            self.config_dict["font"], self.config_dict["basesize"] - 8), text=text, fg="red")
        error_label.pack(side="top", pady=10)
        error_label.after(800, lambda: error_label.destroy())

    ''' SECTION III: file management methods '''

    def get_config_dict(self, config):
        """Import the configuration file (python script) by removing all comments and then return it as a dictionary."""
        with open(config, "r") as file:
            config_list = file.read().splitlines()
        # remove all comments
        variable_list = [x.strip().split("#")[0]
                         for x in config_list if x.strip().split("#")[0]]
        # add all values to a dictionary
        config_dict = {key: eval(value)
                       for (key, value) in [variable.split(" = ") for variable in variable_list]}
        return config_dict

    def check_config(self):
        """Check that the configuration file has not been modified from what is expected in the application and return boolean."""
        compare_config = {'fullscreen', 'allow_fullscreen_escape', 'geometry', 'window_title', 'experiment_title', 'confirm_completion', 'receiver_email', 'tester', 'logo', 'meta_instruction', 'meta_fields', 'expo_text', 'warm_up', 'warm_up_title', 'warm_up_description', 'warm_up_file', 'use_text_stimuli', 'self_paced_reading', 'cumulative', 'title', 'description', 'likert', 'endpoints', 'dynamic_fc', 'non_dynamic_button', 'dynamic_img', 'google_drive_link',
                          'delay_judgment', 'participants', 'remove_unfinished', 'remove_ratio', 'item_lists', 'item_file', 'item_file_extension', 'item_number_col', 'item_or_file_col', 'sub_exp_col', 'cond_col', 'extra_cols', "spr_control_options", 'items_randomize', 'results_file', 'results_file_extension', 'feedback', 'audio_button_text', 'button_text', 'finished_message', 'bye_message', 'quit_warning', 'error_judgment', 'error_meta', 'font', 'font_mono', 'basesize'}
        # allow to proceed if the check was passed and all keys are as they should be
        if compare_config == set(self.config_dict.keys()):
            self.logger.info(
                f"Configuration file {self.config} passed the completeness check.")
            return True
        # stop the experiment from proceeding
        else:
            self.logger.warning(
                f"These entries are either missing from {self.config} or have been added to it: {compare_config^set(self.config_dict.keys())}")
            return False

    def id_generator(self, size=15, chars=string.ascii_lowercase + string.ascii_uppercase + string.digits):
        """Generate a random participant id and set it as the id_string property."""
        self.id_string = ''.join(random.choice(chars) for _ in range(size))
        self.logger.info(f"New Participant ID generated: {self.id_string}")

    def housekeeping(self):
        """Store and retrieve participant number from file as well as the configuration settings as a json file. Also checks that configuration has not changed between different runs of the same experiment."""
        # check if the results path exists, if it doesn't, create it
        if not os.path.isdir(self.resultsdir):
            os.makedirs(self.resultsdir)
        # read in the participant and the config json files
        try:
            self.read_housekeeping_files()
        # if they can't be found (because its a new experiment), create them
        except FileNotFoundError as e:
            self.create_housekeeping_files()
            self.logger.info(
                f"Housekeeping file '{self.part_file}' not found, creating one instead: {e}")
        # assign participant to an item list (using the modulo method for latin square)
        self.item_list_no = self.part_num % self.config_dict["item_lists"] + 1

    def create_housekeeping_files(self):
        """Create both the file that stores the number of participants tested and the json file that stores the experiment settings."""
        # set the participant number to 0 and write it to the housekeeping file
        # to track how many people still need to be tested
        self.part_num = 0
        with open(self.part_file, 'a') as file:
            file.write(str(self.part_num))
        # save self.config_dict in the results directory to validate on later runs that the same settings are being used
        with open(self.config_file, "w", encoding='utf-8') as file:
            json.dump(self.config_dict, file, ensure_ascii=False, indent=4)

    def read_housekeeping_files(self):
        """Read the file that stores the number of participants tested and, if there are more to test, call the json file check."""
        # read in the participant file
        with open(self.part_file, 'r') as file:
            self.part_num = int(file.read())
        # don't proceed if the experiment is over already
        if self.part_num == self.config_dict["participants"]:
            self.experiment_finished()
        # check the settings json file
        else:
            self.check_housekeeping_files()

    def check_housekeeping_files(self):
        """Check if the saved json config file is set to the same parameters as the file used to inititialize the class. Throw a warning if not."""
        # read in the json file
        with open(self.config_file, "r") as file:
            compare_config = json.load(file)
        # compare the core entries, as opposed to all of them; changing the font size in the middle of the exp shouldn't be a problem
        if {k: self.config_dict[k] for k in self.config_core} == {k: compare_config[k] for k in self.config_core}:
            self.logger.info(
                f"Configuration check passed. Core settings in {self.config} have not been modified from previous participants.")
        # if core elements were changed indicate on as such on GUI screen and in log file
        else:
            self.display_long(
                f"The configurations for the currently running experiment have changed from previous participants.\nCheck '{self.config}' or start a new experiment (e.g. by changing the experiment title) to proceed.")
            self.logger.warning(
                f"Config dict: { {k: self.config_dict[k] for k in self.config_core} }\nCompare dict: { {k: compare_config[k] for k in self.config_core} }")
            # also display and exit button
            self.submit_button(self.root.destroy, "Exit")
            # stop the display of other elements
            self.phases["problem"] = True

    def housekeeping_file_update(self):
        """Increase the participant number and write it to the participants housekeeping file."""
        # increase participant number
        self.part_num += 1
        # write participant number to the housekeeping file
        with open(self.part_file, 'w') as file:
            file.write(str(self.part_num))
        self.logger.info(
            f"Starting with Participant Number {self.part_num}/{self.config_dict['participants']} now! Participant was assigned to Item File {self.item_list_no}")

    def prepare_results_df(self):
        """Initialize the results df with appropriate header depending on the experiment. Set the df as outdf."""
        # outfile in new folder with id number attached
        name = f"{self.config_dict['results_file']}_{str(self.part_num).zfill(len(str(self.config_dict['participants'])))}_{self.id_string}{self.config_dict['results_file_extension']}"
        # system independent path to file in results directory
        self.outfile = os.path.join(self.resultsdir, f"{name}")
        # generate a list with the header names for the results df
        header_list = ["id", "date", "start_time", "tester",
                       self.config_dict["meta_fields"], "sub_exp", "item", "cond"]
        # for standard judgment experiments (either text or audio)
        if self.config_dict["self_paced_reading"]:
            # add a column for each word in the item (of the first item)
            header_list = header_list + \
                [self.items.iloc[0, 0].split(), "control"]
        else:
            # add judgments and reaction times
            header_list = header_list + ["judgment", "reaction_time"]
        # flatten the list of lists, remove capitalization and spaces (mainly from meta fields)
        header_list = [item.casefold().replace(" ", "_")
                       for item in pd.core.common.flatten(header_list)]
        # initilize the results df
        self.outdf = pd.DataFrame(columns=header_list)

    def resize_image(self, x, desired_width=250):
        """Resize and return images for dynamic forced choice tasks."""
        image = Image.open(x)
        # compute rescaled dimensions
        new_dimensions = (int(image.width / (image.width / desired_width)),
                          int(image.height / (image.width / desired_width)))
        image = image.resize(new_dimensions, Image.ANTIALIAS)
        return ImageTk.PhotoImage(image)

    def unfinished_participant_results(self):
        """Depending on user settings, delete or keep data from experiment runs that were ended before the intended stopping point."""
        # if specified by user, do not save unfinished participant results (according to the given ratio)
        if self.config_dict["remove_unfinished"]:
            if self.item_num < len(self.items) * self.config_dict["remove_ratio"]:
                # also reduce the participant number in the housekeeping file
                self.part_num -= 1
                with open(self.part_file, 'w') as file:
                    file.write(str(self.part_num))
                self.logger.info(
                    "Participant will not be counted towards the amount of people to be tested.")
        # if not specified, save the dataframe
        else:
            # add a column with a constant value showing that the participant did not finish the exp
            self.outdf['finished'] = 'F'
            self.save_multi_ext(self.outdf, self.outfile)
            self.logger.info(
                f"Results file will not be deleted and participant will count. Saved file: {self.outfile}")

    def delete_file(self, file):
        """Delete files or directories."""
        try:
            os.remove(file)
            self.logger.info(f"File deleted: {file}")
        # if permission error, then the file is a dir and we need a different function
        except PermissionError as e:
            shutil.rmtree(file)
            self.logger.info(
                f"Directory and all contained files deleted: {file}")
        # log if the file could not be found
        except FileNotFoundError as e:
            self.logger.warning(f"File does not exist: {file}; {e}")

    def delete_all_results(self):
        """Delete both the results directory (including configuration json and feedback file) as well as the participants housekeeping file."""
        for x in [self.resultsdir, self.part_file]:
            self.delete_file(x)

    def merge_all_results(self, save_file=True):
        """Merge all results from the various participants into a single df and return as well as optionally save it.

        Keyword Arguments:
            save_file {bool} -- Whether to save the file; just return df if False (default: {True})

        Returns:
            df -- pandas DataFrame containing all the merged results
        """
        outfile = self.config_dict["experiment_title"] + \
            "_results_full" + self.config_dict["results_file_extension"]
        # Get results files
        results_files = sorted(
            glob.glob(os.path.join(
                self.resultsdir, f'*{self.config_dict["results_file_extension"]}')))

        # remove the feedback file
        try:
            results_files.remove(os.path.join(
                self.resultsdir, f'FEEDBACK{self.config_dict["results_file_extension"]}'))
        except ValueError as e:
            self.logger.info(f"Feedback file not in file list: {e}")
        # print out which files were found as well as their size
        self.logger.info(f'Found {len(results_files)} results files:')
        for file in results_files:
            # log the files that were combined and their size
            self.logger.info(
                f"{file} \t {round(os.path.getsize(file) / 1000, 3)} KB")

        # read in all the individual result files and concatenate them length-wise
        dfs = [self.read_multi_ext(x) for x in results_files]
        df_all = pd.concat(dfs)

        if save_file:
            self.save_multi_ext(df_all, outfile)

        self.logger.info(f"Merged results file generated: {outfile}")

        return df_all

    def generate_plot(self, df, dv, by=""):
        """Generate a and return plot to have an overview of the results

        Arguments:
            df {pandas DF} -- DataFrame containing the results (e.g. from self.merge_all_results)
            dv {str} -- Dependent variable (judgment; reaction_time)

        Keyword Arguments:
            by {str} -- add to generate facets; e.g. 'item' or 'item + id' (default: {""})

        Returns:
            plot -- Seaborn plot object that can be printed
        """
        plot = (ggplot(df, aes("cond", dv, color="cond", pch="cond", group=1))
                # points and lines for means
                + geom_point(stat="summary", fun_y=statistics.mean)
                + geom_line(stat="summary",
                            fun_y=statistics.mean, color="gray")
                # error bars with 95 % CI
                + stat_summary(fun_data='mean_cl_normal',
                               geom="errorbar", width=0.25)
                # single observations as points
                + geom_jitter(alpha=.3, width=.2)
                # no legend
                + guides(color=False, pch=False)
                + theme_minimal()
                + labs(y=f"{dv} +/- 95%CI"))
        # with a faceting argument, add facets to the plot
        if by:
            plot = (plot + facet_wrap(f"~ {by}"))
        return plot

    def read_multi_ext(self, file, extension=None):
        """Read csv, xlsx, and txt files and returns a pandas DataFrame.

        Arguments:
            file {str} -- File to read in

        Keyword Arguments:
            extension {str} -- Extension of the file; inferred if None (default: {None})

        Returns:
            df -- pandas DataFrame
        """
        if extension is None:
            _, extension = os.path.splitext(file)
        if extension == ".csv":
            df = pd.read_csv(file, sep=";")
        elif extension == ".xlsx":
            df = pd.read_excel(file)
        elif extension == ".txt":
            df = pd.read_table(file)
        return df

    def save_multi_ext(self, df, file, extension=None):
        """Save a pandas DataFrame, depending on extension used in outname or given explicitly.

        Arguments:
            df {df} -- pandas DataFrame to save
            file {str} -- Name of the saved file

        Keyword Arguments:
            extension {str} -- Extension of the file; inferred if None (default: {None})
        """
        if extension is None:
            _, extension = os.path.splitext(file)
        if extension == ".csv":
            df.to_csv(file, sep=';', index=False)
        elif extension == ".xlsx":
            df.to_excel(file, sheet_name='Sheet1', index=False)
        elif extension == ".txt":
            df.to_table(file, index=False)

    def to_latin_square(self, df, outname, sub_exp_col="sub_exp", cond_col="cond", item_col="item", item_number_col="item_number"):
        """Take a dataframe with all conditions and restructure it with Latin Square. Saves the files.

        Arguments:
            df {df} -- pandas Dataframe with all conditions for each item
            outname {str} -- Name for the saved files (uniqueness handled automatically); include extension

        Keyword Arguments:
            sub_exp_col {str} -- Column containing the subexperiment identifier (default: {"sub_exp"})
            cond_col {str} -- Column containing the condition identifiers (default: {"cond"})
            item_col {str} -- Column with the item text (default: {"item"})
            item_number_col {str} -- Column with the item number (default: {"item_number"})

        Returns:
            list -- List with all the names of the files that were saved to disk
        """
        # two lists we will be adding the split-up dfs to
        dfs_critical = []
        dfs_filler = []
        # get the extension so we can reuse it for saving process
        name, extension = os.path.splitext(outname)
        # split the dataframe by the sub experiment value
        dfs = [pd.DataFrame(x) for _, x in df.groupby(
            sub_exp_col, as_index=False)]
        for frame in dfs:
            # get the unique condition values and sort them
            conditions = sorted(list(set(frame[cond_col])))

            # do a cartesian product of item numbers and conditions
            products = [(item, cond) for item in set(frame[item_number_col])
                        for cond in conditions]
            # check if all such products exist in the dataframe
            check_list = [((frame[item_number_col] == item)
                           & (frame[cond_col] == cond)).any() for item, cond in products]
            # list the missing combinations
            missing_combos = ', '.join([''.join(map(str, product)) for product, boolean in zip(
                products, check_list) if not boolean])

            # stop the process if not all permutations are present
            if not all(check_list):
                raise Exception(
                    f"Not all permutations of items and conditions are present in the dataframe. Missing combinations: {missing_combos}")

            # generate the appropriate amount of lists
            for k in range(len(conditions)):
                # order the conditions to match the list being created
                lat_conditions = conditions[k:] + conditions[:k]
                # generate (and on subsequent runs reset) the new df with all the columns in the argument df
                out_df = pd.DataFrame(columns=frame.columns)
                # look for the appropriate rows in the argument df (using the conditions multiple times with 'cycle')
                for item, cond in zip(set(sorted(frame[item_number_col])), cycle(lat_conditions)):
                    # find the row in questions
                    out_l = [out_df, frame.loc[(frame[item_number_col] == item) &
                                               (frame[cond_col] == cond)]]
                    # add it at the end of the dataframe
                    out_df = pd.concat(out_l)
                # reorder the most important columns
                columns_to_order = [item_col, sub_exp_col,
                                    item_number_col, cond_col]
                # and just add the rest (if any)
                new_columns = columns_to_order + \
                    (out_df.columns.drop(columns_to_order).tolist())
                out_df = out_df[new_columns]
                # add multi-list dfs to the critical list
                if len(lat_conditions) > 1:
                    dfs_critical.append(out_df)
                # add single-condition dfs to the filler dict
                else:
                    dfs_filler.append(out_df)

        # add all filler lists to the critical ones
        for filler in dfs_filler:
            # replace the current df with the longer version containing the fillers as well
            for i, df in enumerate(dfs_critical):
                dfs_critical[i] = pd.concat([df, filler])

        # save all lists individually with a suffix corresponding to the differnt lists
        for i, df in enumerate(dfs_critical):
            save_multi_ext(df, f"{name}{i+1}{extension}")

    def send_confirmation_email(self):
        """Send confirmation e-mail to specified recipient with merged results file attached."""
        subject = f"{self.config_dict['experiment_title']}: Experiment Finished"
        body = f"Dear User,\n\nThis is to let you know that your experiment {self.config_dict['experiment_title']} has finished and all {self.config_dict['participants']} participants have been tested. We have attached the results file ({self.config_dict['experiment_title'] + '_results_full.csv'}) below.\n\nRegards,\nPyExpTK\n\n"
        sender_email = "pyexptk@gmail.com"
        password = "pyexp_1_2_3"

        # Create a multi-part message and set headers
        message = MIMEMultipart()
        message["From"] = sender_email
        # message["To"] = receiver_email
        message["Subject"] = subject
        # Recommended for mass emails
        message["Bcc"] = self.config_dict["receiver_email"]

        # Add body to email
        message.attach(MIMEText(body, "plain"))

        # merged results
        self.merge_all_results(save_file=True)
        filename = self.config_dict["experiment_title"] + "_results_full.csv"

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
            "Content-Disposition",
            f"attachment; filename= {filename}",
        )

        # Add attachment to message and convert message to string
        message.attach(part)
        text = message.as_string()

        # Log in to server using secure context and send email
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender_email, password)
            server.sendmail(
                sender_email, self.config_dict["receiver_email"], text)

        self.logger.info(
            f"Confirmation e-mail sent to:\t{self.config_dict['receiver_email']}\nAttached file:\t{filename}")

    ''' SECTION IV: Buttons '''

    def text_or_image_button(self, value, text=None, image=None, side="left", likert_append=True):
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
        x = Radiobutton(self.frame_judg, image=image, text=text, variable=self.judgment, value=value, font=(
            self.config_dict["font"], self.config_dict["basesize"]))
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
        if self.config_dict["dynamic_fc"] or self.config_dict["dynamic_img"]:
            self.dynamic_fc_buttons()

        # simply display the static likert buttons
        else:
            self.likert_style_buttons()

        if self.config_dict["use_text_stimuli"] and not self.config_dict["self_paced_reading"]:
            # enable likert choice after specified delay is over
            read_item_timer = Timer(
                self.config_dict["delay_judgment"], self.enable_submit)
            read_item_timer.start()

    def likert_style_buttons(self):
        """Display likert style radio buttons, optionally with endpoints. Also used for (static) Forced Choice."""
        # endpoint 1
        if self.config_dict["endpoints"][0]:
            scale_left = Label(self.frame_judg, text=self.config_dict["endpoints"][0], font=(
                self.config_dict["font"], self.config_dict["basesize"]), fg="gray20")
            scale_left.pack(side="left", expand=True, padx=10, pady=5)

        # create a button for each element in the likert list
        for x in self.config_dict['likert']:
            self.text_or_image_button(text=str(x), value=str(
                x).casefold().replace(" ", "_"))

        # endpoint 2
        if self.config_dict["endpoints"][1]:
            scale_right = Label(self.frame_judg, text=self.config_dict["endpoints"][1], font=(
                self.config_dict["font"], self.config_dict["basesize"]), fg="gray20")
            scale_right.pack(side="left", expand=True, padx=10, pady=5)

    def dynamic_fc_buttons(self):
        """Display either image or text buttons that take their arguments from the item file (dynamic FC)."""
        self.fc_images = {}  # reset images dict
        for x, name in zip(self.items.iloc[self.item_num, 4:], self.items.iloc[:, 4:].columns):
            if self.config_dict["dynamic_img"]:
                # store images in dict (otherwise they won't be displayed)
                self.fc_images[x] = self.resize_image(x)
                self.text_or_image_button(value=str(name).casefold().replace(
                    " ", "_"), image=self.fc_images[x], side=random.choice(["left", "right"]))

            else:
                # just create the text buttons
                self.text_or_image_button(text=str(x), value=str(
                    name).casefold().replace(" ", "_"), side=random.choice(["left", "right"]))

        if self.config_dict["non_dynamic_button"]:
            self.text_or_image_button(
                text=self.config_dict["non_dynamic_button"], value=self.config_dict["non_dynamic_button"].casefold().replace(" ", "_"), likert_append=False, side="right")

    def submit_button(self, continue_func, text=None):
        """Display a submit button that takes different continuation functions.

        Arguments:
            continue_func {function} -- Function that should be executed on button press

        Keyword Arguments:
            text {str} -- Text to be displayed on the button; if None, value will be taken from the config file (default: {None})
        """
        # if no other text argument is passed, use the text in the configuration file
        if text is None:
            text = self.config_dict["button_text"]
        self.display_line()

        # frame and button with text for the submit button
        frame_submit = Frame(self.root)
        frame_submit.pack(expand=False, fill="both", side="top", pady=10)
        self.submit = Button(frame_submit, text=text, command=continue_func, fg="blue",
                             font=(
                                 self.config_dict["font"], self.config_dict["basesize"] - 10),
                             highlightcolor="gray90", highlightbackground="white",
                             highlightthickness=0, padx=10, pady=5,)
        self.submit.pack()
        # in the critical portion of the audio stimuli, the button is deactivated by default and becomes available after the item was played in full
        # in self-paced reading, only after all words of an item have been displayed
        if self.config_dict["self_paced_reading"]:
            if self.phases["critical"]:
                self.submit.config(state="disabled")

    ''' SECTION V: methods that are called upon button or keyboard presses '''

    def play_stimulus(self):
        """Play the file from the item list; either locally or via streaming it from the online source."""
        # check if the item is a link, if yes retrieve it
        if "https://" in self.items.iloc[self.item_num, 0]:
            # google drive export link conversion to usable link for playback
            if self.config_dict["google_drive_link"]:
                url = self.items.iloc[self.item_num, 0].replace(
                    "file/d/", "uc?export=download&id=").replace("/view?usp=sharing", "")
                url = BytesIO(urlopen(url).read())
            # for others, just use the link in the item file
            else:
                url = BytesIO(
                    urlopen(self.items.iloc[self.item_num, 0]).read())
            self.sound = pygame.mixer.Sound(url)
        else:
            # load file into mixer
            self.sound = pygame.mixer.Sound(
                self.items.iloc[self.item_num, 0])
        # start time we need for audio stimuli reaction time
        self.time_start = time.time()
        # play file
        self.sound.play()
        # after sound is over, change the value of played
        played_sound_timer = Timer(self.sound.get_length(), self.enable_submit)
        played_sound_timer.start()

    def save_participant_information(self):
        """Save all the meta fields to a list if all are filled out or display an error. On success, move on to exposition."""
        # empty the list (necessary for when the button is pressed multiple times)
        self.meta_entries_final.clear()
        # store the entries of the fields in the final attribute
        for i in range(len(self.meta_entries)):
            self.meta_entries_final.append(self.meta_entries[i].get())

        # if any of the fields are empty, print out an error message
        if "" in self.meta_entries_final:
            self.display_error(self.config_dict["error_meta"])
        # if all selections were made, move on to exposition
        else:
            self.empty_window()
            self.start_exposition_phase()

    def exit_exposition(self):
        """End the exposition stage and move on to either warm-up or critical section."""
        self.empty_window()
        self.start_warm_up_phase(
        ) if self.config_dict["warm_up"] else self.start_critical_phase()

    def next_word(self, event=None):
        """Increase the word counter and update the label text in self-paced-reading experiments. Record reaction times for each word in dictionary."""
        # NOTE: the event argument is just there to catch the event argument passed down by the button press
        # get number of words for current item (though it should stay the same for all items)
        number_of_words = len(self.items.iloc[self.item_num, 0].split())
        # if the word is in the middle of the item, take the reaction times
        if 0 < self.word_index <= number_of_words:
            # reaction times for the current word
            self.spr_reaction_times[self.word_index] = time.time(
            ) - self.time_start
        # if all words have been shown, remask the item and activate the continue button
        if self.word_index == number_of_words:
            # re-mask the item text so that participants cant just read the entire item at the end (especially important in the cumulative version)
            self.item_text.config(text=self.masked)
            # allow continuation
            self.enable_submit()
        # if there are more words, increase word index, unmask next word and record button press time
        else:
            self.word_index += 1
            self.item_text.config(text=self.create_masked_item())

    def submit_control(self):
        """Submit the judgment for self-paced reading control questions and move to the next item afterwards (if a choice was made)."""
        if self.judgment.get():
            self.logger.info(
                f"Done with control question {self.item_num + 1}/{len(self.items)}!")
            self.next_self_paced_reading_item()
        else:
            self.display_error(self.config_dict["error_judgment"])

    def submit_judgment(self):
        """Submit the judgment (likert, FC, image) as well as the reaction times and continue to next item. If at the end of the item list, move on to critical section (if currently in warm-up) or feedback section."""
        # if there's a judgment, compute the reaction times, append to df and move on to next item
        if self.judgment.get():
            # reaction times: subtract start time from stop time to get reaction times
            reaction_time = time.time() - self.time_start
            if self.config_dict["use_text_stimuli"]:
                # with text stimuli also subtract the delay
                reaction_time = reaction_time - \
                    self.config_dict["delay_judgment"]
            # for audio stimuli, also subtract the length of the item (because judgments are available only after the item has been played anyway)
            else:
                reaction_time = reaction_time - self.sound.get_length()

            # progress report
            self.logger.info(
                f"Done with item {self.item_num + 1}/{len(self.items)}!")

            # save the judgment and the reaction times
            self.save_dependent_measures(reaction_time)
            # move on to the next item (if any)
            self.next_item_general()
        # if no selection was made using the radio buttons, display error
        else:
            self.display_error(self.config_dict["error_judgment"])

    def next_item_general(self):
        """General waypoint function that performs all necessary tasks to display a new item (if there are more to be shown)."""
        # reset buttons for next item and increase item counter
        self.judgment.set("")
        self.item_num += 1
        # if there are more items to be shown, do that
        try:
            # reset the time counter for the reaction times
            self.time_start = time.time()
            if self.config_dict["use_text_stimuli"]:
                self.next_text_item()
            else:
                self.next_audio_item()
            if self.config_dict["dynamic_fc"] or self.config_dict["dynamic_img"]:
                self.update_judgment_buttons()
        # otherwise either go to the feedback section or enter the critical stage of the exp
        except IndexError as e:
            self.logger.info(f"No more items to show: {e}")
            self.item_list_over()

    def item_list_over(self):
        """Either launch the feedback or critical section of the experiment (because all items were seen)."""
        self.empty_window()
        # if all items have been shown and we're already in the critical phase, go to feedback
        if self.phases["critical"]:
            self.display_feedback()
        # reset the item counter and show the critical item list
        else:
            self.logger.info(
                "Warm-Up completed. Proceeding with critical phase now.")
            self.item_num = 0
            self.start_critical_phase()

    def item_list_over_spr(self):
        """Either launch the feedback or critical section of the experiment (because all items were seen). For self-paced-reading"""
        self.empty_window()
        if self.phases["critical"]:
            # remove the binding from the space bar
            self.root.unbind("<space>")
            # go to the feedback section
            self.display_feedback()
        # if we are at the end of the warm up phase, init critical
        else:
            self.logger.info(
                "Warm-Up completed. Proceeding with critical phase now.")
            # reset the counters and show the critical item list
            self.word_index = 0
            self.item_num = 0
            self.start_critical_phase()

    def save_dependent_measures(self, reaction_time=None):
        """Compile all the info we need for the results file and add it to the results dataframe."""
        # set up all the info that should be written to the file (in that order)
        out_l = [self.id_string, self.today, self.start_time, self.config_dict["tester"], self.meta_entries_final, list(
            self.items.iloc[self.item_num, 1:4])]
        # reaction times for all words
        if self.config_dict["self_paced_reading"]:
            out_l = out_l + [round(value, 5)
                             for value in self.spr_reaction_times.values()] + [self.judgment.get()]
        # judgments
        else:
            out_l = out_l + [self.judgment.get(), str(round(reaction_time, 5))]
        # flatten list of lists; turn to string, remove capital letters and add rows to pandas df
        out_l = [str(item).casefold()
                 for item in pd.core.common.flatten(out_l)]
        self.outdf.loc[len(self.outdf)] = out_l

    def next_self_paced_reading_item(self):
        """Shows the next item in self-paced reading experiment, calls functions to save reaction times and judgments. At the end of item list, moves on to either critical section (if currently in warm-up) or the feedback section."""
        self.logger.info(
            f"Done with item {self.item_num + 1}/{len(self.items)}!")

        self.submit.config(state="disabled")
        self.save_dependent_measures()
        self.item_num += 1

        try:
            # empty the stored reaction times
            self.spr_reaction_times = {}
            # run masking on new item and reset the word index
            self.word_index = 0
            # reset the control judgment
            self.judgment.set("")
            # and go back to the masked item frame
            self.empty_window()
            self.display_spacer_frame()
            self.display_masked_item()
        # otherwise either go to the feedback section or enter the critical stage of the exp
        except IndexError as e:
            self.logger.info(f"No more items to show: {e}")
            self.item_list_over_spr()

    def next_text_item(self):
        """Update the item text on the screen to show the new item and handle reaction times and button resets."""
        # disable the likert scale button
        for obj in self.likert_list:
            obj.config(state="disabled")
        # start the timer for reactivation
        read_item_timer = Timer(
            self.config_dict["delay_judgment"], self.enable_submit)
        read_item_timer.start()
        # show new item
        self.item_text.config(
            text=self.items.iloc[self.item_num, 0])

    def next_audio_item(self):
        """Disable the judgment and submit buttons and flash the play button."""
        # because the play button will automatically update itself to play the new item (bc of the item_num), we only need to disable the button for audio stimuli
        if self.item_num < len(self.items):
            self.submit.config(state="disabled")
            for obj in self.likert_list:
                obj.config(state="disabled")
            self.flash_play_button(0)
        else:
            self.logger.info(f"No more items to show")
            self.item_list_over()

    def update_judgment_buttons(self):
        """Update the text/image for the FC buttons; order is randomized."""
        self.fc_images = {}
        for i, txt_or_img, col_names in zip(random.sample(range(len(self.likert_list)), len(self.likert_list)), self.items.iloc[self.item_num, 4:], self.items.iloc[:, 4:].columns):
            # use images instead of text with dynamic image FC (resize before display)
            if self.config_dict["dynamic_img"]:
                self.fc_images[txt_or_img] = self.resize_image(txt_or_img)
                self.likert_list[i].config(
                    text=None, value=col_names, image=self.fc_images[txt_or_img])
            # change the text to that of the current item (since item counter has been incremented)
            else:
                self.likert_list[i].config(
                    text=txt_or_img, value=col_names)

    def save_feedback(self):
        """Save participant feedback file together with the results, but under a different name; all feedback texts together in a single file."""
        # platform independent path to feedback file
        feedback_file = os.path.join(
            self.resultsdir, f"FEEDBACK{self.config_dict['results_file_extension']}")

        # subtract the start time from current time and convert it to minutes
        tot_duration = round((time.time() - self.exp_start)/60, 2)

        # if exp was quit before intended end point (and thus there's no actual feedback), put a notice in the file
        if self.phases["quit"]:
            feedback = f"[CANCELLED at {self.item_num + 1}/{len(self.items)} items]"
        # if there is a feedback, use that
        elif self.feedback.get().replace(" ", ""):
            feedback = self.feedback.get()
        # if participant did not write any feedback, put NA
        else:
            feedback = "NA"

        out_l = [self.id_string, tot_duration, self.part_num, feedback]
        # read in the feedback file
        try:
            df_feedback = self.read_multi_ext(feedback_file)
        # or create one if it couldn't be found
        except FileNotFoundError as e:
            # setup the column headers
            cols = ["id", "duration_minutes", "part_no", "feedback"]
            # and create the pandas object
            df_feedback = pd.DataFrame(columns=cols)
            self.logger.info(
                f"No feedback file '{feedback_file}', creating one instead: {e}")

        # add the new row of the current participant and save the file
        df_feedback.loc[len(df_feedback)] = out_l
        self.save_multi_ext(df_feedback, feedback_file)

        # show the goodbye message
        try:
            self.display_over()
        # if the GUI has been exited already, do nothing
        except TclError:
            pass

    def enable_submit(self):
        """Unlock disabled submit buttons, either after a timer or after an event (like the audio finishing to play) has occurred."""
        self.submit.config(state="normal")
        for obj in self.likert_list:
            obj.config(state="normal")

    def flash_play_button(self, count):
        """Flash the play button a number of times to encourage that it is clicked by rapidly color swapping."""
        bg = self.audio_btn.cget('highlightcolor')
        fg = self.audio_btn.cget('highlightbackground')
        self.audio_btn.config(highlightcolor=fg, highlightbackground=bg)
        count += 1
        # if the specified amount of flashes has not been reached call the function again, passing the updated count
        if (count < 10):
            self.audio_btn.after(100, self.flash_play_button, count)

    def on_closing(self):
        """Warn before closing the root experiment window with the system buttons."""
        # show a warning message that the exiting participant has to accept
        if messagebox.askokcancel("Quit", self.config_dict["quit_warning"]):
            self.root.destroy()
            self.phases["quit"] = True
            # if ended before intended ending, log that and handle results and feedback file
            if self.phases["critical"] and not self.phases["finished"]:
                self.logger.warning(
                    "IMPORTANT!: Experiment was quit manually.")
                self.unfinished_participant_results()
                self.save_feedback()
            else:
                self.logger.info(
                    "Experiment was quit manually outside of the critical section.")


if __name__ == '__main__':
    logging.basicConfig(filename="experiment.log", level=logging.INFO,
                        format="%(asctime)s - %(name)s - %(levelname)-8s - %(funcName)s - %(message)s")

    Exp = Experiment("test.py")
    Exp.start_experiment()
    # print(Exp)
