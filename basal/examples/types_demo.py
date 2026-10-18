"""Sends one request per decision type (and a combined, structured request) to a running basal server and prints
request + response. Used to produce the examples in the README and the technical report.

  python basal/examples/types_demo.py --url http://127.0.0.1:8000/v1/systemone
"""
import argparse
import json

import httpx

REQUESTS = {
    "choice": {
        "state": "Klient: od wczoraj nie mogę zalogować się do bankowości internetowej, system pokazuje błąd hasła.",
        "questions": {"dept": {"type": "choice", "instructions": "Do którego działu skierować zgłoszenie?",
                               "criteria": {"cards": "Reklamacje kart", "online": "Wsparcie bankowości elektronicznej",
                                            "loans": "Kredyty"}}}},
    "noul": {
        "state": "Umowa zawarta na odległość. Towar odebrano 3 marca 2025 r. Oświadczenie o odstąpieniu od umowy "
                 "wysłano 20 marca 2025 r. Regulamin: konsument może odstąpić od umowy w terminie 14 dni od objęcia "
                 "rzeczy w posiadanie; do zachowania terminu wystarczy wysłanie oświadczenia przed jego upływem.",
        "questions": {"in_time": {"type": "noul", "instructions": "Czy odstąpienie od umowy złożono w terminie?"}}},
    "score": {
        "state": "Zgłoszenie z oddziału w Gdańsku: od 7:40 nie działa żaden terminal płatniczy, klienci odchodzą od "
                 "kas, kolejka na 30 osób. Obejście: tylko gotówka.",
        "questions": {"urgency": {"type": "score", "instructions": "Jak pilne jest to zgłoszenie?",
                                  "criteria": ["niska — można zaplanować", "średnia — w ciągu kilku dni",
                                               "wysoka — dziś", "krytyczna — natychmiast"]}}},
    "fan_out": {  # several typed questions about one state in ONE request (answered independently)
        "state": {"ticket": "Dzień dobry, 12.05 zamówiłam czajnik (nr 88412), przyszedł z pękniętą obudową. "
                            "Proszę o wymianę albo zwrot pieniędzy. Anna Nowak",
                  "customer": {"segment": "VIP", "orders_last_year": 14}},
        "questions": {
            "category": {"type": "choice", "instructions": "Jaki jest rodzaj zgłoszenia?",
                         "criteria": {"complaint": "Reklamacja towaru", "delivery": "Opóźniona dostawa",
                                      "invoice": "Faktura", "other": "Inne"}},
            "needs_photo": {"type": "noul", "instructions": "Czy do rozpatrzenia potrzebne jest zdjęcie uszkodzenia?",
                            "criteria": {"true": "Tak, poprosić o zdjęcie", "false": "Nie, można rozpatrzyć od razu"}},
            "tone": {"type": "score", "instructions": "Jak zdenerwowana jest klientka?",
                     "criteria": {"calm": "spokojna", "annoyed": "zirytowana", "angry": "bardzo zdenerwowana"}}}},
    "structured_criteria": {  # options and instructions as JSON objects (serialised into the prompt)
        "state": "Page: checkout. Fields: [1] button 'Pay now' (enabled); [2] checkbox 'I accept the terms' "
                 "(unchecked); [3] link 'Back to cart'.",
        "questions": {"next_click": {
            "type": "choice",
            "instructions": {"goal": "Complete the purchase", "rule": "Required fields must be set before paying."},
            "criteria": {"1": {"element": "[1] Pay now", "role": "button"},
                         "2": {"element": "[2] I accept the terms", "role": "checkbox", "checked": False},
                         "3": {"element": "[3] Back to cart", "role": "link"}}}}},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000/v1/systemone")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = {}
    with httpx.Client(timeout=60) as c:
        for name, body in REQUESTS.items():
            c.post(a.url, json=body)  # warm-up (first request of a shape)
            r = c.post(a.url, json=body).json()
            out[name] = {"request": body, "response": r}
            print(f"=== {name}\n{json.dumps(r, ensure_ascii=False, indent=1)}")
        bad = {"state": "x", "questions": {"q": {"type": "choice", "criteria": [str(i) for i in range(12)]}}}
        r = c.post(a.url, json=bad)
        out["too_many_options"] = {"status": r.status_code, "response": r.json()}
        print(f"=== too_many_options {r.status_code} {r.json()}")
    if a.out:
        with open(a.out, "w") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
