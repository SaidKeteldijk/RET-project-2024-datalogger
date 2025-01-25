# RET-project-2024-datalogger
 
 # Inleiding (Dutch)

Deze Github repository dient als handleiding en technische documentatie voor de hardware en software van de retourstroom module. De in informatie die in deze repository te vinden is, is bedoelt voor het technische personeel van firma Rotterdam Elektrische Tram(RET).

De retourstroom module (RSM) is een datalogger die ontwikkeld is om DC en AC stroom te meten in aardingsnetwerken van Spoorbeveiligingsruimtes in Gelijk Richter Stations van de RET. 

De functionaliteiten van de RSM zijn:

- Het uitlezen van current transducers die een 4-20mA output of 0-10V output geven.
- Het loggen van de gemeten AC of DC stroom.
- Het plotten/weergeven van de opgeslagen stroom waarde
- Het instellen van setpoints voor de alarmen van het Bedrijfsmeldsysteem (BMS) en supervisory control and data acquisition (SCADA) systeem van de RET.
- Het laten af gaan van een alarm signaal(24V signaal) bij het detecteren van een overschreiding van een van de setpoints.
- Het door sturen van de gemeten stroom waarde via een 4-20mA signaal.


# Intro (English)

This GitHub repository serves as a manual and technical documentation for the hardware and software of the return current module. The information provided in this repository is intended for the technical staff of the Rotterdam Electric Tram (RET) company.

The return current module (RSM) is a data logger developed to measure DC and AC current in grounding networks of Rail Signal Rooms at Rectifier Stations of the RET.

The functionalities of the RSM are:

- Reading current transducers that provide a 4-20mA output or 0-10V output.
- Logging the measured AC or DC current.
- Plotting/displaying the stored current values.
- Setting setpoints for the alarms of the RET's Business Alarm System (BMS) and Supervisory Control and Data Acquisition (SCADA) system.
- Triggering an alarm signal (24V signal) when a setpoint is exceeded.
- Transmitting the measured current value via a 4-20mA signal.

The English translated documentation of this page can be found below the dutch documentation.

![alt text](RSM-module.jpg)

# De elektronica 

De elektronica van de RSM bestaat uit een Raspberry Pi 4B, een door de RET ontwikkelde Raspberry Pi HAT en een Raspberry Pi touch 7 display.

![alt text](Eletronics-assembly.jpg)

De pinout(bekabelingsschema) voor de module is hier onder te vinden. De module is in staat om op een DC spanning van 6V tot 50V te werken en ver bruikt gemiddeld 400mA. 

![alt text](Pinout.png)

De Raspberry Pi HAT is opgebouwd uit de volgende units:
- Buckconverter om de ingangsspanning om te zetten naar een voedingsspanning van 5VDC.
- Een Boostconverter om de juiste spanning aan te bieden voor de alarmen voor het BMS en SCADA systeem.
- Een 4 kanaals relais unit om een hoog signaal (24V) of laag signaal(0V) door te geven aan het BMS of SCADA systeem.
- Een ADC module die een current transducer sensor kan uitlezen die een 4-20mA of 0-10V uitgangssignaal heeft.
- Een 4-20mA output loop generator


# De software

De software die op de Raspberry Pi 4B van de RSM draait is als volgt opgebouwd. Voor het besturingssysteem wordt er een Linux kernel gebruikt (Rasberry OS). 
Hierin wordt er een virtuele omgeving opgebouwd in python, in deze virtuele omgeving (VM) wordt de Python app opgestart die alle elektronica bestuurd en de grafische interface beheert.
De Python source code is te vinden in "RET-project-2024-datalogger > src > main.py".

Voor het starten van de Python app met VENV (Virtual Environment) zijn de volgende command's nodig. Deze commando's ingevuld te worden in de terminal van Linux:

- cd Desktop/App
- source myenv/bin/activate << start de VENV
- python3 systemtest.py  << start de App


![alt text](Software-setup.png)


# Software buggs 

Er staan nog een aantal bugs(software fouten die niet destructief zijn voor de melding van de gehele module ) in de Python code van de RSM module. 

De bugs zijn:

- De update functie voor weergeven van de actuele stroom in Ampere verdwijnt als er naar een andere pagine wordt genavigeerd. Maar de alarm en log functies blijven wel werken.

- Bij het genereren van log.csv bestanden wordt de actuele datum niet meegegeven het wordt dan log(1).csv.

- Er is nog geen functie om een sensor met een 0-10V uitgang in te lezen.

- De pyplot functie werkt, maar zorgt wel voor een grafiek die soms een vertekend beeld geeft.

- De setpoints(grenswaardes) voor BMS en SCADA blijven niet bewaard als de RSM wordt restart of als de module niet plots geen spanning meer heeft.

