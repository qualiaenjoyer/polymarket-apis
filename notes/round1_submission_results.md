# Round 1 state-filter live results log

Date logged: 2026-04-14

## Live scores (user reported)

- submission_10_fill_streak: **3491**
- submission_12_adverse_selection: **3470**
- submission_14_flow_cap: **3470**
- submission_11_inventory_age: **3088**
- submission_13_flatten_cycle: **2930**

## Relative ranking

1. submission_10_fill_streak (best)
2. submission_12_adverse_selection (tie)
3. submission_14_flow_cap (tie)
4. submission_11_inventory_age
5. submission_13_flatten_cycle

## Immediate takeaways

- Fill-streak gating appears to be the only state filter that produced a clear live uplift over the 3470 cluster.
- Adverse-selection and flow-cap filters were effectively neutral in this run (same score bucket).
- Inventory-age and flatten-cycle filters were too restrictive and likely removed profitable continuation flow.
- Next tuning should focus on narrow sweeps around submission_10 behavior, while keeping quote placement unchanged.
