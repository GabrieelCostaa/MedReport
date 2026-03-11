"""
Tracking de tokens e custo estimado para chamadas OpenAI.
"""
from dataclasses import dataclass, field


# Preços GPT-4o (USD por 1M tokens) — atualizar conforme pricing OpenAI
PRICING = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}

# Câmbio aproximado USD -> BRL
USD_TO_BRL = 5.80


@dataclass
class TokenUsage:
    agent: str
    model: str = "gpt-4o"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    cost_brl: float = 0.0

    def calculate_cost(self):
        prices = PRICING.get(self.model, PRICING["gpt-4o"])
        self.cost_usd = (
            (self.prompt_tokens / 1_000_000) * prices["input"]
            + (self.completion_tokens / 1_000_000) * prices["output"]
        )
        self.cost_brl = self.cost_usd * USD_TO_BRL

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "cost_brl": round(self.cost_brl, 4),
        }


@dataclass
class PipelineUsage:
    agents: list[TokenUsage] = field(default_factory=list)

    def add(self, usage: TokenUsage):
        self.agents.append(usage)

    @property
    def total_prompt_tokens(self) -> int:
        return sum(u.prompt_tokens for u in self.agents)

    @property
    def total_completion_tokens(self) -> int:
        return sum(u.completion_tokens for u in self.agents)

    @property
    def total_tokens(self) -> int:
        return sum(u.total_tokens for u in self.agents)

    @property
    def total_cost_usd(self) -> float:
        return sum(u.cost_usd for u in self.agents)

    @property
    def total_cost_brl(self) -> float:
        return sum(u.cost_brl for u in self.agents)

    def to_dict(self) -> dict:
        return {
            "agents": [u.to_dict() for u in self.agents],
            "totals": {
                "prompt_tokens": self.total_prompt_tokens,
                "completion_tokens": self.total_completion_tokens,
                "total_tokens": self.total_tokens,
                "cost_usd": round(self.total_cost_usd, 6),
                "cost_brl": round(self.total_cost_brl, 4),
            },
        }


def extract_usage(response, agent_name: str, model: str = "gpt-4o") -> TokenUsage:
    usage = TokenUsage(agent=agent_name, model=model)
    if hasattr(response, "usage") and response.usage:
        usage.prompt_tokens = response.usage.prompt_tokens or 0
        usage.completion_tokens = response.usage.completion_tokens or 0
        usage.total_tokens = response.usage.total_tokens or 0
    usage.calculate_cost()
    return usage
