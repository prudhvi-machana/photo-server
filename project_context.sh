#!/bin/bash

OUTPUT="project_context.txt"

echo "========================================" > "$OUTPUT"
echo "PHOTO SERVER - PROJECT CONTEXT" >> "$OUTPUT"
echo "Generated: $(date)" >> "$OUTPUT"
echo "========================================" >> "$OUTPUT"

echo "" >> "$OUTPUT"
echo "PROJECT STRUCTURE" >> "$OUTPUT"
echo "=================" >> "$OUTPUT"

tree -a -I '.venv|.git|__pycache__|*.pyc|*.db|storage' . >> "$OUTPUT"

echo "" >> "$OUTPUT"
echo "SOURCE FILES" >> "$OUTPUT"
echo "============" >> "$OUTPUT"

find app -type f -name '*.py' | sort | while read -r file; do
    echo "" >> "$OUTPUT"
    echo "----------------------------------------" >> "$OUTPUT"
    echo "--- $file ---" >> "$OUTPUT"
    echo "----------------------------------------" >> "$OUTPUT"
    cat "$file" >> "$OUTPUT"
    echo "" >> "$OUTPUT"
done

echo "" >> "$OUTPUT"
echo "CONFIGURATION" >> "$OUTPUT"
echo "=============" >> "$OUTPUT"

for file in requirements.txt alembic.ini; do
    if [ -f "$file" ]; then
        echo "" >> "$OUTPUT"
        echo "----------------------------------------" >> "$OUTPUT"
        echo "--- $file ---" >> "$OUTPUT"
        echo "----------------------------------------" >> "$OUTPUT"
        cat "$file" >> "$OUTPUT"
    fi
done

echo ""
echo "Project context generated: $OUTPUT"
