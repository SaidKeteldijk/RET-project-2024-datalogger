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
import json
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import math  # voor de sinus in analog_test

# ------------------- SETUP & GLOBALS -------------------
# We gebruiken BCM-mode zodat we 1-op-1 met GPIO-nummers kunnen werken!
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

customtkinter.set_appearance_mode("light")
customtkinter.set_default_color_theme("dark-blue")

# Relay pins (BCM)
Relay1 = 17  # bijv. fysiek pin 11
Relay2 = 22  # fysiek pin 15
Relay3 = 27  # fysiek pin 13
Relay4 = 25  # fysiek pin 22

GPIO.setup(Relay1, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(Relay2, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(Relay3, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(Relay4, GPIO.OUT, initial=GPIO.LOW)

# Alarms (user-set vanuit de GUI)
alarm_current = None
BMS_alarm1 = None
BMS_alarm2 = None
SCADA_alarm1 = None
SCADA_alarm2 = None

# Voor labels
BMS1_label = None
BMS2_label = None
SCADA1_label = None
SCADA2_label = None
current_label = None

# We bewaren veel samples om een stabiel gemiddelde te maken
current_samples = collections.deque(maxlen=256)
current_lock = threading.Lock()

# ------------------- SPI - MCP3008 (ADC) -------------------
# We maken één spidev-object voor de MCP3008 (hardware CS0 = GPIO8).
adc_spi = spidev.SpiDev()
adc_spi.open(0, 0)       # bus=0, device=0 (CE0)
adc_spi.max_speed_hz = 1350000
adc_spi.mode = 0  # MCP3008 werkt meestal in SPI mode 0

# ------------------- SPI - DAC8551 via software CS -------------------
# We hergebruiken dezelfde MOSI/SCLK-lijnen, maar togglen zelf GPIO7 als CS.
DAC_CS = 7     # fysiek pin 26, in BCM numbering
GPIO.setup(DAC_CS, GPIO.OUT, initial=GPIO.HIGH)

# Om ook voor de DAC te schrijven, gebruiken we OOK spidev, maar het mag
# in principe dezelfde bus (bus=0) zijn. Je kunt daarvoor hetzélfde spidev-object
# hergebruiken of een tweede. Hier doen we voor de DAC gewoon "adc_spi" hergebruiken
# en manuelt CS laag/hoog toggelen. Let wel op mode en speed:
adc_spi.mode = 1  # DAC8551 vraagt vaak mode 1 of 2
adc_spi.max_speed_hz = 1_000_000

# Voor GUI
app = customtkinter.CTk()
app.geometry("800x480")
app.title("RET Demo Dashboard")
app.grid_columnconfigure(0, weight=1)
app.grid_columnconfigure(1, weight=1)
focused_entry = None

# Numeric input variabelen
BMS_first_input = tkinter.DoubleVar()
BMS_second_input = tkinter.DoubleVar()
SCADA_first_input = tkinter.DoubleVar()
SCADA_second_input = tkinter.DoubleVar()

# Huidig scherm (main of functional tests)
current_screen = 0

# ------------------- BESTANDSLOCATIES -------------------
LOG_FOLDER = "/home/ret/Desktop/App/Log"
SETTINGS_FILE = "/home/ret/Desktop/App/settings.json"

# ------------------- LOGGING -------------------
# Hysteresis om te voorkomen dat het loggen steeds start/stop bij kleine schommelingen
LOG_HYSTERESIS = 0.5

logging_active = False  # True/False of we op dit moment aan het loggen zijn
logfile_handle = None

# File index zodat we nieuwe bestanden maken log_file_0001.csv, log_file_0002.csv, etc.
log_file_index = 0

def find_next_log_index(log_dir=LOG_FOLDER):
    highest = 0
    pattern = re.compile(r"^log_file_(\d{4})\.csv$")
    if not os.path.isdir(log_dir):
        os.makedirs(log_dir)
    for filename in os.listdir(log_dir):
        match = pattern.match(filename)
        if match:
            idx = int(match.group(1))
            if idx > highest:
                highest = idx
    return highest + 1

def get_next_log_filename():
    global log_file_index
    filename = f"log_file_{log_file_index:04d}.csv"
    full_path = os.path.join(LOG_FOLDER, filename)
    log_file_index += 1
    return full_path

def start_logging():
    global logging_active, logfile_handle
    if logging_active:
        return
    new_csv = get_next_log_filename()
    print(f"[LOG] Starting new CSV file: {new_csv}")
    logfile_handle = open(new_csv, "w", buffering=1)
    logfile_handle.write("Timestamp,Current\n")
    logging_active = True

def stop_logging():
    global logging_active, logfile_handle
    if logging_active and logfile_handle is not None:
        print("[LOG] Stopping logging and saving file.")
        logfile_handle.close()
        logfile_handle = None
    logging_active = False

def check_and_log(current_val):
    global logging_active, logfile_handle, BMS_alarm1

    if BMS_alarm1 is None:
        return

    start_threshold = BMS_alarm1
    stop_threshold = BMS_alarm1 - LOG_HYSTERESIS
    if stop_threshold < 0:
        stop_threshold = 0

    if (not logging_active) and (current_val >= start_threshold):
        start_logging()
    elif logging_active and (current_val <= stop_threshold):
        stop_logging()

    if logging_active and logfile_handle:
        timestamp = strftime("%Y-%m-%d %H:%M:%S")
        logfile_handle.write(f"{timestamp},{current_val:.3f}\n")

# ------------------- OPSLAAN / LADEN VAN ALARM INSTELLINGEN -------------------
calibration_offset = 0.0

def load_settings():
    global BMS_alarm1, BMS_alarm2, SCADA_alarm1, SCADA_alarm2, calibration_offset

    if not os.path.isfile(SETTINGS_FILE):
        print(f"[SETTINGS] Geen {SETTINGS_FILE} gevonden, gebruik default waardes.")
        return

    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
        BMS_alarm1 = data.get("BMS_alarm1", None)
        BMS_alarm2 = data.get("BMS_alarm2", None)
        SCADA_alarm1 = data.get("SCADA_alarm1", None)
        SCADA_alarm2 = data.get("SCADA_alarm2", None)
        calibration_offset = data.get("calibration_offset", 0.0)

        print("[SETTINGS] Settings geladen uit:", SETTINGS_FILE)
        print("BMS_alarm1=", BMS_alarm1)
        print("BMS_alarm2=", BMS_alarm2)
        print("SCADA_alarm1=", SCADA_alarm1)
        print("SCADA_alarm2=", SCADA_alarm2)
        print("calibration_offset=", calibration_offset)

    except Exception as e:
        print(f"[SETTINGS] Fout bij inlezen van {SETTINGS_FILE}:", e)

def save_settings():
    data = {
        "BMS_alarm1": BMS_alarm1,
        "BMS_alarm2": BMS_alarm2,
        "SCADA_alarm1": SCADA_alarm1,
        "SCADA_alarm2": SCADA_alarm2,
        "calibration_offset": calibration_offset,
    }
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print("[SETTINGS] Settings opgeslagen in:", SETTINGS_FILE)
    except Exception as e:
        print(f"[SETTINGS] Fout bij opslaan in {SETTINGS_FILE}:", e)

# ------------------- ALARM / RELAY CHECKS -------------------
def alarm_check1():
    global BMS_alarm1, alarm_current
    if BMS_alarm1 is not None:
        if alarm_current > BMS_alarm1:
            GPIO.output(Relay1, GPIO.HIGH)
        else:
            GPIO.output(Relay1, GPIO.LOW)
    app.after(300, alarm_check1)

def alarm_check2():
    global BMS_alarm2, alarm_current
    if BMS_alarm2 is not None:
        if alarm_current > BMS_alarm2:
            GPIO.output(Relay2, GPIO.HIGH)
        else:
            GPIO.output(Relay2, GPIO.LOW)
    app.after(300, alarm_check2)

def alarm_check3():
    global SCADA_alarm1, alarm_current
    if SCADA_alarm1 is not None:
        if alarm_current > SCADA_alarm1:
            GPIO.output(Relay3, GPIO.HIGH)
        else:
            GPIO.output(Relay3, GPIO.LOW)
    app.after(300, alarm_check3)

def alarm_check4():
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
    val = BMS_first_input.get()
    if val <= 0:
        BMS_alarm1 = None
        messagebox.showinfo("Alarm setting", "BMS Alarm 1 is now deactivated (None).")
    else:
        BMS_alarm1 = val
        messagebox.showinfo("Alarm setting", f"BMS Alarm 1 set to: {val:.2f}")
    save_settings()

def BMS_set2():
    global BMS_alarm2, BMS_alarm1
    val = BMS_second_input.get()
    if val <= 0:
        BMS_alarm2 = None
        messagebox.showinfo("Alarm setting", "BMS Alarm 2 is now deactivated (None).")
    else:
        if BMS_alarm1 is not None and val <= BMS_alarm1:
            messagebox.showwarning(
                "Invalid Alarm Setting",
                "The second BMS alarm cannot be lower or equal to the first BMS alarm."
            )
            return
        BMS_alarm2 = val
        messagebox.showinfo("Alarm setting", f"BMS Alarm 2 set to: {val:.2f}")
    save_settings()

def SCADA_set1():
    global SCADA_alarm1
    val = SCADA_first_input.get()
    if val <= 0:
        SCADA_alarm1 = None
        messagebox.showinfo("Alarm setting", "SCADA Alarm 1 is now deactivated (None).")
    else:
        SCADA_alarm1 = val
        messagebox.showinfo("Alarm setting", f"SCADA Alarm 1 set to: {val:.2f}")
    save_settings()

def SCADA_set2():
    global SCADA_alarm2, SCADA_alarm1
    val = SCADA_second_input.get()
    if val <= 0:
        SCADA_alarm2 = None
        messagebox.showinfo("Alarm setting", "SCADA Alarm 2 is now deactivated (None).")
    else:
        if SCADA_alarm1 is not None and val <= SCADA_alarm1:
            messagebox.showwarning(
                "Invalid Alarm Setting",
                "The second SCADA alarm cannot be lower or equal than the first SCADA alarm."
            )
            return
        SCADA_alarm2 = val
        messagebox.showinfo("Alarm setting", f"SCADA Alarm 2 set to: {val:.2f}")
    save_settings()

# ------------------- DAC (DAC8551) SCHRIJFFUNCTIE -------------------
def write_dac8551(dac_value):
    """
    Schrijf 16 bits naar de DAC8551 (0..65535).
    Totale frame is 24 bits: [ control byte=0x00, high_byte, low_byte ].
    """
    if dac_value < 0:
        dac_value = 0
    elif dac_value > 0xFFFF:
        dac_value = 0xFFFF

    high_byte = (dac_value >> 8) & 0xFF
    low_byte  = dac_value & 0xFF

    # SYNC (DAC_CS) laag
    GPIO.output(DAC_CS, GPIO.LOW)
    # Verstuur 3 bytes: control=0, high, low
    adc_spi.xfer2([0x00, high_byte, low_byte])
    # SYNC weer hoog
    GPIO.output(DAC_CS, GPIO.HIGH)

def analog_test():
    """
    Genereert een 0-5V sinusgolf met 1Hz (5 cycli) via de DAC8551.
    """
    print("Generating a 1Hz 0–5V sine wave on DAC8551...")

    sample_rate = 100
    freq = 1.0
    period = 1.0 / freq
    cycles_to_play = 5
    total_samples = int(sample_rate * cycles_to_play)

    for n in range(total_samples):
        t = (n % sample_rate) / float(sample_rate)  # 0..1 fractie
        # sinus(2πt) is -1..1 -> scale naar 0..5 V
        voltage = 2.5 * (1.0 + math.sin(2 * math.pi * t))
        dac_value = int((voltage / 5.0) * 65535)

        write_dac8551(dac_value)

        time.sleep(period / sample_rate)
    write_dac8551(0)
    print("Done sending 5 cycles of a 1Hz sine wave.")

# ------------------- TESTS & RELAYS -------------------
def functional_tests():
    global current_screen
    current_screen = 1
    clear_app()

    customtkinter.CTkButton(app, width=150, height=50, text="Test BMS & SCADA relays", command=relay_test).grid(row=1, column=0, padx=20, pady=10)
    customtkinter.CTkButton(app, width=150, height=50, text="Test 0-5V 1Hz Sinus", command=analog_test).grid(row=2, column=0, padx=20, pady=10)
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

# ------------------- ADC FUNCTIES (MCP3008) -------------------
def DC_current_ADC1(samples=5):
    """
    Meet van kanaal 1 van de MCP3008, gemiddelde over meerdere samples,
    pas calibration_offset toe en converteer naar A.
    """
    global current, calibration_offset
    total = 0
    for _ in range(samples):
        adc = adc_spi.xfer2([1, (8 + 1) << 4, 0])  # channel=1
        raw_value = ((adc[1] & 3) << 8) + adc[2]
        total += raw_value
    raw_avg = total / samples

    max_adc = 1023
    max_current = 50
    # Trek de offset eraf
    raw_avg -= calibration_offset
    if raw_avg < 0:
        raw_avg = 0

    current = (raw_avg / max_adc) * max_current
    return current

def continuous_measurement_loop():
    while True:
        sample = DC_current_ADC1(samples=1)
        with current_lock:
            current_samples.append(sample)
        time.sleep(0.01)  # ~100 samples/sec

# ------------------- GUI UPDATES -------------------
def update_current_display():
    global current_label, current_samples, alarm_current
    with current_lock:
        if len(current_samples) > 0:
            current_mean = sum(current_samples) / len(current_samples)
            alarm_current = current_mean
        else:
            current_mean = 0.0
            alarm_current = 0.0

    current_label.configure(text=f"Current: {current_mean:.2f} A")
    check_and_log(alarm_current)
    app.after(200, update_current_display)

def alarm_label_update():
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
        data = pd.read_csv(file, sep=",", header=0)
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
        adc = adc_spi.xfer2([1, (8 + 1) << 4, 0])  # channel=1
        raw_value = ((adc[1] & 3) << 8) + adc[2]
        total += raw_value
        time.sleep(0.005)

    calibration_offset = total / samples
    print(f"Calibration complete. Offset: {calibration_offset:.2f}")
    messagebox.showinfo("Calibration", f"Calibration completed!\nOffset: {calibration_offset:.2f}")

    save_settings()

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
    stop_logging()  # Sluit log-bestand als we nog aan het loggen zijn
    app.destroy()

measurement_thread = threading.Thread(target=continuous_measurement_loop, daemon=True)
measurement_thread.start()

log_file_index = find_next_log_index()

load_settings()
main_screen_startup()

alarm_check1()
alarm_check2()
alarm_check3()
alarm_check4()

app.protocol("WM_DELETE_WINDOW", on_close)
app.mainloop()
