#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
!-RUN-LIST_USER_CERTIFICATES.py

Script para listar, inspecionar e exibir todos os certificados digitais do usuário
instalados no repositório de certificados do Windows (CurrentUser\\MY / Pessoal).

Recursos:
- Exibe titular, CPF, CNPJ, emissor (AC), validade, status, número de série, thumbprints.
- Reconhece dados e padrões ICP-Brasil (e-CPF, e-CNPJ, A1/A3, data de nascimento, RG, e-mail).
- Resumo visual de status (Válido, Expirando em breve, Expirado).
- Suporte a filtros de busca e opções de exportação de relatório (.txt ou .json).
- Execução direta com menu interativo e suporte a argumentos via linha de comando.
"""

import argparse
import getpass
import json
import os
import re
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path

# Tentativa de import da biblioteca cryptography
try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed25519, rsa
except ImportError:
    print("\n[!] A biblioteca 'cryptography' é necessária para a leitura detalhada dos certificados.")
    print("    Instale-a com o comando: pip install cryptography\n")
    input("Pressione Enter para sair...")
    sys.exit(1)

# Ativa suporte a caracteres UTF-8 e cores ANSI no Windows
if sys.platform == "win32":
    try:
        os.system("")  # Ativa VT100 / ANSI escape sequences no terminal do Windows
    except Exception:
        pass
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

# Cores ANSI para terminal
class Cor:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"

    # Cores de primeiro plano
    VERDE = "\033[92m"
    AMARELO = "\033[93m"
    VERMELHO = "\033[91m"
    CIANO = "\033[96m"
    AZUL = "\033[94m"
    MAGENTA = "\033[95m"
    BRANCO = "\033[97m"
    CINZA = "\033[90m"


def format_cpf(cpf: str) -> str:
    """Formata string de 11 dígitos para o padrão de CPF: 000.000.000-00."""
    cpf = re.sub(r"\D", "", cpf or "")
    if len(cpf) == 11:
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    return cpf


def format_cnpj(cnpj: str) -> str:
    """Formata string de 14 dígitos para o padrão de CNPJ: 00.000.000/0000-00."""
    cnpj = re.sub(r"\D", "", cnpj or "")
    if len(cnpj) == 14:
        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    return cnpj


def parse_icp_brasil_pf(val_bytes: bytes) -> dict:
    """
    Decodifica o OID 2.16.76.1.3.1 (Pessoa Física / e-CPF) conforme norma DOC-ICP-04.
    Estrutura:
    - 8 bytes: Data de Nascimento (DDMMAAAA)
    - 11 bytes: CPF
    - 11 bytes: NIS / PIS / PASEP
    - 15 bytes: RG
    - Restante: Órgão expedidor e UF
    """
    data = val_bytes
    # Remove cabeçalho ASN.1 OCTET STRING caso presente (tag 0x04)
    if len(data) > 2 and data[0] == 0x04:
        length = data[1]
        data = data[2 : 2 + length]

    text = data.decode("latin-1", errors="ignore")
    birth = text[0:8] if len(text) >= 8 else ""
    cpf = text[8:19] if len(text) >= 19 else ""
    nis = text[19:30] if len(text) >= 30 else ""
    rg = text[30:45].strip() if len(text) >= 45 else ""
    emissor_rg = text[45:].strip() if len(text) > 45 else ""

    nascimento_fmt = f"{birth[0:2]}/{birth[2:4]}/{birth[4:8]}" if len(birth) == 8 and birth.isdigit() else birth

    return {
        "nascimento": nascimento_fmt,
        "cpf": format_cpf(cpf),
        "cpf_raw": cpf,
        "nis": nis if nis and set(nis) != {"0"} else "",
        "rg": rg if rg and set(rg) != {"0"} else "",
        "emissor_rg": emissor_rg,
    }


def parse_icp_brasil_pj(val_bytes: bytes) -> dict:
    """Decodifica o OID 2.16.76.1.3.3 (Pessoa Jurídica / e-CNPJ) - CNPJ com 14 dígitos."""
    data = val_bytes
    if len(data) > 2 and data[0] == 0x04:
        length = data[1]
        data = data[2 : 2 + length]
    text = data.decode("latin-1", errors="ignore").strip()
    cnpj = re.sub(r"\D", "", text)
    return {
        "cnpj": format_cnpj(cnpj),
        "cnpj_raw": cnpj,
    }


def extract_cert_info(cert: x509.Certificate, index: int) -> dict:
    """Extrai todas as propriedades relevantes do certificado x509."""
    # Common Name (CN) e outros atributos do Subject
    subject_cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
    cn_value = subject_cn[0].value if subject_cn else "Sem Nome (CN ausente)"

    subject_ous = [attr.value for attr in cert.subject.get_attributes_for_oid(x509.oid.NameOID.ORGANIZATIONAL_UNIT_NAME)]
    subject_orgs = [attr.value for attr in cert.subject.get_attributes_for_oid(x509.oid.NameOID.ORGANIZATION_NAME)]

    # Emissor (Issuer)
    issuer_cn = cert.issuer.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
    issuer_cn_value = issuer_cn[0].value if issuer_cn else "Sem Emissor (CN ausente)"
    issuer_orgs = [attr.value for attr in cert.issuer.get_attributes_for_oid(x509.oid.NameOID.ORGANIZATION_NAME)]
    issuer_org_value = issuer_orgs[0] if issuer_orgs else ""

    # Datas de Validade (UTC)
    now_utc = datetime.now(timezone.utc)
    valid_from_utc = cert.not_valid_before_utc
    valid_to_utc = cert.not_valid_after_utc

    # Conversão para fuso horário local
    valid_from_local = valid_from_utc.astimezone()
    valid_to_local = valid_to_utc.astimezone()

    # Cálculo do status e dias restantes
    if now_utc < valid_from_utc:
        status = "AINDA NÃO VÁLIDO"
        status_code = "FUTURE"
        days_diff = (valid_from_utc - now_utc).days
        status_msg = f"Iniciará em {days_diff} dia(s)"
    elif now_utc > valid_to_utc:
        status = "EXPIRADO"
        status_code = "EXPIRED"
        days_diff = (now_utc - valid_to_utc).days
        status_msg = f"Expirou há {days_diff} dia(s)"
    else:
        status = "VÁLIDO"
        days_diff = (valid_to_utc - now_utc).days
        if days_diff <= 30:
            status_code = "EXPIRING"
            status_msg = f"Expira em {days_diff} dia(s) (URGENTE)"
        else:
            status_code = "VALID"
            status_msg = f"Expira em {days_diff} dia(s)"

    # Impressões digitais (Thumbprints)
    thumbprint_sha1 = cert.fingerprint(hashes.SHA1()).hex().upper()
    thumbprint_sha256 = cert.fingerprint(hashes.SHA256()).hex().upper()

    # Número de Série
    serial_number = cert.serial_number
    serial_hex = f"{serial_number:X}"

    # Chave Pública
    pub_key = cert.public_key()
    if isinstance(pub_key, rsa.RSAPublicKey):
        key_info = f"RSA {pub_key.key_size} bits"
    elif isinstance(pub_key, ec.EllipticCurvePublicKey):
        key_info = f"ECC {pub_key.curve.name} ({pub_key.key_size} bits)"
    elif isinstance(pub_key, dsa.DSAPublicKey):
        key_info = f"DSA {pub_key.key_size} bits"
    elif isinstance(pub_key, ed25519.Ed25519PublicKey):
        key_info = "Ed25519"
    else:
        key_info = pub_key.__class__.__name__

    # Informações avançadas (SAN, OIDs ICP-Brasil, e-mail)
    emails = []
    cpf_info = None
    cnpj_info = None
    dns_names = []
    icp_pf_data = {}
    icp_pj_data = {}

    try:
        san_ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        san_val = san_ext.value
        for item in san_val:
            if isinstance(item, x509.RFC822Name):
                emails.append(item.value)
            elif isinstance(item, x509.DNSName):
                dns_names.append(item.value)
            elif isinstance(item, x509.OtherName):
                oid_str = item.type_id.dotted_string
                if oid_str == "2.16.76.1.3.1":  # ICP-Brasil PF
                    icp_pf_data = parse_icp_brasil_pf(item.value)
                    if icp_pf_data.get("cpf"):
                        cpf_info = icp_pf_data["cpf"]
                elif oid_str == "2.16.76.1.3.3":  # ICP-Brasil PJ
                    icp_pj_data = parse_icp_brasil_pj(item.value)
                    if icp_pj_data.get("cnpj"):
                        cnpj_info = icp_pj_data["cnpj"]
    except x509.ExtensionNotFound:
        pass
    except Exception:
        pass

    # Se CPF não foi achado no OID SAN, tenta extrair do final do CN (padrão comum: "NOME:00000000000")
    if not cpf_info and not cnpj_info:
        cn_doc_match = re.search(r":(\d{11})$", cn_value)
        if cn_doc_match:
            cpf_info = format_cpf(cn_doc_match.group(1))
        else:
            cnpj_match = re.search(r":(\d{14})$", cn_value)
            if cnpj_match:
                cnpj_info = format_cnpj(cnpj_match.group(1))

    # Key Usages
    key_usages = []
    try:
        ku_ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.KEY_USAGE)
        ku = ku_ext.value
        if ku.digital_signature:
            key_usages.append("Assinatura Digital")
        if ku.content_commitment:
            key_usages.append("Não Repúdio")
        if ku.key_encipherment:
            key_usages.append("Cifragem de Chaves")
        if ku.data_encipherment:
            key_usages.append("Cifragem de Dados")
        if ku.key_agreement:
            key_usages.append("Acordo de Chaves")
        if ku.key_cert_sign:
            key_usages.append("Assinatura de Certificados")
        if ku.crl_sign:
            key_usages.append("Assinatura de LCR (CRL)")
    except x509.ExtensionNotFound:
        pass
    except Exception:
        pass

    # Extended Key Usages
    extended_usages = []
    try:
        eku_ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.EXTENDED_KEY_USAGE)
        for eku in eku_ext.value:
            oid_name = eku.dotted_string
            if oid_name == "1.3.6.1.5.5.7.3.1":
                extended_usages.append("Autenticação de Servidor (SSL/TLS)")
            elif oid_name == "1.3.6.1.5.5.7.3.2":
                extended_usages.append("Autenticação de Cliente (e-CPF/e-CNPJ/Login)")
            elif oid_name == "1.3.6.1.5.5.7.3.3":
                extended_usages.append("Assinatura de Código")
            elif oid_name == "1.3.6.1.5.5.7.3.4":
                extended_usages.append("Proteção de E-mail (S/MIME)")
            elif oid_name == "1.3.6.1.5.5.7.3.8":
                extended_usages.append("Carimbo do Tempo")
            elif oid_name == "1.3.6.1.5.5.7.3.9":
                extended_usages.append("Assinatura OCSP")
            else:
                extended_usages.append(oid_name)
    except x509.ExtensionNotFound:
        pass
    except Exception:
        pass

    # Classificação / Tipo do certificado
    is_icp_brasil = "ICP-Brasil" in str(cert.subject) or "ICP-Brasil" in str(cert.issuer) or bool(icp_pf_data or icp_pj_data)
    tipo_desc = "Certificado Digital"
    if is_icp_brasil:
        tipo_sub = "ICP-Brasil"
        for ou in subject_ous:
            if "e-CPF" in ou or "e-CNPJ" in ou:
                tipo_sub = f"ICP-Brasil ({ou})"
                break
        if "ICP-Brasil" == tipo_sub:
            if cpf_info:
                tipo_sub = "ICP-Brasil e-CPF"
            elif cnpj_info:
                tipo_sub = "ICP-Brasil e-CNPJ"
        tipo_desc = tipo_sub
    elif cn_value == "localhost" or "localhost" in dns_names:
        tipo_desc = "Certificado de Desenvolvimento (Localhost)"
    elif cert.subject == cert.issuer:
        tipo_desc = "Certificado Autoassinado (Self-Signed)"

    return {
        "index": index,
        "cn": cn_value,
        "tipo": tipo_desc,
        "cpf": cpf_info,
        "cnpj": cnpj_info,
        "emails": emails,
        "icp_pf_data": icp_pf_data,
        "icp_pj_data": icp_pj_data,
        "emissor_cn": issuer_cn_value,
        "emissor_org": issuer_org_value,
        "emissor_completo": cert.issuer.rfc4514_string(),
        "titular_completo": cert.subject.rfc4514_string(),
        "status": status,
        "status_code": status_code,
        "status_msg": status_msg,
        "dias_restantes": days_diff,
        "valid_from": valid_from_local.strftime("%d/%m/%Y %H:%M:%S"),
        "valid_to": valid_to_local.strftime("%d/%m/%Y %H:%M:%S"),
        "valid_from_iso": valid_from_utc.isoformat(),
        "valid_to_iso": valid_to_utc.isoformat(),
        "serial_number_hex": serial_hex,
        "serial_number_dec": str(serial_number),
        "thumbprint_sha1": thumbprint_sha1,
        "thumbprint_sha256": thumbprint_sha256,
        "chave_publica": key_info,
        "key_usages": key_usages,
        "extended_usages": extended_usages,
    }


def load_certificates(store_name: str = "MY") -> list[dict]:
    """Carrega os certificados digitais do repositório especificado via ssl.enum_certificates."""
    try:
        raw_certs = ssl.enum_certificates(store_name)
    except Exception as e:
        print(f"{Cor.VERMELHO}[-] Erro ao acessar o repositório de certificados '{store_name}': {e}{Cor.RESET}")
        return []

    cert_list = []
    for idx, (cert_bytes, encoding_type, trust) in enumerate(raw_certs, 1):
        try:
            cert = x509.load_der_x509_certificate(cert_bytes)
            info = extract_cert_info(cert, idx)
            cert_list.append(info)
        except Exception as e:
            cert_list.append({
                "index": idx,
                "cn": f"Erro ao decodificar certificado #{idx}: {e}",
                "status": "ERRO",
                "status_code": "ERROR",
                "status_msg": str(e),
                "tipo": "Desconhecido",
            })

    return cert_list


def print_banner(store_name: str, total_count: int, valid_count: int, expiring_count: int, expired_count: int, use_color: bool = True):
    """Imprime cabeçalho estilizado com estatísticas."""
    c_bold = Cor.BOLD if use_color else ""
    c_reset = Cor.RESET if use_color else ""
    c_cian = Cor.CIANO if use_color else ""
    c_verd = Cor.VERDE if use_color else ""
    c_amar = Cor.AMARELO if use_color else ""
    c_verm = Cor.VERMELHO if use_color else ""
    c_dim = Cor.DIM if use_color else ""

    current_user = getpass.getuser()
    current_time = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")

    print("\n" + "=" * 80)
    print(f"{c_bold}{c_cian}  PAINEL DE CERTIFICADOS DIGITAIS DO USUÁRIO (WINDOWS) {c_reset}")
    print("=" * 80)
    print(f" {c_dim}Usuário do Sistema:{c_reset} {c_bold}{current_user}{c_reset}  |  "
          f"{c_dim}Repositório:{c_reset} {c_bold}CurrentUser\\{store_name}{c_reset}  |  "
          f"{c_dim}Data:{c_reset} {current_time}")
    print("-" * 80)
    print(f" {c_bold}Resumo Geral:{c_reset}  "
          f"Total: {c_bold}{total_count}{c_reset}   |   "
          f"{c_verd}● Válidos: {valid_count}{c_reset}   |   "
          f"{c_amar}▲ Expirando em breve (<= 30d): {expiring_count}{c_reset}   |   "
          f"{c_verm}■ Expirados: {expired_count}{c_reset}")
    print("=" * 80 + "\n")


def print_certificate_card(cert: dict, use_color: bool = True, detailed: bool = False):
    """Exibe as informações do certificado em formato de cartão visual estruturado."""
    c_bold = Cor.BOLD if use_color else ""
    c_reset = Cor.RESET if use_color else ""
    c_dim = Cor.DIM if use_color else ""
    c_cian = Cor.CIANO if use_color else ""

    # Determina a cor do status
    if cert["status_code"] == "VALID":
        badge_cor = Cor.VERDE if use_color else ""
        badge_icon = "●"
    elif cert["status_code"] == "EXPIRING":
        badge_cor = Cor.AMARELO if use_color else ""
        badge_icon = "▲"
    else:
        badge_cor = Cor.VERMELHO if use_color else ""
        badge_icon = "■"

    badge = f"{badge_cor}{c_bold}{badge_icon} [{cert['status']} - {cert['status_msg']}]{c_reset}"

    idx_str = f"[{cert['index']:02d}]"
    print(f"{c_bold}{c_cian}┌── {idx_str} {cert['cn']}{c_reset}")
    print(f"│  {c_dim}Status:{c_reset}          {badge}")
    print(f"│  {c_dim}Tipo:{c_reset}            {cert.get('tipo', 'N/A')}")

    if cert.get("cpf"):
        print(f"│  {c_dim}CPF:{c_reset}             {c_bold}{cert['cpf']}{c_reset}")
    if cert.get("cnpj"):
        print(f"│  {c_dim}CNPJ:{c_reset}            {c_bold}{cert['cnpj']}{c_reset}")

    # Dados adicionais PF do ICP-Brasil se disponíveis
    icp_pf = cert.get("icp_pf_data", {})
    if icp_pf.get("nascimento"):
        print(f"│  {c_dim}Nascimento:{c_reset}      {icp_pf['nascimento']}")
    if icp_pf.get("rg"):
        rg_txt = icp_pf["rg"]
        if icp_pf.get("emissor_rg"):
            rg_txt += f" ({icp_pf['emissor_rg']})"
        print(f"│  {c_dim}RG:{c_reset}              {rg_txt}")

    if cert.get("emails"):
        print(f"│  {c_dim}E-mail:{c_reset}          {', '.join(cert['emails'])}")

    print(f"│  {c_dim}Emissor (AC):{c_reset}    {cert.get('emissor_cn', 'N/A')}")
    print(f"│  {c_dim}Validade:{c_reset}        De {cert.get('valid_from', 'N/A')} até {cert.get('valid_to', 'N/A')}")
    print(f"│  {c_dim}Chave Pública:{c_reset}   {cert.get('chave_publica', 'N/A')}")
    print(f"│  {c_dim}Serial (HEX):{c_reset}    {cert.get('serial_number_hex', 'N/A')}")
    print(f"│  {c_dim}SHA-1:{c_reset}           {cert.get('thumbprint_sha1', 'N/A')}")

    if detailed:
        print(f"│  {c_dim}SHA-256:{c_reset}         {cert.get('thumbprint_sha256', 'N/A')}")
        if cert.get("key_usages"):
            print(f"│  {c_dim}Usos da Chave:{c_reset}   {', '.join(cert['key_usages'])}")
        if cert.get("extended_usages"):
            print(f"│  {c_dim}Usos Avançados:{c_reset}  {', '.join(cert['extended_usages'])}")
        print(f"│  {c_dim}Titular Completo:{c_reset} {cert.get('titular_completo', 'N/A')}")
        print(f"│  {c_dim}Emissor Completo:{c_reset} {cert.get('emissor_completo', 'N/A')}")

    print(f"{c_cian}└" + "─" * 78 + f"{c_reset}\n")


def export_to_text(certs: list[dict], filepath: Path) -> Path:
    """Gera um relatório completo em formato texto com codificação UTF-8."""
    lines = [
        "=" * 80,
        "RELATÓRIO DE CERTIFICADOS DIGITAIS DO USUÁRIO",
        "=" * 80,
        f"Data/Hora de Geração: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}",
        f"Usuário: {getpass.getuser()}",
        f"Total de Certificados: {len(certs)}",
        "=" * 80,
        "",
    ]

    for cert in certs:
        lines.append(f"[{cert['index']:02d}] {cert['cn']}")
        lines.append(f"    Status:            {cert['status']} ({cert['status_msg']})")
        lines.append(f"    Tipo:              {cert.get('tipo', 'N/A')}")
        if cert.get("cpf"):
            lines.append(f"    CPF:               {cert['cpf']}")
        if cert.get("cnpj"):
            lines.append(f"    CNPJ:              {cert['cnpj']}")
        icp_pf = cert.get("icp_pf_data", {})
        if icp_pf.get("nascimento"):
            lines.append(f"    Data Nascimento:   {icp_pf['nascimento']}")
        if icp_pf.get("rg"):
            lines.append(f"    RG:                {icp_pf['rg']} {icp_pf.get('emissor_rg', '')}".strip())
        if cert.get("emails"):
            lines.append(f"    E-mail(s):         {', '.join(cert['emails'])}")
        lines.append(f"    Emissor:           {cert.get('emissor_cn', 'N/A')}")
        lines.append(f"    Validade:          De {cert.get('valid_from', 'N/A')} até {cert.get('valid_to', 'N/A')}")
        lines.append(f"    Chave Pública:     {cert.get('chave_publica', 'N/A')}")
        lines.append(f"    Serial (Hex):      {cert.get('serial_number_hex', 'N/A')}")
        lines.append(f"    Serial (Dec):      {cert.get('serial_number_dec', 'N/A')}")
        lines.append(f"    Thumbprint SHA-1:  {cert.get('thumbprint_sha1', 'N/A')}")
        lines.append(f"    Thumbprint SHA256: {cert.get('thumbprint_sha256', 'N/A')}")
        if cert.get("key_usages"):
            lines.append(f"    Usos da Chave:     {', '.join(cert['key_usages'])}")
        if cert.get("extended_usages"):
            lines.append(f"    Finalidades EKU:   {', '.join(cert['extended_usages'])}")
        lines.append(f"    DN do Titular:     {cert.get('titular_completo', 'N/A')}")
        lines.append(f"    DN do Emissor:     {cert.get('emissor_completo', 'N/A')}")
        lines.append("-" * 80)
        lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")
    return filepath


def export_to_json(certs: list[dict], filepath: Path) -> Path:
    """Exporta lista estruturada de certificados em JSON."""
    filepath.write_text(json.dumps(certs, ensure_ascii=False, indent=2), encoding="utf-8")
    return filepath


def interactive_menu(certs: list[dict], store_name: str, use_color: bool = True):
    """Menu interativo quando executado no console sem argumentos."""
    c_bold = Cor.BOLD if use_color else ""
    c_reset = Cor.RESET if use_color else ""
    c_cian = Cor.CIANO if use_color else ""
    c_verd = Cor.VERDE if use_color else ""

    while True:
        print(f"{c_bold}Opções disponíveis:{c_reset}")
        print(f"  {c_cian}[número]{c_reset} - Ver detalhes aprofundados do certificado (ex: 1, 2, ...)")
        print(f"  {c_cian}[T]{c_reset}      - Exportar relatório em formato TXT (relatorio_certificados.txt)")
        print(f"  {c_cian}[J]{c_reset}      - Exportar relatório em formato JSON (relatorio_certificados.json)")
        print(f"  {c_cian}[L]{c_reset}      - Listar novamente todos os certificados")
        print(f"  {c_cian}[S]{c_reset}      - Sair do programa")

        escolha = input(f"\n{c_bold}Escolha uma opção (ou Enter para sair): {c_reset}").strip()

        if not escolha or escolha.lower() in ["s", "sair", "exit", "q"]:
            print("\nEncerrando visualizador de certificados.")
            break

        if escolha.isdigit():
            idx = int(escolha)
            matching = [c for c in certs if c["index"] == idx]
            if matching:
                print(f"\n{c_bold}{c_verd}=== DETALHES COMPLETOS DO CERTIFICADO #{idx} ==={c_reset}")
                print_certificate_card(matching[0], use_color=use_color, detailed=True)
            else:
                print(f"\n[!] Certificado com índice {idx} não encontrado. Intervalo válido: 1 a {len(certs)}.\n")
        elif escolha.lower() == "t":
            out_file = Path.cwd() / "!-RELATORIO_CERTIFICADOS.txt"
            export_to_text(certs, out_file)
            print(f"\n{c_verd}[+] Relatório exportado com sucesso para:{c_reset} {out_file}\n")
        elif escolha.lower() == "j":
            out_file = Path.cwd() / "!-RELATORIO_CERTIFICADOS.json"
            export_to_json(certs, out_file)
            print(f"\n{c_verd}[+] Relatório JSON exportado com sucesso para:{c_reset} {out_file}\n")
        elif escolha.lower() == "l":
            for c in certs:
                print_certificate_card(c, use_color=use_color, detailed=False)
        else:
            print(f"\n[!] Opção '{escolha}' inválida. Tente novamente.\n")


def parse_arguments():
    """Configura argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description="Exibe e inspeciona todos os certificados digitais do usuário instalados no Windows."
    )
    parser.add_argument(
        "--store",
        "-s",
        default="MY",
        help="Nome do repositório de certificados do Windows (Padrão: 'MY' / Pessoal). Outros: Root, CA, Trust.",
    )
    parser.add_argument(
        "--filter",
        "-f",
        default=None,
        help="Filtra certificados por termo de busca no Nome (CN), CPF, CNPJ, Emissor ou Serial.",
    )
    parser.add_argument(
        "--valid-only",
        action="store_true",
        help="Exibe apenas certificados válidos (dentro do prazo de validade).",
    )
    parser.add_argument(
        "--expired-only",
        action="store_true",
        help="Exibe apenas certificados expirados.",
    )
    parser.add_argument(
        "--detailed",
        "-d",
        action="store_true",
        help="Exibe detalhes completos (SHA256, Distinguished Names, Usos de Chave) na listagem inicial.",
    )
    parser.add_argument(
        "--export",
        "-e",
        nargs="?",
        const="!-RELATORIO_CERTIFICADOS.txt",
        default=None,
        help="Exporta o relatório para o arquivo especificado (padrão: !-RELATORIO_CERTIFICADOS.txt).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Gera a saída em formato JSON estruturado na tela.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Desativa as cores ANSI na saída do terminal.",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="Não abre o menu interativo após listar os certificados.",
    )
    return parser.parse_args()


def main():
    args = parse_arguments()
    use_color = not args.no_color

    # Carrega certificados
    certs = load_certificates(args.store)
    if not certs:
        print(f"\nNenhum certificado encontrado no repositório '{args.store}'.\n")
        if not args.no_interactive and len(sys.argv) == 1:
            input("Pressione Enter para sair...")
        return 0

    # Aplica filtros se especificados
    filtered_certs = certs
    if args.valid_only:
        filtered_certs = [c for c in filtered_certs if c.get("status_code") in ("VALID", "EXPIRING")]
    elif args.expired_only:
        filtered_certs = [c for c in filtered_certs if c.get("status_code") == "EXPIRED"]

    if args.filter:
        termo = args.filter.lower()
        filtered_certs = [
            c
            for c in filtered_certs
            if termo in (c.get("cn") or "").lower()
            or termo in (c.get("cpf") or "").lower()
            or termo in (c.get("cnpj") or "").lower()
            or termo in (c.get("emissor_cn") or "").lower()
            or termo in (c.get("serial_number_hex") or "").lower()
            or termo in (c.get("thumbprint_sha1") or "").lower()
            or any(termo in (email or "").lower() for email in c.get("emails", []))
        ]

    # Saída puramente JSON se solicitado
    if args.json:
        print(json.dumps(filtered_certs, ensure_ascii=False, indent=2))
        return 0

    # Estatísticas
    total = len(certs)
    valid_count = sum(1 for c in certs if c.get("status_code") == "VALID")
    expiring_count = sum(1 for c in certs if c.get("status_code") == "EXPIRING")
    expired_count = sum(1 for c in certs if c.get("status_code") == "EXPIRED")

    print_banner(
        args.store,
        total_count=total,
        valid_count=valid_count,
        expiring_count=expiring_count,
        expired_count=expired_count,
        use_color=use_color,
    )

    if args.filter or args.valid_only or args.expired_only:
        print(f"Filtro aplicado: exibindo {len(filtered_certs)} de {total} certificado(s).\n")

    # Exibe os cartões
    for c in filtered_certs:
        print_certificate_card(c, use_color=use_color, detailed=args.detailed)

    # Exportação via argumento de linha de comando
    if args.export:
        out_path = Path(args.export)
        if out_path.suffix.lower() == ".json":
            export_to_json(filtered_certs, out_path)
        else:
            export_to_text(filtered_certs, out_path)
        print(f"[+] Relatório exportado com sucesso para: {out_path.resolve()}\n")

    # Se executado diretamente (ex: duplo-clique no Windows sem flags extras)
    is_direct_run = len(sys.argv) == 1
    if is_direct_run and not args.no_interactive:
        interactive_menu(certs, args.store, use_color=use_color)
    elif not args.no_interactive and not args.json and not args.export:
        input("Pressione Enter para sair...")

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
