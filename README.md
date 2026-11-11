# Sensor Ops

Local Python service for tracing voltage measurements from a simulated device. It distinguishes missing readings from low readings, detects duplicate submissions, and reports the latest device state.

**Data path:** CSV replay → HTTP JSON → validation → SQLite → per-device summary.

## Run locally

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:local_app --factory --host 127.0.0.1
```

In a second terminal in the same folder:

```sh
source .venv/bin/activate
python replay.py
curl -s http://127.0.0.1:8000/devices/bench-1/summary
python replay.py
python -m unittest discover -s tests -v
```

The first replay records five rows: two normal, two above the threshold, one sensor fault. The second replay reports duplicates and does not change the counts. Open http://127.0.0.1:8000/docs to try the API.

## Design decisions

- Integer millivolts keep the threshold test exact. 2,800 mV is inclusive.
- A null reading means sensor fault. An out-of-range input is rejected instead of being stored.
- A device sequence is unique. An identical retry is accepted; reuse with a different payload returns HTTP 409. SQLite enforces uniqueness even with concurrent requests.
- Latest means highest device sequence, not the last HTTP request. Devices must retain their sequence across restarts or use a new device ID.
- This is a local prototype: synthetic data, no authentication and no direct hardware connection. Keep it on loopback. The API classifies individual samples; the companion firmware implements a stateful alarm, so its output can intentionally differ.

To pair with the companion C simulator, run its `make all` and `./demo > /tmp/firmware-demo.csv` and pass that file to `python replay.py`. Run against a fresh database or use a new device ID when importing a different dataset.
