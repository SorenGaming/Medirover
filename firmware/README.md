# Firmware til ESP32

Hver enhed kører MicroPython med `espnow`. Kopiér den relevante `main.py` til enhedens rodmappe.

| Enhed | Program |
| --- | --- |
| Bil | [`bil/main.py`](bil/main.py) |
| Base | [`base/main.py`](base/main.py) |
| Station 1 | [`station1/main.py`](station1/main.py) |
| Station 2 | [`station2/main.py`](station2/main.py) |

Basen er USB/UART-forbindelsen til Ubuntu. Bil og base læser lågkontakten på GPIO 13 i den nyeste firmware. Se de øvrige pin-numre og kalibreringsværdier i den relevante `main.py`. KiCad-filerne dokumenterer deres angivne skemarevisioner.

[Se UART-protokollen](../dokumentation/uart.md) · [Åbn elektronikfilerne](../projektfiler/elektronik/)
