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


'''
    TODO:
    - support for video stimuli
    - option to have several experimental blocks with a break inbetween
    - for self-paced reading, add control questions

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
        # Calculate and set geometry
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry('{}x{}+{}+{}'.format(width, height, x, y))

    def empty_window(self):
        """Gather all frames and content within them and delete them from view."""
        # get children
        widget_list = self.root.winfo_children()
        # add grandchildren
        for item in widget_list:
            if item.winfo_children():
                widget_list.extend(item.winfo_children())

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
                   'item_or_file_col', 'sub_exp_col', 'cond_col', 'dynamic_txt_or_img_cols']

    def __init__(self, config):
        """Initialie the experiment class and start up the tkinter GUI.

        Arguments:
            config {str} -- Python script name that contains the experiment's configuration parameters.
        """
        self.logger = logging.getLogger(__name__)
        self.config = config
        self.config_dict = self.get_config_dict(self.config)

        self.root = Tk()
        self.setup_gui()

        # time of testing
        self.experiment_started = time.time()  # track eperiment duration
        self.start_time = datetime.datetime.now().strftime("%H:%M:%S")
        self.today = datetime.date.today().strftime("%d/%m/%Y")

        # housekeeping files which track participants and experiment configuration
        self.part_and_list_file = self.config_dict["experiment_title"] + \
            "_participants.txt"
        self.config_file = os.path.join(
            f"{self.config_dict['experiment_title']}_results", "config.json")

        # store meta data
        self.meta_entries = []
        self.meta_entries_final = []

        # item stuff
        self.item_list_no = ""
        self.likert_list = []
        self.judgment = StringVar()
        self.item_counter = 0
        self.word_index = 0  # for self-paced reading
        self.masked = ""

        # reaction times
        self.time_start = ""
        self.spr_reaction_times = {}  # for self-paced reading

        # images
        self.logo = self.resize_image(self.config_dict["logo"], 100)
        self.playimage = self.resize_image(os.path.join(
            "media", "play.png"), 100) if not self.config_dict["use_text_stimuli"] else None
        self.fc_images = {}  # for dynamic FC with images
        # feedback text
        self.feedback = StringVar()
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
            if self.participant_number != self.config_dict["participants"] and not self.phases["problem"]:
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
        self.retrieve_items()
        if not self.config_dict["warm_up"]:
            self.prepare_results_df()
        self.display_spacer_frame()
        self.display_short(self.config_dict["title"], 5)
        self.display_short(self.config_dict["description"])
        if self.config_dict["warm_up"]:
            self.item_counter = 0
        self.init_items()

    def init_items(self):
        """Display the various kinds of elements needed for the different types of experiments (text, play and submit buttons, likert scale, ...)."""
        if not self.config_dict["self_paced_reading"]:
            if self.config_dict["use_text_stimuli"]:
                self.display_text_item()
            else:
                pygame.init()
                self.display_audio_stimulus()
            self.judgment_buttons()
            self.submit_button(self.submit_judgment)
            self.submit.config(state="disabled")
        elif self.config_dict["use_text_stimuli"] and self.config_dict["self_paced_reading"]:
            self.display_masked_item()
            self.submit.config(state="disabled")
        self.time_start = time.time()

    def experiment_finished(self):
        """Show message when all necessary participants have been tested."""
        self.display_long(self.config_dict["finished_message"], 8)

        # send confirmation e-mail if so specified
        if self.config_dict["confirm_completion"]:
            self.send_confirmation_email()

        self.submit_button(self.root.destroy, "Exit")
        self.logger.info(
            f"All Participants have been tested. If you want to test more than {self.config_dict['participants']} people, increase the amount in the specs file!")

    ''' SECTION II: display methods used by the initializing functions '''

    def display_short(self, text, size_mod=0, side="top"):
        """Display a short message without word wrap enabled. Show nothing if instruction text is empty."""
        if text:
            frame = Frame(self.root)
            frame.pack(expand=False, fill="both", side="top", pady=2)
            label = Label(frame, text=text, font=(
                self.config_dict["font"], self.config_dict["basesize"] + size_mod))
            label.pack(pady=2, side=side)

    def display_long(self, text, size_mod=0):
        """Display a long message with word wrap enabled. Show nothing if instruction text is empty."""
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

    def retrieve_items(self, filename=None, warm_up_list=None):
        """Retrieve the items from the specified item file and randomize their order if specified. Items are stored in items object."""
        if filename is None:
            filename = self.config_dict["item_file"]
        # in case there is no additional argument, use the item list number
        if warm_up_list is None:
            # load the correct item file for the specific participant
            infile = filename + str(self.item_list_no) + \
                self.config_dict["item_file_extension"]
        # if there is (as with the warm up)
        else:
            infile = filename + self.config_dict["item_file_extension"]

        # read in the conditions file
        df_items = self.read_multi_ext(
            infile, self.config_dict["item_file_extension"])

        # if so specified and we're past the warm-up phase, randomize the items
        if self.config_dict["items_randomize"] and self.phases["critical"]:
            df_items = df_items.sample(frac=1).reset_index(drop=True)

        # rearrange the columns of the data frame using the entries in item_file_columns
        columns_to_order = pd.core.common.flatten([self.config_dict['item_or_file_col'], self.config_dict['sub_exp_col'],
                                                   self.config_dict['item_number_col'], self.config_dict['cond_col'], self.config_dict['dynamic_txt_or_img_cols']])
        try:
            df_items = df_items[columns_to_order]
        except KeyError as e:
            self.logger.error(
                f"Column mismatch. Check the following values: {e}")

        self.items = df_items

    def display_text_item(self):
        """Display frame, label, and submit button for text items."""
        frame_item = Frame(self.root)
        frame_item.pack(expand=False, fill="both",
                        side="top", pady=10, padx=25)
        self.item_text = Label(frame_item, font=(
            self.config_dict["font"], self.config_dict["basesize"] + 7), text=self.items.iloc[0, self.item_counter], height=6, wraplength=1000)
        self.item_text.pack()

    def display_audio_stimulus(self):
        """Display frame, label, and play button for audio items."""
        frame_audio = Frame(self.root, height=10)
        frame_audio.pack(expand=False, fill="both",
                         side="top", pady=10, padx=25)

        self.audio_btn = Button(frame_audio, text=self.config_dict["audio_button_text"], image=self.playimage, compound="left", fg="black", font=(
            self.config_dict["font"], self.config_dict["basesize"]), padx=20, pady=25, command=lambda: self.play_stimulus())
        self.audio_btn.pack(side="top")

    def display_masked_item(self):
        """Display frame, label, and button for masked items in self-paced reading"""
        frame_item = Frame(self.root)
        frame_item.pack(expand=False, fill="both",
                        side="top", pady=10, padx=25)
        self.item_text = Label(frame_item, font=(
            self.config_dict["font_mono"], self.config_dict["basesize"] + 8), text=self.create_masked_item(), height=9, wraplength=1000)
        self.item_text.pack()
        self.submit_button(self.next_self_paced_reading_item)

        # press the space bar to show next word
        self.root.bind('<space>', self.next_word)

    def create_masked_item(self):
        """Take item and mask letters and words with underscores, depending on word counter."""
        # replace all non-whitespace characters with underscores
        self.masked = re.sub(
            "[^ ]", "_", self.items.iloc[self.item_counter, 0])
        masked_split = self.masked.split()

        # if cumulative option is selected, the word identified by counter and all previous ones will be shown
        if self.config_dict["cumulative"]:
            for i in range(self.word_index):
                masked_split[i] = self.items.iloc[self.item_counter, 0].split()[
                    i]
        # if non-cumulative, only the target word is displayed
        else:
            # if the index is zero, dont unmask anything
            if self.word_index == 0:
                masked_split = masked_split
            # otherwise show the word bearing the index - 1 (without the subtraction we would always skip the first word in the unmasking because of the previous part of the conditional)
            else:
                masked_split[self.word_index - 1] = self.items.iloc[self.item_counter, 0].split()[
                    self.word_index - 1]

        # start the reaction times
        self.time_start = time.time()

        return " ".join(masked_split)

    def display_feedback(self):
        """Save, the results, display instructions and entry field for feedback after the critical section."""
        # end the critical portion
        self.phases["critical"] = False
        self.outdf['finished'] = "T"
        self.save_multi_ext(self.outdf, self.outfile,
                            self.config_dict["results_file_extension"])
        self.logger.info(f"Results file saved: {self.outfile}")

        # unless the feedback text is empty, show a frame to allow feedback entry
        if not self.config_dict["feedback"]:
            self.display_over()
        elif self.config_dict["feedback"]:
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
        compare_config = {'fullscreen', 'allow_fullscreen_escape', 'geometry', 'window_title', 'experiment_title', 'confirm_completion',
                          'receiver_email', 'tester', 'logo', 'meta_instruction', 'meta_fields', 'expo_text', 'warm_up', 'warm_up_title',
                          'warm_up_description', 'warm_up_file', 'use_text_stimuli', 'self_paced_reading', 'cumulative', 'title', 'description',
                          'likert', 'endpoints', 'dynamic_fc', 'non_dynamic_button', 'dynamic_img', 'google_drive_link', 'delay_judgment', 'participants',
                          'remove_unfinished', 'remove_ratio', 'item_lists', 'item_file', 'item_file_extension', 'item_number_col', 'item_or_file_col',
                          'sub_exp_col', 'cond_col', 'dynamic_txt_or_img_cols', 'items_randomize', 'results_file', 'results_file_extension', 'feedback',
                          'audio_button_text', 'button_text', 'finished_message', 'bye_message', 'quit_warning', 'error_judgment', 'error_meta', 'font',
                          'font_mono', 'basesize'}
        # compare the two
        if compare_config == set(self.config_dict.keys()):
            self.logger.info(
                f"Configuration file {self.config} passed the completeness check.")
            return True
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
        if not os.path.isdir(self.config_dict["experiment_title"] + "_results"):
            os.makedirs(self.config_dict["experiment_title"] + "_results")
        # if participant and saved config file do not exist, create them
        try:
            self.read_and_check_housekeeping_files()
        except FileNotFoundError as e:
            self.create_housekeeping_files()
            self.logger.info(
                f"Housekeeping file '{self.part_and_list_file}' not found, creating one instead: {e}")
        # assign participant to an item list (using the modulo method for latin square)
        self.item_list_no = self.participant_number % self.config_dict["item_lists"] + 1

    def create_housekeeping_files(self):
        with open(self.part_and_list_file, 'a') as file:
            file.write("0")
        self.participant_number = 0
        # save self.config_dict in the results directory to validate on later runs that the same settings are being used
        with open(self.config_file, "w", encoding='utf-8') as file:
            json.dump(self.config_dict, file, ensure_ascii=False, indent=4)

    def read_and_check_housekeeping_files(self):
        with open(self.part_and_list_file, 'r') as file:
            self.participant_number = int(file.read())
        # check if the saved config file is the same as the one in self.config_dict: dict_a == dict_b; otherwise throw a warning
        with open(self.config_file, "r") as file:
            compare_config = json.load(file)
        # compare the core entries, as opposed to all of them; changing the font size in the middle of the exp shouldn't be a problem
        if not {k: self.config_dict[k] for k in self.config_core} == {k: compare_config[k] for k in self.config_core}:
            self.display_long(
                f"The configurations for the currently running experiment have changed from previous participants.\nCheck '{self.config}' or start a new experiment (e.g. by changing the experiment title) to proceed.")
            self.logger.warning(
                f"Config dict: { {k: self.config_dict[k] for k in self.config_core} }\nCompare dict: { {k: compare_config[k] for k in self.config_core} }")
            self.submit_button(self.root.destroy, "Exit")
            self.phases["problem"] = True
        else:
            self.logger.info(
                f"Configuration check passed. Core settings in {self.config} have not been modified from previous participants.")
        if self.participant_number == self.config_dict["participants"]:
            self.experiment_finished()

    def housekeeping_file_update(self):
        """Increase the participant number and write it to the participants housekeeping file."""
        # increase participant number and write it to the housekeeping file
        self.participant_number += 1
        with open(self.part_and_list_file, 'w') as file:
            file.write(str(self.participant_number))
        self.logger.info(
            f"Starting with Participant Number {self.participant_number}/{self.config_dict['participants']} now! Participant was assigned to Item File {self.item_list_no}")

    def prepare_results_df(self):
        """Initialize the results df with appropriate header depending on the experiment. Set the df as outdf."""
        # outfile in new folder with id number attached
        self.outfile = os.path.join(f"{self.config_dict['experiment_title']}_results",
                                    f"{self.config_dict['results_file']}_{str(self.participant_number).zfill(len(str(self.config_dict['participants'])))}_{self.id_string}{self.config_dict['results_file_extension']}")
        header_list = ["id", "date", "start_time", "tester",
                       self.config_dict["meta_fields"], "sub_exp", "item", "cond"]
        # for standard judgment experiments (either text or audio)
        if (self.config_dict["use_text_stimuli"] and not self.config_dict["self_paced_reading"]) or not self.config_dict["use_text_stimuli"]:
            # add judgments and reaction times
            header_list = header_list + ["judgment", "reaction_time"]
        else:
            # add a column for each word in the item (of the first item)
            header_list = header_list + [self.items.iloc[0, 0].split()]
        # flatten the list of lists, remove capitalization and spaces and initialize pandas object
        header_list = [item.casefold().replace(" ", "_")
                       for item in pd.core.common.flatten(header_list)]
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
        if self.config_dict["remove_unfinished"] and self.item_counter < len(self.items) * self.config_dict["remove_ratio"]:
            # also reduce the participant number in the housekeeping file
            self.participant_number -= 1
            with open(self.part_and_list_file, 'w') as file:
                file.write(str(self.participant_number))
            self.logger.info(
                "Participant will not be counted towards the amount of people to be tested.")
        else:
            self.outdf['finished'] = 'F'
            self.save_multi_ext(self.outdf, self.outfile,
                                self.config_dict["results_file_extension"])
            self.logger.info(
                f"Results file will not be deleted and the participant will count towards the specified amount. Saved file: {self.outfile}")

    def delete_file(self, file):
        """Delete files or directories."""
        try:
            os.remove(file)
            self.logger.info(f"File deleted: {file}")
        except PermissionError as e:
            shutil.rmtree(file)
            self.logger.info(
                f"Directory and all contained files deleted: {file}")
        except FileNotFoundError as e:
            self.logger.warning(f"File does not exist: {file}; {e}")

    def delete_all_results(self):
        """Delete both the results directory (including configuration json and feedback file) as well as the participants housekeeping file."""
        result_dir = self.config_dict["experiment_title"] + "_results"
        for x in [result_dir, self.part_and_list_file]:
            self.delete_file(x)

    def merge_all_results(self):
        """Merge all results from the various participants into a single df and save it."""
        outfile = self.config_dict["experiment_title"] + \
            "_results_full" + self.config_dict["results_file_extension"]

        # Get results files
        files_dir = self.config_dict["experiment_title"] + "_results"
        results_files = sorted(
            glob.glob(os.path.join(
                files_dir, f'*{self.config_dict["results_file_extension"]}')))

        # remove the feedback file
        try:
            results_files.remove(os.path.join(
                files_dir, f'FEEDBACK{self.config_dict["results_file_extension"]}'))
        except ValueError as e:
            self.logger.info(f"Feedback file not in file list: {e}")
        # print out which files were found as well as their size
        self.logger.info(f'Found {len(results_files)} results files:')
        for file in results_files:
            self.logger.info(
                f"{file} \t {round(os.path.getsize(file) / 1000, 3)} KB")

        dfs = [self.read_multi_ext(x, self.config_dict["results_file_extension"])
               for x in results_files]
        df_all = pd.concat(dfs)

        self.save_multi_ext(
            df_all, outfile, self.config_dict["results_file_extension"])

        self.logger.info(f"Merged results file generated: {outfile}")

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
            outname {str} -- Name for the saved files (uniqueness handled automatically); include extension; cannot include the word 'nonfiller'.

        Keyword Arguments:
            sub_exp_col {str} -- Column containing the subexperiment identifier (default: {"sub_exp"})
            cond_col {str} -- Column containing the condition identifiers (default: {"cond"})
            item_col {str} -- Column with the item text (default: {"item"})
            item_number_col {str} -- Column with the item number (default: {"item_number"})

        Returns:
            list -- List with all the names of the files that were saved to disk
        """
        if "nonfiller" in outname:
            raise Exception(
                f"File name {outname} is wrong; do not use 'nonfiller' in the outfile name.")
        dfs_dict = {}
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
            # if they are not all there, raise an error and show which combos are missing
            missing_combos = ', '.join([''.join(map(str, product)) for product, boolean in zip(
                products, check_list) if not boolean])
            if not all(check_list):
                raise Exception(
                    f"Not all permutations of items and conditions are present in the dataframe. Missing combinations: {missing_combos}")

            # generate the appropriate amount of lists
            for k in range(len(conditions)):
                # order the conditions to match the list being created
                lat_conditions = conditions[k:] + conditions[:k]
                # generate (and on subsequent runs reset) the new df with all the columns in the argument df
                out_df = pd.DataFrame(columns=frame.columns)
                # look for the appriate rows in the argument df (using the conditions multiple times with 'cycle')
                for item, cond in zip(set(sorted(frame[item_number_col])), cycle(lat_conditions)):
                    out_l = [out_df, frame[frame.item_number.eq(
                        item) & frame.cond.eq(cond)]]
                    out_df = pd.concat(out_l)
                # reorder the most important columns and just add the rest (if any)
                columns_to_order = [item_col, sub_exp_col,
                                    item_number_col, cond_col]
                new_columns = columns_to_order + \
                    (out_df.columns.drop(columns_to_order).tolist())
                out_df = out_df[new_columns]
                # add a 'nonfiller' suffix if several lists are being made; this is the way we will distinguish filler from critical dfs
                temp_name = name if len(
                    lat_conditions) == 1 else f"{name}_nonfiller"
                dfs_dict[temp_name] = out_df

        # separate critical and filler dfs
        dfs_critical = [dfs_dict[x] for x in dfs_dict if "nonfiller" in x]
        dfs_filler = [dfs_dict[x] for x in dfs_dict if "nonfiller" not in x]

        # add all filler lists to the critical ones
        for filler in dfs_filler:
            for i, df in enumerate(dfs_critical):
                dfs_critical[i] = pd.concat([df, filler])

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
        self.merge_all_results()
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
        """
        x = Radiobutton(self.frame_judg, image=image, text=text, variable=self.judgment, value=value, font=(
            self.config_dict["font"], self.config_dict["basesize"]))
        x.pack(side=side, expand=True, padx=10)
        if likert_append:
            self.likert_list.append(x)
            x.config(state="disabled")

    def judgment_buttons(self):
        """Display the likert, FC buttons or images used to give linguistic judgments."""
        # frame for the judgment buttons
        self.frame_judg = Frame(self.root, relief="sunken", bd=2)
        self.frame_judg.pack(side="top", pady=20)

        if not self.config_dict["dynamic_fc"] and not self.config_dict["dynamic_img"]:
            self.likert_style_buttons()

        # get the Forced Choice options from the item file
        else:
            self.dynamic_fc_buttons()

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

        # likert scale
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
        if not self.config_dict["dynamic_img"]:
            for x, name in zip(self.items.iloc[self.item_counter, 4:], self.items.iloc[:, 4:].columns):
                self.text_or_image_button(text=str(x), value=str(
                    name).casefold().replace(" ", "_"), side=random.sample(["left", "right"], 1))

        else:
            self.fc_images = {}  # reset images dict
            for x, name in zip(self.items.iloc[self.item_counter, 4:], self.items.iloc[:, 4:].columns):
                # store images in dict (otherwise they won't be displayed)
                self.fc_images[x] = self.resize_image(x)
                self.text_or_image_button(value=str(name).casefold().replace(
                    " ", "_"), image=self.fc_images[x], side=random.choice(["left", "right"]))

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
        self.submit = Button(frame_submit, text=text, fg="blue", font=(self.config_dict["font"], self.config_dict["basesize"] - 10), padx=10, pady=5,
                             command=continue_func, highlightcolor="gray90", highlightbackground="white", highlightthickness=0)
        self.submit.pack()
        # in the critical portion of the audio stimuli, the button is deactivated by default and becomes available after the item was played in full
        # in self-paced reading, only after all words of an item have been displayed
        if (not self.config_dict["use_text_stimuli"] or self.config_dict["self_paced_reading"]) and self.phases["critical"]:
            self.submit.config(state="disabled")

    ''' SECTION V: methods that are called upon button or keyboard presses '''

    def play_stimulus(self):
        """Play the file from the item list; either locally or via streaming it from the online source."""
        # check if the item is a link, if yes retrieve it
        if "https://" in self.items.iloc[self.item_counter, 0]:
            # google drive export link conversion to usable link for playback
            if self.config_dict["google_drive_link"]:
                url = self.items.iloc[self.item_counter, 0].replace(
                    "file/d/", "uc?export=download&id=").replace("/view?usp=sharing", "")
                url = BytesIO(urlopen(url).read())
            # for others, just use the link in the item file
            else:
                url = BytesIO(
                    urlopen(self.items.iloc[self.item_counter, 0]).read())
            self.sound = pygame.mixer.Sound(url)
        else:
            # load file into mixer
            self.sound = pygame.mixer.Sound(
                self.items.iloc[self.item_counter, 0])
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
        # if the word is in the middle of the item, take the reaction times
        if 0 < self.word_index <= len(self.items.iloc[self.item_counter, 0].split()):
            # reaction times
            self.spr_reaction_times[self.word_index] = time.time(
            ) - self.time_start
        # if all words have been shown, activate the continue button
        if self.word_index == len(self.items.iloc[self.item_counter, 0].split()):
            # re-mask the item text so that participants cant just read the entire item at the end (especially important in the cumulative version)
            self.item_text.config(text=self.masked)
            self.enable_submit()
        # if there are more words, increase word index, unmask next word and record button press time
        else:
            self.word_index += 1
            self.item_text.config(text=self.create_masked_item())

    def submit_judgment(self):
        """Submit the judgment (likert, FC, image) as well as the reaction times and continue to next item. If at the end of the item list, move on to critical section (if currently in warm-up) or feedback section."""
        # if no selection was made using the radio buttons, display error
        if not self.judgment.get():
            self.display_error(self.config_dict["error_judgment"])
        elif self.judgment.get():
            # reaction times: subtract start time from stop time to get reaction times
            if self.config_dict["use_text_stimuli"]:
                reaction_time = time.time() - self.time_start - \
                    self.config_dict["delay_judgment"]
            # for audio stimuli, also subtract the length of the item (because judgments are available only after the item has been played anyway)
            else:
                reaction_time = time.time() - self.time_start - self.sound.get_length()

            # progress report
            self.logger.info(
                f"Done with item {self.item_counter + 1}/{len(self.items)}!")

            self.save_dependent_measures(reaction_time)
            self.next_item_general()

    def next_item_general(self):
        """General waypoint function that performs all necessary tasks to display a new item (if there are more to be shown)."""
        # reset buttons for next item and increase item counter
        self.judgment.set("")
        self.item_counter += 1
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
        if self.phases["critical"]:
            self.display_feedback()
        elif not self.phases["critical"]:
            self.logger.info(
                "Warm-Up completed. Proceeding with critical phase now.")
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
        elif not self.phases["critical"] and self.config_dict["warm_up"]:
            self.word_index = 0
            self.logger.info(
                "Warm-Up completed. Proceeding with critical phase now.")
            self.start_critical_phase()

    def save_dependent_measures(self, reaction_time=None):
        """Compile all the info we need for the results file."""
        # set up all the info that should be written to the file (in that order)
        out_l = [self.id_string, self.today, self.start_time, self.config_dict["tester"], self.meta_entries_final, list(
            self.items.iloc[self.item_counter, 1:4])]
        # reaction times for all words
        if self.config_dict["self_paced_reading"]:
            out_l = out_l + [round(value, 5)
                             for value in self.spr_reaction_times.values()]
        # judgments
        else:
            out_l = out_l + [self.judgment.get(), str(round(reaction_time, 5))]
        # flatten list of lists; turn to string, remove capital letters and add rows to pandas df
        out_l = [str(item).casefold()
                 for item in pd.core.common.flatten(out_l)]
        self.outdf.loc[len(self.outdf)] = out_l

    def next_self_paced_reading_item(self):
        """Record reaction times in outdf in self-paced-reading ecperiments and shows the next item. At the end of item list, moves on to either critical section (if currently in warm-up) or the feedback section."""
        self.logger.info(
            f"Done with item {self.item_counter + 1}/{len(self.items)}!")

        self.submit.config(state="disabled")
        self.save_dependent_measures()
        self.item_counter += 1

        try:
            # empty the stored reaction times
            self.spr_reaction_times = {}
            # run masking on new item and reset the word index
            self.word_index = 0
            self.item_text.config(text=self.create_masked_item())
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
            text=self.items.iloc[self.item_counter, 0])

    def next_audio_item(self):
        """Disable the judgment and submit buttons and flash the play button."""
        # because the play button will automatically update itself to play the new item (bc of the item_counter), we only need to disable the button for audio stimuli
        self.submit.config(state="disabled")
        for obj in self.likert_list:
            obj.config(state="disabled")
        self.flash_play_stimulus_button(0)

    def update_judgment_buttons(self):
        """Update the text/image for the FC buttons."""
        self.fc_images = {}
        for i, txt_or_img, col_names in zip(random.sample(range(len(self.likert_list)), len(self.likert_list)), self.items.iloc[self.item_counter, 4:], self.items.iloc[:, 4:].columns):
            if self.config_dict["dynamic_fc"] and not self.config_dict["dynamic_img"]:
                self.likert_list[i].config(
                    text=txt_or_img, value=col_names)
            elif self.config_dict["dynamic_img"]:
                self.fc_images[txt_or_img] = self.resize_image(txt_or_img)
                self.likert_list[i].config(
                    text=None, value=col_names, image=self.fc_images[txt_or_img])

    def save_feedback(self):
        """Save participant feedback file together with the results, but under a different name; all feedback texts together in a single file."""
        feedback_file = os.path.join(
            f"{self.config_dict['experiment_title']}_results", f"FEEDBACK{self.config_dict['results_file_extension']}")

        experiment_duration = round(
            (time.time() - self.experiment_started)/60, 2)

        # save the feedback with id string and internal number as csv file
        if self.feedback.get().replace(" ", "") and not self.phases["quit"]:
            feedback = self.feedback.get()
        elif self.phases["quit"]:
            feedback = f"[CANCELLED at {self.item_counter + 1}/{len(self.items)} items]"
        else:
            feedback = "NA"

        out_l = [self.id_string, experiment_duration,
                 self.participant_number, feedback]
        # open the feedback file or create one if it doesn't exist
        try:
            df_feedback = self.read_multi_ext(
                feedback_file, self.config_dict["results_file_extension"])
        except FileNotFoundError as e:
            df_feedback = pd.DataFrame(
                columns=["id", "duration_minutes", "part_no", "feedback"])
            self.logger.info(
                f"No feedback file '{feedback_file}' found, creating one instead: {e}")
        # add the new row of the current participant and save the file
        df_feedback.loc[len(df_feedback)] = out_l
        self.save_multi_ext(df_feedback, feedback_file,
                            self.config_dict["results_file_extension"])

        if not self.phases["quit"]:
            self.display_over()

    def enable_submit(self):
        """Unlock disabled submit buttons, either after a timer or after an event (like the audio finishing to play) has occurred."""
        if not self.phases["quit"]:
            self.submit.config(state="normal")
            for obj in self.likert_list:
                obj.config(state="normal")

    def flash_play_stimulus_button(self, count):
        """Flash the play button a number of times to encourage that it is clicked."""
        bg = self.audio_btn.cget('highlightcolor')
        fg = self.audio_btn.cget('highlightbackground')
        self.audio_btn.config(highlightcolor=fg, highlightbackground=bg)
        count += 1
        if (count < 10):
            self.audio_btn.after(100, self.flash_play_stimulus_button, count)

    def on_closing(self):
        """Warn before closing the root experiment window with the system buttons."""
        if messagebox.askokcancel("Quit", self.config_dict["quit_warning"]):
            self.root.destroy()
            self.phases["quit"] = True
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
