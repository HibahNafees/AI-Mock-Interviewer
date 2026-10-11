"""Job fields for the eval harness: a fictional résumé and job description each.

Facts here are invented for testing and are not reused in any app prompt
(examples that match test answers inflate the scores).
"""

FIELDS = {
    "backend": {
        "label": "Backend engineer (software)",
        "resume": (
            "Priya Raman — Backend Engineer, 4 years.\n"
            "Northwind Logistics (2022–now): built the shipment-tracking API in Go and "
            "PostgreSQL, about 40 million events a day. Moved webhook delivery to a "
            "queue with retries and dead-lettering; failed deliveries fell from 3% to "
            "0.2%. Cut the nightly billing job from 5 hours to 50 minutes by batching "
            "writes. On-call lead for a team of five; wrote the incident runbook.\n"
            "Brightpath (2020–2022): Python/Django developer on a booking product; "
            "added Redis caching for search, p95 down from 900 ms to 180 ms.\n"
            "Skills: Go, Python, PostgreSQL, Redis, Kafka, Docker, AWS."
        ),
        "jd": (
            "Mid-level Backend Engineer. You will design and run APIs that handle "
            "high event volumes, own reliability (on-call, incident reviews), tune "
            "PostgreSQL, and work with product managers on trade-offs. We value clear "
            "communication, ownership, and measurable impact. Go or Python required; "
            "experience with queues and caching is a plus."
        ),
    },
    "sales": {
        "label": "Account executive (sales)",
        "resume": (
            "Marco Diaz — Account Executive, 3 years.\n"
            "Ledgerly (2023–now): mid-market AE selling accounting software to "
            "finance teams of 20–200 people. Closed $1.1M in new ARR last year, 118% "
            "of quota. Shortened the sales cycle from 74 to 51 days by running "
            "mutual action plans with champions. Won back two churned logos.\n"
            "Copperleaf (2021–2023): SDR, booked 30+ meetings a month; promoted after "
            "14 months.\n"
            "Skills: discovery, MEDDICC, Salesforce, Gong, negotiation."
        ),
        "jd": (
            "Account Executive, Mid-Market. Own the full cycle from discovery to close "
            "for finance software. You will run discovery calls, handle objections on "
            "price and switching cost, build business cases with CFOs, and forecast "
            "accurately. We look for consultative selling, resilience, and a track "
            "record against quota."
        ),
    },
}
