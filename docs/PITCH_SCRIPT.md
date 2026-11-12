Sol Pitch Script (7 minutes, then a 3-minute demo video)

Bracketed numbers like [1] point to the references at the end. Say the source name out loud for the main figures (Meralco, the DOE, GoSolar PH).

Slide 0: Title (0:00 to 0:11)

Good day, everyone. We are Team Kosmos, and this is Sol, an AI agent that helps a household go solar.

Slide 1: Hook (0:11 to 0:45)

Electricity bills for Meralco customers keep climbing. According to Meralco's rate advisories, the overall rate for a typical household was ₱12.95 per kilowatt-hour in January 2026 [2] and reached ₱15.06 in October [1], which is 16 percent higher. Meralco treats a typical household as one that uses 200 kilowatt-hours a month [1], so that household's bill has gone from about ₱2,590 to about ₱3,010. With numbers like these, more families are asking whether solar can bring the bill down.

Slide 2: Compare (0:45 to 1:20)

Once a family starts looking, the first problem is the number of choices. Published installed prices run from ₱45 to ₱75 per watt [3][4], so three sellers can offer setups that look identical on paper [3]. Buyers also have good reason to be careful, because the Department of Trade and Industry has said that substandard solar products are entering the market and is looking at mandatory certification [5]. As a result, an ordinary buyer has very little to go on when choosing a supplier.

Slide 3: Understand (1:20 to 2:11)

Even after choosing a seller, solar remains overwhelming for the average consumer, mostly because there is so much to learn. Your panels power your home first, and any extra power goes to the grid. Meralco credits that export at its monthly blended generation cost, which is lower than the full retail rate you pay when you buy power back at night [6]. The family also faces several paths, namely net metering, a zero-export system or a micro solar system, and each one has its own paperwork [6][8]. Net metering alone has six stages and an ERC compliance fee of ₱1,500 [7]. Finally, a household that declines the optional REC meter has its solar generation estimated with an approved method [6].

Slide 4: Meet Sol (2:11 to 2:44)

This is why we built Sol, an AI agent that does three jobs for a household. First, it helps map the installation site. Second, it recommends a solar supplier or installer. Third, it recommends and compares solar packages. Everything starts with your address. Sol drops a pin on the map, outlines the installation site and measures it, and in our example eight panels fit. Every number you see afterward comes from that measured site.

Slide 5: Ask (2:44 to 3:10)

After the site is mapped, we simply talk to Sol. Our example household uses more power than Meralco's typical 200 kilowatt-hour home [1]. It pays ₱6,780 a month, which Sol converts to about 450 kilowatt-hours, it has a budget of up to ₱300,000, and it wants a lower bill. With those three details, Sol can compare the household's options.

Slide 6: Compare options (3:10 to 3:59)

Sol first compares three paths: staying on the grid, going solar, and going solar with a battery. Sol shows a range of outcomes, because a single number would hide the uncertainty in prices and weather. Over ten years in our model, staying on the grid costs about ₱813,000, solar lands between ₱248,000 and ₱457,000, and solar with a battery lands between ₱287,000 and ₱502,000. The spread comes from two things, the price the household is quoted [3] and the weather year it gets [11]. The battery adds backup power, but at these prices it does not pay for itself within ten years. The model uses Meralco's October rate of ₱15.06 [1] and hourly PVGIS sunlight data [11].

Slide 7: Sol picks (3:59 to 5:12)

Next comes the recommendation. From the site and the budget, Sol works out the size this home needs, about 4.4 kilowatts without a battery. It then searches the ready-made packages that installers publish on their own websites and keeps the ones that fit. In our example, the cheapest is PTG Solar's package at ₱177,700, but its page does not say whether permits and net-metering paperwork are included [10]. Triple30's 5-kilowatt package starts at ₱285,000, which stays inside the ₱300,000 budget, and it includes permit processing, so Sol picks it [10]. DevSolutions' hybrid package starts at ₱337,000, which is over budget [10].

Each package comes with whatever contact details its installer publishes, such as a phone number, an email and a website [10]. Sol can also list the installers registered with the DOE in the household's area [9]. The DOE states that it does not endorse any listed firm, so Sol repeats that warning on every list [9]. The prices are what the installers published, the pictures are stock photos, and no installer has agreed to take part.

Slide 8: Assumptions and sources (5:12 to 5:45)

Because a household is about to spend real money, Sol is built so its answers can be checked. A language model handles the conversation, while tools do every calculation. Facts about Meralco and DOE rules come from a local library of their documents, which Sol searches using retrieval-augmented generation and returns with links to the original pages [6][7][8]. Each assumption behind a number is listed with its source, and any placeholder is labeled as one.

Slide 9: Passport (5:45 to 6:16)

When a household does go solar, Sol issues a Solar Passport, a signed record of the plan that anyone can verify. After an installer confirms the installation, the Passport is meant to unlock vouchers and discounts, which is our answer to the rewards part of the challenge. The rewards programme is our proposal. The vouchers on screen are samples, and nothing has been agreed with Meralco or with any business.

Slide 10: Who it helps (6:16 to 6:43)

Three groups benefit. Households get an honest range of outcomes and a clearer path to a supplier. Installers meet customers who already have a measured site and a budget. Meralco gets better-prepared customers who can be pointed to registered installers and to the right grid pathway [8][9]. The installer and Meralco benefits are our proposal, and Sol promises no Meralco benefit.

Slide 13: Close (6:43 to 7:00)

In short, Sol maps your installation site, recommends who can install it, and compares real packages in one conversation. Thank you, and let us now watch Sol work on a real address.

References:

[1] Meralco, "Higher Residential Rates this October 2026" (overall typical-household rate ₱15.0615 per kWh; 200 kWh household; about ₱64 increase).
    https://www.meralco.com.ph/media/articles/higher-residential-rates-october-2026

[2] Meralco, February 2026 rate advisory (January 2026 rate ₱12.9508 per kWh; typical consumption of 200 kWh).
    https://www.meralco.com.ph/media/advisories/higher-residential-rates-february

[3] GoSolar PH, solar panel price and brands guides (installed prices of about ₱45,000 to ₱75,000 per kW; look-alike setups).
    https://gosolarph.com/guides/best-solar-panel-brands-philippines/

[4] Tech Pilipinas, "How Much Do Rooftop Solar Panels Actually Cost in the Philippines?" (about ₱45 to ₱75 per watt in 2026).
    https://techpilipinas.com/solar-panel-cost-philippines/

[5] Inquirer and GMA News on the DTI's move toward mandatory certification of solar products.
    https://business.inquirer.net/592097/dti-moves-to-regulate-solar-panel-systems  |  https://www.gmanetwork.com/news/topstories/nation/990024/dti-eyes-mandatory-certification-for-solar-power-products/story/

[6] Meralco, "Solar and Net Metering" (export credit based on the monthly blended generation cost; optional REC meter and the estimate if it is declined).
    https://www.meralco.com.ph/residential/energy-solutions/solar-and-renewables/solar-net-metering

[7] Meralco, "Apply for Net Metering" (six stages; ₱1,500 ERC Certificate of Compliance application fee).
    https://www.meralco.com.ph/residential/energy-solutions/solar-and-renewables/re-net-metering-application

[8] Meralco, "Distributed Energy Resources" (DOE DC2026-08-0017: zero-export and micro solar systems); Rappler's summary of the circular.
    https://www.meralco.com.ph/residential/energy-solutions/solar-and-renewables/distributed-energy-resources  |  https://www.rappler.com/business/things-to-know-simplified-rules-solar-panels-department-energy/

[9] Department of Energy, Official Solar PV Installer Registry (lists as of Jan 31 and Jul 13, 2026; the DOE does not endorse any listed firm).
    https://doe.gov.ph/official-doe-solar-pv-installer-registry-updated-as-of-july-13-2026  |  https://prod-cms.doe.gov.ph/documents/d/eumb/list-of-solar-pv-installer-registry-as-of-31-january-2026-pdf

[10] Prices and inclusions as published by each installer on its own website, checked 12 November 2026: PTG Solar, Triple30 Renewables, DevSolutions Solar.
    https://ptgsolarph.com/  |  https://triple30renewables.com/  |  https://www.devsolutions.com.ph/

[11] EU Joint Research Centre, PVGIS 5 user manual (the hourly sunlight data the model uses).
    https://joint-research-centre.ec.europa.eu/pvgis-photovoltaic-geographical-information-system/getting-started-pvgis/pvgis-user-manual_en
