import re

trimmed = 'Share Capital Numbers* Amount Numbers* Amount As at March 31, 2025 Issued, subscribed and fully paid up Equity shares of Rs.2 each 55983969 11.20 55983969 11.20'

cleaned2 = trimmed
cleaned2 = re.sub(r'^.*?\bparticulars\b(?:\s+notes?\s+no)?', '', cleaned2, flags=re.IGNORECASE).strip()
cleaned2 = re.sub(r'^\s*notes?\s*(?:no\.?)?', '', cleaned2, flags=re.IGNORECASE).strip()
cleaned2 = re.sub(r'^(?:\s*(?:numbers?|amount))(?:\s+(?:numbers?|amount))*', '', cleaned2, flags=re.IGNORECASE).strip()
print('After numbers/amount strip:', repr(cleaned2[:150]))

while True:
    updated = re.sub(
        r'^(?:\s*(?:As at|As on|For the year ended|Year ended)\s+[A-Za-z]+\s+\d{1,2},?\s+\d{4}(?:\s*\([^)]+\))?)+',
        '', cleaned2, flags=re.IGNORECASE,
    ).strip()
    if updated == cleaned2:
        break
    cleaned2 = updated
print('After period strip:', repr(cleaned2[:150]))

tokens = cleaned2.split()
print('Tokens:', tokens)

NUMBER_TOKEN_RE = re.compile(r'^[\(\[]?-?(?:\d[\d,]*)(?:\.\d+)?[\)\]]?%?$')
def is_number_token(token):
    if not NUMBER_TOKEN_RE.match(token):
        return False
    if token.isdigit() and 1 <= int(token) <= 100 and '.' not in token and ',' not in token:
        return False
    return True

for i, t in enumerate(tokens):
    print(f'[{i}] {t:>15} -> number: {is_number_token(t)}')

# Now check the _share_capital_column_plan
# It checks the table_text (trimmed) for "numbers" and "amount"
lowered = trimmed.lower()
print('\n--- Column plan check ---')
print('value_count = 4')
print('numbers in lowered:', 'numbers' in lowered)
print('amount in lowered:', 'amount' in lowered)

DATE_PERIOD_RE = re.compile(
    r'(?:as at|as on|for the year ended|year ended)\s+('
    r'(?:[A-Za-z]+\s+\d{1,2},\s+\d{4})'
    r'|(?:\d{1,2}[/-]\d{1,2}[/-]\d{4})'
    r'|(?:\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})'
    r')',
    re.IGNORECASE,
)
FY_PERIOD_RE = re.compile(r'\bFY\s?(\d{2,4})\b', re.IGNORECASE)

periods = []
for match in DATE_PERIOD_RE.finditer(trimmed):
    label = re.sub(r'\s+', ' ', str(match.group(1) or '')).strip()
    if label:
        periods.append(label)
for match in FY_PERIOD_RE.finditer(trimmed):
    label = f'FY{match.group(1)}'
    periods.append(label)
print('Periods found:', periods)