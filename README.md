# stepbound-be

Il backend di [Stepbound](https://github.com/Vanni-broUser/stepbound-github):
riceve da solo, senza che il giocatore debba condividere nulla, i **rapporti
di errore** del gioco e gli **eventi di gioco anonimi**, e risponde alle
domande su come si gioca: quanti giocano, quali livelli completano, quali
zombi uccidono, dove muoiono.

Flask 3, SQLAlchemy 2 (Flask-SQLAlchemy, migrazioni con Flask-Migrate/Alembic),
Postgres 16, Gunicorn.

Lato app: `lib/report/telemetry.dart` e `docs/telemetry.md` nel repository
del gioco. Il gioco non ha bisogno della rete: offline accoda sul telefono
(con limiti di età e dimensione) e invia al primo avvio online.

## Avvio in locale

```bash
cp .env.example .env          # e cambia le chiavi
docker compose up --build     # API su http://localhost:8000, Postgres incluso
curl localhost:8000/healthz
```

Senza Docker:

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
export $(grep -v '^#' .env | xargs)   # DATABASE_URL, INGEST_KEY, …
export FLASK_APP=wsgi.py
flask db upgrade
flask run
```

## Test

Girano su un Postgres vero (le query usano JSONB e `ON CONFLICT`):

```bash
createdb stepbound_test
TEST_DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/stepbound_test python -m pytest -q
```

La CI GitHub (`.github/workflows/ci.yml`) fa lo stesso con un servizio
Postgres, e controlla che le migrazioni corrispondano ai modelli
(`flask db check`).

## Configurazione

Tutto da variabili d'ambiente, descritte in `.env.example`:

| Variabile | A cosa serve |
| --- | --- |
| `DATABASE_URL` | Postgres, driver psycopg 3 |
| `INGEST_KEY` | chiave che l'app manda in `X-Stepbound-Key` (= `STEPBOUND_TELEMETRY_KEY` del gioco); è nell'APK, tiene fuori il traffico a caso |
| `PLAYER_ID_PEPPER` | segreto per l'HMAC degli id di installazione: nel database non finisce mai l'id che conosce il telefono. Non cambiarlo |
| `ADMIN_TOKEN` | token Bearer per le statistiche e i rapporti |
| `INGEST_RATE_LIMIT`, `RATELIMIT_STORAGE_URI` | limite di richieste per indirizzo; con più worker usa `redis://…` |
| `TRUSTED_PROXIES` | quanti reverse proxy stanno davanti (per l'indirizzo del client) |
| `EVENT_RETENTION_DAYS`, `REPORT_RETENTION_DAYS` | conservazione, 395 e 180 giorni come da informativa privacy |

L'app si avvia solo se le tre chiavi sono impostate.

## API

### Dall'app (`X-Stepbound-Key`)

`POST /v1/ingest`: quello che il telefono aveva in coda.

```json
{
  "installId": "3f2a…(16-64 caratteri, casuale)",
  "app": {"version": "0.1.0 (402)", "commit": "abc123", "platform": "android",
          "os": "Android 11 (SDK 30)", "model": "Xiaomi Redmi 9"},
  "events": [{"id": "<uuid>", "type": "zombie_killed", "at": "2026-09-30T12:00:00Z",
              "session": "<uuid>", "data": {"level": "hometown", "place": "Porto", "kind": "brute"}}],
  "reports": [{"id": "<uuid>", "at": "…", "source": "async",
               "summary": "Bad state: …", "text": "RAPPORTO DI ERRORE DI STEPBOUND…"}]
}
```

Risponde `200 {"stored": {"events": n, "reports": m, "duplicates": d}}`.
L'invio è *at-least-once*: un evento o rapporto con un id già visto viene
ignorato, così un blocco reinviato dopo una risposta persa non si duplica.
`400` corpo non valido, `401` chiave sbagliata, `413` oltre 1 MB, `429`
troppe richieste. Limiti: 500 eventi e 5 rapporti per richiesta, 4 KB di
`data` per evento, 256 KB per rapporto. Un evento con una data fuori da
[-120 giorni, +1 giorno] (orologio del telefono sbagliato) prende la data
di arrivo.

`POST /v1/forget` `{"installId": "…"}`: il giocatore ha spento l'invio;
cancella il giocatore e, a cascata, tutti i suoi eventi e rapporti.

### Lettura (`Authorization: Bearer $ADMIN_TOKEN`)

Tutte accettano `?days=N` (default 30, max 400).

| Endpoint | Cosa dice |
| --- | --- |
| `GET /v1/stats/overview` | giocatori totali, nuovi e attivi, attivi per giorno, sessioni, durata media, ore giocate, piattaforme, versioni |
| `GET /v1/stats/levels` | per livello: giocatori che l'hanno iniziato e completato, tasso di completamento, morti, medie di zombi uccisi, zaini, ricordi, passi, minuti |
| `GET /v1/stats/zombies` | uccisioni per tipo di zombi, e quali tipi uccidono Mario |
| `GET /v1/stats/places` | quanti giocatori raggiungono ogni posto (dove si fermano), e dove si muore |
| `GET /v1/stats/events` | conteggio grezzo per tipo di evento |
| `GET /v1/errors` | i bug, dal più frequente: rapporti raggruppati per impronta, con giocatori colpiti, prima e ultima volta, versione |
| `GET /v1/errors/<id>` | un rapporto intero (`?format=text` per il testo così com'è, da caricare come salvataggio e riprodurre) |

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" "https://…/v1/stats/levels?days=7"
```

L'impronta di un errore (`stepbound_be/fingerprint.py`) è la sorgente, la
prima riga con numeri e stringhe oscurati, e i primi frame dello stack in
`package:stepbound/`: lo stesso bug con indici diversi è un gruppo solo.

`GET /healthz` controlla anche il database.

## Dati e privacy

- Nessuna tabella contiene IP, nomi, email o l'id di installazione: i
  giocatori sono un HMAC-SHA256 di un id casuale generato dall'app.
- L'indirizzo IP vive solo nei contatori del rate limit.
- `flask purge` cancella eventi e rapporti oltre la conservazione e i
  giocatori rimasti senza dati: va pianificato **ogni giorno** (cron, timer
  systemd o lo scheduler dell'hosting), perché l'informativa privacy del
  gioco lo promette.

## Deploy

L'immagine Docker applica le migrazioni all'avvio e serve con Gunicorn
sulla porta 8000. Davanti serve un reverse proxy **HTTPS** (Caddy, nginx o
il bilanciatore dell'hosting): iOS non accetta HTTP in chiaro. Poi, nel
progetto GitLab del gioco, le variabili protette `STEPBOUND_TELEMETRY_URL`
(l'URL pubblico) e `STEPBOUND_TELEMETRY_KEY` (= `INGEST_KEY`).

## Struttura

```
stepbound_be/
  __init__.py      create_app, /healthz
  config.py        impostazioni dall'ambiente
  models.py        Player, GameEvent, ErrorReport
  validation.py    lettura e controllo del corpo di /v1/ingest
  ingest.py        /v1/ingest, /v1/forget
  stats.py         /v1/stats/*, /v1/errors
  fingerprint.py   raggruppamento dei rapporti
  anonymize.py     HMAC degli id
  cli.py           flask purge
migrations/        Alembic
tests/             pytest su Postgres
```
