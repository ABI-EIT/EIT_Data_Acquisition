# EIT Data Acquisition App

## Installation

To install the app, first obtain the source code, for example by cloning the public github repository:
```
$ git clone git://github.com/ABI-EIT/EIT_Data_Acquisition.git
```
Once you have a copy of the source, you can install it with:

```
$ python -m venv venv
$ .\venv\Scripts\activate
$ pip install -e .
$ python -m eit_data_acquisition --install
```

This will create a folder named eit_app in your working directory which contains the app installation.

Run eit_app\main\main.exe to run the program.

## Usage
1.	Connect EIT electronics module to the imaging domain (human subject or phantom) via the electrode connection header.
2.	Connect EIT electronics module to the table computer via a USB cable.
3.	Open the EIT app and select the appropriate COM port of the electronics module from the Device Name dropdown menu. Data will begin streaming to the app.
4.	Use the Set Background button to set the current measurement frame as the background for time difference EIT reconstruction.
5.	Use the Record Data button to record streaming data to a file. 

