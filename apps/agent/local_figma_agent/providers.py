from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod

from openai import AzureOpenAI, OpenAI

from .models import LlmProviderConfig, ProviderSmokeResult


def load_provider_config() -> LlmProviderConfig:
    raw_provider = os.getenv("LLM_PROVIDER", "openai")
    provider = "azure-openai" if raw_provider == "azure" else raw_provider
    model = os.getenv("LLM_MODEL", "gpt-4.1")

    if provider == "azure-openai":
        ready = all(
            [
                os.getenv("AZURE_OPENAI_API_KEY"),
                os.getenv("AZURE_OPENAI_ENDPOINT"),
                os.getenv("AZURE_OPENAI_DEPLOYMENT"),
                os.getenv("AZURE_OPENAI_API_VERSION"),
            ]
        )
        return LlmProviderConfig(
            provider="azure-openai",
            model=model,
            providerReady=bool(ready),
            azureEndpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            azureDeployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            azureApiVersion=os.getenv("AZURE_OPENAI_API_VERSION"),
        )

    return LlmProviderConfig(
        provider="openai",
        model=model,
        providerReady=bool(os.getenv("OPENAI_API_KEY")),
        baseUrl=os.getenv("OPENAI_BASE_URL"),
        organization=os.getenv("OPENAI_ORG_ID"),
    )


class ProviderClient(ABC):
    def __init__(self, config: LlmProviderConfig):
        self.config = config

    @abstractmethod
    def complete_text(self, prompt: str) -> str:
        raise NotImplementedError

    def complete_json(self, prompt: str) -> dict:
        content = self.complete_text(prompt)
        return json.loads(content)

    def smoke(self) -> ProviderSmokeResult:
        output = self.complete_text("Return the single word pong.")
        return ProviderSmokeResult(
            provider=self.config.provider,
            model=self.config.model,
            invoked=True,
            output=output,
        )


class OpenAIProviderClient(ProviderClient):
    def __init__(self, config: LlmProviderConfig):
        super().__init__(config)
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=config.baseUrl,
            organization=config.organization,
        )

    def complete_text(self, prompt: str) -> str:
        if hasattr(self.client, "responses"):
            response = self.client.responses.create(
                model=self.config.model,
                input=prompt,
            )
            return response.output_text

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""


class AzureOpenAIProviderClient(ProviderClient):
    def __init__(self, config: LlmProviderConfig):
        super().__init__(config)
        self.client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=config.azureApiVersion,
            azure_endpoint=config.azureEndpoint,
        )

    def complete_text(self, prompt: str) -> str:
        model = self.config.azureDeployment or self.config.model
        if hasattr(self.client, "responses"):
            response = self.client.responses.create(
                model=model,
                input=prompt,
            )
            return response.output_text

        response = self.client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""


class MockProviderClient(ProviderClient):
    def complete_text(self, prompt: str) -> str:
        return "pong" if "single word pong" in prompt.lower() else "{}"


def build_provider_client(config: LlmProviderConfig) -> ProviderClient:
    if not config.providerReady:
        return MockProviderClient(config)

    if config.provider == "azure-openai":
        return AzureOpenAIProviderClient(config)

    return OpenAIProviderClient(config)
