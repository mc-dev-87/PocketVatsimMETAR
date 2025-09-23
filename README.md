# PocketVatsimMETAR

PocketVatsimMETAR is a lightweight, always-on desktop application designed for vATC on the VATSIM. It provides real-time METAR and ATIS information directly on your screen. With its minimalist, ATC-style interface, the app is a perfect, non-intrusive tool for staying up-to-date with current weather conditions without switching windows.

<img width="143" height="307" alt="image" src="https://github.com/user-attachments/assets/1ed5070d-dd27-4ba1-8dfa-a7c199d2ca54" />

## Features

- Fetches METAR data every 30 minutes from the VATSIM network.
- Fetches ATIS data every 5 minutes from the VATSIM network.
- Colored dots show the flight category (VFR, SVFR, IFR).
- Left-click on any airport to view the full METAR details.
- Right-click on the app to drag it.
- Press the Esc key to close the app.

## Configuration File

> [!NOTE]
> The application can be customized using a **config.json** file. This is an optional file that must be placed in the same directory as the **PocketVatsimMETAR.exe** file. If the file is not found, the application will run with default settings.

You can use it to modify the following:

- List of airports: Change the ICAO codes and their grouping.
- Dot colors: Customize the colors for VFR, SVFR, and IFR categories.
- Font: Adjust the font family and size to your preference.

## How to Use
- Download the latest .exe file from the Releases page.
- Customize config.json (must be placed in the same directory as the PocketVatsimMETAR.exe file)

> [!IMPORTANT]
> This application is signed with a self-signed certificate to verify its authenticity. When you first run the app, Windows may display a SmartScreen warning. You can safely bypass this warning by clicking "More info" and then "Run anyway".
