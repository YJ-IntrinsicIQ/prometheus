"""M63/G3 source-anchored reference set. Every anchor was read by hand from the primary filing PDF (data/Processed/...); this script only
re-verifies that each quote is present on the cited PDF page (1-based). It never looks at extractor output. Values are in INR crore unless unit says otherwise."""
import json, pathlib, re, sys
import pymupdf
R = pathlib.Path(__file__).resolve().parents[2]
PDF = {
 "datapatterns:fy26": "data/Processed/datapatterns/fy26/annual_report/datapatterns_fy26.pdf",
 "datapatterns:fy24": "data/Processed/datapatterns/fy24/annual_report/datapatterns_fy24.pdf",
 "datapatterns:fy22": "data/Processed/datapatterns/fy22/annual_report/datapatterns_fy22.pdf",
 "tanla:fy26": "data/Processed/tanla/fy26/annual_report/tanla_fy26.pdf",
 "sun_pharma:fy26": "data/Processed/sun_pharma/fy26/annual_report/sun_pharma_fy26.pdf",
 "ujjivan:fy25": "data/Processed/ujjivan/fy25/annual_report/ujjivan_fy25.pdf",
 "ltts:fy26": "data/Processed/ltts/fy26/annual_report/a5e2aee1-f21a-4812-a614-2851ebb3923b.pdf",
}
# kind: FIN = a number in the financial fact registry; CAP = capital-allocation fact; TXN = transaction state; TXT = narrative fact; FID = source-fidelity (must NOT be a company commitment)
A = [
 # ── Data Patterns FY26 (standalone, INR crore) ──
 dict(id="DP-01", co="datapatterns", fy="fy26", cat="income", kind="FIN", metric="revenue", value=924.77, basis="standalone", page=133, quote="Revenue from operations 23 924.77 708.35"),
 dict(id="DP-02", co="datapatterns", fy="fy26", cat="income", kind="FIN", metric="pat", value=271.37, basis="standalone", page=133, quote="Profit for the year (A) 271.37 221.81"),
 dict(id="DP-03", co="datapatterns", fy="fy26", cat="income", kind="FIN", metric="eps_basic", value=48.47, basis="standalone", page=133, quote="48.47 39.62"),
 dict(id="DP-04", co="datapatterns", fy="fy26", cat="cashflow", kind="FIN", metric="cfo", value=80.15, basis="standalone", page=134, quote="Net cash from /(used in) operating activities (A) 80.15 (89.88)"),
 dict(id="DP-05", co="datapatterns", fy="fy26", cat="capital", kind="FIN", metric="cash_and_equivalents", value=56.85, basis="standalone", page=132, quote="Cash and cash equivalents 14 56.85 37.64"),
 dict(id="DP-06", co="datapatterns", fy="fy26", cat="capital", kind="FIN", metric="other_bank_balances", value=36.98, basis="standalone", page=132, quote="Bank balances other than above 14 36.98 88.76"),
 dict(id="DP-07", co="datapatterns", fy="fy26", cat="capital", kind="FIN", metric="total_debt", value=0.0, basis="standalone", page=132, quote="Borrowings 17 - -"),
 dict(id="DP-08", co="datapatterns", fy="fy26", cat="capital_allocation", kind="CAP", metric="dividends_paid", value=44.23, basis="standalone", page=134, quote="Dividend paid (44.23) (36.39)"),
 dict(id="DP-09", co="datapatterns", fy="fy26", cat="capital_allocation", kind="FIN", metric="capex", value=72.06, basis="standalone", page=134, quote="(44.47) (35.86)", note="PPE/CWIP 44.47 + intangibles 27.59 (two statement lines, p134)", page2=134, quote2="(27.59) (70.57)"),
 dict(id="DP-10", co="datapatterns", fy="fy26", cat="income", kind="FIN", metric="revenue", value=708.35, basis="standalone", page=133, quote="708.35", period="fy25", page_check=False),
 dict(id="DP-11", needle="926", co="datapatterns", fy="fy26", cat="future_economics", kind="TXT", value="Order book Rs 926 Cr at 31 March 2026", page=6, quote="Rs 926 Cr Order Book at 31st March 2026"),
 dict(id="DP-12", needle="single segment", co="datapatterns", fy="fy26", cat="business", kind="TXT", value="single reportable segment", page=24, quote="operates only in a single segment"),
 dict(id="DP-13", needle="6.92", co="datapatterns", fy="fy26", cat="risk", kind="TXT", value="contingent liabilities Rs 6.92 Cr (FY26)", page=176, quote="Total 6.92 7.10"),
 dict(id="DP-14", needle="no subsidiaries", co="datapatterns", fy="fy26", cat="basis", kind="TXT", value="standalone only: no subsidiaries", page=29, quote="The Company has no subsidiaries"),
 # fidelity (D): outlook / external target must not be a company promise
 dict(id="DP-15", co="datapatterns", fy="fy24", cat="management", kind="FID", value="pipeline outlook Rs 2-3 bn over next couple of years", page=8, quote="pipeline going forward of Rs 2 – 3 bn over next couple of years", forbidden="Achieve a business pipeline"),
 dict(id="DP-16", co="datapatterns", fy="fy22", cat="management", kind="FID", value="Defence Ministry aim 70% self-reliance by 2027", page=27, quote="The Defence Ministry aims to achieve 70% self-reliance in weaponry by 2027", forbidden="Achieve 70% self-reliance"),
 # ── Tanla FY26 (consolidated; filing in INR lakh, here crore) ──
 dict(id="TN-01", co="tanla", fy="fy26", cat="income", kind="FIN", metric="revenue", value=4417.7064, basis="consolidated", page=385, quote="Revenue from operations 29 4,41,770.64 4,02,772.15"),
 dict(id="TN-02", co="tanla", fy="fy26", cat="income", kind="FIN", metric="pat", value=509.1458, basis="consolidated", page=385, quote="Profit for the year (V - VI) 50,914.58 50,728.28"),
 dict(id="TN-03", co="tanla", fy="fy26", cat="income", kind="FIN", metric="eps_basic", value=38.36, basis="consolidated", page=385, quote="Basic (INR) 38.36 37.76"),
 dict(id="TN-04", co="tanla", fy="fy26", cat="cashflow", kind="FIN", metric="cfo", value=574.1948, basis="consolidated", page=386, quote="Net cash flows generated from operating activities 57,419.48 64,210.47"),
 dict(id="TN-05", co="tanla", fy="fy26", cat="capital", kind="FIN", metric="cash_and_equivalents", value=748.0121, basis="consolidated", page=383, quote="Cash and cash equivalents 15 74,801.21 50,150.30"),
 dict(id="TN-06", co="tanla", fy="fy26", cat="capital", kind="FIN", metric="other_bank_balances", value=315.6184, basis="consolidated", page=383, quote="Bank balances other than cash and cash equivalents 16 31,561.84 37,915.79"),
 dict(id="TN-07", co="tanla", fy="fy26", cat="capital_allocation", kind="CAP", metric="buyback", value=175.0, basis="consolidated", page=73, quote="2 million shares repurchased at INR 875 per share for a total consideration of INR 175 Cr"),
 dict(id="TN-08", co="tanla", fy="fy26", cat="capital_allocation", kind="CAP", metric="buyback_cash_outflow", value=179.0, basis="consolidated", page=177, quote="buyback of shares of INR 179 Cr"),
 dict(id="TN-09", co="tanla", fy="fy26", cat="capital_allocation", kind="CAP", metric="dividends_declared_per_share", value=12.0, basis="consolidated", page=73, quote="totalling INR 12 per share for the year"),
 dict(id="TN-10", co="tanla", fy="fy26", cat="capital_allocation", kind="FIN", metric="capex", value=97.6505, basis="consolidated", page=386, quote="Payments for acquisition of property plant and equipment (1,087.28) (4,893.60) Payments for acquisition of other intangibles (8,677.74) (7,869.83)", note="PPE 10.8728 + other intangibles 86.7774 (statement lines); MD&A p177 states capex INR 97 Cr and FCF INR 477 Cr"),
 dict(id="TN-12", co="tanla", fy="fy26", cat="cashflow", kind="FIN", metric="fcf", value=476.5443, basis="consolidated", page=386, quote="Net cash flows generated from operating activities 57,419.48 64,210.47", note="CFO 574.1948 - total capex 97.6505; MD&A p177 states FCF INR 477 Cr"),
 dict(id="TN-11", needle="1,144", co="tanla", fy="fy26", cat="capital", kind="TXT", value="management 'cash and cash equivalents INR 1,144 Cr' is a broader treasury figure (cash, current investments, FDs, liquid funds) than balance-sheet cash 748 Cr", page=168, quote="Cash and cash equivalents at INR 1,144 Cr post dividend and buyback of INR 340 Cr"),
 # ── Sun Pharma FY26 (consolidated, INR million in filing) ──
 dict(id="SP-01", co="sun_pharma", fy="fy26", cat="income", kind="FIN", metric="revenue", value=58462.04, basis="consolidated", page=243, quote="Revenue from operations 30 584,620.4 525,784.4"),
 dict(id="SP-02", co="sun_pharma", fy="fy26", cat="income", kind="FIN", metric="pat", value=11479.42, basis="consolidated", page=243, quote="attributable to owners of the parent company (XII-XIII) 114,794.2 109,290.4"),
 dict(id="SP-03", co="sun_pharma", fy="fy26", cat="income", kind="FIN", metric="eps_basic", value=47.8, basis="consolidated", page=244, quote="Basic (in `) 47.8 45.6"),
 dict(id="SP-04", co="sun_pharma", fy="fy26", cat="cashflow", kind="FIN", metric="cfo", value=12419.18, basis="consolidated", page=246, quote="Net cash generated from / (used in) operating activities (A) 124,191.8 140,720.9"),
 dict(id="SP-05", co="sun_pharma", fy="fy26", cat="capital_allocation", kind="FIN", metric="capex", value=3609.37, basis="consolidated", page=246, quote="(36,093.7) (21,285.8)"),
 dict(id="SP-06", co="sun_pharma", fy="fy26", cat="capital", kind="FIN", metric="cash_and_equivalents", value=9770.51, basis="consolidated", page=241, quote="Cash and cash equivalents 14 97,705.1 102,687.7"),
 dict(id="SP-07", co="sun_pharma", fy="fy26", cat="capital", kind="FIN", metric="total_debt", value=4081.61, basis="consolidated", page=242, quote="Borrowings 25 40,503.5 18,671.1", components_page=242, components_quote="Borrowings 21 312.6 25.2"),
 dict(id="SP-08", co="sun_pharma", fy="fy26", cat="transaction", kind="TXN", value="Organon acquisition announced after year end; not completed", page=10, quote="Subsequent to the close of the financial year, Sun Pharma announced the acquisition of Organon & Co", state="announced"),
 dict(id="SP-09", co="sun_pharma", fy="fy26", cat="capital_allocation", kind="CAP", metric="dividends_declared_per_share", value=16.0, basis="standalone", page=50, quote="interim dividend of ₹ 11.00", note="interim 11.00 + final 5.00 recommended"),
 # ── Ujjivan SFB FY25 (bank) ──
 dict(id="UJ-01", num=3636, metric="net_interest_income", needle="3,636", co="ujjivan", fy="fy25", cat="income", kind="TXT", value="Net interest income Rs 3,636 Cr", page=12, quote="` 3,636 Crores Net Interest Income"),
 dict(id="UJ-02", needle="726", co="ujjivan", fy="fy25", cat="income", kind="TXT", value="Profit after tax Rs 726 Cr", page=7, quote="Net Profit of ` 726 Crores"),
 dict(id="UJ-03", num=37630, metric="total_deposits", needle="37,630", co="ujjivan", fy="fy25", cat="capital", kind="TXT", value="Total deposits Rs 37,630 Cr", page=7, quote="total deposits of ` 37,630 Crores"),
 dict(id="UJ-04", num=2.2, metric="gross_npa_ratio", needle="2.2%", co="ujjivan", fy="fy25", cat="risk", kind="TXT", value="Gross NPA 2.2%, Net NPA 0.5%", page=8, quote="Gross NPA ratio of 2.2% and a consistently low Net NPA of 0.5%"),
 dict(id="UJ-05", num=23.1, metric="capital_adequacy_ratio", needle="23.1", co="ujjivan", fy="fy25", cat="capital", kind="TXT", value="Capital adequacy ratio 23.1%", page=12, quote="23.1% Capital Adequacy Ratio"),
 dict(id="UJ-06", needle="753 branches", co="ujjivan", fy="fy25", cat="business", kind="TXT", value="753 branches, 26 states and UTs", page=7, quote="753 branches across 26 states"),
 dict(id="UJ-07", needle="1.5", co="ujjivan", fy="fy25", cat="capital_allocation", kind="TXT", value="dividend per share Rs 1.5", page=18, quote="` 1.5 Dividend per Share"),
 dict(id="UJ-08", num=7201, metric="total_income", needle="7,201", co="ujjivan", fy="fy25", cat="income", kind="TXT", value="Total income Rs 7,201 Cr", page=18, quote="` 7,201 Crores Total Income"),
]

# ── Held-out fifth company (LTTS FY26, consolidated, INR million in the filing). NOT used while developing any G1-G3 repair; scored separately. ──
H = [
 dict(id="LT-01", co="ltts", fy="fy26", cat="income", kind="FIN", metric="revenue", value=10995.9, basis="consolidated", page=354, quote="Revenue from operations 23 109,959 96,422"),
 dict(id="LT-02", co="ltts", fy="fy26", cat="income", kind="FIN", metric="pat", value=1279.2, alt=[1281.1], basis="consolidated", page=354, quote="Equity shareholders of the Company 12,792 12,667", note="profit attributable to equity holders 12,792 mn (profit for the year 12,811 mn)"),
 dict(id="LT-03", co="ltts", fy="fy26", cat="income", kind="FIN", metric="eps_basic", value=120.71, alt=[115.89], basis="consolidated", page=354, quote="Basic (I) 115.89 112.75", note="continuing 115.89 / continuing+discontinued 120.71"),
 dict(id="LT-04", co="ltts", fy="fy26", cat="cashflow", kind="FIN", metric="cfo", value=1455.1, basis="consolidated", page=355, quote="Net cash (used in)/from operating activities 14,551 14,811"),
 dict(id="LT-05", co="ltts", fy="fy26", cat="capital_allocation", kind="FIN", metric="capex", value=185.1, basis="consolidated", page=355, quote="Purchase of property, plant and equipment and intangibles (1,851) (1,116)"),
 dict(id="LT-06", co="ltts", fy="fy26", cat="capital", kind="FIN", metric="cash_and_equivalents", value=1649.7, basis="consolidated", page=353, quote="Cash and cash equivalent 12 16,497 13,831"),
 dict(id="LT-07", co="ltts", fy="fy26", cat="capital", kind="FIN", metric="other_bank_balances", value=0.8, basis="consolidated", page=353, quote="Other bank balances 13 8 1,827"),
 dict(id="LT-08", co="ltts", fy="fy26", cat="income", kind="FIN", metric="revenue", value=9207.1, basis="standalone", page=280, quote="Revenue from operations 23 92,071 85,051", note="the same filing also prints standalone statements; a registry with both bases must keep them apart"),
]
A_ALL = A + H

def norm(s): return re.sub(r"\s+", " ", s.replace("’", "'")).strip()
def verify():
    docs, bad = {}, []
    for a in A_ALL:
        key = f"{a['co']}:{a['fy']}"
        if key not in PDF or not (R / PDF[key]).exists():
            bad.append((a["id"], "pdf missing", key)); continue
        d = docs.setdefault(key, pymupdf.open(R / PDF[key]))
        for pg, q in ((a["page"], a["quote"]), (a.get("components_page"), a.get("components_quote")), (a.get("page2"), a.get("quote2"))):
            if pg and norm(q) not in norm(d[pg - 1].get_text()): bad.append((a["id"], "quote not on page", pg, q))
    return bad
if __name__ == "__main__":
    bad = verify(); print(len(A), "anchors +", len(H), "held-out;", "ALL QUOTES VERIFIED ON CITED PAGES" if not bad else f"{len(bad)} FAILED"); [print(" ", b) for b in bad]
    if "--write" in sys.argv:
        (R / "tests/g3/reference_set.json").write_text(json.dumps(A, indent=1, ensure_ascii=False))
        (R / "tests/g3/reference_heldout.json").write_text(json.dumps(H, indent=1, ensure_ascii=False))
