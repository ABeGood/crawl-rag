import asyncio
from crawl4ai import (AsyncWebCrawler, 
                      BrowserConfig, 
                      CrawlerRunConfig,
                      CacheMode,
                      MemoryAdaptiveDispatcher,
                      CrawlerMonitor)

import xml.etree.ElementTree as ET
import requests
import logging
import pandas as pd
from parser import process_result

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


async def crawl_batch():
    browser_config = BrowserConfig(headless=True, verbose=False)
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        stream=False  # Default: get all results at once
    )

    # urls = get_urls()[300:401]
    urls = get_urls()

    logger.info(f'Number of urls: {len(urls)}')

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

        extracted_dicts_list = []

        # Process all results after completion
        for result in results:
            if result.success:
                data = await process_result(result)
                if data:
                    extracted_dicts_list.append(data)
                    logger.info(f'Data len: {len(extracted_dicts_list)}')

            else:
                print(f"Failed to crawl {result.url}: {result.error_message}")

        df = pd.DataFrame(extracted_dicts_list)
        df.to_csv('df.csv')


if __name__ == "__main__":
    # Set your API keys as environment variables:
    # export OPENAI_API_KEY="your-openai-key"
    # export GEMINI_API_KEY="your-gemini-key"
    
    asyncio.run(crawl_batch())
