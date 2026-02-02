# Low-Latency Order Matching Engine (Exchange Core)

A high-performance, low-latency matching engine inspired by **REG NMS principles** and real-world centralized exchanges.

This project focuses on building the **core exchange matching engine**, emphasizing **fair price–time priority execution**, real-time trade streaming, and exchange-grade system design.

---

## 🚀 Overview

The REG NMS Matching Engine replicates the internal order-matching logic used by modern exchanges.  
Unlike trading bots or simulators, this system matches **real user orders** using deterministic and fair execution rules.

### Key Objectives
- Demonstrate low-latency financial infrastructure design
- Implement strict **price–time priority (FIFO)** matching
- Build real-time systems using WebSockets
- Showcase understanding of market microstructure

---

## 🏗️ System Architecture

The engine follows a modular architecture similar to real crypto exchanges:

- **FastAPI Backend** – REST APIs for order entry and authentication
- **Matching Engine Core** – Executes trades using price–time priority
- **In-Memory Order Book** – Ultra-fast matching using optimized data structures
- **MongoDB Persistence** – Stores completed trades and orders
- **WebSocket Layer** – Streams real-time trade execution data

**Goal:** Simulate an exchange engine comparable to Binance/Coinbase at a conceptual level.

---

## ⚙️ Design Choices

| Component | Reason |
|--------|--------|
| FastAPI | Asynchronous, high-performance, native WebSocket support |
| In-Memory Order Book | Avoids database latency in the matching path |
| MongoDB | Flexible JSON-like storage for trade logs |
| WebSockets | Real-time trade updates like real exchanges |

---

## 🧠 Core Data Structures

To enforce REG NMS–style price–time priority, the following structures are used:

| Data Structure | Purpose |
|--------------|--------|
| SortedDict | Maintains sorted price levels (best bid / ask lookup) |
| Deque | FIFO execution within each price level |
| Dictionary | Symbol-wise order book storage |

This ensures:
- Best-price execution
- FIFO fairness
- No trade-through violations

---

## 🔁 Matching Algorithm

The matching engine strictly follows **Price–Time Priority**:

1. Match orders at the **best available price**
2. Within the same price level, execute the **oldest order first**
3. Fully consume better price levels before moving to worse ones

### Supported Order Types
- **Market** – Execute immediately at best available price
- **Limit** – Execute at limit price or rest in the order book
- **IOC (Immediate or Cancel)** – Execute immediately, cancel remaining
- **FOK (Fill or Kill)** – Execute fully immediately or cancel entirely

This behavior closely mirrors real exchange execution logic.

---

## 🔐 Authentication

- OAuth2 Password-based authentication
- Token-based access for protected endpoints
- Simple in-memory user store (demo purpose)

---

## 📡 API Endpoints

| Endpoint | Description |
|-------|------------|
| POST `/token` | User authentication |
| POST `/submit_order` | Place BUY / SELL orders |
| POST `/cancel_order` | Cancel open orders |
| WS `/ws/trades` | Real-time trade execution feed |

---

## 📈 Trade-offs & Engineering Decisions

| Decision | Reasoning |
|--------|-----------|
| In-memory matching | Eliminates DB latency in critical path |
| Single match loop | Guarantees FIFO correctness |
| MongoDB for trades only | Keeps matching fast while preserving history |
| No frontend | Backend and systems-focused design |

---

## 🧪 Use Cases

- Exchange core engine prototype
- Trading system simulation
- Market microstructure research
- Backend / quant infrastructure interview showcase

---

## 📌 Disclaimer

This project is for **educational and demonstrative purposes only** and is not intended for production trading or financial use.
