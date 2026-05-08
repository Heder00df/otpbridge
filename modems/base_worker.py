from abc import ABC, abstractmethod
from typing import Optional, Callable

class BaseModemWorker(ABC):
    """
    Interface comum para qualquer hardware de modem.
    Implementações: E303Worker, GoIPWorker, OpenVoxWorker.
    """

    def __init__(self, modem_id: int, number: str, on_otp: Callable):
        self.modem_id = modem_id
        self.number = number
        self.on_otp = on_otp
        self.activation_id: Optional[str] = None
        self.service: Optional[str] = None
        self.status = "OFFLINE"  # OFFLINE | FREE | BUSY | ERROR

    def is_free(self) -> bool:
        return self.status == "FREE"

    def reserve(self, activation_id: str, service: str):
        self.activation_id = activation_id
        self.service = service
        self.status = "BUSY"

    def release(self, finish_status: int):
        label = "CONCLUÍDO" if finish_status == 3 else "CANCELADO"
        print(f"[Modem {self.modem_id}] {label} (status={finish_status})")
        self.activation_id = None
        self.service = None
        self.status = "FREE"

    @abstractmethod
    def start(self):
        """Inicia o worker (conecta ao hardware, registra callbacks)."""

    @abstractmethod
    def stop(self):
        """Para o worker e libera recursos."""
