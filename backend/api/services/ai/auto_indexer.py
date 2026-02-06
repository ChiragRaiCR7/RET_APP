"""
Auto-Indexer Service.

Automatically indexes configured groups into ChromaDB after ZIP scanning.
Works with UnifiedRAGService from advanced_ai_service.
"""

import logging
import json
import threading
from typing import Any, Callable, Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass, field
import xml.etree.ElementTree as ET
from collections import Counter

from api.core.config import settings

logger = logging.getLogger(__name__)

# Try lxml for better XML handling
try:
    from lxml import etree as LET
    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False
    logger.warning("lxml not available, using standard xml.etree")


@dataclass
class IndexingProgress:
    """Progress information for indexing operation"""
    status: str = "idle"  # idle, preparing, indexing, completed, failed
    progress: float = 0.0
    files_done: int = 0
    files_total: int = 0
    docs_done: int = 0
    current_file: str = ""
    groups_done: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class XMLRecord:
    """Represents an extracted XML record"""
    content: str
    tag: str
    index: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class XMLRecordExtractor:
    """Extract records from XML files for embedding"""
    
    # Common record-level tags in various XML schemas
    COMMON_RECORD_TAGS = [
        "record", "item", "entry", "row", "element",
        "document", "article", "work", "resource",
        "journal_article", "book", "peer_review",
        "dissertation", "posted_content", "component",
    ]
    
    def __init__(self, max_records: int = 5000, max_chars_per_record: int = 6000):
        self.max_records = max_records
        self.max_chars_per_record = max_chars_per_record
    
    def detect_record_tag(self, xml_path: Path) -> Optional[str]:
        """Auto-detect the record tag by finding repeated child elements"""
        try:
            if LXML_AVAILABLE:
                parser = LET.XMLParser(
                    resolve_entities=False,
                    no_network=True,
                    recover=True,
                    huge_tree=True,
                )
                tree = LET.parse(str(xml_path), parser)
                root = tree.getroot()
            else:
                tree = ET.parse(str(xml_path))
                root = tree.getroot()
            
            # Count immediate children tags
            child_tags = [self._strip_ns(child.tag) for child in root]
            tag_counts = Counter(child_tags)
            
            # Find tags that appear multiple times
            repeated = [tag for tag, count in tag_counts.items() if count > 1]
            
            if repeated:
                return repeated[0]
            
            # Check for known record tags
            for child in root:
                tag = self._strip_ns(child.tag)
                if tag.lower() in [t.lower() for t in self.COMMON_RECORD_TAGS]:
                    return tag
            
            return None
            
        except Exception as e:
            logger.warning(f"Error detecting record tag: {e}")
            return None
    
    def _strip_ns(self, tag: str) -> str:
        """Remove namespace from tag"""
        if "}" in tag:
            return tag.split("}")[-1]
        return tag
    
    def _flatten_element(self, elem, max_field_len: int = 300) -> str:
        """Flatten XML element to text representation"""
        tag = self._strip_ns(elem.tag)
        
        # Get attributes
        attrs = dict(elem.attrib)
        attr_str = " ".join([f'{k}="{v}"' for k, v in list(attrs.items())[:10]])
        
        # Get child field values
        fields = []
        for child in list(elem)[:50]:
            child_tag = self._strip_ns(child.tag)
            child_text = (child.text or "").strip()
            if child_text:
                if len(child_text) > max_field_len:
                    child_text = child_text[:max_field_len] + "…"
                fields.append(f"{child_tag}: {child_text}")
        
        # Get full text content
        try:
            full_text = " ".join([t.strip() for t in elem.itertext() if t.strip()])
        except:
            full_text = (elem.text or "").strip()
        
        if len(full_text) > 1200:
            full_text = full_text[:1200] + "…"
        
        # Build output
        parts = [f"<{tag}>"]
        if attr_str:
            parts.append(f"ATTRS: {attr_str}")
        if fields:
            parts.append("FIELDS: " + " | ".join(fields[:40]))
        if full_text:
            parts.append(f"CONTENT: {full_text}")
        
        return "\n".join(parts)
    
    def extract_records(
        self,
        xml_path: Path,
        record_tag: Optional[str] = None,
    ) -> List[XMLRecord]:
        """Extract records from XML file"""
        records = []
        
        # Auto-detect record tag if not provided
        if not record_tag:
            record_tag = self.detect_record_tag(xml_path)
        
        try:
            if LXML_AVAILABLE and record_tag:
                # Use iterparse for memory efficiency
                context = LET.iterparse(
                    str(xml_path),
                    events=("end",),
                    tag=record_tag,
                    recover=True,
                    huge_tree=True,
                )
                
                for event, elem in context:
                    if len(records) >= self.max_records:
                        break
                    
                    content = self._flatten_element(elem)
                    if len(content) > self.max_chars_per_record:
                        content = content[:self.max_chars_per_record] + "…"
                    
                    records.append(XMLRecord(
                        content=content,
                        tag=record_tag,
                        index=len(records),
                    ))
                    
                    # Clear element to save memory
                    elem.clear()
                    while elem.getprevious() is not None:
                        try:
                            del elem.getparent()[0]
                        except:
                            break
            else:
                # Fallback: parse entire file
                if LXML_AVAILABLE:
                    parser = LET.XMLParser(recover=True, huge_tree=True)
                    tree = LET.parse(str(xml_path), parser)
                else:
                    tree = ET.parse(str(xml_path))
                
                root = tree.getroot()
                
                # If we have a record tag, find all matching elements
                if record_tag:
                    elements = root.findall(f".//{record_tag}")
                else:
                    # Use direct children as records
                    elements = list(root)
                
                for elem in elements[:self.max_records]:
                    content = self._flatten_element(elem)
                    if len(content) > self.max_chars_per_record:
                        content = content[:self.max_chars_per_record] + "…"
                    
                    records.append(XMLRecord(
                        content=content,
                        tag=record_tag or "element",
                        index=len(records),
                    ))
                    
        except Exception as e:
            logger.error(f"Error extracting records from {xml_path}: {e}")
            
            # Fallback: read as raw text chunks
            try:
                text = xml_path.read_text(encoding="utf-8", errors="ignore")
                chunk_size = self.max_chars_per_record
                
                for i in range(0, min(len(text), self.max_records * chunk_size), chunk_size):
                    records.append(XMLRecord(
                        content=text[i:i + chunk_size],
                        tag="RAW_CHUNK",
                        index=len(records),
                    ))
            except:
                pass
        
        return records


class AutoIndexer:
    """
    Automatically indexes configured groups after ZIP scanning.

    Runs in a background thread to not block the UI.
    Uses UnifiedRAGService for indexing operations.
    """

    ADMIN_PREFS_FILENAME = "admin_prefs.json"

    def __init__(
        self,
        session_id: str,
        session_dir: Path,
        rag_service: Any,  # UnifiedRAGService instance
    ):
        self.session_id = session_id
        self.session_dir = Path(session_dir)
        self.rag_service = rag_service
        
        # State tracking
        self._progress = IndexingProgress()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_flag = False
        
        # Extractor
        self._extractor = XMLRecordExtractor()
        
        # Load admin config
        self._admin_config = self._load_admin_config()
    
    def _load_admin_config(self) -> Dict[str, Any]:
        """Load admin preferences for auto-index groups."""
        prefs_path = Path(settings.RET_RUNTIME_ROOT) / self.ADMIN_PREFS_FILENAME
        
        if prefs_path.exists():
            try:
                with open(prefs_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    return config
            except Exception as e:
                logger.warning(f"Error loading admin config: {e}")
        
        return {"auto_index_groups": []}
    
    @property
    def auto_index_groups(self) -> List[str]:
        """Get list of groups configured for auto-indexing"""
        return self._admin_config.get("auto_index_groups", [])
    
    @property
    def progress(self) -> IndexingProgress:
        """Get current indexing progress"""
        with self._lock:
            return IndexingProgress(
                status=self._progress.status,
                progress=self._progress.progress,
                files_done=self._progress.files_done,
                files_total=self._progress.files_total,
                docs_done=self._progress.docs_done,
                current_file=self._progress.current_file,
                groups_done=list(self._progress.groups_done),
                error=self._progress.error,
            )
    
    def _update_progress(
        self,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        files_done: Optional[int] = None,
        files_total: Optional[int] = None,
        docs_done: Optional[int] = None,
        current_file: Optional[str] = None,
        group_done: Optional[str] = None,
        error: Optional[str] = None,
    ):
        """Update progress state"""
        with self._lock:
            if status is not None:
                self._progress.status = status
            if progress is not None:
                self._progress.progress = progress
            if files_done is not None:
                self._progress.files_done = files_done
            if files_total is not None:
                self._progress.files_total = files_total
            if docs_done is not None:
                self._progress.docs_done = docs_done
            if current_file is not None:
                self._progress.current_file = current_file
            if group_done is not None:
                if group_done not in self._progress.groups_done:
                    self._progress.groups_done.append(group_done)
            if error is not None:
                self._progress.error = error
    
    def detect_eligible_groups(
        self,
        xml_inventory: List[Dict[str, Any]],
    ) -> List[str]:
        """
        Detect which groups from the XML inventory should be auto-indexed
        based on admin configuration.
        
        Args:
            xml_inventory: List of XML file entries with 'group' field
            
        Returns:
            List of group names that should be auto-indexed
        """
        if not self.auto_index_groups:
            return []
        
        # Get unique groups from inventory
        inventory_groups = set()
        for entry in xml_inventory:
            group = entry.get("group") or self._infer_group(entry)
            if group:
                inventory_groups.add(group)
        
        # Find intersection with configured auto-index groups
        eligible = []
        for cfg_group in self.auto_index_groups:
            cfg_lower = cfg_group.lower()
            for inv_group in inventory_groups:
                if cfg_lower == inv_group.lower() or inv_group.lower().startswith(cfg_lower):
                    eligible.append(inv_group)
        
        return list(set(eligible))
    
    def _infer_group(self, entry: Dict[str, Any]) -> str:
        """Infer group from file path"""
        logical_path = entry.get("logical_path", "")
        filename = entry.get("filename", "")
        
        # Try to extract group from path
        parts = logical_path.replace("\\", "/").split("/")
        if len(parts) > 1:
            return parts[0]
        
        # Use filename prefix
        if "_" in filename:
            return filename.split("_")[0]
        
        return "MISC"
    
    def start_auto_index(
        self,
        xml_inventory: List[Dict[str, Any]],
        groups_to_index: List[str],
        callback: Optional[Callable[[IndexingProgress], None]] = None,
    ):
        """
        Start auto-indexing in background thread.
        
        Args:
            xml_inventory: List of XML file entries
            groups_to_index: List of group names to index
            callback: Optional progress callback
        """
        if self._thread and self._thread.is_alive():
            logger.warning("Indexing already in progress")
            return
        
        self._stop_flag = False
        self._update_progress(
            status="preparing",
            progress=0.0,
            files_done=0,
            docs_done=0,
            error=None,
        )
        self._progress.groups_done = []
        
        self._thread = threading.Thread(
            target=self._index_worker,
            args=(xml_inventory, groups_to_index, callback),
            daemon=True,
        )
        self._thread.start()
    
    def stop(self):
        """Request stop of background indexing"""
        self._stop_flag = True
    
    def _index_worker(
        self,
        xml_inventory: List[Dict[str, Any]],
        groups_to_index: List[str],
        callback: Optional[Callable[[IndexingProgress], None]],
    ):
        """Background worker for indexing"""
        try:
            self._update_progress(status="indexing")
            
            # Filter inventory to only target groups
            target_groups = set(g.lower() for g in groups_to_index)
            files_to_index = []
            
            for entry in xml_inventory:
                group = (entry.get("group") or self._infer_group(entry)).lower()
                if group in target_groups:
                    files_to_index.append(entry)
            
            if not files_to_index:
                self._update_progress(
                    status="completed",
                    progress=1.0,
                    error="No files to index for selected groups",
                )
                return
            
            self._update_progress(files_total=len(files_to_index))
            
            total_docs = 0
            
            for i, entry in enumerate(files_to_index):
                if self._stop_flag:
                    self._update_progress(
                        status="stopped",
                        error="Indexing stopped by user",
                    )
                    return
                
                xml_path = Path(entry.get("xml_path", ""))
                filename = entry.get("filename", "unknown")
                group = entry.get("group") or self._infer_group(entry)
                
                self._update_progress(
                    current_file=filename,
                    files_done=i,
                    progress=i / len(files_to_index),
                )
                
                if callback:
                    callback(self.progress)
                
                if not xml_path.exists():
                    logger.warning(f"XML file not found: {xml_path}")
                    continue
                
                try:
                    # Extract records from XML
                    records = self._extractor.extract_records(xml_path)
                    
                    if records:
                        # Convert to format expected by RAG engine
                        record_dicts = [
                            {
                                "content": r.content,
                                "metadata": {
                                    "tag": r.tag,
                                    "record_index": r.index,
                                }
                            }
                            for r in records
                        ]
                        
                        # Index into RAG service
                        stats = self.rag_service.index_xml_records(
                            xml_records=record_dicts,
                            group=group,
                            filename=filename,
                        )
                        
                        total_docs += stats.get("indexed_docs", 0)
                        self._update_progress(docs_done=total_docs)
                
                except Exception as e:
                    logger.error(f"Error indexing {filename}: {e}")
                
                # Mark group as done if last file for this group
                remaining_for_group = [
                    f for f in files_to_index[i+1:]
                    if (f.get("group") or self._infer_group(f)).lower() == group.lower()
                ]
                if not remaining_for_group:
                    self._update_progress(group_done=group)
            
            self._update_progress(
                status="completed",
                progress=1.0,
                files_done=len(files_to_index),
            )
            
            if callback:
                callback(self.progress)
            
            logger.info(f"Auto-indexing completed: {total_docs} documents indexed")
            
        except Exception as e:
            logger.error(f"Auto-indexing failed: {e}")
            self._update_progress(
                status="failed",
                error=str(e),
            )
            
            if callback:
                callback(self.progress)


def get_auto_indexer(
    session_id: str,
    session_dir: Path,
    rag_service: Any,
) -> AutoIndexer:
    """Factory function to create auto-indexer."""
    return AutoIndexer(
        session_id=session_id,
        session_dir=session_dir,
        rag_service=rag_service,
    )
