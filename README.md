# Content Ingestion & Scraping System

A modular, extensible, and robust system for ingesting and structuring technical knowledge from a variety of sources (blogs, PDFs, and more), outputting clean markdown in a consistent JSON schema. Now includes a FastAPI server for programmatic access.

---

## **Features**

- **Multi-source ingestion:** Blogs, PDFs, and more (easily extensible).
- **Automatic content type detection:** URLs and file types are routed to the correct scraper.
- **Advanced crawling:** Handles static, dynamic (JavaScript), and API-driven sites.
- **Powerful PDF extraction:** Uses `pdfplumber` for accurate text extraction, with chunking and cleaning.
- **Markdown output:** All content is normalized and output as markdown.
- **Intelligent chunking:** Long content (e.g., PDFs) is split at sentence boundaries for downstream processing.
- **Async processing:** Fast, scalable, and non-blocking.
- **Comprehensive error handling:** Logs and skips failures, never halts the pipeline.
- **Progress tracking:** Uses `tqdm` for real-time feedback.
- **Extensible architecture:** Add new scrapers for new content types with minimal code changes.
- **REST API:** Expose crawling and scraping via a FastAPI server.

---

## **Project Structure**

```
GREAT/
  main.py                # CLI entry point
  fastapi_server.py      # FastAPI server for programmatic access
  requirements.txt       # All dependencies
  setup.py               # Setup script for environment and NLTK data
  README.md              # Documentation
  output.json            # Example output
  p.pdf                  # Example PDF
  scraper/
    base.py              # Base scraper class and data models
    blog_scraper.py      # Blog/article scraper (markdown, metadata)
    pdf_scraper.py       # PDF scraper (chunking, cleaning)
    content_crawler.py   # Smart crawler (RSS, Playwright, API, BS4, etc.)
    blog_crawler.py      # Blog-specific crawler (legacy)
    orchestrator.py      # Orchestrates crawling, scraping, and output
```

---

## **Setup & Installation**

### **1. Clone the Repository**


### **2. Create and Activate a Virtual Environment**
```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Unix/Mac:
source .venv/bin/activate
```

### **3. Install Dependencies**
```bash
pip install -r requirements.txt
```

### **4.Install Playwright Browsers**
```bash
playwright install
```

### **5. Download NLTK Data**
```bash
python setup.py
```

---

## **Dataflow & Process**

1. **Input:**  
   - URLs (blog, article, or PDF) or file paths are provided via CLI or API.
2. **Content Type Detection:**  
   - The system determines the type (blog, PDF, etc.) and routes to the appropriate scraper.
3. **Crawling:**  
   - For web sources, the crawler discovers all relevant content URLs using a multi-strategy approach (feeds, APIs, JS automation, static HTML, sitemaps).
4. **Scraping:**  
   - Each discovered URL or file is scraped using the appropriate tool, extracting clean, structured content.
5. **Chunking & Normalization:**  
   - Content is split into logical chunks and normalized to markdown.
6. **Output:**  
   - All results are saved in a consistent JSON schema for downstream use.

---

## **Techniques & Methods**

### **Crawling & Discovery**
- **RSS/Atom Feed Discovery:** First attempts to find and parse feeds for fast, structured link discovery.
- **Playwright Automation:** For JavaScript-heavy sites, simulates user interaction, scrolling, and network interception.
- **API Reverse Engineering:** Attempts to find and use backend APIs for direct content discovery.
- **BeautifulSoup Heuristics:** Parses static HTML for links, titles, and reconstructs URLs if needed.
- **Sitemap Parsing:** As a last resort, parses `/sitemap.xml` for content URLs.
- **Cloudscraper & Undetected Chrome:** Bypass anti-bot and Cloudflare protections for difficult sites.

### **Scraping & Extraction**
- **Blog Scraper:** Uses a multi-strategy fallback approach:
  1. Tries `newspaper3k` for extraction.
  2. If that fails, uses manual BeautifulSoup extraction (custom logic for main content).
  3. If that fails, falls back to extracting all `<p>` tags as a last resort.
  4. If that fails, uses Selenium to render the page and extract content (for JavaScript-heavy sites).
  5. If all else fails, aggressively extracts all visible text from the `<body>` tag.
  This ensures robust extraction from a wide variety of blog sites, including those with non-standard or dynamic structures.
- **PDF Scraper:** Uses `pdfplumber` for robust text extraction, skips images, cleans filler lines, and splits content into sentence-aligned chunks. Outputs as markdown.
- **Content Normalization:** All content is cleaned, unicode-normalized, and output as markdown using `html2text`.

### **Chunking**
- **Intelligent Chunking:** For long-form content (e.g., PDFs), splits output into ~6000 character chunks, always at sentence boundaries, ensuring readability and logical completeness.

---
## **CLI Usage**

### **Basic Usage**
```bash
python main.py --team-id "aline123" --urls "https://quill.co/blog" --output "output.json"
```

### **Scraping a PDF**
```bash
python main.py --team-id "aline123" --urls "C:/path/to/file.pdf" --output "output.json"
```

### **Multiple Sources**
```bash
python main.py --team-id "aline123" --urls "https://example.com/blog" "C:/path/to/file.pdf" --output "output.json"
```

---

## **Output Schema**

All results are saved in a consistent JSON schema:

```json
{
  "team_id": "aline123",
  "items": [
    {
      "title": "Item Title",
      "content": "Markdown content",
      "content_type": "blog|podcast_transcript|call_transcript|linkedin_post|reddit_comment|book|other",
      "source_url": "optional-url",
      "author": "",
      "user_id": ""
    }
  ]
}
```


## **API Usage (FastAPI Server)**

### **Start the Server**
```bash
python fastapi_server.py
# or
uvicorn fastapi_server:app --reload
```

### **Endpoints**

#### **POST `/crawl`**
Trigger the content crawler to crawl a website and return discovered content URLs.

**Request Body:**
```json
{
  "start_url": "https://example.com",  // (required) The URL to start crawling from
  "max_pages": 10                      // (optional) Maximum number of pages to crawl (default: 10)
}
```

**Example:**
```bash
curl -X POST "http://localhost:8000/crawl" \
  -H "Content-Type: application/json" \
  -d '{"start_url": "https://quill.co/blog", "max_pages": 5}'
```

**Response:**
```json
{
  "results": {
    "blog": [
      "https://quill.co/blog/post1",
      "https://quill.co/blog/post2"
    ],
    "unknown": [
      "https://quill.co/other"
    ]
  }
}
```

#### **API Documentation**
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---





## **Troubleshooting**

- **No output?** Check logs for errors, ensure dependencies are installed, and that the input URLs/files are accessible.
- **PDF not extracting?** Ensure the file is not encrypted or image-only (OCR not enabled by default).
- **JavaScript-heavy site not working?** Ensure Playwright browsers are installed (`playwright install`).
- **API not responding?** Ensure all dependencies are installed and the server is running.

---

