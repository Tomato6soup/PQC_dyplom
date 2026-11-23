# Tworzy run_matrix_v5.sh i locustfile_v5_batch.py z oryginalow v3b (oryginaly zostaja bez zmian)
def zamien(tekst, stare, nowe):
    if tekst.count(stare) != 1:
        raise SystemExit("BLAD: fragment znaleziono " + str(tekst.count(stare)) + " razy: " + stare)
    return tekst.replace(stare, nowe)

m = open("run_matrix_v3b.sh").read()
m = zamien(m, "BATCH_SIZE=1 ", "")
m = zamien(m, "-f locustfile_v3.py", "-f locustfile_v5_batch.py")
open("run_matrix_v5.sh", "w").write(m)

l = open("locustfile_v3.py").read()
l = zamien(l, 'PACING_S = float(os.getenv("PACING_S", "0.05"))\n',
           'PACING_S = float(os.getenv("PACING_S", "0.05"))\nBATCH_MODE = os.getenv("BATCH_MODE", "seq")\n')
l = zamien(l, "            if ok and PACING_S > 0:\n",
           '            if ok and PACING_S > 0 and BATCH_MODE != "burst":\n')
l = zamien(l, "            exception=last_exc if sent < BATCH_SIZE else None,\n        )\n",
           "            exception=last_exc if sent < BATCH_SIZE else None,\n        )\n"
           '        if BATCH_MODE == "burst" and PACING_S > 0:\n'
           "            time.sleep(BATCH_SIZE / (1.0 / PACING_S))\n")
open("locustfile_v5_batch.py", "w").write(l)
print("OK: run_matrix_v5.sh i locustfile_v5_batch.py gotowe")
