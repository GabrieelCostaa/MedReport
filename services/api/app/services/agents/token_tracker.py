"""
Tracking de tokens e custo estimado para chamadas OpenAI.

Duas correções que valem registro, porque a intuição erra nas duas:

1. Tokens em CACHE custam metade. Os prompts dos agentes têm prefixo grande e
   estável (system + few-shots), cenário ideal para o cache automático da
   OpenAI — e as tentativas de retry do Instructor reenviam quase o mesmo
   prefixo. Ignorar `cached_tokens` fazia o custo ser SUPERestimado.

2. O Instructor JÁ agrega o usage de todas as tentativas de retry no objeto
   final (`update_total_usage` soma antes de a validação falhar). Somar as
   tentativas por conta própria — via hooks, por exemplo — causaria DUPLA
   contagem. Não faça isso.

Preços conferidos na documentação oficial da OpenAI em 21/07/2026.
"""
import contextlib
import contextvars
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# USD por 1M tokens. `cached_input` = prompt já em cache (50% de desconto).
PRICING = {
    "gpt-4o": {"input": 2.50, "cached_input": 1.25, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "cached_input": 0.075, "output": 0.60},
}

# Câmbio aproximado USD -> BRL. É uma estimativa fixa: o custo em USD é o
# número confiável, o BRL serve para ordem de grandeza.
USD_TO_BRL = 5.80

# Modelos já reportados como ausentes da tabela — evita repetir o log a cada
# chamada (seriam 3+ por laudo).
_MODELOS_SEM_PRECO: set[str] = set()


@dataclass
class TokenUsage:
    agent: str
    model: str = "gpt-4o"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0       # subconjunto de prompt_tokens, custa metade
    reasoning_tokens: int = 0    # subconjunto de completion_tokens (modelos de raciocínio)
    cost_usd: float = 0.0
    cost_brl: float = 0.0
    preco_conhecido: bool = True  # False => custo é estimativa por fallback

    def calculate_cost(self):
        prices = PRICING.get(self.model)
        if prices is None:
            # Fallback silencioso escondia erro de custo por trás de um número
            # plausível: bastava trocar o modelo por env para o valor exibido
            # e persistido ficar errado sem nenhum sinal.
            self.preco_conhecido = False
            prices = PRICING["gpt-4o"]
            if self.model not in _MODELOS_SEM_PRECO:
                _MODELOS_SEM_PRECO.add(self.model)
                logger.warning(
                    "[CUSTO] Modelo '%s' não está na tabela PRICING — custo estimado "
                    "com o preço do gpt-4o e marcado como não confiável. "
                    "Adicione o preço em token_tracker.PRICING.",
                    self.model,
                )

        cached = max(0, min(self.cached_tokens, self.prompt_tokens))
        nao_cacheado = self.prompt_tokens - cached
        self.cost_usd = (
            (nao_cacheado / 1_000_000) * prices["input"]
            + (cached / 1_000_000) * prices.get("cached_input", prices["input"])
            + (self.completion_tokens / 1_000_000) * prices["output"]
        )
        self.cost_brl = self.cost_usd * USD_TO_BRL

    def to_dict(self) -> dict:
        d = {
            "agent": self.agent,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "cost_brl": round(self.cost_brl, 4),
        }
        if self.cached_tokens:
            d["cached_tokens"] = self.cached_tokens
        if self.reasoning_tokens:
            d["reasoning_tokens"] = self.reasoning_tokens
        if not self.preco_conhecido:
            d["preco_conhecido"] = False
        return d


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

    @property
    def total_cached_tokens(self) -> int:
        return sum(u.cached_tokens for u in self.agents)

    @property
    def custo_confiavel(self) -> bool:
        """False se algum agente usou modelo fora da tabela de preços."""
        return all(u.preco_conhecido for u in self.agents)

    def to_dict(self) -> dict:
        totals = {
            "prompt_tokens": self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.total_cost_usd, 6),
            "cost_brl": round(self.total_cost_brl, 4),
        }
        if self.total_cached_tokens:
            totals["cached_tokens"] = self.total_cached_tokens
        if not self.custo_confiavel:
            totals["custo_confiavel"] = False
        return {"agents": [u.to_dict() for u in self.agents], "totals": totals}


# ─── Coletor de chamadas auxiliares ─────────────────────────────────────────
# O tradutor CID→MeSH e o filtro de relevância em PT chamam a OpenAI de dentro
# do pubmed_service, que não conhece a sessão do pipeline — o custo deles
# simplesmente não existia na conta do laudo. Um ContextVar resolve sem estado
# global compartilhado: é por-task, então requisições concorrentes não se
# misturam.
_coletor_auxiliar: contextvars.ContextVar = contextvars.ContextVar(
    "coletor_usage_auxiliar", default=None,
)


@contextlib.contextmanager
def coletar_uso_auxiliar(pipeline_usage):
    """Enquanto ativo, chamadas auxiliares somam em `pipeline_usage`."""
    token = _coletor_auxiliar.set(pipeline_usage)
    try:
        yield
    finally:
        _coletor_auxiliar.reset(token)


def registrar_uso_auxiliar(response, agent_name: str, model: str) -> None:
    """Registra uma chamada auxiliar no coletor ativo (no-op se não houver)."""
    coletor = _coletor_auxiliar.get()
    if coletor is None:
        return
    try:
        coletor.add(extract_usage(response, agent_name, model=model))
    except Exception as e:  # contabilidade nunca derruba a funcionalidade
        logger.debug("Falha ao registrar uso auxiliar de %s: %s", agent_name, e)


def usage_from_exception(exc, agent_name: str, model: str = "gpt-4o") -> "TokenUsage | None":
    """Recupera o custo de tentativas que TERMINARAM EM FALHA.

    Quando as `max_retries` do Instructor se esgotam, ele levanta
    `InstructorRetryException` carregando `total_usage` — o consumo real de
    todas as tentativas, todas faturadas. Como o código só media a resposta de
    sucesso, esse custo desaparecia por completo da conta: justamente o caso
    caro (3 chamadas de gpt-4o com prompt grande) virava R$0,00.

    Devolve None quando a exceção não é do Instructor ou não traz usage.
    """
    total = getattr(exc, "total_usage", None)
    if total is None:
        return None
    usage = TokenUsage(agent=f"{agent_name} (falhou)", model=model)
    usage.prompt_tokens = getattr(total, "prompt_tokens", 0) or 0
    usage.completion_tokens = getattr(total, "completion_tokens", 0) or 0
    usage.total_tokens = getattr(total, "total_tokens", 0) or 0
    prompt_det = getattr(total, "prompt_tokens_details", None)
    if prompt_det is not None:
        usage.cached_tokens = getattr(prompt_det, "cached_tokens", 0) or 0
    if not usage.total_tokens and not usage.prompt_tokens:
        return None
    usage.calculate_cost()
    logger.warning(
        "[CUSTO] %s esgotou as tentativas — %d tokens (US$ %.4f) faturados sem resultado",
        agent_name, usage.total_tokens, usage.cost_usd,
    )
    return usage


def extract_usage(response, agent_name: str, model: str = "gpt-4o") -> TokenUsage:
    """Extrai o usage de uma resposta da OpenAI.

    Em respostas do Instructor, `response.usage` já vem com o total agregado de
    TODAS as tentativas de retry — não some nada por fora.
    """
    usage = TokenUsage(agent=agent_name, model=model)
    raw = getattr(response, "usage", None)
    if raw:
        usage.prompt_tokens = getattr(raw, "prompt_tokens", 0) or 0
        usage.completion_tokens = getattr(raw, "completion_tokens", 0) or 0
        usage.total_tokens = getattr(raw, "total_tokens", 0) or 0
        # Detalhamento que existe desde o SDK 1.x e era descartado inteiro.
        prompt_det = getattr(raw, "prompt_tokens_details", None)
        if prompt_det is not None:
            usage.cached_tokens = getattr(prompt_det, "cached_tokens", 0) or 0
        completion_det = getattr(raw, "completion_tokens_details", None)
        if completion_det is not None:
            usage.reasoning_tokens = getattr(completion_det, "reasoning_tokens", 0) or 0
        if not usage.prompt_tokens and not usage.completion_tokens:
            # Sinal de contrato quebrado: a Responses API usa input_tokens/
            # output_tokens, e o getattr defensivo devolveria zero em silêncio
            # — custo R$0,00 sem erro nenhum.
            logger.warning(
                "[CUSTO] Resposta de '%s' (%s) não expôs prompt/completion_tokens — "
                "o custo deste agente será contado como zero. A API mudou de contrato?",
                agent_name, model,
            )
    usage.calculate_cost()
    return usage
