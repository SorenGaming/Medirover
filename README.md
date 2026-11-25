# Medirover

Skoleprojekt om en prototype til transport af attrapmedicin fra en base til to stationer. Ubuntu kører lokalserveren. Windows bruges til betjening, og den planlagte centrale database og backup ligger på en anden maskine.

`lokalserver/` indeholder FastAPI, PostgreSQL-skema og læsning af kvitteringer fra basen via USB/UART. API’et gemmer bestillinger og holder højst én tur aktiv. Swagger på `/docs` bruges til udvikling og prøvebestillinger.

Til ændringer opretter Søren og Isak hver en gren og en pull request. Den anden gennemgår ændringen, før den flettes ind i `main`.
