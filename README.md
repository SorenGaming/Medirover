# Medirover

Skoleprojekt om en prototype til transport af attrapmedicin fra en base til to stationer. Ubuntu kører lokalserveren. Windows bruges til betjening, og den planlagte centrale database og backup ligger på en anden maskine.

`lokalserver/` indeholder FastAPI, PostgreSQL-skema og læsning af kvitteringer fra basen via USB/UART. API’et gemmer bestillinger og holder højst én tur aktiv. Swagger på `/docs` bruges til udvikling og prøvebestillinger.

Hjemmesiden viser turhistorik, afsluttede ture pr. station og seneste måling af temperatur og relativ luftfugtighed. Se `lokalserver/LAES_MIG.txt` for start, UART-format og test. Sensorvisningen afventer målinger fra den fysiske boks.

`esp32/` indeholder MicroPython-programmerne (`main.py`) til bilen, basen og de to stationer. De taler sammen med ESP-NOW, og basen sidder på Ubuntu via USB/UART (protokollen står i `lokalserver/LAES_MIG.txt`). Bilens kalibrering fra autotune 23/11 står direkte i `esp32/bil/main.py`.

Til ændringer opretter Søren og Isak hver en gren og en pull request. Den anden gennemgår ændringen, før den flettes ind i `main`.
