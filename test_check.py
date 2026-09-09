import re

text = """Management Message Business Segment Review As on March 31, 2022 (` in 000's) Revenue 2,821,324 27,692,669 746,743 31,260,736 Segment Assets 61,766,622 161,706,653 8,436,055 231,909,331 Unallocated Assets 4,135,311 13 Total Assets 236,044,642 14 Segment Liabilities 54,498,992 142,679,793 7,443,443 204,622,228 Unallocated Liabilities 3,648,737 16 Capital Employed 7,267,650 19,026,881 992,612 27,287,144 Unallocated Capital Employed 486,533 18"""

lowered = text.lower()
numeric_hits = len(re.findall(r'\b\d[\d,]*(?:\.\d+)?%?\b', text))
has_table_header = 'particulars' in lowered or 'notes no' in lowered or 'category' in lowered
print('numeric_hits:', numeric_hits)
print('has_table_header:', has_table_header)
print('looks_like:', numeric_hits >= 4 and (has_table_header or 'financial_note'.startswith('primary_') or 'financial_note'.endswith('_note')))