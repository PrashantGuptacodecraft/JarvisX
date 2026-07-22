import re

with open("tests/test_historical_query.py", "r") as f:
    text = f.read()

text = re.sub(r'temp_store\._compress_tier\d+_to_tier\d+\(([^,]+),\s*([^,]+),\s*\{[^}]+\}\)', r'temp_store.compress(\1, \2)', text)

with open("tests/test_historical_query.py", "w") as f:
    f.write(text)
