# T-Zero: Event-Driven Omni-Asset Treasury Router
**Manus × Vibecoding Consulting Hackathon Submission**

T-Zero solves the multi-billion-dollar inefficiency of trapped weekend liquidity in B2B cross-border payments. 

Instead of relying on humans or simple IF/THEN automation, T-Zero uses an autonomous agentic workflow driven by a strict **"Policy-as-Code" JSON mandate** (`AP2_Mandate_V3.json`) to enforce cryptographic risk limits.

### 🧠 The Autonomous Logic
When legacy SWIFT rails go offline, the agent autonomously:
1. **Parses complex vendor SLAs** from legacy CSVs.
2. **Solves the Knapsack Problem** under limited digital liquidity by calculating penalty logic.
3. **Performs live-web network gas checks** to ensure blockchain routing is cost-effective.
4. **Dynamically routes urgent payments** via Web3 stablecoin rails (USDC) while smartly queuing standard payments via TradFi SWIFT.
5. **Generates SAP S/4HANA double-entry accounting files** (`SAP_S4_Recon.csv`) to reconcile the general ledger.

### 📂 Repository Structure
* `AP_Run_V3.csv` - The raw, messy Accounts Payable ledger.
* `AP2_Mandate_V3.json` - The cryptographic governance rules.
* `Treasury_Positions.xlsx` - Simulated live balances (TradFi & Custody).
* `treasury_router.py` - The deterministic Python code autonomously generated and executed by Manus.
* `index.html` - The generated CFO Command Center UI.

### 🎥 Watch the Demo
[Insert Link to your 2-Minute Loom Video Here]
