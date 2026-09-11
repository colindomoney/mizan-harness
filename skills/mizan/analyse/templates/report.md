# Mizan points-of-interest report
batch: <dir> · runs: <ids> · bank: <id> · models: <list>
judge: <model id> · skill version: <x.y> · prep script sha: <short sha> · generated: <ISO8601>

## 1. Inventory
<table from summary.md §A>

## 2. Data quality
<bullets: truncation, identical cells, flag noise, coverage gaps; each with cell_ids>
Excluded from findings because of the above: <cell_ids or "none">

## 3. Findings
### F1. <one-line claim>
Replication: <replicates 5/5 | partial 2/5 | single-run | n/a (one run available)>
Evidence:
- <cell_id> — "<quote ≤25 words>"
- <cell_id> — "<quote ≤25 words>"
Metric: <the summary.md number(s) this rests on>
Would be falsified by: <one line>
### F2 … F5 (same shape)

## 4. Pair asymmetry table
<from summary.md §C, models as columns, pairs as rows>

## 5. Lexicon table
<from summary.md §E and §G, categories as rows, model×run as columns>

## 6. Figures table
<from summary.md §F>

## 7. Watchlist for next batch
- <single-run or partial finding> — confirm/refute by <what to look at>
- …

## 8. Suggested metrics / lexicon additions
<anything the judge wanted and couldn't get from the script>
