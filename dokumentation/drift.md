# Drift på Medirover-nettet

| Maskine | Adresse | Opgave |
| --- | --- | --- |
| Betjenings-pc | `10.20.10.10` (VLAN 10) | Browser og SSH-administration. |
| Ubuntu | `10.20.20.10` (VLAN 20) | nginx, FastAPI, lokal PostgreSQL og USB til basen. |
| Windows B | `10.20.30.10` (VLAN 30) | Central PostgreSQL og modtagelse af backup. |

## Server og netværk

På Ubuntu starter systemd appen som tjenestekontoen `medirover`. Uvicorn lytter på `127.0.0.1:8000`, og nginx publicerer hjemmesiden og de nødvendige API-ruter med HTTPS. `/docs` er til lokal udvikling. UART kræver `dialout` og basens sti fra `ls /dev/serial/by-id/`. Angiv den sti og installationsmappen i [systemd-filen](../lokalserver/drift/medirover.service). Indlæs den [vedlagte nginx-konfiguration](../lokalserver/drift/nginx-medirover.conf) i det eksisterende HTTPS-serverafsnit.

UFW tillader TCP 22 og 443 til Ubuntu fra betjeningsmaskinen. SSH tillader nøglelogin og afviser adgangskode og root. Cisco R1 og R2 udveksler ruter med OSPF. R1 håndterer NAT mod 5G-routeren. Ubuntu videresender ingen trafik.

## Central database og backup

- [`sync-central.sh`](../lokalserver/drift/sync-central.sh) kører hvert femte minut og kopierer ture og målinger til `medirover_central`. Begge databaser bruger [samme grundskema](../lokalserver/schema.sql). Windows tillader PostgreSQL fra Ubuntu. Synkroniseringen bruger en særskilt databasebruger og en lokal `.pgpass` med begrænsede filrettigheder.
- [`backup.sh`](../lokalserver/drift/backup.sh) bruger `pg_dump` dagligt kl. 12. Dumpet sendes via SSH til en fast modtagerkommando på Windows. Efter bekræftet modtagelse opdateres tidspunktet i historikfanen.
- [`modtag-backup.ps1`](../lokalserver/drift/modtag-backup.ps1) er en selvstændig modtager til samme format. Den validerer størrelse og SHA-256, før filen navngives som en færdig backup. Angiv den som den faste kommando for backupnøglen ved en ny opsætning. Opret arbejdsmappe og kendte værtsnøgler, før afsenderen aktiveres.
- [Gendannelsesprøven](beviser/gendannelse.txt) blev kørt i en særskilt PostgreSQL-instans med egen testdatabase.

[Netværksmodel](../projektfiler/netvaerk/Medirover.pkt) · [Resultater fra det fysiske net](test-og-beviser.md)
