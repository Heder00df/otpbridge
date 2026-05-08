"""
Script de diagnóstico — roda antes de qualquer coisa.
Verifica modems conectados e testa AT^CVOICE?.

Uso: python -m tests.test_modem
"""
import os, fcntl, termios, tty, time, glob

def send_at(port: str, command: str, wait: float = 1.0) -> str:
    """
    Abre a porta com O_NONBLOCK para contornar BrokenPipeError do driver
    option da Huawei, depois alterna para modo bloqueante antes de ler.
    """
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        fcntl.fcntl(fd, fcntl.F_SETFL, 0)          # volta para bloqueante
        tty.setraw(fd)
        attrs = termios.tcgetattr(fd)
        attrs[4] = termios.B115200
        attrs[5] = termios.B115200
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        time.sleep(0.1)
        os.write(fd, (command + "\r").encode())
        time.sleep(wait)
        try:
            resp = os.read(fd, 1024)
        except BlockingIOError:
            resp = b""
        return resp.decode(errors="ignore").strip()
    finally:
        os.close(fd)

def main():
    print("=== OTPBridge — Diagnóstico de Modems ===\n")
    ports = sorted(glob.glob("/dev/ttyUSB*"))

    if not ports:
        print("Nenhuma porta /dev/ttyUSB* encontrada.")
        print("Verifique se o modem está conectado e o driver carregado.")
        return

    print(f"{len(ports)} porta(s) detectada(s):\n")
    for i, port in enumerate(ports):
        print(f"Porta {i+1}: {port}")

        resp = send_at(port, "AT")
        ok = "OK" in resp
        print(f"  AT          → {'OK' if ok else repr(resp)}")
        if not ok:
            print()
            continue

        resp = send_at(port, "AT+CNUM")
        print(f"  AT+CNUM     → {repr(resp)}")

        resp = send_at(port, "AT^CVOICE?")
        if "ERROR" in resp:
            print(f"  AT^CVOICE?  → ❌ VOZ BLOQUEADA neste modem")
        elif "CVOICE" in resp:
            print(f"  AT^CVOICE?  → ✅ VOZ HABILITADA")
        else:
            print(f"  AT^CVOICE?  → {repr(resp)}")
        print()

if __name__ == "__main__":
    main()
