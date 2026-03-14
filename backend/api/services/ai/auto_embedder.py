
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
        """Load admin preferences for auto-embedding configuration.

        Priority:
        1. global ``data/ai_config.json`` managed by admin panel
        2. ``admin_prefs.json`` in the session directory (optional override)
        3. ``conversion_index.json`` may contain ``admin_prefs`` key (optional override)
        4. Default: disabled
        """
        def _normalize(cfg: Dict[str, Any]) -> Dict[str, Any]:
            auto_groups = cfg.get("auto_embedded_groups", [])
            excluded_groups = cfg.get("excluded_groups", [])

            if not isinstance(auto_groups, list):
                auto_groups = []
            if not isinstance(excluded_groups, list):
                excluded_groups = []

            # Prefer canonical flag when present.
            if "auto_embed_enabled" in cfg:
                enabled = bool(cfg.get("auto_embed_enabled"))
            else:
                enabled = bool(cfg.get("enable_auto_embedding"))

            return {
                "auto_embed_enabled": enabled,
                "enable_auto_embedding": enabled,  # legacy alias
                "auto_embedded_groups": sorted({str(g).strip().upper() for g in auto_groups if str(g).strip()}),
                # legacy compatibility only (not used in eligibility policy)
                "excluded_groups": sorted({str(g).strip().upper() for g in excluded_groups if str(g).strip()}),
            }

        # 1) Try global admin config first
        try:
            from api.services.admin_service import get_ai_indexing_config_data

            global_cfg = _normalize(get_ai_indexing_config_data() or {})
        except Exception as e:
            logger.warning(f"Failed to load global admin config: {e}")
            global_cfg = _normalize({})

        config = dict(global_cfg)

        # 1) Try dedicated admin prefs file
        prefs_path = self.session_dir / self.ADMIN_PREFS_FILENAME
        if prefs_path.exists():
            try:
                with open(prefs_path, "r", encoding="utf-8") as f:
                    session_cfg = _normalize(json.load(f))
                config.update(session_cfg)
            except Exception as e:
                logger.error(f"Failed to load admin config from {prefs_path}: {e}")

        # 2) Try admin_prefs section inside conversion_index.json
        index_path = self.session_dir / "conversion_index.json"
        if index_path.exists():
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    idx_data = json.load(f)
                admin_prefs = idx_data.get("admin_prefs") or {}
                if admin_prefs:
                    idx_cfg = _normalize(admin_prefs)
                    config.update(idx_cfg)
            except Exception as e:
                logger.warning(f"Failed to read admin_prefs from conversion_index.json: {e}")

        logger.info(
            "Effective admin config for session %s: enabled=%s auto=%s excluded=%s",
            self.session_id,
            config.get("auto_embed_enabled"),
            config.get("auto_embedded_groups", []),
            config.get("excluded_groups", []),
        )
        return config

    def reload_admin_config(self) -> Dict[str, Any]:
        """Reload effective admin config from configured sources."""
        self.admin_config = self._load_admin_config()
        return dict(self.admin_config)

    def set_admin_config(self, config: Dict[str, Any]) -> None:
        """Accept admin config externally (e.g., from admin router or DB).

        This allows the admin panel to push config without relying on
        file existence in the session directory.
        """
        auto_groups = config.get("auto_embedded_groups", []) if isinstance(config, dict) else []
        excluded_groups = config.get("excluded_groups", []) if isinstance(config, dict) else []
        enabled = bool(
            (config or {}).get("auto_embed_enabled")
            or (config or {}).get("enable_auto_embedding")
        )

        self.admin_config = {
            "auto_embed_enabled": enabled,
            "enable_auto_embedding": enabled,
            "auto_embedded_groups": sorted({str(g).strip().upper() for g in (auto_groups or []) if str(g).strip()}),
            # legacy compatibility only (not used in eligibility policy)
            "excluded_groups": sorted({str(g).strip().upper() for g in (excluded_groups or []) if str(g).strip()}),
        }
        logger.info(
            f"Admin config set externally: "
            f"enabled={self.admin_config.get('auto_embed_enabled')}, "
            f"groups={self.admin_config.get('auto_embedded_groups', [])}, "
            f"excluded={self.admin_config.get('excluded_groups', [])}"
        )
    
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

    @property
    def excluded_groups(self) -> List[str]:
        """Get list of admin-excluded groups for auto-embedding."""
        groups = self.admin_config.get("excluded_groups", [])
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
        
        # Eligibility policy: ONLY groups explicitly configured by admin,
        # excluding any groups in the excluded_groups list.
        configured = set(self.configured_groups)
        excluded = set(self.excluded_groups)

        eligible: List[str] = []
        for group in sorted(all_groups):
            if group in excluded:
                logger.info("Group %s is excluded from auto-embedding (in excluded_groups)", group)
                continue
            if group in configured:
                logger.info("Group %s is eligible for auto-embedding (configured by admin)", group)
                eligible.append(group)
            else:
                logger.info(
                    "Group %s is not eligible for auto-embedding (not in admin auto_embedded_groups)",
                    group,
                )

        missing_from_inventory = sorted(configured - all_groups)
        for group in missing_from_inventory:
            logger.info(
                "Group %s is configured for auto-embedding but not present in current inventory",
                group,
            )
        
        logger.info(
            f"Detected {len(all_groups)} groups in inventory. "
            f"Admin configured: {configured}. "
            f"Excluded: {excluded}. "
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
        group_callback: Optional[Callable[[str, str, str], None]] = None,
    ):
        """
        Start background embedding for specified groups.
        
        Args:
            xml_inventory: List of XML file entries from conversion
            groups_to_embed: Groups to embed (must be in admin config)
            callback: Optional callback for progress updates
            group_callback: Optional (group, status, detail) callback for per-group tracking
        """
        if self._thread and self._thread.is_alive():
            logger.warning("Auto-embedding already in progress")
            return
        
        # Filter groups to only those in admin config and not excluded
        configured = set(self.configured_groups)
        excluded = set(self.excluded_groups)
        filtered_groups = [
            g for g in groups_to_embed 
            if g.upper() in configured and g.upper() not in excluded
        ]
        
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
            args=(xml_inventory, filtered_groups, callback, group_callback),
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
        group_callback: Optional[Callable[[str, str, str], None]] = None,
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

            # Load conversion_index.json for accurate group-to-file mapping
            conversion_index: Optional[Dict[str, Any]] = None
            index_path = self.session_dir / "conversion_index.json"
            if index_path.exists():
                try:
                    with open(index_path, "r", encoding="utf-8") as f:
                        conversion_index = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load conversion_index.json: {e}")

            # Collect CSV files for each group using conversion_index
            normalized_groups = [str(g).strip().upper() for g in groups_to_embed if str(g).strip()]
            group_files: Dict[str, List[Path]] = {g: [] for g in normalized_groups}

            if conversion_index and "files" in conversion_index:
                # Use accurate mapping from conversion index
                for file_entry in conversion_index["files"]:
                    if not isinstance(file_entry, dict):
                        continue

                    file_group = str(file_entry.get("group") or "").strip().upper()
                    if file_group not in group_files:
                        continue

                    csv_name = (
                        file_entry.get("csv_file")
                        or file_entry.get("output_file")
                        or file_entry.get("filename")
                        or ""
                    )
                    if not csv_name:
                        continue

                    file_type = str(file_entry.get("file_type") or "").strip().lower()
                    if file_type and file_type != "csv" and not str(csv_name).lower().endswith(".csv"):
                        continue

                    csv_path = csv_dir / str(csv_name)
                    if csv_path.exists():
                        group_files[file_group].append(csv_path)
            else:
                # Fallback: match files by group name in filename
                for csv_path in csv_dir.iterdir():
                    if not csv_path.is_file() or csv_path.suffix.lower() != ".csv":
                        continue
                    for group in normalized_groups:
                        if group.lower() in csv_path.stem.lower():
                            group_files[group].append(csv_path)
                            break

            # Deduplicate files per group while preserving order
            for group_name, files in list(group_files.items()):
                unique_files = list(dict.fromkeys(files))
                group_files[group_name] = unique_files
            
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

                if group_callback:
                    try:
                        group_callback(group, "embedding", f"{len(files)} files")
                    except Exception:
                        pass
                
                # Use RAG service to embed this group with retry logic
                max_retries = 3
                retry_delay = 2.0  # seconds, doubles on each retry
                last_error: Optional[Exception] = None
                
                for attempt in range(max_retries):
                    try:
                        result = self.rag_service.embed_groups(
                            groups=[group],
                            csv_dir=csv_dir,
                            conversion_index=conversion_index,
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

                        if group_callback:
                            try:
                                group_callback(group, "completed", f"{result.indexed_docs} docs, {result.indexed_chunks} chunks")
                            except Exception:
                                pass
                        
                        last_error = None
                        break  # Success, exit retry loop
                        
                    except Exception as e:
                        last_error = e
                        if attempt < max_retries - 1:
                            wait_time = retry_delay * (2 ** attempt)
                            logger.warning(
                                f"Embedding group {group} failed (attempt {attempt + 1}/{max_retries}). "
                                f"Retrying in {wait_time:.1f}s: {e}"
                            )
                            time.sleep(wait_time)
                        else:
                            logger.error(
                                f"Failed to embed group {group} after {max_retries} attempts: {e}"
                            )
                
                if last_error:
                    # Log final failure but continue with next group
                    logger.error(f"Skipping group {group} due to embedding failure: {last_error}")
                    if group_callback:
                        try:
                            group_callback(group, "failed", str(last_error))
                        except Exception:
                            pass
            
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

            # Emit structured perf metric
            try:
                import logging as _logging
                _perf_logger = _logging.getLogger("ret.metrics")
                _perf_logger.info(
                    "perf_metric: auto_embed_worker %.1fms",
                    elapsed * 1000,
                    extra={"extra_fields": {
                        "op": "auto_embed_worker",
                        "elapsed_ms": round(elapsed * 1000, 2),
                        "items": files_processed,
                        "groups": len(groups_to_embed),
                        "docs": total_docs,
                        "chunks": total_chunks,
                    }},
                )
            except Exception:
                pass
            
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