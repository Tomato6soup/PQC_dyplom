import csv
CZASY = [30, 60, 90, 180]

def czytaj(p):
    with open(p, newline='') as f:
        r = csv.DictReader(f)
        return r.fieldnames, list(r)

def zbierz(typ):
    wiersze = []
    for c in CZASY:
        pola, rows = czytaj('wyniki_czas_' + str(c) + 's_' + typ + '.csv')
        for x in rows:
            x['czas_s'] = c
            x['zrodlo'] = 'seria_czasu'
            wiersze.append(x)
    pola, rows = czytaj('wyniki_v3b_' + typ + '.csv')
    for x in rows:
        if x['runtime'] == 'default':
            x['czas_s'] = 120
            x['zrodlo'] = 'v3b'
            wiersze.append(x)
    wiersze.sort(key=lambda x: (x['czas_s'], x['algo'], int(x['users']), int(x.get('run', 0) or 0)))
    wyj = 'wyniki_czas_wszystkie_' + typ + '.csv'
    with open(wyj, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['czas_s', 'zrodlo'] + pola)
        w.writeheader()
        w.writerows(wiersze)
    print(wyj, len(wiersze), 'wierszy')

zbierz('runs')
zbierz('summary')
