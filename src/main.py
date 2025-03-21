import tkinter
import customtkinter
import RPi.GPIO as GPIO
import time
##from time import sleep , strftime, time
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import pandas as pd
import matplotlib.pyplot as plt
from time import sleep
from time import strftime
import spidev
import csv
import threading
import collections
from tkinter import messagebox

customtkinter.set_appearance_mode("light")
customtkinter.set_default_color_theme("dark-blue")

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)



# pinout for version 1.0.3
Relay1 = 11 # SCADA 1 // 13  BMS 1
Relay2 = 15 # BMS 1   // 11 BM 2
Relay3 = 13 # SCADA 2 // 22 SCADA 1
Relay4 = 22 # BMS 2   // 15 SCADA 2

GPIO.setup(Relay1, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(Relay2, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(Relay3, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(Relay4, GPIO.OUT, initial=GPIO.LOW)

BMS_alarm1 = None
BMS_alarm2 = None
SCADA_alarm1 = None
SCADA_alarm2 = None

BMS1_label = None
BMS2_label = None
SCADA1_label = None
SCADA2_label = None

current = None

log_status = False
current_screen = 0

spi = spidev.SpiDev()
spi.open(0, 0)  
spi.max_speed_hz = 1350000

focused_entry = None

app = customtkinter.CTk()
app.geometry("800x480")
app.title("RET Demo Dashboard")
app.grid_columnconfigure(0, weight=1)
app.grid_columnconfigure(1, weight=1)

BMS_first_input = tkinter.DoubleVar()
BMS_second_input = tkinter.DoubleVar()
SCADA_first_input = tkinter.DoubleVar()
SCADA_second_input = tkinter.DoubleVar()

current_samples = collections.deque(maxlen=2048)  # holds last 256 samples
current_lock = threading.Lock()

calibration_offset = 0.0

def continuous_measurement_loop():
    while True:
        sample = DC_current_ADC1(samples=1)
        with current_lock:
            current_samples.append(sample)
        time.sleep(0.01)  # 100 samples per second

def continuous_measurement():
    global current_samples
    while True:
        sample = DC_current_ADC1(samples=1)  # single sample per iteration
        with current_lock:
            current_samples.append(sample)
        time.sleep(0.01)  # measure every ~4ms (~256Hz)


def on_focus(entry):
    global focused_entry
    focused_entry = entry  

def BMS_set1():
    global BMS_alarm1
    if BMS_first_input.get() < 0:
        print("ERROR: INVALID VALUE")

    elif BMS_first_input.get() >= 0:
        BMS_alarm1 = BMS_first_input.get()
        print("BMS Alarm 1 set to:", BMS_alarm1)
        

def BMS_set2():
    global BMS_alarm2
    if BMS_second_input.get() <= BMS_first_input.get():
        print("The second alarm cannot be lower than the first alarm")
         
    elif BMS_second_input.get() > BMS_first_input.get():
        BMS_alarm2 = BMS_second_input.get()
        print("BMS Alarm 2 set to:", BMS_alarm2)

def SCADA_set1():
    global SCADA_alarm1
    if SCADA_first_input.get() < 0:
        print("ERROR: INVALID VALUE")

    elif SCADA_first_input.get() >= 0:
        SCADA_alarm1 = SCADA_first_input.get()
        print("SCADA Alarm 1 set to:", SCADA_alarm1)

def SCADA_set2():
    global SCADA_alarm2
    if SCADA_second_input.get() < 0:
        print("ERROR: INVALID VALUE")

    elif SCADA_second_input.get() >= 0:
        SCADA_alarm2 = SCADA_second_input.get()
        print("SCADA Alarm 2 set to:", SCADA_alarm2)

def alarm_check1():
    global BMS_alarm1, log_status
    if BMS_alarm1 is not None:
        current_value = DC_current_ADC1()
        if current_value > BMS_alarm1 and not log_status:
            log_status = True
            threading.Thread(target=log_data, daemon=True).start()
            GPIO.output(Relay1, GPIO.HIGH)
        elif current_value <= BMS_alarm1 and log_status:
            log_status = False
            GPIO.output(Relay1, GPIO.LOW)
    app.after(300, alarm_check1)

def alarm_check2():
    global BMS_alarm2, log_status
    if BMS_alarm2 is not None:
        current_value = DC_current_ADC1()
        if current_value > BMS_alarm2 and log_status:
            log_status = False
            GPIO.output(Relay2, GPIO.HIGH)
        elif current_value <= BMS_alarm2:
            GPIO.output(Relay2, GPIO.LOW)
    app.after(300, alarm_check2)


def alarm_check3():
    global SCADA_alarm1
    if SCADA_alarm1 is not None:
        current_value = DC_current_ADC1()
        if current_value > BMS_alarm1:
            GPIO.output(Relay3, GPIO.HIGH)
        else:
            GPIO.output(Relay3, GPIO.LOW)
    app.after(300, alarm_check3)

def alarm_check4():
    global SCADA_alarm2
    if SCADA_alarm2 is not None:
        current_value = DC_current_ADC1()
        if current_value > BMS_alarm2:
            GPIO.output(Relay4, GPIO.HIGH)
        else:
            GPIO.output(Relay4, GPIO.LOW)
    app.after(300, alarm_check4)

def functional_tests():
    global current_screen
    current_screen = 1
    clear_app()

    customtkinter.CTkButton(app, width=150, height=50, text="Test BMS & SCADA relays", command=relay_test).grid(row=1, column=0, padx=20, pady=10)
    customtkinter.CTkButton(app, width=150, height=50, text="Test 4-20mA output", command=analog_test).grid(row=2, column=0, padx=20, pady=10)
    customtkinter.CTkButton(app, width=150, height=50, text="Back to Home", command=main_screen_startup).grid(row=3, column=0, padx=20, pady=10)

def relay_test():
    print("Performing system functionality test....")
    GPIO.output(Relay3, GPIO.HIGH) # SCADA 1
    time.sleep(3)
    GPIO.output(Relay3, GPIO.LOW) 
    GPIO.output(Relay1, GPIO.HIGH) # BMS 1 
    time.sleep(3)
    GPIO.output(Relay1, GPIO.LOW)
    GPIO.output(Relay4, GPIO.HIGH)# SCADA 2
    time.sleep(3)
    GPIO.output(Relay4, GPIO.LOW)
    GPIO.output(Relay2, GPIO.HIGH) # BMS 2
    time.sleep(3)
    GPIO.output(Relay2, GPIO.LOW)

def analog_test():
    print("Creating a 1Hz sinus from 4-") 


def AC_current_ADC0(): ##function for pcb version 3 & 4
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
    global current
    total = 0
    for _ in range(samples):
        adc = spi.xfer2([1, (8 + 1) << 4, 0])  
        raw_value = ((adc[1] & 3) << 8) + adc[2]  
        total += raw_value
    raw_value = total / samples  # Gemiddelde van meerdere metingen
    # print("Gemiddelde ADC kanaal 1 bit waarde:", raw_value, "en", current)


    max_adc = 1023
    min_current = 0
    max_current = 50
    average_error = 0.0036248

    raw_value = raw_value - 9

    if raw_value <= 0:
        raw_value = 0

    current = ((raw_value / max_adc) * max_current)#*(1 - average_error)
    #print("Gemid ADC 1 waarde:", raw_value, "en", current)
    return current

def update_current_display():
    # global current_label

    # if current_label:
    #     current_value = DC_current_ADC1()
    #     current_label.configure(text=f"Current: {current_value:.2f} A")

    # app.after(1000, update_current_display) 

    global current_label, current_samples

    with current_lock:
        if len(current_samples) > 0:
            current_mean = sum(current_samples) / len(current_samples)
        else:
            current_value = 0.0

    current_label.configure(text=f"Current: {current_mean:.2f} A")

    app.after(200, update_current_display)  # update label every second

def alarm_label_update():
    global BMS_alarm1
    global BMS_alarm2
    global SCADA_alarm1
    global SCADA_alarm2

    if BMS_alarm1 is not None:
        BMS1_label.configure(text=f"BMS first alarm: {BMS_alarm1:.2f} A")
    else:
        BMS1_label.configure(text="BMS first alarm: unavailable")
    
    if BMS_alarm2 is not None:
        BMS2_label.configure(text=f"BMS second alarm: {BMS_alarm2:.2f} A")
    else:
        BMS2_label.configure(text="BMS second alarm: unavailable")

    if SCADA_alarm1 is not None:
        SCADA1_label.configure(text=f"SCADA first alarm: {SCADA_alarm1:.2f} A")
    else:
        SCADA1_label.configure(text="SCADA first alarm: unavailable")

    if SCADA_alarm2 is not None:
        SCADA2_label.configure(text=f"SCADA second alarm: {SCADA_alarm2:.2f} A")
    else:
        SCADA2_label.configure(text="SCADA second alarm: unavailable")

    app.after(500, alarm_label_update)  # update every 500ms

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

def log_data():
    global current
    print("Starting data logging...")
    with open("/home/ret/Desktop/App/Log/log_report.csv", "a") as log:
        while log_status:
            log.write("{0},{1}\n".format(strftime("%Y-%m-%d %H:%M:%S"), float(current)))
            sleep(0.3)
    print("Data logging stopped.")

def clear_app():
    print("Clearing window...")
    for i in app.winfo_children():
        i.destroy()


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
        initialdir="/home/ret/Desktop/App/Log",
        title="Select a CSV File"
    )
    if file_path:
        print("Plotting data...")
        plot_log_report(file_path)


def plot_log_report(file):
    print("Plotting data...")
    try:
        
        data = pd.read_csv(file, sep=",", header=None, names=["DateTime", "Value"])
        
        
        data["DateTime"] = data["DateTime"].astype(str).str.strip()  
        data["Datetime"] = pd.to_datetime(data["DateTime"], format="%Y-%m-%d %H:%M:%S", errors='coerce')
        
        
        if data["Datetime"].isnull().any():
            print("Error: Invalid datetime format in CSV. Please check for inconsistencies.")
            print(data.loc[data["Datetime"].isnull()])  
            return
        
        
        fig, ax = plt.subplots(figsize=(8, 3.5))
        ax.plot(data["Datetime"], data["Value"], label="Log Data", color="blue", linewidth=2)
        
        
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

def calibrate_sensor():
    global calibration_offset

    print("Calibrating sensor... Ensure current is zero.")
    messagebox.showinfo("Calibration", "Calibration started. Ensure current is zero.")

    samples = 256
    total = 0
    for _ in range(samples):
        adc = spi.xfer2([1, (8 + 1) << 4, 0])  
        raw_value = ((adc[1] & 3) << 8) + adc[2]
        total += raw_value
        time.sleep(0.005)  # short delay (~5ms)

    calibration_offset = total / samples
    print(f"Calibration complete. Offset: {calibration_offset:.2f}")

    messagebox.showinfo("Calibration", f"Calibration completed!\nOffset: {calibration_offset:.2f}")



def main_screen_startup():
    global current_label
    global BMS1_label
    global BMS2_label
    global SCADA1_label
    global SCADA2_label
    global current_screen
    
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


    input1 = customtkinter.CTkEntry(app, width=100, height=30, textvariable=BMS_first_input)
    input1.grid(row=1, column=3, padx=20, pady=0)
    input1.bind("<FocusIn>", lambda e: on_focus(input1))
    
    input2 = customtkinter.CTkEntry(app, width=100, height=30, textvariable=BMS_second_input)
    input2.grid(row=3, column=3, padx=20, pady=0)
    input2.bind("<FocusIn>", lambda e: on_focus(input2))

    input3 = customtkinter.CTkEntry(app, width=100, height=30, textvariable=SCADA_first_input)
    input3.grid(row=1, column=1, padx=20, pady=0)
    input3.bind("<FocusIn>", lambda e: on_focus(input3))

    input4 = customtkinter.CTkEntry(app, width=100, height=30, textvariable=SCADA_second_input)
    input4.grid(row=3, column=1, padx=20, pady=0)
    input4.bind("<FocusIn>", lambda e: on_focus(input4))

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

    customtkinter.CTkLabel(app, text="Set First BMS alarm").grid(row=0, column=3, padx=30, pady=0)
    customtkinter.CTkLabel(app, text="Set second BMS alarm").grid(row=2, column=3, padx=30, pady=0)
    customtkinter.CTkLabel(app, text="Set First SCADA alarm").grid(row=0, column=1, padx=30, pady=0)
    customtkinter.CTkLabel(app, text="Set second SCADA alarm").grid(row=2, column=1, padx=30, pady=0)

    customtkinter.CTkButton(app, width=60, height=30, text="SET", command=BMS_set1).grid(row=1, column=5, padx=20, pady=0)
    customtkinter.CTkButton(app, width=60, height=30, text="SET", command=BMS_set2).grid(row=3, column=5, padx=20, pady=0)
    customtkinter.CTkButton(app, width=60, height=30, text="SET", command=SCADA_set1).grid(row=1, column=2, padx=20, pady=0)
    customtkinter.CTkButton(app, width=60, height=30, text="SET", command=SCADA_set2).grid(row=3, column=2, padx=20, pady=0)
    customtkinter.CTkButton(app, width=150, height=50, text="Full system test", command=functional_tests).grid(row=1, column=0, padx=20, pady=10)
    customtkinter.CTkButton(app, width=150, height=50, text="Log reports", command=log_tab).grid(row=2, column=0, padx=20, pady=10)

    customtkinter.CTkButton(app, width=150, height=50, text="Calibrate Sensor", command=calibrate_sensor).grid(row=5, column=0, padx=10, pady=10)


    update_current_display()
    alarm_label_update()


# add this before app.mainloop()
measurement_thread = threading.Thread(target=continuous_measurement_loop, daemon=True)
measurement_thread.start()


main_screen_startup()

alarm_check1()
alarm_check2()
alarm_check3()
alarm_check4()
alarm_label_update()
update_current_display()



app.mainloop()