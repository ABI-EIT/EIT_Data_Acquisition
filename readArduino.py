import csv
import time
import matplotlib.pyplot as plt
import serial


i = 0

ser = serial.Serial('COM10', 115200)
ser.close()
ser.open()
ser.flushInput()

# Data saving
fieldnames = ['Time', 'Flow1', 'Flow2' ]
timestr = time.strftime("%Y%m%d-%H%M%S")

while True:
        data = ser.readline()
        # decoded_data = data.decode()
        try:
            decoded_data = float(data[0:len(data) - 2].decode("utf-8")) # Convert to numeric data
        except ValueError:
            continue
        print(decoded_data)

        # Save Data
        with open(timestr + ".txt", "a") as csv_file:
               writer = csv.writer(csv_file, delimiter=",")
               if i == 0:
                        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                        writer.writeheader()
               else:
                        writer.writerow([serial.time.time(), decoded_data])

        i += 1
