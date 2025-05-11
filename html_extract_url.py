import re

# Use raw string (r"") for the file path
html_file_path = r'F:\VENV\selenium_env\view-source_gumroad_library_purchase_date.html'

# Read HTML content from the file
try:
    with open(html_file_path, 'r', encoding='utf-8') as file:
        html_content = file.read()
except OSError as e:
    print(f"Error opening file: {e}")
    exit(1)

# Regex pattern to find all download_url values
pattern = r'"download_url":"(https://app.gumroad.com/d/[a-z0-9]+(?:[a-z0-9-]+)*)"'

# Find all matches using regex
download_urls = re.findall(pattern, html_content)

# Save the download URLs to a text file
output_file_path = r'F:\VENV\selenium_env\gumroad_download_urls.txt'  # Specify output path
with open(output_file_path, 'w', encoding='utf-8') as file:
    for url in download_urls:
        file.write(f"{url}\n")

print(f"Extracted {len(download_urls)} download URLs and saved to {output_file_path}.")
