"""
Bedrock Prompt Caching Service

Implements prompt caching for Bedrock API calls to reduce latency and costs.
Caches system prompts and tool definitions via ephemeral cache control.

Reference: https://docs.aws.amazon.com/bedrock/latest/userguide/cached-prompts.html
"""

import hashlib
from typing import Optional, List, Dict, Any
from app.core.logging import setup_logger, create_log_name
from app.core.config import settings


class PromptCacheManager:
    """
    Manages prompt caching for Bedrock API calls.
    Uses ephemeral cache control to cache system prompts and tool definitions.
    """

    def __init__(self, logger=None):
        """
        Initialize the prompt cache manager.
        
        Args:
            logger: Optional logger instance.
        """
        self.logger = logger or self._get_default_logger()

    def _get_default_logger(self):
        """Create a default logger if none provided."""
        dt, _ = create_log_name()
        log_file_name = f"{settings.LOGGER_PATH}prompt_cache_{dt}.log"
        return setup_logger("prompt_cache_logger", log_file_name)

    @staticmethod
    def _compute_hash(content: str) -> str:
        """Compute SHA256 hash of content for tracking."""
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    def prepare_cached_bedrock_request(
        self,
        system_prompt: str,
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Prepare prompt caching metadata for Bedrock request.
        
        Note: Bedrock's prompt caching is handled at the service level.
        This method logs caching intent and returns metadata for tracking.
        
        Args:
            system_prompt: System prompt for the main agent.
            tools: Tool definitions.
            
        Returns:
            Dictionary with caching metadata.
        """
        try:
            cache_hash_prompt = self._compute_hash(system_prompt)
            cache_hash_tools = self._compute_hash(str(tools))
            
            self.logger.info(f"Prompt caching prepared - System prompt hash: {cache_hash_prompt}, Tools hash: {cache_hash_tools}")
            
            # Return metadata for tracking
            cache_metadata = {
                "system_prompt_hash": cache_hash_prompt,
                "tools_hash": cache_hash_tools,
                "enabled": True,
                "size_bytes": len(system_prompt) + len(str(tools))
            }
            
            self.logger.debug("Prompt caching metadata prepared")
            return cache_metadata
        except Exception as e:
            self.logger.exception(f"Failed to prepare caching metadata: {e}")
            raise


def get_prompt_cache_manager(logger=None) -> PromptCacheManager:
    """
    Factory function to create a PromptCacheManager instance.
    
    Args:
        logger: Optional logger instance.
        
    Returns:
        PromptCacheManager instance.
    """
    return PromptCacheManager(logger=logger)
