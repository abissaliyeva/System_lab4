import argparse
import logging
import threading

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
log = logging.getLogger("ORDER")

orders = {}
next_id = 1
lock = threading.Lock()

PRIMARY_URL = "http://127.0.0.1:5001"
REPLICA_URL = "http://127.0.0.1:5002"
CATALOG_TIMEOUT = 3


def is_positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


@app.route("/orders", methods=["POST"])
def create_order():
    global next_id

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    product_id = data.get("product_id")
    quantity = data.get("quantity", 1)
    source = data.get("catalog_source", "primary")

    if not is_positive_int(product_id):
        return jsonify({"error": "Field 'product_id' is required and must be a positive integer"}), 400
    if not is_positive_int(quantity):
        return jsonify({"error": "Field 'quantity' must be a positive integer"}), 400
    if source not in ("primary", "replica"):
        return jsonify({"error": "Field 'catalog_source' must be 'primary' or 'replica'"}), 400

    base_url = PRIMARY_URL if source == "primary" else REPLICA_URL
    try:
        resp = requests.get(f"{base_url}/products/{product_id}", timeout=CATALOG_TIMEOUT)
    except requests.exceptions.RequestException:
        log.error("catalogue (%s) is unreachable", source)
        return jsonify({"error": f"Catalog {source} is unavailable. Please try again later."}), 503

    if resp.status_code == 404:
        return jsonify({"error": f"Product with id {product_id} not found in catalog {source}"}), 404
    if resp.status_code != 200:
        return jsonify({"error": f"Catalog {source} returned an unexpected error."}), 503

    try:
        product = resp.json()
        name, price = product["name"], product["price"]
        stock, version = product["stock"], product["version"]
    except (ValueError, KeyError, TypeError):
        return jsonify({"error": f"Catalog {source} returned invalid data."}), 503

    with lock:
        order = {
            "id": next_id,
            "product_id": product_id,
            "product_name": name,
            "product_price": price,
            "product_stock": stock,
            "product_version": version,
            "quantity": quantity,
            "total": price * quantity,
            "catalog_source": source,
        }
        orders[next_id] = order
        next_id += 1

    log.info("ORDER #%s created, product read from %s: %s price=%s stock=%s version=%s total=%s",
             order["id"], source.upper(), name, price, stock, version, order["total"])
    return jsonify(order), 201


@app.route("/orders/<int:order_id>", methods=["GET"])
def get_order(order_id):
    order = orders.get(order_id)
    if order is None:
        return jsonify({"error": f"Order with id {order_id} not found"}), 404
    return jsonify(order), 200


@app.errorhandler(404)
def handle_404(e):
    return jsonify({"error": "Resource not found"}), 404


@app.errorhandler(405)
def handle_405(e):
    return jsonify({"error": "Method not allowed for this endpoint"}), 405


@app.errorhandler(500)
def handle_500(e):
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Order Service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5003)
    parser.add_argument("--primary-url", default=PRIMARY_URL)
    parser.add_argument("--replica-url", default=REPLICA_URL)
    args = parser.parse_args()
    PRIMARY_URL = args.primary_url.rstrip("/")
    REPLICA_URL = args.replica_url.rstrip("/")

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s.%(msecs)03d [%(name)s] %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    log.info("Order Service on port %s (primary %s, replica %s)", args.port, PRIMARY_URL, REPLICA_URL)
    app.run(host=args.host, port=args.port, debug=False)