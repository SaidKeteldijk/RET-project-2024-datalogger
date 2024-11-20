import tkinter
from tkinter import filedialog, messagebox, ttk
import customtkinter
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Setting appearance and theme
customtkinter.set_appearance_mode("light")
customtkinter.set_default_color_theme("dark-blue")

# Medium red color (RET Rotterdam-like red)
BUTTON_COLOR = "#D32F2F"

# Alarm counts
first_alarm_count = 0
second_alarm_count = 0

# Global variables
ampere_label = None
gauge_bar = None
first_alarm_label = None
second_alarm_label = None
csv_data = None  # Stores the loaded .csv data


# Function to show an error popup
def show_error(message):
    messagebox.showerror("Invalid Input", message)


# Function to set first alarm
def set1():
    global first_alarm_count
    try:
        value = first_input.get()
        if value < 0:
            show_error("First alarm value must be a positive number!")
        else:
            print("Alarm set to:", value)
            first_alarm_count += 1
            update_alarm_counts()
    except Exception as e:
        show_error(f"An error occurred: {e}")


# Function to set second alarm
def set2():
    global second_alarm_count
    try:
        value = second_input.get()
        if value <= first_input.get():
            show_error("Second alarm value must be greater than the first alarm value!")
        else:
            print("Alarm set to:", value)
            second_alarm_count += 1
            update_alarm_counts()
    except Exception as e:
        show_error(f"An error occurred: {e}")


# Function to simulate updating the current ampere measurement
def update_gauge():
    global gauge_bar, ampere_label
    if gauge_bar:
        if csv_data is not None:
            # Fetch a random value from the loaded data
            current_ampere = csv_data["Ampere"].mean()  # Example: Use the mean value for simplicity
            ampere_label.text = f"Current Ampere: {current_ampere:.2f} A"
            gauge_bar['value'] = min(100, current_ampere)  # Progress bar value clamped at 100
        else:
            ampere_label.text = "No Data Loaded"
            gauge_bar['value'] = 0
    app.after(1000, update_gauge)  # Update every second


# Function to update the alarm counts
def update_alarm_counts():
    global first_alarm_label, second_alarm_label
    first_alarm_label.text = f"First Alarms Triggered: {first_alarm_count}"
    second_alarm_label.text = f"Second Alarms Triggered: {second_alarm_count}"


# Function to clear the main window
def clear_main_window():
    for widget in app.winfo_children():
        widget.destroy()


# Function to open log reports page in the main window
def open_log_page():
    clear_main_window()
    label = customtkinter.CTkLabel(app, text="Log Reports", font=("Arial", 20))
    label.pack(pady=20)

    file_explorer_button = customtkinter.CTkButton(
        app, text="Open File Explorer", command=open_file_explorer, fg_color=BUTTON_COLOR
    )
    file_explorer_button.pack(pady=20)

    back_button = customtkinter.CTkButton(
        app, text="Back to Main Page", command=show_main_page, fg_color=BUTTON_COLOR
    )
    back_button.pack(pady=20)


# Function to open the file explorer and load data
def open_file_explorer():
    global csv_data
    file_path = filedialog.askopenfilename(title="Select a CSV File", filetypes=[("CSV files", "*.csv")])
    if file_path:
        try:
            # Load the CSV file
            csv_data = pd.read_csv(file_path)
            print(f"Loaded CSV Data: \n{csv_data.head()}")
            plot_graph()  # Plot the data after loading
        except Exception as e:
            show_error(f"Error loading file: {e}")


# Function to plot data from the loaded .csv
def plot_graph():
    clear_main_window()

    if csv_data is not None:
        # Create a Matplotlib figure
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.plot(csv_data.iloc[:, 0], csv_data.iloc[:, 1], marker="o", label="Ampere Data")  # Adjust column indices
        ax.set_title("Ampere Data from CSV")
        ax.set_xlabel("Time")
        ax.set_ylabel("Ampere")
        ax.legend()

        # Embed the plot in the Tkinter window
        canvas = FigureCanvasTkAgg(fig, master=app)
        canvas.draw()
        canvas.get_tk_widget().pack(pady=20)

        # Back button
        back_button = customtkinter.CTkButton(app, text="Back to Main Page", command=show_main_page, fg_color=BUTTON_COLOR)
        back_button.pack(pady=20)
    else:
        show_error("No data loaded to display.")


# Function to display the main page
def show_main_page():
    clear_main_window()

    # Configure grid rows and columns
    app.grid_rowconfigure(0, weight=1)  # Top padding
    app.grid_rowconfigure(1, weight=1)  # Navigation buttons
    app.grid_rowconfigure(2, weight=5)  # Centered content
    app.grid_rowconfigure(3, weight=2)  # Bottom content
    app.grid_columnconfigure(0, weight=1)  # Left (navigation)
    app.grid_columnconfigure(1, weight=3)  # Center (main content)
    app.grid_columnconfigure(2, weight=1)  # Right (alarm settings)

    global ampere_label, gauge_bar, first_alarm_label, second_alarm_label

    # Navigation buttons on the left
    log_button = customtkinter.CTkButton(app, text="Open Log Reports", command=open_log_page, fg_color=BUTTON_COLOR)
    log_button.grid(row=1, column=0, padx=10, pady=10, sticky="n")

    test_button = customtkinter.CTkButton(app, text="Test System", command=open_test_system, fg_color=BUTTON_COLOR)
    test_button.grid(row=2, column=0, padx=10, pady=10, sticky="n")

    # Centered content
    ampere_label = customtkinter.CTkLabel(app, text="Current Ampere: 0 A", font=("Arial", 20))
    ampere_label.grid(row=1, column=1, pady=10, sticky="n")

    gauge_bar = ttk.Progressbar(app, orient="horizontal", length=300, mode="determinate", maximum=100)
    gauge_bar.grid(row=2, column=1, pady=20, sticky="n")

    first_alarm_label = customtkinter.CTkLabel(app, text="First Alarms Triggered: 0", font=("Arial", 15))
    first_alarm_label.grid(row=2, column=1, pady=40, sticky="s")

    second_alarm_label = customtkinter.CTkLabel(app, text="Second Alarms Triggered: 0", font=("Arial", 15))
    second_alarm_label.grid(row=2, column=1, pady=80, sticky="s")

    # Alarm settings on the right inside a frame
    alarm_frame = customtkinter.CTkFrame(app)
    alarm_frame.grid(row=1, column=2, rowspan=3, padx=10, pady=10, sticky="nsew")

    text1 = customtkinter.CTkLabel(alarm_frame, text="Set First Alarm")
    text1.grid(row=0, column=0, padx=20, pady=5, sticky="w")

    input1 = customtkinter.CTkEntry(alarm_frame, width=100, height=30, textvariable=first_input)
    input1.grid(row=1, column=0, padx=20, pady=5, sticky="w")

    alarm_button1 = customtkinter.CTkButton(alarm_frame, width=60, height=30, text="SET", command=set1, fg_color=BUTTON_COLOR)
    alarm_button1.grid(row=1, column=1, padx=10, pady=5, sticky="e")

    text2 = customtkinter.CTkLabel(alarm_frame, text="Set Second Alarm")
    text2.grid(row=2, column=0, padx=20, pady=5, sticky="w")

    input2 = customtkinter.CTkEntry(alarm_frame, width=100, height=30, textvariable=second_input)
    input2.grid(row=3, column=0, padx=20, pady=5, sticky="w")

    alarm_button2 = customtkinter.CTkButton(alarm_frame, width=60, height=30, text="SET", command=set2, fg_color=BUTTON_COLOR)
    alarm_button2.grid(row=3, column=1, padx=10, pady=5, sticky="e")

    # Start updating the gauge
    update_gauge()


# Main Application Window
app = customtkinter.CTk()
app.geometry("800x480")
app.title("RET Demo Dashboard")

# Variables
first_input = tkinter.DoubleVar()
second_input = tkinter.DoubleVar()

# Show
