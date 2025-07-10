#!/bin/bash
#
# my-words.sh - Generate word cloud from your voice data
#
# This script uses the transcript_cli.py to export your voice transcripts
# from the last 6 months and generates a word cloud visualization.
#
# Requirements:
# - wordcloud Python library: pip install wordcloud
# - transcript_cli.py in the same directory
#
# Usage:
#   ./my-words.sh
#

set -e

# Configuration
MONTHS_BACK=6
OUTPUT_FILE="my_words.png"
TEMP_FILE="/tmp/my_voice_data.txt"

# Calculate date range (6 months ago to today)
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    START_DATE=$(date -v-${MONTHS_BACK}m +"%Y-%m-%d")
else
    # Linux
    START_DATE=$(date -d "${MONTHS_BACK} months ago" +"%Y-%m-%d")
fi
END_DATE=$(date +"%Y-%m-%d")

echo "Generating word cloud from your voice data..."
echo "Date range: $START_DATE to $END_DATE"

# Export voice data using transcript_cli.py
echo "Exporting your voice transcripts..."
python transcript_cli.py --export-own-voice "$START_DATE to $END_DATE" --export-format text > "$TEMP_FILE"

# Check if we got any data
if [ ! -s "$TEMP_FILE" ]; then
    echo "No voice data found for the specified time period."
    echo "Make sure Rewind.ai has been recording audio and you have spoken during this time."
    rm -f "$TEMP_FILE"
    exit 1
fi

# Generate word cloud
echo "Generating word cloud..."
python3 -c "
import sys
from wordcloud import WordCloud
import matplotlib.pyplot as plt

# Read the text data
with open('$TEMP_FILE', 'r') as f:
    text = f.read()

if not text.strip():
    print('No text data found.')
    sys.exit(1)

# Generate word cloud
wordcloud = WordCloud(
    width=800, 
    height=400, 
    background_color='white',
    max_words=100,
    colormap='viridis'
).generate(text)

# Save as image
plt.figure(figsize=(10, 5))
plt.imshow(wordcloud, interpolation='bilinear')
plt.axis('off')
plt.title('My Words - Last $MONTHS_BACK Months of Voice Data')
plt.tight_layout()
plt.savefig('$OUTPUT_FILE', dpi=300, bbox_inches='tight')
print(f'Word cloud saved as $OUTPUT_FILE')
"

# Clean up
rm -f "$TEMP_FILE"

echo "Done! Word cloud saved as $OUTPUT_FILE"
echo "To view: open $OUTPUT_FILE (macOS) or xdg-open $OUTPUT_FILE (Linux)"