# Lab 3: REST API and Two Services

Two Flask services with in-memory data:

- **Service A, Catalog** (`catalog_service.py`, port 5001): create and get products.
- **Service B, Orders** (`orders_service.py`, port 5002): create and get orders. When an order is created, B asks A for the product over HTTP (2-second timeout), calculates the total, and saves the product name and price inside the order.

## Run

```powershell
pip install -r requirements.txt
```

Terminal 1:
```powershell
python catalog_service.py --port 5001
```

Terminal 2:
```powershell
python orders_service.py --port 5002 --catalog-url http://127.0.0.1:5001
```

## Endpoints

**Service A**
- `POST /products` with `{"name": "Laptop", "price": 499.99}`: returns 201, or 400 on bad input
- `GET /products/<id>`: returns 200, or 404 if not found

**Service B**
- `POST /orders` with `{"product_id": 1, "quantity": 3}`: returns 201, 400 on bad input, 404 if the product does not exist, 503 if A is down or too slow
- `GET /orders/<id>`: returns 200 from B's saved data (A is not called), or 404 if not found

## The three checks (Terminal 3)

```powershell
# create a product
curl.exe -i -X POST http://127.0.0.1:5001/products -H "Content-Type: application/json" -d '{\"name\":\"Laptop\",\"price\":499.99}'

# Check 1: both running -> 201 with name, price, quantity, total
curl.exe -i -X POST http://127.0.0.1:5002/orders -H "Content-Type: application/json" -d '{\"product_id\":1,\"quantity\":3}'
curl.exe -i http://127.0.0.1:5002/orders/1

# Stop A (Ctrl+C in Terminal 1), then:

# Check 2: A stopped -> 503 JSON error, B keeps running
curl.exe -i -X POST http://127.0.0.1:5002/orders -H "Content-Type: application/json" -d '{\"product_id\":1,\"quantity\":2}'

# Check 3: A stopped -> 200 with the saved order
curl.exe -i http://127.0.0.1:5002/orders/1
```

Evidence (screenshots or logs) for the three checks is in the `screenshots/` folder.


# Lab 4. Product Catalogue Replication

pip install -r requirements.txt
python catalog_replica.py --port 5002
python catalog_primary.py --port 5001 --replica-url http://127.0.0.1:5002
python order_app.py --port 5003 --primary-url http://127.0.0.1:5001 --replica-url http://127.0.0.1:5002

python test.py async
python test.py sync