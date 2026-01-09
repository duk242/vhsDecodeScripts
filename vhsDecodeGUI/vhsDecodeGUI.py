import customtkinter as ctk
from tkinter import filedialog, END
import subprocess
import threading
import time
import re
import os
import glob
import signal

# --- Configuration Constants ---
# Assuming 25 frames per second (PAL standard, common for VHS)
FPS = 25.0
# The executable name (must be in the system PATH or a full path provided by user)
VHS_DECODE_COMMAND = "vhs-decode"
CONFIG_FILE_NAME = "vhs_decode_config.txt" # File to save command arguments

# Regex patterns for parsing vhs-decode output
FRAME_PATTERN = re.compile(r"File Frame (\d+): VHS")
# Updated to match any line containing the text "dropping field"
DROPPED_FIELD_PATTERN = "dropping field"
# Updated to match any line containing the text "skipped a track"
TRACK_SKIP_PATTERN = "skipped a track"
ANSI_ESCAPE_PATTERN = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')

# --- Utility Functions ---

def convert_frame_to_timecode(frame_number):
    """Converts a frame number (at 25 FPS) to HH:MM:SS.FF format."""
    try:
        frame_number = int(frame_number)
    except (TypeError, ValueError):
        return "00:00:00.00"

    # Calculate total seconds and remaining frames
    total_seconds = frame_number / FPS
    frames = frame_number % FPS
    
    # Calculate HH:MM:SS components
    seconds = int(total_seconds % 60)
    minutes = int((total_seconds // 60) % 60)
    hours = int(total_seconds // 3600)
    
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{int(frames):02d}"

class VhsDecodeApp(ctk.CTk):
    """Main application window for the VHS Decode GUI."""
    def __init__(self):
        super().__init__()
        
        # --- Theme and Appearance Setup ---
        self.pastel_green = "#A7F484" # Pastel green accent color
        ctk.set_appearance_mode("Dark") 
        ctk.set_default_color_theme("blue") # Base theme, using custom colors below

        # --- App Setup ---
        self.title("VHS Decode GUI")
        self.geometry("800x650")
        
        # Configure main window grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0) # Input/Controls
        self.grid_rowconfigure(1, weight=0) # Status Dashboard
        self.grid_rowconfigure(2, weight=1) # Log Area
        self.grid_rowconfigure(3, weight=0) # Control Button

        # --- State Variables ---
        self.input_file_path = ctk.StringVar(value="")
        self.command_args = ctk.StringVar(value="--tf VHS --pal") 
        
        # Status variables (for the dashboard)
        self.current_frame = ctk.StringVar(value="0")
        self.timecode = ctk.StringVar(value="00:00:00.00")
        self.decode_fps = ctk.StringVar(value="0.00")
        self.dropped_field_count = ctk.StringVar(value="0")
        self.track_skip_count = ctk.StringVar(value="0")

        self.decoding_in_progress = False
        self.process = None # Subprocess handle
        self.export_in_progress = False
        self.export_process = None
        
        # Performance Tracking & Throttling
        self.start_time = 0.0
        self.last_frame = 0 # For FPS calculation
        self.last_time = 0.0 # For FPS calculation
        self.last_gui_update_time = time.time() # For 5-second throttling
        self.frame_buffer = 0 # Latest frame number received
        self.dropped_field_buffer = 0 # Count since last GUI update
        self.track_skip_buffer = 0 # Count since last GUI update

        # --- Config and Cleanup ---
        self.config_file_path = CONFIG_FILE_NAME
        self._load_config() # Load configuration right away
        self.protocol("WM_DELETE_WINDOW", self._on_closing) # Handle window close event
        
        # --- Build UI ---
        self._create_input_frame()
        self._create_status_dashboard()
        self._create_log_frame()
        self._create_control_frame()


    # --- Config Management ---

    def _load_config(self):
        """Loads command arguments from a local config file."""
        if os.path.exists(self.config_file_path):
            try:
                with open(self.config_file_path, 'r') as f:
                    content = f.read()
                    match = re.search(r'vhsdecodeArguments="(.*?)"', content)
                    if match:
                        self.command_args.set(match.group(1))
            except Exception as e:
                self.log_output(f"Warning: Could not load config file: {e}")

    def _save_config(self):
        """Saves command arguments to a local config file, preserving other settings."""
        try:
            new_line = f'vhsdecodeArguments="{self.command_args.get()}"\n'
            lines = []
            if os.path.exists(self.config_file_path):
                with open(self.config_file_path, 'r') as f:
                    lines = f.readlines()
            
            updated = False
            for i, line in enumerate(lines):
                if line.strip().startswith("vhsdecodeArguments="):
                    lines[i] = new_line
                    updated = True
                    break
            
            if not updated:
                if lines and not lines[-1].endswith('\n'):
                    lines.append('\n')
                lines.append(new_line)
            
            with open(self.config_file_path, 'w') as f:
                f.writelines(lines)
        except Exception as e:
            self.log_output(f"Warning: Could not save config file: {e}")

    def _on_closing(self):
        """Handles window close event: saves config and safely closes."""
        # Attempt to terminate the running process before exiting
        if self.decoding_in_progress and self.process:
            try:
                self.process.terminate() 
            except Exception:
                pass # Process might already be dead
            time.sleep(0.5) # Give subprocess a moment to clean up

        if self.export_in_progress and self.export_process:
            try:
                self.export_process.terminate()
            except Exception:
                pass

        self._save_config()
        self.destroy()

    # --- UI Component Creation Methods ---

    def _create_input_frame(self):
        """Creates the frame for command and file selection."""
        input_frame = ctk.CTkFrame(self)
        input_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        input_frame.grid_columnconfigure((0, 1), weight=1)
        
        # Command Input
        cmd_label = ctk.CTkLabel(input_frame, text="vhs-decode Arguments:", anchor="w", text_color=self.pastel_green)
        cmd_label.grid(row=0, column=0, padx=10, pady=(10, 2), sticky="w")
        
        self.cmd_entry = ctk.CTkEntry(input_frame, textvariable=self.command_args, placeholder_text="e.g., --decode-audio --video-format ntsc-vhs")
        self.cmd_entry.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")

        # File Selection
        file_label = ctk.CTkLabel(input_frame, text="Input FLAC File Path:", anchor="w", text_color=self.pastel_green)
        file_label.grid(row=0, column=1, padx=10, pady=(10, 2), sticky="w")
        
        file_entry = ctk.CTkEntry(input_frame, textvariable=self.input_file_path, placeholder_text="Select a .flac file...", state="readonly")
        file_entry.grid(row=1, column=1, padx=10, pady=(0, 10), sticky="ew")
        
        file_button = ctk.CTkButton(input_frame, text="Select File", command=self._select_input_file, fg_color=self.pastel_green, text_color="#1F1F1F", hover_color="#89C86F")
        file_button.grid(row=1, column=1, padx=(0, 10), pady=(0, 10), sticky="e") 
        
        # Dynamically adjust the entry padding to ensure the button is visible
        input_frame.update_idletasks()
        file_entry.configure(width=input_frame.winfo_width() / 2 - file_button.winfo_width() - 30)

    def _create_status_dashboard(self):
        """Creates the dashboard displaying real-time metrics."""
        dashboard = ctk.CTkFrame(self)
        dashboard.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        # 5 equal columns for 5 status boxes
        dashboard.grid_columnconfigure((0, 1, 2, 3, 4), weight=1) 
        
        def create_status_box(parent, column, label_text, value_var):
            """Helper function to create a styled status indicator box."""
            box = ctk.CTkFrame(parent)
            box.grid(row=0, column=column, padx=8, pady=10, sticky="nsew")
            box.grid_columnconfigure(0, weight=1)
            
            label = ctk.CTkLabel(box, text=label_text, font=ctk.CTkFont(size=12), text_color=self.pastel_green)
            label.grid(row=0, column=0, padx=10, pady=(5, 0), sticky="ew")
            
            value = ctk.CTkLabel(box, textvariable=value_var, font=ctk.CTkFont(size=18, weight="bold"), text_color="white")
            value.grid(row=1, column=0, padx=10, pady=(0, 5), sticky="ew")
            return box

        # Status Boxes
        create_status_box(dashboard, 0, "Current Frame", self.current_frame)
        create_status_box(dashboard, 1, "Timecode (HH:MM:SS.FF)", self.timecode)
        create_status_box(dashboard, 2, "Decode Speed (FPS)", self.decode_fps)
        create_status_box(dashboard, 3, "Dropped Field Count", self.dropped_field_count)
        create_status_box(dashboard, 4, "Track Skip Count", self.track_skip_count)

    def _create_log_frame(self):
        """Creates the scrollable, read-only log output area."""
        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=2, column=0, padx=20, pady=(10, 10), sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)
        
        log_label = ctk.CTkLabel(log_frame, text="Decoder Output Log:", anchor="w", text_color=self.pastel_green)
        log_label.grid(row=0, column=0, padx=10, pady=(5, 0), sticky="w")

        # CTkTextbox is a customized Tkinter Text widget
        self.log_text_area = ctk.CTkTextbox(log_frame, wrap="word", activate_scrollbars=True, text_color="white", fg_color="#2B2B2B", font=ctk.CTkFont(family="Consolas", size=11))
        self.log_text_area.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        
        # Configure tags for ANSI colors
        self.log_text_area.tag_config("30", foreground="#808080") # Black (Gray)
        self.log_text_area.tag_config("31", foreground="#FF5555") # Red
        self.log_text_area.tag_config("32", foreground="#55FF55") # Green
        self.log_text_area.tag_config("33", foreground="#FFFF55") # Yellow
        self.log_text_area.tag_config("34", foreground="#5555FF") # Blue
        self.log_text_area.tag_config("35", foreground="#FF55FF") # Magenta
        self.log_text_area.tag_config("36", foreground="#55FFFF") # Cyan
        self.log_text_area.tag_config("37", foreground="#FFFFFF") # White
        
        self.log_text_area.configure(state="disabled") # Set to read-only

    def _create_control_frame(self):
        """Creates the main control button and status message area."""
        control_frame = ctk.CTkFrame(self, fg_color="transparent")
        control_frame.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="ew")
        control_frame.grid_columnconfigure((0, 1), weight=1) # Two columns for buttons
        
        self.start_button = ctk.CTkButton(control_frame, text="Start Decoding", command=self._start_decoding, height=40, font=ctk.CTkFont(size=16, weight="bold"), fg_color=self.pastel_green, text_color="#1F1F1F", hover_color="#89C86F")
        self.start_button.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="ew") # Left button
        
        self.cancel_button = ctk.CTkButton(control_frame, text="Cancel Decoding", command=self._cancel_decoding, height=40, font=ctk.CTkFont(size=16, weight="bold"), fg_color="#C84040", text_color="white", hover_color="#A83030", state="disabled")
        self.cancel_button.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="ew") # Right button
        
        # Status message for process feedback (errors, completion)
        self.status_message = ctk.CTkLabel(control_frame, text="", text_color="red")
        self.status_message.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 5), sticky="ew") # Span both columns

        # --- Extra Tools Buttons ---
        self.ld_analyse_button = ctk.CTkButton(control_frame, text="Open in ld-analyse", command=self._open_ld_analyse, height=30, fg_color="#4A4A4A", hover_color="#5A5A5A")
        self.ld_analyse_button.grid(row=2, column=0, padx=(10, 5), pady=(10, 0), sticky="ew")

        self.align_button = ctk.CTkButton(control_frame, text="Auto Audio Align", command=self._auto_audio_align, height=30, fg_color="#4A4A4A", hover_color="#5A5A5A")
        self.align_button.grid(row=2, column=1, padx=(5, 10), pady=(10, 0), sticky="ew")

        self.export_button = ctk.CTkButton(control_frame, text="Video Export", command=self._video_export, height=30, fg_color="#4A4A4A", hover_color="#5A5A5A")
        self.export_button.grid(row=3, column=0, padx=(10, 5), pady=(10, 0), sticky="ew")


    # --- Logic and Event Handlers ---

    def _select_input_file(self):
        """Opens a file dialog to select the input FLAC file."""
        file_path = filedialog.askopenfilename(
            title="Select Input FLAC File",
            filetypes=(("FLAC files", "*.flac"), ("All files", "*.*"), ("Raw Capture files", "*.u8"), ("TBC Files", "*.tbc"))
        )
        if file_path:
            self.input_file_path.set(file_path)
    
    def _cancel_decoding(self):
        """Sends SIGTERM to the subprocess to safely stop decoding."""
        if self.decoding_in_progress and self.process:
            self.log_output("\n--- User requested cancellation. Attempting safe termination... ---")
            
            # Use terminate() which sends SIGTERM (CTRL+C/Break equivalent on Unix/Mac)
            try:
                self.process.terminate() 
            except OSError:
                # Handle case where process may have already exited
                pass
            
            self.cancel_button.configure(state="disabled")
        else:
             self.status_message.configure(text="No active process to cancel.", text_color="orange")

    def _open_ld_analyse(self):
        """Opens the decoded TBC file in ld-analyse."""
        input_path = self.input_file_path.get()
        if not input_path:
            self.log_output("Error: No input file selected.")
            return

        input_dir = os.path.dirname(input_path)
        input_basename = os.path.basename(input_path)
        filename_only = os.path.splitext(input_basename)[0]
        tbc_path = os.path.join(input_dir, f"{filename_only}-Decoded.tbc")
        
        cmd = ["ld-analyse", tbc_path]
        self.log_output(f"--- Launching ld-analyse ---\nCommand: {' '.join(cmd)}")
        
        threading.Thread(target=self._run_generic_command, args=(cmd,), daemon=True).start()

    def _auto_audio_align(self):
        """Runs the Auto Audio Align script."""
        input_path = self.input_file_path.get()
        if not input_path:
            self.log_output("Error: No input file selected.")
            return

        input_dir = os.path.dirname(input_path)
        
        # Find required files
        linear_flacs = glob.glob(os.path.join(input_dir, "*-linear.flac"))
        json_files = glob.glob(os.path.join(input_dir, "*Decoded.tbc.json"))
        
        if not linear_flacs:
            self.log_output("Error: No *-linear.flac file found in input directory.")
            return
        if not json_files:
            self.log_output("Error: No *Decoded.tbc.json file found in input directory.")
            return
            
        # Heuristic: use the first match, or try to match basename
        input_basename = os.path.basename(input_path)
        filename_only = os.path.splitext(input_basename)[0]
        
        # Try to find files that contain the input filename, otherwise default to first found
        linear_flac = next((f for f in linear_flacs if filename_only in os.path.basename(f)), linear_flacs[0])
        json_file = next((f for f in json_files if filename_only in os.path.basename(f)), json_files[0])

        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(script_dir, "AutoAudioAlign", "align.sh")
        cmd = [script_path, linear_flac, json_file]
        
        self.log_output(f"--- Starting Auto Audio Align ---\nCommand: {' '.join(cmd)}")
        threading.Thread(target=self._run_generic_command, args=(cmd,), daemon=True).start()

    def _video_export(self):
        """Runs tbc-video-export with arguments from config."""
        if self.export_in_progress:
            return

        input_path = self.input_file_path.get()
        if not input_path:
            self.log_output("Error: No input file selected.")
            return

        input_dir = os.path.dirname(input_path)
        input_basename = os.path.basename(input_path)
        filename_only = os.path.splitext(input_basename)[0]
        tbc_path = os.path.join(input_dir, f"{filename_only}-Decoded.tbc")
        
        export_args = ""
        if os.path.exists(self.config_file_path):
            try:
                with open(self.config_file_path, 'r') as f:
                    content = f.read()
                    match = re.search(r'videoExportArguments="(.*?)"', content)
                    if match:
                        export_args = match.group(1)
            except Exception as e:
                self.log_output(f"Warning: Could not read config file: {e}")

        output_base = os.path.join(input_dir, f"{filename_only}-export")
        cmd = ["tbc-video-export"] + export_args.split() + [tbc_path, output_base]
        
        self.export_in_progress = True
        self.export_button.configure(text="Cancel Export", command=self._cancel_export, fg_color="#C84040", hover_color="#A83030")

        self.log_output(f"--- Starting Video Export ---\nCommand: {' '.join(cmd)}")
        threading.Thread(target=self._run_export_process, args=(cmd,), daemon=True).start()

    def _cancel_export(self):
        """Cancels the running video export process."""
        if self.export_in_progress and self.export_process:
            self.log_output("\n--- User requested export cancellation... ---")
            try:
                self.export_process.send_signal(signal.SIGINT)
            except Exception:
                pass

    def _run_export_process(self, cmd_list):
        """Runs the export command, parses output for progress, and logs."""
        try:
            self.export_process = subprocess.Popen(
                cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            progress_pattern = re.compile(r"Info:\s+(\d+)\s+frames processed\s+-\s+([\d.]+)\s+FPS")

            for line in iter(self.export_process.stdout.readline, ''):
                if line:
                    line_stripped = line.strip()
                    match = progress_pattern.search(line_stripped)
                    if match:
                        frames = int(match.group(1))
                        fps = float(match.group(2))
                        self.after(0, self._update_export_status, frames, fps)
                    
                    self.after(0, self.log_output, line_stripped)
            
            self.export_process.stdout.close()
            return_code = self.export_process.wait()
            
            self.after(0, self._finalize_export, return_code)
                
        except Exception as e:
            self.after(0, self.log_output, f"Failed to run command: {e}")
            self.after(0, self._finalize_export, -1)

    def _update_export_status(self, frames, fps):
        """Updates the status dashboard with export progress."""
        self.current_frame.set(f"{frames:,}")
        self.decode_fps.set(f"{fps:.2f}")
        self.timecode.set(convert_frame_to_timecode(frames))

    def _finalize_export(self, return_code):
        """Resets UI after export finishes."""
        self.export_in_progress = False
        self.export_process = None
        self.export_button.configure(text="Video Export", command=self._video_export, fg_color="#4A4A4A", hover_color="#5A5A5A")
        
        if return_code == 0:
            self.log_output("Video Export finished successfully.")
        elif return_code != 0:
            self.log_output(f"Video Export finished with error code {return_code}")

    def _run_generic_command(self, cmd_list):
        """Runs a command in a subprocess and logs output."""
        try:
            process = subprocess.Popen(
                cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            for line in iter(process.stdout.readline, ''):
                if line:
                    self.after(0, self.log_output, line.strip())
            
            process.stdout.close()
            return_code = process.wait()
            
            if return_code != 0:
                self.after(0, self.log_output, f"Process finished with error code {return_code}")
            else:
                self.after(0, self.log_output, "Process finished successfully.")
                
        except Exception as e:
            self.after(0, self.log_output, f"Failed to run command: {e}")

    def _start_decoding(self):
        """Prepares state and starts the decoding process in a separate thread."""
        if self.decoding_in_progress:
            self.status_message.configure(text="Decoding already in progress. Please wait.")
            return

        input_path = self.input_file_path.get()
        if not input_path or not os.path.exists(input_path):
            self.status_message.configure(text="Error: Please select a valid input file.", text_color="red")
            return

        # 1. Reset State
        self.log_text_area.configure(state="normal")
        self.log_text_area.delete("1.0", END)
        self.log_text_area.configure(state="disabled")
        
        self.current_frame.set("0")
        self.timecode.set("00:00:00.00")
        self.decode_fps.set("0.00")
        self.dropped_field_count.set("0")
        self.track_skip_count.set("0")
        self.status_message.configure(text="")

        # 2. Build Command & Calculate Output Path
        args = self.command_args.get().strip()
        
        # Calculate Output Path (same directory, same name, plus '-Decoded', no extension)
        input_dir = os.path.dirname(input_path)
        input_basename = os.path.basename(input_path)
        filename_only = os.path.splitext(input_basename)[0]
        output_filename = f"{filename_only}-Decoded"
        output_path = os.path.join(input_dir, output_filename)
        
        # The full command structure is: vhs-decode [args] [input_file] [output_prefix]
        full_command_display = f"{VHS_DECODE_COMMAND} {args} \"{input_path}\" \"{output_path}\""

        self.log_output(f"--- Starting Decode ---\nOutput Prefix: {output_path}\nFull Command: {full_command_display}\n")

        # 3. Start Thread
        self.start_time = time.time()
        self.last_frame = 0
        self.last_time = self.start_time
        # Initialize throttling variables
        self.last_gui_update_time = self.start_time
        self.frame_buffer = 0
        self.dropped_field_buffer = 0
        self.track_skip_buffer = 0
        
        self.decoding_in_progress = True
        self.start_button.configure(text="Decoding...", state="disabled", fg_color="#3E3E3E", text_color="white")
        self.cancel_button.configure(state="normal") # Enable cancel button

        # Pass the arguments and paths explicitly to the thread function
        self.decode_thread = threading.Thread(target=self._run_decode_process, 
                                             args=(args, input_path, output_path), 
                                             daemon=True)
        self.decode_thread.start()

    def _run_decode_process(self, args, input_path, output_path):
        """Executes vhs-decode and reads its output line by line."""
        try:
            # The structure must be: [vhs-decode] + [user args] + [input file path] + [output file prefix]
            user_args_list = args.split()
            
            # Construct the final command list: [vhs-decode, arg1, arg2, ..., input_path, output_path]
            command_list = [VHS_DECODE_COMMAND] + user_args_list + [input_path] + [output_path]

            self.process = subprocess.Popen(
                command_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, # Merge stdout and stderr for single log
                text=True,
                bufsize=1,
                universal_newlines=True # Ensure output is read as text
            )

            # Read output line by line until EOF
            for line in iter(self.process.stdout.readline, ''):
                # Use self.after to safely update the GUI from the worker thread
                self.after(0, self._process_output_line, line.strip()) 
            
            # Wait for the process to finish
            self.process.stdout.close()
            return_code = self.process.wait()

            # Schedule final status update on main thread
            self.after(0, self._finalize_decoding, return_code)

        except FileNotFoundError:
            # Handle case where vhs-decode is not in the PATH
            self.after(0, self._finalize_decoding, -1, f"Error: '{VHS_DECODE_COMMAND}' not found. Ensure it is installed and in your system PATH.")
        except Exception as e:
            # Handle other unexpected errors
            self.after(0, self._finalize_decoding, -1, f"An unexpected error occurred: {type(e).__name__}: {e}")

    def _update_gui_status(self, current_frame):
        """Safely updates all GUI status indicators using accumulated data and resets buffers."""
        current_time = time.time()
        
        # 1. Update frame and timecode
        self.current_frame.set(f"{current_frame:,}")
        self.timecode.set(convert_frame_to_timecode(current_frame))

        # 2. Update Dropped Field Count
        current_dropped = int(self.dropped_field_count.get())
        self.dropped_field_count.set(str(current_dropped + self.dropped_field_buffer))
        self.dropped_field_buffer = 0

        # 3. Update Track Skip Count
        current_skip = int(self.track_skip_count.get())
        self.track_skip_count.set(str(current_skip + self.track_skip_buffer))
        self.track_skip_buffer = 0
        
        # 4. Update FPS
        frame_diff = current_frame - self.last_frame
        time_diff = current_time - self.last_time

        if time_diff > 0:
            fps = frame_diff / time_diff
            self.decode_fps.set(f"{fps:.2f}")

        # Reset tracking variables for FPS calculation and throttling timer
        self.last_frame = current_frame
        self.last_time = current_time
        self.last_gui_update_time = current_time

    def _process_output_line(self, line):
        """Analyzes a single line of output and updates state or the log, applying 5-second throttling."""
        if not line:
            return

        frame_found = False
        
        # 1. Frame and Timecode Parsing
        frame_match = FRAME_PATTERN.search(line)
        if frame_match:
            current_frame = int(frame_match.group(1))
            self.frame_buffer = current_frame # Always track the latest frame number
            frame_found = True
            
        # 2. Dropped Field Count
        # Check if the line contains the new, more general pattern
        elif DROPPED_FIELD_PATTERN in line:
            self.dropped_field_buffer += 1
            
        # 3. Track Skip Count
        # Check if the line contains the new, more general pattern
        elif TRACK_SKIP_PATTERN in line:
            self.track_skip_buffer += 1
            
        # 4. General Log
        else:
            self.log_output(line)

        # Check for throttling (only attempt update if we've seen a frame and 5 seconds passed)
        if frame_found and (time.time() - self.last_gui_update_time >= 5.0):
            self._update_gui_status(self.frame_buffer)


    def _finalize_decoding(self, return_code, error_message=None):
        """Resets the UI state after the process finishes."""
        # Ensure the final buffered counts are reflected in the UI, unless the process was terminated/failed immediately.
        if self.frame_buffer > 0 and (time.time() - self.last_gui_update_time > 0):
            self._update_gui_status(self.frame_buffer)
        
        self.decoding_in_progress = False
        self.start_button.configure(text="Start Decoding", state="normal", fg_color=self.pastel_green)
        self.cancel_button.configure(state="disabled") # Disable cancel button
        
        if error_message:
            self.status_message.configure(text=error_message, text_color="red")
            self.log_output(f"\n--- DECODING FAILED ---")
        elif return_code == 0:
            # Calculate final average FPS upon success
            total_time = time.time() - self.start_time
            total_frames = int(self.current_frame.get().replace(',', ''))
            
            if total_time > 0 and total_frames > 0:
                 final_fps = total_frames / total_time
                 self.decode_fps.set(f"{final_fps:.2f} (Final Avg)")
                 self.log_output(f"\n--- DECODING COMPLETE ---\nTotal time: {total_time:.2f}s | Final Average FPS: {final_fps:.2f}")
            else:
                 self.log_output(f"\n--- DECODING COMPLETE --- (No frames processed or duration was too short)")
                 
            self.status_message.configure(text="Decoding completed successfully!", text_color=self.pastel_green)

        elif self.process.returncode in [-2, -9, 143]: # Common codes for SIGINT/SIGKILL/SIGTERM
            self.status_message.configure(text="Decoding cancelled by user.", text_color="orange")
            self.log_output(f"\n--- DECODING CANCELLED --- (Exit code {self.process.returncode})")

        else:
            # Non-zero return code (likely a vhs-decode error)
            self.status_message.configure(text=f"Decoding finished with error code {return_code}", text_color="orange")
            self.log_output(f"\n--- DECODING FINISHED WITH NON-ZERO EXIT CODE: {return_code} ---")

    def log_output(self, text):
        """Appends text to the read-only log area and scrolls to the bottom."""
        self.log_text_area.configure(state="normal")
        
        # Split by ANSI SGR codes (colors)
        parts = re.split(r'(\x1B\[[\d;]*m)', text)
        current_tags = []
        
        for part in parts:
            if not part:
                continue
            
            if part.startswith('\x1B['):
                # Parse SGR code
                try:
                    content = part[2:-1]
                    codes = content.split(';')
                    for code in codes:
                        if code == '0' or code == '':
                            current_tags = []
                        elif code in ['30', '31', '32', '33', '34', '35', '36', '37']:
                            # Remove existing color tags
                            current_tags = [t for t in current_tags if t not in ['30', '31', '32', '33', '34', '35', '36', '37']]
                            current_tags.append(code)
                except Exception:
                    pass
            else:
                # Text content - strip other ANSI codes
                clean_text = ANSI_ESCAPE_PATTERN.sub('', part)
                if clean_text:
                    self.log_text_area.insert(END, clean_text, tuple(current_tags))

        self.log_text_area.insert(END, "\n")
        self.log_text_area.see(END) # Auto-scroll
        self.log_text_area.configure(state="disabled")

# Standard Python entry point
if __name__ == "__main__":
    app = VhsDecodeApp()
    app.mainloop()
