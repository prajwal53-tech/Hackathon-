import asyncio
import json
import math
import random
import time
from datetime import datetime
from typing import Dict, List, Optional

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel


logger = structlog.get_logger()
app = FastAPI(title="Smart Bus Optimization API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Data Models ---
class Stop(BaseModel):
    id: str
    name: str
    lat: float
    lon: float


class Route(BaseModel):
    id: str
    name: str
    stops: List[str]


class BusState(BaseModel):
    id: str
    route_id: str
    lat: float
    lon: float
    speed_kmh: float
    next_stop_id: Optional[str]
    eta_next_stop_s: Optional[int]


class TicketEvent(BaseModel):
    ts: float
    route_id: str
    stop_id: str
    count: int


class ScheduleEntry(BaseModel):
    route_id: str
    stop_id: str
    planned_time: float
    optimized_time: Optional[float] = None


# In-memory stores
STOPS: Dict[str, Stop] = {}
ROUTES: Dict[str, Route] = {}
BUSES: Dict[str, BusState] = {}
SCHEDULE: List[ScheduleEntry] = []


# --- Bootstrap synthetic network ---
def bootstrap_network() -> None:
    global STOPS, ROUTES, BUSES, SCHEDULE

    center_lat, center_lon = 37.7749, -122.4194
    radius_deg = 0.03

    # Create 8 stops on a circle
    STOPS = {}
    for i in range(8):
        theta = 2.0 * math.pi * (i / 8.0)
        lat = center_lat + radius_deg * math.sin(theta)
        lon = center_lon + radius_deg * math.cos(theta)
        STOPS[f"S{i}"] = Stop(id=f"S{i}", name=f"Stop {i}", lat=lat, lon=lon)

    route_a = Route(id="R1", name="Route 1", stops=[f"S{i}" for i in range(8)])
    route_b = Route(id="R2", name="Route 2", stops=[f"S{i}" for i in range(7, -1, -1)])
    ROUTES = {route_a.id: route_a, route_b.id: route_b}

    # Seed two buses
    BUSES = {
        "B1": BusState(
            id="B1",
            route_id="R1",
            lat=STOPS["S0"].lat,
            lon=STOPS["S0"].lon,
            speed_kmh=25.0,
            next_stop_id="S1",
            eta_next_stop_s=60,
        ),
        "B2": BusState(
            id="B2",
            route_id="R2",
            lat=STOPS["S4"].lat,
            lon=STOPS["S4"].lon,
            speed_kmh=22.0,
            next_stop_id="S3",
            eta_next_stop_s=60,
        ),
    }

    # Create simple rolling schedule for each stop
    now = time.time()
    SCHEDULE = []
    for route in ROUTES.values():
        for idx, stop_id in enumerate(route.stops):
            base_time = now + idx * 120
            for k in range(12):  # next ~2 hours at 10 min interval
                SCHEDULE.append(
                    ScheduleEntry(route_id=route.id, stop_id=stop_id, planned_time=base_time + k * 600)
                )


bootstrap_network()


# --- Simple EWMA forecaster per (route, stop) ---
EWMA_STATE: Dict[str, float] = {}
ALPHA = 0.3


def update_ewma(key: str, value: float) -> float:
    previous_value = EWMA_STATE.get(key, value)
    new_value = ALPHA * value + (1 - ALPHA) * previous_value
    EWMA_STATE[key] = new_value
    return new_value


# --- Rule-based scheduler ---
def optimize_schedule(now_ts: float) -> None:
    for entry in SCHEDULE:
        key = f"{entry.route_id}:{entry.stop_id}"
        forecast = EWMA_STATE.get(key, 8.0)
        if forecast > 15:
            entry.optimized_time = max(now_ts, entry.planned_time - 180)  # advance by up to 3 min
        elif forecast < 5:
            entry.optimized_time = entry.planned_time + 60  # small delay to smooth
        else:
            entry.optimized_time = entry.planned_time


# --- Simulators ---
async def gps_simulator() -> None:
    while True:
        for bus in BUSES.values():
            route = ROUTES[bus.route_id]
            stops = route.stops
            try:
                target_index = stops.index(bus.next_stop_id) if bus.next_stop_id in stops else 0
            except ValueError:
                target_index = 0
            next_stop = STOPS[stops[target_index]]

            # Move 20% toward target stop each tick
            bus.lat += (next_stop.lat - bus.lat) * 0.2
            bus.lon += (next_stop.lon - bus.lon) * 0.2
            bus.eta_next_stop_s = max(5, int((bus.eta_next_stop_s or 60) * 0.85))

            # If we are very close to the stop, snap to it and target next
            if abs(bus.lat - next_stop.lat) < 1e-4 and abs(bus.lon - next_stop.lon) < 1e-4:
                bus.lat = next_stop.lat
                bus.lon = next_stop.lon
                next_index = (target_index + 1) % len(stops)
                bus.next_stop_id = stops[next_index]
                bus.eta_next_stop_s = 60

        await asyncio.sleep(1)


async def ticket_simulator(event_queue: asyncio.Queue) -> None:
    rng = random.Random()
    while True:
        route = random.choice(list(ROUTES.values()))
        stop_id = random.choice(route.stops)

        # Simple time-of-day effect
        hour = datetime.utcnow().hour
        base = 6 if hour < 6 else (16 if 7 <= hour <= 9 or 16 <= hour <= 18 else 10)
        count = max(0, int(rng.gauss(mu=base, sigma=3)))

        event = TicketEvent(ts=time.time(), route_id=route.id, stop_id=stop_id, count=count)
        key = f"{route.id}:{stop_id}"
        update_ewma(key, float(count))

        await event_queue.put({"type": "ticket", "data": event.model_dump()})
        await asyncio.sleep(2)


async def scheduler_loop(event_queue: asyncio.Queue) -> None:
    while True:
        now_ts = time.time()
        optimize_schedule(now_ts)
        avg_forecast = float(sum(EWMA_STATE.values()) / len(EWMA_STATE)) if EWMA_STATE else 0.0
        await event_queue.put({"type": "schedule_opt", "data": {"ts": now_ts, "avg_forecast": avg_forecast}})
        await asyncio.sleep(5)


async def buses_broadcast_loop(event_queue: asyncio.Queue) -> None:
    while True:
        snapshot = [bus.model_dump() for bus in BUSES.values()]
        await event_queue.put({"type": "buses", "data": {"ts": time.time(), "buses": snapshot}})
        await asyncio.sleep(1)


# --- SSE stream infrastructure ---
subscribers: List[asyncio.Queue] = []


async def event_broker() -> None:
    event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)

    async def broadcaster() -> None:
        while True:
            item = await event_queue.get()
            for q in list(subscribers):
                try:
                    q.put_nowait(item)
                except asyncio.QueueFull:
                    pass

    # Start simulators
    asyncio.create_task(gps_simulator())
    asyncio.create_task(ticket_simulator(event_queue))
    asyncio.create_task(scheduler_loop(event_queue))
    asyncio.create_task(buses_broadcast_loop(event_queue))

    await broadcaster()


@app.on_event("startup")
async def on_startup() -> None:
    asyncio.create_task(event_broker())


@app.get("/health")
async def health() -> Dict[str, bool]:
    return {"ok": True}


@app.get("/static")
async def static_data() -> Dict[str, List[dict]]:
    return {
        "stops": [s.model_dump() for s in STOPS.values()],
        "routes": [r.model_dump() for r in ROUTES.values()],
        "schedule": [e.model_dump() for e in SCHEDULE[:200]],
    }


@app.get("/sse")
async def sse_stream() -> StreamingResponse:
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    subscribers.append(queue)

    async def gen():
        try:
            while True:
                item = await queue.get()
                yield f"data: {json.dumps(item)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if queue in subscribers:
                subscribers.remove(queue)

    return StreamingResponse(gen(), media_type="text/event-stream")

