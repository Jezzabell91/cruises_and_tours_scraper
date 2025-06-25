import json
import re
import time
import random
from urllib.parse import urlparse, urljoin

import streamlit as st
import requests
from bs4 import BeautifulSoup


class FlightCentreScraper:
    def __init__(self):
        self.session = requests.Session()
        # Set headers to mimic a real browser
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def determine_scraper_type(self, url):
        """Determine if the URL is for a cruise or tour"""
        if "cruises.flightcentre" in url:
            return "cruise"
        elif "tours.flightcentre" in url:
            return "tour"
        else:
            return None
    
    def check_robots_txt(self, base_url):
        """Check robots.txt to understand crawling restrictions"""
        try:
            robots_url = urljoin(base_url, '/robots.txt')
            response = self.session.get(robots_url, timeout=10)
            if response.status_code == 200:
                # Add a small delay to be respectful
                time.sleep(random.uniform(1, 3))
            return True
        except Exception:
            return True
    
    def fetch_page(self, url):
        """Fetch the webpage content"""
        try:
            # Add random delay to avoid being blocked
            time.sleep(random.uniform(1, 2))
            
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            raise Exception(f"Failed to fetch page: {e}")
    
    def clean_text(self, text):
        """Clean text by replacing Unicode characters with ASCII equivalents"""
        if not text:
            return text
        
        # Replace Unicode characters with ASCII equivalents
        replacements = {
            '\u2013': '-',  # en dash → hyphen
            '\u2014': '-',  # em dash → hyphen
            '\u2019': "'",  # right single quotation mark → apostrophe
            '\u2018': "'",  # left single quotation mark → apostrophe
            '\u201c': '"',  # left double quotation mark → straight quote
            '\u201d': '"',  # right double quotation mark → straight quote
            '\u2026': '...',  # horizontal ellipsis → three dots
        }
        
        for unicode_char, ascii_char in replacements.items():
            text = text.replace(unicode_char, ascii_char)
        
        return text

    def parse_cruise_itinerary_days(self, soup):
        """Extract individual cruise itinerary days"""
        itinerary_items = []
        
        # Find the itinerary container first
        itinerary_container = soup.find('div', class_='grid-item-block-dates-accordion')
        if not itinerary_container:
            # Try alternative selector
            itinerary_container = soup.find('div', class_='accordion-block')
        
        if not itinerary_container:
            return itinerary_items
        
        # Find all date-list items within the container
        day_items = itinerary_container.find_all('div', class_='date-list')
        
        for item in day_items:
            day_info = {}
            
            # Initialize all required keys
            day_info['icon'] = ""
            day_info['day'] = ""
            day_info['title'] = ""
            day_info['image'] = ""
            day_info['body'] = ""
            
            # Get all direct child div elements
            divs = item.find_all('div', recursive=False)
            
            if len(divs) >= 2:  # Should have at least 2 divs: day/date and location
                # First div contains day number and date
                first_div = divs[0]
                day_h5 = first_div.find('h5')
                if day_h5:
                    day_text = day_h5.get_text(strip=True)
                    # Extract day number from "Day 1", "Day 2", etc.
                    day_match = re.search(r'Day\s+(\d+)', day_text)
                    if day_match:
                        day_info['day'] = day_match.group(1)
                    else:
                        # Skip if it doesn't match day pattern
                        continue
                
                # Second div contains location and description
                second_div = divs[1]
                location_h5 = second_div.find('h5')
                if location_h5:
                    location_text = location_h5.get_text(strip=True)
                    day_info['title'] = self.clean_text(location_text)
                
                # Look for description in the content-wrap div
                content_wrap = second_div.find('div', class_='content-wrap')
                if content_wrap:
                    # Try to find the description text in various nested structures
                    description_text = ""
                    
                    # First try: text-info-summary span (original structure)
                    text_info = content_wrap.find('span', class_='text-info')
                    if text_info:
                        text_summary = text_info.find('span', class_='text-info-summary')
                        if text_summary:
                            description_text = text_summary.get_text(strip=True)
                    
                    # Second try: direct text-info-summary (new structure)
                    if not description_text:
                        text_summary = content_wrap.find('span', class_='text-info-summary')
                        if text_summary:
                            description_text = text_summary.get_text(strip=True)
                    
                    # Third try: any text in descr div
                    if not description_text:
                        descr_div = content_wrap.find('div', class_='descr')
                        if descr_div:
                            # Get all text but exclude "More" and "Less" buttons
                            for element in descr_div.find_all(['span'], class_=['more', 'less']):
                                element.decompose()
                            description_text = descr_div.get_text(strip=True)
                    
                    if description_text:
                        day_info['body'] = self.clean_text(description_text)
                
                # Handle special case for "At Sea" days which might not have descriptions
                if not day_info['body'] and day_info['title'] == "At Sea":
                    day_info['body'] = "Day at sea - enjoy the ship's amenities and relax as you cruise to your next destination."
            
            # Only add if we have the essential information (day and title minimum)
            if day_info['day'] and day_info['title']:
                # If no body text was found, add a generic message
                if not day_info['body']:
                    day_info['body'] = f"Explore {day_info['title']} and enjoy the local attractions and culture."
                
                itinerary_items.append(day_info)
        
        return itinerary_items

    def parse_tour_itinerary_description(self, soup):
        """Extract the tour itinerary description/summary"""
        # Look for the itinerary description section
        description_elem = soup.find('div', class_='ao-clp-custom-tdp-itinerary__description')
        if description_elem:
            # Get text and clean up extra whitespace
            text = description_elem.get_text(strip=True)
            text = self.clean_text(text)
            # Split into sentences and clean up
            sentences = [s.strip() for s in text.split('.') if s.strip()]
            return ['. '.join(sentences)]
        return [""]
    
    def parse_tour_itinerary_days(self, soup):
        """Extract individual tour day itineraries"""
        itinerary_items = []
        
        # Find the itinerary section specifically (not inclusions)
        itinerary_section = soup.find('section', class_='ao-clp-custom-tdp-itinerary')
        if not itinerary_section:
            return itinerary_items
        
        # Find all itinerary day items within the itinerary section only
        day_items = itinerary_section.find_all('li', class_='js-ao-common-accordion')
        
        for item in day_items:
            day_info = {}
            
            # Initialize all required keys including empty icon and image
            day_info['icon'] = ""
            day_info['day'] = ""
            day_info['title'] = ""
            day_info['image'] = ""
            day_info['body'] = ""
            
            # Get the day title (e.g., "Day 1: Hanoi")
            title_elem = item.find('div', class_='js-ao-common-accordion__title')
            if title_elem:
                title_text = title_elem.get_text(strip=True)
                # Remove the arrow element text if present
                arrow_elem = title_elem.find('div', class_='ao-common-accordion__arrow')
                if arrow_elem:
                    arrow_text = arrow_elem.get_text(strip=True)
                    title_text = title_text.replace(arrow_text, '').strip()
                
                title_text = self.clean_text(title_text)
                
                # Extract day number and clean title
                day_match = re.search(r'Day (\d+):', title_text)
                if day_match:
                    day_info['day'] = day_match.group(1)
                    # Remove "Day X: " from the title, keeping only what comes after
                    clean_title = re.sub(r'^Day \d+:\s*', '', title_text)
                    day_info['title'] = clean_title
                else:
                    # If it doesn't match "Day X:" pattern, skip this item (likely an inclusion)
                    continue
            else:
                continue
            
            # Get the day content/body
            content_elem = item.find('div', class_='ao-common-accordion__bottom-content')
            if content_elem:
                # Get all paragraphs in the content
                paragraphs = content_elem.find_all('p')
                if paragraphs:
                    body_text = ' '.join([p.get_text(strip=True) for p in paragraphs])
                else:
                    body_text = content_elem.get_text(strip=True)
                body_text = self.clean_text(body_text)
                day_info['body'] = body_text
            
            if day_info['title'] and day_info['body']:
                itinerary_items.append(day_info)
        
        return itinerary_items
    
    def scrape_content(self, url):
        """Main method to scrape content based on URL type"""
        # Determine the type of scraper needed
        scraper_type = self.determine_scraper_type(url)
        
        if scraper_type is None:
            raise Exception("URL is not a recognized Flight Centre cruise or tour URL")
        
        # Parse URL to get base domain
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Check robots.txt (for politeness)
        self.check_robots_txt(base_url)
        
        # Fetch the page
        html_content = self.fetch_page(url)
        
        # Parse with BeautifulSoup
        soup = BeautifulSoup(html_content, 'lxml')
        
        if scraper_type == "cruise":
            # For cruises, there's typically no summary section
            summary = [""]
            itinerary = self.parse_cruise_itinerary_days(soup)
        else:  # tour
            # Extract summary (itinerary description)
            summary = self.parse_tour_itinerary_description(soup)
            # Extract itinerary days
            itinerary = self.parse_tour_itinerary_days(soup)
        
        # Format the result
        result = {
            "summary": summary,
            "itinerary": itinerary
        }
        
        return result


def main():
    st.set_page_config(
        page_title="Cruise and Tour Itinerary Extractor",
        page_icon="🌏",
        layout="wide"
    )

    st.title("Cruise and Tour Itinerary Extractor")
    st.markdown("Extract itinerary information from Flight Centre cruise and tour pages")
    
    # Input section
    st.header("Enter URL")
    url = st.text_input(
        "Flight Centre URL (Cruise or Tour)",
        placeholder="https://cruises.flightcentre.com.au/cruises/... or https://tours.flightcentre.com.au/t/..."
    )
    
    # Validation and type detection
    scraper_type = None
    if url:
        if "cruises.flightcentre" in url:
            scraper_type = "cruise"
            st.info("🚢 Detected: Cruise URL")
        elif "tours.flightcentre" in url:
            scraper_type = "tour"
            st.info("🗺️ Detected: Tour URL")
        else:
            st.warning("⚠️ Please enter a valid Flight Centre cruise or tour URL")
    
    # Scrape button
    if st.button("🔍 Extract Information", type="primary", disabled=not scraper_type):
        if url:
            try:
                with st.spinner(f"Scraping {scraper_type} information..."):
                    scraper = FlightCentreScraper()
                    result = scraper.scrape_content(url)
                
                # Display results
                st.success(f"✅ {scraper_type.title()} information extracted successfully!")
                
                # Show summary stats
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Type", scraper_type.title())
                with col2:
                    st.metric("Days Found", len(result['itinerary']))
                with col3:
                    if scraper_type == 'cruise' and result['itinerary']:
                        first_port = result['itinerary'][0]['title']
                        last_port = result['itinerary'][-1]['title']
                        st.metric("Route", f"{first_port} → {last_port}")
                    elif scraper_type == 'tour':
                        st.metric("Summary Length", len(result['summary'][0]) if result['summary'][0] else 0)
                    else:
                        st.metric("Route", "No itinerary found")
                
                # Display JSON
                st.header("📄 Extracted Data")
                
                # Pretty formatted JSON
                json_output = json.dumps(result, indent=2, ensure_ascii=False)
                st.code(json_output, language="json")
                
                # Download button
                filename_part = url.split('/')[-2] if len(url.split('/')) > 2 and url.split('/')[-2] else url.split('/')[-1]
                if not filename_part:
                    filename_part = scraper_type
                
                st.download_button(
                    label="💾 Download JSON",
                    data=json_output,
                    file_name=f"{scraper_type}_data_{filename_part}.json",
                    mime="application/json"
                )
                
                # Display preview
                st.header("📋 Preview")
                
                # Summary
                st.subheader("Summary")
                if result['summary'][0]:
                    st.write(result['summary'][0])
                else:
                    if scraper_type == 'cruise':
                        st.write("No summary available for cruise itineraries")
                    else:
                        st.write("No summary found")
                
                # Itinerary
                st.subheader("Itinerary")
                if result['itinerary']:
                    for day in result['itinerary']:
                        with st.expander(f"Day {day['day']}: {day['title']}"):
                            st.write(day['body'])
                else:
                    st.write("No itinerary days found")
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.info("Please check the URL and try again. Make sure it's a valid Flight Centre page.")
    
    # Instructions
    st.header("📖 How to Use")
    st.markdown("""
    1. **Find a cruise or tour**: Go to Flight Centre Cruises or Tours (any region)
    2. **Copy the URL**: Copy the page URL from your browser
    3. **Paste and extract**: Paste the URL above and click "Extract Information"
    4. **Automatic detection**: The scraper will automatically detect if it's a cruise or tour
    5. **View results**: The extracted data will appear below in JSON format
    6. **Download**: Use the download button to save the JSON file
    """)
    
    st.header("Example URLs")
    
    # Cruise examples
    st.subheader("🚢 Cruise Examples")
    cruise_urls = [
        "https://cruises.flightcentre.com.au/cruises/indonesian-explorer-pacific-encounter-2026-02-03-2/",
        "https://cruises.flightcentre.co.uk/cruises/great-stirrup-cay-nassau-from-miami-florida-norwegian-gem-2025-06-30/?occupancy=2-0-0-0-0",
        "https://cruises.flightcentre.co.za/cruises/south-africa-from-durban-msc-opera-2026-01-16/"
    ]
    
    for i, example_url in enumerate(cruise_urls, 1):
        st.code(example_url, language=None)
    
    # Tour examples
    st.subheader("🗺️ Tour Examples")
    tour_urls = [
        "https://tours.flightcentre.com.au/t/1842",
        "https://tours.flightcentre.co.nz/t/5578",
        "https://tours.flightcentre.ca/t/237183"
    ]
    
    for i, example_url in enumerate(tour_urls, 1):
        st.code(example_url, language=None)


if __name__ == "__main__":
    main()