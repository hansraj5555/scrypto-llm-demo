#!/usr/bin/env python3
"""
Documentation Harvesting Script

Harvests official Radix docs and scrypto-examples for use as LLM context.
Stores raw and cleaned versions with metadata tracking.
"""

import os
import json
import requests
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
import subprocess
import tempfile
import shutil
import re

class ScryptoDocHarvester:
    def __init__(self):
        self.kb_dir = Path("kb")
        self.raw_dir = self.kb_dir / "raw"
        self.cleaned_dir = self.kb_dir / "cleaned"
        
        # Create directories
        for dir_path in [self.kb_dir, self.raw_dir, self.cleaned_dir]:
            dir_path.mkdir(exist_ok=True)
        
        self.metadata = {
            "harvest_timestamp": datetime.utcnow().isoformat(),
            "sources": [],
            "raw_files": 0,
            "cleaned_files": 0,
            "total_size_bytes": 0
        }
    
    def harvest_scrypto_examples(self) -> bool:
        """Harvest official scrypto-examples repository."""
        
        print("📥 Harvesting scrypto-examples repository...")
        
        try:
            # Clone to temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                repo_path = temp_path / "scrypto-examples"
                
                # Clone repository
                result = subprocess.run([
                    "git", "clone", "--depth", "1",
                    "https://github.com/radixdlt/scrypto-examples.git",
                    str(repo_path)
                ], capture_output=True, text=True)
                
                if result.returncode != 0:
                    print(f"❌ Failed to clone scrypto-examples: {result.stderr}")
                    return False
                
                # Find all Rust/Scrypto files
                rust_files = list(repo_path.rglob("*.rs"))
                toml_files = list(repo_path.rglob("Cargo.toml"))
                md_files = list(repo_path.rglob("*.md"))
                
                file_count = 0
                
                # Process Rust files
                for rs_file in rust_files:
                    if self._is_valuable_rust_file(rs_file):
                        content = rs_file.read_text(encoding='utf-8', errors='ignore')
                        
                        # Save raw
                        raw_filename = f"examples_{rs_file.parent.name}_{rs_file.name}"
                        raw_path = self.raw_dir / raw_filename
                        raw_path.write_text(content, encoding='utf-8')
                        
                        # Clean and save
                        cleaned_content = self._clean_rust_content(content, str(rs_file))
                        cleaned_path = self.cleaned_dir / raw_filename.replace('.rs', '_cleaned.md')
                        cleaned_path.write_text(cleaned_content, encoding='utf-8')
                        
                        file_count += 1
                        self.metadata["total_size_bytes"] += len(content.encode('utf-8'))
                
                # Process key documentation files
                for md_file in md_files:
                    if md_file.name.lower() in ['readme.md', 'tutorial.md', 'guide.md']:
                        content = md_file.read_text(encoding='utf-8', errors='ignore')
                        
                        raw_filename = f"docs_{md_file.parent.name}_{md_file.name}"
                        raw_path = self.raw_dir / raw_filename
                        raw_path.write_text(content, encoding='utf-8')
                        
                        cleaned_content = self._clean_markdown_content(content)
                        cleaned_path = self.cleaned_dir / raw_filename
                        cleaned_path.write_text(cleaned_content, encoding='utf-8')
                        
                        file_count += 1
                        self.metadata["total_size_bytes"] += len(content.encode('utf-8'))
                
                print(f"✅ Harvested {file_count} files from scrypto-examples")
                
                self.metadata["sources"].append({
                    "name": "scrypto-examples",
                    "url": "https://github.com/radixdlt/scrypto-examples",
                    "files_harvested": file_count,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                return True
                
        except Exception as e:
            print(f"❌ Error harvesting scrypto-examples: {e}")
            return False
    
    def harvest_radix_docs(self) -> bool:
        """Harvest key documentation from Radix docs site."""
        
        print("📥 Harvesting official Radix documentation...")
        
        # Key documentation URLs to fetch
        doc_urls = [
            ("scrypto_overview", "https://docs.radixdlt.com/docs/scrypto-overview"),
            ("blueprint_basics", "https://docs.radixdlt.com/docs/blueprint-basics"),
            ("resource_creation", "https://docs.radixdlt.com/docs/resource-creation"),
            ("component_creation", "https://docs.radixdlt.com/docs/component-creation"),
            ("asset_oriented_programming", "https://docs.radixdlt.com/docs/asset-oriented-programming"),
            ("getting_started", "https://docs.radixdlt.com/docs/getting-started-scrypto")
        ]
        
        successful = 0
        
        for doc_name, url in doc_urls:
            try:
                print(f"  📄 Fetching {doc_name}...")
                
                response = requests.get(url, timeout=30)
                if response.status_code == 200:
                    content = response.text
                    
                    # Save raw HTML
                    raw_filename = f"radix_docs_{doc_name}.html"
                    raw_path = self.raw_dir / raw_filename
                    raw_path.write_text(content, encoding='utf-8')
                    
                    # Extract and clean text content
                    cleaned_content = self._extract_and_clean_html(content, doc_name)
                    cleaned_filename = f"radix_docs_{doc_name}.md"
                    cleaned_path = self.cleaned_dir / cleaned_filename
                    cleaned_path.write_text(cleaned_content, encoding='utf-8')
                    
                    successful += 1
                    self.metadata["total_size_bytes"] += len(content.encode('utf-8'))
                    
                else:
                    print(f"  ⚠️  Failed to fetch {doc_name}: HTTP {response.status_code}")
                    
                # Be respectful with rate limiting
                time.sleep(1)
                
            except Exception as e:
                print(f"  ❌ Error fetching {doc_name}: {e}")
        
        print(f"✅ Successfully harvested {successful}/{len(doc_urls)} documentation pages")
        
        self.metadata["sources"].append({
            "name": "radix-docs",
            "base_url": "https://docs.radixdlt.com", 
            "files_harvested": successful,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return successful > 0
    
    def _is_valuable_rust_file(self, file_path: Path) -> bool:
        """Check if a Rust file is valuable for learning."""
        
        # Skip test files, build files, etc.
        skip_patterns = [
            'target/', 'tests/', '.git/', 
            'build.rs', 'main.rs'  # Skip unless it's example main
        ]
        
        file_str = str(file_path)
        if any(pattern in file_str for pattern in skip_patterns):
            # Allow main.rs in example directories
            if 'example' not in file_str.lower() and 'main.rs' in file_str:
                return False
        
        # Must have Scrypto-related content
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            scrypto_indicators = [
                'use scrypto::', '#[blueprint]', 'ComponentAddress',
                'ResourceAddress', 'Bucket', 'Vault', 'impl'
            ]
            return any(indicator in content for indicator in scrypto_indicators)
        except:
            return False
    
    def _clean_rust_content(self, content: str, file_path: str) -> str:
        """Clean and structure Rust content for LLM training."""
        
        lines = content.split('\n')
        cleaned_lines = []
        
        # Add header
        cleaned_lines.append(f"# Scrypto Example: {Path(file_path).stem}")
        cleaned_lines.append(f"Source: {file_path}")
        cleaned_lines.append("")
        
        # Process content
        in_comment_block = False
        current_section = ""
        
        for line in lines:
            line = line.rstrip()
            
            # Handle multi-line comments
            if '/*' in line:
                in_comment_block = True
            if '*/' in line:
                in_comment_block = False
                continue
            
            if in_comment_block:
                continue
            
            # Remove single-line comments but preserve doc comments
            if line.strip().startswith('//') and not line.strip().startswith('///'):
                continue
            
            # Identify sections
            if line.strip().startswith('use '):
                if current_section != "imports":
                    cleaned_lines.append("## Imports")
                    cleaned_lines.append("```rust")
                    current_section = "imports"
            elif line.strip().startswith('#[blueprint]'):
                if current_section:
                    cleaned_lines.append("```")
                cleaned_lines.append("## Blueprint Definition")
                cleaned_lines.append("```rust")
                current_section = "blueprint"
            elif line.strip().startswith('impl '):
                if current_section and current_section != "impl":
                    cleaned_lines.append("```")
                    cleaned_lines.append("## Implementation")
                    cleaned_lines.append("```rust")
                current_section = "impl"
            
            cleaned_lines.append(line)
        
        # Close final code block
        if current_section:
            cleaned_lines.append("```")
        
        return '\n'.join(cleaned_lines)
    
    def _clean_markdown_content(self, content: str) -> str:
        """Clean markdown content."""
        
        # Remove excessive whitespace
        lines = [line.rstrip() for line in content.split('\n')]
        
        # Remove empty lines at start/end
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        
        return '\n'.join(lines)
    
    def _extract_and_clean_html(self, html_content: str, doc_name: str) -> str:
        """Extract and clean text from HTML documentation."""
        
        # Simple HTML text extraction (you could use BeautifulSoup for better results)
        import re
        
        # Remove script and style elements
        html_content = re.sub(r'<script.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        html_content = re.sub(r'<style.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        
        # Convert common HTML entities
        html_content = html_content.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
        
        # Remove HTML tags but preserve structure
        text_content = re.sub(r'<[^>]+>', '', html_content)
        
        # Clean up whitespace
        lines = [line.strip() for line in text_content.split('\n') if line.strip()]
        
        # Add header
        result_lines = [
            f"# Radix Documentation: {doc_name.replace('_', ' ').title()}",
            f"Extracted from: Radix DLT Documentation",
            f"Harvest date: {datetime.utcnow().strftime('%Y-%m-%d')}",
            "",
            *lines
        ]
        
        return '\n'.join(result_lines)
    
    def save_metadata(self):
        """Save harvest metadata."""
        
        # Update file counts
        self.metadata["raw_files"] = len(list(self.raw_dir.glob("*")))
        self.metadata["cleaned_files"] = len(list(self.cleaned_dir.glob("*")))
        
        # Save metadata
        metadata_path = self.kb_dir / "metadata.json"
        with open(metadata_path, 'w') as f:
            json.dump(self.metadata, f, indent=2)
        
        print(f"💾 Saved metadata: {self.metadata['raw_files']} raw files, {self.metadata['cleaned_files']} cleaned files")
    
    def run_full_harvest(self) -> bool:
        """Run complete harvest of all sources."""
        
        print("🚀 Starting complete documentation harvest...")
        print("=" * 50)
        
        success_count = 0
        
        # Harvest scrypto examples
        if self.harvest_scrypto_examples():
            success_count += 1
        
        # Small delay between harvests
        time.sleep(2)
        
        # Harvest official docs
        if self.harvest_radix_docs():
            success_count += 1
        
        # Save metadata
        self.save_metadata()
        
        print("=" * 50)
        if success_count > 0:
            print(f"✅ Harvest complete! {success_count} sources processed.")
            print(f"📊 Total files: {self.metadata['raw_files']} raw, {self.metadata['cleaned_files']} cleaned")
            print(f"💽 Total size: {self.metadata['total_size_bytes'] / 1024:.1f} KB")
            return True
        else:
            print("❌ Harvest failed - no sources processed successfully")
            return False

def main():
    """Command line interface for harvesting."""
    
    harvester = ScryptoDocHarvester()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "examples":
            success = harvester.harvest_scrypto_examples()
        elif command == "docs":
            success = harvester.harvest_radix_docs()
        elif command == "clean":
            # Clean existing harvest
            import shutil
            if harvester.raw_dir.exists():
                shutil.rmtree(harvester.raw_dir)
            if harvester.cleaned_dir.exists():
                shutil.rmtree(harvester.cleaned_dir)
            harvester.raw_dir.mkdir()
            harvester.cleaned_dir.mkdir()
            print("🧹 Cleaned existing harvest")
            return
        else:
            print("Usage: python harvest_docs.py [examples|docs|clean]")
            return
    else:
        # Run full harvest
        success = harvester.run_full_harvest()
    
    harvester.save_metadata()
    
    if not success:
        exit(1)

if __name__ == "__main__":
    import sys
    main()