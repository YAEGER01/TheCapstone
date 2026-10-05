import re

# The models.py file we want to modify
file = "models.py"

# Read models.py
with open(file, "r", encoding="utf-8") as f:
    content = f.read()

# Find ONLY db_table declarations and lowercase their values
content = re.sub(
    r'(db_table\s*=\s*["\'])([^"\']+)(["\'])',
    lambda m: m.group(1) + m.group(2).lower() + m.group(3),
    content
)

# Save the modified models.py
with open(file, "w", encoding="utf-8") as f:
    f.write(content)

print("DONE: All db_table names have been converted to lowercase.")