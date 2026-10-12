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
    "healthcare": {
        "label": "Registered nurse (healthcare)",
        "resume": (
            "Aisha Okafor — Registered Nurse, 5 years.\n"
            "Riverbend General Hospital (2021–now): RN on a 32-bed medical-surgical "
            "unit, 1:5 patient ratio. Charge nurse two shifts a week. Led a fall-"
            "prevention huddle that cut unit falls from 9 to 3 in a year. Precepted "
            "six new graduate nurses.\n"
            "Lakeside Clinic (2019–2021): outpatient nurse; ran the diabetes education "
            "group, 25 patients a month.\n"
            "Licenses: RN, BLS, ACLS. Skills: Epic charting, IV therapy, wound care, "
            "patient education."
        ),
        "jd": (
            "Registered Nurse, Emergency Department. Assess and triage patients, "
            "deliver time-critical care, communicate with physicians and families "
            "under pressure, and document accurately in Epic. We look for calm "
            "prioritisation, teamwork, patient advocacy and safe medication practice. "
            "Active RN license and ACLS required; 2+ years acute care preferred."
        ),
    },
    "media": {
        "label": "Video producer (media)",
        "resume": (
            "Leo Brandt — Video Producer, 4 years.\n"
            "Halfmoon Studio (2022–now): produced a weekly explainer series for a "
            "science YouTube channel; grew it from 40k to 210k subscribers. Managed "
            "shoots with crews of 3–6 and budgets up to $15k per episode. Cut "
            "turnaround from 3 weeks to 9 days with a shared edit template.\n"
            "Freelance (2020–2022): short documentaries for two nonprofits; one was "
            "screened at a regional film festival.\n"
            "Skills: Premiere Pro, DaVinci Resolve, storyboarding, scripting, "
            "audience analytics."
        ),
        "jd": (
            "Video Producer, Brand Content. Own short-form and long-form video from "
            "concept to delivery for our social channels. Write treatments, run "
            "shoots, manage freelancers and budgets, and use analytics to decide what "
            "to make next. Please share a portfolio. We value storytelling, "
            "organisation and taking feedback well."
        ),
    },
    "business": {
        "label": "Business analyst (business)",
        "resume": (
            "Hannah Lee — Business Analyst, 3 years.\n"
            "Crestline Retail (2022–now): analyst for a 120-store grocery chain. "
            "Built the weekly sales dashboard used by 30 regional managers. Found that "
            "stock-outs on 40 top items cost about $2M a year and led the reorder-"
            "point fix that halved them. Ran the pricing test for private-label "
            "products.\n"
            "Summit Consulting (2021–2022): junior analyst on two cost-reduction "
            "projects for a logistics client.\n"
            "Skills: SQL, Excel, Tableau, A/B testing, stakeholder interviews."
        ),
        "jd": (
            "Business Analyst, Operations Strategy. Turn messy data into clear "
            "recommendations for leadership. You'll size opportunities, build models "
            "in Excel and SQL, run experiments, and present to directors. Expect case "
            "questions. We look for structured problem solving, business judgment and "
            "crisp communication."
        ),
    },
    "teaching": {
        "label": "Primary school teacher (education)",
        "resume": (
            "Daniel Moreno — Primary Teacher, 6 years.\n"
            "Oakfield Elementary (2020–now): Grade 3 teacher, class of 26. Introduced "
            "guided reading groups; students at grade-level reading rose from 58% to "
            "81% in two years. Grade-level lead for four teachers. Runs the after-"
            "school robotics club.\n"
            "Pinecrest Primary (2018–2020): Grade 2 teacher; co-taught an inclusion "
            "class with a special-education teacher.\n"
            "Credentials: state teaching license (K–6). Skills: differentiated "
            "instruction, classroom management, parent communication."
        ),
        "jd": (
            "Grade 4 Classroom Teacher. Plan and deliver engaging lessons across "
            "subjects, differentiate for a wide range of learners including students "
            "with IEPs, manage behaviour positively, assess progress and keep parents "
            "informed. Teaching license required. We value warmth, high expectations "
            "and collaboration with colleagues."
        ),
    },
    "trades": {
        "label": "Electrician (skilled trades)",
        "resume": (
            "Tom Becker — Licensed Electrician, 7 years.\n"
            "Brightline Electric (2019–now): journeyman on commercial fit-outs and "
            "service calls. Led a 4-person crew on a 3-storey office renovation, "
            "finished a week early with zero safety incidents. Troubleshoots panels, "
            "lighting controls and motor circuits; trains two apprentices.\n"
            "Apprenticeship (2015–2019): residential wiring and new builds.\n"
            "Licenses: journeyman electrician, OSHA 30. Skills: NEC code, blueprint "
            "reading, conduit bending, fault finding."
        ),
        "jd": (
            "Commercial Electrician. Install, maintain and troubleshoot electrical "
            "systems in offices and light industrial sites. Read blueprints, follow "
            "NEC and lockout/tagout, work safely with other trades and explain issues "
            "to clients. Journeyman license required; leadership experience is a plus."
        ),
    },
}
