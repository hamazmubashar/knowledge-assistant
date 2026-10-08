import pymupdf

PAGES = [
    ["ANNUAL LEAVE POLICY", "",
     "1. Entitlement",
     "Full-time employees receive 20 days of paid annual leave per calendar year.",
     "Part-time employees receive leave in proportion to their contracted hours.",
     "",
     "2. Requesting Leave",
     "Leave requests must be submitted through the HR portal at least 10 working days",
     "before the first day of leave. Managers respond within 3 working days."],
    ["3. Carry-Over Rules",
     "Up to 5 unused days may be carried into the next calendar year.",
     "Carried-over days expire on 31 March if not used.",
     "",
     "4. Sick Leave",
     "Sick leave is separate from annual leave. Employees must notify their manager",
     "before 10:00 on the first day of absence."],
    ["5. Contact",
     "Questions about this policy should be sent to the HR team through the portal."],
]

doc = pymupdf.open()
for lines in PAGES:
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
doc.save("/code/leave_policy.pdf")
print("Created leave_policy.pdf (3 pages, synthetic)")