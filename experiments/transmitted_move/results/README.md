# Transmitted-move replay

One MNQ on 27 previously exposed sessions. Each control uses the candidate's accepted timings.
A flat control pays no friction. Standalone continuation and fade each manage their own position.
Attribution rows retain only that signal type from the accepted combined ledger.
The overlapping return labels in the JSON use every priced opportunity.

| Extra seconds | Portfolio | Fills | Gross USD | Net $3 | Net $6 | Net $9 | $9 net less top 3 | $6 close DD | $6 observed intrabar DD | Missing held seconds |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---:|
| 0 | combined | 3127 | -949.00 | -10,330.00 | -19,711.00 | -29,092.00 | -29,540.00 | 19,893.50 | 19,896.50–19,896.50 | 324 |
| 0 | continuation_standalone | 2337 | -102.50 | -7,113.50 | -14,124.50 | -21,135.50 | -21,569.50 | 14,177.00 | 14,180.50–14,180.50 | 220 |
| 0 | continuation_attribution | 1583 | -1,016.50 | -5,765.50 | -10,514.50 | -15,263.50 | -15,711.00 | 10,566.00 | 10,569.50–10,569.50 | 180 |
| 0 | fade_standalone | 2369 | -107.50 | -7,214.50 | -14,321.50 | -21,428.50 | -21,781.00 | 14,416.50 | 14,420.00–14,420.00 | 202 |
| 0 | fade_attribution | 1544 | 67.50 | -4,564.50 | -9,196.50 | -13,828.50 | -14,152.50 | 9,463.00 | 9,466.00–9,466.00 | 144 |
| 1 | combined | 3085 | -211.00 | -9,466.00 | -18,721.00 | -27,976.00 | -28,473.50 | 18,812.50 | 18,815.00–18,815.00 | 319 |
| 1 | continuation_standalone | 2309 | 827.00 | -6,100.00 | -13,027.00 | -19,954.00 | -20,405.00 | 13,175.50 | 13,179.50–13,179.50 | 217 |
| 1 | continuation_attribution | 1542 | -573.50 | -5,199.50 | -9,825.50 | -14,451.50 | -14,847.00 | 9,874.50 | 9,878.00–9,878.00 | 174 |
| 1 | fade_standalone | 2344 | -6.50 | -7,038.50 | -14,070.50 | -21,102.50 | -21,463.00 | 14,153.00 | 14,156.50–14,156.50 | 201 |
| 1 | fade_attribution | 1543 | 362.50 | -4,266.50 | -8,895.50 | -13,524.50 | -13,932.50 | 9,116.00 | 9,118.50–9,118.50 | 145 |
| 9 | combined | 2833 | -1,126.00 | -9,625.00 | -18,124.00 | -26,623.00 | -26,985.50 | 18,171.50 | 18,174.50–18,174.50 | 293 |
| 9 | continuation_standalone | 2158 | 696.50 | -5,777.50 | -12,251.50 | -18,725.50 | -19,194.50 | 12,306.00 | 12,310.00–12,310.00 | 214 |
| 9 | continuation_attribution | 1409 | -820.00 | -5,047.00 | -9,274.00 | -13,501.00 | -13,703.00 | 9,308.00 | 9,311.00–9,311.00 | 181 |
| 9 | fade_standalone | 2183 | 1,867.00 | -4,682.00 | -11,231.00 | -17,780.00 | -18,512.00 | 11,401.00 | 11,406.50–11,406.50 | 186 |
| 9 | fade_attribution | 1424 | -306.00 | -4,578.00 | -8,850.00 | -13,122.00 | -13,484.50 | 8,934.50 | 8,937.50–8,937.50 | 112 |
| 60 | combined | 1876 | -760.00 | -6,388.00 | -12,016.00 | -17,644.00 | -18,072.00 | 12,069.50 | 12,073.50–12,073.50 | 208 |
| 60 | continuation_standalone | 1537 | -267.50 | -4,878.50 | -9,489.50 | -14,100.50 | -14,438.50 | 9,527.00 | 9,531.50–9,531.50 | 163 |
| 60 | continuation_attribution | 948 | -841.50 | -3,685.50 | -6,529.50 | -9,373.50 | -9,633.50 | 6,533.00 | 6,537.00–6,537.00 | 104 |
| 60 | fade_standalone | 1563 | 615.50 | -4,073.50 | -8,762.50 | -13,451.50 | -13,902.50 | 8,789.50 | 8,792.00–8,792.00 | 150 |
| 60 | fade_attribution | 928 | 81.50 | -2,702.50 | -5,486.50 | -8,270.50 | -8,673.50 | 5,580.50 | 5,587.50–5,587.50 | 104 |

The drawdown interval accounts for unknown high–low order inside observed seconds.
It cannot bound prices during gaps or establish a trailing-account drawdown.
Paired intervals use all 27 scheduled days, 10,000 five-session circular-block draws and seed 604. Values are daily dollars.

| Extra seconds | Cost | Control | Candidate difference, total USD | Paired 95% daily interval |
|---:|---:|---|---:|---:|
| 1 | 6 | cash | -18,721.00 | [-890.30, -485.63] |
| 1 | 6 | leader | +725.00 | [-67.56, +122.33] |
| 1 | 6 | always_long | +71.00 | [-54.15, +63.41] |
| 1 | 6 | mnq_body | -1,155.00 | [-107.63, +25.74] |
| 1 | 6 | anchor_midpoint | +668.00 | [-47.19, +98.70] |
| 1 | 9 | cash | -27,976.00 | [-1,305.01, -747.42] |
| 1 | 9 | leader | +725.00 | [-67.56, +122.33] |
| 1 | 9 | always_long | +71.00 | [-54.15, +63.41] |
| 1 | 9 | mnq_body | -2,085.00 | [-144.52, -7.39] |
| 1 | 9 | anchor_midpoint | +413.00 | [-56.96, +90.02] |
| 9 | 6 | cash | -18,124.00 | [-839.81, -503.00] |
| 9 | 6 | leader | -612.00 | [-161.89, +91.75] |
| 9 | 6 | always_long | -435.00 | [-139.00, +102.11] |
| 9 | 6 | mnq_body | -1,415.00 | [-110.13, +9.13] |
| 9 | 6 | anchor_midpoint | +759.50 | [-30.35, +85.57] |
| 9 | 9 | cash | -26,623.00 | [-1,222.34, -745.44] |
| 9 | 9 | leader | -612.00 | [-161.89, +91.75] |
| 9 | 9 | always_long | -435.00 | [-139.00, +102.11] |
| 9 | 9 | mnq_body | -2,213.00 | [-141.98, -18.96] |
| 9 | 9 | anchor_midpoint | +525.50 | [-39.71, +76.85] |

**Frozen promotion gate:** failed.

[Full results](summary.json) · [Daily returns](daily.csv) · [Accepted orders](accepted-orders.csv.gz) · [Case chart](cases.html) · [Source checksums](schedule.json)
