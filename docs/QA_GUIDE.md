## Product

**Isn't this just a solar calculator?**
A calculator gives one number from a form. Sol takes a roof from an address, simulates it hour by hour over 16 weather years, builds options to your budget and goal, and issues a Passport that earns rewards for going solar.

**What is the Passport?**
Your proof of going solar. Sol issues it with your plan and signs it. Your installer confirms the install, and then it unlocks vouchers and discounts. It does not prove your real roof or usage. Those are inputs.

**What can't it do?**
Electrical design, shading, multi-plane roofs and permits. A licensed installer confirms every result.

**What would you build next?**
Multi-plane roofs and shading from imagery, real meter data that unlocks usage rewards, and installer quotes.

## Picking parts and installers

**How does Sol choose parts?**
The optimizer filters a catalog by what fits your roof, your budget and your goal, then ranks what's left. The model doesn't invent parts. It can only pick from the catalog. This is built.

**How does it choose an installer?**
It compares quotes on price against your budget and on what each one covers, such as the permit and net-metering filing. This is a proposal. The installers on the slide are samples, and none has agreed to take part.

**Why did it skip the battery?**
At these prices the battery doesn't pay for itself within ten years. It buys backup power, and Sol picks it if backup is your goal.

## Rewards

**What are the vouchers?**
Signed codes tied to one Passport, issued after the install is confirmed. Examples are a free site survey or an installer discount on the recommended package. Values are samples until a partner funds them.

**Can someone fake or reuse one?**
The code comes from Sol's signature, so it can't be invented. It is only issued after the install is confirmed, and it redeems once.

**Is this a Meralco reward?**
No. Meralco is not involved and Sol promises no Meralco benefit. Vouchers have no cash value.

**Who pays for them?**
Today nobody, because the values are samples. The idea is that installers or retailers fund them, because they get a customer who arrives with a layout and a checked price. That is a pitch, not an agreement.

**Why not points or tiers?**
They need a program owner and rules we can't make up. A voucher works with one Passport and needs no account.

**How would usage rewards work?**
A monthly generation reading from a REC meter would be added to the Passport, and the usage reward would unlock. The demo has no meter data, so that reward shows as locked.

## Numbers and trust

**What stops the AI from making up numbers?**
It can't calculate. Numbers come from tools, and a check compares the AI's text against the tool results.

**Why 10 years?**
Ten years is the horizon for every figure, so the comparison is easy to read. A payback longer than 10 years shows as "not within 10 years".

**Does the battery pay for itself?**
Not within 10 years in our example. The battery adds ₱89k to ₱155k and saves roughly ₱50k to ₱110k of bills, so solar alone is cheaper. The battery buys backup power. The 80% self-use share with a battery is our assumption, and it decides this result.

**Where do the deck's comparison numbers come from?**
A small illustrative model for one 450 kWh household (our example family, bigger than Meralco's typical 200 kWh household), using the published ₱45 to ₱75 per watt, the Meralco October rate and PVGIS weather years. It assumes a flat tariff and no upkeep. The app runs the real hourly simulation.

**How do you handle net-metering credit?**
Exports earn a credit based on Meralco's blended generation cost, not the retail rate. We use the published charge, let you edit it, and show a lower-credit case.

**How accurate is the weather data?**
PVGIS-ERA5 is a modeled dataset, and we label it that way. That's why Sol shows a best case and a bad year.

**Where do prices come from?**
Public retailer listings, with source and time on each. If a fetch fails, we show cached prices labeled as cached. Always confirm with the seller.

**Is anything verified in the real world?**
Not in the demo. Results are modeled estimates for synthetic households, and the Passport says so.

## Impact

**How does this help customers?**
They get a range instead of one number, a plain answer on what exports earn, rule answers with source links, and a Passport that earns vouchers and discounts for going solar. This is built.

**How does this help business owners?**
Installers and sellers get a customer who arrives with a layout, a price and checked assumptions. They open the same Passport link as a quote brief, confirm the install, and redeem vouchers with a code. The Passport page and redeem route are built. Partner funding is our pitch.

**How does this help Meralco?**
Customers arrive knowing how exports are credited and which grid pathway applies. There is a record to point to when referring them to a listed installer, which steers them toward registered installs. This is a next step, not a built feature, and Sol promises no Meralco benefit.

**Why would a household trust it?**
Prices show sources, outputs show ranges, the math is open, rule answers link to their source, and the Passport shows its sources.

**Are the installers "Meralco accredited"?**
Demo installers are synthetic. We haven't found a citable Meralco list, so we'd say "listed installers" until we do.

## Technical

**What was hardest?**
Hourly battery dispatch across many weather years, an optimizer constrained by budget and roof size, reliable live price fetching, and a signed Passport with install confirmation.

**Why RAG?**
It gives the agent Meralco and DOE rules with source links, so it doesn't answer rule questions from memory. RAG supplies facts only. Numbers come from the tools.

**What's in the document library?**
Meralco tariff and net-metering pages, the DOE circular DC2026-08-0017 and product pages, stored locally with keyword search as a fallback.

**What if the document search gets it wrong?**
Every answer shows its source passage and link, so you can check it. Anything it can't find, it says it can't find.

**What if the AI or the internet fails?**
The forms and buttons use the same API as the chat, so the app still works. Prices and weather data fall back to cached files.

## Data and rules

**Is customer data safe?**
The demo uses synthetic data. Uploads are processed per session and not stored.

**Did you write this inside the code window?**
Yes. All code was written between 9:00 AM Nov 12 and 9:00 AM Nov 13. Before that we only planned and collected data.
