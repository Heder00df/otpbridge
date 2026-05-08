"""
Testa o fluxo completo chamando a API local como se fosse a HeroSMS.
Requer o servidor rodando com SIMULATE=true.

Uso:
  Terminal 1: SIMULATE=true python main.py
  Terminal 2: python tests/test_flow.py
"""
import time
import requests

BASE = "http://localhost:8000"
KEY = "change-me"

def call(action, **params):
    r = requests.get(f"{BASE}/supplier", params={"action": action, "key": KEY, **params})
    return r.json()

def main():
    print("=== OTPBridge — Teste de Fluxo Completo ===\n")

    # 1. GET_SERVICES
    print("1. GET_SERVICES")
    resp = call("GET_SERVICES")
    print(f"   → {resp}\n")

    # 2. GET_NUMBER
    print("2. GET_NUMBER (service=telegram)")
    resp = call("GET_NUMBER", service="telegram", country="55")
    print(f"   → {resp}")
    if resp.get("status") != "success":
        print("   ❌ Sem número disponível")
        return
    activation_id = resp["activationId"]
    number = resp["number"]
    print(f"   ✅ número={number}  activationId={activation_id}\n")

    # 3. Aguarda OTP (simulador entrega em 3-8s)
    print("3. Aguardando OTP do simulador...")
    time.sleep(10)

    # 4. FINISH_ACTIVATION
    print("4. FINISH_ACTIVATION (status=3 = concluído)")
    resp = call("FINISH_ACTIVATION", activationId=activation_id, status=3)
    print(f"   → {resp}\n")

    # 5. GET_SERVICES novamente — modem deve estar livre
    print("5. GET_SERVICES (modem deve estar livre novamente)")
    resp = call("GET_SERVICES")
    print(f"   → {resp}\n")

    print("=== Fluxo concluído ===")

if __name__ == "__main__":
    main()
