import asyncio
from crawl4ai import (AsyncWebCrawler, 
                      BrowserConfig, 
                      CrawlerRunConfig,
                      CacheMode,
                      MemoryAdaptiveDispatcher,
                      CrawlerMonitor)

import xml.etree.ElementTree as ET
import requests
import os
import re
import logging
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Union
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crawl_log.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def get_urls(sitemap_url: str = "https://www.krasanamiru.cz/product-sitemap.xml") -> list[str]:
    """
    Extract product URLs from XML sitemap.
    
    Args:
        sitemap_url: URL of the XML sitemap
        
    Returns:
        List of product URLs
    """
    try:
        print(f"🔍 Fetching sitemap: {sitemap_url}")
        response = requests.get(sitemap_url, timeout=30)
        response.raise_for_status()
        
        # Parse XML
        root = ET.fromstring(response.content)
        
        # Handle namespace (common in sitemaps)
        namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        
        # Extract URLs
        urls = []
        for url_element in root.findall('.//ns:url', namespace):
            loc_element = url_element.find('ns:loc', namespace)
            if loc_element is not None:
                urls.append(loc_element.text)
        
        # Fallback: try without namespace
        if not urls:
            for url_element in root.findall('.//url'):
                loc_element = url_element.find('loc')
                if loc_element is not None:
                    urls.append(loc_element.text)
        
        print(f"✅ Found {len(urls)} URLs in sitemap")
        return urls
        
    except Exception as e:
        print(f"❌ Error fetching sitemap: {e}")
        return []

async def save_result_markdown(result, path='pages'):
    os.makedirs(path, exist_ok=True)

    filename = re.sub(r'[^\w\-_.]', '_', result.url.split('//')[-1]) + '.md'
    with open(f'{path}/{filename}', 'w', encoding='utf-8') as f:
            f.write(result.markdown)

async def save_result_full_html(result, path='pages'):
    os.makedirs(path, exist_ok=True)

    filename = re.sub(r'[^\w\-_.]', '_', result.url.split('//')[-1]) + '-full' + '.html'
    with open(f'{path}/{filename}', 'w', encoding='utf-8') as f:
            f.write(result.html)

async def save_result_clean_html(result, path='pages'):
    os.makedirs(path, exist_ok=True)

    filename = re.sub(r'[^\w\-_.]', '_', result.url.split('//')[-1]) + '-clean' + '.html'
    with open(f'{path}/{filename}', 'w', encoding='utf-8') as f:
            f.write(result.cleaned_html)

def save_extracted_data(result, data, path='pages'):
    os.makedirs(path, exist_ok=True)

    filename = re.sub(r'[^\w\-_.]', '_', result.url.split('//')[-1]) + '.json'
    with open(f'{path}/{filename}', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def process_result(result):
    # Parse HTML and find main div
    soup = BeautifulSoup(result.html, 'html.parser')
    main_div = soup.find('main')
    
    if main_div:
        main_content = main_div.get_text()
        
        if "404" in main_content:
            logger.warning(f"SKIPPED - 404 Error in main: {result.url}")
            return
        
        if "již se neprodává" in main_content:
            logger.warning(f"SKIPPED - Product no longer sold in main: {result.url}")
            return
        
        logger.info(f"Extracting data: {result.url}")
        data = extract_data(main_div, result.url)
        save_extracted_data(result, data)
    
    # Process successful results
    logger.info(f"Processing: {result.url}")
    # await save_result_markdown(result)
    # await save_result_full_html(result)

    # await save_result_clean_html(result)

def extract_data(div, url:str) -> Dict[str, Union[str, List[str], float, None]]:
    
    data = {
        'url': url,
        'category': None,
        'volume': None,
        'purpose': None,
        'description': None,
        'suitable_for': None,
        'how_to_use': None,
        'ingredients': None
    }
    
    # Extract category from breadcrumbs
    breadcrumbs = div.find('div', class_='breadcrumbs')
    if breadcrumbs:
        links = breadcrumbs.find_all('a')
        category = [link.get_text().strip() for link in links[1:]]  # Skip first "Krása na míru"
        
        # Add the last breadcrumb (current page)
        last_breadcrumb = breadcrumbs.find('span', class_='breadcrumb_last')
        if last_breadcrumb:
            category.append(last_breadcrumb.get_text().strip())
        
        data['category'] = category if category else None
    
    # Extract data from productContent
    product_content = div.find('div', class_='productContent')
    if product_content:
        content_text = product_content.get_text()
        
        # Extract volume
        volume_match = re.search(r'Obsah:\s*(\d+(?:\.\d+)?)\s*ml', content_text, re.IGNORECASE)
        if volume_match:
            data['volume'] = float(volume_match.group(1))
        
        # Extract all paragraphs
        paragraphs = product_content.find_all('p')
        
        for p in paragraphs:
            p_text = p.get_text().strip()
            
            # Extract purpose (first paragraph with only strong content)
            if not data['purpose']:
                strong_only = p.find('strong')
                if strong_only and p_text == strong_only.get_text().strip():
                    data['purpose'] = p_text
                    continue
            
            # Extract description (paragraph starting with "Jednorázová")
            if not data['description'] and ('Jednorázová' in p_text or 'plátýnková maska' in p_text):
                data['description'] = p_text
                continue
            
            # Extract suitable_for
            if 'Vhodná pro:' in p_text:
                data['suitable_for'] = re.sub(r'^.*?Vhodná pro:\s*', '', p_text).strip()
                continue
            elif 'Typ pleti' in p_text:
                data['suitable_for'] = re.sub(r'^.*?Typ pleti[:\s]*', '', p_text).strip()
                continue
            
            # Extract how_to_use
            if 'Jak použít:' in p_text:
                data['how_to_use'] = re.sub(r'^.*?Jak použít:\s*', '', p_text).strip()
                continue
    
    # Extract ingredients
    ingredients_section = div.find('div', class_='ingrediences')
    if ingredients_section:
        text_content = ingredients_section.find('div', class_='text-content')
        if text_content:
            ingredients_text = text_content.get_text().strip()
            # Clean up ingredients text
            if ingredients_text.startswith('Ingredients:'):
                ingredients_text = ingredients_text[12:].strip()
            data['ingredients'] = ingredients_text
    
    return data

async def crawl_batch():
    browser_config = BrowserConfig(headless=True, verbose=False)
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        stream=False  # Default: get all results at once
    )

    urls = get_urls()

    dispatcher = MemoryAdaptiveDispatcher(
        memory_threshold_percent=70.0,
        check_interval=1.0,
        max_session_permit=10,
        monitor=CrawlerMonitor()
    )


    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Get all results at once
        results = await crawler.arun_many(
            urls=urls,
            config=run_config,
            dispatcher=dispatcher
        )

        # Process all results after completion
        for result in results:
            if result.success:
                await process_result(result)

            else:
                print(f"Failed to crawl {result.url}: {result.error_message}")


if __name__ == "__main__":
    # Set your API keys as environment variables:
    # export OPENAI_API_KEY="your-openai-key"
    # export GEMINI_API_KEY="your-gemini-key"
    
    asyncio.run(crawl_batch())
