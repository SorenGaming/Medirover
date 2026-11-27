# Lokalserver

| Fil | Opgave |
| --- | --- |
| [`app.py`](app.py) | FastAPI, turkommandoer og behandling af svar fra basen. |
| [`dashboard.py`](dashboard.py) | Historik, stationsstatistik og målinger fra PostgreSQL. |
| [`uart.py`](uart.py) | Læser og validerer svar fra basen. |
| [`schema.sql`](schema.sql) | Ture, temperatur, fugt og databasebegrænsninger. |
| [`static/`](static/) | Hjemmesidens HTML, CSS og JavaScript. |
| [`drift/`](drift/) | nginx, systemd, central synkronisering og backup. |

## Kør på Linux

Kør fra mappen `lokalserver` med en PostgreSQL-bruger, der kan oprette en lokal database. Der bruges en tom udviklingsdatabase i eksemplet.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
createdb medirover_dev
psql -X -v ON_ERROR_STOP=1 -d medirover_dev -f schema.sql
MEDIROVER_DATABASE_DSN='dbname=medirover_dev' \
  .venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Åbn [hjemmesiden](http://127.0.0.1:8000/) eller [Swagger](http://127.0.0.1:8000/docs) lokalt. Tilslut basen og angiv `MEDIROVER_UART_PORT` for at sende en fysisk ordre. [UART-protokol](../dokumentation/uart.md) · [Projektets drift](../dokumentation/drift.md)

## Kør tests

Angiv en særskilt PostgreSQL-testdatabase. Testbrugeren skal kunne oprette midlertidige skemaer i den.

```bash
.venv/bin/python -m pip install -r requirements-test.txt
createdb medirover_test
MEDIROVER_TEST_DSN='dbname=medirover_test' .venv/bin/python -m pytest -q
```

Uden `MEDIROVER_TEST_DSN` springer pytest de databaseafhængige prøver over. Testene af UART og turforløb bruger en efterligning af basen, så bilen står stille.
