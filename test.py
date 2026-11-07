import sys
import time

import requests

PRIMARY = "http://127.0.0.1:5001"
REPLICA = "http://127.0.0.1:5002"
ORDER = "http://127.0.0.1:5003"


def stamp():
    return time.strftime("%H:%M:%S")


def say(text=""):
    print(text, flush=True)


def step(text):
    say()
    say(f"[{stamp()}] {text}")


def call(method, url, **kwargs):
    try:
        return requests.request(method, url, timeout=15, **kwargs)
    except requests.exceptions.ConnectionError:
        say(f"ERROR: cannot connect to {url}. Is that service running?")
        sys.exit(1)


def read(base):
    return call("GET", f"{base}/products/1").json()


def show(label, p):
    say(f"    {label:<8} price={p['price']}  stock={p['stock']}  version={p['version']}")


def make_order(source):
    r = call("POST", f"{ORDER}/orders", json={"product_id": 1, "quantity": 1, "catalog_source": source})
    o = r.json()
    say(f"    Order #{o['id']} (catalog_source={source}): "
        f"price={o['product_price']} stock={o['product_stock']} version={o['product_version']}")
    return o


def print_table(header, rows):
    say()
    cols = len(header)
    widths = [max(len(str(r[i])) for r in rows + [header]) for i in range(cols)]
    line = "  ".join("{:<" + str(w) + "}" for w in widths)
    say(line.format(*header))
    say("  ".join("-" * w for w in widths))
    for r in rows:
        say(line.format(*r))


def reset_all():
    call("POST", f"{PRIMARY}/reset")
    call("POST", f"{REPLICA}/reset")


def fmt(p, field):
    return f"{p[field]}, v{p['version']}"


def experiment_async():
    say("=" * 64)
    say("EXPERIMENT 1: ASYNCHRONOUS REPLICATION")
    say("=" * 64)
    reset_all()

    step("1. Check that primary and replica hold the same product (version 1)")
    p, r = read(PRIMARY), read(REPLICA)
    show("Primary", p)
    show("Replica", r)
    o0 = make_order("replica")
    rows = [("Before update", fmt(p, "price"), fmt(r, "price"), o0["product_price"])]

    step("2. Update the primary: price 450000, mode async")
    t0 = time.perf_counter()
    resp = call("PUT", f"{PRIMARY}/products/1", json={"price": 450000, "mode": "async"})
    ms = (time.perf_counter() - t0) * 1000
    say(f"    Primary answered {resp.json()['status']} after {ms:.0f} ms (it did not wait for the replica)")
    t_update = time.perf_counter()

    step("3. IMMEDIATELY read the product from the primary and the replica")
    p, r = read(PRIMARY), read(REPLICA)
    show("Primary", p)
    show("Replica", r)
    if r["version"] < p["version"]:
        say("    -> The replica is behind: this is a STALE READ.")

    step("4. Create an order with catalog_source=replica (while the replica lags)")
    o1 = make_order("replica")
    if o1["product_price"] != p["price"]:
        say(f"    -> The order got the OLD price {o1['product_price']} (primary already has {p['price']}).")
    rows.append(("Immediately after async PUT", fmt(p, "price"), fmt(r, "price"),
                 f"Old price {o1['product_price']}"))

    step("5. Wait until the update reaches the replica (checking every 0.5 s)")
    while True:
        r = read(REPLICA)
        waited = time.perf_counter() - t_update
        if r["version"] >= p["version"] or waited > 20:
            break
        time.sleep(0.5)
    say(f"    Replica received version {r['version']} about {waited:.1f} s after the update.")

    step("6. Repeat the reads and the order")
    p, r = read(PRIMARY), read(REPLICA)
    show("Primary", p)
    show("Replica", r)
    o2 = make_order("replica")
    rows.append(("After 5 seconds", fmt(p, "price"), fmt(r, "price"),
                 f"New price {o2['product_price']}"))

    say()
    say("RESULTS TABLE - Experiment 1 (price)")
    print_table(("Time", "Primary", "Replica", "Order sees"), rows)


def experiment_sync():
    say()
    say("=" * 64)
    say("EXPERIMENT 2: SYNCHRONOUS REPLICATION")
    say("=" * 64)

    step("1. State before the update")
    p, r = read(PRIMARY), read(REPLICA)
    show("Primary", p)
    show("Replica", r)

    step("2. Update the primary: stock 5, mode sync (watch the replica log for 'APPLIED' and 'ACK')")
    t0 = time.perf_counter()
    resp = call("PUT", f"{PRIMARY}/products/1", json={"stock": 5, "mode": "sync"})
    ms = (time.perf_counter() - t0) * 1000
    body = resp.json()
    say(f"    Primary answered {body['status']} after {ms:.0f} ms (it waited for the replica's ACK)")
    say(f"    {body.get('replication', '')}")

    step("3. After SUCCESS, read the product from both catalogues")
    p, r = read(PRIMARY), read(REPLICA)
    show("Primary", p)
    show("Replica", r)

    step("4. Create an order with catalog_source=replica")
    o = make_order("replica")

    say()
    say("RESULTS TABLE - Experiment 2 (stock)")
    print_table(("Node", "Result after SUCCESS"), [
        ("Catalog Primary", f"stock {p['stock']}, version {p['version']}"),
        ("Catalog Replica", f"stock {r['stock']}, version {r['version']}"),
        ("Order Service", f"receives stock {o['product_stock']} and version {o['product_version']}"),
    ])
    if p["version"] != 3:
        say()
        say(f"Note: version is {p['version']}. The lab expects version 3 when this runs right after the async experiment.")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode == "async":
        experiment_async()
    elif mode == "sync":
        experiment_sync()
    elif mode == "all":
        experiment_async()
        experiment_sync()
    else:
        say("Usage: python experiment.py [async|sync|all]")
        sys.exit(1)