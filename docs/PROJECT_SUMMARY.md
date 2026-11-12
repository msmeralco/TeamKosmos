# Sol: Your Clean Energy Partner

Team Kosmos, IDOL Hackathon 2026. Challenge 1: Clean Energy Adoption and Rewards.

## What Sol does
Tell Sol your roof, your bill, your budget and your goal. It returns two or three solar options, a 10-year cost comparison with a best case and a bad year (a 25-year cash flow sits behind it), and a Solar Passport: your proof of going solar, which earns vouchers and discounts once an installer confirms the install.

## The problem
- Meralco's typical household rate rose 16% from January to October 2026 (₱12.95 to ₱15.06 per kWh).
- Published installed prices run from ₱45 to ₱75 per watt. Buyers can't tell a qualified quote from a cheap one.
- Exports are credited below the retail rate. Without a REC meter, generation is estimated by formula. Few people know this before they buy.

## How it works
1. **Roof:** type an address. Sol outlines the roof from OpenStreetMap on a satellite map. Adjust it, or draw it by hand.
2. **Chat:** give your bill, budget and goal (cut the bill, best 10-year savings, fastest payback, blackout backup).
3. **Prices:** Sol reads 3 to 5 retailer sites. Each price shows its source and time. Cached prices are labeled.
4. **Options:** the optimizer builds the top 2 or 3 parts lists within budget, goal and roof size.
5. **Simulation:** pvlib with PVGIS-ERA5 hourly weather, run hour by hour against an estimated household load.
6. **ROI table:** grid only, solar, and solar with battery over 10 years. Toggle net metering, edit the buyback rate, see payback and the 25-year cash flow.
7. **Layout, Passport and rewards:** a 2D panel layout, then the Solar Passport. After an installer confirms the install, it unlocks vouchers and discounts.
8. **Ask the rules:** Sol answers questions about net metering, tariffs and the DOE circular from a local document library (RAG), with source links.

## Solar Passport
Your proof of going solar. Sol issues it with your plan and signs it. An installer confirms the install, and the confirmed Passport unlocks rewards. Three stages: plan, installed, redeemed.

## Solar Rewards
A confirmed Passport earns vouchers and discounts, for example a free site survey or an installer discount on the recommended package. Each voucher is a signed code tied to one Passport and redeems once. Values are sample values until a partner funds them. Vouchers have no cash value, and Sol promises no Meralco benefit. A usage reward, unlocked by real generation data, is a next step.

## RAG (document search)
A local library of Meralco tariff and net-metering pages, the DOE circular and product pages. The agent searches it and gets back passages with source links. RAG gives facts and citations only; every number comes from the tools.

## Who benefits
| Who | What they get | Status |
|---|---|---|
| **Customers** | An honest range instead of one number, what net metering really credits, rule answers with sources (RAG), and a Passport that earns vouchers and discounts for going solar. | Built |
| **Business owners** (installers, sellers) | A customer who arrives with a layout, a price and checked assumptions. The same Passport link works as a quote brief, and vouchers redeem with a code. | Passport page and redeem built; partner funding is a pitch |
| **Meralco** | Better-prepared customers who know how exports are credited and which grid pathway applies, and a record to point to in referrals to accredited installers. | Pitch only. No integration, no promised benefit |

## Rules we hold ourselves to
- The AI never does math. It calls tools, and the math panel shows sources.
- Exports are credited at an editable monthly generation charge, with a lower-credit sensitivity.
- Embodied carbon appears only when published. Otherwise it reads "not disclosed".
- A local document search (RAG) gives the agent Meralco and DOE facts with source links.
- Every result is an estimate for a licensed installer to confirm. Demo data is synthetic.
- Reward values are samples. A voucher is a signed code, not money, and not an offer from Meralco.

## Build tiers
| Tier | Target | Scope |
|---|---|---|
| 1 | Hour ~14 | Address and drawing on satellite map, simulation, ROI table with ranges, chat agent with tool calls |
| 2 | Hour ~20 | Optimizer, live product fetch with cache, 2D layout, Passport with vouchers, sketch canvas |
| 2b | Hour ~22 | Document search (RAG) tool for the agent |
| 3 | Stretch | Photo or blueprint auto-outline, battery polish, 3D view |

Cut from the bottom. Feature freeze 6:00 AM Nov 13.

## Event rules
- Code only between 9:00 AM Nov 12 and 9:00 AM Nov 13. Planning, installs and data gathering before that are allowed.
- Submit the repo link before 9:30 AM Nov 13.
- Pitch: 10 minutes plus 5 minutes Q&A, built around a working demo.
- Judging: Innovation 30, Functionality 25, Impact 20, Technical Challenge 15, Presentation 10.
- Plagiarism and privacy breaches mean disqualification. Use no real customer data.

## Before the code window
- Make one Gemini test call with an image and a function call.
- Pick 3 to 5 demo addresses and confirm OpenStreetMap has an outline for each.
- Shortlist 3 to 5 retailer sites and check robots.txt and terms.
- Pull the latest Meralco generation charge and typical rate.
- Build a starter catalog of panels, inverters and batteries.
- Plan a backup demo video in case venue wifi fails.

## Open items
- Meralco's exact export-credit figure.
- Which Gemini model supports image input and function calling on our key.
- OpenStreetMap coverage for the demo addresses.
- Whether a citable list of Meralco-accredited installers exists. Until then, say "listed installers".
