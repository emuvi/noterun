#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Executa uma sequência configurável de requisições GET/POST à API."""

import json
import sys
import time
import urllib.parse

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def print_error(message: str) -> None:
    """Imprime mensagem de erro no stderr."""
    print(message, file=sys.stderr)


# =============================================================================
# CONFIGURAÇÃO: cada item de REQUESTS representa uma chamada, na ordem listada
# =============================================================================
BASE_URL = "https://wsrenach.hom.denatran.serpro.gov.br/api"

# Campos por chamada:
#   method: "GET" ou "POST"
#   endpoint: caminho relativo à BASE_URL ou URL completa
#   params: parâmetros de query para GET
#   query_params: parâmetros adicionais na URL para POST
#   body_format: "json", "form", "text" ou "none" (POST)
#   body: conteúdo do POST
#   headers: headers adicionais ou sobrescritos para aquela chamada
REQUESTS = [
    {
        "description": "Consulta de exame por número do laudo",
        "method": "GET",
        "endpoint": "/exames-toxicologicos/v1.1/exames/6TS1HJ0SAZ000000011",
        "params": {},
    },
    # Adicione outras chamadas aqui, por exemplo:
    # {
    #     "description": "Exemplo de POST",
    #     "method": "POST",
    #     "endpoint": "/caminho/do/endpoint",
    #     "query_params": {"origem": "script"},
    #     "body_format": "json",
    #     "body": {"campo": "valor"},
    # },
]

DEFAULT_POST_BODY_FORMAT = "json"

CERT_STORE = r"CURRENT_USER\MY"
CERT_SUBJECT_CN = "EVERTON MURILO VIEIRA:05152001900"
CERT_THUMBPRINT = "1D086223243A82631E6D0F00EFB932DB5AD12D8D"

REQUEST_HEADERS = {
    "Accept": "application/json;charset=utf-8",
    # Exemplo: "Authorization": "Bearer ...",
}

TIMEOUTS_MS = (15000, 15000, 30000, 30000)
KEEP_ALIVE = True
IGNORE_SERVER_CERT_ERRORS = False
SSL_ERROR_IGNORE_FLAGS = 0x3300

WINHTTP_PROGID = "WinHttp.WinHttpRequest.5.1"
WINHTTP_OPTION_SSL_ERROR_IGNORE_FLAGS = 4


def _definir_opcao_winhttp(http, option_id, value):
    try:
        http.SetOption(option_id, value)
    except AttributeError:
        http._oleobj_.InvokeTypes(
            6, 0, 4, (24, 0), ((3, 1), (12, 1)), option_id, value
        )


def _adicionar_query_params(url, params):
    if not params:
        return url

    parsed = urllib.parse.urlsplit(url)
    existing_params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    new_params = urllib.parse.urlencode(params, doseq=True)
    query = urllib.parse.urlencode(existing_params)
    if query and new_params:
        query = f"{query}&{new_params}"
    else:
        query = query or new_params
    return urllib.parse.urlunsplit(parsed._replace(query=query))


def _montar_requisicao(request_config):
    method = request_config["method"].strip().upper()
    if method not in ("GET", "POST"):
        raise ValueError('O método de cada chamada deve ser "GET" ou "POST".')

    endpoint = request_config["endpoint"].strip()
    if endpoint.lower().startswith(("http://", "https://")):
        url = endpoint
    else:
        url = f"{BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"

    headers = dict(REQUEST_HEADERS)
    headers.update(request_config.get("headers", {}))

    if method == "GET":
        url = _adicionar_query_params(url, request_config.get("params", {}))
        return method, url, None, headers

    url = _adicionar_query_params(url, request_config.get("query_params", {}))
    body_format = request_config.get(
        "body_format", DEFAULT_POST_BODY_FORMAT
    ).strip().lower()
    post_body = request_config.get("body")

    if body_format == "json":
        body = json.dumps(post_body, ensure_ascii=False)
        headers.setdefault("Content-Type", "application/json;charset=utf-8")
    elif body_format == "form":
        if not isinstance(post_body, dict):
            raise TypeError('O campo "body" deve ser um dicionário no formato "form".')
        body = urllib.parse.urlencode(post_body, doseq=True)
        headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
    elif body_format == "text":
        if not isinstance(post_body, str):
            raise TypeError('O campo "body" deve ser texto no formato "text".')
        body = post_body
        headers.setdefault("Content-Type", "text/plain; charset=utf-8")
    elif body_format == "none":
        body = None
    else:
        raise ValueError('body_format deve ser "json", "form", "text" ou "none".')

    return method, url, body, headers


class SessaoMTLS:
    """Reutiliza o mesmo objeto WinHTTP ao executar várias chamadas em sequência."""

    def __init__(self):
        try:
            import win32com.client
            self._win32com = win32com.client
        except ImportError as erro:
            raise RuntimeError(
                "A biblioteca pywin32 é necessária. Instale com: pip install pywin32"
            ) from erro

        self._init_http()
        self.cert_path = f"{CERT_STORE}\\{CERT_SUBJECT_CN}"

    def _init_http(self):
        self.http = self._win32com.Dispatch(WINHTTP_PROGID)
        self.http.SetTimeouts(*TIMEOUTS_MS)

    def executar(self, request_config, is_first=False):
        method, url, body, headers = _montar_requisicao(request_config)

        last_err = None
        for attempt in range(1, 3):
            try:
                self.http.Open(method, url, False)

                if IGNORE_SERVER_CERT_ERRORS:
                    _definir_opcao_winhttp(
                        self.http,
                        WINHTTP_OPTION_SSL_ERROR_IGNORE_FLAGS,
                        SSL_ERROR_IGNORE_FLAGS,
                    )

                self.http.SetClientCertificate(self.cert_path)
                if KEEP_ALIVE:
                    headers.setdefault("Connection", "Keep-Alive")
                for name, value in headers.items():
                    self.http.SetRequestHeader(name, str(value))

                if attempt == 1:
                    print(f"[*] Enviando {method} para: {url}")
                    print(f"[*] Certificado: {CERT_SUBJECT_CN} (SHA-1: {CERT_THUMBPRINT})")
                    if IGNORE_SERVER_CERT_ERRORS:
                        print("[!] Validação do certificado do servidor está desabilitada.")
                    if is_first:
                        print("[*] Se necessário, informe o PIN do token A3.\n")

                if body is None:
                    self.http.Send()
                else:
                    self.http.Send(body)
                return self.http.Status, self.http.StatusText, self.http.ResponseText
            except Exception as erro:
                last_err = erro
                if attempt < 2:
                    print(f"[*] Erro transitório na requisição (tentativa {attempt}/2). Reiniciando sessão e tentando novamente...")
                    time.sleep(1.5)
                    try:
                        self._init_http()
                    except Exception:
                        pass
                    continue
        raise last_err


def main() -> int:
    if not REQUESTS:
        print("Nenhuma chamada configurada em REQUESTS.")
        return 0

    try:
        sessao = SessaoMTLS()
    except Exception as erro:
        print_error(f"[!] Não foi possível iniciar a sessão: {erro}")
        return 1

    failures = 0
    for numero, request_config in enumerate(REQUESTS, 1):
        descricao = request_config.get("description", f"Chamada {numero}")
        print(f"\n[CHAMADA {numero}/{len(REQUESTS)}] {descricao}")
        try:
            status, status_text, response_body = sessao.executar(request_config, is_first=(numero == 1))
            print(f"Status HTTP: {status} ({status_text})")
            try:
                print(json.dumps(json.loads(response_body), indent=2, ensure_ascii=False))
            except (TypeError, ValueError):
                print(response_body)
            if isinstance(status, int) and status >= 400:
                failures += 1
                print_error(f"[!] Chamada {numero} ({descricao}) retornou HTTP {status} ({status_text})")
        except Exception as erro:
            failures += 1
            print_error(f"[!] Falha na chamada {numero} ({descricao}): {erro}")

    return 1 if failures > 0 else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[*] Processo interrompido pelo usuário.")
        sys.exit(0)
    except Exception as erro:
        print_error(f"[!] Erro fatal: {erro}")
        sys.exit(1)