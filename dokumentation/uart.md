# USB/UART mellem Ubuntu og basen

Basen sender og modtager ASCII-linjer ved 115.200 baud. Hver linje slutter med LF. En tur identificeres med sit UUID. Serverens læsetråd sorterer svar og hændelser efter deres type og tur-ID.

| Kommando fra server | Funktion |
| --- | --- |
| `ORDER,<id>,<1 eller 2>` | Bestil til den valgte station. Bilen skal være i basen. |
| `KLAR,<id>` | Pakken er klar til afgang. |
| `STOP,<id>` | Stop turen. |
| `FORTSAET,<id>` | Fortsæt en tur efter en fejl. |
| `LUK,<id>` | Afslut en stoppet tur. |

Basen svarer `OK,<id>` eller `NAK,<id>,<grund>`. Serveren venter højst tre sekunder på svaret. Basens hændelser `STARTED`, `ACK`, `HOME` og `ERR` opdaterer turen i databasen. `ACK` er stationens kvittering. `HOME` markerer en fuldført tur.

Målingen sendes som `TEMP,rover,<°C>,<%RH>`. Luftfugtighed er valgfri for at bevare kompatibilitet med ældre rammer. Tiden registreres ved modtagelsen på Ubuntu, og siden markerer en måling som forældet efter to minutter.

[Serverens parser](../lokalserver/uart.py) · [Basens program](../firmware/base/main.py)
