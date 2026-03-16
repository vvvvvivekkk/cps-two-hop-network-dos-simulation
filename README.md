# Transmission Scheduling for Remote State Estimation in CPS

Full-stack FastAPI project that simulates a cyber-physical system with two-hop communication under DoS attacks:

- Hop-1: Sensor -> Relay
- Hop-2: Relay -> Estimator

The estimator runs a Kalman filter while an adaptive transmission scheduler selects which sensor transmits each step.

## Features

- 5-sensor CPS simulation with process and measurement noise
- Two-hop communication manager with relay buffer
- DoS attack simulation:
  - packet drop
  - delay
  - bandwidth flood
- DoS detection based on abnormal drop and delay behavior
- Adaptive transmission scheduler based on estimation error, priority, and delivery history
- SQLite persistence for attacks, packet logs, estimation results, metrics, and sensor data
- Modern dashboard (Tailwind + Chart.js) with live updates
- Background simulation thread control through FastAPI

## Stack

- Backend: FastAPI
- Simulation: Python + NumPy + SciPy
- Estimation: Scalar Kalman Filter
- Database: SQLite
- Frontend: HTML + Tailwind CSS + JavaScript
- Charts: Chart.js

## Project Structure

- app/main.py
- app/core/database.py
- app/models/schemas.py
- app/simulation/kalman.py
- app/simulation/network.py
- app/simulation/scheduler.py
- app/simulation/engine.py
- app/static/index.html
- app/static/js/dashboard.js

## Setup

1. Create a virtual environment and activate it.
2. Install dependencies:

   pip install -r requirements.txt

3. Run server:

   uvicorn app.main:app --reload

   Important: use `app.main:app` (dot notation). Do not use `app:main:app`.

4. Open browser:

   http://127.0.0.1:8000

## API Endpoints

- POST /start_simulation
- POST /stop_simulation
- GET /network_status
- GET /attack_status
- GET /estimation_data
- GET /network_metrics
- GET /logs

## Notes

- Relay buffer default capacity is 50 packets.
- Scheduler selects the sensor with highest adaptive weighted estimation error.
- Attack profiles can be sent in /start_simulation request body.
