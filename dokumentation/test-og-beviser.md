# Test og beviser

| Prøve | Resultat | Bilag |
| --- | --- | --- |
| Fysisk OSPF efter kabelbrud, 26. november | R1 mistede R2 og ruten til VLAN 30. Begge kom tilbage på samme link. Fra linket kom op, til naboskabet var `FULL`, gik der 9,380 sekunder. | [R1-konsol før, under og efter](beviser/ospf-brudproeve.png) |
| Trunks og OSPF | Cisco-udskrifter viser VLAN på switchens trunks og OSPF-ruter på routerne. | [S1 trunks](beviser/s1-trunks.txt) · [R1 ruter og NAT](beviser/r1-ruter-og-nat.txt) · [R2 OSPF](beviser/r2-ospf.txt) |
| Negativ forbindelse mellem VLAN | Windows B i VLAN 30 fik timeout mod Ubuntu i VLAN 20 på TCP 443. Ingen matchende loglinje for selve denne prøve blev bevaret. | [Klientudskrift](beviser/vlan30-til-vlan20.txt) |
| Ubuntu HTTPS og SSH | Tilladt HTTPS gav HTTP 200 med certifikatkontrol. Ubuntu loggede port 22 og 443 blokeret fra testkilden. Nøglelogin bestod den 26. november, mens adgangskode og direkte root-login blev afvist. | [UFW SSH](beviser/ufw-ssh.txt) · [UFW HTTPS](beviser/ufw-https.txt) · [Kontrol af SSH-politik](#ssh-politik) |
| Fysiske ture | Én tur til hver station sluttede med stations-ACK og HOME. Begge tur-ID’er fandtes lokalt og centralt. Hjemmesiden viste også temperatur og fugt. | [UART og HTTP](beviser/ture.txt) · [HTTPS og statistik](beviser/hjemmeside-api.txt) |
| Backup og restore | Efter gendannelse af den daglige backup gav `COUNT(*)` **9 ture og 241 målinger**, med samme statusfordeling som dumpet. | [SQL og udskrift](beviser/gendannelse.txt) |
| Programmering | [Pytest](../lokalserver/README.md#kør-tests) prøver API, PostgreSQL og UART. Hardware og netværk afprøves fysisk. | [Testfiler](../lokalserver/) |
| Netværksmodel | Cisco Packet Tracer viser VLAN, OSPF og forbindelserne. ESP-NOW og USB/UART er angivet som forbindelser i modellen. | [Packet Tracer](../projektfiler/netvaerk/Medirover.pkt) |

## SSH-politik

Den 26. november bestod syntaxkontrollen `sshd -t` på Ubuntu. Efter genindlæsning viste den effektive konfiguration `PubkeyAuthentication yes`, `PasswordAuthentication no`, `KbdInteractiveAuthentication no` og `PermitRootLogin no`. En ny SSH-session fra betjenings-pc'en returnerede `soren` med nøglelogin. Forsøg med adgangskode, keyboard-interactive og direkte root-login gav afvisning.

De fysiske målinger stammer fra det monterede testanlæg. Firmwareændringer og kodeoprydning på GitHub kan have en nyere revision end udstyret ved disse prøver.

## Kontrol af afleveringsversionen

Den 27. november bestod alle 20 pytest-prøver med en separat PostgreSQL-instans. Backupmodtageren gemte en PostgreSQL-dump byte for byte og afviste forkert SHA-256, forkert længde og ugyldigt hoved. nginx-konfigurationen bestod `nginx -t`. Bash-scripts og JavaScript bestod deres syntaksprøver. Firmwarekoden blev sammenlignet med udgangspunktet, og kun forklaringerne i koden blev ændret.
