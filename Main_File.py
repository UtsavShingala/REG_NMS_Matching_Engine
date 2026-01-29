"""
High-performance Cryptocurrency Matching Engine (REG NMS-inspired).
Supports price-time priority, market/limit/IOC/FOK orders.
FastAPI REST for order entry, WebSocket for trade events, MongoDB persistence, OAuth2 auth.
"""

from fastapi import FastAPI, WebSocket, HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import List, Dict, Union
from collections import deque
from sortedcontainers import SortedDict  # SortedDict for price-level management:contentReference[oaicite:0]{index=0}
from motor.motor_asyncio import AsyncIOMotorClient
import uuid
import asyncio
import datetime

app = FastAPI()

# OAuth2 password flow setup with token URL "token" (FastAPI example):contentReference[oaicite:1]{index=1}
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
# Simple in-memory user "database" for demonstration
fake_users_db = {
    "alice": {"username": "alice", "hashed_password": "secret"}  # password is 'secret'
}

class OrderIn(BaseModel):
    symbol: str
    order_type: str  # "market", "limit", "ioc", "fok"
    side: str        # "buy" or "sell"
    quantity: float
    price: Union[float, None] = None  # Optional for market orders

class CancelOrder(BaseModel):
    order_id: str

# MongoDB setup (local instance)
client = AsyncIOMotorClient("mongodb://localhost:27017")
db = client["exchange"]
orders_collection = db["orders"]
trades_collection = db["trades"]

# In-memory order books: symbol -> {'bids': SortedDict, 'asks': SortedDict}
order_books: Dict[str, Dict[str, SortedDict]] = {}
# Map order_id -> order data (for cancellation lookup)
order_map: Dict[str, Dict] = {}

# WebSocket connections for trade events
trade_subscribers: List[WebSocket] = []

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Simple token authentication: token is username for demo purposes.
    """
    user = fake_users_db.get(token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid authentication credentials")
    return user

@app.post("/token")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Authenticate user and return a bearer token.
    """
    user = fake_users_db.get(form_data.username)
    if not user or user["hashed_password"] != form_data.password:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    # Return token (for demo, token is username)
    return {"access_token": user["username"], "token_type": "bearer"}

def get_order_book(symbol: str):
    """
    Get or create an order book for a symbol.
    """
    sym = symbol.upper()
    if sym not in order_books:
        order_books[sym] = {
            'bids': SortedDict(),  # key: price, value: deque of orders (highest first)
            'asks': SortedDict()   # (lowest first)
        }
    return order_books[sym]

async def broadcast_trade(trade_event: dict):
    """
    Broadcast trade event to all WebSocket subscribers.
    """
    for ws in list(trade_subscribers):
        try:
            await ws.send_json(trade_event)
        except Exception:
            trade_subscribers.remove(ws)

@app.websocket("/ws/trades")
async def trades_ws(websocket: WebSocket):
    """
    WebSocket endpoint for streaming real-time trade execution events:contentReference[oaicite:2]{index=2}.
    """
    await websocket.accept()
    trade_subscribers.append(websocket)
    try:
        while True:
            await asyncio.sleep(10)  # keep alive
    except Exception:
        trade_subscribers.remove(websocket)

@app.post("/submit_order")
async def submit_order(order: OrderIn, user: dict = Depends(get_current_user)):
    """
    Submit a new order (market, limit, IOC, or FOK) with price-time priority matching.
    """
    symbol = order.symbol.upper()
    side = order.side.lower()
    typ = order.order_type.lower()
    qty = order.quantity
    if qty <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive")
    if typ in ["limit", "ioc", "fok"]:
        if order.price is None:
            raise HTTPException(status_code=400, detail="Limit orders require a price")
        price = order.price
    else:  # market
        price = None

    order_id = f"ORDER-{uuid.uuid4()}"
    timestamp = datetime.datetime.utcnow().isoformat()
    # Persist new order with status 'open'
    await orders_collection.insert_one({
        "order_id": order_id, "symbol": symbol, "user": user["username"],
        "side": side, "type": typ, "quantity": qty, "price": price,
        "timestamp": timestamp, "status": "open"
    })
    book = get_order_book(symbol)
    trades_executed = []
    remaining = qty

    # Helper: get best bid/ask using SortedDict.peekitem:contentReference[oaicite:3]{index=3}
    def get_best_price(bids: SortedDict, asks: SortedDict):
        best_bid = bids.peekitem(-1)[0] if bids else None  # highest bid
        best_ask = asks.peekitem(0)[0] if asks else None   # lowest ask
        return best_bid, best_ask

    # Pre-check for FOK: ensure full fill is possible
    if typ == "fok":
        available = 0
        if side == "buy":
            for ask_price, queue in book['asks'].items():
                if price is None or ask_price <= price:
                    available += sum(o['quantity'] for o in queue)
        else:
            for bid_price, queue in book['bids'].items():
                if price is None or bid_price >= price:
                    available += sum(o['quantity'] for o in queue)
        if available < remaining:
            # Cannot fully fill: cancel order
            await orders_collection.update_one({"order_id": order_id}, {"$set": {"status": "cancelled"}})
            return {"order_id": order_id, "status": "cancelled", "filled": False}

    # Matching loop
    while remaining > 0:
        best_bid, best_ask = get_best_price(book['bids'], book['asks'])
        if side == "buy":
            if not book['asks'] or (price is not None and best_ask > price):
                break
            match_price = best_ask
            queue = book['asks'][match_price]
        else:
            if not book['bids'] or (price is not None and best_bid < price):
                break
            match_price = best_bid
            queue = book['bids'][match_price]

        # Execute trade with top-of-book (FIFO)
        maker_order = queue[0]
        trade_qty = min(remaining, maker_order['quantity'])
        maker_order['quantity'] -= trade_qty
        remaining -= trade_qty

        trade_id = f"TRADE-{uuid.uuid4()}"
        trade = {
            "trade_id": trade_id,
            "symbol": symbol,
            "price": match_price,
            "quantity": trade_qty,
            "maker_order_id": maker_order['order_id'],
            "taker_order_id": order_id,
            "aggressor_side": side,
            "timestamp": datetime.datetime.utcnow().isoformat()
        }
        trades_executed.append(trade)
        await trades_collection.insert_one(trade)
        await broadcast_trade(trade)

        # Update maker order in DB
        if maker_order['quantity'] == 0:
            queue.popleft()
            await orders_collection.update_one({"order_id": maker_order['order_id']},
                                            {"$set": {"status": "filled"}})
        else:
            await orders_collection.update_one({"order_id": maker_order['order_id']},
                                            {"$set": {"quantity": maker_order['quantity'], "status": "partial"}})
        if not queue:
            # Remove empty price level
            if side == "buy":
                del book['asks'][match_price]
            else:
                del book['bids'][match_price]

        if typ == "ioc":
            # Cancel any remaining immediately
            break

    # Handle any remaining portion of the order
    if remaining > 0:
        if typ == "limit":
            # Insert remaining as resting limit order
            resting_price = price if price is not None else (match_price if 'match_price' in locals() else None)
            if resting_price is None:
                # No resting price (market order with no book), cancel remainder
                await orders_collection.update_one({"order_id": order_id}, {"$set": {"status": "cancelled"}})
            else:
                side_book = book['bids'] if side == "buy" else book['asks']
                if resting_price not in side_book:
                    side_book[resting_price] = deque()
                side_book[resting_price].append({"order_id": order_id, "quantity": remaining})
                # Update DB with remaining as open
                await orders_collection.update_one({"order_id": order_id},
                                                {"$set": {"quantity": remaining, "status": "open"}})
        else:
            # IOC or market orders cancel any leftover immediately
            await orders_collection.update_one({"order_id": order_id}, {"$set": {"status": "cancelled"}})
    else:
        # Order fully filled
        await orders_collection.update_one({"order_id": order_id}, {"$set": {"status": "filled"}})

    return {"order_id": order_id, "trades": trades_executed}

@app.post("/cancel_order")
async def cancel_order(cancel: CancelOrder, user: dict = Depends(get_current_user)):
    """
    Cancel an existing order by ID.
    """
    order_id = cancel.order_id
    db_order = await orders_collection.find_one({"order_id": order_id})
    if not db_order:
        raise HTTPException(status_code=404, detail="Order not found")
    if db_order.get("status") in ["filled", "cancelled"]:
        raise HTTPException(status_code=400, detail="Order already finalized")
    symbol = db_order["symbol"]
    side = db_order["side"]
    price = db_order["price"]
    book = get_order_book(symbol)
    side_book = book['bids'] if side == "buy" else book['asks']
    if price in side_book:
        queue = side_book[price]
        for o in list(queue):
            if o["order_id"] == order_id:
                queue.remove(o)
                break
        if not queue:
            del side_book[price]
    await orders_collection.update_one({"order_id": order_id}, {"$set": {"status": "cancelled"}})
    return {"order_id": order_id, "status": "cancelled"}
