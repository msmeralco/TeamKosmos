# Sol demo script (10 minutes)

Run before going on stage: `python backend/scripts/demo_run.py` must pass for all three personas.

| Time | Step | What to show |
|---|---|---|
| 0:00 to 1:00 | Hook and problem | Residential rate up 16% since January. The 450 kWh household. Solar options are hard to compare and hard to understand. Three slides, each with a source line. |
| 1:00 to 2:45 | Meet Sol | Type a prepared address. The satellite map shows the roof outline. Adjust one corner. |
| 2:45 to 5:00 | Ask and answer | Give the bill, budget and goal in chat. Show the live product feed. Sol returns three packages. |
| 5:00 to 6:45 | Compare | ROI table: grid only vs on-grid vs hybrid. Flip the net-metering toggle. Show the best-case and bad-year range and the 25-year cash flow. |
| 6:45 to 7:45 | Show the math | Open the math drawer: sources, assumptions, export credit approximation, scenario definitions. |
| 7:45 to 9:15 | Passport | Issue the Passport, scan the QR, open the verify page, show the green check. Optionally change one digit in the downloaded record and show verification fail. |
| 9:15 to 10:00 | Close | "Compare honestly. Understand clearly. Verify openly." |
| Q&A (5 min) | | See section 13 of `context/IMPLEMENTATION_PLAN.md`. |

## If something fails

Say so, then switch to the recorded video at the same step. The video is chaptered by the rows above.

- LLM busy: use the forms path, which works without the LLM.
- Network down: use the phone hotspot. Demo outlines and PVGIS files are bundled.
- Scraper empty: cached and seed prices are shown with a "cached, last checked" label.
