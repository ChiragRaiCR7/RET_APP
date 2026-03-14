"""
LangGraph RAG Pipeline — RET v4

Graph-based RAG implementation replacing the monolithic UnifiedRAGService.chat().
Delegates to the existing retrieval/embedding primitives in advanced_ai_service.py
while orchestrating via LangGraph for streaming, checkpointing, and HITL.

Modules:
- state        — Graph state TypedDict
- nodes        — Individual graph node functions
- graph        — Graph construction and compiled graph factory
- client       — Shared async Azure OpenAI client layer
- dspy_modules — DSPy wrappers for prompt optimisation (behind FEATURE_DSPY_ENABLED)
"""
