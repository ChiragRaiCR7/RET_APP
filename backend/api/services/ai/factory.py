"""
AI Service Factory - Creates the appropriate AI service based on strategy.

This module provides a factory pattern for creating AI service instances,
allowing the application to easily switch between different implementations.
"""

import logging
from typing import Dict, Optional, Type

from api.services.ai.base import AIStrategy, BaseAIService

logger = logging.getLogger(__name__)

# Registry of available strategies (populated dynamically to avoid circular imports)
_strategy_registry: Dict[AIStrategy, Type[BaseAIService]] = {}


def register_strategy(strategy: AIStrategy, service_class: Type[BaseAIService]) -> None:
    """Register a strategy implementation"""
    _strategy_registry[strategy] = service_class
    logger.debug(f"Registered AI strategy: {strategy.value} -> {service_class.__name__}")


class AIServiceFactory:
    """
    Factory for creating AI service instances.
    
    Usage:
        service = AIServiceFactory.create(
            strategy=AIStrategy.LITE,
            session_id="my-session",
            persist_dir="/path/to/persist"
        )
    """
    
    _default_strategy: AIStrategy = AIStrategy.LITE
    
    @classmethod
    def create(
        cls,
        strategy: AIStrategy | str,
        session_id: str,
        persist_dir: Optional[str] = None,
        auto_initialize: bool = True,
    ) -> BaseAIService:
        """
        Create an AI service instance.
        
        Args:
            strategy: The AI strategy to use
            session_id: Unique session identifier
            persist_dir: Directory for persisting data
            auto_initialize: Whether to automatically initialize the service
            
        Returns:
            Configured AI service instance
            
        Raises:
            ValueError: If the strategy is not supported
        """
        # Convert string to enum if needed
        if isinstance(strategy, str):
            strategy = AIStrategy.from_string(strategy)
        
        # Ensure strategies are registered
        cls._ensure_strategies_registered()
        
        # Get the service class
        service_class = _strategy_registry.get(strategy)
        
        if service_class is None:
            available = list(_strategy_registry.keys())
            raise ValueError(
                f"Unknown AI strategy: {strategy}. "
                f"Available strategies: {[s.value for s in available]}"
            )
        
        # Create and optionally initialize the service
        service = service_class(session_id=session_id, persist_dir=persist_dir)
        
        if auto_initialize:
            try:
                service.initialize()
            except Exception as e:
                logger.warning(f"Failed to initialize {strategy.value} service: {e}")
        
        return service
    
    @classmethod
    def get_available_strategies(cls) -> list[AIStrategy]:
        """Get list of available AI strategies"""
        cls._ensure_strategies_registered()
        return list(_strategy_registry.keys())
    
    @classmethod
    def set_default_strategy(cls, strategy: AIStrategy) -> None:
        """Set the default strategy for new services"""
        cls._default_strategy = strategy
    
    @classmethod
    def create_default(
        cls,
        session_id: str,
        persist_dir: Optional[str] = None,
    ) -> BaseAIService:
        """Create a service using the default strategy"""
        return cls.create(
            strategy=cls._default_strategy,
            session_id=session_id,
            persist_dir=persist_dir,
        )
    
    @classmethod
    def _ensure_strategies_registered(cls) -> None:
        """Ensure all strategies are registered (lazy loading)"""
        if _strategy_registry:
            return
        
        # Import strategies here to avoid circular imports
        try:
            from api.services.ai.lite import LiteAIStrategy
            register_strategy(AIStrategy.LITE, LiteAIStrategy)
        except ImportError as e:
            logger.warning(f"Could not load LITE strategy: {e}")
        
        try:
            from api.services.ai.langchain_strategy import LangChainAIStrategy
            register_strategy(AIStrategy.LANGCHAIN, LangChainAIStrategy)
        except ImportError as e:
            logger.warning(f"Could not load LANGCHAIN strategy: {e}")
        
        try:
            from api.services.ai.advanced import AdvancedAIStrategy
            register_strategy(AIStrategy.ADVANCED, AdvancedAIStrategy)
        except ImportError as e:
            logger.warning(f"Could not load ADVANCED strategy: {e}")


# Convenience function for quick service creation
def get_ai_service(
    session_id: str,
    strategy: AIStrategy | str = AIStrategy.LITE,
    persist_dir: Optional[str] = None,
) -> BaseAIService:
    """
    Convenience function to get an AI service instance.
    
    Args:
        session_id: Session identifier
        strategy: AI strategy to use (default: LITE)
        persist_dir: Directory for persistence
        
    Returns:
        Configured AI service instance
    """
    return AIServiceFactory.create(
        strategy=strategy,
        session_id=session_id,
        persist_dir=persist_dir,
    )
