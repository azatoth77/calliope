"""
La conversazione come registro degli eventi (10/10/2026, decisione 0027, progetto
docs/ricerche/2026-10-10-registro-eventi.md).

Passi 0 e 1 del § 8, **in ombra**: la storia di Brain resta la fonte, gli eventi si scrivono
accanto e la proiezione del contesto si confronta con lei a ogni turno.

- `tipi.py`: l'evento, l'elenco chiuso dei tipi con la visibilità predefinita, ciò che va su
  disco (§ 2.1, § 2.2, § 2.4);
- `registro.py`: un registro per persona (anonimo per satellite per ospiti e voci incerte), in
  sola aggiunta, il disco a lotti nel thread dell'archivio, il rigioco al riavvio, «dimentica»,
  le porte fra registri (§ 2.3–2.6);
- `proiezioni.py`: funzioni pure degli eventi, il contesto del modello (§ 3.1);
- `misura.py`: il passo 0, parlato diverso dalla storia e domande non registrate (§ 1);
- `ombra.py`: il collegamento con il ciclo della voce (che cosa è stato detto e sentito, la
  storia di Brain, il confronto) e `calliope stato`.

Solo libreria standard e sqlite3.
"""
