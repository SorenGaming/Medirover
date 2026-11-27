# Netværk

[Åbn Medirover.pkt](Medirover.pkt) i Cisco Packet Tracer. Modellen grupperer betjeningen og Ubuntu i LAN A og Windows B i LAN B. R1 og R2 har en separat transitforbindelse i OSPF-område 0.

| S1-port | Forbindelse | VLAN |
| --- | --- | --- |
| Gi1/0/1 | R1 G0/0 | Trunk 10, 20, 99 og 900 |
| Gi1/0/2 | Access point til betjeningen | Access 10 |
| Gi1/0/3 | Ubuntu | Access 20 |
| Gi1/0/4 | R2 G0/0 | Trunk 30 og 199 |
| Gi1/0/5 | Windows B | Access 30 |
| Gi1/0/6 | NX200 | Access 900 |
| Gi1/0/7–24 | Ubrugte porte | Parkeret i VLAN 998 og lukket |

Begge trunks bruger ubrugt native VLAN 999. Packet Tracer-modellens switch benytter Fa0-porte. R1 G0/1 og R2 G0/1 bruger henholdsvis `10.20.254.1/30` og `10.20.254.2/30`. R1's WAN-adresse er `192.168.1.254/24` med NX200 på `192.168.1.1` som standardgateway.

[Trafik og tjenester](../../dokumentation/drift.md) · [Fysiske netværksprøver](../../dokumentation/test-og-beviser.md)
