"""
Prepare the secure Mosquitto broker for CyberShield SatCom 3D (v1.1).

Creates, next to this script:
  passwd            Mosquitto password file (hashed passwords, made by mosquitto_passwd)
  credentials.txt   the plain passwords, for you and the simulators (keep it private!)
  certs/            ca.crt, server.crt, server.key for TLS on port 8883 (needs openssl)
  mosquitto-secure.local.conf   mosquitto-secure.conf with full paths for THIS computer

Usage (from the project root):
  python iot/mosquitto/setup_secure_mqtt.py
  python iot/mosquitto/setup_secure_mqtt.py --mosquitto-dir "D:\\Program Files\\mosquitto" --devices IOT-001,IOT-002,IOT-003,ESP32-001
  python iot/mosquitto/setup_secure_mqtt.py --host 192.168.1.23      (IP the ESP32 uses, for the TLS certificate)

Runs again safely: existing passwords in credentials.txt are kept.
"""
import argparse
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def find_tool(name: str, folder: str | None) -> str | None:
    if folder:
        for candidate in (Path(folder) / name, Path(folder) / f"{name}.exe"):
            if candidate.exists():
                return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    for guess in (r"C:\Program Files\mosquitto", r"D:\Program Files\mosquitto", r"C:\Program Files\Git\usr\bin"):
        exe = Path(guess) / f"{name}.exe"
        if exe.exists():
            return str(exe)
    return None


def load_credentials(path: Path) -> dict[str, str]:
    creds = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if ":" in line and not line.startswith("#"):
                user, pw = line.split(":", 1)
                creds[user.strip()] = pw.strip()
    return creds


def make_certs(openssl: str, host: str, certs: Path) -> None:
    certs.mkdir(exist_ok=True)
    ca_key, ca_crt = certs / "ca.key", certs / "ca.crt"
    key, csr, crt = certs / "server.key", certs / "server.csr", certs / "server.crt"
    ext = certs / "server.ext"
    sans = ["DNS:localhost", "IP:127.0.0.1"] + ([f"IP:{host}"] if host.replace(".", "").isdigit() else [f"DNS:{host}"])
    sans = list(dict.fromkeys(sans))
    ext.write_text(f"subjectAltName={','.join(sans)}\n", encoding="utf-8")

    def run(*args):
        subprocess.run([openssl, *args], check=True, capture_output=True)

    run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "825", "-keyout", str(ca_key), "-out", str(ca_crt),
        "-subj", "/CN=CyberShield Lab CA")
    run("req", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(csr), "-subj", f"/CN={host}")
    run("x509", "-req", "-in", str(csr), "-CA", str(ca_crt), "-CAkey", str(ca_key), "-CAcreateserial",
        "-out", str(crt), "-days", "825", "-sha256", "-extfile", str(ext))
    csr.unlink(missing_ok=True)
    print(f"  TLS certificates in {certs} (CA: ca.crt, valid for: {', '.join(sans)})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--devices", default="IOT-001,IOT-002,IOT-003,ESP32-001", help="device IDs (= MQTT user names)")
    ap.add_argument("--mosquitto-dir", default=None, help="folder with mosquitto_passwd(.exe)")
    ap.add_argument("--host", default="localhost", help="name or IP of the broker for the TLS certificate")
    ap.add_argument("--no-tls", action="store_true", help="skip the certificates")
    args = ap.parse_args()

    passwd_tool = find_tool("mosquitto_passwd", args.mosquitto_dir)
    if not passwd_tool:
        sys.exit("mosquitto_passwd not found. Pass --mosquitto-dir \"D:\\Program Files\\mosquitto\".")

    cred_file = HERE / "credentials.txt"
    creds = load_credentials(cred_file)
    for user in ["backend"] + [d.strip().upper() for d in args.devices.split(",") if d.strip()]:
        creds.setdefault(user, secrets.token_urlsafe(12))

    passwd = HERE / "passwd"
    passwd.unlink(missing_ok=True)
    first = True
    for user, pw in creds.items():
        cmd = [passwd_tool, "-b"] + (["-c"] if first else []) + [str(passwd), user, pw]
        subprocess.run(cmd, check=True, capture_output=True)
        first = False
    cred_file.write_text("# CyberShield MQTT accounts (user:password). Keep this file private.\n"
                         + "".join(f"{u}:{p}\n" for u, p in creds.items()), encoding="utf-8")
    print(f"  {len(creds)} MQTT accounts -> {passwd} (hashed) and {cred_file} (plain, private)")

    if not args.no_tls:
        openssl = find_tool("openssl", None)
        if openssl:
            make_certs(openssl, args.host, HERE / "certs")
        else:
            print("  openssl not found: TLS skipped (install Git for Windows, it includes openssl). "
                  "Port 1883 with passwords still works.")

    # A ready-to-use broker config with absolute paths (Mosquitto needs full paths).
    template = (HERE / "mosquitto-secure.conf").read_text(encoding="utf-8")
    local = template
    for name in ("passwd", "acl.conf", "certs/ca.crt", "certs/server.crt", "certs/server.key"):
        local = local.replace(f"iot/mosquitto/{name}", str(HERE / name).replace("\\", "/"))
    if args.no_tls or not (HERE / "certs" / "ca.crt").exists():
        local = local.split("# Encrypted MQTT (TLS).")[0] + "\n" + local.split("tls_version tlsv1.2", 1)[1]
    (HERE / "mosquitto-secure.local.conf").write_text(local, encoding="utf-8")
    print(f"  broker config with full paths -> {HERE / 'mosquitto-secure.local.conf'}")

    print("\nPut this in the .env file of the project:")
    print("  MQTT_USERNAME=backend")
    print(f"  MQTT_PASSWORD={creds['backend']}")
    if not args.no_tls and (HERE / "certs" / "ca.crt").exists():
        print("  # for encrypted MQTT also:")
        print("  MQTT_TLS=true")
        print("  MQTT_PORT=8883")
        print(f"  MQTT_CA_CERT={HERE / 'certs' / 'ca.crt'}")
    print("\nThen start Mosquitto with the new config (see docs/SECURE_MQTT.md):")
    print(f'  mosquitto -c "{HERE / "mosquitto-secure.local.conf"}" -v')


if __name__ == "__main__":
    main()
