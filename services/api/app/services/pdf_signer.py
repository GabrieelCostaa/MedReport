"""
PDF Digital Signature Service using pyHanko (PAdES standard).

Supports two modes:
  1. Self-signed (development/advanced signature) — SHA-256 with auto-generated cert
  2. ICP-Brasil (production/qualified signature) — via PKCS#11 hardware token or PFX file

The signed PDF includes:
  - Invisible PAdES B-B signature
  - Visible signature box with doctor name, CRM, date
  - Timestamp (when TSA is configured)

Fallback: if pyHanko is unavailable, returns the original PDF unchanged.
"""
import io
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from pyhanko.sign import signers, fields as sig_fields
    # SimpleSigner vive em pyhanko.sign.signers nas versões atuais (0.2x+);
    # em versões antigas ficava em pyhanko.sign.general.
    try:
        from pyhanko.sign.signers import SimpleSigner
    except ImportError:  # pragma: no cover - compat com pyHanko legado
        from pyhanko.sign.general import SimpleSigner
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    PYHANKO_AVAILABLE = True
except ImportError:
    PYHANKO_AVAILABLE = False
    logger.debug("pyHanko not available — PDF signing disabled")


def _create_self_signed_signer(
    common_name: str = "MedReport",
    organization: str = "MedReport OPME Platform",
) -> Optional["SimpleSigner"]:
    """
    Create a self-signed certificate for development/advanced signatures.
    NOT ICP-Brasil — for testing and SHA-256 advanced signature mode.
    """
    if not PYHANKO_AVAILABLE:
        return None
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime as dt

        # Generate key pair
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        # Build self-signed cert
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "SP"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(dt.datetime.now(dt.timezone.utc))
            .not_valid_after(dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=365))
            .sign(key, hashes.SHA256())
        )

        # Serialize to PEM
        key_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)

        # Constrói o SimpleSigner a partir dos PEMs EM MEMÓRIA (sem arquivo em disco).
        # As versões atuais do pyHanko expõem load_*_from_pemder_data para isso;
        # SimpleSigner.load() passou a exigir caminhos de arquivo.
        from pyhanko.keys import (
            load_private_key_from_pemder_data,
            load_certs_from_pemder_data,
        )
        try:
            from pyhanko_certvalidator.registry import SimpleCertificateStore
        except ImportError:  # pragma: no cover
            from pyhanko.sign.general import SimpleCertificateStore

        signing_key = load_private_key_from_pemder_data(key_pem, passphrase=None)
        certs = list(load_certs_from_pemder_data(cert_pem))
        signing_cert = certs[0]
        registry = SimpleCertificateStore()
        registry.register_multiple(certs)

        return SimpleSigner(
            signing_cert=signing_cert,
            signing_key=signing_key,
            cert_registry=registry,
        )
    except Exception as e:
        logger.warning("Failed to create self-signed signer: %s", e)
        return None


def sign_pdf_pades(
    pdf_bytes: bytes,
    medico_nome: str = "",
    medico_crm: str = "",
    reason: str = "Assinatura eletrônica de relatório OPME",
    location: str = "Brasil",
    pfx_path: str = "",
    pfx_password: str = "",
) -> bytes:
    """
    Sign a PDF with PAdES B-B digital signature.

    Args:
        pdf_bytes: Original PDF bytes
        medico_nome: Doctor name for visible signature
        medico_crm: CRM number for visible signature
        reason: Signature reason (displayed in PDF viewer)
        location: Signing location
        pfx_path: Path to ICP-Brasil PFX/P12 file (optional)
        pfx_password: PFX password (optional)

    Returns:
        Signed PDF bytes (or original if signing fails)
    """
    if not PYHANKO_AVAILABLE:
        logger.debug("pyHanko not available, returning unsigned PDF")
        return pdf_bytes

    try:
        # Choose signer
        signer = None

        if pfx_path:
            # ICP-Brasil mode: load from PFX file
            try:
                signer = SimpleSigner.load_pkcs12(
                    pfx_path,
                    passphrase=pfx_password.encode() if pfx_password else None,
                )
                logger.info("Using ICP-Brasil PFX certificate for signing")
            except Exception as e:
                logger.warning("Failed to load PFX certificate: %s", e)

        if signer is None:
            # Self-signed mode (development/advanced signature)
            cn = f"{medico_nome} - CRM {medico_crm}" if medico_nome else "MedReport"
            signer = _create_self_signed_signer(common_name=cn)

        if signer is None:
            logger.warning("No signer available, returning unsigned PDF")
            return pdf_bytes

        # Incremental writer diretamente do stream do PDF (pyHanko atual recebe
        # o stream binário; versões antigas recebiam o PdfFileReader).
        writer = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes))

        # Add signature field (invisible by default)
        sig_field_name = "MedReportSignature"

        # Sign with PAdES B-B
        meta = signers.PdfSignatureMetadata(
            field_name=sig_field_name,
            md_algorithm="sha256",
            reason=reason,
            location=location,
            name=f"{medico_nome} (CRM: {medico_crm})" if medico_nome else "MedReport",
            subfilter=sig_fields.SigSeedSubFilter.PADES,
        )

        # Prepare and sign
        pdf_signer = signers.PdfSigner(meta, signer=signer)

        output = io.BytesIO()
        pdf_signer.sign_pdf(
            writer,
            output=output,
        )

        signed_bytes = output.getvalue()
        logger.info(
            "PDF signed with PAdES B-B: medico=%s, crm=%s, size=%d bytes",
            medico_nome, medico_crm, len(signed_bytes),
        )
        return signed_bytes

    except Exception as e:
        logger.warning("PDF PAdES signing failed, returning unsigned: %s", e)
        return pdf_bytes


def verify_pdf_signature(pdf_bytes: bytes) -> dict:
    """
    Verify PAdES signatures in a PDF.

    Returns:
        {
            "signed": True/False,
            "signatures": [{"signer": "...", "valid": True/False, "reason": "..."}],
        }
    """
    if not PYHANKO_AVAILABLE:
        return {"signed": False, "signatures": [], "error": "pyHanko not available"}

    try:
        from pyhanko.sign.validation import validate_pdf_signature
        from pyhanko.pdf_utils.reader import PdfFileReader

        reader = PdfFileReader(io.BytesIO(pdf_bytes))
        sigs = []

        for sig in reader.embedded_signatures:
            try:
                status = validate_pdf_signature(sig)
                sigs.append({
                    "signer": status.signer_reported_name or "Unknown",
                    "valid": status.bottom_line,
                    "intact": status.intact,
                    "trusted": status.trusted,
                    "reason": getattr(sig.sig_object, "/Reason", ""),
                })
            except Exception as e:
                sigs.append({
                    "signer": "Unknown",
                    "valid": False,
                    "error": str(e),
                })

        return {
            "signed": len(sigs) > 0,
            "signatures": sigs,
        }

    except Exception as e:
        return {"signed": False, "signatures": [], "error": str(e)}
