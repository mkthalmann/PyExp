# general
fullscreen = True
allow_fullscreen_escape = False
# default main window size in pixels (width x height); only for when fullscreen escape is allowed
geometry = "1200x700"
window_title = "Experiment Name"
# experiment title (never shown to the user; single word; no non-alphanumeric characters)
# used for the results file folder and the housekeeping file
experiment_title = "TEST"
# e-mail address to send completion notification to
# separate multiple addresses via commas in the same string
confirm_completion = False
receiver_email = "maik.thalmann@gmail.com"

logo = "media/logo.png"

# meta data
meta_instruction = "Please fill out all the fields below:"
meta_fields = 'Age', 'Gender', 'Language', "Major"

# exposition
expo_text = '''Liebe/r Teilnehmer/In,\n\nim Folgenden werden wir Ihnen einige Sätze des Deutschen zeigen. Wir möchten Sie bitten, diese aufmerksam durchzulesen und im Anschluss in eine von vier verschiedenen Kategorien einzuordnen. Dabei wird es darum gehen, die im Satz präsentierte Handlung mithilfe der vier Auswahlmöglichkeiten genauer zu beschreiben.\n\n\nViel Spaß und herzlichen Dank für Ihre Teilnahme!'''

# warm up section
warm_up = False
# leave as empty string to disable
warm_up_title = "This is a familiarization phase."
# leave as empty string to disable
warm_up_description = "Please do as you're told so won't fuck up my experiment."
# uses item_file_extension: .csv; .txt; .xlsx
warm_up_file = "items/warm_up"  # warm_up_audio/warm_up

# critical section
use_text_stimuli = True
# self-paced reading instead of judgments
self_paced_reading = False
# determines whether previous words are also shown (True) or not (False) in self-paced reading tasks; inconsequential otherwise
cumulative = False
title = ""  # leave as empty string to disable
description = ""  # leave as empty string to disable
# can also be used as forced choice; mixing strings and integers is fine (though I can't think of why anybody would want this)
likert = [1, 2, 3, 4, 5, 6, 7]
endpoints = ["(horrid)", "(splendid)"]  # empty strings to disable: ["", ""]

# option to retrieve the judgment/fc options from the item file for each item separately; will overwrite whatever is specified in likert list above
# does not work with self-paced reading, but with traditional text and audio stimuli
# column names will be displayed in the results file
dynamic_fc = False
# display image options instead of text; images will be rescaled automatically
# remember to add the entire path to the file, including extension, but its possible to mix file types
dynamic_img = False
# for audio stimuli:
# if using non-direct google drive links (obtained via export settings), set this to true to convert it to a usable one
# for links obtained by highlighting multiple files, right-clicking on them and then clicking "Share"
google_drive_link = False

# disable both the submit and likert scale buttons for a number of seconds to encourage people to actually read the item (0 to disable)
# this will not feature in the reaction times of course
delay_judgment = 1

# number of participants to be tested
participants = 100

# delete results file of participants who did not complete the experiment
remove_unfinished = False
# threshold underneath of which the results file will be deleted
remove_ratio = .75

# item file
# assumes file with suffix containing the number of the list: "complete_list1.xlsx")
item_lists = 2  # with 4, you should have four lists: $list1, $list2, $list3, $list4
# complete_list; complete_audio; complete_spr; complete_dynamic; complete_image; complete_image_jpg; complete_audio_url; complete_audio_url_gd
item_file = "items/complete_dynamic"
item_file_extension = ".xlsx"  # .csv; .txt; .xlsx
items_randomize = True

# prefix for the results file
results_file = "results"
results_file_extension = ".csv"  # .csv; .txt; .xlsx

# feedback section
# leave empty to not have a feedback section at the end of the exp
feedback = "Feedback test\nWhat would you like to tell me?"

# button text
audio_button_text = "Play Item"
button_text = "Continue"

# messages and errors
finished_message = "Thank you for your interest in participating in the study. Unfortunately, all slots have already been filled."
bye_message = "THANK YOU! The experiment is finished, you can exit the window now. \nOnce again, we truly appreciate your assistance."
quit_warning = "Are you absolutely sure you want to quit the Experiment?\n\nYou will not be able to restart it again from where you left off."
error_judgment = "Make a selection, please!"
error_meta = "Fill out all fields, please!"

# font setup
font = "Roboto Condensed"
font_mono = "Source Code Pro"  # only used in self-paced-reading
basesize = 25
