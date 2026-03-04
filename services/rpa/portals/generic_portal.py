"""
Bot genérico para portais com estrutura comum.
Pode ser configurado via seletores CSS/XPath.
"""
import logging
from typing import Any, Optional

try:
    from core.base_bot import BaseBot, CapturedQuote, JobConfig
    from core.config import PortalConfig
except ImportError:
    from ..core.base_bot import BaseBot, CapturedQuote, JobConfig
    from ..core.config import PortalConfig

logger = logging.getLogger(__name__)


DEFAULT_SELECTORS = {
    "login": {
        "username": 'input[name="username"], input[name="email"], input[type="email"]',
        "password": 'input[name="password"], input[type="password"]',
        "submit": 'button[type="submit"], input[type="submit"]',
    },
    "list": {
        "quote_rows": "table tbody tr, .quote-item, [data-quote]",
        "quote_id": "[data-quote-id], .quote-id, td:first-child",
        "next_page": ".pagination .next, [aria-label='Next']",
    },
    "detail": {
        "id": ".quote-number, #quote-id, h1",
        "deadline": ".deadline, [data-deadline], .prazo",
        "buyer": ".buyer-name, .comprador, .hospital",
        "items_table": "table.items tbody tr, .item-row",
        "item_code": ".product-code, td:nth-child(1)",
        "item_name": ".product-name, td:nth-child(2)",
        "item_qty": ".quantity, td:nth-child(3)",
        "attachments": "a[href*='.pdf'], a[href*='download'], .attachment-link",
    },
}


class GenericPortalBot(BaseBot):
    """
    Bot genérico configurável por seletores.
    Útil para portais com estrutura HTML padrão.
    """
    
    def __init__(self, portal_config: PortalConfig):
        super().__init__(portal_config)
        self.selectors = {**DEFAULT_SELECTORS, **portal_config.selectors}
    
    async def login(self, job: JobConfig) -> bool:
        """Login genérico via formulário."""
        login_url = self.portal_config.login_url or self.portal_config.base_url
        await self._page.goto(login_url, wait_until="networkidle", timeout=30000)
        
        if await self.detect_captcha():
            raise RuntimeError("CAPTCHA detectado no login")
        
        username, password = await self._get_credentials(job)
        
        sel = self.selectors["login"]
        await self._page.fill(sel["username"], username)
        await self._page.fill(sel["password"], password)
        await self._page.click(sel["submit"])
        
        await self._page.wait_for_load_state("networkidle", timeout=15000)
        
        if await self._is_login_page():
            raise RuntimeError("Login falhou - ainda na página de login")
        
        await self.take_screenshot("after_login")
        return True
    
    async def _get_credentials(self, job: JobConfig) -> tuple[str, str]:
        """Obtém credenciais do secrets manager ou variáveis de ambiente."""
        import os
        username = os.getenv(f"PORTAL_{self.portal_name.upper()}_USER", "")
        password = os.getenv(f"PORTAL_{self.portal_name.upper()}_PASSWORD", "")
        
        if not username or not password:
            raise RuntimeError(f"Credenciais não configuradas para {self.portal_name}")
        
        return username, password
    
    async def _is_login_page(self) -> bool:
        """Verifica se ainda está na página de login."""
        sel = self.selectors["login"]
        try:
            element = await self._page.query_selector(sel["password"])
            return element is not None
        except Exception:
            return False
    
    async def navigate_to_list(self, job: JobConfig):
        """Navega para listagem de cotações."""
        list_url = self.portal_config.list_url
        if list_url:
            await self._page.goto(list_url, wait_until="networkidle", timeout=30000)
        
        await self.take_screenshot("quote_list")
    
    async def get_quote_list(self, job: JobConfig) -> list[Any]:
        """Extrai lista de cotações da página."""
        sel = self.selectors["list"]
        quotes = []
        
        rows = await self._page.query_selector_all(sel["quote_rows"])
        
        for row in rows[:job.max_quotations]:
            try:
                id_element = await row.query_selector(sel["quote_id"])
                if id_element:
                    quote_id = await id_element.inner_text()
                    quote_id = quote_id.strip()
                    if quote_id:
                        quotes.append({
                            "id": quote_id,
                            "element": row,
                        })
            except Exception as e:
                logger.warning("Erro ao extrair ID de cotação: %s", e)
        
        logger.info("Encontradas %d cotações na listagem", len(quotes))
        return quotes
    
    async def capture_quote_detail(self, quote_ref: Any, job: JobConfig) -> Optional[CapturedQuote]:
        """Captura detalhes de uma cotação."""
        try:
            element = quote_ref.get("element")
            if element:
                await element.click()
                await self._page.wait_for_load_state("networkidle", timeout=15000)
            
            sel = self.selectors["detail"]
            
            quote_id = await self._safe_text(sel["id"]) or quote_ref.get("id", "")
            deadline = await self._safe_text(sel["deadline"])
            buyer = await self._safe_text(sel["buyer"])
            
            items = await self._extract_items(sel)
            attachments = await self._extract_attachments(sel)
            
            await self.take_screenshot(f"quote_{quote_id}")
            
            return CapturedQuote(
                external_id=quote_id,
                portal=self.portal_name,
                status="open",
                deadline_at=deadline,
                buyer_name=buyer,
                items=items,
                attachments=attachments,
                raw_html=await self._page.content(),
            )
            
        except Exception as e:
            logger.exception("Erro ao capturar cotação %s: %s", quote_ref, e)
            return None
    
    async def _safe_text(self, selector: str) -> Optional[str]:
        """Extrai texto de elemento de forma segura."""
        try:
            element = await self._page.query_selector(selector)
            if element:
                return (await element.inner_text()).strip()
        except Exception:
            pass
        return None
    
    async def _extract_items(self, sel: dict) -> list[dict]:
        """Extrai itens da cotação."""
        items = []
        try:
            rows = await self._page.query_selector_all(sel["items_table"])
            for i, row in enumerate(rows):
                code = await self._safe_element_text(row, sel["item_code"])
                name = await self._safe_element_text(row, sel["item_name"])
                qty = await self._safe_element_text(row, sel["item_qty"])
                
                if name:
                    items.append({
                        "line_no": str(i + 1),
                        "product_code_raw": code,
                        "product_name_raw": name,
                        "qty": qty,
                        "uom": "un",
                    })
        except Exception as e:
            logger.warning("Erro ao extrair itens: %s", e)
        return items
    
    async def _safe_element_text(self, parent, selector: str) -> Optional[str]:
        """Extrai texto de sub-elemento."""
        try:
            element = await parent.query_selector(selector)
            if element:
                return (await element.inner_text()).strip()
        except Exception:
            pass
        return None
    
    async def _extract_attachments(self, sel: dict) -> list[dict]:
        """Extrai links de anexos."""
        attachments = []
        try:
            links = await self._page.query_selector_all(sel["attachments"])
            for link in links:
                href = await link.get_attribute("href")
                text = await link.inner_text()
                if href:
                    attachments.append({
                        "filename": text.strip() or "attachment",
                        "url": href,
                        "downloaded": False,
                    })
        except Exception as e:
            logger.warning("Erro ao extrair anexos: %s", e)
        return attachments
