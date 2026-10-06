"""
Le regole di Calliope sui comandi della casa: valgono per ogni adattatore.

Il comando è già stato interpretato (quali entità, quale azione) ma non eseguito. Qui si
decide se può partire:

- solo entità esposte: un bersaglio fuori dall'elenco delle esposte blocca tutto, anche se
  il sistema lo accetterebbe (cintura e bretelle: Home Assistant già le filtra);
- domini delicati in sola lettura: serrature, allarme, porte del garage e cancelli
  (`casa_sola_lettura_domini`, `casa_sola_lettura_classi`). Si leggono, non si comandano;
- i pulsanti che riavviano o spengono un apparecchio (classe «restart», «spegni»,
  «riavvia», «reboot», «riconnetti» nel nome), salvo `casa_consentiti` (04/10);
- scene, script e automazioni solo se sono in `casa_consentiti`: possono fare qualunque
  cosa, anche aprire una serratura;
- frasi e automazioni personalizzate della casa (non le frasi standard): non si eseguono,
  Calliope non sa cosa fanno;
- l'ospite niente, salvo i domini di `casa_ospite_domini` (per esempio le luci);
- tutto ciò che non è un comando della casa (ora, timer, liste…) torna al modello, che ha
  i tool di Calliope per quelle cose.
"""

import re

from .base import Entita, Interpretazione

# Domini «interruttore» che possono comandare qualunque cosa: un relè Shelly del cancello è
# uno switch, un pulsante (button) si preme con «accendi», una valvola del gas, un
# input_boolean che arma l'allarme. Per questi decide anche il nome (o la stanza, o un alias)
# dell'entità: con una parola di `casa_nomi_delicati` si leggono e non si comandano (analisi
# di sicurezza del 03/10, S6). Le luci no: «la luce del garage» resta comandabile.
_PER_NOME = {"switch", "button", "input_button", "input_boolean", "valve", "siren"}

# Pulsanti che riavviano o spengono un apparecchio (verifica sulla DGX del 04/10: i button di
# riavvio e di spegnimento, di un router, di un modem o di un NAS, si comandavano; HA li
# espone con la classe «restart» o solo con il nome): «premi riavvia» detto per sbaglio, o
# da una TV, può spegnere la rete di casa. In sola lettura per tutti, salvo
# casa_consentiti. Conta il nome dell'entità o l'id (a inizio di parola, anche dopo «_»),
# non la stanza
_RIAVVIO = re.compile(r"(?<![^\W_])(?:spegn|shutdown|shut_down|riavvi|reboot|restart|riconnett|"
                      r"reconnect|power_?off)", re.I)
_PULSANTI = {"button", "input_button"}

# Domini che possono fare qualunque cosa: solo da elenco
_DA_ELENCO = {"script", "automation", "scene"}

# Motivi del rifiuto → frase da dire. Sono frasi fisse: per la sicurezza non si lascia
# che il modello le riformuli in «fatto»
FRASI = {
    "delicata": ("Per sicurezza serrature, allarme, cancello e porta del garage non li "
                 "comando a voce: posso solo dirti come sono."),
    "non_esposta": ("Quel dispositivo non è tra quelli che posso comandare: va esposto ad "
                    "Assist in Home Assistant."),
    "riavvio": ("Per sicurezza non premo i pulsanti che riavviano o spengono un "
                "apparecchio: chi amministra può aggiungerli all'elenco casa_consentiti."),
    "da_elenco": ("Non avvio scene, script o automazioni che non conosco: chi amministra "
                  "può aggiungerli all'elenco casa_consentiti."),
    "propria": ("Quella è una frase personalizzata della casa: da qui non la eseguo, perché "
                "non so cosa fa."),
    "ospite": "",          # lo spiega il modello, come per gli altri tool
    "non_casa": "",        # torna al modello: non è un comando della casa
}


class Regole:
    def __init__(self, cfg):
        self.domini_lettura = {d.strip().lower() for d in
                               (getattr(cfg, "casa_sola_lettura_domini", None) or [])}
        self.classi_lettura = {c.strip().lower() for c in
                               (getattr(cfg, "casa_sola_lettura_classi", None) or [])}
        self.consentiti = {c.strip().lower() for c in
                           (getattr(cfg, "casa_consentiti", None) or [])}
        self.ospite_domini = {d.strip().lower() for d in
                              (getattr(cfg, "casa_ospite_domini", None) or [])}
        nomi = [str(n).strip().lower() for n in
                (getattr(cfg, "casa_nomi_delicati", None) or []) if str(n).strip()]
        # «cancell*» = come inizio di parola; senza asterisco la parola intera («porta» non
        # prende «portatile»)
        parti = [re.escape(n[:-1]) + r"\w*" if n.endswith("*") else re.escape(n) + r"\b"
                 for n in nomi]
        self.nomi_delicati = (re.compile(r"(?<!\w)(?:" + "|".join(parti) + ")", re.I)
                              if parti else None)

    def delicata(self, e: Entita) -> bool:
        """Si legge ma non si comanda. Un'entità in `casa_consentiti` (id o nome) si
        comanda comunque: è la scelta esplicita di chi amministra per uno switch voluto."""
        if e.id.lower() in self.consentiti or e.nome.lower() in self.consentiti:
            return e.dominio in self.domini_lettura
        if e.dominio in self.domini_lettura:
            return True
        if self.riavvio(e):
            return True
        classe = (e.classe or "").lower()
        if e.dominio in ("cover", "binary_sensor", "valve") and classe in self.classi_lettura:
            return True
        per_nome = e.dominio in _PER_NOME or (e.dominio == "cover"
                                              and classe in ("", "door", "gate", "garage"))
        if per_nome and self.nomi_delicati is not None:
            testo = " ".join([e.nome or "", e.id.split(".", 1)[-1].replace("_", " "),
                              e.area or "", *(e.alias or [])])
            return bool(self.nomi_delicati.search(testo))
        return False

    @staticmethod
    def riavvio(e: Entita) -> bool:
        """Un pulsante che riavvia o spegne un apparecchio (classe «restart», o «spegni»,
        «shutdown», «riavvia», «reboot», «riconnetti» nel nome o nell'id)."""
        if e.dominio not in _PULSANTI:
            return False
        if (e.classe or "").lower() == "restart":
            return True
        return bool(_RIAVVIO.search(f"{e.nome or ''} {e.id.split('.', 1)[-1]}"))

    def da_elenco(self, e: Entita) -> bool:
        return (e.dominio in _DA_ELENCO and e.id.lower() not in self.consentiti
                and e.nome.lower() not in self.consentiti)

    def visibile(self, e: Entita, livello: str) -> bool:
        """L'entità si può leggere da chi parla?"""
        if livello == "ospite":
            return e.dominio in self.ospite_domini
        return livello in ("familiare", "amministra")

    def controlla(self, interp: Interpretazione, esposte: dict[str, Entita],
                  livello: str) -> str | None:
        """Il motivo del rifiuto (chiave di FRASI), o None se il comando può partire."""
        if interp.origine != "predefinita":
            return "propria"
        if interp.azione == "altro":
            return "non_casa"
        if livello not in ("familiare", "amministra") and not self.ospite_domini:
            return "ospite"
        for eid in interp.bersagli:
            e = esposte.get(eid)
            if e is None:
                return "non_esposta"
            if livello == "ospite" and e.dominio not in self.ospite_domini:
                return "ospite"
            if interp.azione == "comando":
                if self.delicata(e):
                    return "riavvio" if self.riavvio(e) else "delicata"
                if self.da_elenco(e):
                    return "da_elenco"
        if livello == "ospite" and not interp.bersagli:
            return "ospite"          # niente bersagli da controllare: per l'ospite no
        return None
