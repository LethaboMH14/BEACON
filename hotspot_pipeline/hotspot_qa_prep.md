# **Claims Hot-Spot Map — Interview Q&A Prep** 

_Anticipated hiring-manager / judge questions on data cleaning, hot-spot logic, and the severity score — with grounded answers using real figures from the dataset_ 

All figures below are pulled directly from the actual cleaned dataset (15,712 claim rows) and the resulting hot-spot table (764 qualifying suburbs), not illustrative examples. Use these as talking points — they're accurate as of the current pipeline run. 

## **Section 1 — Data Cleaning** 

### **<mark>Q1. How was the data cleaned?</mark>** 

Five specific steps were applied to the raw 15,712-row claims file: 

- **Dates parsed** — the incident timestamp was broken into hour, day of week, and month, so time-based patterns could be grouped later. 

- **Missing claim categories backfilled** — 196 rows (mostly Armed Robbery claims) had no item category recorded. These were filled in using the naming pattern already present elsewhere in the data, and every backfilled row was explicitly flagged so the fix is auditable, not silent. 

- **Missing locations flagged, not deleted** — 651 rows had no suburb. Rather than dropping them (which would lose real incident data), they were kept and flagged, so they still contribute to overall pattern analysis but are excluded from any suburb-level or map-based view. 

- **Invalid claim amounts flagged** — 81 rows had a claim amount of zero or below, which doesn't make sense as a real claim value. These were flagged and excluded specifically from cost calculations, while still being counted as a real incident for frequency purposes. 

- **Location text standardized** — suburb names were trimmed and uppercased so that formatting differences wouldn't cause the same place to be counted as two different locations. Checking this against the actual data confirmed the suburb names were already consistent — no duplicates needed merging. 

### **<mark>Q2. Why fag data instead of just deletng it?</mark>** 

Deleting incomplete rows would quietly shrink the dataset and lose real signal — a claim with a missing suburb still represents a real incident that happened, and still contributes to citywide or peril-type patterns even if it can't be placed on a map. Flagging keeps every row in the dataset while making it explicit which calculations that row should or shouldn't be part of. This is also a transparency choice: anyone auditing the pipeline can see exactly which rows were touched and why, rather than trusting that a silent deletion was reasonable. 

### **<mark>Q3. Why were 81 rows with zero or negatve claim amounts kept in the dataset at all?</mark>** 

Because the incident itself is still real — someone filed a claim for a genuine event, even if the dollar figure recorded looks like a data error (likely a reversal, recovery, or entry mistake, though the exact cause isn't documented in the source file). Removing the row would understate how often crime occurs in that suburb. Keeping it in the frequency count but excluding it from cost/severity math is the accurate middle ground. 

### **<mark>Q4. What would you do diferently with more tme or a data dictonary?</mark>** 

Two things specifically: confirm with Discovery what the negative claim amounts actually represent (rather than assuming), and geocode by suburb plus province instead of suburb name alone, which would remove the small risk of matching a same-named suburb in the wrong part of the country. 

## **Section 2 — Incident Counts by Suburb** 

### **<mark>Q5. How is the number of incidents in a partcular suburb determined?</mark>** 

Every cleaned claim row that has a valid suburb is grouped by that suburb name, and the incident count is simply the number of claim rows in that group. For example: **Johannesburg has 110 incidents, Somerset West has 107, Rondebosch has 102** — these are direct counts straight from the claims data, not estimates. 

### **<mark>Q6. Why is there a minimum threshold for a suburb to count as a hot-spot?</mark>** 

The full dataset has 2,929 unique suburb names, but most have only one or two incidents each — that's noise, not a meaningful pattern. A minimum of 5 incidents was set before a suburb is treated as a genuine recurring hot-spot. That threshold keeps 764 suburbs, which still covers about 75% of all usable claims, while filtering out one-off, statistically unreliable locations. 

### **<mark>Q7. Isn't a suburb with more incidents always the bigger risk?</mark>** 

Not necessarily, which is exactly why incident count alone isn't used as the final risk measure — see the severity score section below. A high incident count means the crime happens often there, but says nothing about how costly or severe those incidents are. 

## **Section 3 — Top Claim Types** 

### **<mark>Q8. How is the 'top claim type' for a suburb determined?</mark>** 

For each suburb, every claim's peril type (Theft, Hijack, Armed Robbery, Burglary, etc.) is counted, and whichever type occurs most often in that suburb is reported as its top claim type, along with how many times it occurred. Across the dataset as a whole, Theft is overwhelmingly the most common peril — 14,380 of the 15,712 total claims — so it's the top claim type for the large majority of hot-spot suburbs too. 

### **<mark>Q9. If Thef dominates almost everywhere, how useful is the top claim type feld?</mark>** 

Fair challenge — the full claim-type breakdown (not just the top one) is what carries the real signal. Each hot-spot suburb stores every peril type present and its count, not just the single most common one, so a suburb that's mostly Theft but also has a notable share of Hijack or Armed Robbery claims still surfaces that detail. The top claim type is a quick-glance summary; the full breakdown is what supports a deeper investigation. 

### **<mark>Q10. Which suburbs have hijacking or armed robbery as a leading patern, not just thef?</mark>** 

This is answerable directly from the full claim-type breakdown stored per suburb, by filtering for suburbs where Hijack or Armed Robbery makes up a large share of their total incidents rather than just checking the single top type — a natural next step for the analysis, and a good demonstration of the data's depth beyond the headline number. 

## **Section 4 — Peak Time** 

### **<mark>Q11. How is the 'peak tme' for a suburb determined?</mark>** 

Three separate time dimensions are calculated per suburb: the month that has the most incidents, the day of the week that has the most incidents, and the specific hour of the day that has the most incidents — each computed independently from the parsed date/time fields. For example, in the current data, Bryanston's incidents peak in May, on Fridays, around midday (hour 12), while Rondebosch's peak at midnight on Saturdays. 

### **<mark>Q12. Why calculate month, day of week, and hour separately instead of one combined 'peak tme'?</mark>** 

Each dimension answers a different practical question. Peak hour tells a resident or security patrol when in the day to be most cautious. Peak day of week supports scheduling patrol shifts. Peak month can reveal seasonal patterns — useful for planning ahead of high-risk periods. Combining them into one figure would lose that granularity and make the output less actionable. 

### **<mark>Q13. With relatvely small incident counts per suburb, how reliable is a 'peak hour'?</mark>** 

This is a genuine limitation worth being upfront about. A suburb with exactly 5 incidents (the minimum threshold) could show a 'peak hour' based on just one or two claims landing in the same hour by chance, which isn't statistically strong evidence of a true pattern. This is more reliable for higher-volume suburbs — the ones with dozens or more incidents, like the current top-ranked hot-spots — and should be treated as indicative rather than definitive for lower-volume ones. Flagging incident count alongside the peak time in any UI or report is the honest way to convey this. 

## **Section 5 — Severity Score** 

### **<mark>Q14. How is the severity score calculated?</mark>** 

It combines two things in equal measure: how often incidents happen in that suburb, and how much they cost in total. 

- ●Incident count is scaled to a 0–1 range across all hot-spot suburbs (the suburb with the most incidents scores closest to 1, the suburb with the fewest scores closest to 0). 

- ●Total claim cost — using only the valid, non-anomalous claim amounts — is scaled to a 0–1 range the same way. 

- ●The two scaled scores are averaged equally: severity score = 0.5 × frequency score + 0.5 × cost score. 

### **<mark>Q15. Why combine frequency and cost instead of just ranking by incident count?</mark>** 

Because the two can tell different stories. In the current data, **Garsfontein has only 57 incidents — fewer than several other hot-spots — but an average claim cost of roughly R183,000, nearly double most other top suburbs, giving it a severity score of 0.75** . A ranking based on incident count alone would rank it well below higher-volume, lower-cost suburbs, even though the financial exposure there is significantly worse per incident. The combined score surfaces suburbs like this that a simple frequency count would under-rank. 

### **<mark>Q16. Is the 50/50 weightng between frequency and cost the 'right' answer?</mark>** 

No — and this is worth being direct about: it's a deliberate but adjustable design choice, not something derived mathematically from the data. It reflects a judgment that frequency and financial severity matter equally for prioritizing attention. A different priority — for example, minimizing total financial loss versus reducing how often crime occurs at all — would justify a different weighting, such as 70% cost-weighted or 70% frequency-weighted. The weighting is a single configurable variable in the code, so it can be adjusted and the map regenerated to show how the ranking shifts under a different priority. 

### **<mark>Q17. What does the top of the current severity ranking actually look like?</mark>** 

The three highest-severity suburbs currently are Bryanston (score 0.85, 89 incidents, ~R9.45 million total claim cost), Somerset West (score 0.77, 107 incidents, ~R6.03 million total), and Johannesburg (score 0.77, 110 incidents, ~R5.6 million total) — Bryanston ranks first despite fewer raw incidents than the other two, specifically because its average claim cost is significantly higher. 

### **Q18. Could the severity score be manipulated or gamed — for example, by an insurer wanting to justify higher premiums in an area?** 

The inputs (incident count and total claim cost) come directly and only from the historical claims data — there's no manual override or subjective input at the suburb level, so an individual suburb's score can't be hand-adjusted without editing the underlying claims themselves. The one place where judgment enters is the 50/50 weighting decision discussed above, which is applied uniformly across every suburb, not selectively. That said, this is a fair question to flag honestly in any real deployment — any automated risk-scoring system that could influence pricing or resource allocation should have a documented review process, not just a running script. 

## **Section 6 — The Map Itself** 

### **<mark>Q19. How does the data become the actual map people see?</mark>** 

Each qualifying hot-spot suburb name is converted to map coordinates using a free, public geocoding service (OpenStreetMap's Nominatim), then plotted as a marker using Leaflet, an open-source mapping library. Marker color and size are both driven by the severity score — red and larger for the highest-severity hot-spots, yellow and smaller for lower-severity ones — so the riskiest areas are visually the most prominent without needing to read every number. 

### **<mark>Q20. Does the map update automatcally as new claims come in?</mark>** 

Not automatically in the current build — it's generated from a snapshot of the cleaned data at the time the pipeline is run. Making it continuously live would mean scheduling the cleaning-and-aggregation pipeline to re-run periodically (the same pattern already used for the other live data sources in this project, like load-shedding and weather), then regenerating the map from the fresh output. That's a natural next step, not a current limitation being hidden. 

