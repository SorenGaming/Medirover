# Medirover

**3. semester · IT-teknolog · gruppe 3B10 · Søren og Isak**

Medirover er en prototype, der transporterer en lukket pakke med attrapmedicin fra en base til én af to stationer. Betjeningen foregår i en browser. Ubuntu gemmer ture og målinger i PostgreSQL og sender kommandoer over USB til basens ESP32. Basen, bilen og stationerne kommunikerer via ESP-NOW.

| Mappe | Indhold |
| --- | --- |
| [`firmware`](firmware/) | MicroPython til bil, base og de to stationer. |
| [`lokalserver`](lokalserver/) | Hjemmeside, FastAPI, UART, PostgreSQL-skema, tests og driftsscripts. |
| [`projektfiler`](projektfiler/) | Projektforslag, systemtegninger, Packet Tracer, KiCad, CAD og projektstyring. |
| [`dokumentation`](dokumentation/) | Testbeviser, netværksoversigt og guide til installation og drift. |

[Åbn projektets systemtegning](projektfiler/systemtegninger/teknisk-systemtegning.png) · [Download Packet Tracer-filen](projektfiler/netvaerk/Medirover.pkt) · [Se test og beviser](dokumentation/test-og-beviser.md)

## Prøv lokalserveren

[Start og test lokalserveren](lokalserver/README.md) beskriver Python, PostgreSQL og testkommandoer. Medirovers fysiske opsætning bruger [nginx, systemd, UFW, central synkronisering og backup](dokumentation/drift.md). Databasedata, adgangskoder og private nøgler oprettes separat på maskinerne.
