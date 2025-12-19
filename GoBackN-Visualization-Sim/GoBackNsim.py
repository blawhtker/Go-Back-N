import tkinter as tk
from tkinter import scrolledtext
import time

# GLOBAL SETTINGS & DEFAULTS
# These control how the simulation starts. You can change them in the GUI too.
DEFAULT_TOTAL_PACKETS = 40
DEFAULT_WINDOW_SIZE = 8
DEFAULT_TIMEOUT = 7        # Seconds to wait before retransmission
DEFAULT_DELAY = 3         # Seconds it takes for packets to propagate
DEFAULT_SEQ_SPACE = 41     # The maximum sequence number

# PACKET CLASS
# Holds the type ('DATA' or 'ACK')
# and the Sequence Number (ID).

class Packet:
    def __init__(self, type, seq_num, data=None):
        self.type = type        
        self.seq_num = seq_num  
        self.data = data        

# CHANNEL SIMULATOR
# This class acts as the "Network Wire". It handles:
# 1. Delay (holding packets for a few seconds).
# 2. Loss (dropping packets if they are on the "kill list").
class Channel:
    def __init__(self, loss_data_str, loss_ack_str, delay):
        # Convert "2, 5, 8" text input into a list of integers [2, 5, 8]
        self.loss_data = [int(x) for x in loss_data_str.split(',') if x.strip().isdigit()]
        self.loss_ack = [int(x) for x in loss_ack_str.split(',') if x.strip().isdigit()]
        self.delay = delay
        self.packet_queue = [] # This list holds all packets currently traveling

    def send_to_network(self, packet, destination, current_time, offset=0.0):
        """
        Puts a packet onto the wire.
        'offset' is used for the "burst" effect. It adds a tiny delay (Transmission Delay)
        so packets don't look like they are stacked on top of each other.
        """
        drop = False
        
        # Check if this packet is scheduled to be lost
        if packet.type == 'DATA':
            if packet.seq_num in self.loss_data:
                drop = True
                self.loss_data.remove(packet.seq_num) # Only drop it once
        elif packet.type == 'ACK':
            if packet.seq_num in self.loss_ack:
                drop = True
                self.loss_ack.remove(packet.seq_num)

        if drop:
            return "DROP"
        
        # Calculate exactly when this packet will arrive.
        # Arrival = (Current Time) + (Tiny Burst Offset) + (Propagation Delay)
        send_time_float = current_time + offset
        arrival_time_float = send_time_float + self.delay
        
        # Store it in the queue to be delivered later
        self.packet_queue.append((arrival_time_float, packet, destination, send_time_float))
        return "SENT"

    def get_delivered_packets(self, current_time):
        """
        Looks at the queue and returns any packets that should have arrived by 'current_time'.
        """
        delivered = []
        keep_in_queue = []
        
        for item in self.packet_queue:
            arrival_time, pkt, dest, send_time = item
            
            # If the current time is past the arrival time, deliver it!
            if current_time >= arrival_time:
                delivered.append(item)
            else:
                keep_in_queue.append(item)
        
        self.packet_queue = keep_in_queue
        return delivered

# SENDER CLASS
# Implements the Go-Back-N Logic.
class Sender:
    def __init__(self, window_size, total_packets, timeout):
        self.window_size = window_size
        self.total_packets = total_packets
        self.timeout = timeout
        
        # Critical GBN Variables
        self.base = 0             # Start of  window (oldest un-acked packet)
        self.next_seq = 0         # Next packet we are preparing to send
        self.buffer = {}          # Save sent packets here in case needed to retransmit
        self.timer_start = -1     # Timestamp when the timer started
        self.retransmissions = 0
        self.duplicate_pkts = 0   

    def check_timer(self, current_time):
        """
        Checks if the timer has expired.
        NOTE: In Go-Back-N, only have ONE timer, for the 'base' packet.
        """
        # If the window is empty (we caught up), turn off the timer
        if self.base == self.next_seq:
            return False 
        
        # Check if time elapsed > timeout limit
        if current_time - self.timer_start >= self.timeout:
            return True 
        return False

# RECEIVER CLASS
class Receiver:
    def __init__(self):
        self.expected_seq = 0   # The specific packet number we are waiting for
        self.delivered_count = 0
        self.last_ack_sent = -1 # Used to prevent spamming the log with duplicate ACKs

# MAIN GUI APPLICATION
class GbnSimulator:
    def __init__(self, root):
        self.root = root
        self.root.title("EEL 4781: Go-Back-N Protocol Simulator")
        self.root.geometry("1100x850")

        self.running = False
        self.is_finishing = False # Used for the "Victory Lap" (Wait 5s at end)
        self.current_time = 0
        self.sender = None
        self.receiver = None
        self.channel = None
        self.tick_start_time = 0 

        self.setup_gui()

    def setup_gui(self):
        # 1. Config Area (Top)
        config_frame = tk.LabelFrame(self.root, text="Simulation Configuration", font=("Arial", 12, "bold"), padx=10, pady=10)
        config_frame.pack(fill="x", padx=10, pady=5)

        self.e_packets = self.create_labeled_entry(config_frame, "Total Packets:", DEFAULT_TOTAL_PACKETS, 0, 0)
        self.e_window = self.create_labeled_entry(config_frame, "Window Size (N):", DEFAULT_WINDOW_SIZE, 0, 2)
        self.e_timeout = self.create_labeled_entry(config_frame, "Timeout (sec):", DEFAULT_TIMEOUT, 0, 4)   # Ideal delay = (2 * Propagation Delay) + 1 for smooth animation
        self.e_loss_data = self.create_labeled_entry(config_frame, "Dropped Packet Sequence:", "", 1, 0)
        self.e_loss_ack = self.create_labeled_entry(config_frame, "Dropped ACK Seqence:", "", 1, 2)
        self.e_delay = self.create_labeled_entry(config_frame, "Propagation Delay (sec):", DEFAULT_DELAY, 1, 4)

        btn_frame = tk.Frame(config_frame)
        btn_frame.grid(row=0, column=6, rowspan=2, padx=20)
        self.btn_start = tk.Button(btn_frame, text="START SIMULATION", bg="#ddffdd", font=("Arial", 12, "bold"), command=self.start_sim)
        self.btn_start.pack(pady=2, fill="x")
        self.btn_stop = tk.Button(btn_frame, text="STOP", bg="#ffdddd", font=("Arial", 12), command=self.stop_sim, state="disabled")
        self.btn_stop.pack(pady=2, fill="x")

        # 2. Visualization Area (The Sliding Window)
        vis_frame = tk.LabelFrame(self.root, text="Go-Back-N Protocol (Sliding Window) Visualization", font=("Arial", 12, "bold"), padx=10, pady=10)
        vis_frame.pack(fill="x", padx=10, pady=5)

        self.canvas = tk.Canvas(vis_frame, height=400, bg="white")
        self.canvas.pack(fill="x", expand=True)

        legend_frame = tk.Frame(vis_frame)
        legend_frame.pack(pady=5)
        self.make_legend_item(legend_frame, "green", "Acked/Received").pack(side="left", padx=10)
        self.make_legend_item(legend_frame, "yellow", "Sent (In Window)").pack(side="left", padx=10)
        self.make_legend_item(legend_frame, "orange", "Data In Flight").pack(side="left", padx=10)
        self.make_legend_item(legend_frame, "#add8e6", "Expecting").pack(side="left", padx=10)
        self.make_legend_item(legend_frame, "red", "Window", is_border=True).pack(side="left", padx=10)

        # 3. Stats Area
        stats_frame = tk.Frame(self.root)
        stats_frame.pack(fill="x", padx=20)
        self.lbl_time = tk.Label(stats_frame, text="Time: 0s", font=("Arial", 14, "bold"))
        self.lbl_time.pack(side="left", padx=20)
        self.lbl_retrans = tk.Label(stats_frame, text="Retransmissions: 0", font=("Arial", 14, "bold"), fg="red")
        self.lbl_retrans.pack(side="left", padx=20)
        self.lbl_dupes = tk.Label(stats_frame, text="Duplicate Packets Sent: 0", font=("Arial", 14, "bold"), fg="orange")
        self.lbl_dupes.pack(side="left", padx=20)

        # 4. Log Area (Bottom)
        log_frame = tk.LabelFrame(self.root, text="Event Log", font=("Arial", 12, "bold"), padx=10, pady=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_area = scrolledtext.ScrolledText(log_frame, height=10, font=("Consolas", 11))
        self.log_area.pack(fill="both", expand=True)
        
        self.log_area.tag_config("INFO", foreground="black")
        self.log_area.tag_config("SEND", foreground="blue")
        self.log_area.tag_config("ACK", foreground="green")
        self.log_area.tag_config("LOSS", foreground="red")
        self.log_area.tag_config("TIMEOUT", foreground="darkred", background="#ffdddd")
        self.log_area.tag_config("DONE", foreground="green", background="#ddffdd")

    def create_labeled_entry(self, parent, label, default, row, col):
        """Helper to create Label and an Entry box next to it."""
        tk.Label(parent, text=label, font=("Arial", 11)).grid(row=row, column=col, sticky="e", padx=5)
        entry = tk.Entry(parent, width=10, font=("Arial", 11))
        entry.insert(0, str(default))
        entry.grid(row=row, column=col+1, sticky="w", padx=5)
        return entry

    def make_legend_item(self, parent, color, text, is_border=False):
        """Helper to create small colored boxes in the legend."""
        f = tk.Frame(parent)
        if is_border:
            c = tk.Canvas(f, width=20, height=20, bg="white", highlightbackground="red", highlightthickness=2)
        else:
            c = tk.Canvas(f, width=20, height=20, bg=color, highlightthickness=1)
        c.pack(side="left")
        tk.Label(f, text=text, font=("Arial", 10)).pack(side="left")
        return f

    def log(self, tag, message):
        timestamp = f"[{self.current_time:02d}s] "
        self.log_area.insert(tk.END, timestamp + message + "\n", tag)
        self.log_area.see(tk.END)

    def start_sim(self):
        if self.running: return
        self.log_area.delete(1.0, tk.END)
        self.current_time = 0
        self.is_finishing = False
        
        # Read the values from input fields
        try:
            total = int(self.e_packets.get())
            win = int(self.e_window.get())
            timeout = int(self.e_timeout.get())
            delay = int(self.e_delay.get())
            data_drops = self.e_loss_data.get()
            ack_drops = self.e_loss_ack.get()
        except ValueError:
            self.log("LOSS", "Error: Please enter valid integers.")
            return

        # Initialize Logic Components
        self.channel = Channel(data_drops, ack_drops, delay)
        self.sender = Sender(win, total, timeout)
        self.receiver = Receiver()
        
        self.running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.log("INFO", "--- Simulation Started ---")
        
        # Start both the Logic Loop (Slow) and Animation Loop (Fast)
        self.tick_start_time = time.time()
        self.root.after(1000, self.simulation_tick)
        self.root.after(20, self.animate_loop)

    def stop_sim(self):
        self.running = False
        self.is_finishing = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.log("INFO", "--- Simulation Stopped ---")

    def animate_loop(self):
        """
        This runs 50 times per second to make the packets move smoothly.
        It does NOT change any logic, it just draws what is currently happening.
        """
        if not self.running: return
        elapsed = time.time() - self.tick_start_time
        if elapsed > 1.0: elapsed = 1.0
        self.draw_visualization(fraction=elapsed)
        self.root.after(20, self.animate_loop)

    def draw_visualization(self, fraction=0.0):
        self.canvas.delete("all")
        box_width = 30
        gap = 5
        start_x = 20
        
        total = self.sender.total_packets
        base = self.sender.base
        next_seq = self.sender.next_seq
        expected = self.receiver.expected_seq
        
        sender_y = 50
        receiver_y = 300
        
        # --- 1. DRAW SENDER (TOP ROW) ---
        self.canvas.create_text(start_x, sender_y - 30, text="SENDER", font=("Arial", 11, "bold"), anchor="w", fill="black")
        self.canvas.create_line(10, sender_y + 40, 1000, sender_y + 40, dash=(4, 4), fill="gray")

        for i in range(total):
            x = start_x + i * (box_width + gap)
            color = "lightgray"
            if i < base: color = "#90ee90" # Green (Acked)
            elif i >= base and i < next_seq: color = "#ffffe0" # Yellow (Sent)
            
            self.canvas.create_rectangle(x, sender_y, x + box_width, sender_y + box_width, fill=color, outline="black")
            self.canvas.create_text(x + box_width/2, sender_y + box_width/2, text=str(i))

        # Draw Red Window Border
        if base < total:
            win_start_x = start_x + base * (box_width + gap)
            end_seq = base + self.sender.window_size
            if end_seq > total: end_seq = total
            win_end_x = start_x + end_seq * (box_width + gap) - gap
            
            self.canvas.create_rectangle(win_start_x - 3, sender_y - 3, win_end_x + 3, sender_y + box_width + 3, outline="red", width=2)
            self.canvas.create_text(win_start_x, sender_y - 15, text=f"Window Base={base}", anchor="w", fill="red", font=("Arial", 8))
        elif self.is_finishing or base == total:
            self.canvas.create_text(start_x, sender_y - 15, text="TRANSMISSION COMPLETE", anchor="w", fill="green", font=("Arial", 10, "bold"))

        #2. DRAW PACKETS IN FLIGHT (MIDDLE)
        if self.channel:
            # Iterate all packets currently traveling in the channel
            for arrival_time, packet, destination, send_time in self.channel.packet_queue:
                
                # 'fraction' makes the animation smooth between seconds
                now = self.current_time + fraction
                
                # Calculate how far the packet has traveled (0% to 100%)
                time_passed = now - send_time
                progress = time_passed / self.channel.delay
                
                if progress < 0: progress = 0
                if progress > 1: progress = 1
                
                # Calculate Y position (Falling down or Rising up)
                start_y_vis = sender_y + box_width + 10
                end_y_vis = receiver_y - 10
                travel_distance = end_y_vis - start_y_vis
                
                pkt_x = start_x + packet.seq_num * (box_width + gap)

                if packet.type == 'DATA':
                    # DATA goes Down
                    current_y = start_y_vis + (travel_distance * progress)
                    fill_col = "orange"
                    txt = f"D{packet.seq_num}"
                    self.canvas.create_rectangle(pkt_x, current_y, pkt_x + box_width, current_y + 20, fill=fill_col, outline="black")
                    self.canvas.create_text(pkt_x + 15, current_y + 10, text=txt, font=("Arial", 8, "bold"))
                elif packet.type == 'ACK':
                    # ACK goes Up
                    current_y = end_y_vis - (travel_distance * progress)
                    fill_col = "#90ee90"
                    txt = f"A{packet.seq_num}"
                    self.canvas.create_oval(pkt_x + 5, current_y, pkt_x + 25, current_y + 20, fill=fill_col, outline="black")
                    self.canvas.create_text(pkt_x + 15, current_y + 10, text=txt, font=("Arial", 8, "bold"))

        # 3. DRAW RECEIVER (BOTTOM ROW) 
        self.canvas.create_text(start_x, receiver_y - 30, text="RECEIVER", font=("Arial", 11, "bold"), anchor="w", fill="black")
        self.canvas.create_line(10, receiver_y - 20, 1000, receiver_y - 20, dash=(4, 4), fill="gray")

        for i in range(total):
            x = start_x + i * (box_width + gap)
            color = "lightgray"
            if i < expected: color = "#90ee90" # Green
            elif i == expected: color = "#add8e6" # Blue
            
            self.canvas.create_rectangle(x, receiver_y, x + box_width, receiver_y + box_width, fill=color, outline="black")
            self.canvas.create_text(x + box_width/2, receiver_y + box_width/2, text=str(i))
            
            # Highlight the packet we are waiting for
            if i == expected:
                self.canvas.create_rectangle(x - 2, receiver_y - 2, x + box_width + 2, receiver_y + box_width + 2, outline="blue", width=2)
                self.canvas.create_text(x, receiver_y + box_width + 12, text="Wait", anchor="w", fill="blue", font=("Arial", 8))

    def simulation_tick(self):
        """
        Main Logic Loop. Runs once per second.
        Checks timers, sends packets, and delivers arrivals.
        """
        if not self.running: return
        self.tick_start_time = time.time()
        
        # CHECK: If everything is acknowledged
        if self.sender.base == self.sender.total_packets:
            if not self.is_finishing:
                self.is_finishing = True
                self.log("DONE", "All Packets Acknowledged! Simulation Complete...")
                self.root.after(5000, self.stop_sim)
            
            # Keep moving existing packets, but don't send new ones
            self.process_channel_only()
            self.lbl_time.config(text=f"Time: {self.current_time}s")
            self.current_time += 1
            self.root.after(1000, self.simulation_tick)
            return

        # --- NORMAL LOGIC ---
        
        # 1. SENDER TIMEOUT CHECK
        if self.sender.check_timer(self.current_time):
            self.log("TIMEOUT", f"Timeout Packet {self.sender.base}. Retransmitting Window.")
            self.sender.retransmissions += 1
            self.sender.timer_start = self.current_time
            
            # Retransmit the WHOLE window (Go-Back-N behavior)
            burst_offset = 0.0
            for seq in range(self.sender.base, self.sender.next_seq):
                self.sender.duplicate_pkts += 1
                pkt = self.sender.buffer[seq]
                
                # Send with offset (Burst) so they don't overlap visually
                status = self.channel.send_to_network(pkt, "Receiver", self.current_time, offset=burst_offset)
                burst_offset += 0.2 
                
                if status == "SENT": self.log("LOSS", f"Retransmitting Data {seq}")
                else: self.log("LOSS", f"Retransmission Data {seq} DROPPED by Channel")

        # 2. SEND BURST OF NEW PACKETS 
        burst_offset = 0.0
        while (self.sender.next_seq < self.sender.base + self.sender.window_size) and (self.sender.next_seq < self.sender.total_packets):
            seq = self.sender.next_seq
            pkt = Packet('DATA', seq, f"Payload_{seq}")
            self.sender.buffer[seq] = pkt
            
            # If this is the oldest un-acked packet, start the timer!
            if self.sender.base == self.sender.next_seq:
                self.sender.timer_start = self.current_time
                
            status = self.channel.send_to_network(pkt, "Receiver", self.current_time, offset=burst_offset)
            burst_offset += 0.2 
            
            if status == "SENT": self.log("SEND", f"Sender Data {seq}")
            else: self.log("LOSS", f"Sender Data {seq} -> DROPPED")
            self.sender.next_seq += 1

        # 3. DELIVER ARRIVING PACKETS
        self.process_channel_only()

        # 4. UPDATE GUI LABELS
        self.lbl_time.config(text=f"Time: {self.current_time}s")
        self.lbl_retrans.config(text=f"Retransmissions: {self.sender.retransmissions}")
        self.lbl_dupes.config(text=f"Duplicate Packets Sent: {self.sender.duplicate_pkts}")

        self.current_time += 1
        self.root.after(1000, self.simulation_tick)

    def process_channel_only(self):
        """Helper function to handle packet arrivals and ACK generation."""
        # Get list of packets that have arrived 'now'
        arrivals = self.channel.get_delivered_packets(self.current_time)
        
        for item in arrivals:
            arrival_time, pkt, dest, send_time = item
            
            # --- RECEIVER LOGIC ---
            if dest == "Receiver" and pkt.type == 'DATA':
                if pkt.seq_num == self.receiver.expected_seq:
                    # Hooray! This is the packet we wanted.
                    self.log("INFO", f"Receiver Data {pkt.seq_num} (Expected). Sending ACK.")
                    self.receiver.delivered_count += 1
                    self.receiver.expected_seq += 1
                    self.receiver.last_ack_sent = pkt.seq_num
                    
                    ack = Packet('ACK', pkt.seq_num)
                    
                    # IMPORTANT: We send the ACK based on the exact fractional arrival time
                    # This keeps the "spacing" between ACKs consistent with the Data spacing.
                    status = self.channel.send_to_network(ack, "Sender", arrival_time, offset=0.0)
                    
                    if status == "DROP": self.log("LOSS", f"ACK {pkt.seq_num} Dropped by Channel")
                else:
                    # Uh oh. Duplicate or Out of Order.
                    if pkt.seq_num < self.receiver.expected_seq:
                        self.log("INFO", f"Receiver Data {pkt.seq_num} (Duplicate). Ignore.")
                    else:
                        self.log("INFO", f"Receiver Data {pkt.seq_num} (Out of Order). Discard.")
                        # Rule: Re-send ACK for the last thing we successfully got.
                        if self.receiver.expected_seq > 0:
                            last_ack = self.receiver.expected_seq - 1
                            if self.receiver.last_ack_sent == last_ack:
                                self.log("INFO", f"Receiver sent ACK {last_ack}. Suppress duplicate.")
                            else:
                                self.log("INFO", f"Receiver re-sending ACK {last_ack}")
                                self.receiver.last_ack_sent = last_ack
                                ack = Packet('ACK', last_ack)
                                self.channel.send_to_network(ack, "Sender", arrival_time, offset=0.0)

            # --- SENDER LOGIC (Processing ACKs) ---
            elif dest == "Sender" and pkt.type == 'ACK':
                self.log("ACK", f"Sender received ACK {pkt.seq_num}")
                # Cumulative ACK: If we get ACK 5, it means 0-5 are safe.
                if pkt.seq_num >= self.sender.base:
                    self.sender.base = pkt.seq_num + 1
                    
                    # Reset timer if there are still packets waiting for ACKs
                    if self.sender.base < self.sender.next_seq:
                        self.sender.timer_start = self.current_time
                    else:
                        self.sender.timer_start = -1

if __name__ == "__main__":
    root = tk.Tk()
    app = GbnSimulator(root)
    root.mainloop()