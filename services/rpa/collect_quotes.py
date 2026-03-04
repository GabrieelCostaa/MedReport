"""
Robô RPA para coleta de cotações em portais de planos de saúde.

Este script é o ponto de entrada principal para execução de jobs RPA.
Suporta dois modos:
1. CLI: execução única via linha de comando
2. Worker: execução contínua processando jobs da fila

Uso:
    # Modo demo (gera dados fake)
    python collect_quotes.py --portal demo --tenant tnt_001

    # Modo real (requer credenciais)
    PORTAL_BIONEXO_USER=xxx PORTAL_BIONEXO_PASSWORD=yyy python collect_quotes.py --portal bionexo

    # Modo worker (processa fila)
    python collect_quotes.py --worker --workers 3
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime

from core.base_bot import JobConfig
from core.config import DEFAULT_CONFIG
from core.metrics import GLOBAL_METRICS
from core.orchestrator import RpaOrchestrator, run_single_job
from core.circuit_breaker import CircuitBreakerRegistry

logging.basicConfig(
    level=os.getenv("RPA_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="RPA de Cotações OPME")
    
    parser.add_argument(
        "--portal",
        default=os.getenv("PORTAL_NAME", "demo"),
        help="Nome do portal (default: demo)"
    )
    parser.add_argument(
        "--tenant",
        default=os.getenv("TENANT_ID", "default"),
        help="ID do tenant"
    )
    parser.add_argument(
        "--max-quotes",
        type=int,
        default=50,
        help="Máximo de cotações a capturar"
    )
    parser.add_argument(
        "--no-attachments",
        action="store_true",
        help="Não baixar anexos"
    )
    parser.add_argument(
        "--worker",
        action="store_true",
        help="Executar em modo worker (processa fila)"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Número de workers (modo worker)"
    )
    parser.add_argument(
        "--output",
        choices=["json", "summary"],
        default="summary",
        help="Formato de saída"
    )
    
    return parser.parse_args()


async def run_cli(args):
    """Executa coleta única via CLI."""
    job_config = JobConfig(
        tenant_id=args.tenant,
        portal=args.portal,
        max_quotations=args.max_quotes,
        download_attachments=not args.no_attachments,
    )
    
    logger.info(
        "Iniciando coleta: portal=%s, tenant=%s, max=%d",
        args.portal, args.tenant, args.max_quotes
    )
    
    try:
        quotes = await run_single_job(job_config)
        
        if args.output == "json":
            output = {
                "success": True,
                "portal": args.portal,
                "tenant": args.tenant,
                "quotes_count": len(quotes),
                "items_count": sum(len(q.items) for q in quotes),
                "quotes": [
                    {
                        "external_id": q.external_id,
                        "status": q.status,
                        "buyer_name": q.buyer_name,
                        "deadline_at": q.deadline_at,
                        "items_count": len(q.items),
                        "attachments_count": len(q.attachments),
                    }
                    for q in quotes
                ],
                "metrics": GLOBAL_METRICS.get_all_stats(),
            }
            print(json.dumps(output, indent=2, default=str))
        else:
            print(f"\n{'='*60}")
            print(f"COLETA FINALIZADA - {args.portal.upper()}")
            print(f"{'='*60}")
            print(f"Cotações encontradas: {len(quotes)}")
            print(f"Total de itens: {sum(len(q.items) for q in quotes)}")
            print(f"Anexos: {sum(len(q.attachments) for q in quotes)}")
            print()
            
            for q in quotes[:5]:
                print(f"  [{q.external_id}] {q.buyer_name or 'N/A'}")
                print(f"    Deadline: {q.deadline_at or 'N/A'}")
                print(f"    Itens: {len(q.items)}")
            
            if len(quotes) > 5:
                print(f"  ... e mais {len(quotes) - 5} cotações")
            
            print()
            
            stats = GLOBAL_METRICS.get_portal_stats(args.portal)
            print(f"Estatísticas do portal:")
            print(f"  Total de execuções: {stats['total_runs']}")
            print(f"  Sucesso: {stats['successful_runs']}")
            print(f"  Falhas: {stats['failed_runs']}")
            print(f"  Tempo médio: {stats['avg_duration_ms']:.0f}ms")
        
        return 0
        
    except Exception as e:
        logger.exception("Erro na coleta: %s", e)
        
        if args.output == "json":
            print(json.dumps({
                "success": False,
                "error": str(e),
                "portal": args.portal,
            }, indent=2))
        else:
            print(f"\nERRO: {e}")
        
        return 1


async def run_worker(args):
    """Executa em modo worker contínuo."""
    orchestrator = RpaOrchestrator()
    
    logger.info("Iniciando modo worker com %d workers", args.workers)
    
    await orchestrator.start(num_workers=args.workers)
    
    try:
        while True:
            await asyncio.sleep(60)
            
            stats = GLOBAL_METRICS.get_all_stats()
            cb_status = CircuitBreakerRegistry.get_all_status()
            
            logger.info(
                "Status: runs_ativos=%d, total=%d, circuit_breakers=%s",
                stats["active_runs"],
                stats["total_runs"],
                [s["name"] + ":" + s["state"] for s in cb_status]
            )
            
    except KeyboardInterrupt:
        logger.info("Recebido sinal de parada")
    finally:
        await orchestrator.stop()
    
    return 0


async def main():
    args = parse_args()
    
    if args.worker:
        return await run_worker(args)
    else:
        return await run_cli(args)


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
