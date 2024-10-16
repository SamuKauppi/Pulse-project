from machine import Pin, Signal, ADC, I2C
from piotimer import Piotimer
import ssd1306
import utime
from fifo import Fifo
from wifi import WLAN as Wifi
import kubios

# Read pulse with Piotimer and add them to a Fifo
def check_pulse(t):
    v = adc.read_u16()
    buffer.put(v)

def restart(t):
    global is_active
    data_manager.reset()
    is_active = 1
    print("juttu")
   
# Calculate the average from an array (partially written by ChatGPT)
def calculate_average(arr, threshold_b, threshold_a, heart_val):
    # Filter out non relevant values around the current value 
    filtered_values = list(filter(lambda num: num > heart_val - threshold_b and num < heart_val + threshold_a and num != 0, arr))
    
    # find the max and min values
    sum_val = 0
    count = 0
    max_val = float('-inf')
    min_val = float('inf')
    for num in filtered_values:
        sum_val += num
        count += 1
        if num > max_val:
            max_val = num
        if num < min_val:
            min_val = num
    
    if count > 0:
        # Return avg and diff
        avg_val = round(sum_val / count)
        return avg_val
    else:
        return 0


# Used for printing the curve on plotter view
print_counter = 0
def print_curve(value, avg, pulse_check):
    global print_counter
    print_counter += 1
    if print_counter > 6:
        print("Pulse: ", value, pulse_check, avg)
        print_counter = 0
        
    
# Handles the collected data and sends it to be calculated to DataManager
class BeatHandler:
    def __init__(self, data_manager):
        
        # beat detection
        self.last_state = 0      # Was it under or over pulse_check
        self.highest_v = 0       # Stores highest value
        self.bpm_was_made = 0    # Prevents checking ppi more than once per peak
        self.counter = 0         # Counts the ppi
        self.data_manager = data_manager
    
    # Process beat. Called every frame
    def process_beat(self, value, avg, max_value, dropped):
        # Create pulse check threhold
        pulse_check = round((avg + max_value * 1.5) / 2.5)
        
        # Used to debug by displaying the curve
        print_curve(value, avg, pulse_check)
        
        # If the current value is higher than pulse check threhold
        if value > pulse_check:
            # Find the peak (highest value)
            if self.highest_v < value:
                self.highest_v = value
            # If the value starts to fall and the bpm has not been calculated on this peak
            # Send the PPI
            elif self.bpm_was_made == 0:
                self.bpm_was_made = 1
                self.send_ppi(self.counter)
                
            self.last_state = 1
        else:
            # If the value just dropped below pulse check 
            if self.last_state == 1:
                self.bpm_was_made = 0
                self.highest_v = 0
            self.last_state = 0
            
        # Counts the PPI
        self.counter += 1 + dropped
                   
        
    # Sends the counted ppi's to data_manager
    def send_ppi(self, steps):
        
        # Send the ppi to display on oled
        self.data_manager.add_bpm_value(steps)
        # Send the ppi to save it for sending it to kubios
        self.data_manager.add_ppi(steps)
        # Reset ppi counter
        self.counter = 0
    
# A class that handles the OLED-screen and bpm
class DataManager:
    def __init__(self, connection):
        # oled
        i2c = I2C(1, scl=Pin("GP15"), sda=Pin("GP14"), freq=400000)
        self.oled = ssd1306.SSD1306_I2C(128, 64, i2c)
        self.text_onscreen = [] # For displaying bpm and flavour text under
        self.text_onscreen.append(["", 16])
        self.text_onscreen.append(["", 42])
        
        # ppis used which are sent to kubios 
        self.ppis = []
        self.max_size = 25
        self.max_time = 200000
        self.connection = connection
        self.timer = 0
        # values saved from kubios
        self.bpm = 0
        self.pns = 0
        self.sns = 0
        self.is_done = 0
        
        # variables related on displaying bpm on oled
        self.bpms = Fifo(9) # 9 is a lucky
        self.average_bpm = 0
        self.is_measuring = False
        self.MAX_BPM = 240
        self.MIN_BPM = 40
        self.FILTER = 60
    
    # Add a bpm-value to a list and get the average, which is displayed on oled
    # if the difference between the max and min is small enough, measuring is true
    # When measuring is true, PPI's are being saved
    def add_bpm_value(self, steps):
        # Calculate bpm: 60 seconds / number of frames between peaks * 0.004 seconds
        bpm = round(60 / (steps * 0.004))
        # Check if the bpm is realistic
        if self.MIN_BPM < bpm < self.MAX_BPM:
            # get the previous value if it exists and add new
            prev = 0
            if not self.bpms.empty():
                prev = self.bpms.get()
            self.bpms.put(bpm)
            data = self.bpms.get_data()
            # Calculate average bpm ignoring false values
            self.average_bpm = calculate_average(data, self.FILTER, self.FILTER, bpm)
            # Check if the pulse is stable enough
            # This math is spaghetti but works, I guess
            self.is_measuring = (abs(bpm - prev) + (max(data) - min(data)) * 1.5) / 2.5 < self.FILTER
            # Reset timer and ppi's if pulse is not stable
            if not self.is_measuring or self.timer == 0:
                self.timer = utime.ticks_ms()
                self.ppis = []
        else:
            self.is_measuring = False
            
            
    # Saves PPI's in array
    # Once it's full, send the data to kubios after filtering false values
    # (Partially written by ChatGPT)
    def add_ppi(self, steps):
        # Add ppis once a steady pulse has been found
        if self.is_measuring:
            # Multiply 4ms to get ppi
            self.ppis.append(steps * 4)
            # Once the list is filled or when max time have passed with steady pulse
            # Filter out false values and send it to kubios
            if len(self.ppis) >= self.max_size or utime.ticks_ms() - self.timer > self.max_time:
                # Sort the data
                sorted_ppis = sorted(self.ppis)
                
                # Calculate the quartiles
                q1_index = int(len(sorted_ppis) * 0.15)
                q3_index = int(len(sorted_ppis) * 0.85)
                q1 = sorted_ppis[q1_index]
                q3 = sorted_ppis[q3_index]
                
                # Calculate the interquartile range
                iqr = q3 - q1
                
                # Calculate the reasonable range for heart rates
                lower_bound = q1 - (1.5 * iqr)
                upper_bound = q3 + (1.5 * iqr)
                
                # Exclude any outliers using filter
                filtered_ppis = list(filter(lambda x: x >= lower_bound and x <= upper_bound, self.ppis))
                
                self.send_data(filtered_ppis)
                
    # Send data to kubios and backend
    # Then display them on oled
    def send_data(self, data):
        # print the data for debugging
        print("sending: ", data)
        # Update oled screen
        self.is_touching("sending...")
        # Fetch token
        token = kubios.get_access_token()
        # Fetch data
        result = kubios.analyze_hrv(data, token)
        # Save relevant data
        self.sns = result['analysis']['sns_index']
        self.pns = result['analysis']['pns_index']
        self.bpm = int(result['analysis']['mean_hr_bpm'])
        # Format the relevant data and send it to backend
        hr_dict = {"bpm":self.bpm,
                   "sns":self.sns,
                   "pns":self.pns}
        print(hr_dict)
        #self.connection.post("http://192.168.105.93:5000/data", hr_dict) # Samu
        #self.connection.post("http://192.168.105.166:5000/data", hr_dict) # Arman
        #self.connection.post("http://192.168.105.13:5000/data", hr_dict) # server
        print("complete: ", result)
        self.is_done = 1
    
    # Show the bpm on screen
    def show_bpm(self):
        self.show_text("BPM: " + str(self.average_bpm) + "  <3", self.text_onscreen[0][0], 32)
        self.text_onscreen[0] = ["BPM: " + str(self.average_bpm) + "  <3", 32]
    
    # Show text below the bpm
    def is_touching(self, text):
        self.show_text(text, self.text_onscreen[1][0], 42)
        self.text_onscreen[1] = [text, 42]
    
    # Show final results fetched from kubios
    def show_final_results(self):
        self.oled.fill(0)
        self.oled.text("Your HRV data:", 0, 0)
        self.oled.text("BPM: " + str(self.bpm), 0, 30)
        self.oled.text("SNS: " + str(self.sns), 0, 40)
        self.oled.text("PNS: " + str(self.pns),0, 50)
        self.oled.show()
        
        
    # Delete old text and then show new text on screen 
    def show_text(self, value, oldvalue, pos):
        self.oled.text(oldvalue, 0, pos, 0)
        self.oled.text(value, 0, pos)
        self.oled.show()
    
    # reset
    def reset(self):
        self.average_bpm = 0
        self.bpms = Fifo(13)
        self.ppis = []
        self.is_done = 0
        self.timer = 0
        print("juttu")
    
    def get_bpm(self):
        return self.average_bpm
        
# Pins
adc = ADC(Pin("GP27"))
led = Pin("LED", Pin.OUT)
restart = Pin("GP12", Pin.IN, Pin.PULL_DOWN)
restart.irq(handler = restart, trigger = Pin.IRQ_RISING)

# wifi
connection = Wifi()
connection.connect()

# Instance of data manager
data_manager = DataManager(connection)
data_manager.show_bpm() # Just to show something in the beginning
# Instance of BeatHandler
beat_calc = BeatHandler(data_manager) 

# Buffer containing the raw data collected
buffer = Fifo(375)
# Smaller buffer used to get average
avg_buffer = Fifo(100)
lag = 0

# Average of avg_check_data. When inside the min&max diff, the value can be valid
avg = 0
# Difference. When inside the min&max, the value can be valid
diff = 0

# Used for filtering data
MIN_AVG = 12000
MAX_AVG = 50000
MAX_DIFF = 24000

# If a finger is detected
is_counting = 0
# Last state of the finger check (prevents unnessesary calls to draw OLED-screen)
last_state = 1
# Last bpm that was recorded (prevents unnessesary calls to draw OLED-screen) 
last_bpm = 0
# When 0, final values are displayed and this prevents them being drawn multiple times
is_active = 1

# Piotimer
SAMPLE_RATE = 250
timer = Piotimer(mode = Piotimer.PERIODIC, freq = SAMPLE_RATE, callback=check_pulse)

# main loop
while True:
    if buffer.empty():
        continue
    if data_manager.is_done == 0:
        lag = buffer.dropped()       # Get the dropped value (used to counteract lag from calculations)
        buffer.dc = 0                # Reset the dropped value
        raw_value = buffer.get()     # Get the raw value from buffer
        # Calculate avgerage
        avg_buffer.put(raw_value)
        avg = calculate_average(avg_buffer.get_data(), MAX_DIFF, MAX_DIFF, avg_buffer.get())  
        diff = buffer.get_max() - buffer.get_min()
        
        # Check if a finger is on the sensor
        if MIN_AVG < avg < MAX_AVG and diff < MAX_DIFF:
            # If a new bpm is detected, display it
            if last_bpm != data_manager.get_bpm():
                data_manager.show_bpm()
                last_bpm = data_manager.get_bpm()
            
            # Send values to calculate bpm
            beat_calc.process_beat(raw_value, buffer.get_min(), buffer.get_max(), lag)
            
            is_counting = 1
        else:
            is_counting = 0
        
        # Update the status to OLED-screen
        if is_counting == 1 and last_state == 0:
            data_manager.is_touching("calculating...")
            last_state = 1
        elif is_counting == 0 and last_state == 1:
            data_manager.is_touching("not detected...")
            last_state = 0
            
    elif is_active == 1:
        data_manager.show_final_results()
        is_active = 0

