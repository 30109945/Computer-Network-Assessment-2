# Distance Vector Routing Simulation

This repository contains a Python socket-based simulation of how routing tables are built using a distance vector routing approach.

The simulation uses three routers:

```text
A --1-- B --1-- C
A --5-- C
```

Router A and Router C have a direct route with cost 5, but both can learn a cheaper route through Router B with total cost 2.

## What the program shows

The program demonstrates the basic distance vector process:

```text
Router receives neighbour routing table
Router calculates possible new cost
If the new cost is cheaper, the routing table is updated
The updated routing table is printed
```

Each router runs as a separate Python process and communicates with the others using UDP sockets.

## Files

```text
router\_v2.py
README.md
```

## Requirements

Python 3 is required.

No external libraries are needed. The program uses built-in Python modules such as:

```text
socket
json
threading
time
sys
dataclasses
```

## How to run

Open three separate terminals in the same folder as `router\_v2.py`.

Terminal 1:

```bash
python Router.py A
```

Terminal 2:

```bash
python Router.py B
```

Terminal 3:

```bash
python Router.py C
```

Start all three routers within a few seconds of each other.

## Expected result

Router A should learn that Router C is cheaper through Router B:

```text
\[A] Better route: C cost 5 via C -> cost 2 via B
```

Router C should also learn that Router A is cheaper through Router B:

```text
\[C] Better route: A cost 5 via A -> cost 2 via B
```

This shows that routing tables are being updated using distance vector messages from neighbouring routers.

## UDP ports

Each router listens on a different UDP port:

```text
Router A: 5001
Router B: 5002
Router C: 5003
```

The routers communicate on localhost using `127.0.0.1`.

## Message format

Routing updates are sent as JSON messages. Example:

```json
{
  "type": "distance\_vector\_update",
  "from": "A",
  "table": {
    "A": 0,
    "B": 1,
    "C": 5
  }
}
```

JSON was used because it makes the routing update easy to read during testing.

## Notes

This is not a full RIPng implementation. It is a simulation of the routing-table construction process used in distance vector routing.

The program focuses on:

* routing table construction
* neighbour updates
* UDP socket communication
* better route selection
* split horizon
* route timeout handling

## How to stop

Press `CTRL + C` in each terminal.

