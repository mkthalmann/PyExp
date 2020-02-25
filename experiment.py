# pylint: disable=no-member,W0614

from tkinter import *
from tkinter import messagebox
from threading import Timer
import json
import random  # randomize items
import string  # participant id
import re  # regular expressions
import os
import glob
import shutil
import pygame  # audio
from PIL import Image, ImageTk
from io import BytesIO  # linked files
from urllib.request import urlopen  # linked files
import time
import datetime
import pandas as pd
# e-mail stuff
import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

'''
    TODO:
    -

    FIXME:
    - 
'''


class Window():

    def __init__(self):
        pass

    # center the window
    def center_window(self):
        # Call all pending idle tasks - carry out geometry management and redraw widgets.
        self.root.update_idletasks()
        # Get width and height of the screen
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        # Calculate and set geometry
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry('{}x{}+{}+{}'.format(width, height, x, y))

    # list of all frames and content within them and delete them from view
    def empty_window(self):
        # get children
        widget_list = self.root.winfo_children()
        # add grandchildren
        for item in widget_list:
            if item.winfo_children():
                widget_list.extend(item.winfo_children())

        for item in widget_list:
            item.pack_forget()

    # make the window fullscreen (Escape to return to specified geometry)
    def fullscreen(self):
        self.root.geometry("{0}x{1}+0+0".format(
            self.root.winfo_screenwidth() - 3, self.root.winfo_screenheight() - 3))
        if self.config_dict["allow_fullscreen_escape"]:
            self.root.bind('<Escape>', self.return_geometry)

    def return_geometry(self, event):
        self.root.geometry(self.config_dict["geometry"])


class Experiment(Window):

    # class attribute: core values
    config_core = ["experiment_title", "warm_up",
                   "warm_up_file", "use_text_stimuli", "self_paced_reading", "cumulative", "likert", "dynamic_fc", "dynamic_img", "item_file"]

    def __init__(self, config):
        # configuration dictionary
        self.config = config
        self.config_dict = self.get_config_dict(self.config)

        # generate the window and perform some general setups
        self.root = Tk()
        self.root.wm_title(self.config_dict["window_title"])
        self.root.geometry(self.config_dict["geometry"])
        self.fullscreen(
        ) if self.config_dict["fullscreen"] else self.center_window()
        # add close warning
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # time of testing
        self.experiment_started = time.time()  # track eperiment duration
        self.start_time = datetime.datetime.now().strftime("%H:%M:%S")
        self.today = datetime.date.today().strftime("%d/%m/%Y")

        # housekeeping files which track participants and experiment configuration
        self.part_and_list_file = self.config_dict["experiment_title"] + \
            "_storage.txt"
        self.config_file = self.config_dict["experiment_title"] + \
            "_results/config.txt"

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
        self.logo = PhotoImage(file=self.config_dict["logo"]).subsample(6, 6)
        self.playimage = PhotoImage(
            file="media/play.png").subsample(6, 6) if not self.config_dict["use_text_stimuli"] else None
        self.fc_images = {}  # for dynamic FC with images
        # feedback text
        self.feedback = StringVar()
        # phase checker dict; for critical phase, finished exp, and quit application
        self.phases = dict.fromkeys(["critical", "finished", "quit"], False)

    def __str__(self):
        core_dict = {k: self.config_dict[k] for k in self.config_core}
        return "\nExperiment with the following core settings:\n" + '\n'.join(['{key} = {value}'.format(key=key, value=core_dict.get(key)) for key in core_dict])

    def __repr__(self):
        return f"Experiment('{self.config}')"

    ''' SECTION I: initializing methods for the various phases of the experiment '''

    def init_meta(self):
        if self.check_config():
            self.display_spacer_frame()
            self.housekeeping_lists()
            # only display the stuff below if more participants are needed
            if self.participant_number != self.config_dict["participants"]:
                self.id_generator()
                self.display_meta_forms()
                self.submit_btn(self.save_meta)
        else:
            self.display_long(
                "You seem to have edited some of the configuration identifiers in config.py.\nThe experiment cannot proceed unless all and only those keys are present which are supposed to be there.")

    def init_exposition(self):
        self.display_spacer_frame()
        self.display_long(self.config_dict["expo_text"], 8)
        self.submit_btn(self.save_expo)

    # warm up/training phase
    def init_warm_up(self):
        self.items_retrieve_shuffle(
            self.config_dict["warm_up_file"], self.config_dict["warm_up"])
        self.open_results_file()
        print("Starting Warm-Up phase.\n")
        self.display_spacer_frame()
        self.display_short(self.config_dict["warm_up_title"], 5)
        self.display_short(self.config_dict["warm_up_description"])
        if not self.config_dict["self_paced_reading"]:
            if self.config_dict["use_text_stimuli"]:
                self.display_items()
            elif not self.config_dict["use_text_stimuli"]:
                pygame.init()
                self.display_audio_stimuli()
            self.likert_scale()
            self.submit_btn(self.save_judgment_next_item)
            self.submit.config(state="disabled")
        elif self.config_dict["use_text_stimuli"] and self.config_dict["self_paced_reading"]:
            self.display_masked_item()
            self.submit.config(state="disabled")
        self.time_start = time.time()

    # initialize all critical contents of the experiment
    def init_critical(self):
        self.housekeeping_update()
        self.items_retrieve_shuffle()
        if not self.config_dict["warm_up"]:
            self.open_results_file()
        self.display_spacer_frame()
        self.display_short(self.config_dict["title"], 5)
        self.display_short(self.config_dict["description"])
        self.phases["critical"] = True
        if self.config_dict["warm_up"]:
            self.item_counter = 0
        if self.config_dict["use_text_stimuli"]:
            if self.config_dict["self_paced_reading"]:
                self.display_masked_item()
            else:
                self.display_items()
                self.likert_scale()
                self.submit_btn(self.save_judgment_next_item)
        else:
            pygame.init()
            self.display_audio_stimuli()
            self.likert_scale()
            self.submit_btn(self.save_judgment_next_item)
        self.time_start = time.time()

    # message showing up when all necessary participants have been tested
    def init_experiment_finished(self):
        frame_finished = Frame(self.root)
        frame_finished.pack(expand=False, fill="both",
                            side="top", pady=10, padx=25)
        finished_label = Label(frame_finished, font=(
            self.config_dict["font"], self.config_dict["basesize"] + 8), text=self.config_dict["finished_message"], height=12, wraplength=1000)
        finished_label.pack()

        # send confirmation e-mail if so specified
        if self.config_dict["confirm_completion"]:
            self.send_confirmation()

        self.submit_btn(self.root.destroy)
        print(
            f"\nAll Participants have been tested. If you want to test more than {self.config_dict['participants']} people, increase the amount in the specs file!")

    ''' SECTION II: display methods used by the initializing functions '''

    def display_short(self, text, size_mod=0, side="top"):
        if text != "":
            frame = Frame(self.root)
            frame.pack(expand=False, fill="both", side="top", pady=2)
            label = Label(frame, text=text, font=(
                self.config_dict["font"], self.config_dict["basesize"] + size_mod))
            label.pack(pady=2, side=side)

    def display_long(self, text, size_mod=0):
        if text != "":
            frame = Frame(self.root)
            frame.pack(expand=False, fill="both",
                       side="top", pady=10, padx=25)
            label = Label(frame, font=(self.config_dict["font"], self.config_dict["basesize"] + size_mod),
                          text=text, height=12, wraplength=1000)
            label.pack()

    def display_meta_forms(self, instruction=None):
        if instruction is None:
            instruction = self.config_dict["meta_instruction"]
        # instructions for the meta fields
        self.display_short(instruction, -5)

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

    # get the item info from the item file, store it, and shuffle the items
    def items_retrieve_shuffle(self, filename=None, warm_up_list=None):
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

        self.items = df_items

    def display_items(self, item=None):
        item = item or self.items.iloc[0, self.item_counter]
        # frame to display the item plus the scenario
        frame_item = Frame(self.root)
        frame_item.pack(expand=False, fill="both",
                        side="top", pady=10, padx=25)
        self.item_text = Label(frame_item, font=(
            self.config_dict["font"], self.config_dict["basesize"] + 8), text=item, height=7, wraplength=1000)
        self.item_text.pack()

    def display_audio_stimuli(self):
        frame_audio = Frame(self.root, height=10)
        frame_audio.pack(expand=False, fill="both",
                         side="top", pady=10, padx=25)

        # button for playing the file
        self.audio_btn = Button(frame_audio, text=self.config_dict["audio_button_text"], image=self.playimage, compound="left", fg="black", font=(
            self.config_dict["font"], self.config_dict["basesize"]), padx=20, pady=25, command=lambda: self.play_stimulus())
        self.audio_btn.pack(side="top")

    def display_masked_item(self):
        # item frame for self paced reading exps
        frame_item = Frame(self.root)
        frame_item.pack(expand=False, fill="both",
                        side="top", pady=10, padx=25)
        # note the use of the mono-spaced font here
        self.item_text = Label(frame_item, font=(
            self.config_dict["font_mono"], self.config_dict["basesize"] + 8), text=self.create_masked_item(), height=9, wraplength=1000)
        self.item_text.pack()

        # press the space bar to show next word
        self.root.bind('<space>', self.next_word)

        self.submit_btn(self.next_spr_item)

        # start the reaction times
        self.time_start = time.time()

    # mask the complete item and reveal only the specified parts
    def create_masked_item(self):
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
        return " ".join(masked_split)

    def display_feedback(self):
        # end the critical portion
        self.phases["critical"] = False

        # unless the feedback text is empty, show a frame to allow feedback entry
        if not self.config_dict["feedback"] == "":
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
            self.submit_btn(self.save_feedback)
        # otherwise, just end the exp
        else:
            self.display_over()

    def display_over(self):
        self.empty_window()
        self.display_spacer_frame()
        self.display_long(self.config_dict["bye_message"], 10)
        self.display_line()

        # state that exp is done, so that no warning message is displayed upon closing the window and end application after 5 seconds
        self.phases["finished"] = True
        self.root.after(5000, self.root.destroy)
        print("\nExperiment has finished.\n")
        # save the data set
        self.save_multi_ext(self.outdf, self.outfile,
                            self.config_dict["results_file_extension"])
        print(self.outdf)

    def display_spacer_frame(self):
        # frame to hold logo
        spacer_frame = Frame(self.root)
        spacer_frame.pack(side="top", fill="both")
        spacer_img = Label(spacer_frame, image=self.logo)
        spacer_img.pack(fill="x")
        self.display_line()

    def display_line(self):
        spacer_line_btm = Frame(self.root, height=2, width=800, bg="gray90")
        spacer_line_btm.pack(side="top", anchor="c", pady=30)

    def display_error(self):
        error_label = Label(self.root, font=(
            self.config_dict["font"], self.config_dict["basesize"] - 8), text=self.config_dict["error_judgment"], fg="red")
        error_label.pack(side="top", pady=10)
        error_label.after(800, lambda: error_label.destroy())

    ''' SECTION III: file management methods '''

    def get_config_dict(self, config):
        with open(config, "r") as file:
            config_list = file.read().splitlines()

        # remove all comments
        variable_list = [x.strip().split("#")[0]
                         for x in config_list if not x.strip().split("#")[0] == ""]

        # add all values to a list
        config_dict = {}
        for variable in variable_list:
            key, value = variable.split(" = ")
            config_dict[key] = eval(value)
        return config_dict

    def check_config(self):
        compare_config = ['fullscreen', 'allow_fullscreen_escape', 'geometry', 'window_title', 'experiment_title', 'confirm_completion', 'receiver_email', 'tester', 'logo', 'meta_instruction', 'meta_fields', 'expo_text', 'warm_up', 'warm_up_title', 'warm_up_description', 'warm_up_file', 'use_text_stimuli', 'self_paced_reading', 'cumulative', 'title', 'description', 'likert', 'endpoints', 'dynamic_fc',
                          'dynamic_img', 'google_drive_link', 'delay_judgment', 'participants', 'remove_unfinished', 'remove_ratio', 'item_lists', 'item_file', 'item_file_extension', 'items_randomize', 'results_file', 'results_file_extension', 'feedback', 'audio_button_text', 'button_text', 'finished_message', 'bye_message', 'quit_warning', 'error_judgment', 'error_meta', 'font', 'font_mono', 'basesize']

        # compare the two
        if compare_config == list(self.config_dict.keys()):
            return True
        else:
            # show the differences
            print("\nThese entries are either missing from config.py or have been added to it:\n" + str(list(set(compare_config)
                                                                                                             ^ set(list(self.config_dict.keys())))))
            return False

    def id_generator(self, size=15, chars=string.ascii_lowercase + string.ascii_uppercase + string.digits):
        self.id_string = ''.join(random.choice(chars) for _ in range(size))
        print(f"\nNew Participant ID generated: {self.id_string}\n")

    # file to store how many participants have been tested
    def housekeeping_lists(self):
        # generate folder if it does not exist already
        if not os.path.isdir(self.config_dict["experiment_title"] + "_results"):
            os.makedirs(self.config_dict["experiment_title"] + "_results")

        # if file does not exist, create it
        if not os.path.isfile(self.part_and_list_file):
            with open(self.part_and_list_file, 'a') as file:
                file.write("0")
            self.participant_number = 0
            # save self.config_dict in the results directory to validate on later runs that the same settings are being used
            with open(self.config_file, "w") as file:
                file.write(str(self.config_dict))

        # or: retrieve how many have been tested if the file already exists
        else:
            with open(self.part_and_list_file, 'r') as file:
                self.participant_number = int(file.read())
            # check if the saved config file is the same as the one in self.config_dict: dict_a == dict_b; otherwise throw a warning
            with open(self.config_file, "r") as file:
                compare_config = eval(file.read())
            # compare the core entries, as opposed to all of them; changing the font size in the middle of the exp shouldn't be a problem
            if not {k: self.config_dict[k] for k in self.config_core} == {k: compare_config[k] for k in self.config_core}:
                self.display_long(
                    f"The configurations for the currently running experiment have changed from previous participants.\nCheck '{self.config}' or start a new experiment to proceed.")
            if self.participant_number == self.config_dict["participants"]:
                self.init_experiment_finished()

        # assign participant to an item list (using the modulo method for latin square)
        self.item_list_no = self.participant_number % self.config_dict["item_lists"] + 1

    def housekeeping_update(self):
        # increase participant number and write it to the housekeeping file
        self.participant_number += 1
        with open(self.part_and_list_file, 'w') as file:
            file.write(str(self.participant_number))
        # feedback print
        print(
            f"Starting with Participant Number {self.participant_number}/{self.config_dict['participants']} now! Participant was assigned to Item File {self.item_list_no}\n")

    def open_results_file(self):
        # outfile in new folder with id number attached
        self.outfile = self.config_dict["experiment_title"] + "_results/" + self.config_dict["results_file"] + "_" + \
            str(self.participant_number).zfill(len(str(self.config_dict["participants"]))) + "_" + \
            self.id_string + self.config_dict["results_file_extension"]

        # for standard judgment experiments (either text or audio)
        if (self.config_dict["use_text_stimuli"] and not self.config_dict["self_paced_reading"]) or not self.config_dict["use_text_stimuli"]:
            # header row: id number, meta data and then item stuff
            out_l = [["id"], ["date"], ["start_time"], ["tester"], self.config_dict["meta_fields"], ["sub_exp"], ["item"],
                     ["cond"], ["judgment"], ["reaction_time"]]
        else:
            # header with a column for each word in the item (of the first item)
            out_l = [["id"], ["date"], ["start_time"], ["tester"], self.config_dict["meta_fields"], ["sub_exp"], ["item"],
                     ["cond"], self.items.iloc[0, 0].split()]

        # flatten the list of lists, remove capitalization and spaces
        out_l = [item.casefold().replace(" ", "_")
                 for sublist in out_l for item in sublist]

        # initialize pandas object
        self.outdf = pd.DataFrame(columns=out_l)

    def delete_unfinished_part(self):
        # if specified by user, do not save unfinished participant results (according to the given ratio)
        if self.config_dict["remove_unfinished"] and self.item_counter < len(self.items) * self.config_dict["remove_ratio"]:
            # also reduce the participant number in the housekeeping file
            self.participant_number -= 1
            with open(self.part_and_list_file, 'w') as file:
                file.write(str(self.participant_number))
            print(
                "Participant will not be counted towards the amount of people to be tested.\n")
        else:
            print("Results file will not be deleted and the participant will count towards the specified amount.\n")
            # save the data set
            self.save_multi_ext(self.outdf, self.outfile,
                                self.config_dict["results_file_extension"])

    def delete_file(self, file):
        if os.path.exists(file):
            if os.path.isfile(file):
                os.remove(file)
                print(f"\nFile deleted: {file}\n")
            if os.path.isdir(file):
                shutil.rmtree(file)
                print(f"\nDirectory and all contained files deleted: {file}\n")
        else:
            print(f"\nFile does not exist: {file}\n")

    def delete_all_results(self):
        result_dir = self.config_dict["experiment_title"] + "_results"
        for x in [result_dir, self.part_and_list_file]:
            self.delete_file(x)

    def merge_all_results(self):
        outfile = self.config_dict["experiment_title"] + \
            "_results_full" + self.config_dict["results_file_extension"]

        # Get results files
        files_dir = self.config_dict["experiment_title"] + "_results/"
        results_files = sorted(
            glob.glob(files_dir + f'*{self.config_dict["results_file_extension"]}'))

        # remove the feedback file
        if files_dir + "FEEDBACK" + self.config_dict["results_file_extension"] in results_files:
            results_files.remove(files_dir + "FEEDBACK" +
                                 self.config_dict["results_file_extension"])

        # feedback print
        print(f'\nFound {len(results_files)} results files:\n')
        for i in range(0, len(results_files)):
            print(
                f"{results_files[i]} \t {round(os.path.getsize(results_files[i]) / 1000, 3)} KB")

        dfs = [self.read_multi_ext(x, self.config_dict["results_file_extension"])
               for x in results_files]
        df_all = pd.concat(dfs)

        self.save_multi_ext(
            df_all, outfile, self.config_dict["results_file_extension"])

        print(f"\nMerged results file generated: {outfile}")

    def read_multi_ext(self, file, extension):
        if extension == ".csv":
            df = pd.read_csv(file, sep=";")
        elif extension == ".xlsx":
            df = pd.read_excel(file)
        elif extension == ".txt":
            df = pd.read_table(file)
        return df

    def save_multi_ext(self, df, file, extension):
        if extension == ".csv":
            df.to_csv(file, sep=';', index=False)
        elif extension == ".xlsx":
            df.to_excel(file, sheet_name='Sheet1', index=False)
        elif extension == ".txt":
            df.to_table(file, index=False)

    def send_confirmation(self):
        subject = f"{self.config_dict['experiment_title']}: Experiment Finished"
        body = f"Dear User,\n\nThis is to let you know that your experiment {self.config_dict['experiment_title']} has finished and all {self.config_dict['participants']} participants have been tested. We have attached the results file below.\n\nRegards,\nPyExpTK\n\n"
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

        print(
            f"\nConfirmation e-mail sent to:\t{self.config_dict['receiver_email']}\nAttached file:\t{filename}\n")

    ''' SECTION IV: Buttons '''

    # judgment radio buttons in frame
    def likert_scale(self, endpoints=None):
        if endpoints == None:
            endpoints = self.config_dict["endpoints"]
        # frame for the judgment buttons
        frame_judg = Frame(self.root, relief="sunken", bd=2)
        frame_judg.pack(side="top", pady=20)

        # non-dynamic likert or forced choice
        if not self.config_dict["dynamic_fc"] and not self.config_dict["dynamic_img"]:
            # endpoint 1
            if endpoints[0] != "":
                scale_left = Label(frame_judg, text=endpoints[0], font=(
                    self.config_dict["font"], self.config_dict["basesize"]), fg="gray")
                scale_left.pack(side="left", expand=True, padx=10, pady=5)

            # likert scale
            for x in self.config_dict['likert']:
                x = Radiobutton(frame_judg, text=str(x), variable=self.judgment, value=str(
                    x).casefold().replace(" ", "_"), font=(self.config_dict["font"], self.config_dict["basesize"]))
                self.likert_list.append(x)
                x.pack(side="left", expand=True, padx=10)
                x.config(state="disabled")

            # endpoint 2
            if endpoints[1] != "":
                scale_right = Label(frame_judg, text=endpoints[1], font=(
                    self.config_dict["font"], self.config_dict["basesize"]), fg="gray")
                scale_right.pack(side="left", expand=True, padx=10, pady=5)

        # get the Forced Choice options from the item file
        elif self.config_dict["dynamic_fc"] and not self.config_dict["dynamic_img"]:
            for x, name in zip(self.items.iloc[self.item_counter, 4:], self.items.iloc[:, 4:].columns):
                x = Radiobutton(frame_judg, text=str(x), variable=self.judgment, value=str(
                    name).casefold().replace(" ", "_"), font=(self.config_dict["font"], self.config_dict["basesize"]))
                self.likert_list.append(x)
                x.pack(side="left", expand=True, padx=10)
                x.config(state="disabled")

        # display images instead of text as answer options
        elif self.config_dict["dynamic_img"]:
            # reset images dict
            self.fc_images = {}
            # for rescaling purposes
            desired_width = 300
            for x, name in zip(self.items.iloc[self.item_counter, 4:], self.items.iloc[:, 4:].columns):
                image = Image.open(x)
                # compute rescaled dimensions
                new_dimensions = (image.width / (image.width / desired_width),
                                  image.height / (image.width / desired_width))
                image = image.resize(new_dimensions, Image.ANTIALIAS)
                self.fc_images[x] = ImageTk.PhotoImage(image)

                x = Radiobutton(frame_judg, image=self.fc_images[x], variable=self.judgment, value=str(
                    name).casefold().replace(" ", "_"), font=(self.config_dict["font"], self.config_dict["basesize"]))
                self.likert_list.append(x)
                x.pack(side="left", expand=True, padx=25)
                x.config(state="disabled")

        if self.config_dict["use_text_stimuli"] and not self.config_dict["self_paced_reading"]:
            # enable likert choice after specified delay is over
            read_item_timer = Timer(
                self.config_dict["delay_judgment"], self.enable_submit)
            read_item_timer.start()

    # submit button that takes different continuation functions
    def submit_btn(self, continue_func):
        self.display_line()

        frame_submit = Frame(self.root)
        frame_submit.pack(expand=False, fill="both", side="top", pady=10)
        self.submit = Button(frame_submit, text=self.config_dict["button_text"], fg="blue", font=(self.config_dict["font"], self.config_dict["basesize"] - 10), padx=10, pady=5,
                             command=continue_func, highlightcolor="gray90", highlightbackground="white", highlightthickness=0)
        self.submit.pack()

        # in the critical portion of the audio stimuli, the button is deactivated by default and becomes available after the item was played in full
        # in self-paced reading, only after all words of an item have been displayed
        if (not self.config_dict["use_text_stimuli"] or self.config_dict["self_paced_reading"]) and self.phases["critical"]:
            self.submit.config(state="disabled")

    ''' SECTION V: methods that are called upon button or keyboard presses '''

    def play_stimulus(self):
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

    # function for submit button
    def save_meta(self):
        # empty the list (necessary for when the button is pressed multiple times)
        self.meta_entries_final.clear()
        # loop over all fields to get the entry
        for i in range(len(self.meta_entries)):
            # store the entries of the fields in the final attribute
            self.meta_entries_final.append(self.meta_entries[i].get())

        # if any of the fields are empty, print out an error message
        if "" in self.meta_entries_final:
            error_label = Label(self.root, font=(
                self.config_dict["font"], self.config_dict["basesize"] - 8), text=self.config_dict["error_meta"], fg="red")
            error_label.pack(side="top", pady=10)
            error_label.after(800, lambda: error_label.destroy())

        # if all selections were made, move on to exposition
        else:
            self.empty_window()
            self.init_exposition()

    # clear window and move on to items
    def save_expo(self):
        self.empty_window()
        self.init_warm_up(
        ) if self.config_dict["warm_up"] else self.init_critical()

    # increases the word counter and updates the label text
    def next_word(self, bla):
        # no need to record the reaction time for first button press. thats before anything is shown
        if self.word_index == 0:
            # go to next word
            self.word_index += 1
            self.item_text.config(text=self.create_masked_item())
            # start reaction times
            self.time_start = time.time()
        # if the word is in the middle of the item, take the reaction times and reveal the next one
        elif self.word_index != 0 and self.word_index < len(self.items.iloc[self.item_counter, 0].split()):
            # reaction times
            self.spr_reaction_times[self.word_index] = time.time(
            ) - self.time_start

            # reset reaction times and go to next word
            self.word_index += 1
            self.item_text.config(text=self.create_masked_item())
            self.time_start = time.time()
        # if all words have been shown, activate the continue button
        elif self.word_index == len(self.items.iloc[self.item_counter, 0].split()):
            # record final reaction time and store it
            self.spr_reaction_times[self.word_index] = time.time(
            ) - self.time_start

            # re-mask the item text so that participants cant just read the entire item at the end (especially important in the cumulative version)
            self.item_text.config(text=self.masked)
            self.enable_submit()

    def next_spr_item(self):
        # feedback print
        print(f"Done with item {self.item_counter + 1}/{len(self.items)}!")

        # disable the submit button
        self.submit.config(state="disabled")

        # compile all the info we need for the results file
        out_l = [[self.id_string], [self.today], [self.start_time], [self.config_dict["tester"]], self.meta_entries_final, list(
            self.items.iloc[self.item_counter, 1:4]), [round(value, 5) for value in self.spr_reaction_times.values()]]
        # flatten list of lists; turn to string, remove capital letters
        out_l = [str(item).casefold() for sublist in out_l for item in sublist]

        # add rows to pandas df
        self.outdf.loc[len(self.outdf)] = out_l

        # make sure that the next item is shown
        self.item_counter += 1

        # if there are more items to be shown, do that
        if self.item_counter < len(self.items):
            # empty the stored reaction times
            self.spr_reaction_times = {}
            # run masking on new item and reset the word index
            self.word_index = 0
            self.item_text.config(text=self.create_masked_item())
        else:
            if self.phases["critical"]:
                # remove the binding from the space bar
                self.root.unbind("<space>")
                # go to the feedback section
                self.empty_window()
                self.display_feedback()
            # if we are at the end of the warm up phase, clear window and init critical
            elif not self.phases["critical"]:
                self.word_index = 0
                print("\nWarm-Up completed. Proceeding with critical phase now.\n")
                self.empty_window()
                self.init_critical()

    # submit the judgment and continue to next item
    def save_judgment_next_item(self):
        # check that a selection was made
        if self.judgment.get() != "":
            # reaction times: subtract start time from stop time to get reaction times
            if self.config_dict["use_text_stimuli"]:
                reaction_time = time.time() - self.time_start - \
                    self.config_dict["delay_judgment"]
            # for audio stimuli, also subtract the length of the item (because judgments are available only after the item has been played anyway)
            else:
                reaction_time = time.time() - self.time_start - self.sound.get_length()

            # set up all the info that should be written to the file (in that order)
            out_l = [[self.id_string], [self.today], [self.start_time], [self.config_dict["tester"]], self.meta_entries_final, list(self.items.iloc[self.item_counter, 1:4]), [
                self.judgment.get()], [str(round(reaction_time, 5))]]

            # flatten list of lists; turn to string, remove capital letters
            out_l = [str(item).casefold()
                     for sublist in out_l for item in sublist]

            # add rows to pandas df
            self.outdf.loc[len(self.outdf)] = out_l

            # progress report
            print(f"Done with item {self.item_counter + 1}/{len(self.items)}!")

            # reset buttons for next item and increase item counter
            self.judgment.set("")
            self.item_counter += 1

            # if there are more items to be shown, do that
            if self.item_counter < len(self.items):
                if self.config_dict["use_text_stimuli"]:
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
                # because the play button will automatically update itself to play the new item (bc of the item_counter), we only need to disable the button for audio stimuli
                else:
                    self.submit.config(state="disabled")
                    for obj in self.likert_list:
                        obj.config(state="disabled")
                    self.flash_play(0)
                # in case of dynamic FC we need to update the radio buttons
                if self.config_dict["dynamic_fc"]:
                    for i, x, name in zip(range(len(self.likert_list)), self.items.iloc[self.item_counter, 4:], self.items.iloc[:, 4:].columns):
                        self.likert_list[i].config(text=x, value=name)

                # and reset the time counter for the reaction times
                self.time_start = time.time()

            # otherwise either go to the feedback section or enter the critical stage of the exp
            else:
                if self.phases["critical"]:
                    self.empty_window()
                    self.display_feedback()
                elif not self.phases["critical"]:
                    print("\nWarm-Up completed. Proceeding with critical phase now.\n")
                    self.empty_window()
                    self.init_critical()

        # if no selection was made using the radio buttons, display error
        else:
            self.display_error()

    def save_feedback(self):
        # feedback file will be saved together with the results, but under a different name; all feedback texts together in a single file
        feedback_file = self.config_dict["experiment_title"] + "_results/" + \
            "FEEDBACK" + self.config_dict["results_file_extension"]

        experiment_duration = round(
            (time.time() - self.experiment_started)/60, 2)

        # save the feedback with id string and internal number as csv file
        if self.feedback.get().replace(" ", "") == "":
            out_l = [self.id_string, experiment_duration,
                     self.participant_number, "NA"]
        else:
            out_l = [self.id_string, experiment_duration,
                     self.participant_number, self.feedback.get()]

        # open the feedback file or create one if it doesn't exist
        if os.path.isfile(feedback_file):
            df_feedback = self.read_multi_ext(
                feedback_file, self.config_dict["results_file_extension"])
        else:
            df_feedback = pd.DataFrame(
                columns=["id", "duration_minutes", "part_no", "feedback"])
        # add the new row of the current participant and save the file
        df_feedback.loc[len(df_feedback)] = out_l
        self.save_multi_ext(df_feedback, feedback_file,
                            self.config_dict["results_file_extension"])

        self.display_over()

    def enable_submit(self):
        if not self.phases["quit"]:
            self.submit.config(state="normal")
            for obj in self.likert_list:
                obj.config(state="normal")

    def flash_play(self, count):
        bg = self.audio_btn.cget('highlightcolor')
        fg = self.audio_btn.cget('highlightbackground')
        self.audio_btn.config(highlightcolor=fg, highlightbackground=bg)
        count += 1
        if (count < 10):
            self.audio_btn.after(100, self.flash_play, count)

    # warn before closing the root experiment window with the system buttons
    def on_closing(self):
        if messagebox.askokcancel("Quit", self.config_dict["quit_warning"]):
            self.root.destroy()
            self.phases["quit"] = True
            if self.phases["critical"] and not self.phases["finished"]:
                print("\nIMPORTANT!: Experiment was quit manually.")
                # either save the results or don't (depending on specification)
                self.delete_unfinished_part()
            else:
                print(
                    "\nExperiment was quit manually. This happened before the critical section, so there is no action required.")


if __name__ == '__main__':
    Exp = Experiment("test.py")
    Exp.init_meta()
    Exp.root.mainloop()
