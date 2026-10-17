"""Porte locali per le prove (17/10, #5).

`porta_libera()` prende una porta effimera con `bind(0)` e la rilascia: fra il `close()` e il
`bind` di chi la usa dopo (un sottoprocesso, Calliope vera) un altro processo può riceverla, da
un altro `bind(0)` o per una connessione in uscita. Con le altre prove di un `--completo` in
corso succede: è la corsa trovata il 15/10 in `prova_agenti` (il tunnel finto).

`porta_fuori_effimere()` sceglie invece a caso fra 20000 e 31999, sotto le porte effimere di
Windows (da 49152) e di Linux (da 32768): lì il sistema non assegna porte da solo, e una porta
la può prendere solo chi la chiede per numero.
"""

import random
import socket


def porta_libera() -> int:
    """Una porta effimera libera adesso (va bene per un server che la apre subito, nello stesso
    processo; per un sottoprocesso meglio `porta_fuori_effimere`)."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def porta_fuori_effimere() -> int:
    """Una porta libera fra 20000 e 31999, a caso: fuori dalle porte effimere (Hyper-V ne
    riserva alcune, e una porta occupata si salta). In ultima istanza una effimera."""
    for _ in range(200):
        p = random.randrange(20000, 32000)
        s = socket.socket()
        try:
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    return porta_libera()
