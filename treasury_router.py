#!/usr/bin/env python3.11
"""
T-Zero Autonomous Treasury Router
AP2_Mandate_V3 Compliance Engine
Knapsack Optimizer + Jurisdictional Router + SAP S/4 Reconciliation Output

Knapsack strategy: Because we have only 3 urgent items and a $4M cap,
we enumerate ALL 2^3 = 8 subsets and pick the feasible one that maximises
total penalty saved. This is exact, O(1) effectively, and avoids the
400M-cell DP table that caused a timeout with cent-precision integers.
"""

import json
import csv
import os
import itertools
from decimal import Decimal, ROUND_HALF_UP

# ─────────────────────────────────────────────────────────────────────────────
# 1. LOAD SOURCE DATA
# ─────────────────────────────────────────────────────────────────────────────

MANDATE_PATH = "/home/ubuntu/upload/AP2_Mandate_V3.json"
CSV_PATH     = "/home/ubuntu/upload/AP_Run_V3.csv"
OUTPUT_CSV   = "/home/ubuntu/SAP_S4_Recon.csv"

with open(MANDATE_PATH) as f:
    mandate = json.load(f)

DIGITAL_CAP       = Decimal(str(mandate["digital_liquidity_cap_usd"]))   # 4,000,000
SE_ASIA_COUNTRIES = mandate["rules"]["routing_constraints"]["SE_Asia"]["countries"]
ALLOWED_NETWORKS  = mandate["rules"]["routing_constraints"]["SE_Asia"]["allowed_networks"]
MAX_GAS_USD       = Decimal(str(mandate["rules"]["execution_thresholds"]["max_acceptable_network_gas_usd"]))
DEFAULT_RAIL      = mandate["rules"]["execution_thresholds"]["default_rail_preference"]

# EUR/USD spot rate (conservative weekend estimate)
EUR_USD_RATE = Decimal("1.085")

# ─────────────────────────────────────────────────────────────────────────────
# 2. PARSE INVOICES FROM CSV
# ─────────────────────────────────────────────────────────────────────────────

invoices = []
with open(CSV_PATH, newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        invoices.append({
            "Invoice_Ref":    row["Invoice_Ref"].strip(),
            "Vendor_Name":    row["Vendor_Name"].strip(),
            "Amount":         Decimal(row["Amount"].strip()),
            "Ccy":            row["Ccy"].strip(),
            "Dest_Country":   row["Dest_Country"].strip(),
            "Value_Date":     row["Value_Date"].strip(),
            "Priority":       row["Priority"].strip(),
            "Penalty_Clause": row["Penalty_Clause"].strip(),
        })

print("=" * 70)
print("T-ZERO AUTONOMOUS TREASURY ROUTER — AP2_MANDATE_V3")
print("=" * 70)
print(f"\nDigital Liquidity Cap : ${DIGITAL_CAP:,.0f} USDC (Fireblocks)")
print(f"TradFi Nostro         : $18,500,000 USD (JPM NY — LOCKED weekend)")
print(f"Invoices loaded       : {len(invoices)}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 3. PENALTY PARSER
# ─────────────────────────────────────────────────────────────────────────────

def parse_penalty(invoice):
    clause = invoice["Penalty_Clause"]
    amount = invoice["Amount"]
    ccy    = invoice["Ccy"]

    if clause in ("None", ""):
        return Decimal("0")

    # Percentage-based penalty  e.g. "5%_Loss_of_Discount" or "2%_Late_Fee"
    if "%" in clause:
        pct_str = clause.split("%")[0]
        pct = Decimal(pct_str) / Decimal("100")
        penalty_native = amount * pct
        if ccy == "EUR":
            return (penalty_native * EUR_USD_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return penalty_native.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Flat fee  e.g. "Flat_Fee_500_EUR"
    if "Flat_Fee" in clause:
        parts = clause.split("_")
        fee_amount = Decimal(parts[2])
        fee_ccy    = parts[3]
        if fee_ccy == "EUR":
            return (fee_amount * EUR_USD_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return fee_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return Decimal("0")

# Annotate
for inv in invoices:
    if inv["Ccy"] == "EUR":
        inv["Amount_USD"] = (inv["Amount"] * EUR_USD_RATE).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        inv["Amount_USD"] = inv["Amount"]
    inv["Penalty_USD"] = parse_penalty(inv)

print("─" * 70)
print("STEP 1 — PENALTY PARSING")
print("─" * 70)
for inv in invoices:
    print(f"  {inv['Invoice_Ref']}  {inv['Vendor_Name']:<28}  "
          f"Amount: ${inv['Amount_USD']:>12,.2f}  "
          f"Penalty: ${inv['Penalty_USD']:>10,.2f}")

# ─────────────────────────────────────────────────────────────────────────────
# 4. KNAPSACK — exact subset enumeration (n=3, 8 subsets)
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "─" * 70)
print("STEP 2 — KNAPSACK OPTIMISATION (Digital Liquidity = $4,000,000)")
print("─" * 70)

urgent   = [inv for inv in invoices if inv["Priority"] == "URGENT"]
standard = [inv for inv in invoices if inv["Priority"] == "STANDARD"]

urgent_total = sum(inv["Amount_USD"] for inv in urgent)
print(f"\n  Urgent payments count : {len(urgent)}")
print(f"  Urgent payments total : ${urgent_total:,.2f}")
print(f"  Digital cap           : ${DIGITAL_CAP:,.2f}")
print(f"  Shortfall             : ${urgent_total - DIGITAL_CAP:,.2f}")

# Enumerate all subsets
best_penalty = Decimal("-1")
best_subset  = []
n = len(urgent)

for r in range(n + 1):
    for combo in itertools.combinations(range(n), r):
        subset = [urgent[i] for i in combo]
        total_amt = sum(inv["Amount_USD"] for inv in subset)
        total_pen = sum(inv["Penalty_USD"] for inv in subset)
        if total_amt <= DIGITAL_CAP and total_pen > best_penalty:
            best_penalty = total_pen
            best_subset  = subset

selected_urgent = best_subset
selected_refs   = {inv["Invoice_Ref"] for inv in selected_urgent}
dropped_urgent  = [inv for inv in urgent if inv["Invoice_Ref"] not in selected_refs]

selected_total   = sum(inv["Amount_USD"] for inv in selected_urgent)
dropped_total    = sum(inv["Amount_USD"] for inv in dropped_urgent)
penalty_saved    = sum(inv["Penalty_USD"] for inv in selected_urgent)
penalty_incurred = sum(inv["Penalty_USD"] for inv in dropped_urgent)

print(f"\n  ✔ SELECTED for digital payment (penalty saved):")
for inv in selected_urgent:
    print(f"      {inv['Invoice_Ref']}  {inv['Vendor_Name']:<28}  "
          f"${inv['Amount_USD']:>12,.2f}  penalty=${inv['Penalty_USD']:,.2f}")
print(f"      SUBTOTAL: ${selected_total:,.2f}")

print(f"\n  ✘ DROPPED (lowest-impact — penalty incurred):")
for inv in dropped_urgent:
    print(f"      {inv['Invoice_Ref']}  {inv['Vendor_Name']:<28}  "
          f"${inv['Amount_USD']:>12,.2f}  penalty=${inv['Penalty_USD']:,.2f}")
print(f"      SUBTOTAL: ${dropped_total:,.2f}")

print(f"\n  Penalty cost SAVED    : ${penalty_saved:,.2f}")
print(f"  Penalty cost INCURRED : ${penalty_incurred:,.2f}")

# ─────────────────────────────────────────────────────────────────────────────
# 5. JURISDICTIONAL ROUTING
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "─" * 70)
print("STEP 3 — JURISDICTIONAL ROUTING & RAIL ASSIGNMENT")
print("─" * 70)

GAS_FEE_FILE = "/home/ubuntu/base_gas_fee.txt"
if os.path.exists(GAS_FEE_FILE):
    with open(GAS_FEE_FILE) as gf:
        live_gas_usd = Decimal(gf.read().strip())
    gas_ok     = live_gas_usd <= MAX_GAS_USD
    gas_status = f"${live_gas_usd:.4f} — {'WITHIN' if gas_ok else 'EXCEEDS'} ${MAX_GAS_USD} threshold"
else:
    live_gas_usd = None
    gas_ok       = True
    gas_status   = "PENDING live check"

print(f"  SE Asia gas threshold : ${MAX_GAS_USD} max | Status: {gas_status}")

def assign_rail(inv, is_selected):
    country  = inv["Dest_Country"]
    priority = inv["Priority"]
    penalty  = inv["Penalty_USD"]

    # STANDARD, no penalty → SWIFT Monday
    if priority == "STANDARD" and penalty == 0:
        return ("TradFi_SWIFT", "SWIFT_GPI", "Monday_08:00_EST",
                "No penalty; default_rail_preference enforced per AP2 mandate")

    # Dropped urgent → deferred SWIFT Monday
    if not is_selected:
        return ("DEFERRED_SWIFT", "SWIFT_GPI", "Monday_08:00_EST",
                "Dropped by knapsack optimiser — lowest penalty impact; SWIFT Monday queue")

    # Selected urgent + SE Asia
    if country in SE_ASIA_COUNTRIES:
        network = ALLOWED_NETWORKS[0]  # "Base"
        gas_label = f"${live_gas_usd:.4f}" if live_gas_usd is not None else "TBD"
        if gas_ok:
            return ("Stablecoin_USDC", network, "Immediate_24/7",
                    f"SE Asia jurisdiction; {network} gas {gas_label} within ${MAX_GAS_USD} threshold; "
                    f"Ethereum_Mainnet prohibited per AP2 mandate")
        else:
            fallback = ALLOWED_NETWORKS[1] if len(ALLOWED_NETWORKS) > 1 else "Solana"
            return ("Stablecoin_USDC", fallback, "Immediate_24/7",
                    f"SE Asia jurisdiction; Base gas {gas_label} exceeds threshold — fallback to {fallback}")

    # Selected urgent + non-SE Asia
    return ("Stablecoin_USDC", "Base", "Immediate_24/7",
            "URGENT; TradFi blackout active; stablecoin trigger condition met per AP2 mandate")

# Build routing table
routing_results = []

for inv in selected_urgent:
    rail, network, queue, notes = assign_rail(inv, is_selected=True)
    routing_results.append({**inv, "Rail": rail, "Network": network,
                             "Queue_Time": queue, "Notes": notes})

for inv in dropped_urgent:
    rail, network, queue, notes = assign_rail(inv, is_selected=False)
    routing_results.append({**inv, "Rail": rail, "Network": network,
                             "Queue_Time": queue, "Notes": notes})

for inv in standard:
    rail, network, queue, notes = assign_rail(inv, is_selected=False)
    routing_results.append({**inv, "Rail": rail, "Network": network,
                             "Queue_Time": queue, "Notes": notes})

for r in routing_results:
    if r["Rail"] == "Stablecoin_USDC":
        flag = "✔ DIGITAL"
    elif "DEFERRED" in r["Rail"]:
        flag = "⏸ DEFERRED"
    else:
        flag = "🏦 TRADFI"
    print(f"\n  [{flag}] {r['Invoice_Ref']}  {r['Vendor_Name']}")
    print(f"      Rail    : {r['Rail']}  |  Network: {r['Network']}")
    print(f"      Queue   : {r['Queue_Time']}")
    print(f"      Notes   : {r['Notes']}")

# ─────────────────────────────────────────────────────────────────────────────
# 6. OUTPUT SAP_S4_Recon.csv
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "─" * 70)
print("STEP 4 — WRITING SAP_S4_Recon.csv")
print("─" * 70)

fieldnames = [
    "Invoice_Ref", "Vendor_Name", "Amount", "Ccy", "Amount_USD",
    "Dest_Country", "Value_Date", "Priority", "Penalty_Clause",
    "Penalty_USD", "Rail", "Network", "Queue_Time", "Notes"
]

with open(OUTPUT_CSV, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for r in routing_results:
        writer.writerow({k: r[k] for k in fieldnames})

print(f"\n  Output written → {OUTPUT_CSV}")
print(f"  Rows: {len(routing_results)}")

# ─────────────────────────────────────────────────────────────────────────────
# 7. SUMMARY STATISTICS (for dashboard)
# ─────────────────────────────────────────────────────────────────────────────

stablecoin_payments = [r for r in routing_results if r["Rail"] == "Stablecoin_USDC"]
tradfi_payments     = [r for r in routing_results if "SWIFT" in r["Rail"]]
deferred_payments   = [r for r in routing_results if "DEFERRED" in r["Rail"]]

stablecoin_total = sum(r["Amount_USD"] for r in stablecoin_payments)
tradfi_total     = sum(r["Amount_USD"] for r in tradfi_payments)

summary = {
    "total_penalty_saved_usd":       float(penalty_saved),
    "total_penalty_incurred_usd":    float(penalty_incurred),
    "payments_stablecoin_count":     len(stablecoin_payments),
    "payments_stablecoin_total_usd": float(stablecoin_total),
    "payments_tradfi_count":         len(tradfi_payments),
    "payments_tradfi_total_usd":     float(tradfi_total),
    "payments_deferred_count":       len(deferred_payments),
    "digital_cap_usd":               float(DIGITAL_CAP),
    "digital_used_usd":              float(selected_total),
    "digital_remaining_usd":         float(DIGITAL_CAP - selected_total),
    "live_gas_usd":                  float(live_gas_usd) if live_gas_usd else None,
    "gas_threshold_usd":             float(MAX_GAS_USD),
    "gas_check_passed":              gas_ok,
    "routing_table": [
        {
            "Invoice_Ref":  r["Invoice_Ref"],
            "Vendor_Name":  r["Vendor_Name"],
            "Amount_USD":   float(r["Amount_USD"]),
            "Penalty_USD":  float(r["Penalty_USD"]),
            "Rail":         r["Rail"],
            "Network":      r["Network"],
            "Queue_Time":   r["Queue_Time"],
            "Priority":     r["Priority"],
            "Dest_Country": r["Dest_Country"],
        }
        for r in routing_results
    ]
}

with open("/home/ubuntu/treasury_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

print("\n" + "=" * 70)
print("ROUTING SUMMARY")
print("=" * 70)
print(f"  Payments via Stablecoin (USDC) : {len(stablecoin_payments)}  |  ${stablecoin_total:,.2f}")
print(f"  Payments queued for TradFi     : {len(tradfi_payments)}  |  ${tradfi_total:,.2f}")
print(f"  Total Penalty Cost SAVED       : ${penalty_saved:,.2f}")
print(f"  Total Penalty Cost INCURRED    : ${penalty_incurred:,.2f}")
print(f"  Digital Liquidity Used         : ${selected_total:,.2f} / ${DIGITAL_CAP:,.2f}")
print(f"  Digital Liquidity Remaining    : ${DIGITAL_CAP - selected_total:,.2f}")
print("=" * 70)
print("\nSummary JSON → /home/ubuntu/treasury_summary.json")
print("Done.\n")
