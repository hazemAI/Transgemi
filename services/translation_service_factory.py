"""Factory for creating translation service instances based on configuration."""

import logging

from core.config_manager import ConfigManager


class TranslationServiceFactory:
    """Factory to create the appropriate translation service based on config."""

    @staticmethod
    def create_service(config: ConfigManager):
        """Create a translation service instance based on configuration.

        Args:
            config: Configuration manager instance

        Returns:
            Translation service instance (Gemini, OpenRouter, Groq, SambaNova, or Cerebras)

        Raises:
            ValueError: If service name is unknown or service initialization fails
        """
        service_name = config.translation_service.lower()

        try:
            if service_name == "gemini":
                from services.gemini_service import GeminiTranslationService

                return GeminiTranslationService(config)
            elif service_name == "openrouter":
                from services.openrouter_service import OpenRouterTranslationService

                return OpenRouterTranslationService(config)
            elif service_name == "groq":
                from services.groq_service import GroqTranslationService

                return GroqTranslationService(config)
            elif service_name == "sambanova":
                from services.sambanova_service import SambaNovaTranslationService

                return SambaNovaTranslationService(config)
            elif service_name == "cerebras":
                from services.cerebras_service import CerebrasTranslationService

                return CerebrasTranslationService(config)
            else:
                raise ValueError(f"Unknown translation service: {service_name}")

        except Exception as exc:
            logging.error("Failed to create %s service: %s", service_name, exc)
            raise
