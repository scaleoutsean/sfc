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
from typing import Tuple

def create_certificates():
    # Create CA certificates under ./certs/_master/
    dest = pathlib.Path("./certs/_master")
    dest.mkdir(parents=True, exist_ok=True)

    key_path = dest / "ca.key"
    crt_path = dest / "ca.crt"

    # If they already exist, leave them alone
    if key_path.exists() and crt_path.exists():
        logging.info("CA key and certificate already exist at %s. Skipping generation.", dest)
        return (key_path, crt_path)

    subj = "/CN=SFC-CA"
    days = "3650"

    try:
        # Generate private key
        logging.info("Generating CA private key: %s", key_path)
        subprocess.run(["openssl", "genrsa", "-out", str(key_path), "4096"], check=True)

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
            "-subj",
            subj,
        ], check=True)

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

    dest.mkdir(parents=True, exist_ok=True)

    key_path = dest / f"{base_name}.key"
    csr_path = dest / f"{base_name}.csr"
    cert_path = dest / f"{base_name}.crt"

    # If already present, skip
    if key_path.exists() and cert_path.exists():
        logging.info("%s TLS key and certificate already exist. Skipping generation.", base_name)
        return (key_path, cert_path)

    # Generate key and CSR, then sign with CA    
    logging.info("Generating %s private key...", base_name)
    subprocess.run(["openssl", "genrsa", "-out", str(key_path), "4096"], check=True)

    if base_name == "s3":
        # Write SAN config for S3
        san_config = dest / "s3_san.cnf"
        san_config.write_text(f"""
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = s3

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = s3
""")
        logging.info("Generating %s CSR with SAN...", base_name)
        subprocess.run([
            "openssl", "req", "-new", "-key", str(key_path), "-out", str(csr_path), "-config", str(san_config)
        ], check=True)
        logging.info("Signing %s certificate with CA and SAN...", base_name)
        subprocess.run([
            "openssl", "x509", "-req", "-in", str(csr_path), "-CA", str(ca_crt), "-CAkey", str(ca_key), "-CAcreateserial",
            "-out", str(cert_path), "-days", days, "-sha256", "-extensions", "v3_req", "-extfile", str(san_config)
        ], check=True)
        try:
            san_config.unlink()
        except Exception:
            pass
    elif base_name == "influxdb":
        # Write SAN config for InfluxDB
        san_config = dest / "influxdb_san.cnf"
        san_config.write_text(f"""
[req]
distinguished_name = req_distinguished_name
x509_extensions = v3_req
prompt = no

[req_distinguished_name]
CN = influxdb

[v3_req]
subjectAltName = @alt_names

[alt_names]
DNS.1 = influxdb
""")
        logging.info("Generating %s CSR with SAN...", base_name)
        subprocess.run([
            "openssl", "req", "-new", "-key", str(key_path), "-out", str(csr_path), "-config", str(san_config)
        ], check=True)
        logging.info("Signing %s certificate with CA and SAN...", base_name)
        subprocess.run([
            "openssl", "x509", "-req", "-in", str(csr_path), "-CA", str(ca_crt), "-CAkey", str(ca_key), "-CAcreateserial",
            "-out", str(cert_path), "-days", days, "-sha256", "-extensions", "v3_req", "-extfile", str(san_config)
        ], check=True)
        try:
            san_config.unlink()
        except Exception:
            pass
    else:
        logging.info("Generating %s CSR...", base_name)
        subprocess.run([
            "openssl",
            "req",
            "-new",
            "-key",
            str(key_path),
            "-out",
            str(csr_path),
            "-subj",
            subj,
        ], check=True)
        logging.info("Signing %s certificate with CA...", base_name)
        subprocess.run([
            "openssl",
            "x509",
            "-req",
            "-in",
            str(csr_path),
            "-CA",
            str(ca_crt),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-out",
            str(cert_path),
            "-days",
            days,
            "-sha256",
        ], check=True)    

    # Restrict permissions on private key
    try:
        os.chmod(str(key_path), 0o600)
    except OSError:
        logging.debug("Failed to chmod %s private key; continuing.", base_name)

    # Copy CA public cert (binary-safe)
    (dest / "ca.crt").write_bytes(ca_crt.read_bytes())

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
    with open(str(conf_path), "w", encoding="utf-8") as fh:
        fh.write(conf_text)

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
    with open(str(conf_path), "w", encoding="utf-8") as fh:
        fh.write(conf_text)

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
    with open(str(conf_path), "w", encoding="utf-8") as fh:
        fh.write(conf_text)

    logging.info("Grafana TLS material created at %s", str(dest))
    return (key_path, cert_path)


def copy_ca_to_all():
    # Copies CA public key to all services
    for service in ["s3", "influxdb", "grafana", "sfc", "utils"]:
        src = pathlib.Path("./certs/_master/ca.crt")
        dst = pathlib.Path(f"./certs/{service}/ca.crt")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
    return


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate CA and per-service TLS certificates.")
    parser.add_argument("--service", choices=["all", "s3", "influxdb", "grafana", "ca"], default="all", help="Which certs to generate")
    args = parser.parse_args()

    if args.service == "ca":
        create_certificates()
    elif args.service == "s3":
        create_s3_config()
        copy_ca_to_all()
    elif args.service == "influxdb":
        create_influxdb_config()
        copy_ca_to_all()
    elif args.service == "grafana":
        create_grafana_config()
        copy_ca_to_all()
    else:
        create_certificates()
        create_influxdb_config()
        create_s3_config()
        create_grafana_config()
        copy_ca_to_all()
