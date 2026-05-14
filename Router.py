"""
Socket-based Distance Vector routing table simulation.

Demo topology:
    A --1-- B --1-- C
    A --5-- C

Expected learning moment:
    A should learn C through B with cost 2 instead of direct cost 5.
    C should learn A through B with cost 2 instead of direct cost 5.
"""

import json
import socket
import sys
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional


RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[96m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"

HOST = "127.0.0.1"

INFINITY = 16
UPDATE_INTERVAL = 3
ROUTE_TIMEOUT = 15
GARBAGE_TIMEOUT = 9
STARTUP_DELAY = 5

PORTS = {
    "A": 5001,
    "B": 5002,
    "C": 5003,
}

TOPOLOGY = {
    "A": {"B": 1, "C": 5},
    "B": {"A": 1, "C": 1},
    "C": {"A": 5, "B": 1},
}


def colored(text: str, color_code: str) -> str:
    return f"{color_code}{text}{RESET}"


@dataclass
class RoutingTableEntry:
    destination: str
    next_hop: str
    metric: int
    timeout: Optional[int] = None
    garbage_timer: Optional[int] = None


class Router:
    def __init__(self, router_id: str):
        self.router_id = router_id
        self.port = PORTS[router_id]
        self.neighbors: Dict[str, int] = {}
        self.routing_table: Dict[str, RoutingTableEntry] = {}

        self.lock = threading.Lock()
        self.running = True

        # Separate sockets make the demo cleaner on Windows.
        # One socket only receives. One socket only sends.
        self.receive_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.receive_sock.bind((HOST, self.port))
        self.receive_sock.settimeout(1)

        self.send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def add_neighbor(self, neighbor_id: str, cost: int) -> None:
        self.neighbors[neighbor_id] = cost

    def initialise_routing_table(self) -> None:
        with self.lock:
            self.routing_table[self.router_id] = RoutingTableEntry(
                destination=self.router_id,
                next_hop=self.router_id,
                metric=0,
                timeout=None,
            )

            for neighbor_id, cost in self.neighbors.items():
                self.routing_table[neighbor_id] = RoutingTableEntry(
                    destination=neighbor_id,
                    next_hop=neighbor_id,
                    metric=cost,
                    timeout=None,
                )

    def get_distance_vector(self, to_neighbor: str) -> Dict[str, int]:
        vector: Dict[str, int] = {}

        with self.lock:
            for dest, entry in self.routing_table.items():
                # Split horizon:
                # Do not advertise a route back to the neighbour it was learned from.
                if entry.next_hop == to_neighbor and dest != to_neighbor:
                    continue

                vector[dest] = min(entry.metric, INFINITY)

        return vector

    def send_routing_update(self) -> None:
        for neighbor_id in self.neighbors:
            message = {
                "type": "distance_vector_update",
                "from": self.router_id,
                "table": self.get_distance_vector(to_neighbor=neighbor_id),
            }

            data = json.dumps(message).encode("utf-8")
            self.send_sock.sendto(data, (HOST, PORTS[neighbor_id]))

            print(
                colored(
                    f"[{self.router_id}] Sent update to {neighbor_id}: {message['table']}",
                    CYAN,
                )
            )

    def listen_for_updates(self) -> None:
        while self.running:
            try:
                data, _ = self.receive_sock.recvfrom(4096)
                message = json.loads(data.decode("utf-8"))

            except socket.timeout:
                continue

            except json.JSONDecodeError:
                print(colored(f"[{self.router_id}] Ignored invalid JSON message", RED))
                continue

            except OSError:
                break

            if message.get("type") != "distance_vector_update":
                continue

            from_router = message.get("from")
            received_table = message.get("table", {})

            if from_router not in self.neighbors:
                print(
                    colored(
                        f"[{self.router_id}] Ignored update from non-neighbour {from_router}",
                        RED,
                    )
                )
                continue

            print(
                colored(
                    f"[{self.router_id}] Received update from {from_router}: {received_table}",
                    YELLOW,
                )
            )

            changed = self.receive_routing_update(from_router, received_table)

            if changed:
                self.display_routing_table()

    def receive_routing_update(self, from_router: str, received_table: Dict[str, int]) -> bool:
        updated = False
        cost_to_sender = self.neighbors[from_router]

        with self.lock:
            for dest, received_metric in received_table.items():
                if dest == self.router_id:
                    continue

                new_metric = min(int(received_metric) + cost_to_sender, INFINITY)
                existing_entry = self.routing_table.get(dest)

                if existing_entry is None:
                    self.routing_table[dest] = RoutingTableEntry(
                        destination=dest,
                        next_hop=from_router,
                        metric=new_metric,
                        timeout=ROUTE_TIMEOUT,
                    )

                    print(
                        colored(
                            f"[{self.router_id}] New route learned: "
                            f"{dest} cost {new_metric} via {from_router}",
                            GREEN,
                        )
                    )
                    updated = True
                    continue

                if existing_entry.next_hop == from_router:
                    if existing_entry.metric != new_metric:
                        print(
                            colored(
                                f"[{self.router_id}] Route changed: "
                                f"{dest} cost {existing_entry.metric} -> {new_metric} "
                                f"via {from_router}",
                                GREEN if new_metric < existing_entry.metric else YELLOW,
                            )
                        )
                        updated = True

                    existing_entry.metric = new_metric

                    if existing_entry.timeout is not None:
                        existing_entry.timeout = ROUTE_TIMEOUT

                    if new_metric >= INFINITY:
                        existing_entry.garbage_timer = GARBAGE_TIMEOUT
                    else:
                        existing_entry.garbage_timer = None

                    continue

                if new_metric < existing_entry.metric:
                    old_metric = existing_entry.metric
                    old_next_hop = existing_entry.next_hop

                    self.routing_table[dest] = RoutingTableEntry(
                        destination=dest,
                        next_hop=from_router,
                        metric=new_metric,
                        timeout=ROUTE_TIMEOUT,
                    )

                    print(
                        colored(
                            f"[{self.router_id}] Better route: "
                            f"{dest} cost {old_metric} via {old_next_hop} "
                            f"-> cost {new_metric} via {from_router}",
                            GREEN,
                        )
                    )
                    updated = True

        return updated

    def age_routes(self) -> bool:
        updated = False

        with self.lock:
            for dest, entry in list(self.routing_table.items()):
                if entry.timeout is None:
                    continue

                if entry.metric < INFINITY:
                    entry.timeout -= UPDATE_INTERVAL

                    if entry.timeout <= 0:
                        entry.metric = INFINITY
                        entry.garbage_timer = GARBAGE_TIMEOUT

                        print(
                            colored(
                                f"[{self.router_id}] Route timeout: {dest} is now unreachable",
                                RED,
                            )
                        )
                        updated = True

                else:
                    if entry.garbage_timer is not None:
                        entry.garbage_timer -= UPDATE_INTERVAL

                        if entry.garbage_timer <= 0:
                            print(
                                colored(
                                    f"[{self.router_id}] Removed unreachable route: {dest}",
                                    RED,
                                )
                            )
                            del self.routing_table[dest]
                            updated = True

        return updated

    def display_routing_table(self) -> None:
        with self.lock:
            rows = sorted(
                self.routing_table.values(),
                key=lambda entry: entry.destination,
            )

        print(colored(f"\nRouting Table for Router {self.router_id}", BOLD + CYAN))
        print(f"{'Destination':<15}{'Next Hop':<12}{'Metric':<8}{'Timeout'}")
        print("-" * 50)

        for entry in rows:
            timeout = "direct" if entry.timeout is None else str(entry.timeout)

            line = (
                f"{entry.destination:<15}"
                f"{entry.next_hop:<12}"
                f"{entry.metric:<8}"
                f"{timeout}"
            )

            if entry.metric < INFINITY:
                print(colored(line, GREEN))
            else:
                print(colored(line, RED))

        print()

    def run(self) -> None:
        self.initialise_routing_table()

        print(
            colored(
                f"Router {self.router_id} listening on UDP port {self.port}",
                BOLD + CYAN,
            )
        )

        self.display_routing_table()

        listener = threading.Thread(target=self.listen_for_updates, daemon=True)
        listener.start()

        print(
            colored(
                f"[{self.router_id}] Waiting {STARTUP_DELAY} seconds so the other routers can start...",
                YELLOW,
            )
        )
        time.sleep(STARTUP_DELAY)

        try:
            while self.running:
                self.send_routing_update()

                if self.age_routes():
                    self.display_routing_table()

                time.sleep(UPDATE_INTERVAL)

        except KeyboardInterrupt:
            print(colored(f"\n[{self.router_id}] Router stopped by user", RED))

        finally:
            self.running = False
            self.receive_sock.close()
            self.send_sock.close()


def build_router(router_id: str) -> Router:
    router = Router(router_id)

    for neighbor_id, cost in TOPOLOGY[router_id].items():
        router.add_neighbor(neighbor_id, cost)

    return router


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python Router.py <router_id>")
        print("Example: python Router.py A")
        print(f"Available routers: {', '.join(PORTS)}")
        sys.exit(1)

    router_id = sys.argv[1].upper()

    if router_id not in PORTS:
        print(f"Unknown router '{router_id}'. Use one of: {', '.join(PORTS)}")
        sys.exit(1)

    router = build_router(router_id)
    router.run()


if __name__ == "__main__":
    main()
