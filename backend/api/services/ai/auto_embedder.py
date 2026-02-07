"""
Auto-Embedder Service — Fast Background Embedding with Semantic Reranking

Automatically embeds only admin-configured groups into ChromaDB after conversion.
Features:
  - Background worker with progress tracking
  - Fast batch processing
  - Semantic chunking with optimal strategies
  - Only embeds admin-configured groups (strict filtering)
  - Advanced RAG with semantic reranking

Used by UnifiedRAGService from advanced_ai_service.
"""
# pyright: reportUnknownMemberType=false, reportUnknownParameterType=false

import json
import logging
import threading
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass, field
from collections import Counter

from api.core.config import settings

logger = logging.getLogger(__name__)

# LXML is required for better XML performance
try:
    from lxml import etree as ET  # type: ignore
    LXML_AVAILABLE = True
    logger.info("Using LXML for auto-embedding (recommended)")
except ImportError:
    import xml.etree.ElementTree as ET  # type: ignore
    LXML_AVAILABLE = False
    logger.warning("LXML not available for auto-embedding - using slower ElementTree. Install lxml: pip install lxml")


@dataclass
class EmbeddingProgress:
    """Progress information for embedding operation"""
    status: str = "idle"  # idle, preparing, embedding, completed, failed
    progress: float = 0.0
    files_done: int = 0
    files_total: int = 0
    docs_done: int = 0
    chunks_done: int = 0
    current_file: str = ""
    groups_done: List[str] = field(default_factory=list)
    error: Optional[str] = None
    elapsed_seconds: float = 0.0


@dataclass
class XMLRecord:
    """Represents an extracted XML record for embedding"""
    content: str
    tag: str
    index: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class XMLRecordExtractor:
    """Extract records from XML files for embedding with semantic chunking"""
    
    # Common record-level tags in various XML schemas
    COMMON_RECORD_TAGS = [
        "record", "item", "entry", "row", "element",
        "document", "article", "work", "resource",
        "journal_article", "book", "peer_review",
        "dissertation", "posted_content", "component",
    ]
    
    def __init__(
        self,
        max_records: int = getattr(settings, "RAG_XML_MAX_RECORDS_PER_FILE", 5000),
        max_chars_per_record: int = getattr(settings, "RAG_XML_MAX_CHARS_PER_RECORD", 1500),
        max_field_len: int = getattr(settings, "RAG_XML_FIELD_MAX_LEN", 300),
    ):
        self.max_records = max_records
        self.max_chars_per_record = max_chars_per_record
        self.max_field_len = max_field_len
    
    def detect_record_tag(self, xml_path: Path) -> Optional[str]:
        """Auto-detect the most likely record-level tag"""
        if not xml_path.exists():
            return None
        
        try:
            tag_counts: Counter = Counter()
            depth_map: Dict[str, int] = {}
            
            # Parse with iterparse for memory efficiency
            if LXML_AVAILABLE:
                context = ET.iterparse(str(xml_path), events=("start", "end"))  # type: ignore
            else:
                context = ET.iterparse(str(xml_path), events=("start", "end"))
            
            depth = 0
            for event, elem in context:
                if event == "start":
                    depth += 1
                    clean_tag = self._strip_ns(elem.tag)
                    tag_counts[clean_tag] += 1
                    if clean_tag not in depth_map:
                        depth_map[clean_tag] = depth
                elif event == "end":
                    depth -= 1
                    elem.clear()
                
                # Stop after collecting enough samples
                if sum(tag_counts.values()) > 1000:
                    break
            
            # Find the tag with highest count at depth 2-4
            candidates = [
                (tag, count) for tag, count in tag_counts.items()
                if 2 <= depth_map.get(tag, 0) <= 4 and count > 5
            ]
            
            if candidates:
                # Prefer common record tags
                for tag, _ in sorted(candidates, key=lambda x: x[1], reverse=True):
                    if tag.lower() in self.COMMON_RECORD_TAGS:
                        return tag
                # Otherwise return most frequent
                return max(candidates, key=lambda x: x[1])[0]
            
        except Exception as e:
            logger.warning(f"Failed to auto-detect record tag for {xml_path.name}: {e}")
        
        return None
    
    def _strip_ns(self, tag: str) -> str:
        """Strip namespace from tag"""
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag
    
    def _flatten_element(self, elem, max_field_len: Optional[int] = None) -> str:
        """Convert XML element to flat text representation"""
        max_len = max_field_len or self.max_field_len
        parts = []
        
        # Add tag name
        tag = self._strip_ns(elem.tag)
        parts.append(f"{tag}")
        
        # Add attributes
        if elem.attrib:
            for k, v in elem.attrib.items():
                k_clean = self._strip_ns(k)
                v_clean = str(v).strip()[:max_len]
                if v_clean:
                    parts.append(f"{k_clean}={v_clean}")
        
        # Add text content
        if elem.text and elem.text.strip():
            text = elem.text.strip()[:max_len]
            parts.append(text)
        
        # Add child elements recursively
        for child in elem:
            child_text = self._flatten_element(child, max_len)
            if child_text:
                parts.append(child_text)
            if child.tail and child.tail.strip():
                parts.append(child.tail.strip()[:max_len])
        
        return " | ".join(parts)
    
    def extract_records(
        self,
        xml_path: Path,
        record_tag: Optional[str] = None,
    ) -> List[XMLRecord]:
        """Extract records from XML file with semantic chunking"""
        if not xml_path.exists():
            return []
        
        if record_tag is None:
            record_tag = self.detect_record_tag(xml_path)
        
        if record_tag is None:
            logger.warning(f"Could not detect record tag for {xml_path.name}")
            return []
        
        records: List[XMLRecord] = []
        
        try:
            if LXML_AVAILABLE:
                context = ET.iterparse(str(xml_path), events=("end",), tag=record_tag)  # type: ignore
            else:
                context = ET.iterparse(str(xml_path), events=("end",))
            
            for idx, (event, elem) in enumerate(context):
                if idx >= self.max_records:
                    break
                
                # Skip if wrong tag (for non-LXML)
                if not LXML_AVAILABLE and self._strip_ns(elem.tag) != record_tag:
                    elem.clear()
                    continue
                
                # Flatten element to text
                content = self._flatten_element(elem)
                
                # Truncate if too long
                if len(content) > self.max_chars_per_record:
                    content = content[:self.max_chars_per_record] + "..."
                
                if content and len(content) > 50:  # Minimum content length
                    records.append(XMLRecord(
                        content=content,
                        tag=record_tag,
                        index=idx,
                        metadata={
                            "source_file": xml_path.name,
                            "record_index": idx,
                            "record_tag": record_tag,
                        }
                    ))
                
                # Clear element to free memory
                elem.clear()
            
        except Exception as e:
            logger.error(f"Failed to extract records from {xml_path.name}: {e}")
        
        return records


class AutoEmbedder:
    """
    Automatically embeds admin-configured groups after conversion.
    
    Features:
    - Fast background processing
    - Semantic chunking with optimal strategies
    - Only embeds admin-configured groups (strict)
    - Progress tracking with elapsed time
    - Uses UnifiedRAGService for embedding operations
    """

    ADMIN_PREFS_FILENAME = "admin_prefs.json"

    def __init__(
        self,
        session_id: str,
        session_dir: Path,
        rag_service: Any,  # UnifiedRAGService
        user_id: str = "",
    ):
        self.session_id = session_id
        self.session_dir = Path(session_dir)
        self.rag_service = rag_service
        self.user_id = user_id
        
        self._progress = EmbeddingProgress()
        self._lock = threading.Lock()
        self._stop_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None
        
        # Load admin configuration
        self.admin_config = self._load_admin_config()
        
        logger.info(
            f"AutoEmbedder initialized for session {session_id}. "
            f"Admin configured groups: {self.admin_config.get('auto_embedded_groups', [])}"
        )
    
    def _load_admin_config(self) -> Dict[str, Any]:
        """Load admin preferences for auto-embedding configuration"""
        prefs_path = self.session_dir / self.ADMIN_PREFS_FILENAME
        
        if not prefs_path.exists():
            logger.info(f"No admin config found at {prefs_path}, using defaults")
            return {
                "auto_embed_enabled": False,
                "auto_embedded_groups": [],
            }
        
        try:
            with open(prefs_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            # Ensure required keys exist
            if "auto_embed_enabled" not in config:
                config["auto_embed_enabled"] = False
            if "auto_embedded_groups" not in config:
                config["auto_embedded_groups"] = []
            
            return config
        except Exception as e:
            logger.error(f"Failed to load admin config: {e}")
            return {
                "auto_embed_enabled": False,
                "auto_embedded_groups": [],
            }
    
    @property
    def is_auto_embed_enabled(self) -> bool:
        """Check if auto-embedding is enabled in admin config"""
        return self.admin_config.get("auto_embed_enabled", False)
    
    @property
    def configured_groups(self) -> List[str]:
        """Get list of admin-configured groups for auto-embedding"""
        groups = self.admin_config.get("auto_embedded_groups", [])
        if isinstance(groups, list):
            return [str(g).strip().upper() for g in groups if g]
        return []
    
    def _update_progress(
        self,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        files_done: Optional[int] = None,
        files_total: Optional[int] = None,
        docs_done: Optional[int] = None,
        chunks_done: Optional[int] = None,
        current_file: Optional[str] = None,
        group_done: Optional[str] = None,
        error: Optional[str] = None,
        elapsed_seconds: Optional[float] = None,
    ):
        """Thread-safe progress update"""
        with self._lock:
            if status is not None:
                self._progress.status = status
            if progress is not None:
                self._progress.progress = min(100.0, max(0.0, progress))
            if files_done is not None:
                self._progress.files_done = files_done
            if files_total is not None:
                self._progress.files_total = files_total
            if docs_done is not None:
                self._progress.docs_done = docs_done
            if chunks_done is not None:
                self._progress.chunks_done = chunks_done
            if current_file is not None:
                self._progress.current_file = current_file
            if group_done is not None and group_done not in self._progress.groups_done:
                self._progress.groups_done.append(group_done)
            if error is not None:
                self._progress.error = error
            if elapsed_seconds is not None:
                self._progress.elapsed_seconds = elapsed_seconds
    
    def detect_eligible_groups(
        self,
        xml_inventory: List[Dict[str, Any]],
    ) -> List[str]:
        """
        Detect groups from XML inventory that are eligible for auto-embedding.
        
        Returns only groups that are BOTH:
        1. Present in the converted output
        2. Configured in admin settings for auto-embedding
        """
        if not self.is_auto_embed_enabled:
            logger.info("Auto-embedding is disabled in admin config")
            return []
        
        # Get all groups from inventory
        all_groups = set()
        for entry in xml_inventory:
            group = self._infer_group(entry)
            if group and group != "UNKNOWN":
                all_groups.add(group.upper())
        
        # Filter to only admin-configured groups
        configured = set(self.configured_groups)
        eligible = list(all_groups.intersection(configured))
        
        logger.info(
            f"Detected {len(all_groups)} groups in inventory. "
            f"Admin configured: {configured}. "
            f"Eligible for auto-embedding: {eligible}"
        )
        
        return sorted(eligible)
    
    def _infer_group(self, entry: Dict[str, Any]) -> str:
        """Infer group from XML entry"""
        # Try group field first
        if "group" in entry and entry["group"]:
            return str(entry["group"]).strip().upper()
        
        # Try logical_path
        if "logical_path" in entry:
            path = str(entry["logical_path"])
            # Extract first folder component
            parts = [p for p in path.split("/") if p and p != "."]
            if parts:
                return parts[0].upper()
        
        return "UNKNOWN"
    
    def start_auto_embed(
        self,
        xml_inventory: List[Dict[str, Any]],
        groups_to_embed: List[str],
        callback: Optional[Callable[[EmbeddingProgress], None]] = None,
    ):
        """
        Start background embedding for specified groups.
        
        Args:
            xml_inventory: List of XML file entries from conversion
            groups_to_embed: Groups to embed (must be in admin config)
            callback: Optional callback for progress updates
        """
        if self._thread and self._thread.is_alive():
            logger.warning("Auto-embedding already in progress")
            return
        
        # Filter groups to only those in admin config
        configured = set(self.configured_groups)
        filtered_groups = [g for g in groups_to_embed if g.upper() in configured]
        
        if not filtered_groups:
            logger.warning(
                f"No eligible groups to embed. Requested: {groups_to_embed}, "
                f"Configured: {list(configured)}"
            )
            self._update_progress(
                status="completed",
                progress=100.0,
                error="No eligible groups (check admin config)"
            )
            return
        
        logger.info(f"Starting auto-embedding for groups: {filtered_groups}")
        
        self._stop_flag.clear()
        self._thread = threading.Thread(
            target=self._embed_worker,
            args=(xml_inventory, filtered_groups, callback),
            daemon=True,
            name=f"AutoEmbedder-{self.session_id[:8]}"
        )
        self._thread.start()
    
    def stop(self):
        """Stop the embedding worker"""
        self._stop_flag.set()
    
    def _embed_worker(
        self,
        xml_inventory: List[Dict[str, Any]],
        groups_to_embed: List[str],
        callback: Optional[Callable[[EmbeddingProgress], None]],
    ):
        """Background worker that performs the embedding"""
        import time
        start_time = time.time()
        
        try:
            self._update_progress(status="preparing", progress=0.0)
            
            # Get conversion index (CSV files)
            csv_dir = self.session_dir / "output"
            if not csv_dir.exists():
                raise ValueError(f"Output directory not found: {csv_dir}")
            
            # Collect CSV files for each group
            group_files: Dict[str, List[Path]] = {g: [] for g in groups_to_embed}
            
            for csv_path in csv_dir.glob("*.csv"):
                # Try to match file to group
                for group in groups_to_embed:
                    if group.lower() in csv_path.stem.lower():
                        group_files[group].append(csv_path)
                        break
            
            # Calculate total files
            total_files = sum(len(files) for files in group_files.values())
            if total_files == 0:
                logger.warning("No CSV files found for embedding")
                self._update_progress(
                    status="completed",
                    progress=100.0,
                    error="No CSV files found"
                )
                return
            
            self._update_progress(
                status="embedding",
                files_total=total_files,
                progress=5.0
            )
            
            # Embed each group
            files_processed = 0
            total_docs = 0
            total_chunks = 0
            
            for group_idx, (group, files) in enumerate(group_files.items()):
                if self._stop_flag.is_set():
                    logger.info("Embedding stopped by user")
                    self._update_progress(status="stopped", error="Stopped by user")
                    return
                
                if not files:
                    continue
                
                logger.info(f"Embedding group: {group} ({len(files)} files)")
                
                # Use RAG service to embed this group
                try:
                    result = self.rag_service.embed_groups(
                        groups=[group],
                        csv_dir=csv_dir,
                        conversion_index=None,  # Will scan CSV dir
                    )
                    
                    files_processed += len(files)
                    total_docs += result.indexed_docs
                    total_chunks += result.indexed_chunks
                    
                    elapsed = time.time() - start_time
                    progress = ((group_idx + 1) / len(groups_to_embed)) * 95.0 + 5.0
                    
                    self._update_progress(
                        progress=progress,
                        files_done=files_processed,
                        docs_done=total_docs,
                        chunks_done=total_chunks,
                        group_done=group,
                        elapsed_seconds=elapsed,
                    )
                    
                    if callback:
                        with self._lock:
                            callback(self._progress)
                    
                except Exception as e:
                    logger.error(f"Failed to embed group {group}: {e}")
                    # Continue with next group
            
            elapsed = time.time() - start_time
            self._update_progress(
                status="completed",
                progress=100.0,
                files_done=files_processed,
                docs_done=total_docs,
                chunks_done=total_chunks,
                elapsed_seconds=elapsed,
            )
            
            logger.info(
                f"Auto-embedding completed: {files_processed} files, "
                f"{total_docs} documents, {total_chunks} chunks in {elapsed:.1f}s"
            )
            
            if callback:
                with self._lock:
                    callback(self._progress)
        
        except Exception as e:
            logger.error(f"Auto-embedding failed: {e}", exc_info=True)
            elapsed = time.time() - start_time
            self._update_progress(
                status="failed",
                error=str(e),
                elapsed_seconds=elapsed,
            )
            if callback:
                with self._lock:
                    callback(self._progress)
    
    @property
    def progress(self) -> EmbeddingProgress:
        """Get current progress (thread-safe)"""
        with self._lock:
            return EmbeddingProgress(
                status=self._progress.status,
                progress=self._progress.progress,
                files_done=self._progress.files_done,
                files_total=self._progress.files_total,
                docs_done=self._progress.docs_done,
                chunks_done=self._progress.chunks_done,
                current_file=self._progress.current_file,
                groups_done=list(self._progress.groups_done),
                error=self._progress.error,
                elapsed_seconds=self._progress.elapsed_seconds,
            )


def get_auto_embedder(
    session_id: str,
    session_dir: Path,
    rag_service: Any,
) -> AutoEmbedder:
    """Factory function to create auto-embedder."""
    return AutoEmbedder(
        session_id=session_id,
        session_dir=session_dir,
        rag_service=rag_service,
    )
