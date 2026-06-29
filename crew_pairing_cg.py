"""
Crew Pairing Problem - Column Generation Solver
================================================
Constructs a 1-day leg-based network and solves the Crew Pairing Problem
using Column Generation via the columngenerationsolverpy library.

Formulation: Set Covering (each flight covered at least once).
Pricing Subproblem: Resource-Constrained Shortest Path (RCSPP) on the
leg-based DAG with FDT limit enforcement.
"""

import pandas as pd
import numpy as np
import networkx as nx
import columngenerationsolverpy
import time

# =============================================================================
# 1. OPERATIONAL PARAMETERS (EASA Regulations & Project Specs)
# =============================================================================
MCT = 45                    # Minimum Connection Time (minutes)
MIN_REST = 720              # 12 hours minimum rest (minutes)
CHECK_IN_FLIGHT = 70        # Minutes before departure
CHECK_OUT_FLIGHT = 30       # Minutes after arrival
AIRPORT_SECURITY_BUFFER = 60  # Buffer for ground transfers
MAX_SIT_TIME = 360          # 6 hours max sit time within a duty

UNIQUE_BASES = ['FRA', 'MUC', 'DUS', 'STR', 'HAM', 'CGN', 'BER', 'NUE', 'HAJ']

# =============================================================================
# 2. DATA LOADING
# =============================================================================
DATA_DIR = r"C:\Users\defne\Documents\Master\Semester 2\Analytics Project\or_project_data\or_project_data"
flights_path = DATA_DIR + r"\flight_schedule.csv"
gt_path = DATA_DIR + r"\ground_transportation_times.csv"
fdt_path = DATA_DIR + r"\fdt_limits.csv"


def load_easa_limits(csv_path):
    """Parse FDT limits from CSV. Returns list of ((start_h, end_h), {num_legs: max_minutes})."""
    df_fdt = pd.read_csv(csv_path)
    parsed_limits = []
    sector_columns = [col for col in df_fdt.columns if col.isdigit()]

    for _, row in df_fdt.iterrows():
        start_str = str(row['flight_duty_time_start_time']).strip()
        end_str = str(row['flight_duty_time_end_time']).strip()

        start_h = pd.to_timedelta(start_str).total_seconds() / 3600.0
        end_h = pd.to_timedelta(end_str).total_seconds() / 3600.0

        sector_map = {}
        for col in sector_columns:
            num_sectors = int(col)
            max_fdt_minutes = int(float(row[col]) * 60)
            sector_map[num_sectors] = max_fdt_minutes

        parsed_limits.append(((start_h, end_h), sector_map))
    return parsed_limits


EASA_FDT_LIMITS = load_easa_limits(fdt_path)


def get_max_fdt(check_in_minutes, l_d):
    """Returns the max flight duty time in minutes based on check-in time and number of legs (l_d)."""
    minute_of_day = check_in_minutes % 1440
    hour_of_day = minute_of_day / 60.0
    l_d = min(l_d, 10)  # EASA limits cap at 10 sectors

    for (start_h, end_h), sector_limits in EASA_FDT_LIMITS:
        if start_h > end_h:
            if hour_of_day >= start_h or hour_of_day <= end_h:
                return sector_limits[l_d]
        else:
            if start_h <= hour_of_day <= end_h:
                return sector_limits[l_d]
    return 720  # Safe fallback


# Load flights
print("Loading flight schedule...")
df = pd.read_csv(flights_path)
df['SCHEDULED_DEPARTURE_TIME'] = pd.to_datetime(df['SCHEDULED_DEPARTURE_TIME'])
df['SCHEDULED_ARRIVAL_TIME'] = pd.to_datetime(df['SCHEDULED_ARRIVAL_TIME'])

# Filter for 1 day (2025-04-27)
target_date = pd.to_datetime('2025-04-27').date()
df = df[df['SCHEDULED_DEPARTURE_TIME'].dt.date == target_date].copy()
df = df.sort_values(by='SCHEDULED_DEPARTURE_TIME').reset_index(drop=True)

# Calculate absolute minutes from the start of the day
baseline_date = pd.to_datetime('2025-04-27')
df['DEP_MINUTES'] = (df['SCHEDULED_DEPARTURE_TIME'] - baseline_date).dt.total_seconds() / 60
df['ARR_MINUTES'] = (df['SCHEDULED_ARRIVAL_TIME'] - baseline_date).dt.total_seconds() / 60
df['FLIGHT_DURATION'] = df['ARR_MINUTES'] - df['DEP_MINUTES']

print(f"  Loaded {len(df)} flights for {target_date}")

# Load Ground Transportation
gt_df = pd.read_csv(gt_path)
ground_transit_map = {}
for _, row in gt_df.iterrows():
    orig = str(row['Dep Ap']).strip().upper()
    dest = str(row['Arr Ap']).strip().upper()
    transit_time_minutes = int(float(row['avg_duration']) * 60)
    ground_transit_map[(orig, dest)] = transit_time_minutes
    ground_transit_map[(dest, orig)] = transit_time_minutes  # Assuming symmetric

print(f"  Loaded {len(ground_transit_map)} ground transport connections")

# =============================================================================
# 3. FLIGHT-TO-ROW INDEX MAPPING
# =============================================================================
# Create a stable ordering of flight leg IDs for the master problem rows
flight_legs = list(df['LEG_ID'].astype(str))
leg_to_row = {leg_id: i for i, leg_id in enumerate(flight_legs)}
row_to_leg = {i: leg_id for i, leg_id in enumerate(flight_legs)}
num_flights = len(flight_legs)

print(f"  Index mapping: {num_flights} flight legs -> rows 0..{num_flights - 1}")

# =============================================================================
# 4. CONSTRUCT THE LEG-BASED NETWORK GRAPH
# =============================================================================
print("\nConstructing leg-based network...")
G = nx.DiGraph()

# Add flight leg nodes
for idx, row in df.iterrows():
    leg_id = str(row['LEG_ID'])
    G.add_node(
        leg_id,
        type='FLIGHT',
        origin=row['DEPARTURE_AIRPORT'],
        destination=row['ARRIVAL_AIRPORT'],
        dep_time=row['DEP_MINUTES'],
        arr_time=row['ARR_MINUTES'],
        duration=row['FLIGHT_DURATION']
    )

# Add Source and Sink Nodes for Bases
for base in UNIQUE_BASES:
    source_id = f"SOURCE_{base}"
    sink_id = f"SINK_{base}"
    G.add_node(source_id, type='SOURCE', base=base)
    G.add_node(sink_id, type='SINK', base=base)

# Generate Edges (Connections)
flight_nodes = [n for n, attr in G.nodes(data=True) if attr['type'] == 'FLIGHT']

# Connect Flights to Flights
for i, leg1_id in enumerate(flight_nodes):
    leg1 = G.nodes[leg1_id]

    for leg2_id in flight_nodes[i+1:]:
        leg2 = G.nodes[leg2_id]

        time_gap = leg2['dep_time'] - leg1['arr_time']

        # Connection Type A: Standard Turnaround (Same Airport)
        if leg1['destination'] == leg2['origin']:
            if MCT <= time_gap <= MAX_SIT_TIME:
                G.add_edge(leg1_id, leg2_id, type='TURN', gap=time_gap, cost=0)

        # Connection Type B: Ground Transfer (Different Airport)
        else:
            orig_ap = leg1['destination']
            dest_ap = leg2['origin']

            if (orig_ap, dest_ap) in ground_transit_map:
                transit_time = ground_transit_map[(orig_ap, dest_ap)]
                total_required_time = transit_time + AIRPORT_SECURITY_BUFFER

                if total_required_time <= time_gap <= MAX_SIT_TIME:
                    transfer_cost = 45.0 + (transit_time * 0.40)
                    G.add_edge(leg1_id, leg2_id, type='TRANSFER', gap=time_gap,
                               cost=transfer_cost, transit_time=transit_time)

# Connect Source/Sink to Flights (Including Initial/Final Ground Transfers)
for leg_id in flight_nodes:
    leg = G.nodes[leg_id]

    for base in UNIQUE_BASES:
        source_id = f"SOURCE_{base}"
        sink_id = f"SINK_{base}"

        # --- Duty Start ---
        if leg['origin'] == base:
            G.add_edge(source_id, leg_id, type='START_DUTY', cost=0, transit_time=0)
        else:
            if (base, leg['origin']) in ground_transit_map:
                transit_time = ground_transit_map[(base, leg['origin'])]
                transfer_cost = 45.0 + (transit_time * 0.40)
                G.add_edge(source_id, leg_id, type='START_DUTY_TRANSFER',
                           cost=transfer_cost, transit_time=transit_time)

        # --- Duty End ---
        if leg['destination'] == base:
            G.add_edge(leg_id, sink_id, type='END_DUTY', cost=0, transit_time=0)
        else:
            if (leg['destination'], base) in ground_transit_map:
                transit_time = ground_transit_map[(leg['destination'], base)]
                transfer_cost = 45.0 + (transit_time * 0.40)
                G.add_edge(leg_id, sink_id, type='END_DUTY_TRANSFER',
                           cost=transfer_cost, transit_time=transit_time)

# Print graph statistics
print("=== 1-Day Leg-Based Network Graph Constructed ===")
print(f"Total Nodes: {G.number_of_nodes()}")
print(f"  - Flights: {len(flight_nodes)}")
print(f"  - Source/Sinks: {len(UNIQUE_BASES) * 2}")
print(f"Total Edges: {G.number_of_edges()}")

edge_types = {}
for u, v, attr in G.edges(data=True):
    t = attr.get('type')
    edge_types[t] = edge_types.get(t, 0) + 1
for t, count in edge_types.items():
    print(f"  - {t}: {count}")

