"""
Bot de demonstração para testes.
Simula um portal genérico sem acessar sites reais.
"""
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional
import random

try:
    from core.base_bot import BaseBot, CapturedQuote, JobConfig
    from core.config import PortalConfig
except ImportError:
    from ..core.base_bot import BaseBot, CapturedQuote, JobConfig
    from ..core.config import PortalConfig


class DemoPortalBot(BaseBot):
    """
    Bot de demonstração que gera dados fake.
    Útil para testar o pipeline sem depender de portais reais.
    """
    
    def __init__(self):
        config = PortalConfig(
            name="demo",
            display_name="Portal Demo",
            base_url="https://demo.example.com",
            login_url="https://demo.example.com/login",
            list_url="https://demo.example.com/cotacoes",
        )
        super().__init__(config)
    
    async def _setup_browser(self):
        """Demo não precisa de browser real."""
        pass
    
    async def _cleanup(self):
        """Demo não precisa de cleanup."""
        pass
    
    async def login(self, job: JobConfig) -> bool:
        """Simula login."""
        await asyncio.sleep(0.5)  # Simula latência
        return True
    
    async def navigate_to_list(self, job: JobConfig):
        """Simula navegação."""
        await asyncio.sleep(0.3)
    
    async def get_quote_list(self, job: JobConfig) -> list[Any]:
        """Gera lista de IDs fake."""
        count = random.randint(3, 10)
        return [f"DEMO-{uuid.uuid4().hex[:8].upper()}" for _ in range(count)]
    
    async def capture_quote_detail(self, quote_ref: Any, job: JobConfig) -> Optional[CapturedQuote]:
        """Gera cotação fake."""
        await asyncio.sleep(0.2)
        
        hospitals = ["Hospital São Paulo", "Hospital Albert Einstein", "Hospital Sírio-Libanês"]
        cities = ["São Paulo", "Rio de Janeiro", "Belo Horizonte", "Curitiba"]
        states = ["SP", "RJ", "MG", "PR"]
        
        products = [
            ("OPME-001", "Placa bloqueada 3.5mm", "un"),
            ("OPME-002", "Parafuso cortical 3.5x40mm", "un"),
            ("OPME-003", "Stent coronário farmacológico", "un"),
            ("OPME-004", "Prótese de quadril cimentada", "un"),
            ("OPME-005", "Fio guia hidrofílico 0.035", "un"),
            ("OPME-006", "Cateter balão PTCA", "un"),
        ]
        
        num_items = random.randint(1, 5)
        items = []
        for i in range(num_items):
            prod = random.choice(products)
            items.append({
                "line_no": str(i + 1),
                "product_code_raw": prod[0],
                "product_name_raw": prod[1],
                "qty": str(random.randint(1, 10)),
                "uom": prod[2],
                "brand_pref": random.choice(["N/A", "Synthes", "Medtronic", "Johnson"]),
                "specs": random.choice(["titânio", "aço inox", "cromo-cobalto", ""]),
            })
        
        city_idx = random.randint(0, len(cities) - 1)
        
        return CapturedQuote(
            external_id=quote_ref,
            portal="demo",
            status="open",
            published_at=datetime.utcnow().isoformat(),
            deadline_at=(datetime.utcnow() + timedelta(days=random.randint(1, 7))).isoformat(),
            buyer_name=random.choice(hospitals),
            buyer_type="hospital",
            delivery_city=cities[city_idx],
            delivery_state=states[city_idx],
            items=items,
            attachments=[
                {
                    "filename": "termo_referencia.pdf",
                    "mime_type": "application/pdf",
                    "url": None,  # Demo não tem URL real
                }
            ] if random.random() > 0.5 else [],
            raw_payload={"demo": True, "generated_at": datetime.utcnow().isoformat()},
        )
