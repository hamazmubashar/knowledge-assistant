DOCS = [
    {"title": "EVAL HR Annual Leave Policy", "group": "hr", "scanned": False, "pages": [
        ["ANNUAL LEAVE", "Full-time staff receive 20 days of paid annual leave each year.",
         "Part-time staff receive leave pro rata to their contracted hours."],
        ["CARRY-OVER", "Up to 5 unused days may be carried into the next year.",
         "Carried days expire on 31 March."]]},
    {"title": "EVAL HR Salary Bands", "group": "hr", "scanned": False, "pages": [
        ["SALARY BANDS 2026", "Band | Monthly range | Review month",
         "A | 2,500 - 3,500 | April", "B | 3,500 - 4,500 | April", "C | 4,000 - 5,500 | April"]]},
    {"title": "EVAL HR Disciplinary Procedure", "group": "hr", "scanned": False, "pages": [
        ["DISCIPLINARY PROCEDURE",
         "Minor misconduct results in a verbal warning recorded for 6 months.",
         "Serious misconduct results in a written warning and a review meeting within 10 working days.",
         "Gross misconduct may lead to dismissal after an investigation."]]},
    {"title": "EVAL HR Parental Leave", "group": "hr", "scanned": True, "pages": [
        ["PARENTAL LEAVE", "Birth parents receive 16 weeks of paid parental leave.",
         "Partners receive 4 weeks of paid leave within 3 months of the birth."]]},
    {"title": "EVAL Support Refund Procedure", "group": "support", "scanned": False, "pages": [
        ["REFUND PROCEDURE", "Customers may request a full refund within 30 days of purchase.",
         "Refunds go to the original payment method within 5 working days.",
         "Opened software licences cannot be refunded."]]},
    {"title": "EVAL Support Escalation Matrix", "group": "support", "scanned": False, "pages": [
        ["ESCALATION MATRIX", "Priority | First response | Escalate to",
         "P1 outage | 15 minutes | On-call engineer", "P2 degraded | 2 hours | Team lead",
         "P3 question | 1 working day | Support queue"]]},
    {"title": "EVAL Support Router Troubleshooting", "group": "support", "scanned": False, "pages": [
        ["ROUTER WILL NOT CONNECT", "Ask the customer to restart the router and wait 2 minutes.",
         "If the status light stays red, check that the WAN cable is in the yellow port."],
        ["FACTORY RESET", "Hold the reset button for 10 seconds with a paper clip.",
         "A factory reset deletes the customer's Wi-Fi name and password."]]},
    {"title": "EVAL Support Warranty Terms", "group": "support", "scanned": False, "pages": [
        ["WARRANTY", "Hardware carries a 24-month warranty from the delivery date.",
         "Water damage and physical damage are not covered."]]},
    {"title": "EVAL Ops Shift Handover", "group": "operations", "scanned": False, "pages": [
        ["SHIFT HANDOVER", "The outgoing supervisor completes the handover checklist before 18:00.",
         "Open safety incidents must be handed over in person, not by message."]]},
    {"title": "EVAL Ops Forklift Safety", "group": "operations", "scanned": False, "pages": [
        ["FORKLIFT SAFETY", "Only certified drivers may operate forklifts.",
         "Pre-use inspections are logged on the tablet at the start of every shift.",
         "Maximum speed inside the warehouse is 8 km/h."]]},
    {"title": "EVAL Ops Stock Count", "group": "operations", "scanned": True, "pages": [
        ["QUARTERLY STOCK COUNT", "Full stock counts happen on the last Saturday of each quarter.",
         "Variances above 2 percent must be reported to the finance team."]]},
    {"title": "EVAL Ops Supplier Delivery", "group": "operations", "scanned": False, "pages": [
        ["INBOUND DELIVERIES", "Suppliers must book a delivery slot 48 hours in advance.",
         "Deliveries without a purchase order number are refused at the gate."]]},
    {"title": "EVAL General Office Information", "group": "general", "scanned": False, "pages": [
        ["OFFICE HOURS", "The office is open from 09:00 to 17:00, Monday to Friday.",
         "Visitors must sign in at reception and wear a visitor badge."]]},
    {"title": "EVAL General Fire Evacuation", "group": "general", "scanned": False, "pages": [
        ["FIRE EVACUATION", "When the alarm sounds, leave the building by the nearest exit.",
         "Do not use the lifts.", "Assemble at the car park opposite the main entrance."]]},
    {"title": "EVAL General IT Password Policy", "group": "general", "scanned": False, "pages": [
        ["PASSWORDS", "Passwords must be at least 14 characters.",
         "Passwords are changed only when a compromise is suspected.",
         "Multi-factor authentication is required for email and VPN."]]},
    {"title": "EVAL General Expense Claims", "group": "general", "scanned": False, "pages": [
        ["EXPENSE CLAIMS", "Submit expense claims within 30 days with itemised receipts.",
         "Meals are reimbursed up to 25 per person per day while travelling."]]},
]

TITLE_TO_GROUP = {d["title"]: d["group"] for d in DOCS}