#!/usr/bin/env python3

###############################################################################
# Synopsis:                                                                   #
# Creates CA and TLS certificates for various services in SolidFire Collector #
#   version 2.1 and above.                                                    #
#                                                                             #
# Author: @scaleoutSean (Github)                                              #
# Repository: https://github.com/scaleoutsean/sfc                             #
# License: the Apache License Version 2.0                                     #
###############################################################################

import os
import pathlib
import subprocess
import logging
import re
import ssl
import sys
import ipaddress
import tempfile
import fnmatch
from typing import Tuple

USE_SUDO = False
FORCE_REGENERATE = False


def _ensure_dir(path: pathlib.Path):
    try:
        path.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        if not USE_SUDO:
            raise
        subprocess.run(["sudo", "mkdir", "-p", str(path)], check=True)


def _write_bytes_file(path: pathlib.Path, data: bytes, mode: int = None):
    try:
        _ensure_dir(path.parent)
        path.write_bytes(data)
        if mode is not None:
            os.chmod(str(path), mode)
        return
    except PermissionError:
        if not USE_SUDO:
            raise

    _ensure_dir(path.parent)
    subprocess.run(["sudo", "tee", str(path)], input=data, stdout=subprocess.DEVNULL, check=True)
    if mode is not None:
        subprocess.run(["sudo", "chmod", format(mode, "o"), str(path)], check=True)


def _write_text_file(path: pathlib.Path, text: str, mode: int = None):
    _write_bytes_file(path, text.encode("utf-8"), mode=mode)


def _extract_cn_from_subj(subj: str, fallback: str = "localhost") -> str:
    marker = "/CN="
    if marker not in subj:
        return fallback
    return subj.split(marker, 1)[1].strip() or fallback


def _build_server_ext_config(common_name: str, dns_names: list, ip_names: list) -> str:
    lines = [
        "[req]",
        "distinguished_name = req_distinguished_name",
        "x509_extensions = v3_req",
        "prompt = no",
        "",
        "[req_distinguished_name]",
        f"CN = {common_name}",
        "",
        "[v3_req]",
        "basicConstraints = critical,CA:FALSE",
        "keyUsage = critical,digitalSignature,keyEncipherment",
        "extendedKeyUsage = serverAuth",
        "subjectAltName = @alt_names",
        "",
        "[alt_names]",
    ]

    n = 1
    for dns in dns_names:
        lines.append(f"DNS.{n} = {dns}")
        n += 1

    n = 1
    for ip in ip_names:
        lines.append(f"IP.{n} = {ip}")
        n += 1

    return "\n".join(lines) + "\n"

def create_certificates():
    # Create CA certificates under ./certs/_master/
    dest = pathlib.Path("./certs/_master")
    _ensure_dir(dest)

    key_path = dest / "ca.key"
    crt_path = dest / "ca.crt"

    # If they already exist, leave them alone unless forced.
    if key_path.exists() and crt_path.exists() and not FORCE_REGENERATE:
        logging.info("CA key and certificate already exist at %s. Skipping generation.", dest)
        return (key_path, crt_path)

    days = "3650"
    ca_config = dest / "ca_ext.cnf"

    try:
        # Generate private key
        logging.info("Generating CA private key: %s", key_path)
        subprocess.run(["openssl", "genrsa", "-out", str(key_path), "4096"], check=True)

        # OpenSSL 3 expects CA certs to carry proper CA/key usage constraints.
        _write_text_file(ca_config, """
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_ca
prompt = no

[req_distinguished_name]
CN = SFC-CA

[v3_ca]
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid:always,issuer
basicConstraints = critical,CA:true
keyUsage = critical,keyCertSign,cRLSign
""")

        # Generate self-signed cert
        logging.info("Generating self-signed CA certificate: %s", crt_path)
        subprocess.run([
            "openssl",
            "req",
            "-x509",
            "-new",
            "-nodes",
            "-key",
            str(key_path),
            "-sha256",
            "-days",
            days,
            "-out",
            str(crt_path),
            "-config",
            str(ca_config),
        ], check=True)

        # Reset serial file when CA is regenerated.
        ca_srl = dest / "ca.srl"
        if ca_srl.exists():
            try:
                ca_srl.unlink()
            except OSError:
                pass

        # Restrict permissions on private key
        try:
            os.chmod(str(key_path), 0o600)
        except OSError:
            logging.debug("Failed to chmod private key; continuing.")

        logging.info("Created CA key and certificate at %s", dest)
        return (key_path, crt_path)
    except subprocess.CalledProcessError as e:
        logging.error("OpenSSL command failed: %s", e)
        raise


def gen_sign_csr(dest: pathlib.Path, base_name: str, subj: str, days: str = "3650") -> Tuple[pathlib.Path, pathlib.Path]:
    """Generate a private key, CSR and sign it with the master CA.

    Returns (key_path, cert_path).
    If both key and cert already exist, the function will skip generation and return them.
    """
    master = pathlib.Path("./certs/_master")
    ca_key = master / "ca.key"
    ca_crt = master / "ca.crt"

    # Ensure CA exists
    if not (ca_key.exists() and ca_crt.exists()):
        create_certificates()

    _ensure_dir(dest)

    key_path = dest / f"{base_name}.key"
    csr_path = dest / f"{base_name}.csr"
    cert_path = dest / f"{base_name}.crt"

    # If already present, skip unless forced.
    if key_path.exists() and cert_path.exists() and not FORCE_REGENERATE:
        logging.info("%s TLS key and certificate already exist. Skipping generation.", base_name)
        return (key_path, cert_path)

    # Generate key and CSR, then sign with CA    
    logging.info("Generating %s private key...", base_name)
    subprocess.run(["openssl", "genrsa", "-out", str(key_path), "4096"], check=True)

    common_name = _extract_cn_from_subj(subj, fallback=base_name)
    dns_names = [common_name]
    ip_names = []

    if base_name in ("influxdb", "s3", "grafana", "explorer"):
        dns_names = [base_name, "localhost"]
        ip_names = ["127.0.0.1"]

    san_config = dest / f"{base_name}_san.cnf"
    _write_text_file(san_config, _build_server_ext_config(common_name, dns_names, ip_names))

    logging.info("Generating %s CSR with SAN extensions...", base_name)
    subprocess.run([
        "openssl", "req", "-new", "-key", str(key_path), "-out", str(csr_path), "-config", str(san_config)
    ], check=True)

    logging.info("Signing %s certificate with CA and SAN extensions...", base_name)
    subprocess.run([
        "openssl", "x509", "-req", "-in", str(csr_path), "-CA", str(ca_crt), "-CAkey", str(ca_key), "-CAcreateserial",
        "-out", str(cert_path), "-days", days, "-sha256", "-extensions", "v3_req", "-extfile", str(san_config)
    ], check=True)

    try:
        san_config.unlink()
    except Exception:
        pass

    # Restrict permissions on private key
    try:
        os.chmod(str(key_path), 0o600)
    except OSError:
        logging.debug("Failed to chmod %s private key; continuing.", base_name)

    # Copy CA public cert (binary-safe)
    _write_bytes_file(dest / "ca.crt", ca_crt.read_bytes())

    # Clean up CSR
    try:
        csr_path.unlink()
    except OSError:
        pass

    return (key_path, cert_path)

def create_influxdb_config():
    # Create InfluxDB 3 CSR, sign it with CA key, copy to ./certs/influxdb
    master = pathlib.Path("./certs/_master")
    ca_key = master / "ca.key"
    ca_crt = master / "ca.crt"

    # Ensure CA exists
    if not (ca_key.exists() and ca_crt.exists()):
        create_certificates()

    dest = pathlib.Path("./certs/influxdb")
    key_path, cert_path = gen_sign_csr(dest, "influxdb", "/CN=influxdb")

    # Write a tiny example TLS config file for convenience
    conf_path = dest / "influxdb_tls.conf"
    conf_text = (
        "# Minimal InfluxDB TLS configuration (example)\n"
        "tls_enabled = true\n"
        f"tls_cert_file = {str(cert_path)}\n"
        f"tls_key_file = {str(key_path)}\n"
        f"tls_ca_file = {str(dest / 'ca.crt')}\n"
    )
    _write_text_file(conf_path, conf_text)

    logging.info("InfluxDB TLS material created at %s", str(dest))
    return (key_path, cert_path)

def create_s3_config():
    # Create S3 Gateway CSR, sign it with CA key, copy to ./certs/s3
    master = pathlib.Path("./certs/_master")
    ca_key = master / "ca.key"
    ca_crt = master / "ca.crt"

    if not (ca_key.exists() and ca_crt.exists()):
        create_certificates()

    dest = pathlib.Path("./certs/s3")
    key_path, cert_path = gen_sign_csr(dest, "s3", "/CN=s3")

    conf_path = dest / "s3_tls.conf"
    conf_text = (
        "# Minimal S3 TLS configuration (example)\n"
        f"tls_cert = {str(cert_path)}\n"
        f"tls_key = {str(key_path)}\n"
        f"tls_ca = {str(dest / 'ca.crt')}\n"
    )
    _write_text_file(conf_path, conf_text)

    logging.info("S3 TLS material created at %s", str(dest))
    return (key_path, cert_path)

def create_grafana_config():
    # Create Grafana CSR, sign it with CA key, copy to ./certs/grafana
    master = pathlib.Path("./certs/_master")
    ca_key = master / "ca.key"
    ca_crt = master / "ca.crt"

    if not (ca_key.exists() and ca_crt.exists()):
        create_certificates()

    dest = pathlib.Path("./certs/grafana")
    key_path, cert_path = gen_sign_csr(dest, "grafana", "/CN=grafana")

    conf_path = dest / "grafana_tls.conf"
    conf_text = (
        "# Minimal Grafana TLS configuration (example)\n"
        f"cert_file = {str(cert_path)}\n"
        f"cert_key = {str(key_path)}\n"
        f"ca_file = {str(dest / 'ca.crt')}\n"
    )
    _write_text_file(conf_path, conf_text)

    logging.info("Grafana TLS material created at %s", str(dest))
    return (key_path, cert_path)


def create_explorer_config():
    # Create InfluxDB Explorer CSR, sign it with CA key, copy to ./certs/explorer
    # NOTE: InfluxDB3 Explorer expects cert.pem and key.pem hardcoded names
    master = pathlib.Path("./certs/_master")
    ca_key = master / "ca.key"
    ca_crt = master / "ca.crt"

    if not (ca_key.exists() and ca_crt.exists()):
        create_certificates()

    dest = pathlib.Path("./certs/explorer")
    _ensure_dir(dest)

    # Generate with expected InfluxDB3 Explorer names
    key_path = dest / "key.pem"
    cert_path = dest / "cert.pem"
    fullchain_path = dest / "fullchain.pem"  # Alternative format for Explorer
    
    # If already present, skip
    if key_path.exists() and cert_path.exists():
        logging.info("Explorer TLS key and certificate already exist. Skipping generation.")
        # Still create fullchain.pem if it doesn't exist
        if not fullchain_path.exists():
            if ca_crt.exists():
                # Create fullchain.pem = cert + CA
                fullchain_content = cert_path.read_text() + "\n" + ca_crt.read_text()
                _write_text_file(fullchain_path, fullchain_content)
                logging.info("Created fullchain.pem for Explorer")
        return (key_path, cert_path)

    # Generate temporary files with standard naming, then rename
    temp_key, temp_cert = gen_sign_csr(dest, "explorer", "/CN=explorer")
    
    # Rename to InfluxDB3 Explorer expected names
    temp_key.rename(key_path)
    temp_cert.rename(cert_path)
    
    # Create fullchain.pem (cert + CA chain) for Explorer compatibility
    if ca_crt.exists():
        fullchain_content = cert_path.read_text() + "\n" + ca_crt.read_text()
        _write_text_file(fullchain_path, fullchain_content)
        logging.info("Created fullchain.pem for Explorer")

    conf_path = dest / "explorer_tls.conf"
    conf_text = (
        "# Minimal InfluxDB Explorer TLS configuration (example)\n"
        f"cert_file = {str(cert_path)}\n"
        f"cert_key = {str(key_path)}\n"
        f"fullchain_file = {str(fullchain_path)}\n"
        f"ca_file = {str(dest / 'ca.crt')}\n"
    )
    _write_text_file(conf_path, conf_text)

    logging.info("InfluxDB Explorer TLS material created at %s", str(dest))
    return (key_path, cert_path)


def copy_ca_to_all():
    # Copies CA public key to all services
    src = pathlib.Path("./certs/_master/ca.crt")
    for service in ["s3", "influxdb", "grafana", "sfc", "utils", "explorer"]:
        dst = pathlib.Path(f"./certs/{service}/ca.crt")
        _ensure_dir(dst.parent)
        _write_bytes_file(dst, src.read_bytes())

    # Keep legacy Docker build context input in sync for influxdb/Dockerfile:
    # COPY ./ca.crt /home/influxdb3/certs/ca.crt
    legacy_influxdb_ca = pathlib.Path("./influxdb/ca.crt")
    _ensure_dir(legacy_influxdb_ca.parent)
    _write_bytes_file(legacy_influxdb_ca, src.read_bytes())
    return


def _parse_solidfire_host_and_port(user_input: str) -> Tuple[str, int]:
    value = user_input.strip()
    if not value:
        raise ValueError("SolidFire host input is empty")

    # Accept inputs like:
    # - 192.168.1.34
    # - sf.example.local
    # - 192.168.1.34:443
    # - https://sf.example.local:8443
    if "://" in value:
        from urllib.parse import urlparse
        parsed = urlparse(value)
        if not parsed.hostname:
            raise ValueError(f"Could not parse host from input: {user_input}")
        host = parsed.hostname
        port = parsed.port or 443
        return host, port

    if value.count(":") == 1 and not value.startswith("["):
        host_part, port_part = value.split(":", 1)
        if host_part and port_part.isdigit():
            return host_part, int(port_part)

    return value, 443


def _safe_cert_filename(host: str) -> str:
    # Keep cert filenames portable and predictable.
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", host.strip())
    return safe or "solidfire"


def _extract_san_entries_from_pem(pem_data: str) -> Tuple[list, list]:
    """Return (dns_names, ip_names) parsed from certificate SAN."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".crt", delete=False, encoding="utf-8") as tmp:
        tmp.write(pem_data)
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            ["openssl", "x509", "-in", tmp_path, "-noout", "-ext", "subjectAltName"],
            check=True,
            capture_output=True,
            text=True,
        )
        output = result.stdout
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    dns_names = []
    ip_names = []
    # Example line: DNS:influxdb, DNS:localhost, IP Address:127.0.0.1
    for line in output.splitlines():
        parts = [p.strip() for p in line.split(",")]
        for part in parts:
            if part.startswith("DNS:"):
                dns_names.append(part[len("DNS:"):].strip())
            elif part.startswith("IP Address:"):
                ip_names.append(part[len("IP Address:"):].strip())

    return dns_names, ip_names


def _host_matches_san(host: str, dns_names: list, ip_names: list) -> bool:
    host = host.strip()
    if not host:
        return False

    try:
        host_ip = ipaddress.ip_address(host)
        normalized_ips = set()
        for ip in ip_names:
            try:
                normalized_ips.add(str(ipaddress.ip_address(ip)))
            except ValueError:
                continue
        return str(host_ip) in normalized_ips
    except ValueError:
        pass

    host_l = host.lower()
    for dns in dns_names:
        dns_l = dns.lower()
        if dns_l == host_l:
            return True
        if "*" in dns_l and fnmatch.fnmatch(host_l, dns_l):
            return True
    return False


def maybe_download_solidfire_certificate(download_mode: str = "auto", solidfire_host: str = ""):
    """Optionally download SolidFire endpoint certificate and store it for SFC trust use.

    Stores cert in:
    - ./certs/solidfire/<fqdn-or-ip>.crt (reference archive)
    - ./sfc/certs/<fqdn-or-ip>.crt (picked up during sfc image build)
    - ./sfc/certs/sf_ca.crt (stable SFC filename)
    - ./certs/sfc/sf_ca.crt (runtime volume-mount path used by compose)
    """
    mode = (download_mode or "auto").strip().lower()
    endpoint = (solidfire_host or "").strip()

    if mode not in ("auto", "yes", "no"):
        logging.warning("Invalid --download-solidfire-cert value '%s'. Using 'auto'.", download_mode)
        mode = "auto"

    if mode == "no":
        logging.info("Skipped SolidFire certificate download (--download-solidfire-cert=no).")
        return

    if not endpoint:
        if mode == "yes":
            if not sys.stdin.isatty():
                logging.warning("--download-solidfire-cert=yes set without --solidfire-host in non-interactive mode; skipping download.")
                return
            endpoint = input("SolidFire host or URL (example: 192.168.1.34 or https://sf.example.local:443): ").strip()
        else:
            if not sys.stdin.isatty():
                logging.info("Non-interactive session detected. Skipping optional SolidFire cert download.")
                return
            answer = input("Do you want to download certificate from SolidFire (n/Y): ").strip().lower()
            if answer in ("n", "no"):
                logging.info("Skipped SolidFire certificate download by user choice.")
                return
            endpoint = input("SolidFire host or URL (example: 192.168.1.34 or https://sf.example.local:443): ").strip()

    if not endpoint:
        logging.warning("No SolidFire host provided. Skipping SolidFire certificate download.")
        return

    try:
        host, port = _parse_solidfire_host_and_port(endpoint)
        pem_data = ssl.get_server_certificate((host, port))
    except Exception as exc:
        logging.error("Failed to download SolidFire certificate from %s: %s", endpoint, exc)
        return

    try:
        dns_names, ip_names = _extract_san_entries_from_pem(pem_data)
        if not _host_matches_san(host, dns_names, ip_names):
            logging.warning(
                "Downloaded SolidFire certificate SAN does not include requested host '%s'. "
                "TLS hostname verification will fail unless you use a matching DNS name or disable verification.",
                host,
            )
            if dns_names or ip_names:
                logging.warning("Certificate SAN entries: DNS=%s IP=%s", dns_names, ip_names)
    except Exception as exc:
        logging.warning("Could not inspect SAN entries in downloaded SolidFire certificate: %s", exc)

    cert_name = _safe_cert_filename(host) + ".crt"

    certs_solidfire_dir = pathlib.Path("./certs/solidfire")
    _ensure_dir(certs_solidfire_dir)
    solidfire_cert_path = certs_solidfire_dir / cert_name
    _write_text_file(solidfire_cert_path, pem_data)

    # Keep SFC build context trust files in sync.
    sfc_build_certs_dir = pathlib.Path("./sfc/certs")
    _ensure_dir(sfc_build_certs_dir)
    _write_text_file(sfc_build_certs_dir / cert_name, pem_data)
    _write_text_file(sfc_build_certs_dir / "sf_ca.crt", pem_data)

    # Keep compose runtime mount path in sync.
    sfc_runtime_certs_dir = pathlib.Path("./certs/sfc")
    _ensure_dir(sfc_runtime_certs_dir)
    _write_text_file(sfc_runtime_certs_dir / "sf_ca.crt", pem_data)

    logging.info("Saved SolidFire certificate to %s", solidfire_cert_path)
    logging.info("Synced SolidFire trust cert to ./sfc/certs/sf_ca.crt and ./certs/sfc/sf_ca.crt")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate CA and per-service TLS certificates.")
    parser.add_argument("--service", choices=["all", "s3", "influxdb", "grafana", "explorer", "ca", "solidfire"], default="all", help="Which certs to generate")
    parser.add_argument(
        "--download-solidfire-cert",
        choices=["auto", "yes", "no"],
        default="auto",
        help="Download SolidFire endpoint cert: auto=interactive prompt, yes=force download, no=skip.")
    parser.add_argument(
        "--solidfire-host",
        default="",
        help="SolidFire host or URL for certificate download (e.g. 192.168.1.34 or https://sf.example.local:443).")
    parser.add_argument(
        "--use-sudo",
        action="store_true",
        help="Use sudo fallback for file writes when permission errors occur.")
    parser.add_argument(
        "--force-regenerate",
        action="store_true",
        help="Regenerate certificates even if they already exist (recommended after CA extension changes).")
    args = parser.parse_args()

    USE_SUDO = args.use_sudo
    FORCE_REGENERATE = args.force_regenerate

    if args.service == "ca":
        create_certificates()
    elif args.service == "solidfire":
        # SolidFire trust cert bootstrap only; avoids touching other service directories.
        pass
    elif args.service == "s3":
        create_s3_config()
        copy_ca_to_all()
    elif args.service == "influxdb":
        create_influxdb_config()
        copy_ca_to_all()
    elif args.service == "grafana":
        create_grafana_config()
        create_explorer_config()
        copy_ca_to_all()
    else:
        create_certificates()
        create_influxdb_config()
        create_s3_config()
        create_grafana_config()
        create_explorer_config()
        copy_ca_to_all()

    # Optional SolidFire trust certificate bootstrap for SFC.
    maybe_download_solidfire_certificate(args.download_solidfire_cert, args.solidfire_host)
