import requests
import json
import time
import logging
import re
import sys
from datetime import datetime
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import config

# Configure logging with UTF-8 encoding
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('monitor.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Set console output encoding to UTF-8 for Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python < 3.7 doesn't have reconfigure
        pass


def parse_german_price(price_str: str) -> Optional[float]:
    """
    Parse German price format (e.g., "139,09 €" -> 139.09 or "126.32  / Monat" -> 126.32)
    Handles both "139,09" and "1.234,56" formats, and Unicode spaces
    """
    if not price_str:
        return None
    
    # Extract just the number part - everything before "/" or "Monat"
    # Handle Unicode spaces (\u2009, \u00A0, etc.) and regular spaces
    price_str = re.sub(r'[/\u2009\u00A0\s]+.*$', '', price_str, flags=re.UNICODE)
    
    # Remove currency symbols
    price_str = price_str.replace('€', '').replace('EUR', '').strip()
    
    # Remove all Unicode whitespace characters
    price_str = re.sub(r'[\u2000-\u200F\u2028-\u202F\u205F-\u206F]', '', price_str)
    
    # German format: dot is thousands separator, comma is decimal separator
    # If there's a comma, it's the decimal separator
    if ',' in price_str:
        # Remove dots (thousands separators) and replace comma with dot
        price_str = price_str.replace('.', '').replace(',', '.')
    else:
        # No comma, might be integer or already in English format
        # Check if dot is decimal separator (2 digits after) or thousands separator
        if '.' in price_str:
            parts = price_str.split('.')
            if len(parts) == 2 and len(parts[1]) <= 2:
                # Likely decimal separator (e.g., "126.32")
                pass  # Keep as is
            else:
                # Likely thousands separator, remove dots
                price_str = price_str.replace('.', '')
    
    # Extract just digits and one decimal point
    # Remove any remaining non-numeric characters except one dot/comma
    price_str = re.sub(r'[^\d.,]', '', price_str)
    
    try:
        return float(price_str)
    except ValueError:
        # Try to log without Unicode issues
        try:
            safe_str = price_str.encode('ascii', 'replace').decode('ascii')
            logger.warning(f"Could not parse price: {safe_str}")
        except:
            logger.warning("Could not parse price: [unparseable string]")
        return None


def get_offers_from_page(soup: BeautifulSoup, base_url: str) -> List[Dict]:
    """
    Extract all leasing offers from a single page
    """
    offers = []
    
    # Strategy 1: Find all price headings/divs with pattern "€ / Monat"
    price_elements = soup.find_all(string=re.compile(r'\d+[.,]\d+\s*€\s*/?\s*Monat', re.I))
    
    # Group price elements by their parent containers to avoid duplicates
    seen_containers = set()
    
    for price_elem in price_elements:
        # Find the parent container (article, div, section, etc.)
        parent = price_elem.find_parent(['article', 'div', 'section', 'li'])
        
        # Keep going up until we find a substantial container
        while parent:
            # Check if this looks like an offer container
            parent_text = parent.get_text()
            if len(parent_text) > 100:  # Substantial content
                parent_id = id(parent)
                if parent_id not in seen_containers:
                    seen_containers.add(parent_id)
                    try:
                        offer = extract_offer_details(parent, base_url)
                        if offer and offer['monthly_price']:
                            offers.append(offer)
                    except Exception as e:
                        logger.debug(f"Error extracting offer: {e}")
                break
            parent = parent.find_parent(['article', 'div', 'section', 'li'])
    
    # Strategy 2: If no offers found, try finding by class names
    if not offers:
        offer_cards = soup.find_all(['article', 'div'], class_=re.compile(r'offer|vehicle|card|item|product', re.I))
        for card in offer_cards:
            try:
                offer = extract_offer_details(card, base_url)
                if offer and offer['monthly_price']:
                    offers.append(offer)
            except Exception as e:
                logger.debug(f"Error extracting offer from card: {e}")
                continue
    
    logger.info(f"Found {len(offers)} offers on page")
    return offers


def extract_offer_details(card, base_url: str) -> Optional[Dict]:
    """
    Extract offer details from a card element
    """
    try:
        card_text = card.get_text()
        
        # Find price - look for pattern like "139,09 € / Monat"
        price_text = None
        price_match = re.search(r'(\d+[.,]\d+)\s*€\s*/?\s*Monat', card_text, re.I)
        if price_match:
            price_text = price_match.group(0)
        else:
            # Try finding in specific elements
            price_elem = card.find(string=re.compile(r'\d+[.,]\d+\s*€\s*/?\s*Monat', re.I))
            if price_elem:
                price_text = price_elem.strip()
        
        if not price_text:
            return None
        
        monthly_price = parse_german_price(price_text)
        if monthly_price is None:
            return None
        
        # Find model name - look for patterns like "308 SW ALLURE" or similar
        model = None
        # Try headings first
        for tag in ['h1', 'h2', 'h3', 'h4', 'h5']:
            model_elem = card.find(tag)
            if model_elem:
                text = model_elem.get_text(strip=True)
                # Check if it looks like a model name (contains numbers and letters, not just price)
                if text and len(text) > 5 and not re.match(r'^\d+[.,]\d+\s*€', text):
                    model = text
                    break
        
        # If no model found, try to extract from text patterns
        if not model:
            # Look for patterns like "308 SW", "2008", etc.
            model_match = re.search(r'(\d{3,4}\s*(?:SW|GT|ALLURE|STYLE|ACTIVE)?\s*[A-Z\s]+)', card_text)
            if model_match:
                model = model_match.group(1).strip()
        
        # Find dealer name - look for "Autohaus", "Peugeot", "Stellantis"
        dealer = None
        dealer_match = re.search(r'((?:Autohaus|Peugeot|Stellantis)[^\n]*?)(?:\n|$)', card_text, re.I)
        if dealer_match:
            dealer = dealer_match.group(1).strip()
        else:
            # Try finding in specific elements
            dealer_elem = card.find(string=re.compile(r'Autohaus|Peugeot|Stellantis', re.I))
            if dealer_elem:
                dealer_parent = dealer_elem.find_parent(['div', 'p', 'span', 'strong'])
                if dealer_parent:
                    dealer = dealer_parent.get_text(strip=True)
        
        # Find lease terms (e.g., "36 Mon. / 5.000 km" or "36 Monate / 5000 km")
        terms = None
        km_per_year = None
        terms_match = re.search(r'(\d+\s*Mon\.?\s*/\s*(\d+[.,]?\d*)\s*k?m)', card_text, re.I)
        if terms_match:
            terms = terms_match.group(1).strip()
            # Extract km value and convert to integer (handle formats like "5.000" or "5000")
            km_str = terms_match.group(2).replace('.', '').replace(',', '')
            try:
                km_per_year = int(km_str)
            except ValueError:
                km_per_year = None
        else:
            terms_elem = card.find(string=re.compile(r'\d+\s*Mon\.?\s*/\s*\d+', re.I))
            if terms_elem:
                terms = terms_elem.strip()
                # Try to extract km from the text
                km_match = re.search(r'/\s*(\d+[.,]?\d*)\s*k?m', terms, re.I)
                if km_match:
                    km_str = km_match.group(1).replace('.', '').replace(',', '')
                    try:
                        km_per_year = int(km_str)
                    except ValueError:
                        km_per_year = None
        
        # Find link to offer - look for "Jetzt leasen" or similar buttons
        link = None
        link_elem = card.find('a', href=True)
        if link_elem:
            href = link_elem['href']
            if href.startswith('http'):
                link = href
            elif href.startswith('/'):
                link = 'https://financing.peugeot.store' + href
            else:
                link = base_url.rstrip('/') + '/' + href.lstrip('/')
        
        # Create unique ID from model + dealer + price + terms
        # This helps identify the same offer even if slightly different
        unique_parts = [str(model or ''), str(dealer or ''), f"{monthly_price:.2f}", str(terms or '')]
        offer_id = '_'.join(unique_parts).replace(' ', '_').lower()
        # Clean up the ID
        offer_id = re.sub(r'[^\w_]', '', offer_id)
        
        return {
            'id': offer_id,
            'model': model or 'Unknown Model',
            'monthly_price': monthly_price,
            'dealer': dealer or 'Unknown Dealer',
            'terms': terms,
            'km_per_year': km_per_year,
            'link': link or base_url,
            'price_text': price_text
        }
    except Exception as e:
        logger.debug(f"Error extracting offer details: {e}")
        return None


def scrape_all_offers() -> List[Dict]:
    """
    Scrape all offers from the Peugeot store, handling pagination
    """
    all_offers = []
    page = 1
    base_url = config.STORE_URL
    
    while True:
        try:
            # Build URL with pagination (append &page=X if URL already has query parameters)
            if page == 1:
                url = base_url
            else:
                # Check if URL already has query parameters
                separator = '&' if '?' in base_url else '?'
                url = f"{base_url}{separator}page={page}"
            
            logger.info(f"Scraping page {page}: {url}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            # Extract offers from this page
            page_offers = get_offers_from_page(soup, base_url)
            
            if not page_offers:
                logger.info(f"No offers found on page {page}, stopping pagination")
                break
            
            all_offers.extend(page_offers)
            logger.info(f"Found {len(page_offers)} offers on page {page}")
            
            # Check if there's a next page
            # Look for pagination indicators
            next_link = soup.find('a', string=re.compile(r'»|next|weiter|>', re.I))
            if not next_link:
                # Try finding by aria-label or title
                next_link = soup.find('a', {'aria-label': re.compile(r'next|weiter', re.I)})
            
            if next_link:
                # Check if it's disabled
                if 'disabled' in next_link.get('class', []) or 'aria-disabled' in next_link.attrs:
                    break
            else:
                # Check if we're on the last page by looking for page numbers
                # If current page number equals max page number, stop
                page_info = soup.find(string=re.compile(r'\d+\s*von\s*\d+', re.I))
                if page_info:
                    match = re.search(r'(\d+)\s*von\s*(\d+)', page_info)
                    if match:
                        current = int(match.group(1))
                        total = int(match.group(2))
                        if current >= total:
                            break
                
                # If no next link and we got fewer offers than expected, might be last page
                if len(page_offers) < 10:  # Assuming at least 10 offers per page normally
                    logger.info("Few offers found, might be last page")
                    break
            
            page += 1
            
            # Safety limit to prevent infinite loops
            if page > 100:
                logger.warning("Reached page limit (100), stopping")
                break
            
            # Be respectful with requests
            time.sleep(2)
            
        except requests.RequestException as e:
            logger.error(f"Error fetching page {page}: {e}")
            break
        except Exception as e:
            logger.error(f"Unexpected error on page {page}: {e}")
            break
    
    logger.info(f"Total offers scraped: {len(all_offers)}")
    return all_offers


def filter_offers_by_price(offers: List[Dict], log: bool = False) -> List[Dict]:
    """
    Filter offers by price range and km allowance
    """
    filtered = []
    for offer in offers:
        # Check price range
        if not (config.MIN_PRICE <= offer['monthly_price'] <= config.MAX_PRICE):
            continue
        
        # Check km allowance (if km_per_year is None, include it - might be missing from some offers)
        if offer.get('km_per_year') is not None:
            if offer['km_per_year'] != config.KM_ALLOWANCE:
                continue
        
        filtered.append(offer)
    
    if log:
        logger.info(f"Filtered {len(filtered)} offers in price range €{config.MIN_PRICE}-€{config.MAX_PRICE} with {config.KM_ALLOWANCE} km/year")
    return filtered


def load_seen_offers() -> set:
    """
    Load previously seen offer IDs from file
    """
    try:
        with open(config.OFFERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return set(data.get('seen_offers', []))
    except FileNotFoundError:
        return set()
    except Exception as e:
        logger.error(f"Error loading seen offers: {e}")
        return set()


def save_seen_offers(seen_offers: set):
    """
    Save seen offer IDs to file
    """
    try:
        with open(config.OFFERS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'seen_offers': list(seen_offers)}, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving seen offers: {e}")


def send_discord_notification(offer: Dict):
    """
    Send a Discord webhook notification for a new offer
    """
    try:
        logger.info(f"Attempting to send Discord notification for: {offer['model']} - €{offer['monthly_price']:.2f}/month")
        
        # Format the message
        km_info = ""
        if offer.get('km_per_year'):
            km_info = f"\n**Kilometer:** {offer['km_per_year']:,} km/year"
        
        embed = {
            "title": f"🚗 New Leasing Offer: {offer['model']}",
            "description": f"**Monthly Rate:** €{offer['monthly_price']:.2f}{km_info}\n"
                          f"**Dealer:** {offer['dealer']}\n"
                          f"**Terms:** {offer.get('terms', 'N/A')}",
            "color": 0x00ff00,  # Green color
            "url": offer.get('link', config.STORE_URL),
            "footer": {
                "text": f"Peugeot Leasing Monitor • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }
        }
        
        # Add mention if Discord user ID is configured
        content = ""
        if config.DISCORD_USER_ID and config.DISCORD_USER_ID.strip():
            content = f"<@{config.DISCORD_USER_ID.strip()}>"
        
        payload = {
            "content": content,
            "embeds": [embed]
        }
        
        logger.debug(f"Sending webhook to: {config.DISCORD_WEBHOOK_URL[:50]}...")
        response = requests.post(config.DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"✅ Discord notification sent successfully for: {offer['model']} (€{offer['monthly_price']:.2f}/month)")
        return True
        
    except requests.RequestException as e:
        logger.error(f"❌ Network error sending Discord notification: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response body: {e.response.text[:200]}")
        return False
    except Exception as e:
        logger.error(f"❌ Error sending Discord notification: {e}", exc_info=True)
        return False


def check_for_new_offers():
    """
    Main function to check for new offers and send notifications
    Processes offers incrementally as pages are scraped
    """
    logger.info("Starting offer check...")
    
    # Load previously seen offers
    seen_offers = load_seen_offers()
    logger.info(f"Previously seen offers: {len(seen_offers)}")
    
    total_offers = 0
    total_filtered = 0
    total_new = 0
    
    try:
        page = 1
        base_url = config.STORE_URL
        
        # URL already contains all filters: 24 months / 15,000 km and 24 months / 20,000 km, max price 151€, radius 50km
        # No need to add additional filters
        
        while True:
            try:
                # Build URL with pagination (append &page=X if URL already has query parameters)
                if page == 1:
                    url = base_url
                else:
                    # Check if URL already has query parameters
                    separator = '&' if '?' in base_url else '?'
                    url = f"{base_url}{separator}page={page}"
                
                logger.info(f"Scraping page {page}: {url}")
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'lxml')
                
                # Extract offers from this page
                page_offers = get_offers_from_page(soup, base_url)
                
                if not page_offers:
                    logger.info(f"No offers found on page {page}, stopping pagination")
                    break
                
                total_offers += len(page_offers)
                logger.info(f"Found {len(page_offers)} offers on page {page} (Total so far: {total_offers})")
                
                # Filter by price range immediately
                filtered_page_offers = filter_offers_by_price(page_offers)
                total_filtered += len(filtered_page_offers)
                
                # Early stopping: If all offers on this page are above max price, we've gone past filtered results
                if page_offers:
                    all_above_max = all(offer['monthly_price'] > config.MAX_PRICE for offer in page_offers)
                    if all_above_max:
                        logger.info(f"All offers on page {page} are above max price (€{config.MAX_PRICE}). Stopping early.")
                        break
                    
                    # Also stop if we've gone many pages without finding any in-range offers
                    if page > 10 and total_filtered == 0:
                        logger.info(f"Scraped {page} pages with no offers in range. Stopping early.")
                        break
                
                if filtered_page_offers:
                    logger.info(f"  → {len(filtered_page_offers)} offers in price range (€{config.MIN_PRICE}-€{config.MAX_PRICE}) with {config.KM_ALLOWANCE} km/year on this page")
                    
                    # Check for new offers and notify immediately
                    new_page_offers = [offer for offer in filtered_page_offers if offer['id'] not in seen_offers]
                    
                    if new_page_offers:
                        total_new += len(new_page_offers)
                        logger.info(f"  → {len(new_page_offers)} NEW offers found on page {page}! Sending notifications...")
                        
                        for i, offer in enumerate(new_page_offers, 1):
                            km_info = f" ({offer.get('km_per_year', 'N/A')} km/year)" if offer.get('km_per_year') else ""
                            logger.info(f"  📢 [{i}/{len(new_page_offers)}] {offer['model']} - €{offer['monthly_price']:.2f}/month{km_info}")
                            send_discord_notification(offer)
                            seen_offers.add(offer['id'])
                            time.sleep(1)  # Small delay between notifications
                        
                        # Save after each page to persist progress
                        save_seen_offers(seen_offers)
                        logger.info(f"  ✅ Notifications sent for page {page}!")
                    else:
                        logger.info(f"  → All {len(filtered_page_offers)} offers on this page were already seen")
                    
                    # Mark all filtered offers as seen (even if not new, to track current state)
                    for offer in filtered_page_offers:
                        seen_offers.add(offer['id'])
                
                # Check if there's a next page
                next_link = soup.find('a', string=re.compile(r'»|next|weiter|>', re.I))
                if not next_link:
                    next_link = soup.find('a', {'aria-label': re.compile(r'next|weiter', re.I)})
                
                if next_link:
                    if 'disabled' in next_link.get('class', []) or 'aria-disabled' in next_link.attrs:
                        break
                else:
                    page_info = soup.find(string=re.compile(r'\d+\s*von\s*\d+', re.I))
                    if page_info:
                        match = re.search(r'(\d+)\s*von\s*(\d+)', page_info)
                        if match:
                            current = int(match.group(1))
                            total = int(match.group(2))
                            if current >= total:
                                break
                    
                    if len(page_offers) < 10:
                        logger.info("Few offers found, might be last page")
                        break
                
                page += 1
                
                # Limit pages to prevent very long runs (adjust based on typical filtered results)
                # If using price filter, should be much fewer pages
                max_pages = 50  # Reasonable limit for filtered results
                if page > max_pages:
                    logger.warning(f"Reached page limit ({max_pages}), stopping. If you're getting many pages, consider using website's price filter.")
                    break
                
                time.sleep(2)
                
            except requests.RequestException as e:
                logger.error(f"Error fetching page {page}: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error on page {page}: {e}")
                break
        
        # Final summary
        logger.info("=" * 60)
        logger.info(f"Scraping complete!")
        logger.info(f"Total offers scraped: {total_offers}")
        logger.info(f"Offers in price range (€{config.MIN_PRICE}-€{config.MAX_PRICE}) with {config.KM_ALLOWANCE} km/year: {total_filtered}")
        logger.info(f"New offers found and notified: {total_new}")
        logger.info(f"Total offers tracked: {len(seen_offers)}")
        logger.info("=" * 60)
        
        # Final save
        save_seen_offers(seen_offers)
        
    except Exception as e:
        logger.error(f"Error during offer check: {e}", exc_info=True)


def main():
    """
    Main monitoring loop
    """
    logger.info("Peugeot Leasing Monitor started")
    logger.info(f"Monitoring price range: €{config.MIN_PRICE}-€{config.MAX_PRICE}/month")
    logger.info(f"Check interval: {config.CHECK_INTERVAL} seconds ({config.CHECK_INTERVAL // 60} minutes)")
    
    # Run initial check
    check_for_new_offers()
    
    # Main loop
    while True:
        try:
            logger.info(f"Waiting {config.CHECK_INTERVAL} seconds until next check...")
            time.sleep(config.CHECK_INTERVAL)
            check_for_new_offers()
        except KeyboardInterrupt:
            logger.info("Monitor stopped by user")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            logger.info("Continuing after error...")
            time.sleep(60)  # Wait a minute before retrying after error


if __name__ == "__main__":
    main()

