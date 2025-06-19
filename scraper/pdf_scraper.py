import PyPDF2
from typing import List, Optional, Tuple
from .base import BaseScraper, ContentItem
import re
from pathlib import Path
import os
import requests
from io import BytesIO
from datetime import datetime
import pdfplumber
import html2text

class PDFScraper(BaseScraper):
    def __init__(self, team_id: str, chunk_size: int = 1000):
        super().__init__(team_id)
        self.chunk_size = chunk_size

    def can_handle(self, url: str) -> bool:
        """Check if the URL points to a PDF file."""
        return url.lower().endswith('.pdf')

    async def scrape(self, url: str, base_url: str = None) -> List[ContentItem]:
        """Scrape content from a PDF file using pdfplumber, clean and output as markdown, split into sentence-aligned chunks, and remove filler lines."""
        items = []
        h2t = html2text.HTML2Text()
        h2t.ignore_links = False
        h2t.ignore_images = True
        h2t.body_width = 0
        try:
            # Support both local file and URL
            if url.lower().startswith('http'):
                response = requests.get(url)
                with open('temp_downloaded.pdf', 'wb') as f:
                    f.write(response.content)
                pdf_path = 'temp_downloaded.pdf'
            else:
                pdf_path = url
            with pdfplumber.open(pdf_path) as pdf:
                full_text = ""
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    full_text += text + "\n"
            # Clean up the text
            full_text = re.sub(r'\n{3,}', '\n\n', full_text.strip())
            # Remove lines that are only repeated dots or similar filler
            full_text = '\n'.join(
                line for line in full_text.splitlines()
                if not re.fullmatch(r'[.\s·•\-]{5,}', line.strip())
            )
            # Convert to markdown
            markdown = h2t.handle(full_text)
            markdown = re.sub(r'\n{3,}', '\n\n', markdown.strip())
            # Remove lines that are only repeated dots or similar filler in markdown too
            markdown = '\n'.join(
                line for line in markdown.splitlines()
                if not re.fullmatch(r'[.\s·•\-]{5,}', line.strip())
            )
            # Split into sentence-aligned chunks (6000 chars max, but only at sentence boundaries)
            chunk_size = 6000
            sentences = re.split(r'(?<=[.!?])\s+', markdown)
            chunks = []
            current_chunk = ""
            for sentence in sentences:
                if not sentence.strip():
                    continue
                if len(current_chunk) + len(sentence) + 1 <= chunk_size:
                    if current_chunk:
                        current_chunk += " " + sentence
                    else:
                        current_chunk = sentence
                else:
                    chunks.append(current_chunk.strip())
                    current_chunk = sentence
            if current_chunk:
                chunks.append(current_chunk.strip())
            for idx, chunk in enumerate(chunks):
                items.append(ContentItem(
                    title=f"{os.path.basename(pdf_path)} (part {idx+1})" if len(chunks) > 1 else os.path.basename(pdf_path),
                    content=chunk,
                    content_type="blog",  # or "other" or "pdf" if you want
                    source_url=url,
                    author="",
                    user_id=""
                ))
            # Clean up temp file if used
            if url.lower().startswith('http'):
                os.remove('temp_downloaded.pdf')
            return items
        except Exception as e:
            self.logger.error(f"Error scraping PDF {url}: {str(e)}")
            return []

    def _process_pdf(self, pdf_file: BytesIO, source_url: str) -> List[ContentItem]:
        """Process PDF content and return chunks as ContentItems."""
        reader = PyPDF2.PdfReader(pdf_file)
        items = []

        # Extract metadata
        metadata = reader.metadata
        title = metadata.get('/Title', 'Untitled Document')
        author = metadata.get('/Author', None)
        date = metadata.get('/CreationDate', None)

        # Process each page
        current_chunk = []
        current_length = 0
        chapter_title = None

        for page in reader.pages:
            text = page.extract_text()
            if not text.strip():
                continue

            # Try to detect chapter titles
            potential_title = self._detect_chapter_title(text)
            if potential_title:
                # Save previous chunk if exists
                if current_chunk:
                    items.append(self._create_chunk_item(
                        current_chunk,
                        chapter_title or title,
                        source_url,
                        author,
                        date
                    ))
                current_chunk = []
                current_length = 0
                chapter_title = potential_title

            # Split text into paragraphs
            paragraphs = text.split('\n\n')
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue

                if current_length + len(para) > self.chunk_size and current_chunk:
                    items.append(self._create_chunk_item(
                        current_chunk,
                        chapter_title or title,
                        source_url,
                        author,
                        date
                    ))
                    current_chunk = []
                    current_length = 0

                current_chunk.append(para)
                current_length += len(para)

        # Add the last chunk if exists
        if current_chunk:
            items.append(self._create_chunk_item(
                current_chunk,
                chapter_title or title,
                source_url,
                author,
                date
            ))

        return items

    def _detect_chapter_title(self, text: str) -> Optional[str]:
        """Detect if the text contains a chapter title."""
        # Common chapter title patterns
        patterns = [
            r'^Chapter\s+\d+[.:]\s*(.+)$',
            r'^\d+[.:]\s*(.+)$',
            r'^[IVX]+[.:]\s*(.+)$',
        ]

        first_line = text.split('\n')[0].strip()
        for pattern in patterns:
            match = re.match(pattern, first_line, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _create_chunk_item(
        self,
        paragraphs: List[str],
        title: str,
        source_url: str,
        author: Optional[str],
        date: Optional[str]
    ) -> ContentItem:
        """Create a ContentItem from a chunk of paragraphs."""
        content = '\n\n'.join(paragraphs)
        return ContentItem(
            title=f"{title} - Part {len(paragraphs)}",
            content=self.normalize_content(content),
            content_type="book",
            source_url=source_url,
            author=author,
            published_date=date,
            metadata={
                "chunk_size": len(content),
                "paragraph_count": len(paragraphs)
            }
        )

    def normalize_content(self, content: str) -> str:
        """Normalize PDF content to clean markdown."""
        content = super().normalize_content(content)
        
        # Fix common PDF extraction issues
        content = re.sub(r'\s+', ' ', content)  # Remove extra whitespace
        content = re.sub(r'([.!?])\s+([A-Z])', r'\1\n\n\2', content)  # Add paragraph breaks
        content = re.sub(r'([.!?])\s+([A-Z])', r'\1\n\n\2', content)  # Add paragraph breaks
        
        return content.strip() 