from fastapi import FastAPI, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uuid
import time
import base64
from collections import defaultdict

app = FastAPI()

TOTAL_ORDERS = 51
RATE_LIMIT = 18
WINDOW = 10

ALLOWED_ORIGINS = [
    "https://exam.sanand.workers.dev"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

# -----------------------------
# In-memory storage
# -----------------------------
idempotency = {}
rate_buckets = defaultdict(list)

catalog = [
    {
        "id": i,
        "item": f"Order {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

# -----------------------------
# Rate Limiter
# -----------------------------
@app.middleware("http")
async def rate_limit(request: Request, call_next):

    if request.method == "OPTIONS":
        return await call_next(request)

    client = request.headers.get("X-Client-Id")

    if client:
        now = time.monotonic()

        bucket = rate_buckets[client]

        while bucket and now - bucket[0] >= WINDOW:
            bucket.pop(0)

        if len(bucket) >= RATE_LIMIT:

            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
            )

            response.headers["Retry-After"] = str(WINDOW)

            origin = request.headers.get("Origin")
            if origin in ALLOWED_ORIGINS:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Expose-Headers"] = "Retry-After"
                response.headers["Vary"] = "Origin"

            return response

        bucket.append(now)

    return await call_next(request)


# -----------------------------
# Root
# -----------------------------
@app.get("/")
def root():
    return {"status": "ok"}


# -----------------------------
# POST /orders
# -----------------------------
@app.post("/orders", status_code=201)
def create_order(
    idempotency_key: str = Header(..., alias="Idempotency-Key")
):

    if idempotency_key in idempotency:
        return JSONResponse(
            status_code=201,
            content=idempotency[idempotency_key]
        )

    order = {
        "id": str(uuid.uuid4())
    }

    idempotency[idempotency_key] = order

    return JSONResponse(
        status_code=201,
        content=order
    )


# -----------------------------
# GET /orders
# -----------------------------
@app.get("/orders")
def list_orders(limit: int = 10, cursor: str | None = None):

    start = 0

    if cursor:
        start = int(base64.b64decode(cursor).decode())

    end = min(start + limit, TOTAL_ORDERS)

    items = catalog[start:end]

    next_cursor = None

    if end < TOTAL_ORDERS:
        next_cursor = base64.b64encode(str(end).encode()).decode()

    return {
        "items": items,
        "next_cursor": next_cursor,
    }