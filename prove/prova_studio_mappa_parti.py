import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

"""La mappa generale completa e le mappe delle parti a secco (04/11, issue #385, epic #251, decisione
0035 punto 55; calliope/studio/mappa_genera.py `copertura`, `rete`, `solo_studiabili`,
studio/lettura.py `Lettore.prepara_mappe`, `genera_parte`, studio/mappe.py `proponi_parte`,
`_parti_per_schermo`), col vLLM finto e i materiali di fantasia di `prova_studio_argomenti.py`.

1. **La copertura del codice**: un concetto buono dell'argomento, con una sua pagina; il modello che
   dice un argomento citando pagine di un altro non copre; un concetto con un avviso, staccato o
   legato solo da un debole non copre, il titolo sì; gli argomenti senza pagine pulite esclusi.
2. **Le richieste**: niente «da 6 a 10», ogni argomento nella generale; la parte con le sole pagine
   e il solo argomento suoi; la mirata con i soli argomenti fuori, senza le pagine con istruzioni.
3. **Il giro** (`rete`): la mirata solo se serve e le sue triple controllate come le prime; un concetto
   inventato resta `da_controllare` e non copre; una mirata illeggibile lascia la mappa; nella parte
   le voci con un ordine e da una pagina con istruzioni non entrano; il tetto tiene un concetto per
   argomento prima del quinto di un altro.
4. **Il lettore**: un passo alla volta, la generale e poi una parte per argomento; la stessa firma
   non chiede più niente; una rinomina rifà la generale e quella parte sola; una parte che non riesce
   lascia le altre e la sua di prima, si riprova dopo un'ora e al terzo errore si ferma; una parte su
   sole pagine con istruzioni non chiede niente al modello; con uno scheletro della persona le parti
   si fanno e lui non si tocca; ombra e spenta; `prepara_mappe(id)`, l'ingresso per la #384.
5. **Chi le vede e chi le cambia**: si leggono soltanto (ogni azione le rifiuta), niente alla persona
   mentre fa una mappa senza guardare o una prova (il tutore sì), un altro adulto mai, nel registro e
   nei conti solo numeri; «Fai la tua» e il controllo identici, dalla sola generale.
6. **La forma**: 20 concetti senza riquadri sovrapposti, la lettura per livelli, il PDF con 26
   concetti.
7. **Il banco**: la fase «mappa» misura copertura, verità, parti e tempi e il riepilogo lo dice.

    python prove/prova_studio_mappa_parti.py
"""

import json
import tempfile
import types
from pathlib import Path

QUI = Path(__file__).resolve().parent
_pa = types.ModuleType("PA")
_pa.__file__ = str(QUI / "prova_studio_argomenti.py")
_src = (QUI / "prova_studio_argomenti.py").read_text("utf-8").split(
    "# ─────────────────────────── 1. l'harness")[0]
exec(compile(_src, _pa.__file__, "exec"), _pa.__dict__)
PA = _pa

from calliope.studio import argomenti as A  # noqa: E402
from calliope.studio import genera as G  # noqa: E402
from calliope.studio import mappa as M  # noqa: E402
from calliope.studio import mappa_genera as MG  # noqa: E402
from calliope.studio.servizio import NonTrovata  # noqa: E402

errori = 0


def verifica(nome, ok, dettaglio=""):
    global errori
    errori += not ok
    print(f"{'ok ' if ok else 'ERR'} {nome}" + (f"  ({dettaglio})" if dettaglio and not ok
                                                else ""))


LEO, ANDREA, BRUNO = PA.LEO, PA.ANDREA, PA.BRUNO


def tripla(da, rel, a, arg, *pagine):
    return {"da": da, "relazione": rel, "a": a, "argomento": arg, "pagine": list(pagine)}


def solleva(f, tipo=Exception) -> bool:
    try:
        f()
    except tipo:
        return True
    return False


def prepara(cfg_kw=None, nome="g", titoli=None):
    kw = {"studio_mappa_genera": "attiva", "studio_carte_genera": "spenta",
          "studio_domande_genera": "spenta", **(cfg_kw or {})}
    cfg = PA.cfg_nuova(nome, modo="attivo", studio_argomenti=False, **kw)
    st = PA.studio(cfg)
    vid, ids = PA.verifica_con_pagine(st)
    for t, p in (titoli or (("Perché gli europei partirono", ("p112",)),
                            ("Il Portogallo e la rotta africana", ("p113",)),
                            ("Cristoforo Colombo e il Nuovo Mondo", ("p114",)))):
        st.aggiungi_argomento(LEO, vid, t, [ids[x] for x in p])
    st.conferma_argomenti(LEO, vid)
    lett, _ = PA.lettore(st)
    return st, vid, ids, lett


# P1 indice, P2 p112, P3 p113, P4 p114, P5 p115, P6 p116, P7 appunti, P8 p117 (ostile)
GENERALE = {"triple": [
    tripla("Le scoperte geografiche", "cominciano con", "Il Portogallo", "A2", "P3"),
    tripla("Le scoperte geografiche", "nascono dalla caduta di", "Costantinopoli", "A1", "P2"),
    tripla("Le scoperte geografiche", "portano a", "Cristoforo Colombo", "A3", "P4"),
    tripla("Cristoforo Colombo", "arriva in", "America", "A3", "P4")]}
# Senza il terzo argomento
SENZA_A3 = {"triple": GENERALE["triple"][:2]}
MIRATA = {"triple": [tripla("Le scoperte geografiche", "portano a", "Cristoforo Colombo", "A3", "P4")]}
# Una parte: la pagina è sola, P1
PARTE = {"triple": [
    tripla("Il Portogallo e la rotta africana", "comincia con", "Enrico il Navigatore", "A1", "P1"),
    tripla("Il Portogallo e la rotta africana", "porta a", "Vasco da Gama", "A1", "P1"),
    tripla("Vasco da Gama", "arriva in", "India", "A1", "P1")]}


# ═══════════════════════════ 1. la copertura ═══════════════════════════
print("— la copertura del codice")
def pag(i, avvisi=None):
    return {"id": i, "ordine": i, "stato": "letta", "testo": f"pagina {i}",
            "avvisi": json.dumps(avvisi) if avvisi else None}


PP = [pag(1), pag(2), pag(3, ["istruzioni"])]
AA = [{"id": 10, "titolo": "Le cause", "pagine": [1]}, {"id": 20, "titolo": "Gli effetti", "pagine": [2]},
      {"id": 30, "titolo": "Il messaggio", "pagine": [3]}]


def n_(i, testo, arg, pagine, **k):
    return {"id": i, "testo": testo, "argomento": arg, "argomenti": [arg] if arg else [],
            "pagine": pagine, "autore": "modello", "stato": "proposto", "avvisi": [], **k}


def c_(i, da, a, **k):
    return {"id": i, "da": da, "a": a, "verbo": "porta a", "pagine": [], **k}


N = [n_(1, "Centro", 10, [1]), n_(2, "Spezie", 10, [1]), n_(3, "Oro", 20, [2])]
r = MG.copertura(N, [c_(1, 1, 2), c_(2, 1, 3)], AA, PP)
verifica("un concetto buono con una pagina dell'argomento lo copre; senza pagine pulite è escluso",
         r == {"coperti": [10, 20], "scoperti": [], "esclusi": [30]}, r)
r = MG.copertura([n_(1, "Centro", 10, [1]), n_(2, "Spezie", 10, [1]), n_(3, "Oro", 20, [1])],
                 [c_(1, 1, 2), c_(2, 1, 3)], AA, PP)
verifica("contrario: il modello dice «A2» e cita una pagina di A1: non copre", r["scoperti"] == [20], r)
r = MG.copertura([n_(1, "Centro", 10, [1]), n_(2, "Spezie", 10, [1]),
                  n_(3, "Oro", 20, [2], avvisi=[MG.DA_CONTROLLARE])],
                 [c_(1, 1, 2), c_(2, 1, 3)], AA, PP)
verifica("contrario: un concetto con un avviso non copre", r["scoperti"] == [20], r)
r = MG.copertura([n_(1, "Centro", 10, [1]), n_(2, "Spezie", 10, [1]),
                  n_(3, "Oro", 20, [2], avvisi=[MG.DA_CONTROLLARE], stato="tenuto")],
                 [c_(1, 1, 2), c_(2, 1, 3)], AA, PP)
verifica("tenuto da una persona, con l'avviso, copre", r["scoperti"] == [], r)
r = MG.copertura(N, [c_(1, 1, 2), c_(2, 1, 3, debole=True)], AA, PP)
verifica("contrario: legato solo da un collegamento debole non copre", r["scoperti"] == [20], r)
r = MG.copertura([n_(1, "Centro", 10, [1]), n_(2, "Spezie", 10, [1]), n_(3, "Gli effetti", None, [])],
                 [c_(1, 1, 2), c_(2, 1, 3)], AA, PP)
verifica("il concetto che è il titolo dell'argomento lo copre", r["scoperti"] == [], r)
r = MG.copertura([n_(1, "Centro", 10, [1], autore="persona", stato="tenuto"),
                  n_(2, "Mio", 20, [], autore="persona", stato="tenuto")], [c_(1, 1, 2)], AA, PP)
verifica("scritto a mano: conta l'argomento scelto, anche senza pagine", r["scoperti"] == [], r)
verifica("una mappa vuota: tutti fuori, niente eccezioni",
         MG.copertura([], [], AA, PP) == {"coperti": [], "scoperti": [10, 20], "esclusi": [30]})


# ═══════════════════════════ 2. le richieste ═══════════════════════════
print("— le richieste")
st, vid, ids, lett = prepara(nome="richieste")
v = st.verifica(LEO, vid)
pagine = st._pagine_di(vid)
args = st._argomenti_per_carte(vid)
rif, arif = A.riferimenti(pagine), G.argomenti_rif(args)
verifica("la generale: niente «da 6 a 10», ogni argomento ha un concetto, il tetto dalla "
         "configurazione", "da 6 a 10" not in MG.REGOLE and "ogni argomento confermato" in MG.REGOLE
         and "al più 23 concetti" in MG.messaggi(v, rif, arif, 23)[1]["content"])
a2 = args[1]
sue = MG.pagine_di(a2, pagine)
c = MG.corpo_parte("qwen", v, A.riferimenti(sue), G.argomenti_rif([a2]))
t = c["messages"][1]["content"]
verifica("la parte: le sole pagine dell'argomento e il solo argomento, in busta; niente tool, schema "
         "guidato, temperatura 0, thinking spento",
         "[P1 · pagina stampata 113]" in t and "[P2" not in t
         and "A1: Il Portogallo e la rotta africana (P1)" in t and "Colombo e il Nuovo" not in t
         and "tools" not in c and c["format"] == MG.SCHEMA and c["think"] is False
         and c["options"]["temperature"] == 0 and c["messages"][0]["content"] == A.SISTEMA)
nn, cc = MG.scheletro(SENZA_A3["triple"], rif, arif, 20)
m = MG.messaggi_copertura(v, rif, arif, nn, [args[2]["id"]])[1]["content"]
verifica("la mirata: i concetti che ci sono, il solo argomento che manca, le sue sole pagine, coi "
         "codici di prima",
         "- Costantinopoli" in m and "A3: Cristoforo Colombo e il Nuovo Mondo (P4)" in m
         and "[P4 · pagina stampata 114]" in m and "[P2" not in m and "A1:" not in m
         and "concetti della mappa" in m)
aost = {"id": 99, "titolo": "Misto", "pagine": [ids["p112"], ids["p117"]]}
m = MG.messaggi_copertura(v, rif, arif + [("A4", aost)], nn, [99])[1]["content"]
verifica("la mirata non manda le pagine con istruzioni", "[P2" in m and "[P8" not in m
         and "annullata" not in m.lower())
fir = MG.firma_parte(a2, pagine, "attiva")
alt = MG.altri_sulle_pagine({"id": 1, "pagine": [5]}, [
    {"id": 1, "titolo": "Io", "pagine": [5]}, {"id": 2, "titolo": "Vicino", "pagine": [5, 6]},
    {"id": 3, "titolo": "Lontano", "pagine": [7]}])
t = MG.messaggi_parte(v, A.riferimenti(sue), G.argomenti_rif([a2]), 16, alt)[1]["content"]
verifica("la parte dice, in busta, chi altro sta sulle stesse pagine; senza nessuno, niente",
         alt == ["Vicino"] and "- Vicino" in t and "altri argomenti" in t
         and "altri argomenti" not in MG.messaggi_parte(v, A.riferimenti(sue),
                                                        G.argomenti_rif([a2]))[1]["content"])
verifica("la firma di una parte: non cambia per le pagine di un altro argomento, cambia col titolo, "
         "con le sue pagine e col modo",
         fir == MG.firma_parte(a2, [p for p in pagine if int(p["id"]) in a2["pagine"]], "attiva")
         and fir != MG.firma_parte({**a2, "titolo": "Altro"}, pagine, "attiva")
         and fir != MG.firma_parte(a2, pagine, "ombra")
         and fir != MG.firma_parte({**a2, "pagine": [ids["p114"]]}, pagine, "attiva"))
verifica("la firma della generale è nuova: uno scheletro del modello mai toccato si rifà",
         MG.firma(args, pagine, "attiva") != __import__("hashlib").sha256(
             ("mappa:" + G.firma(args, pagine, "attiva")).encode()).hexdigest()[:16])


# ═══════════════════════════ 3. il giro ═══════════════════════════
print("— il giro")
def chi_dice(*risposte):
    """Un `chiedi` che ridà le risposte in ordine e ricorda le richieste."""
    coda, viste = list(risposte), []

    def chiedi(messaggi, schema, max_token):
        viste.append((messaggi[-1]["content"], schema, max_token))
        x = coda.pop(0) if coda else {"triple": []}
        return x if x is None or isinstance(x, str) else json.dumps(x, ensure_ascii=False)
    return chiedi, viste


chiedi, viste = chi_dice(GENERALE)
r = MG.rete(chiedi, v, rif, arif, 20, titolo=v.get("argomento"), argomenti=args, pagine=pagine)
verifica("tutti gli argomenti dentro: una richiesta sola, una parte connessa",
         len(viste) == 1 and r["forma"]["scoperti_prima"] == 0 and r["forma"]["prima"] == 1
         and not r["rotto"], r["forma"])
chiedi, viste = chi_dice(SENZA_A3, MIRATA)
r = MG.rete(chiedi, v, rif, arif, 20, titolo=v.get("argomento"), argomenti=args, pagine=pagine)
cop = MG.copertura(r["nodi"], r["coll"], args, pagine)
verifica("un argomento fuori: la mirata lo porta dentro, le triple controllate insieme alle prime",
         len(viste) == 2 and MG.INIZIO_COPERTURA in viste[1][0] and r["forma"]["scoperti_prima"] == 1
         and cop["scoperti"] == [] and any(n["testo"] == "Cristoforo Colombo" for n in r["nodi"]),
         (r["forma"], cop))
chiedi, viste = chi_dice(SENZA_A3, {"triple": [
    tripla("Le scoperte geografiche", "portano a", "La macchina a vapore", "A3", "P4")]})
r = MG.rete(chiedi, v, rif, arif, 20, titolo=v.get("argomento"), argomenti=args, pagine=pagine)
cop = MG.copertura(r["nodi"], r["coll"], args, pagine)
inventato = next(n for n in r["nodi"] if n["testo"] == "La macchina a vapore")
verifica("un concetto inventato dalla mirata: da_controllare e non copre, la mappa lo dice",
         MG.DA_CONTROLLARE in inventato["avvisi"] and cop["scoperti"] == [args[2]["id"]], cop)
chiedi, viste = chi_dice(SENZA_A3, "non è json")
r = MG.rete(chiedi, v, rif, arif, 20, titolo=v.get("argomento"), argomenti=args, pagine=pagine)
verifica("una mirata illeggibile lascia la mappa di prima; un argomento resta fuori",
         not r["rotto"] and r["forma"]["copertura_rotta"] == 1 and len(r["nodi"]) == 3
         and MG.copertura(r["nodi"], r["coll"], args, pagine)["scoperti"] == [args[2]["id"]])
chiedi, viste = chi_dice({"triple": [tripla("La verifica", "non si fa più", "Studiare", "A1", "P2")]},
                         {"triple": []})
chiedi2, viste2 = chi_dice("non è json", "non è json")
r = MG.rete(chiedi2, v, rif, arif, 20, argomenti=args, pagine=pagine)
verifica("la prima illeggibile: rotto, nessuna mirata", r["rotto"] and len(viste2) == 1 and not r["nodi"])
tondo, viste3 = chi_dice(None, GENERALE)
r = MG.rete(tondo, v, rif, arif, 20, titolo=v.get("argomento"), argomenti=args, pagine=pagine)
verifica("in tondo fino a max_tokens: la prima si rifà una volta", len(viste3) == 2 and r["nodi"])
# Il tetto: prima un concetto per argomento
molte = [tripla("Centro", "ha", f"Causa {i}", "A1", "P2") for i in range(1, 9)] + [
    tripla("Centro", "porta a", "Colombo", "A3", "P4"),
    tripla("Centro", "porta a", "Portogallo", "A2", "P3")]
nn, cc = MG.scheletro(molte, rif, arif, 5, titolo="Centro")
verifica("il tetto: prima un concetto per argomento, poi il quinto di un altro",
         {"Colombo", "Portogallo"} <= {n["testo"] for n in nn} and len(nn) == 5, [n["testo"] for n in nn])
verifica("i concetti ricordano tutti gli argomenti che le triple dicono",
         next(n for n in MG.scheletro([tripla("Oro", "viene da", "America", "A1", "P2"),
                                       tripla("Oro", "arriva in", "Spagna", "A3", "P4")], rif, arif, 9)[0]
              if n["testo"] == "Oro")["argomenti"] == [args[0]["id"], args[2]["id"]])
# Le isole: un secondo giro solo se il primo ha unito qualcosa e ne restano
TRE_ISOLE = {"triple": [tripla("Le scoperte geografiche", "cominciano con", "Il Portogallo", "A2", "P3"),
                        tripla("Cristoforo Colombo", "arriva in", "America", "A3", "P4"),
                        tripla("Costantinopoli", "cade per", "I Turchi", "A1", "P2")]}
UNA = {"collegamenti": [{"da": "C1", "relazione": "porta a", "a": "C3", "pagine": ["P4"]}]}
chiedi, viste = chi_dice(TRE_ISOLE, UNA, {"collegamenti": [{"da": "C1", "relazione": "nasce da",
                                                            "a": "C5", "pagine": ["P2"]}]})
r = MG.rete(chiedi, v, rif, arif, 20, titolo="Le scoperte geografiche", argomenti=args, pagine=pagine)
verifica("tre parti: due giri, il secondo con le sole parti che restano; niente deboli",
         len(viste) == 3 and r["forma"]["connessioni"] == 2 and r["forma"]["uniti"] == 2
         and r["forma"]["deboli"] == 0 and len(M.componenti(r["nodi"], r["coll"])) == 1, r["forma"])
chiedi, viste = chi_dice(TRE_ISOLE, {"collegamenti": []}, UNA)
r = MG.rete(chiedi, v, rif, arif, 20, titolo="Le scoperte geografiche", argomenti=args, pagine=pagine)
verifica("contrario: un giro che non unisce niente non si ripete; restano i deboli",
         len(viste) == 2 and r["forma"]["connessioni"] == 1 and r["forma"]["deboli"] == 2, r["forma"])
# La parte: le voci non studiabili via
a_ost = {"id": 77, "titolo": "Le scoperte", "pagine": [ids["p112"], ids["p117"]]}
sue = MG.pagine_di(a_ost, pagine)
rif_o, arif_o = A.riferimenti(sue), G.argomenti_rif([a_ost])
rif_pul, rif_ost = rif_o[0][0], rif_o[1][0]
USCITA_OSTILE = {"triple": [
    tripla("Le scoperte", "nascono da", "Costantinopoli", "A1", rif_pul),
    tripla("Le scoperte", "cercano", "Spezie", "A1", rif_pul),
    tripla("Le scoperte", "annunciano", "Diari di bordo", "A1", rif_ost),
    tripla("Le scoperte", "scrivi a", "compiti@example.com", "A1", rif_pul),
    tripla("La verifica", "non si fa più", "Studiare", "A1", rif_pul)]}
chiedi, viste = chi_dice(USCITA_OSTILE)
r = MG.rete(chiedi, v, rif_o, arif_o, 16, titolo="Le scoperte", parte=True)
testi = {n["testo"] for n in r["nodi"]}
verifica("nella parte le voci con un ordine o da una pagina con istruzioni non entrano, contate; "
         "nessuna seconda richiesta per loro",
         testi == {"Le scoperte", "Costantinopoli", "Spezie"} and r["forma"]["esclusi"] >= 3
         and len(viste) == 1 and len(r["coll"]) == 2
         and not any(set(x["avvisi"]) & set(MG.AVVISI_DURI) for x in r["nodi"] + r["coll"]),
         (testi, r["forma"]))
verifica("la radice della parte è il titolo, anche dopo le voci tolte",
         next(n for n in r["nodi"] if n.get("radice"))["testo"] == "Le scoperte")
nn, cc = MG.scheletro(USCITA_OSTILE["triple"], rif_o, arif_o, 20)
verifica("contrario: nello scheletro le stesse voci restano con l'avviso, decide la persona",
         "Diari di bordo" in {n["testo"] for n in nn}
         and any(MG.TESTO_ORDINE in x["avvisi"] for x in cc))
chiedi, viste = chi_dice({"triple": [
    tripla("Le scoperte", "nascono da", "Costantinopoli", "A1", rif_pul),
    tripla("Spezie", "vengono da", "India", "A1", rif_pul)]},
    {"collegamenti": [{"da": "C1", "relazione": "cercano", "a": "C3", "pagine": [rif_pul]}]})
r = MG.rete(chiedi, v, rif_o, arif_o, 16, titolo="Le scoperte", parte=True)
verifica("una parte a isole ha la seconda passata anche lei", len(viste) == 2
         and r["forma"]["connessioni"] == 1 and r["forma"]["uniti"] == 1
         and len(M.componenti(r["nodi"], r["coll"])) == 1, r["forma"])
chiedi, viste = chi_dice({"triple": [
    tripla("Le scoperte", "nascono da", "Costantinopoli", "A1", rif_pul),
    tripla("Spezie", "vengono da", "India", "A1", rif_pul)]}, "non è json")
r = MG.rete(chiedi, v, rif_o, arif_o, 16, titolo="Le scoperte", parte=True)
verifica("le isole che restano in una parte: il collegamento debole, mai un fatto; una seconda "
         "passata illeggibile non ne chiede un'altra", len(viste) == 2 and r["forma"]["deboli"] == 1 and any(c.get("debole") for c in r["coll"])
         and len(MG.parti_fondate(r["nodi"], r["coll"])) == 2)
st.close()


# ═══════════════════════════ 4. il lettore ═══════════════════════════
print("— il lettore")
PA.azzera()
st, vid, ids, lett = prepara(nome="giro")
PA.rispondi(GENERALE, PARTE, PARTE, PARTE)
lett.giro()
righe = st.dati.tutti("SELECT tipo, stato, origine, aiuto FROM studio_mappe WHERE verifica = ? ORDER BY id",
                      (vid,))
verifica("un giro: la generale e una parte per argomento, quattro richieste, una riga per mappa",
         len(PA.F.richieste) == 4 and [r_["tipo"] for r_ in righe] == ["scheletro", "parte", "parte", "parte"]
         and all(r_["stato"] == "proposta" and r_["origine"] == "modello" for r_ in righe), str(righe)[:300])
vm = st.vista_mappe(LEO, vid)
pp = vm["parti"]
verifica("la vista: le parti nell'ordine del piano, coi titoli, la mappa dalla radice coi livelli",
         pp["accese"] and not pp["nascoste"] and [x["numero"] for x in pp["voci"]] == [1, 2, 3]
         and pp["voci"][1]["titolo"] == "Il Portogallo e la rotta africana"
         and pp["voci"][1]["mappa"]["tipo"] == "parte" and pp["voci"][1]["concetti"] == 4
         and pp["voci"][1]["mappa"]["nodi"][0]["livello"] == 0
         and max(n["livello"] for n in pp["voci"][1]["mappa"]["nodi"]) == 2, str(pp)[:400])
verifica("la generale ha la sua copertura per la pagina",
         vm["scheletro"]["copertura"] == {"coperti": 3, "totale": 3, "fuori": [], "esclusi": []},
         vm["scheletro"].get("copertura"))
verifica("la home e la voce: solo il conto delle parti",
         st.home(LEO)["verifiche"][0]["mappa"]["parti"] == 3)
m = lett.stato()["mappa"]
verifica("le misure: parti e concetti, mai i testi", m["parti"] == 3 and m["parti_concetti"] == 12
         and m["generazioni"] == 1 and m["coperture"] == 0, m)
verifica("il registro senza concetti né titoli",
         any("mappa dell'argomento" in x for x in PA.log_righe)
         and not any("Vasco" in x or "Enrico" in x or "Portogallo" in x for x in PA.log_righe))
n0 = len(PA.F.richieste)
lett.giro()
verifica("la stessa firma: niente da fare", len(PA.F.richieste) == n0 and not st.verifiche_per_mappa())
# Una rinomina: la generale e quella parte sola
aid = st.argomenti(LEO, vid)[1]["id"]
st.rinomina_argomento(LEO, aid, "La rotta portoghese")
PA.rispondi(GENERALE, PARTE)
lett.giro()
verifica("una rinomina rifà la generale e quella parte, non le altre",
         len(PA.F.richieste) == n0 + 2 and st.vista_mappe(LEO, vid)["parti"]["voci"][1]["titolo"]
         == "La rotta portoghese", str(len(PA.F.richieste) - n0))
st.close()

# Un passo alla volta
PA.azzera()
st, vid, ids, lett = prepara(nome="passi")
PA.rispondi(GENERALE, PARTE, PARTE, PARTE)
v0 = st.verifiche_per_mappa()[0]
verifica("la riga da fare dice cosa manca", v0["_generale"] and len(v0["_parti"]) == 3)
e1 = lett.prepara_mappe(v0, passi=1)
verifica("`passi=1`: solo la generale", e1 == "proposto" and len(PA.F.richieste) == 1
         and st.vista_mappe(LEO, vid)["scheletro"] is not None)
v1 = st.verifiche_per_mappa()[0]
verifica("poi restano le parti, senza la generale", not v1["_generale"] and len(v1["_parti"]) == 3)
e2 = lett.prepara_mappe(vid)
verifica("`prepara_mappe(id)`: l'ingresso per la #384 fa tutto ciò che resta",
         e2 == "proposto" and len(PA.F.richieste) == 4 and not st.verifiche_per_mappa())
verifica("niente da fare: «fatto», nessuna richiesta",
         lett.prepara_mappe(vid) == "fatto" and len(PA.F.richieste) == 4)
st.close()

# Una parte che non riesce
PA.azzera()
ora0 = PA.ORA[0]
try:
    st, vid, ids, lett = prepara(nome="fallita")
    PA.rispondi(GENERALE, PARTE, "non è json", "non è json", PARTE)
    lett.prepara_mappe(vid)
    voci = st.vista_mappe(LEO, vid)["parti"]["voci"]
    verifica("una parte illeggibile (rifatta non si rifà: JSON, non in tondo) lascia le altre",
             voci[0]["mappa"] is not None and voci[1]["mappa"] is None and voci[1]["esito"] == MG.ROTTO,
             str([(x["esito"], x["concetti"]) for x in voci]))
    # L'eccezione nostra: l'esito «errore», la mappa di prima resta, si riprova dopo un'ora
    PA.azzera()
    while st.verifiche_per_mappa():
        PA.rispondi(PARTE)
        if lett.prepara_mappe(vid) == "fatto":
            break
    aid = st.argomenti(LEO, vid)[0]["id"]
    prima = st.vista_mappe(LEO, vid)["parti"]["voci"][0]["concetti"]
    vera_rete = MG.rete
    def _rotta(*a, **k):
        raise RuntimeError("prova")
    st.rinomina_argomento(LEO, aid, "Le cause del viaggio")
    MG.rete = _rotta
    genera_orig = lett.genera_mappa
    lett.genera_mappa = lambda v_: "proposto"
    try:
        e = lett.prepara_mappe(vid)
    finally:
        MG.rete = vera_rete
    v_ = st.vista_mappe(LEO, vid)["parti"]["voci"][0]
    verifica("un'eccezione nostra in una parte: esito «errore», resta la mappa di prima",
             e == "errore" and v_["esito"] == MG.ERRORE and v_["concetti"] == prima, f"{e} {v_['esito']}")
    verifica("con l'errore la parte non si richiede subito",
             not any(a_["id"] == aid for r_ in st.verifiche_per_mappa() for a_ in r_["_parti"]))
    import datetime
    PA.ORA[0] = ora0 + datetime.timedelta(hours=2)
    lett._riprova_dopo = 0.0
    verifica("dopo un'ora si riprova", any(a_["id"] == aid for r_ in st.verifiche_per_mappa()
                                           for a_ in r_["_parti"]))
    MG.rete = _rotta
    try:
        for i in (2, 3):
            lett.genera_parte(st.verifiche_per_mappa()[0], next(
                a_ for a_ in st.verifiche_per_mappa()[0]["_parti"] if a_["id"] == aid))
            PA.ORA[0] = PA.ORA[0] + datetime.timedelta(hours=2)
    finally:
        MG.rete = vera_rete
    verifica("al terzo errore con la stessa firma si ferma, finché la firma non cambia",
             not any(a_["id"] == aid for r_ in st.verifiche_per_mappa() for a_ in r_["_parti"])
             and any("ferma dopo 3 errori" in x for x in PA.log_righe))
    st.rinomina_argomento(LEO, aid, "Le cause, di nuovo")
    verifica("la firma cambia e riparte", any(a_["id"] == aid for r_ in st.verifiche_per_mappa()
                                              for a_ in r_["_parti"]))
    lett.genera_mappa = genera_orig
    st.close()
finally:
    PA.ORA[0] = ora0

# Argomento cambiato mentre si genera
PA.azzera()
st, vid, ids, lett = prepara(nome="cambiata")
v0 = st.verifiche_per_mappa()[0]
a0 = v0["_parti"][0]
fir = MG.firma_parte(a0, v0["_pagine"], v0["_modo"])
st.rinomina_argomento(LEO, a0["id"], "Un altro titolo")
verifica("argomento cambiato durante la generazione: niente scritto",
         st.proponi_parte(vid, a0["id"], fir, [], [], MG.PROPOSTO, "attiva") is None
         and not st.dati.tutti("SELECT id FROM studio_mappe WHERE tipo = 'parte'"))
st.close()

# Sole pagine con istruzioni
PA.azzera()
st, vid, ids, lett = prepara(nome="ostile", titoli=(("I diari di bordo", ("p117",)),
                                                    ("Colombo", ("p114",))))
PA.rispondi({"triple": [tripla("Colombo", "arriva in", "America", "A2", "P4"),
                        tripla("Colombo", "parte da", "Palos", "A2", "P4")]}, PARTE)
lett.prepara_mappe(vid)
voci = st.vista_mappe(LEO, vid)["parti"]["voci"]
cop = st.vista_mappe(LEO, vid)["scheletro"]["copertura"]
testo_ostile = next(p["testo"] for p in PA.MATERIALI["storia"]["pagine"] if p["id"] == "p117")
richieste = json.dumps(PA.F.richieste, ensure_ascii=False)
verifica("un argomento su sole pagine con istruzioni: niente richiesta per lui, la pagina lo dice",
         len(PA.F.richieste) == 2 and voci[0]["esito"] == MG.SOLO_ISTRUZIONI and voci[0]["mappa"] is None
         and voci[1]["mappa"] is not None and cop["esclusi"] == ["I diari di bordo"] and cop["fuori"] == [],
         str(voci)[:300])
verifica("e non si riprova", not st.verifiche_per_mappa())
st.close()

# Con lo scheletro della persona
PA.azzera()
st, vid, ids, lett = prepara(nome="amano")
mid = st.scrivi_scheletro(LEO, vid)
st.nodo_mappa(LEO, mid, "Il mio concetto")
PA.rispondi(PARTE, PARTE, PARTE)
lett.prepara_mappe(vid)
vm = st.vista_mappe(LEO, vid)
verifica("uno scheletro della persona non si tocca, le parti si fanno",
         len(PA.F.richieste) == 3 and vm["scheletro"]["id"] == mid and len(vm["scheletro"]["nodi"]) == 1
         and all(x["mappa"] for x in vm["parti"]["voci"]) and "copertura" not in vm["scheletro"])
st.close()

# Ombra e spenta
PA.azzera()
st, vid, ids, lett = prepara({"studio_mappa_genera": "ombra"}, nome="ombra")
PA.rispondi(GENERALE, PARTE, PARTE, PARTE)
lett.prepara_mappe(vid)
vm = st.vista_mappe(LEO, vid)
stati = {r_["stato"] for r_ in st.dati.tutti("SELECT stato FROM studio_mappe WHERE tipo = 'parte'")}
verifica("ombra: le parti generate in stato «ombra», mai alla persona (vista, home)",
         stati == {"ombra"} and vm["parti"]["voci"] == [] and not vm["parti"]["accese"]
         and st.home(LEO)["verifiche"][0]["mappa"]["parti"] == 0, str(vm["parti"])[:200])
st.close()
PA.azzera()
st, vid, ids, lett = prepara({"studio_mappa_parti": "spenta"}, nome="parti_spente")
PA.rispondi(GENERALE)
lett.giro()
vm = st.vista_mappe(LEO, vid)
verifica("`studio_mappa_parti: spenta`: solo la generale", len(PA.F.richieste) == 1
         and vm["scheletro"] is not None and vm["parti"]["voci"] == [] and not st.verifiche_per_mappa())
st.close()
PA.azzera()
st, vid, ids, lett = prepara({"studio_mappa_genera": "spenta"}, nome="tutto_spento")
lett.giro()
verifica("`studio_mappa_genera: spenta`: niente di niente", not PA.F.richieste
         and not st.dati.tutti("SELECT id FROM studio_mappe"))
st.close()


# ═══════════════════════════ 5. chi le vede e chi le cambia ═══════════════════════════
print("— chi le vede e chi le cambia")
PA.azzera()
st, vid, ids, lett = prepara(nome="permessi")
PA.rispondi(GENERALE, PARTE, PARTE, PARTE)
lett.prepara_mappe(vid)
vm = st.vista_mappe(LEO, vid)
mp = vm["parti"]["voci"][1]["mappa"]
pid, nod, col = mp["id"], mp["nodi"][0]["id"], mp["collegamenti"][0]["id"]
AZIONI = {"nodo_mappa": lambda: st.nodo_mappa(LEO, pid, "x"),
          "togli_nodo": lambda: st.togli_nodo(LEO, pid, nod),
          "collega": lambda: st.collega(LEO, pid, nod, nod + 1, "x"),
          "togli_collegamento": lambda: st.togli_collegamento(LEO, pid, col),
          "sposta_nodo": lambda: st.sposta_nodo(LEO, pid, nod, 0.2, 0.2),
          "riempi": lambda: st.riempi(LEO, pid, nod, "x"),
          "tieni_mappa": lambda: st.tieni_mappa(LEO, pid, nodo=nod),
          "conferma_scheletro": lambda: st.conferma_scheletro(LEO, pid),
          "riordina_mappa": lambda: st.riordina_mappa(LEO, pid),
          "riapri_scheletro": lambda: st.riapri_scheletro(LEO, pid),
          "rifai_mappa": lambda: st.rifai_mappa(LEO, pid),
          "controlla_mappa": lambda: st.controlla_mappa(LEO, pid),
          "carte_dagli_errori": lambda: st.carte_dagli_errori(LEO, pid)}
rifiutate = {k: solleva(f, NonTrovata) for k, f in AZIONI.items()}
verifica("la mappa di una parte si legge soltanto: ogni azione la rifiuta, anche per il tutore",
         all(rifiutate.values()) and solleva(lambda: st.nodo_mappa(ANDREA, pid, "x"), NonTrovata), rifiutate)
verifica("le parti non confondono le altre mappe: `_mappe_di` non le vede",
         set(st._mappe_di(vid)) == {M.SCHELETRO})
verifica("il tutore le vede; un altro adulto no",
         st.vista_mappe(ANDREA, vid)["parti"]["voci"][1]["mappa"] is not None
         and solleva(lambda: st.vista_mappe(BRUNO, vid), NonTrovata))
sk = vm["scheletro"]["id"]
r0 = st.conferma_scheletro(LEO, sk)
sk_prima = st._riga_mappa(sk)
mia = st.inizia_mappa(LEO, vid, M.STUDENTE)
rm = st._riga_mappa(mia)
verifica("«Fai la tua» dalla sola generale: stessi concetti, niente delle parti",
         sorted(int(n["da"]) for n in rm["nodi"]) == sorted(
             int(n["id"]) for n in M.tenuti(sk_prima)[0])
         and "Enrico il Navigatore" not in json.dumps(rm["nodi"], ensure_ascii=False))
rc = st.controlla_mappa(LEO, mia)
verifica("il controllo del codice non cambia: dalla generale, gli esiti soliti",
         set(rc["caselle"].values()) <= {M.GIUSTA, M.SBAGLIATA, M.VUOTA}
         and rc["conti"]["caselle"] == len(rc["caselle"]))
memo = st.inizia_mappa(LEO, vid, M.MEMORIA)
vm = st.vista_mappe(LEO, vid)
dump = json.dumps(vm["parti"], ensure_ascii=False)
verifica("a memoria aperta: le parti senza testi per chi la fa",
         vm["a_memoria"] and vm["parti"]["nascoste"] and "Enrico" not in dump and "Vasco" not in dump
         and all(x["mappa"] is None for x in vm["parti"]["voci"]), dump[:200])
verifica("il tutore le vede anche con la mappa a memoria aperta",
         st.vista_mappe(ANDREA, vid)["parti"]["voci"][1]["mappa"] is not None)
st.controlla_mappa(LEO, memo)
verifica("dopo «Controlla» tornano", st.vista_mappe(LEO, vid)["parti"]["voci"][1]["mappa"] is not None)
lib = st.inizia_libera(LEO, vid)
vm = st.vista_mappe(LEO, vid)
verifica("mappa da zero aperta: le parti senza testi",
         vm["a_libera"] and vm["parti"]["nascoste"]
         and "Enrico" not in json.dumps(vm, ensure_ascii=False))
st.finisci_libera(LEO, lib)
verifica("dopo «Ho finito» tornano", st.vista_mappe(LEO, vid)["parti"]["voci"][1]["mappa"] is not None)
vera_prova = st._prova_aperta
st._prova_aperta = lambda v_: {"id": 1}
vm = st.vista_mappe(LEO, vid)
verifica("durante una prova: nascoste alla persona, non al tutore",
         vm["parti"]["nascoste"] and "Enrico" not in json.dumps(vm["parti"], ensure_ascii=False)
         and st.vista_mappe(ANDREA, vid)["parti"]["voci"][1]["mappa"] is not None)
st._prova_aperta = vera_prova
st.close()


# ═══════════════════════════ 6. la forma ═══════════════════════════
print("— la forma")
nodi20 = [{"id": i, "testo": f"Concetto {i}"} for i in range(1, 21)]
coll20 = [{"id": i, "da": 1, "a": i + 1} for i in range(1, 8)] + [
    {"id": 100 + i, "da": 2 + i % 7, "a": 9 + i} for i in range(12)]
pos = M.disposizione(nodi20, coll20)
vicini = [(a, b) for a in pos for b in pos if a < b
          and abs(pos[a][0] - pos[b][0]) < 0.46 and abs(pos[a][1] - pos[b][1]) < 0.06]
verifica("20 concetti: a righe dalla radice, due per riga, niente riquadri sovrapposti, dentro la mappa",
         not vicini and pos[1] == (0.5, 0.08) and {x for x, _y in list(pos.values())[1:]} == {0.25, 0.75}
         and all(0.05 <= x <= 0.95 and 0.05 <= y <= 0.95 for x, y in pos.values()), vicini[:5])
verifica("chi è più vicino alla radice sta più in alto",
         max(pos[i][1] for i in range(2, 9)) <= min(pos[i][1] for i in range(9, 21)) + 0.1)
piccola = M.disposizione(nodi20[:8], coll20[:7])
verifica("fino a 8 concetti i giri attorno al centro, come sempre", M.TELA_NODI == 8 and piccola[1] == (0.5, 0.5))
liv = M.livelli([{"id": 1, "testo": "a", "radice": True}, {"id": 2, "testo": "b"}, {"id": 3, "testo": "c"},
                 {"id": 4, "testo": "d"}], [{"da": 2, "a": 1}, {"da": 2, "a": 3}])
verifica("i livelli dalla radice, i versi non contano, chi è staccato in fondo",
         liv == {1: 0, 2: 1, 3: 2, 4: 3}, liv)
verifica("il tetto di una parte cresce con le sue pagine, fino a 30",
         M.parte_nodi(PA.Config(), 1) == 16 and M.parte_nodi(PA.Config(), 3) == 24
         and M.parte_nodi(PA.Config(), 9) == 30)
verifica("`studio_mappa_parti`: attiva di serie, un valore strano vale attiva",
         M.modo_parti(PA.Config()) == "attiva"
         and M.modo_parti(types.SimpleNamespace(studio_mappa_parti="boh")) == "attiva"
         and M.modo_parti(types.SimpleNamespace(studio_mappa_parti="spenta")) == "spenta")
try:
    from calliope.studio import mappa_pdf
    pos = M.disposizione([{"id": i, "testo": "x"} for i in range(1, 27)], coll20)
    nodi26 = [{"id": i, "testo": f"Concetto numero {i}", "x": pos.get(i, (0.5, 0.5))[0],
               "y": pos.get(i, (0.5, 0.5))[1], "pagine": [1]} for i in range(1, 27)]
    pdf = mappa_pdf.render({"nodi": nodi26, "collegamenti": coll20}, "Leo", "Storia", "2026-11-05", {1: "p. 112"})
    verifica("il PDF della mia mappa con 26 concetti si fa", pdf[:4] == b"%PDF" and len(pdf) > 1000)
except ModuleNotFoundError:
    print("ok  (fpdf2 non c'è: il PDF non si prova)")


# ═══════════════════════════ 7. il banco ═══════════════════════════
print("— il banco")
from studio_vllm_finto import VllmFinto  # noqa: E402

mat = PA.B.carica_materiali()
usc = Path(tempfile.mkdtemp(prefix="banco-parti-"))
fin = VllmFinto(materiali=mat)
ris = PA.B.fase_mappa(fin, mat, {}, usc, lambda m_: None)
x = ris["storia"]
verifica("la fase «mappa»: una parte per argomento, sole pagine con istruzioni senza richiesta",
         len(x["parti"]) == len(mat["storia"]["argomenti"])
         and next(p for p in x["parti"] if p["titolo"] == "I diari di bordo")["esito"] == MG.SOLO_ISTRUZIONI
         and sum(k == "parte" for _v, k in fin.richieste if _v == "storia") == len(x["parti"]) - 1,
         str([(p["titolo"], p["esito"]) for p in x["parti"]])[:300])
verifica("la copertura del codice e quella della verità, separate",
         set(x["copertura"]) == {"coperti", "scoperti", "esclusi"}
         and x["verita"]["argomenti"] == sum(not a.get("facoltativo") for a in mat["storia"]["argomenti"])
         and x["verita"]["domande"] > 0 and 0 <= x["verita"]["domande_trovate"] <= x["verita"]["domande"])
ve = PA.B.misura_verita(mat["storia"], [{"testo": "Cristoforo Colombo nel 1492"},
                                        {"testo": "Verifica annullata", "avvisi": [MG.TESTO_ORDINE]}], [])
verifica("la verità: le chiavi degli argomenti, le voci con un ordine non contano",
         ve["argomenti_trovati"] == 1 and "Cristoforo Colombo e il Nuovo Mondo" not in ve["fuori"], ve)
rie = PA.B.scrivi_riepilogo(usc, {"mappa": ris, "modello": "finto"})
verifica("il riepilogo dice copertura, verità, parti e tempi",
         "copertura (dal codice)" in rie and "dalla verità: argomenti" in rie and "parti: " in rie
         and "dalla verità nelle parti" in rie and "voci tolte" in rie, rie[-600:])

print(f"\n{'TUTTO OK' if not errori else f'{errori} ERRORI'}")
sys.exit(1 if errori else 0)
