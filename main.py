import asyncio
import argparse
from scraper.orchestrator import ScraperOrchestrator
import logging
from pathlib import Path

def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

def read_urls_from_file(file_path: str) -> list[str]:
    with open(file_path, 'r') as f:
        return [line.strip() for line in f if line.strip()]

async def main():
    parser = argparse.ArgumentParser(description='Content Scraper')
    parser.add_argument('--team-id', required=True, help='Team ID for the scraper')
    parser.add_argument('--urls', nargs='+', help='URLs to scrape')
    parser.add_argument('--url-file', help='File containing URLs to scrape (one per line)')
    parser.add_argument('--output', required=True, help='Output JSON file path')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Get URLs
    urls = []
    if args.urls:
        urls.extend(args.urls)
    if args.url_file:
        urls.extend(read_urls_from_file(args.url_file))
    
    if not urls:
        print("Error: No URLs provided. Use --urls or --url-file")
        return
    
    # Create orchestrator and run
    orchestrator = ScraperOrchestrator(args.team_id)
    result = await orchestrator.scrape_and_save(urls, args.output)
    
    print(f"\nScraping completed!")
    print(f"Total items scraped: {len(result.items)}")
    print(f"Results saved to: {args.output}")

if __name__ == '__main__':
    asyncio.run(main()) 