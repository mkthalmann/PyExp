from tkinter import *
from tkinter import messagebox
from threading import Timer
import codecs
import xlrd
import random
import string
import re
import os
import glob
import csv
from xlsxwriter.workbook import Workbook
import shutil
import pygame
import time

import email
import smtplib
import ssl

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from specs import *

'''TO DO:

    - MAJOR POINTS
        - audio items from owncloud/google drive/dropbox (streamed)
        - send the results file via e-mail
        - add video support
        - option to have several experimental blocks with a break inbetween
        - either add automatic conversion from csv to xlsx or add handling of csv files
        - convert all data handling to use pandas

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
        # Calculate geometry
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        # Set geometry
        self.root.geometry('{}x{}+{}+{}'.format(width, height, x, y))

    # list of all frames and content within them
    # and delete them from view
    def empty_window(self):
        # get children
        widget_list = self.root.winfo_children()

        # get grandchildren
        for item in widget_list:
            if item.winfo_children():
                widget_list.extend(item.winfo_children())

        # widget deletion
        for item in widget_list:
            item.pack_forget()

    # make the window fullscreen (Escape to return to specified geometry)
    def fullscreen(self):
        self.root.geometry("{0}x{1}+0+0".format(
            self.root.winfo_screenwidth() - 3, self.root.winfo_screenheight() - 3))
        if allow_fullscreen_escape:
            self.root.bind('<Escape>', self.return_geometry)

    # return to specified geometry event (bound to Escape key in fullscreen method)
    def return_geometry(self, event):
        self.root.geometry(geometry)


class Experiment(Window):

    def __init__(self):
        # generate the window
        self.root = Tk()

        # specifiy the size
        self.root.geometry(geometry)

        # center the window
        self.center_window()

        # add warning before closing the window
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # add the title
        self.root.wm_title(window_title)

        # check if app is still running
        self.quit = False

        # item list to be used for the participant
        self.item_list_no = ""

        # housekeeping file which tracks how many participants have been tested
        self.part_and_list_file = experiment_title + "_storage.txt"

        # store meta data
        self.meta_entries = []
        self.meta_entries_final = []

        # feedback text
        self.feedback = ""

        # variable to store the judgment, item and cond info
        self.likert_list = []
        self.judgment = StringVar()

        # store items
        self.item_counter = 0

        # store all widgets
        self.widget_list = []

        # reaction times
        self.time_start = ""
        self.time_stop = ""
        self.time_reaction = ""

        # create a photoimage object for the play button
        self.photoimage = PhotoImage(file="media/play.png").subsample(6, 6)

        # store and resize the logo for display
        self.logo = PhotoImage(file=logo).subsample(6, 6)

        # masked item
        self.masked = ""
        # number for the word that is displayed first in self-paced-reading
        self.word_index = 0
        # dictionary to store all the reaction times in self-paced-reading
        self.spr_reaction_times = {}

        # check whether we are in the critical portion
        self.critical = False

        # value to check whether exp is done
        self.finished = False

    ''' SECTION I: initializing methods for the various phases of the experiment '''

    # intitialize widgets used for meta data
    def init_meta(self):
        self.display_spacer_frame()
        if fullscreen:
            self.fullscreen()
        self.housekeeping_lists()
        # only display the stuff below if more participants are needed
        if self.participant_number != participants:
            self.id_generator()
            self.display_meta_forms()
            self.submit_btn(self.save_meta)

    # intitialize widgets used for exposition
    def init_exposition(self):
        self.display_spacer_frame()
        self.display_exposition()
        self.submit_btn(self.save_expo)

    # warm up/training phase
    def init_warm_up(self):
        self.items_retrieve_shuffle(warm_up_file, warm_up)
        self.open_results_file()
        print("Starting Warm-Up phase.\n")
        self.display_spacer_frame()
        self.display_instructions(warm_up_title, warm_up_description)
        if use_text_stimuli and self_paced_reading:
            self.display_masked_item()
            self.submit.config(state="disabled")
        elif use_text_stimuli and not self_paced_reading:
            self.display_items()
            self.likert_scale()
            self.submit_btn(self.save_judgment_next_item)
        else:
            pygame.init()
            self.display_audio_stimuli()
            self.likert_scale()
            self.submit_btn(self.save_judgment_next_item)
            self.submit.config(state="disabled")
        self.time_start = time.time()

    # initialize all critical contents of the experiment
    def init_critical(self):
        self.housekeeping_update()
        self.items_retrieve_shuffle()
        if not warm_up:
            self.open_results_file()
        self.display_spacer_frame()
        self.display_instructions()
        self.critical = True
        if warm_up:
            self.item_counter = 0
        if use_text_stimuli:
            if self_paced_reading:
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
    # as determined by storage file and specified number of participants
    def init_experiment_finished(self):
        frame_finished = Frame(self.root)
        frame_finished.pack(expand=False, fill=BOTH, side="top", pady=10, padx=25)
        finished_label = Label(frame_finished, font=(font, basesize + 8), text=finished_message, height=12, wraplength=1000)
        finished_label.pack()

        # send confirmation e-mail if so specified
        if confirm_completion:
            self.send_confirmation()

        self.submit_btn(self.root.destroy)
        print("\nAll Participants have been tested. If you want to test more than %d people, increase the amount in the specs file!" % participants)

    ''' SECTION II: display methods used by the initializing functions '''

    # make labels and entry fields for the fields specified above
    def display_meta_forms(self, fields=meta_fields, instruction=meta_instruction):

        # instructions for the meta fields
        meta_frame = Frame(self.root)
        meta_frame.pack(expand=False, fill=BOTH, side="top", pady=2)
        label = Label(meta_frame, text=instruction, font=(font, basesize - 5))
        label.pack(pady=10)

        # create frame and label for each of the entry fields
        for i in range(len(fields)):
            row = Frame(self.root)
            lab = Label(row, width=15, text=fields[i], anchor='w', font=(font, basesize - 8))
            # create the entry fields and store them
            self.meta_entries.append(Entry(row))

            # deploy all of it
            row.pack(side=TOP, padx=5, pady=5)
            lab.pack(side=LEFT)
            self.meta_entries[i].pack(side=RIGHT, expand=YES, fill=X)

    # expository text and some instructions
    def display_exposition(self, text=expo_text):
        frame_expo = Frame(self.root)
        frame_expo.pack(expand=False, fill=BOTH, side="top", pady=10, padx=25)
        expo_label = Label(frame_expo, font=(font, basesize + 8), text=text, height=12, wraplength=1000)
        expo_label.pack()

    # get the item info from the item file, store it, and shuffle the items
    def items_retrieve_shuffle(self, filename=item_file, warm_up_list=None):
        # in case there is no additional argument, use the item list number
        if warm_up_list is None:
            # load the correct item file for the specific participant
            infile = filename + str(self.item_list_no) + '.xlsx'
        # if there is (as with the warm up)
        else:
            infile = filename + '.xlsx'

        # prepare the list now, we'll used it in the for-loop later
        items = []

        # access the first worksheet
        inbook = xlrd.open_workbook(infile, 1)
        insheet = inbook.sheet_by_index(0)

        # store all the information contained in the workbook in a list to be used late
        for rowx in range(1, insheet.nrows):  # 1: skip the header row
            rowval = insheet.row_values(rowx)
            items.append(rowval[0:])

        # if specified, randomize the items
        if items_randomize:
            random.shuffle(items)

        self.items = items

    # sunken frame plus text
    def display_instructions(self, text1=title, text2=description, size=basesize, color="black"):
        if text1 != "":
            frame_title = Frame(self.root)
            frame_title.pack(expand=False, fill=BOTH, side="top", pady=2)
            label = Label(frame_title, text=text1, fg=color, font=(font, size))
            label.pack(pady=2, side=LEFT)

        if text2 != "":
            frame_desc = Frame(self.root)
            frame_desc.pack(expand=False, fill=BOTH, side="top", pady=2)
            label = Label(frame_desc, text=text2, fg=color, font=(font, size))
            label.pack(pady=2, side=LEFT)

    # item frame
    def display_items(self, item=None):
        item = item or self.items[self.item_counter][0]
        # frame to display the item plus the scenario
        frame_item = Frame(self.root)
        frame_item.pack(expand=False, fill=BOTH, side="top", pady=10, padx=25)
        self.item_text = Label(frame_item, font=(font, basesize + 8), text=item, height=9, wraplength=1000)
        self.item_text.pack()

    # for audio stimuli
    def display_audio_stimuli(self):
        # frame for the items
        frame_audio = Frame(self.root, height=10)
        frame_audio.pack(expand=False, fill=BOTH, side="top", pady=10, padx=25)

        # button for playing the file
        self.audio_btn = Button(frame_audio, text=audio_button_text, image=self.photoimage, compound=LEFT, fg="black", font=(font, basesize), padx=20, pady=5, command=lambda: self.play_stimulus())
        self.audio_btn.pack(side=TOP)

    # item frame for self paced reading exps
    def display_masked_item(self):
        # display the item
        frame_item = Frame(self.root)
        frame_item.pack(expand=False, fill=BOTH, side="top", pady=10, padx=25)
        # note the use of the monospaced font here
        self.item_text = Label(frame_item, font=(font_mono, basesize + 8), text=self.create_masked_item(), height=9, wraplength=1000)
        self.item_text.pack()

        # press the space bar to show next word
        self.root.bind('<space>', self.next_word)

        self.submit_btn(self.next_spr_item)

        # start the reaction times
        self.time_start = time.time()

    # mask the complete item and reveal only the specified parts
    def create_masked_item(self):
        # replace all non-whitespace characters with underscores
        self.masked = re.sub("[^ ]", "_", self.items[self.item_counter][0])
        masked_split = self.masked.split()

        # if cumulative option is selected, the word identified by counter and all previous ones will be shown
        if cumulative:
            for i in range(self.word_index):
                masked_split[i] = self.items[self.item_counter][0].split()[i]
        # if non-cumulative, only the target word is displayed
        else:
            # if the index is zero, dont unmask anything
            if self.word_index == 0:
                masked_split = masked_split
            # otherwise show the word bearing the index - 1 (without the subtraction we would always skip the first word in the unmasking because of the previous part of the conditional)
            else:
                masked_split[self.word_index - 1] = self.items[self.item_counter][0].split()[self.word_index - 1]
        return " ".join(masked_split)

    def display_feedback(self):
        # end the critical portion
        self.critical = False

        # unless the feedback text is empty, show a frame to allow feedback entry
        if not feedback == "":
            # instruction for the feedback
            self.display_spacer_frame()

            feedback_frame = Frame(self.root)
            feedback_frame.pack(expand=False, fill=BOTH, side="top", pady=10, padx=25)
            label = Label(feedback_frame, text=feedback, font=(font, basesize - 5))
            label.pack(pady=15, side="top")

            # entry field for the feedback
            self.feedback = Entry(feedback_frame)
            self.feedback.pack(side="top", expand=YES, fill=X, ipady=5, padx=50)

            # button to submit the feedback
            self.submit_btn(self.save_feedback)
        # otherwise, just end the exp
        else:
            self.display_over()

    def display_over(self):
        # destroy all widgets
        for widget in self.root.winfo_children():
            widget.destroy()

        self.display_spacer_frame()
        frame_bye = Frame(self.root)
        frame_bye.pack(expand=False, fill=BOTH, side="top", pady=10, padx=25)
        bye_label = Label(frame_bye, font=(font, basesize + 10), text=bye_message, height=8, wraplength=1000)
        bye_label.pack()
        self.display_line()

        # state that exp is done, so that no warning message is displayed upon closing the window
        self.finished = True

        # end application after 5 seconds
        self.root.after(5000, self.root.destroy)
        print("\nExperiment has finished.")

    def display_spacer_frame(self):
        # frame to hold logo and text
        spacer_frame = Frame(self.root)
        spacer_frame.pack(side="top", fill=BOTH)

        # logo frame on the right
        spacer_img = Label(spacer_frame, image=self.logo)
        spacer_img.pack(fill=X)

        self.display_line()

    def display_line(self):
        # horizontal line
        spacer_line_btm = Frame(self.root, height=2, width=800, bg="gray90")
        spacer_line_btm.pack(side="top", anchor="c", pady=30)

    def display_error(self):
        error_label = Label(self.root, font=(font, basesize - 8), text=error_judgment, fg="red")
        error_label.pack(side="top", pady=10)
        error_label.after(800, lambda: error_label.destroy())

    ''' SECTION III: file management methods '''

    # participant id generator
    def id_generator(self, size=15, chars=string.ascii_lowercase + string.ascii_uppercase + string.digits):
        self.id_string = ''.join(random.choice(chars) for _ in range(size))
        print("\nNew Participant ID generated: %s\n" % self.id_string)

    # generate global storage file for item lists
    def housekeeping_lists(self):
        # either: set up a new file to store how many participants have been tested
        # if file does not exist, create it
        if not os.path.isfile(self.part_and_list_file):
            fn = codecs.open(self.part_and_list_file, "a", 'utf-8')
            fn.write("0")
            fn.close()
            self.participant_number = 0
        # or: retrieve how many have been tested if the file already exists
        else:
            fn = codecs.open(self.part_and_list_file, "r", "utf-8")
            self.participant_number = int(fn.read())
            fn.close()
            if self.participant_number == participants:
                self.init_experiment_finished()

        # assign participant to an item list (using the modulo method for latin square)
        x = item_lists
        self.item_list_no = self.participant_number % x + 1

    # update the housekeeping file
    def housekeeping_update(self):
        # increase participant number
        self.participant_number += 1
        # and write that to the housekeeping file before closing it
        fn = codecs.open(self.part_and_list_file, "w", "utf-8")
        fn.write(str(self.participant_number))
        fn.close()
        # feedback print
        print("Starting with Participant Number %d/%d now!" % (self.participant_number, participants))
        print("Participant was assigned to Item File: %s\n" % self.item_list_no)

    def open_results_file(self):
        # prepare the results file
        # generate folder if it does not exist already
        if not os.path.isdir(experiment_title + "_results"):
            os.makedirs(experiment_title + "_results")

        # outfile in new folder with id number attached
        self.outfile = experiment_title + "_results/" + results_file + "_" + str(self.participant_number) + "_" + self.id_string + results_file_extension

        # empty file
        open(self.outfile, "w").close()

        # for standard judgment experiments (either text or audio)
        if (use_text_stimuli and not self_paced_reading) or not use_text_stimuli:
            # header row:
            # id number, meta data and then item stuff
            out_l = [["id"], meta_fields, ["sub_exp"], ["item"], ["cond"], ["judgment"], ["reaction_time"]]
            # flatten the list of lists into a normal list
            out_l = [item for sublist in out_l for item in sublist]
        else:
            # header with a column for each word in the item (of the first item)
            out_l = [["id"], meta_fields, ["sub_exp"], ["item"], ["cond"], self.items[0][0].split()]
            out_l = [item for sublist in out_l for item in sublist]

        with open(self.outfile, 'a') as file:
            file.write("\t".join([str(word) for word in out_l]))
            file.write('\n')

    def delete_unfinished_part(self):
        # print the number of completed items
        print("\nParticipant completed %d/%d items." % (self.item_counter, len(self.items)))
        # if specified by user, delete unfinished participant results files (according to the given ratio)
        if remove_unfinished and self.item_counter < len(self.items) * remove_ratio:
            self.delete_file(self.outfile)
            # also reduce the participant number in the housekeeping file
            self.participant_number -= 1
            fn = codecs.open(self.part_and_list_file, "w", "utf-8")
            fn.write(str(self.participant_number))
            fn.close()
            print("Participant will not be counted towards the amount of people to be tested.\n")
        else:
            print("Results file will not be deleted and the participant will count towards the specified amount.")

    def delete_file(self, file):
        if os.path.exists(file):
            if os.path.isfile(file):
                os.remove(file)
                print("\nFile deleted: %s\n" % file)
            if os.path.isdir(file):
                shutil.rmtree(file)
                print("\nDirectory and all contained files deleted: %s\n" % file)
        else:
            print("\nFile does not exist: %s\n" % file)

    def delete_all_results(self):
        # delete results directory
        result_dir = experiment_title + "_results"
        self.delete_file(result_dir)
        # delete housekeeping file
        self.delete_file(self.part_and_list_file)

    def merge_all_results(self):
        outfile = experiment_title + "_results_full.csv"

        # Get csv files
        files_dir = experiment_title + "_results/"
        results_files = sorted(glob.glob(files_dir + '*.csv'))

        # remove the feedback file
        if files_dir + "FEEDBACK.csv" in results_files:
            results_files.remove(files_dir + "FEEDBACK.csv")

        print('\nFound %d results files:\n' % len(results_files))
        for i in range(0, len(results_files)):
            print("%s \t %s KB" % (results_files[i], round(os.path.getsize(results_files[i]) / 1000, 3)))

        # create or empty the file to hold all results
        results_full = open(outfile, "w")
        # and write all of the first file's contents
        for line in open(results_files[0]):
            results_full.write(line)
        # for all other files, skip the header line
        for i in range(len(results_files)):
            f = open(results_files[i])
            # skip header
            f.__next__()
            # write all the lines
            for line in f:
                results_full.write(line)
            f.close()
        results_full.close()

        print("\nMerged results file generated: %s" % outfile)

    def send_confirmation(self):
        subject = "%s: Experiment Finished" % experiment_title
        body = "Dear User,\n\nThis is to let you know that your experiment %s has finished and all %d participants have been tested. We have attached the results file below.\n\nRegards,\nPyExpTK\n\n" % (experiment_title, participants)
        sender_email = "pyexptk@gmail.com"
        password = "pyexp_1_2_3"

        # Create a multipart message and set headers
        message = MIMEMultipart()
        message["From"] = sender_email
        # message["To"] = receiver_email
        message["Subject"] = subject
        message["Bcc"] = receiver_email  # Recommended for mass emails

        # Add body to email
        message.attach(MIMEText(body, "plain"))

        # merged results
        self.merge_all_results()
        filename = experiment_title + "_results_full.csv"

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
            server.sendmail(sender_email, receiver_email, text)

        print("\nConfirmation e-mail sent to:\t%s\nAttached file:\t%s\n" % (receiver_email, filename))

    # helper function to convert csv files to files that are actually usable by the Experiment class
    def convert_csv_to_xlsx():
        # grabs all files in directory
        for csvfile in glob.glob(os.path.join('.', '*.csv')):
            workbook = Workbook(csvfile[:-4] + '.xlsx')
            worksheet = workbook.add_worksheet()
            with open(csvfile, 'rt', encoding='utf8') as f:
                reader = csv.reader(f)
                for r, row in enumerate(reader):
                    for c, col in enumerate(row):
                        worksheet.write(r, c, col)
            workbook.close()

    ''' SECTION IV: Buttons '''

    def play_stimulus(self):
        # load file into mixer
        self.sound = pygame.mixer.Sound(self.items[self.item_counter][0])
        # play file
        self.sound.play()
        # after sound is over, change the value of played
        played_sound_timer = Timer(self.sound.get_length(), self.enable_submit)
        played_sound_timer.start()

    # judgment radio buttons in frame
    def likert_scale(self, endpoints=endpoints):
        # frame for the judgment buttons
        frame_judg = Frame(self.root, relief="sunken", bd=2)
        frame_judg.pack(side="top", pady=20)

        # non-dynamic likert or forced choice
        if not dynamic_fc:
            # buttons within the frame
            # endpoint 1
            if endpoints[0] != "":
                scale_left = Label(frame_judg, text=endpoints[0], font=(font, basesize), fg="gray")
                scale_left.pack(side="left", expand=True, padx=10, pady=5)

            # likert scale
            for x in likert:
                x = Radiobutton(frame_judg, text=str(x), variable=self.judgment, value=str(x), font=(font, basesize))
                self.likert_list.append(x)
                x.pack(side="left", expand=True, padx=10)
                x.config(state="disabled")

            # endpoint 2
            if endpoints[1] != "":
                scale_right = Label(frame_judg, text=endpoints[1], font=(font, basesize), fg="gray")
                scale_right.pack(side="left", expand=True, padx=10, pady=5)

        # get the Forced Choice options from the item file
        elif dynamic_fc:
            for x in self.items[self.item_counter][4:]:
                x = Radiobutton(frame_judg, text=str(x), variable=self.judgment, value=str(x), font=(font, basesize))
                self.likert_list.append(x)
                x.pack(side="left", expand=True, padx=10)
                x.config(state="disabled")

            for obj in self.likert_list:
                    obj.config(state="disabled")

        if use_text_stimuli and not self_paced_reading:
            # enable likert choice after two seconds
            read_item_timer = Timer(delay_judgment, self.enable_submit)
            read_item_timer.start()

    # submit button
    def submit_btn(self, continue_func):
        self.display_line()

        frame_submit = Frame(self.root)
        frame_submit.pack(expand=False, fill=BOTH, side="top", pady=10)
        # for the different commands, look below
        self.submit = Button(frame_submit, text=button_text, fg="blue", font=(font, basesize - 10), padx=10, pady=5, command=continue_func, highlightcolor="gray90", highlightbackground="white", highlightthickness=0)
        self.submit.pack()
        # in the critical portion of the audio stimuli, the button is deactivated by default
        # only becomes available after the item was played in full
        # in self-paced reading, only after all words of an item have been displayed
        if (not use_text_stimuli or self_paced_reading) and self.critical:
            self.submit.config(state="disabled")

    ''' SECTION V: methods that are called upon button or keyboard presses '''

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
            error_label = Label(self.root, font=(font, basesize - 8), text=error_meta, fg="red")
            error_label.pack(side="top", pady=10)
            error_label.after(800, lambda: error_label.destroy())

        # if all selections were made, move on to critical portion
        else:
            # empty the window
            self.empty_window()
            # launch the item judgment portion of the experiment
            self.init_exposition()

    # clear window and move on to critical items
    def save_expo(self):
        # empty the window
        self.empty_window()
        # launch the item judgment portion of the experiment
        if warm_up:
            self.init_warm_up()
        else:
            self.init_critical()

    # increases the word counter and updates the label text
    def next_word(self, bla):
        # no need to record the reaction time for first button press. thats before anything is shown
        if self.word_index == 0:
            # start reaction times
            self.time_start = time.time()

            # go to next word
            self.word_index += 1
            self.item_text.config(text=self.create_masked_item())
        # if the word is in the middle of the item, take the reaction times and reveal the next one
        elif self.word_index != 0 and self.word_index < len(self.items[self.item_counter][0].split()):
            # compute the reaction times
            self.time_stop = time.time()
            self.time_reaction = self.time_stop - self.time_start

            # store the reaction times in the dictionarx
            self.spr_reaction_times[self.word_index] = self.time_reaction

            # reset reaction times and go to next word
            self.time_start = time.time()
            self.word_index += 1
            self.item_text.config(text=self.create_masked_item())
        # if all words have been shown, activate the continue button
        elif self.word_index == len(self.items[self.item_counter][0].split()):
            # record final reaction time and store it
            self.time_stop = time.time()
            self.time_reaction = self.time_stop - self.time_start
            self.spr_reaction_times[self.word_index] = self.time_reaction

            # remask the item text so that participants cant just read the entire item at the end (especially important in the cumulative version)
            self.item_text.config(text=self.masked)
            self.enable_submit()

    def next_spr_item(self):
        # feedback print
        print("Done with item %s/%s!" % (self.item_counter + 1, len(self.items)))

        # disable the submit button
        self.submit.config(state="disabled")

        # compile all the info we need for the results file
        out_l = [[self.id_string], self.meta_entries_final, [self.items[self.item_counter][1]], [self.items[self.item_counter][2]], [self.items[self.item_counter][3]], self.spr_reaction_times.values()]
        # flatten list of lists
        out_l = [item for sublist in out_l for item in sublist]

        # save the data to the file
        # alternative: file.write("\t".join([str(word) for word in out_l]))
        with open(self.outfile, 'a') as file:
            file.write("\t".join([str(word) for word in out_l]))
            file.write('\n')

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
            if self.critical:
                # close the results file
                file.close()
                # remove the binding from the space bar
                self.root.unbind("<space>")
                # go to the feedback section
                self.empty_window()
                self.display_feedback()
            # if we are at the end of the warm up phase, clear window and init critical
            elif not self.critical:
                self.word_index = 0
                print("\nWarm-Up completed. Proceeding with critical phase now.\n")
                self.empty_window()
                self.init_critical()

    # submit the judgment and continue to next item
    def save_judgment_next_item(self):
        # check that a selection was made
        if self.judgment.get() != "":

            # reaction times
            # record time of button press
            self.time_stop = time.time()

            # subtract start time from stop time to get reaction times
            if use_text_stimuli:
                self.time_reaction = self.time_stop - self.time_start - delay_judgment
            # for audio stimuli, also subtract the length of the item (because judgments are available only after the item has been played anyway)
            else:
                self.time_reaction = self.time_stop - self.time_start - self.sound.get_length()

            # set up all the info that should be written to the file (in that order)
            out_l = [[self.id_string], self.meta_entries_final, [self.items[self.item_counter][1]], [self.items[self.item_counter][2]], [self.items[self.item_counter][3]], [self.judgment.get()], [str(round(self.time_reaction, 5))]]
            # flatten list of lists
            out_l = [item for sublist in out_l for item in sublist]

            # save the data to the file
            with open(self.outfile, 'a') as file:
                file.write("\t".join([str(word) for word in out_l]))
                file.write('\n')

            # safety print to see what happens
            print(self.judgment.get() + "\t" + str(round(self.time_reaction, 5)) + "\t" + self.items[self.item_counter][0] + "\t" + str(self.item_counter + 1) + "/" + str(len(self.items)))

            # reset buttons for next item
            self.judgment.set("")

            # make sure that the next item is shown
            self.item_counter += 1

            # if there are more items to be shown, do that
            if self.item_counter < len(self.items):
                if use_text_stimuli:
                    # disable the likert scale button
                    for obj in self.likert_list:
                        obj.config(state="disabled")
                    # start the timer for reactivation
                    read_item_timer = Timer(delay_judgment, self.enable_submit)
                    read_item_timer.start()
                    # show new item
                    self.item_text.config(text=self.items[self.item_counter][0])
                # because the play button will automatically update itself to play the new item (bc of the item_counter),
                # we only need to disable the button for audio stimuli
                else:
                    self.submit.config(state="disabled")
                    for obj in self.likert_list:
                        obj.config(state="disabled")
                    # flash the play button to signal that a new item is available for listening
                    self.flash_play(0)
                # in addition to the above, in case of dynamic FC we need to update the radio buttons
                if dynamic_fc:
                    # list with the options for that item
                    current_fc_options = self.items[self.item_counter][4:]
                    # shuffle the fc options
                    random.shuffle(current_fc_options)

                    # update the display text and value of the buttons
                    for i in range(len(self.likert_list)):
                        self.likert_list[i].config(text=current_fc_options[i], value=current_fc_options[i])

                # and reset the time counter for the reaction times
                self.time_start = time.time()

            # otherwise either go to the feedback section or enter the critical stage of the exp
            else:
                if self.critical:
                    # close the results file
                    file.close()
                    self.empty_window()
                    self.display_feedback()
                elif not self.critical:
                    print("\nWarm-Up completed. Proceeding with critical phase now.\n")
                    self.empty_window()
                    self.init_critical()

        # if no selection was made using the radio buttons, display error
        else:
            self.display_error()

    # save the given feedback in a text file
    def save_feedback(self):
        # feedback file will be saved together with the results, but under a different name; all feedback texts together in a single file
        self.outfile = experiment_title + "_results/" + "FEEDBACK" + results_file_extension

        # save the feedback with id string and internal number as csv file
        if self.feedback.get() == "":
            out_l = [self.id_string, self.participant_number, "NA"]
        else:
            out_l = [self.id_string, self.participant_number, self.feedback.get()]
        with open(self.outfile, 'a') as file:
            file.write("\t".join([str(word) for word in out_l]))
            file.write('\n')
            file.close()

        # end the exp
        self.display_over()

    # allow continuation/judgment
    def enable_submit(self):
        # check if window is still open
        if not self.quit:
            # enable the buttons
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
        if messagebox.askokcancel("Quit", quit_warning):
            self.root.destroy()
            self.quit = True
            if self.critical and not self.finished:
                print("\nIMPORTANT!: Experiment was quit manually. If specified as such, the results file will now be deleted if not enough items were completed.")
                # delete results file if so specified (remove_unfinished)
                self.delete_unfinished_part()
            else:
                print("\nExperiment was quit manually. This happened before the critical section, so there is no action required.")


Exp = Experiment()
Exp.init_meta()

Exp.root.mainloop()
