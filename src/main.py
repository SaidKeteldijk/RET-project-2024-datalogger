import tkinter
import customtkinter
import RPi.GPIO as GPIO
import time
from time import sleep, strftime
import spidev
import csv
import threading
import collections
from tkinter import messagebox
import os
import re
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ------------------- SETUP & GLOBALS -------------------
customtkinter.set_appearance_mode("light")
customtkinter.set_default_color_theme("dark-blue")

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)

# Relay pins
Relay1 = 11
Relay2 = 15
Relay3 = 13
Relay4 = 22

GPIO.setup(Relay1, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(Relay2, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(Relay3, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(Relay4, GPIO.OUT, initial=GPIO.LOW)

# Alarms (user‐set from the GUI)
alarm_current = None
BMS_alarm1 = None
BMS_alarm2 = None
SCADA_alarm1 = None
SCADA_alarm2 = None

# For labels
BMS1_label = None
BMS2_label = None
SCADA1_label = None
SCADA2_label = None
current_label = None

# We store many samples to compute a stable average
current_samples = collections.deque(maxlen=256)
current_lock = threading.Lock()

# For ADC
current = None
calibration_offset = 0.0
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1350000

# For GUI
app = customtkinter.CTk()
app.geometry("800x480")
app.title("RET Demo Dashboard")
app.grid_columnconfigure(0, weight=1)
app.grid_columnconfigure(1, weight=1)
focused_entry = None

# Numeric input variables
BMS_first_input = tkinter.DoubleVar()
BMS_second_input = tkinter.DoubleVar()
SCADA_first_input = tkinter.DoubleVar()
SCADA_second_input = tkinter.DoubleVar()

# Which screen the user is on (main or functional tests)
current_screen = 0

# ------------------- NEW LOGGING STATE MACHINE -------------------
LOG_FOLDER = "/home/ret/Desktop/App/Log"

# States of the logging machine:
#  - BELOW_ALARM1
#  - BETWEEN_ALARMS
#  - ABOVE_ALARM2
current_state = "BELOW_ALARM1"

# Logging flags & file handle
logging_active = False
logfile_handle = None

# File index so we name new files as log_file_0001.csv, log_file_0002.csv, etc.
log_file_index = 0

def find_next_log_index(log_dir=LOG_FOLDER):
    """
    Look for existing log_file_####.csv files, find the highest number,
    and return one higher so we don't overwrite old logs.
    """
    highest = 0
    pattern = re.compile(r"^log_file_(\d{4})\.csv$")
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir)  # Create the directory if needed
    for filename in os.listdir(log_dir):
        match = pattern.match(filename)
        if match:
            idx = int(match.group(1))
            if idx > highest:
                highest = idx
    return highest + 1

def get_next_log_filename():
    """
    Returns something like "/home/ret/Desktop/App/Log/log_file_0001.csv"
    and increments log_file_index for next time.
    """
    global log_file_index
    filename = f"log_file_{log_file_index:04d}.csv"
    full_path = os.path.join(LOG_FOLDER, filename)
    log_file_index += 1
    return full_path

def start_logging():
    """Opens a new CSV file and sets logging_active = True."""
    global logging_active, logfile_handle
    if logging_active:
        return  # already logging
    new_csv = get_next_log_filename()
    print(f"[LOG] Starting new CSV file: {new_csv}")
    logfile_handle = open(new_csv, "w", buffering=1)  # line‐buffered
    # Optionally write header
    logfile_handle.write("Timestamp,Current\n")
    logging_active = True

def stop_logging():
    """Stops logging and closes the CSV file."""
    global logging_active, logfile_handle
    if logging_active and logfile_handle is not None:
        print("[LOG] Stopping logging and saving file.")
        logfile_handle.close()
        logfile_handle = None
    logging_active = False

def check_and_log(current_val):
    """
    Main state machine for logging between BMS_alarm1 and BMS_alarm2.
    If the user hasn't set them yet (None), do nothing.
    """
    global current_state

    # We only proceed if BMS_alarm1 and BMS_alarm2 are defined
    if BMS_alarm1 is None or BMS_alarm2 is None:
        return

    # Let's define local A1 and A2 in case user sets them in reverse
    A1 = min(BMS_alarm1, BMS_alarm2)
    A2 = max(BMS_alarm1, BMS_alarm2)

    # --- State transitions ---
    if current_state == "BELOW_ALARM1":
        # If we rise above A1 but still below A2, we begin logging
        if current_val >= A1 and current_val < A2:
            current_state = "BETWEEN_ALARMS"
            start_logging()

    elif current_state == "BETWEEN_ALARMS":
        # If we exceed A2, stop logging and go to ABOVE_ALARM2
        if current_val >= A2:
            current_state = "ABOVE_ALARM2"
            stop_logging()
        # If we drop below A1, also stop logging
        elif current_val < A1:
            current_state = "BELOW_ALARM1"
            stop_logging()

    elif current_state == "ABOVE_ALARM2":
        # If we drop back below A2 but stay above A1,
        # we start a new log file again
        if current_val < A2 and current_val >= A1:
            current_state = "BETWEEN_ALARMS"
            start_logging()
        # If we drop below A1, no logging
        elif current_val < A1:
            current_state = "BELOW_ALARM1"
            stop_logging()

    # If currently logging, write the data
    if logging_active and logfile_handle:
        timestamp = strftime("%Y-%m-%d %H:%M:%S")
        logfile_handle.write(f"{timestamp},{current_val:.3f}\n")
        # logfile_handle.flush()  # uncomment if you want immediate disk writes

# ------------------- ALARM / RELAY CHECKS -------------------
def alarm_check1():
    """Check BMS_alarm1 condition to toggle Relay1, etc."""
    global BMS_alarm1, alarm_current
    if BMS_alarm1 is not None:
        if alarm_current > BMS_alarm1:
            GPIO.output(Relay1, GPIO.HIGH)
        else:
            GPIO.output(Relay1, GPIO.LOW)
    app.after(300, alarm_check1)

def alarm_check2():
    """Check BMS_alarm2 condition to toggle Relay2, etc."""
    global BMS_alarm2, alarm_current
    if BMS_alarm2 is not None:
        if alarm_current > BMS_alarm2:
            GPIO.output(Relay2, GPIO.HIGH)
        else:
            GPIO.output(Relay2, GPIO.LOW)
    app.after(300, alarm_check2)

def alarm_check3():
    """Check SCADA_alarm1 condition to toggle Relay3, etc."""
    global SCADA_alarm1, alarm_current
    if SCADA_alarm1 is not None:
        if alarm_current > SCADA_alarm1:
            GPIO.output(Relay3, GPIO.HIGH)
        else:
            GPIO.output(Relay3, GPIO.LOW)
    app.after(300, alarm_check3)

def alarm_check4():
    """Check SCADA_alarm2 condition to toggle Relay4, etc."""
    global SCADA_alarm2, alarm_current
    if SCADA_alarm2 is not None:
        if alarm_current > SCADA_alarm2:
            GPIO.output(Relay4, GPIO.HIGH)
        else:
            GPIO.output(Relay4, GPIO.LOW)
    app.after(300, alarm_check4)

# ------------------- SET ALARM CALLBACKS -------------------
def BMS_set1():
    global BMS_alarm1
    if BMS_first_input.get() < 0:
        print("ERROR: INVALID VALUE")
    else:
        BMS_alarm1 = BMS_first_input.get()
        print("BMS Alarm 1 set to:", BMS_alarm1)

def BMS_set2():
    global BMS_alarm2
    if BMS_second_input.get() <= BMS_first_input.get():
        print("The second alarm cannot be lower than the first alarm")
    else:
        BMS_alarm2 = BMS_second_input.get()
        print("BMS Alarm 2 set to:", BMS_alarm2)

def SCADA_set1():
    global SCADA_alarm1
    if SCADA_first_input.get() < 0:
        print("ERROR: INVALID VALUE")
    else:
        SCADA_alarm1 = SCADA_first_input.get()
        print("SCADA Alarm 1 set to:", SCADA_alarm1)

def SCADA_set2():
    global SCADA_alarm2
    if SCADA_second_input.get() < 0:
        print("ERROR: INVALID VALUE")
    else:
        SCADA_alarm2 = SCADA_second_input.get()
        print("SCADA Alarm 2 set to:", SCADA_alarm2)

# ------------------- TESTS & RELAYS -------------------
def functional_tests():
    global current_screen
    current_screen = 1
    clear_app()

    customtkinter.CTkButton(app, width=150, height=50, text="Test BMS & SCADA relays", command=relay_test).grid(row=1, column=0, padx=20, pady=10)
    customtkinter.CTkButton(app, width=150, height=50, text="Test 4-20mA output", command=analog_test).grid(row=2, column=0, padx=20, pady=10)
    customtkinter.CTkButton(app, width=150, height=50, text="Back to Home", command=main_screen_startup).grid(row=3, column=0, padx=20, pady=10)

def relay_test():
    print("Performing system functionality test....")
    GPIO.output(Relay3, GPIO.HIGH)  # SCADA 1
    time.sleep(3)
    GPIO.output(Relay3, GPIO.LOW)
    GPIO.output(Relay1, GPIO.HIGH)  # BMS 1
    time.sleep(3)
    GPIO.output(Relay1, GPIO.LOW)
    GPIO.output(Relay4, GPIO.HIGH)  # SCADA 2
    time.sleep(3)
    GPIO.output(Relay4, GPIO.LOW)
    GPIO.output(Relay2, GPIO.HIGH)  # BMS 2
    time.sleep(3)
    GPIO.output(Relay2, GPIO.LOW)

def analog_test():
    print("Creating a 1Hz sinus from 4-20mA (Not yet implemented)") 

# ------------------- ADC FUNCTIONS -------------------
def AC_current_ADC0():
    """Example function for AC measurement (not fully used here)."""
    global current
    adc = spi.xfer2([1, (8 + 0) << 4, 0])
    raw_value = ((adc[1] & 3) << 8) + adc[2]
    print("the bit value is:", raw_value)
    min_adc = 210
    max_adc = 1023
    max_current = 100
    true_zerro = 201.2
    if raw_value > min_adc:
        normalized_value = (raw_value - true_zerro) / (max_adc - true_zerro)
        current = normalized_value * max_current
    else:
        current = 0
    return current

def DC_current_ADC1(samples=5):
    """
    Measure from channel 1 of the MCP3008, average multiple samples,
    apply calibration offset, convert to current.
    """
    global current, calibration_offset
    total = 0
    for _ in range(samples):
        adc = spi.xfer2([1, (8 + 1) << 4, 0])
        raw_value = ((adc[1] & 3) << 8) + adc[2]
        total += raw_value
    raw_value = total / samples
    print("Gemiddelde ADC kanaal 1 bit waarde:", raw_value, "en", current)

    max_adc = 1023
    max_current = 50
    raw_value = raw_value - calibration_offset

    if raw_value <= 0:
        raw_value = 0

    current = (raw_value / max_adc) * max_current
    return current

def continuous_measurement_loop():
    """Thread that continuously updates current_samples for a stable average."""
    while True:
        sample = DC_current_ADC1(samples=1)
        with current_lock:
            current_samples.append(sample)
        time.sleep(0.01)  # ~100 samples/sec

# ------------------- GUI UPDATES -------------------
def update_current_display():
    """
    Periodically called to:
      1. Compute the average current from current_samples.
      2. Update the label on the GUI.
      3. Run check_and_log() to handle logging logic.
    """
    global current_label, current_samples, alarm_current

    with current_lock:
        if len(current_samples) > 0:
            current_mean = sum(current_samples) / len(current_samples)
            alarm_current = current_mean
        else:
            current_mean = 0.0
            alarm_current = 0.0

    # Update the label
    current_label.configure(text=f"Current: {current_mean:.2f} A")

    # IMPORTANT: call our new logging state machine
    check_and_log(alarm_current)

    # Schedule the next update
    app.after(200, update_current_display)

def alarm_label_update():
    """Periodically update the alarm labels."""
    global BMS_alarm1, BMS_alarm2, SCADA_alarm1, SCADA_alarm2

    if BMS_alarm1 is not None:
        BMS1_label.configure(text=f"BMS first alarm: {BMS_alarm1:.2f} A")
    else:
        BMS1_label.configure(text="BMS first alarm: None")

    if BMS_alarm2 is not None:
        BMS2_label.configure(text=f"BMS second alarm: {BMS_alarm2:.2f} A")
    else:
        BMS2_label.configure(text="BMS second alarm: None")

    if SCADA_alarm1 is not None:
        SCADA1_label.configure(text=f"SCADA first alarm: {SCADA_alarm1:.2f} A")
    else:
        SCADA1_label.configure(text="SCADA first alarm: None")

    if SCADA_alarm2 is not None:
        SCADA2_label.configure(text=f"SCADA second alarm: {SCADA_alarm2:.2f} A")
    else:
        SCADA2_label.configure(text="SCADA second alarm: None")

    app.after(500, alarm_label_update)

def clear_app():
    """Clear all widgets from the window."""
    print("Clearing window...")
    for i in app.winfo_children():
        i.destroy()

# ------------------- LOG PLOTTING -------------------
def log_tab():
    global current_screen
    clear_app()
    current_screen = 1
    customtkinter.CTkButton(app, width=150, height=50, text="Back to home", command=main_screen_startup).grid(row=0, column=0, padx=20, pady=0)
    customtkinter.CTkButton(app, width=150, height=50, text="Log reports", command=open_report).grid(row=0, column=1, padx=20, pady=0)

def open_report():
    print("searching for log data....")
    file_path = tkinter.filedialog.askopenfilename(
        filetypes=[("CSV Files", "*.csv")],
        initialdir=LOG_FOLDER,
        title="Select a CSV File"
    )
    if file_path:
        print("Plotting data...")
        plot_log_report(file_path)

def plot_log_report(file):
    print("Plotting data...")
    try:
        data = pd.read_csv(file, sep=",", header=0)  # because we wrote a header now: 'Timestamp,Current'
        # If you didn't write a header, then use header=None, names=["Timestamp", "Value"]

        # Convert time
        data["Datetime"] = pd.to_datetime(data["Timestamp"], format="%Y-%m-%d %H:%M:%S", errors='coerce')
        if data["Datetime"].isnull().any():
            print("Error: Invalid datetime format in CSV. Please check for inconsistencies.")
            print(data.loc[data["Datetime"].isnull()])
            return

        fig, ax = plt.subplots(figsize=(8, 3.5))
        ax.plot(data["Datetime"], data["Current"], label="Log Data", linewidth=2)
        ax.set_xlabel("Datetime", fontsize=10)
        ax.set_ylabel("Value (Amps)", fontsize=12)
        ax.set_title("Log Data Visualization", fontsize=16)
        ax.tick_params(axis='x', labelrotation=45)
        ax.legend(fontsize=10)
        plt.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=app)
        canvas.draw()
        canvas.get_tk_widget().grid(row=1, column=0, columnspan=6, pady=20)

    except Exception as e:
        print(f"Error reading or plotting CSV file: {e}")

# ------------------- CALIBRATION -------------------
def calibrate_sensor():
    global calibration_offset
    print("Calibrating sensor... Ensure current is zero.")
    messagebox.showinfo("Calibration", "Calibration started. Ensure current is zero.")

    samples = 512
    total = 0
    for _ in range(samples):
        adc = spi.xfer2([1, (8 + 1) << 4, 0])
        raw_value = ((adc[1] & 3) << 8) + adc[2]
        total += raw_value
        time.sleep(0.005)

    calibration_offset = total / samples
    print(f"Calibration complete. Offset: {calibration_offset:.2f}")
    messagebox.showinfo("Calibration", f"Calibration completed!\nOffset: {calibration_offset:.2f}")

# ------------------- NUMPAD -------------------
def append_to_input(value):
    if focused_entry:
        current_text = focused_entry.get()
        focused_entry.delete(0, tkinter.END)
        focused_entry.insert(0, current_text + value)

def backspace_input():
    if focused_entry:
        current_text = focused_entry.get()
        focused_entry.delete(0, tkinter.END)
        focused_entry.insert(0, current_text[:-1])

def on_focus(entry):
    """Remember which entry is currently selected for the numpad."""
    global focused_entry
    focused_entry = entry

# ------------------- MAIN SCREEN -------------------
def main_screen_startup():
    global current_label, BMS1_label, BMS2_label, SCADA1_label, SCADA2_label, current_screen
    if current_screen == 1:
        clear_app()

    current_label = customtkinter.CTkLabel(app, text="Current: 0.00 A", font=("Arial", 24))
    current_label.grid(row=5, column=3, columnspan=3, pady=20)

    BMS1_label = customtkinter.CTkLabel(app, text="BMS first alarm: 0.00 A", font=("Arial", 12))
    BMS1_label.grid(row=6, column=0, columnspan=1, pady=5)

    BMS2_label = customtkinter.CTkLabel(app, text="BMS second alarm: 0.00 A", font=("Arial", 12))
    BMS2_label.grid(row=7, column=0, columnspan=1, pady=5)

    SCADA1_label = customtkinter.CTkLabel(app, text="SCADA first alarm: 0.00 A", font=("Arial", 12))
    SCADA1_label.grid(row=8, column=0, columnspan=1, pady=5)

    SCADA2_label = customtkinter.CTkLabel(app, text="SCADA second alarm: 0.00 A", font=("Arial", 12))
    SCADA2_label.grid(row=9, column=0, columnspan=1, pady=5)

    # Entries for BMS & SCADA
    input3 = customtkinter.CTkEntry(app, width=100, height=30, textvariable=SCADA_first_input)
    input3.grid(row=1, column=1, padx=20, pady=0)
    input3.bind("<FocusIn>", lambda e: on_focus(input3))

    input4 = customtkinter.CTkEntry(app, width=100, height=30, textvariable=SCADA_second_input)
    input4.grid(row=3, column=1, padx=20, pady=0)
    input4.bind("<FocusIn>", lambda e: on_focus(input4))

    input1 = customtkinter.CTkEntry(app, width=100, height=30, textvariable=BMS_first_input)
    input1.grid(row=1, column=3, padx=20, pady=0)
    input1.bind("<FocusIn>", lambda e: on_focus(input1))

    input2 = customtkinter.CTkEntry(app, width=100, height=30, textvariable=BMS_second_input)
    input2.grid(row=3, column=3, padx=20, pady=0)
    input2.bind("<FocusIn>", lambda e: on_focus(input2))

    numpad_frame = customtkinter.CTkFrame(app, width=200, height=200)
    numpad_frame.place(relx=1.0, rely=1.0, anchor="se")

    buttons = [
        ('1', 0, 0), ('2', 0, 1), ('3', 0, 2),
        ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
        ('7', 2, 0), ('8', 2, 1), ('9', 2, 2),
        ('.', 3, 0), ('0', 3, 1), ('⌫', 3, 2)
    ]

    for (text, row, col) in buttons:
        if text == '⌫':
            btn = customtkinter.CTkButton(numpad_frame, text=text, command=backspace_input)
        else:
            btn = customtkinter.CTkButton(numpad_frame, text=text, command=lambda t=text: append_to_input(t))
        btn.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

    numpad_frame.grid_rowconfigure((0, 1, 2, 3), weight=1)
    numpad_frame.grid_columnconfigure((0, 1, 2), weight=1)

    customtkinter.CTkLabel(app, text="Set First SCADA alarm").grid(row=0, column=1, padx=30, pady=0)
    customtkinter.CTkLabel(app, text="Set second SCADA alarm").grid(row=2, column=1, padx=30, pady=0)
    customtkinter.CTkLabel(app, text="Set First BMS alarm").grid(row=0, column=3, padx=30, pady=0)
    customtkinter.CTkLabel(app, text="Set second BMS alarm").grid(row=2, column=3, padx=30, pady=0)

    customtkinter.CTkButton(app, width=60, height=30, text="SET", command=SCADA_set1).grid(row=1, column=2, padx=20, pady=0)
    customtkinter.CTkButton(app, width=60, height=30, text="SET", command=SCADA_set2).grid(row=3, column=2, padx=20, pady=0)
    customtkinter.CTkButton(app, width=60, height=30, text="SET", command=BMS_set1).grid(row=1, column=5, padx=20, pady=0)
    customtkinter.CTkButton(app, width=60, height=30, text="SET", command=BMS_set2).grid(row=3, column=5, padx=20, pady=0)

    customtkinter.CTkButton(app, width=150, height=50, text="Full system test", command=functional_tests).grid(row=1, column=0, padx=20, pady=10)
    customtkinter.CTkButton(app, width=150, height=50, text="Log reports", command=log_tab).grid(row=2, column=0, padx=20, pady=10)
    customtkinter.CTkButton(app, width=150, height=50, text="Calibrate Sensor", command=calibrate_sensor).grid(row=5, column=0, padx=10, pady=10)

    update_current_display()
    alarm_label_update()

# ------------------- START MEASUREMENT THREAD -------------------
def on_close():
    """Clean up on app close."""
    stop_logging()  # ensure file is closed if we're logging
    app.destroy()
    
measurement_thread = threading.Thread(target=continuous_measurement_loop, daemon=True)
measurement_thread.start()

log_file_index = find_next_log_index()  # Start numbering from the next available file
main_screen_startup()

# Start checking alarms for relay toggles
alarm_check1()
alarm_check2()
alarm_check3()
alarm_check4()

# Overwrite app's close handler to run on_close()
app.protocol("WM_DELETE_WINDOW", on_close)
app.mainloop()
